"""Smoke test for the NVIDIA NIM endpoint. Run: uv run scripts/nim_smoke_test.py"""

import sys

from openai import OpenAI

from swiggy_buzz.config import NIM_API_KEY, NIM_BASE_URL, NIM_FALLBACK_MODEL, NIM_MODEL

if not NIM_API_KEY:
    sys.exit("NVIDIA_API_KEY is not set (see .env.example)")

client = OpenAI(base_url=NIM_BASE_URL, api_key=NIM_API_KEY)

for model in (NIM_MODEL, NIM_FALLBACK_MODEL):
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Hi! Who are you?"}],
            temperature=0.6,
            top_p=0.7,
            max_tokens=4096
        )
    except Exception as e:
        print(f"[{model}] FAILED: {e}")
        continue
    print(f"[{model}] OK: {completion.choices[0].message.content!r}")
    break
else:
    sys.exit("no working model")
