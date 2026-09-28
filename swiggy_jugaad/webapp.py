"""Web adapter (demo): serves the static chat UI and a JSON/SSE API over the
same agent loop the CLI uses (bot/cli.py).

Same single-household stand-in as the CLI until a real login/session layer
exists — see bot/cli.py's _CLI_USER_ID for the pattern this mirrors.

/api/pantry and /api/status feed the UI's "under the hood" panel only.
They show raw confidence numbers, which the model itself never states
(bot/prompts.py rule 1): the panel is the model's internals, the chat is
the product.
"""

import json
import logging
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from swiggy_jugaad import config
from swiggy_jugaad.bot import agent
from swiggy_jugaad.bot.session_state import reset_state
from swiggy_jugaad.mcp_client import token_expiry
from swiggy_jugaad.pantry_engine import age_days, usable_life_days
from swiggy_jugaad.pantry_engine.execution import score_entire_pantry
from swiggy_jugaad.store import get_user, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

_DEMO_USER_ID = 2
_STATIC_DIR = Path(__file__).parent / "static"
_INTERNAL_ERROR = "Something went wrong on my side — try that again."
_BUCKET_ORDER = {"likely": 0, "maybe": 1, "out": 2}


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Swiggy Jugaad", lifespan=_lifespan)


class ChatRequest(BaseModel):
    text: str


@app.get("/api/greeting")
def greeting() -> dict:
    onboarded = get_user(_DEMO_USER_ID) is not None
    if not onboarded:
        message = "Hey! Looks like your first time here — tell me your household size and diet to get started."
    else:
        message = "Welcome back! Want recipe ideas, a pantry check, or a grocery top-up?"
    return {"message": message, "onboarded": onboarded}


@app.post("/api/chat")
async def chat(req: ChatRequest) -> dict:
    try:
        reply, events = await run_in_threadpool(agent.step_with_events, _DEMO_USER_ID, req.text)
    except Exception:
        logger.exception("chat turn failed")
        return {"reply": _INTERNAL_ERROR, "events": []}
    return {"reply": reply, "events": events}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


def _chat_events(text: str) -> Iterator[str]:
    try:
        for event in agent.iter_step(_DEMO_USER_ID, text, rich_ui=True):
            yield _sse(event)
    except Exception:
        logger.exception("chat stream failed")
        yield _sse({"type": "error", "kind": "internal", "text": _INTERNAL_ERROR})


@app.post("/api/chat/stream")
def chat_stream(req: ChatRequest) -> StreamingResponse:
    """Server-sent events, one per agent.iter_step event, so the UI can show
    each tool call as it happens. The sync generator is iterated in
    Starlette's threadpool, same as run_in_threadpool above."""
    return StreamingResponse(
        _chat_events(req.text),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/reset")
def reset() -> dict:
    """New conversation. The household and its pantry are kept."""
    reset_state(_DEMO_USER_ID)
    return {"ok": True}


@app.get("/api/pantry")
def pantry() -> dict:
    user = get_user(_DEMO_USER_ID)
    counts = {bucket: 0 for bucket in _BUCKET_ORDER}
    if user is None:
        return {"items": [], "counts": counts}

    now = datetime.now(timezone.utc)
    items = []
    for scored in score_entire_pantry(_DEMO_USER_ID, now) or []:
        item = scored.pantry_item
        pace = item.decay_lambda if item.decay_lambda is not None else 1.0
        items.append({
            "name": item.canonical_name,
            "category": item.category,
            "bucket": scored.bucket,
            "confidence": round(scored.confidence_score, 3),
            "age_days": round(age_days(item, now), 2),
            # Days until C falls to ~5% at this household's pace (MATH.md §2).
            "life_days": round(usable_life_days(item.category, user.household_size) / pace, 2),
            "pace": round(pace, 2),
            "is_out": item.is_out,
            "last_purchased_at": item.last_purchased_at,
        })
        counts[scored.bucket] += 1
    # Most at risk first: what the household is about to run out of is
    # what the agent acts on.
    items.sort(key=lambda i: (-_BUCKET_ORDER[i["bucket"]], i["confidence"]))
    return {"items": items, "counts": counts}


@app.get("/api/status")
def status() -> dict:
    """Everything here is local: no Swiggy or NIM call is made."""
    user = get_user(_DEMO_USER_ID)
    expires = token_expiry()
    return {
        "household": {"household_size": user.household_size, "diet": user.diet} if user else None,
        "swiggy": {
            "token_set": bool(config.SWIGGY_ACCESS_TOKEN),
            "expires_at": expires.isoformat() if expires else None,
        },
        "orders_source": "replay" if config.SWIGGY_ORDERS_REPLAY else "live",
        "model": config.NIM_MODEL,
    }


app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
