"""CLI adapter (v1): reads stdin, drives the agent loop, prints replies.

Telegram/WhatsApp will be a later adapter calling the same agent.step().
Keep this file to I/O only; no logic that belongs in tools.py/agent.py.
"""

from swiggy_jugaad.store import get_user, init_db

from . import agent

# Stand-in for a Telegram chat id (schema.sql's actual user_id meaning)
# until that adapter exists. The CLI only ever talks to one household.
_CLI_USER_ID = 1


def main() -> None:
    init_db()

    if get_user(_CLI_USER_ID) is None:
        print("swiggy-jugaad: looks like your first time — tell me your household size and diet to get started.")
    else:
        print("swiggy-jugaad: welcome back — want recipe ideas, a pantry check, or a grocery top-up?")

    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not text:
            continue
        if text.lower() in {"quit", "exit"}:
            break

        print("…thinking")
        reply = agent.step(_CLI_USER_ID, text)
        print(reply)
