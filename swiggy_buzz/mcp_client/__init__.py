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

__all__ = [
    "instamart_session",
    "swiggy_session",
    "run",
    "SwiggyError",
    "SwiggyNotAuthenticated",
    "SwiggyAuthExpired",
    "SwiggyUnavailable",
    "SwiggyToolError",
]
