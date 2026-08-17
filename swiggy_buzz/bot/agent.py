import json
import logging
from openai import OpenAI

from swiggy_buzz.config import NIM_API_KEY, NIM_BASE_URL, NIM_FALLBACK_MODEL, NIM_MODEL
from swiggy_buzz.mcp_client import SwiggyAuthExpired, SwiggyNotAuthenticated
from .prompts import SYSTEM_PROMPT
from .session_state import get_or_create_state
from .tools import TOOL_SCHEMAS, dispatch

logger = logging.getLogger(__name__)

_client = OpenAI(api_key=NIM_API_KEY, base_url=NIM_BASE_URL)
_MAX_TOOL_HOPS = 8
_NO_MORE_TOOLS_AFTER = {"start_gap_order"}


def _call_llm(messages: list[dict], tool_choice: str):
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
            return completion
        except Exception as e:
            logger.warning("[%s] FAILED for tool calling: %s", model, e)
            continue
    raise RuntimeError("no NIM model answered")


def step(user_id: int, user_text: str) -> str:
    state = get_or_create_state(user_id=user_id)
    state.history.append({"role": "user", "content": user_text})
    force_stop = False
    for _ in range(_MAX_TOOL_HOPS):
        messages = [{"role": "system", "content":SYSTEM_PROMPT}, *state.history]
        completion = _call_llm(messages, tool_choice="none" if force_stop else "auto")
        response = completion.choices[0].message
        state.history.append(response.model_dump(exclude_none=True))

        if not response.tool_calls:
            return response.content or ""

        force_stop = False
        for call in response.tool_calls:
            args = json.loads(call.function.arguments or "{}")
            try:
                result = dispatch(call.function.name, args, user_id)
            except (SwiggyAuthExpired, SwiggyNotAuthenticated) as e:
                # Deliberately escapes the tool layer (see
                # ingester.ingest_user_orders' docstring) — short-circuit
                # straight to "tap to reconnect" instead of leaving this
                # tool call's response missing from history.
                return str(e)

            state.history.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, default=str),
            })

            if call.function.name in _NO_MORE_TOOLS_AFTER:
                force_stop = True

    logger.warning("user %s hit the tool-hop limit", user_id)
    return "Sorry, I'm having trouble finishing that — can you rephrase?"
