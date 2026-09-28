"""Put the web demo's household back to a clean slate between takes.
Run: uv run scripts/reset_demo_user.py [--keep-profile] [--yes]

Deletes the demo household's pantry, corrections and synced-order cache, and
(unless --keep-profile) the household itself, so the next take starts at
onboarding. The global SKU classification cache is kept, so the next sync
doesn't pay for LLM classification again.

Restart the web server (or hit "New chat") afterwards: the conversation
itself lives in memory.
"""

import argparse
from contextlib import closing

from swiggy_jugaad import config
from swiggy_jugaad.store import get_connection, init_db

DEMO_USER_ID = 2  # webapp._DEMO_USER_ID


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--keep-profile", action="store_true", help="keep household size/diet; skip onboarding next take")
    parser.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    args = parser.parse_args()

    what = "pantry, corrections and order cache" + ("" if args.keep_profile else ", and the household profile")
    print(f"This deletes user {DEMO_USER_ID}'s {what} from {config.DB_PATH}.")
    if not args.yes and input("Type RESET to continue: ").strip() != "RESET":
        print("Nothing changed.")
        return

    init_db()
    tables = ["corrections", "pantry_items", "order_cache"] + ([] if args.keep_profile else ["users"])
    with closing(get_connection()) as connection:
        for table in tables:
            deleted = connection.execute(f"DELETE FROM {table} WHERE user_id = ?", (DEMO_USER_ID,)).rowcount
            print(f"  {table}: {deleted} row(s)")
        connection.commit()
    print("Done. Click 'New chat' in the UI (or restart the server) to start fresh.")


if __name__ == "__main__":
    main()
