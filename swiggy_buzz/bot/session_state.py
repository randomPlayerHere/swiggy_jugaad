"""Per-user conversation + in-flight order state, kept in memory.

The CLI is a single process, so a module-level dict keyed by user_id is
enough for v1. Telegram/WhatsApp will need this to survive across
processes/restarts; not a v1 problem.
"""

from dataclasses import dataclass, field

from swiggy_buzz.gap_order import CartLine


@dataclass
class PendingOrder:
    """A cart start_gap_order built but hasn't been checked out yet.
    address_id travels with it; nothing else remembers which address the
    search ran against, since we re-ask every time instead of persisting
    a default (see bot/prompts.py rule 3).
    """

    kept: list[CartLine]
    dropped: list[CartLine]
    address_id: str


@dataclass
class ConversationState:
    history: list[dict] = field(default_factory=list)
    pending_order: PendingOrder | None = None


_STATES: dict[int, ConversationState] = {}


def get_or_create_state(user_id: int) -> ConversationState:
    if user_id not in _STATES:
        _STATES[user_id] = ConversationState()
    return _STATES[user_id]
