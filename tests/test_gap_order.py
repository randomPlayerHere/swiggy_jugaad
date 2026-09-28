"""Gap-order policy tests: variant picking, the checkout guard, and what
the model is shown when an ingredient can't be carted. Swiggy is never
called; tools.run is stubbed to hand back what the async layer would."""

import pytest

from swiggy_jugaad.bot import tools
from swiggy_jugaad.bot.session_state import PendingOrder, get_or_create_state, reset_state
from swiggy_jugaad.gap_order import CartLine, OrderSummary, UnresolvedItem, pick_variant
from swiggy_jugaad.gap_order.checkout import _order_id

USER = 998


def product(name, *prices, size="500 g"):
    return {
        "name": name,
        "brand": None,
        "variants": [{"spin_id": f"{name}-{p}", "sku_id": "s", "size": size, "price": p} for p in prices],
    }


def line(name="Tomato 500 g", price=40.0):
    return CartLine(ingredient="tomato", spin_id="sp", sku_id="sk", name=name, price=price, qty=1)


@pytest.fixture
def state():
    reset_state(USER)
    yield get_or_create_state(USER)
    reset_state(USER)


# --------------------------------------------------------------------------
# pick_variant
# --------------------------------------------------------------------------

def test_pick_variant_takes_cheapest_among_top_results():
    products = [product("Amul Milk", 30, 28), product("Nandini Milk", 26), product("Heritage Milk", 29)]
    chosen, variant = pick_variant(products)
    assert chosen["name"] == "Nandini Milk"
    assert variant["price"] == 26


def test_pick_variant_ignores_cheap_but_irrelevant_tail():
    products = [
        product("Amul Milk", 30),
        product("Nandini Milk", 28),
        product("Heritage Milk", 29),
        product("Milk Bikis Biscuit", 10),
    ]
    assert pick_variant(products)[0]["name"] == "Nandini Milk"


def test_pick_variant_skips_unpriced_and_handles_nothing():
    assert pick_variant([product("Ghee", None)]) is None
    assert pick_variant([]) is None


# --------------------------------------------------------------------------
# checkout response parsing
# --------------------------------------------------------------------------

@pytest.mark.parametrize("response, expected", [
    ({"data": {"orderId": 123}}, "123"),
    ({"orderId": "abc"}, "abc"),
    ({"data": {"order_id": "x9"}}, "x9"),
    ({"data": {"message": "placed"}}, None),
    ({}, None),
])
def test_order_id_found_wherever_it_lands(response, expected):
    assert _order_id(response) == expected


# --------------------------------------------------------------------------
# start_gap_order / confirm_gap_order
# --------------------------------------------------------------------------

def test_start_gap_order_offers_alternatives_and_stages_cart(state, monkeypatch):
    similar = [product("Amul Pure Ghee", 320, 610, size="500 ml"), product("Gowardhan Ghee", 299), product("A", 1), product("B", 2)]
    unresolved = [UnresolvedItem(ingredient="ghee", reason="no products found", similar=similar)]
    monkeypatch.setattr(tools, "run", lambda fn: ([line()], [], unresolved))
    state.turn = 4

    result = tools.start_gap_order(USER, "addr-1", ["tomato", "ghee"])

    assert result["total"] == 40.0
    alternatives = result["unresolved"][0]["alternatives"]
    assert len(alternatives) == 3
    assert alternatives[0] == {"name": "Amul Pure Ghee", "size": "500 ml", "price": 320}
    assert state.pending_order.staged_turn == 4
    assert state.pending_order.address_id == "addr-1"


def test_confirm_refuses_in_the_same_turn_the_cart_was_built(state, monkeypatch):
    placed = []
    monkeypatch.setattr(tools, "run", lambda fn: placed.append(fn))
    monkeypatch.setattr(tools, "mark_address_confirmed", lambda user_id: None)
    state.turn = 3
    state.pending_order = PendingOrder(kept=[line()], dropped=[], address_id="a", staged_turn=3)

    result = tools.confirm_gap_order(USER)

    assert "error" in result
    assert placed == []
    assert state.pending_order is not None  # still there for the household's yes


def test_confirm_places_order_on_a_later_turn(state, monkeypatch):
    summary = OrderSummary(lines=[line()], dropped_for_cap=[line("Ghee 1 L", 900.0)], total=40.0, order_id="SW123")
    monkeypatch.setattr(tools, "run", lambda fn: summary)
    monkeypatch.setattr(tools, "mark_address_confirmed", lambda user_id: None)
    state.turn = 4
    state.pending_order = PendingOrder(kept=[line()], dropped=[], address_id="a", staged_turn=3)

    result = tools.confirm_gap_order(USER)

    assert result == {"order_id": "SW123", "total": 40.0, "dropped_for_cap": ["Ghee 1 L"]}
    assert state.pending_order is None


def test_confirm_without_a_cart_is_refused(state):
    assert "error" in tools.confirm_gap_order(USER)
