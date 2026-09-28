# swiggy-jugaad

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
   See [`pantry_engine/MATH.md`](swiggy_jugaad/pantry_engine/MATH.md) for the
   full spec.
3. **Suggest** — rank the recipe DB by percent of ingredients already owned,
   taste fit, and prep time. Confidence is always shown, never asserted
   ("Rice 91%," not "You have rice").
4. **Gap-order** — search, size/price-match, and cart only what's missing,
   under the ₹1000 cap, and confirm before checkout.

## Interfaces

- **Web chat** (demo) — a phone-frame chat UI served by FastAPI, driving the
  same agent loop as the CLI, streamed turn by turn. Beside it, an "under the
  hood" panel shows what the model believes (every pantry item's decay curve
  and confidence) and what it does (each LLM hop and tool call, live).
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
uv run uvicorn swiggy_jugaad.webapp:app --reload   # web chat UI, at http://localhost:8000
```

### Web API

| Endpoint | What |
| --- | --- |
| `POST /api/chat/stream` | one turn as server-sent events: `llm_start/llm_end`, `tool_start/tool_end`, then `reply` or `error` |
| `POST /api/chat` | the same turn, as one JSON response |
| `GET /api/pantry` | every pantry item with confidence, age, usable life and pace — UI only, never sent to the model |
| `GET /api/status` | household, Swiggy token expiry, order-history source, model (no network calls) |
| `POST /api/reset` | forget the conversation (household and pantry are kept) |

## Demo

```bash
uv run scripts/demo_preflight.py     # keys, models, token expiry, Swiggy reachable — no NIM inference spent
uv run scripts/reset_demo_user.py    # clean slate for the web household (keeps the SKU cache)
uv run uvicorn swiggy_jugaad.webapp:app
# open http://localhost:8000/?privacy  — ?privacy blurs street addresses for screen recordings
```

Swiggy's MCP only returns ~15 days of order history. For an account that
hasn't ordered lately, set `SWIGGY_ORDERS_REPLAY=data/demo_orders.json` in
`.env`: `sync_orders` then replays those sample orders (dated relative to
now) instead of fetching. Everything after the fetch — LLM classification,
decay, recipe ranking — runs unchanged, and addresses, search, cart and
checkout stay live. The UI shows a "sample order history" pill while it's on.

Checkout is real: confirming a cart places a cash-on-delivery Instamart
order. The backend refuses to check out in the same turn the cart was built.

## Tests

```bash
uv run pytest
```

## Folder structure

```
swiggy_jugaad/
├── main.py                  # entrypoint — starts the CLI (v1)
├── swiggy_jugaad/             # the package
│   ├── config.py            # env vars + constants (₹1000 cap, decay defaults)
│   ├── webapp.py            # FastAPI app — serves the web chat UI + /api/chat
│   ├── static/              # web chat UI + "under the hood" panel (HTML/CSS/JS)
│   ├── pantry_engine/       # core IP: decay math + confidence scoring
│   ├── recipe/              # JSON recipe DB + scoring/ranking
│   ├── ingester/            # order history → canonical ingredients
│   ├── gap_order/           # search, cart, checkout for missing items
│   ├── mcp_client/          # typed Swiggy MCP wrappers (retries, auth)
│   ├── bot/                 # CLI + web adapters, agent loop, tool dispatch
│   └── store/               # SQLite models
├── data/
│   ├── recipes.json         # recipe DB (SQLite db lands here too, gitignored)
│   └── demo_orders.json     # sample order history for SWIGGY_ORDERS_REPLAY
├── scripts/
│   ├── swiggy_login.py      # one-time Swiggy OAuth login
│   ├── demo_preflight.py    # pre-recording checks
│   ├── reset_demo_user.py   # wipe the web demo household between takes
│   ├── nim_smoke_test.py    # LLM endpoint check
│   └── tool_call_smoke_test.py
└── tests/
```

## Key constraints (Swiggy MCP, beta)

- Food/Instamart are **immediate delivery only** — no scheduled delivery
- **₹1000 cart cap** on order placement — gap baskets stay small
- **COD only** — no online payment
- Dineout: free reservations only (not used in this submission)
