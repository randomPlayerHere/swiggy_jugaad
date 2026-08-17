"""Web adapter (demo v1): serves the static chat UI and a /api/chat endpoint
over the same agent.step_with_events() the CLI uses (bot/cli.py).

Same single-household stand-in as the CLI until a real login/session layer
exists — see bot/cli.py's _CLI_USER_ID for the pattern this mirrors.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from swiggy_buzz.bot import agent
from swiggy_buzz.store import get_user, init_db

_DEMO_USER_ID = 1
_STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Swiggy Buzz")


@app.on_event("startup")
def _startup() -> None:
    init_db()


class ChatRequest(BaseModel):
    text: str


@app.get("/api/greeting")
def greeting() -> dict:
    if get_user(_DEMO_USER_ID) is None:
        message = "Hey! Looks like your first time here — tell me your household size and diet to get started."
    else:
        message = "Welcome back! Want recipe ideas, a pantry check, or a grocery top-up?"
    return {"message": message}


@app.post("/api/chat")
async def chat(req: ChatRequest) -> dict:
    reply, events = await run_in_threadpool(agent.step_with_events, _DEMO_USER_ID, req.text)
    return {"reply": reply, "events": events}


app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
