"""Per-user conversation + in-flight order state, kept in memory.

The CLI is a single process, so a module-level dict keyed by user_id is
enough for v1. Telegram/WhatsApp will need this to survive across
processes/restarts; not a v1 problem.
"""

from dataclasses import dataclass, field

from swiggy_jugaad.gap_order import CartLine


@dataclass
class PendingOrder:
    """A cart start_gap_order built but hasn't been checked out yet.
    address_id travels with it; nothing else remembers which address the
    search ran against, since we re-ask every time instead of persisting
    a default (see bot/prompts.py rule 3).

    staged_turn is the ConversationState.turn the cart was built in.
    confirm_gap_order refuses to check out in that same turn, so prompt
    rule 4 (an explicit yes, in its own message) holds even if the model
    ignores it.
    """

    kept: list[CartLine]
    dropped: list[CartLine]
    address_id: str
    staged_turn: int = 0


@dataclass
class ConversationState:
    history: list[dict] = field(default_factory=list)
    pending_order: PendingOrder | None = None
    # One per user message; agent.iter_step bumps it before anything else.
    turn: int = 0


_STATES: dict[int, ConversationState] = {}


def get_or_create_state(user_id: int) -> ConversationState:
    if user_id not in _STATES:
        _STATES[user_id] = ConversationState()
    return _STATES[user_id]


def reset_state(user_id: int) -> None:
    """Forget the conversation and any staged cart. The household's profile
    and pantry live in SQLite and are untouched."""
    _STATES.pop(user_id, None)
