"""Central config: env vars and product constants. Import from here, never
read os.environ elsewhere."""

import os

from dotenv import load_dotenv

# Load .env once, at import. Real environment variables win over the file, so
# `SWIGGY_BUZZ_DB=... uv run ...` still overrides for one-off runs.
load_dotenv()

# --- LLM (NVIDIA NIM, OpenAI-compatible) ---
NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
NIM_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
NIM_MODEL = os.environ.get("NIM_MODEL", "mistralai/mistral-nemotron")
NIM_FALLBACK_MODEL = "minimaxai/minimax-m2.7"

# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# --- Swiggy MCP ---
# Server URLs per https://mcp.swiggy.com/builders/docs/start/consumer/use-in-ai-client
SWIGGY_MCP_INSTAMART_URL = "https://mcp.swiggy.com/im"
SWIGGY_MCP_FOOD_URL = "https://mcp.swiggy.com/food"
SWIGGY_MCP_DINEOUT_URL = "https://mcp.swiggy.com/dineout"

# Bearer token from scripts/swiggy_login.py. OAuth 2.1 + PKCE, ~5 day lifetime,
# no refresh token in v1 — when it expires you re-run the login script.
SWIGGY_ACCESS_TOKEN = os.environ.get("SWIGGY_ACCESS_TOKEN", "")

# Local listener the one-time OAuth flow redirects back to. Only used by the
# login script; the app itself never serves HTTP.
SWIGGY_OAUTH_CALLBACK_PORT = int(os.environ.get("SWIGGY_OAUTH_CALLBACK_PORT", "3030"))
SWIGGY_OAUTH_CALLBACK_PATH = "/callback"

# --- Swiggy MCP constraints (beta) ---
CART_CAP_INR = 1000  # hard cap on order placement
# Immediate delivery only; COD only — enforced by Swiggy, mirrored in gap_order.

# --- Storage ---
DB_PATH = os.environ.get("SWIGGY_BUZZ_DB", "data/swiggy_buzz.db")
RECIPE_DB_PATH = "data/recipes.json"

# --- Pantry decay defaults (days to ~depleted, per category) ---
# Tuned per household by corrections: pace multiplier m ×1.2 if ran out early,
# ×0.8 if lasted longer (clamped [0.2, 5.0]); see pantry_engine/MATH.md.
DEFAULT_DECAY_DAYS = {
    "dairy": 4,
    "produce": 5,
    "bread": 4,
    "eggs": 10,
    "rice_grains": 21,
    "pulses": 30,
    "oil": 45,
    "spices": 90,
    "snacks": 7,
}
