# swiggy-buzz

An agent that infers a household's kitchen inventory from Swiggy Instamart
order history (consumption-decay math — no pantry API exists), suggests
recipes ranked by what's already owned, and orders only the missing items
straight through Instamart.

> Swiggy knows what enters your kitchen. Our model knows what's still in it.

Built against the Swiggy MCP (Food / Instamart / Dineout) beta for the
Swiggy Builders Club.

## How it works

1. **Ingest** — pull recent Instamart order history via MCP, normalize raw
   SKU names ("Amul Taaza Toned Milk 500 ml") into canonical ingredients with
   an LLM-backed cache so the classification is only ever paid for once per
   SKU, globally.
2. **Infer** — decay each item from its last purchase using a per-category
   half-life (milk ~4d, rice ~21d, spices ~90d), scaled by household size and
   a personal pace multiplier that tunes itself from corrections you give it.
   See [`pantry_engine/MATH.md`](swiggy_buzz/pantry_engine/MATH.md) for the
   full spec.
3. **Suggest** — rank the recipe DB by percent of ingredients already owned,
   taste fit, and prep time. Confidence is always shown, never asserted
   ("Rice 91%," not "You have rice").
4. **Gap-order** — search, size/price-match, and cart only what's missing,
   under the ₹1000 cap, and confirm before checkout.

## Interfaces

- **Web chat** (demo) — a phone-frame chat UI served by FastAPI, driving the
  same agent loop as the CLI.
- **CLI** — plain stdin/stdout REPL, same agent underneath.

Telegram/WhatsApp is a planned adapter behind the same `agent.step()` loop,
not part of this submission.

## Setup

```bash
cp .env.example .env             # fill in NVIDIA_API_KEY
uv sync
uv run scripts/nim_smoke_test.py # verify the LLM endpoint works

# Swiggy has no API keys — authenticate once via OAuth 2.1 + PKCE
# (opens a browser, phone + OTP). Token lasts ~5 days, no refresh.
uv run scripts/swiggy_login.py   # paste the printed token into .env as SWIGGY_ACCESS_TOKEN
```

## Running

```bash
uv run main.py                              # CLI
uv run uvicorn swiggy_buzz.webapp:app --reload   # web chat UI, at http://localhost:8000
```

## Tests

```bash
uv run pytest
```

## Folder structure

```
swiggy_buzz/
├── main.py                  # entrypoint — starts the CLI (v1)
├── swiggy_buzz/             # the package
│   ├── config.py            # env vars + constants (₹1000 cap, decay defaults)
│   ├── webapp.py            # FastAPI app — serves the web chat UI + /api/chat
│   ├── static/              # web chat UI (phone-frame HTML/CSS/JS)
│   ├── pantry_engine/       # core IP: decay math + confidence scoring
│   ├── recipe/              # JSON recipe DB + scoring/ranking
│   ├── ingester/            # order history → canonical ingredients
│   ├── gap_order/           # search, cart, checkout for missing items
│   ├── mcp_client/          # typed Swiggy MCP wrappers (retries, auth)
│   ├── bot/                 # CLI + web adapters, agent loop, tool dispatch
│   └── store/               # SQLite models
├── data/
│   └── recipes.json         # recipe DB (SQLite db lands here too, gitignored)
├── scripts/
│   ├── swiggy_login.py      # one-time Swiggy OAuth login
│   ├── nim_smoke_test.py    # LLM endpoint check
│   └── tool_call_smoke_test.py
└── tests/
```

## Key constraints (Swiggy MCP, beta)

- Food/Instamart are **immediate delivery only** — no scheduled delivery
- **₹1000 cart cap** on order placement — gap baskets stay small
- **COD only** — no online payment
- Dineout: free reservations only (not used in this submission)
