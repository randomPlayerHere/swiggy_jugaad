"""Agent loop tests. The LLM and the tool layer are both faked: these pin
down the loop's own contract — the event stream it yields, and that the
conversation history it leaves behind is always valid to send back, however
a turn ends."""

import json
from types import SimpleNamespace

import pytest

from swiggy_jugaad.bot import agent
from swiggy_jugaad.bot.session_state import get_or_create_state, reset_state
from swiggy_jugaad.mcp_client import SwiggyAuthExpired, SwiggyUnavailable

USER = 999


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_none=True):
        dumped = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            dumped["tool_calls"] = [
                {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
                for c in self.tool_calls
            ]
        return {k: v for k, v in dumped.items() if v is not None}


def tool_call(id_, name, arguments="{}"):
    return SimpleNamespace(id=id_, function=SimpleNamespace(name=name, arguments=arguments))


def says(content):
    return FakeMessage(content=content)


def calls(*tool_calls):
    return FakeMessage(tool_calls=list(tool_calls))


@pytest.fixture
def llm(monkeypatch):
    """Script the model's replies in order; records every messages list sent."""
    script: list = []
    sent: list[list[dict]] = []

    def fake_call_llm(messages, tool_choice):
        sent.append(messages)
        reply = script.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(choices=[SimpleNamespace(message=reply)]), "fake-model"

    monkeypatch.setattr(agent, "_call_llm", fake_call_llm)
    monkeypatch.setattr(agent, "get_user", lambda user_id: None)
    reset_state(USER)
    yield SimpleNamespace(script=script, sent=sent)
    reset_state(USER)


def assert_history_valid(history: list[dict]):
    """Every assistant tool_call is answered by a tool message before the
    next non-tool message — what the chat completions API requires."""
    open_ids: set[str] = set()
    for message in history:
        if message["role"] == "tool":
            open_ids.discard(message["tool_call_id"])
            continue
        assert not open_ids, f"unanswered tool calls {open_ids} before {message}"
        if message["role"] == "assistant":
            open_ids = {c["id"] for c in message.get("tool_calls", [])}
    assert not open_ids, f"unanswered tool calls at end: {open_ids}"


def run_turn(text="hi", **kwargs):
    return list(agent.iter_step(USER, text, **kwargs))


def test_plain_reply_is_one_llm_hop_and_a_reply(llm):
    llm.script.append(says("hello"))
    events = run_turn()
    assert [e["type"] for e in events] == ["llm_start", "llm_end", "reply"]
    assert events[1]["model"] == "fake-model"
    assert events[-1]["text"] == "hello"


def test_think_tags_are_stripped_from_replies(llm):
    llm.script.append(says("<think>internal musing</think>\nhello"))
    assert run_turn()[-1]["text"] == "hello"


def test_tool_exception_goes_back_to_the_model_and_turn_continues(llm, monkeypatch):
    def boom(name, args, user_id):
        raise ValueError("user 999 is not onboarded")

    monkeypatch.setattr(agent, "dispatch", boom)
    llm.script += [calls(tool_call("c1", "sync_orders")), says("let's set you up first")]

    events = run_turn()
    tool_end = next(e for e in events if e["type"] == "tool_end")
    assert tool_end["ok"] is False
    assert "not onboarded" in tool_end["result"]["error"]
    assert events[-1] == {"type": "reply", "text": "let's set you up first"}
    # the model saw the error as the tool's result
    tool_msg = next(m for m in llm.sent[1] if m["role"] == "tool")
    assert "not onboarded" in json.loads(tool_msg["content"])["error"]
    assert_history_valid(get_or_create_state(USER).history)


def test_auth_error_ends_turn_and_leaves_history_valid_for_the_next(llm, monkeypatch):
    def dispatch(name, args, user_id):
        raise SwiggyAuthExpired()

    monkeypatch.setattr(agent, "dispatch", dispatch)
    # two calls in one message: the second is never run, but must still be answered
    llm.script.append(calls(tool_call("c1", "list_addresses"), tool_call("c2", "get_pantry_status")))

    events = run_turn()
    assert events[-1]["type"] == "error"
    assert events[-1]["kind"] == "auth"
    assert_history_valid(get_or_create_state(USER).history)

    llm.script.append(says("back again"))
    assert run_turn("hello?")[-1] == {"type": "reply", "text": "back again"}
    assert_history_valid(llm.sent[-1][1:])


def test_swiggy_outage_ends_turn_with_plain_message(llm, monkeypatch):
    def dispatch(name, args, user_id):
        raise SwiggyUnavailable("502")

    monkeypatch.setattr(agent, "dispatch", dispatch)
    llm.script.append(calls(tool_call("c1", "list_addresses")))
    events = run_turn()
    assert events[-1]["kind"] == "swiggy"
    assert "502" not in events[-1]["text"]
    assert_history_valid(get_or_create_state(USER).history)


def test_malformed_tool_arguments_never_reach_dispatch(llm, monkeypatch):
    dispatched = []
    monkeypatch.setattr(agent, "dispatch", lambda *a: dispatched.append(a))
    llm.script += [calls(tool_call("c1", "suggest_recipes", "{not json")), says("ok")]

    events = run_turn()
    assert dispatched == []
    assert next(e for e in events if e["type"] == "tool_end")["ok"] is False
    assert_history_valid(get_or_create_state(USER).history)


def test_llm_outage_is_an_error_event(llm):
    llm.script.append(RuntimeError("no NIM model answered"))
    events = run_turn()
    assert events[-1]["type"] == "error"
    assert events[-1]["kind"] == "llm"


def test_no_more_tools_after_staging_a_cart(llm, monkeypatch):
    monkeypatch.setattr(agent, "dispatch", lambda name, args, user_id: {"total": 120})
    choices = []
    original = agent._call_llm

    def recording(messages, tool_choice):
        choices.append(tool_choice)
        return original(messages, tool_choice)

    monkeypatch.setattr(agent, "_call_llm", recording)
    llm.script += [calls(tool_call("c1", "start_gap_order", '{"address_id": "a", "ingredients": ["tomato"]}')), says("₹120, place it?")]
    run_turn()
    assert choices == ["auto", "none"]


def test_step_with_events_keeps_successful_tool_results_only(llm, monkeypatch):
    results = iter([{"household_size": 2, "diet": "veg"}, {"error": "nope"}])
    monkeypatch.setattr(agent, "dispatch", lambda name, args, user_id: next(results))
    llm.script += [calls(tool_call("c1", "get_household_profile"), tool_call("c2", "confirm_gap_order")), says("done")]

    reply, events = agent.step_with_events(USER, "hi")
    assert reply == "done"
    assert events == [{"tool": "get_household_profile", "result": {"household_size": 2, "diet": "veg"}}]


def test_each_message_is_a_new_turn(llm):
    llm.script += [says("a"), says("b")]
    run_turn()
    run_turn()
    assert get_or_create_state(USER).turn == 2
