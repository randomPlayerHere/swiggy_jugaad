"""Typed wrappers around the Swiggy MCP servers (Food / Instamart / Dineout)
with retries and auth. All Swiggy calls go through this module — verify tool
names/params against https://mcp.swiggy.com/builders/llms.txt before adding.

Auth is OAuth 2.1 + PKCE with no API keys. Acquiring a token is a separate,
occasional job (scripts/swiggy_login.py); this package only spends it.
"""

from swiggy_buzz.mcp_client.errors import (
    SwiggyAuthExpired,
    SwiggyError,
    SwiggyNotAuthenticated,
    SwiggyToolError,
    SwiggyUnavailable,
)
from swiggy_buzz.mcp_client.session import instamart_session, run, swiggy_session
from swiggy_buzz.mcp_client.wrappers import (
    SearchResults,
    fetch_addresses,
    fetch_all_orders,
    fetch_go_to_items,
    fetch_orders,
    search_products,
    with_retry,
)

__all__ = [
    "fetch_orders",
    "fetch_all_orders",
    "fetch_addresses",
    "search_products",
    "fetch_go_to_items",
    "SearchResults",
    "with_retry",
    "instamart_session",
    "swiggy_session",
    "run",
    "SwiggyError",
    "SwiggyNotAuthenticated",
    "SwiggyAuthExpired",
    "SwiggyUnavailable",
    "SwiggyToolError",
]
