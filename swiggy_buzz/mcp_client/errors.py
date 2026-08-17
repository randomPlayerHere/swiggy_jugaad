"""Failure modes of the Swiggy MCP connection, split by what the caller
should do about them.

SwiggyAuthExpired is not retryable: retrying a dead token just burns time,
the only fix is re-running the login script. SwiggyUnavailable is
retryable with backoff.

Per https://mcp.swiggy.com/builders/docs/start/authenticate, 401 means the
session is gone, 419 means it was revoked. Neither has a refresh token in v1.
"""


class SwiggyError(Exception):
    """Base for everything this package raises."""


class SwiggyNotAuthenticated(SwiggyError):
    """No token configured at all — SWIGGY_ACCESS_TOKEN is empty."""

    def __init__(self, message: str | None = None):
        super().__init__(
            message
            or "SWIGGY_ACCESS_TOKEN is not set. Run:\n"
            "    uv run scripts/swiggy_login.py\n"
            "then paste the token into .env"
        )


class SwiggyAuthExpired(SwiggyError):
    """Token expired (401) or was revoked (419). Not retryable — the user has
    to re-run the login script. The bot surfaces this as 'tap to reconnect'."""

    def __init__(self, message: str | None = None, *, revoked: bool = False):
        self.revoked = revoked
        reason = "revoked" if revoked else "expired"
        super().__init__(
            message
            or f"Swiggy session {reason}. Re-run: uv run scripts/swiggy_login.py"
        )


class SwiggyUnavailable(SwiggyError):
    """Network trouble or a 5xx from Swiggy. Retryable with backoff."""


class SwiggyToolError(SwiggyError):
    """A tool ran and reported failure (isError on the MCP result). The tool
    itself is fine; the request was bad, or the item/cart/address wasn't
    valid. Not retryable without changing the arguments."""

    def __init__(self, tool_name: str, detail: str):
        self.tool_name = tool_name
        self.detail = detail
        super().__init__(f"Swiggy tool {tool_name!r} failed: {detail}")
