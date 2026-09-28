"""Smoke test for NIM tool-calling support. Run: uv run scripts/tool_call_smoke_test.py

Checks whether NIM_MODEL / NIM_FALLBACK_MODEL return populated tool_calls for
a trivial function schema. bot/agent.py's design depends on the answer:
native OpenAI tool-calling if this passes, otherwise the JSON-object protocol
ingester/normalize.py already has working.
"""

import sys

from openai import OpenAI

from swiggy_jugaad.config import NIM_API_KEY, NIM_BASE_URL, NIM_FALLBACK_MODEL, NIM_MODEL

if not NIM_API_KEY:
    sys.exit("NVIDIA_API_KEY is not set (see .env.example)")

client = OpenAI(base_url=NIM_BASE_URL, api_key=NIM_API_KEY)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name"},
                },
                "required": ["city"],
            },
        },
    }
]

for model in (NIM_MODEL, NIM_FALLBACK_MODEL):
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": "What's the weather in Mumbai right now?"}
            ],
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.0,
            max_tokens=1024,
        )
    except Exception as e:
        print(f"[{model}] FAILED: {e}")
        continue

    message = completion.choices[0].message
    tool_calls = message.tool_calls
    if tool_calls:
        print(f"[{model}] TOOL CALL OK: {tool_calls!r}")
    else:
        print(f"[{model}] NO TOOL CALL — content={message.content!r}")
