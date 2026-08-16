# swiggy-buzz

An agent that infers a household's kitchen inventory from Swiggy Instamart
order history (consumption-decay math — no pantry API exists), suggests
recipes ranked by what's already owned, and orders only the missing items.

> Swiggy knows what enters your kitchen. Our model knows what's still in it.

## Setup

```bash
cp .env.example .env   # fill in NVIDIA_API_KEY, TELEGRAM_BOT_TOKEN
uv sync
uv run scripts/nim_smoke_test.py   # verify the LLM endpoint works
uv run main.py
```

## Folder structure

```
swiggy_buzz/
├── main.py                  # entrypoint — starts the CLI (v1); Telegram/WhatsApp later
├── swiggy_buzz/             # the package
│   ├── config.py            # env vars + constants (₹1000 cap, decay defaults)
│   ├── pantry_engine/       # core IP: decay math + confidence scoring
│   ├── recipe/              # JSON recipe DB + scoring/ranking
│   ├── ingester/            # order history → canonical ingredients
│   ├── gap_order/           # search, cart, checkout for missing items
│   ├── mcp_client/          # typed Swiggy MCP wrappers (retries, auth)
│   ├── bot/                 # CLI adapter (v1) + agent loop
│   └── store/               # SQLite models
├── data/
│   └── recipes.json         # recipe DB (SQLite db lands here too, gitignored)
├── scripts/
│   └── nim_smoke_test.py    # LLM endpoint check
└── tests/
```

See [CLAUDE.MD](CLAUDE.MD) for the full architecture, Swiggy MCP constraints,
and conventions.
