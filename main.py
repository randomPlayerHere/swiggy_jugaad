"""Entrypoint: starts the CLI (v1 interface). Run: uv run main.py"""

from swiggy_jugaad.bot import main as run_cli


def main():
    run_cli()


if __name__ == "__main__":
    main()
