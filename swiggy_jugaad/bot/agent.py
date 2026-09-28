import json
import logging
import re
import time
from collections.abc import Iterator

from openai import OpenAI

from swiggy_jugaad.config import NIM_API_KEY, NIM_BASE_URL, NIM_FALLBACK_MODEL, NIM_MODEL
from swiggy_jugaad.mcp_client import SwiggyAuthExpired, SwiggyError, SwiggyNotAuthenticated
from swiggy_jugaad.store.repo import get_user
from .prompts import RICH_UI_ADDENDUM, SYSTEM_PROMPT
from .session_state import get_or_create_state
from .tools import TOOL_SCHEMAS, dispatch

logger = logging.getLogger(__name__)

# Short timeout, no SDK-level retries: our own two-model fallback in
# _call_llm is the retry strategy. SDK defaults (600s read, 2 silent
# retries) would double up and hide a stuck call for minutes.
_client = OpenAI(api_key=NIM_API_KEY, base_url=NIM_BASE_URL, timeout=25.0, max_retries=0)
_MAX_TOOL_HOPS = 8
# After these, the next hop is forced to answer in text: the household has
# to see the cart (or the placed order) before anything else happens.
_NO_MORE_TOOLS_AFTER = {"start_gap_order", "confirm_gap_order"}

_LLM_DOWN = "Sorry, I'm having trouble reaching the model right now — try again in a moment."
_SWIGGY_DOWN = "Sorry, Swiggy's not cooperating right now — try that again in a moment."
_TOO_MANY_HOPS = "Sorry, I'm having trouble finishing that — can you rephrase?"

# Some NIM reasoning models leak their scratchpad into content.
_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def _call_llm(messages: list[dict], tool_choice: str):
    """(completion, model that answered). Falls back to the second model on
    any failure."""
    for model in (NIM_MODEL, NIM_FALLBACK_MODEL):
        try:
            completion = _client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,
                tools=TOOL_SCHEMAS,
                tool_choice=tool_choice,
                max_tokens=4096
            )
            return completion, model
        except Exception as e:
            logger.warning("[%s] FAILED for tool calling: %s", model, e)
            continue
    raise RuntimeError("no NIM model answered")


def _system_prompt(user_id: int, rich_ui: bool = False) -> str:
    """SYSTEM_PROMPT plus the household's current profile, read fresh each
    call so an onboard_user() mid-conversation is reflected on the next hop
    instead of a stale snapshot taken at session start."""
    user = get_user(user_id)
    if user is None:
        prompt = SYSTEM_PROMPT + "\n\nThis household has not been onboarded yet — get their household size and diet before anything else."
    else:
        prompt = SYSTEM_PROMPT + f"\n\nThis household is already onboarded: household_size={user.household_size}, diet={user.diet}."
    if rich_ui:
        prompt += "\n\n" + RICH_UI_ADDENDUM
    return prompt


def _ms_since(start: float) -> int:
    return round((time.monotonic() - start) * 1000)


def _parse_args(raw: str | None) -> dict | None:
    """The model's tool arguments, or None if they aren't a JSON object."""
    try:
        args = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return None
    return args if isinstance(args, dict) else None


def _close_unanswered(history: list[dict], tool_calls, answered: set[str], reason: str) -> None:
    """Every tool_call in an assistant message needs a matching tool message.
    Without one, the next request is rejected outright and the session stays
    broken until the process restarts. Close out whatever an early exit
    left open."""
    for call in tool_calls:
        if call.id not in answered:
            history.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps({"error": reason}),
            })


def step(user_id: int, user_text: str) -> str:
    reply, _events = step_with_events(user_id, user_text)
    return reply


def step_with_events(user_id: int, user_text: str) -> tuple[str, list[dict]]:
    """iter_step() collected into (final text, successful tool calls), for
    callers that don't stream."""
    reply = ""
    events: list[dict] = []
    for event in iter_step(user_id, user_text):
        if event["type"] == "tool_end" and event["ok"]:
            events.append({"tool": event["tool"], "result": event["result"]})
        elif event["type"] in ("reply", "error"):
            reply = event["text"]
    return reply, events


def iter_step(user_id: int, user_text: str, rich_ui: bool = False) -> Iterator[dict]:
    """One household message through the agent loop, as a stream of events
    a live UI can render while the turn is still running:

        {"type": "llm_start", "hop"}               {"type": "llm_end", "hop", "model", "ms"}
        {"type": "tool_start", "tool", "args"}     {"type": "tool_end", "tool", "result", "ms", "ok"}

    and always exactly one final {"type": "reply", "text"} or
    {"type": "error", "kind": "llm"|"auth"|"swiggy"|"internal", "text"}.

    A tool that raises for any reason other than Swiggy itself (bad
    arguments, an unonboarded user) becomes an {"error": ...} tool result,
    so the model can see what went wrong and recover in the same turn.
    Swiggy failures end the turn, but only after the history is left valid
    for the next one.
    """
    state = get_or_create_state(user_id=user_id)
    state.turn += 1
    state.history.append({"role": "user", "content": user_text})
    force_stop = False
    for hop in range(_MAX_TOOL_HOPS):
        messages = [{"role": "system", "content": _system_prompt(user_id, rich_ui)}, *state.history]
        yield {"type": "llm_start", "hop": hop}
        started = time.monotonic()
        try:
            completion, model = _call_llm(messages, tool_choice="none" if force_stop else "auto")
        except RuntimeError:
            logger.warning("user %s: no NIM model answered", user_id)
            state.history.append({"role": "assistant", "content": _LLM_DOWN})
            yield {"type": "error", "kind": "llm", "text": _LLM_DOWN}
            return
        yield {"type": "llm_end", "hop": hop, "model": model, "ms": _ms_since(started)}

        response = completion.choices[0].message
        state.history.append(response.model_dump(exclude_none=True))

        if not response.tool_calls:
            yield {"type": "reply", "text": _THINK_RE.sub("", response.content or "").strip()}
            return

        force_stop = False
        answered: set[str] = set()
        for call in response.tool_calls:
            name = call.function.name
            args = _parse_args(call.function.arguments)
            yield {"type": "tool_start", "tool": name, "args": args or {}}
            started = time.monotonic()

            fatal: tuple[str, str] | None = None
            try:
                if args is None:
                    result = {"error": "tool arguments were not a valid JSON object"}
                else:
                    result = dispatch(name, args, user_id)
            except (SwiggyAuthExpired, SwiggyNotAuthenticated) as e:
                # Not retryable: only a fresh login fixes it, so end the
                # turn and tell the household (see ingester.ingest_user_orders).
                fatal = ("auth", str(e))
            except SwiggyError as e:
                # Any other Swiggy-side failure (bad tool response, 5xx,
                # timeout): end the turn with a plain message instead of an
                # uncaught 500.
                logger.warning("user %s: Swiggy call failed: %s", user_id, e)
                fatal = ("swiggy", _SWIGGY_DOWN)
            except Exception as e:  # noqa: BLE001 — handed to the model, not swallowed
                logger.exception("user %s: tool %s raised", user_id, name)
                result = {"error": f"{type(e).__name__}: {e}"}

            if fatal is not None:
                kind, text = fatal
                yield {"type": "tool_end", "tool": name, "result": {"error": text}, "ms": _ms_since(started), "ok": False}
                _close_unanswered(state.history, response.tool_calls, answered, reason=text)
                state.history.append({"role": "assistant", "content": text})
                yield {"type": "error", "kind": kind, "text": text}
                return

            answered.add(call.id)
            state.history.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, default=str),
            })
            ok = not (isinstance(result, dict) and "error" in result)
            yield {"type": "tool_end", "tool": name, "result": result, "ms": _ms_since(started), "ok": ok}

            if name in _NO_MORE_TOOLS_AFTER:
                force_stop = True

    logger.warning("user %s hit the tool-hop limit", user_id)
    state.history.append({"role": "assistant", "content": _TOO_MANY_HOPS})
    yield {"type": "error", "kind": "internal", "text": _TOO_MANY_HOPS}
