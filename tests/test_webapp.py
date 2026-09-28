"""Web API tests against a temp DB. No Swiggy or NIM calls: the chat
endpoints are covered by test_agent.py; these cover the panel endpoints and
the order-replay path that feeds them."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from swiggy_jugaad import webapp
from swiggy_jugaad.ingester.parse import parse_orders
from swiggy_jugaad.ingester.replay import load_replay_orders
from swiggy_jugaad.store.models import PantryItem, User

USER = webapp._DEMO_USER_ID
NOW = datetime.now(timezone.utc)


@pytest.fixture
def client(repo):
    return TestClient(webapp.app)


def seed(repo, household_size=2):
    repo.upsert_user(User(USER, household_size, "veg", False, ""))
    for name, category, days in [("milk", "dairy", 0.3), ("rice", "rice_grains", 3), ("tomato", "produce", 4)]:
        bought = (NOW - timedelta(days=days)).isoformat()
        repo.upsert_pantry_item(PantryItem(0, USER, name, category, bought, 1, None, False))


def test_pantry_empty_before_onboarding(client):
    body = client.get("/api/pantry").json()
    assert body == {"items": [], "counts": {"likely": 0, "maybe": 0, "out": 0}}


def test_pantry_items_carry_curve_inputs_most_at_risk_first(client, repo):
    seed(repo)
    body = client.get("/api/pantry").json()

    assert [i["name"] for i in body["items"]] == ["tomato", "rice", "milk"]
    assert body["counts"] == {"likely": 2, "maybe": 0, "out": 1}
    milk = body["items"][-1]
    assert set(milk) >= {"name", "category", "bucket", "confidence", "age_days", "life_days", "pace", "is_out"}
    assert milk["pace"] == 1.0
    assert 0 < milk["confidence"] <= 1
    assert milk["age_days"] == pytest.approx(0.3, abs=0.01)


def test_pantry_life_shrinks_after_ran_out_early(client, repo):
    seed(repo)
    before = next(i for i in client.get("/api/pantry").json()["items"] if i["name"] == "milk")["life_days"]
    repo.update_decay_lambda(USER, "milk", 1.2)
    repo.mark_item_out(USER, "milk")
    milk = next(i for i in client.get("/api/pantry").json()["items"] if i["name"] == "milk")
    assert milk["bucket"] == "out"
    assert milk["life_days"] == pytest.approx(before / 1.2, abs=0.01)


def test_status_is_local_and_reports_household(client, repo, monkeypatch):
    monkeypatch.setattr(webapp.config, "SWIGGY_ORDERS_REPLAY", "data/demo_orders.json")
    assert client.get("/api/status").json()["household"] is None
    seed(repo)
    body = client.get("/api/status").json()
    assert body["household"] == {"household_size": 2, "diet": "veg"}
    assert body["orders_source"] == "replay"
    assert "token_set" in body["swiggy"]


def test_reset_is_ok(client):
    assert client.post("/api/reset").json() == {"ok": True}


def test_replay_orders_are_relative_to_now_and_parse():
    now = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
    raw = load_replay_orders("data/demo_orders.json", now=now)
    assert raw[0]["createdAt"] > raw[-1]["createdAt"]  # newest first, like fetch_all_orders
    parsed = parse_orders(raw)
    assert len(parsed) == len(raw)
    assert all(o.is_delivered for o in parsed)
    newest = max(o.purchased_at for o in parsed)
    assert now - newest == timedelta(days=0.4)
