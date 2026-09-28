"""Pre-recording checks for the web demo. Run: uv run scripts/demo_preflight.py

Spends no NIM inference by default: the models are checked against NIM's
/v1/models listing, which is how an end-of-life model shows up (it drops off
the list, then answers 410). Pass --nim to also make one 1-token chat call.

Makes one read-only Swiggy call (get_addresses) to prove the token works.
"""

import argparse
import os
import sys
from datetime import datetime, timezone

import httpx

from swiggy_jugaad import config
from swiggy_jugaad.mcp_client import SwiggyError, fetch_addresses, run, token_expiry
from swiggy_jugaad.recipe import load_recipes_from_dicts
from swiggy_jugaad.store import get_pantry, get_user, init_db

DEMO_USER_ID = 2  # webapp._DEMO_USER_ID; not imported so this stays a plain script
failures = 0


def check(ok: bool, label: str, detail: str = "") -> None:
    global failures
    failures += not ok
    print(f"{'✅' if ok else '❌'} {label}{f' — {detail}' if detail else ''}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--nim", action="store_true", help="also make one 1-token NIM chat call")
    args = parser.parse_args()

    # --- NIM ---
    check(bool(config.NIM_API_KEY), "NVIDIA_API_KEY set")
    try:
        r = httpx.get(f"{config.NIM_BASE_URL}/models", headers={"Authorization": f"Bearer {config.NIM_API_KEY}"}, timeout=20)
        r.raise_for_status()
        listed = {m["id"] for m in r.json()["data"]}
        check(config.NIM_MODEL in listed, f"primary model listed: {config.NIM_MODEL}")
        check(config.NIM_FALLBACK_MODEL in listed, f"fallback model listed: {config.NIM_FALLBACK_MODEL}")
    except httpx.HTTPError as e:
        check(False, "NIM /v1/models reachable", str(e))

    if args.nim:
        from openai import OpenAI

        try:
            client = OpenAI(api_key=config.NIM_API_KEY, base_url=config.NIM_BASE_URL, timeout=30, max_retries=0)
            client.chat.completions.create(model=config.NIM_MODEL, messages=[{"role": "user", "content": "hi"}], max_tokens=1)
            check(True, f"{config.NIM_MODEL} answers a chat call")
        except Exception as e:  # noqa: BLE001
            check(False, f"{config.NIM_MODEL} answers a chat call", str(e)[:160])

    # --- Swiggy ---
    check(bool(config.SWIGGY_ACCESS_TOKEN), "SWIGGY_ACCESS_TOKEN set")
    expires = token_expiry()
    if expires:
        left = expires - datetime.now(timezone.utc)
        hours = left.total_seconds() / 3600
        check(hours > 6, "Swiggy token not about to expire", f"expires {expires:%Y-%m-%d %H:%M} UTC ({hours:.0f}h left)")
    try:
        addresses = run(lambda: fetch_addresses())
        check(bool(addresses), "Swiggy MCP answers (get_addresses)", f"{len(addresses)} saved addresses")
    except SwiggyError as e:
        check(False, "Swiggy MCP answers (get_addresses)", str(e).splitlines()[0])

    # --- order history source ---
    if config.SWIGGY_ORDERS_REPLAY:
        check(os.path.exists(config.SWIGGY_ORDERS_REPLAY), "order replay file exists", config.SWIGGY_ORDERS_REPLAY)
    else:
        print("ℹ️  SWIGGY_ORDERS_REPLAY unset — sync_orders reads live Swiggy history (~15 days)")

    # --- local data ---
    try:
        init_db()
        check(True, "SQLite DB initializes", config.DB_PATH)
    except Exception as e:  # noqa: BLE001
        check(False, "SQLite DB initializes", str(e))
    try:
        check(True, "recipe DB loads", f"{len(load_recipes_from_dicts())} recipes")
    except Exception as e:  # noqa: BLE001
        check(False, "recipe DB loads", str(e))

    user = get_user(DEMO_USER_ID)
    if user is None:
        print("ℹ️  demo household not onboarded — the video starts at onboarding")
    else:
        print(f"ℹ️  demo household: {user.household_size} people, {user.diet}; {len(get_pantry(DEMO_USER_ID))} pantry items")

    print()
    print("All good — ready to record." if not failures else f"{failures} check(s) failed.")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
