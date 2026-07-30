"""Authenticated connections to the Swiggy MCP servers.

Swiggy issues no API keys — auth is OAuth 2.1 + PKCE, and the resulting bearer
token is what we carry here. Getting that token is a separate, occasional job
(scripts/swiggy_login.py); this module only *spends* it, by attaching it as an
Authorization header. That split is deliberate: the app never serves HTTP and
never runs a consent flow, so nothing here needs a callback listener.

Tokens last ~5 days with no refresh token in v1, so an expired session is a
normal event rather than an error path — see errors.SwiggyAuthExpired.

Everything is async because the MCP SDK is; run() bridges to the synchronous
rest of the codebase (store/, pantry_engine/) so callers don't go async too.
"""

import anyio
import httpx
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TypeVar

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from swiggy_buzz import config
from swiggy_buzz.mcp_client.errors import (
    SwiggyAuthExpired,
    SwiggyNotAuthenticated,
    SwiggyUnavailable,
)

T = TypeVar("T")

# Swiggy's own codes: 401 = session gone, 419 = explicitly revoked.
_REVOKED_STATUS = 419

# The MCP SDK's own defaults, which we now have to set ourselves: since 1.28
# the transport takes a pre-built httpx client instead of headers/timeouts, so
# nothing configures these for us. Long read timeout is for SSE streams.
_TIMEOUT = httpx.Timeout(30.0, read=300.0)


def _auth_headers(token: str | None = None) -> dict[str, str]:
    """Bearer header, or raise if we have nothing to send. Checked eagerly so
    the failure names the fix instead of surfacing as a 401 mid-request."""
    token = token if token is not None else config.SWIGGY_ACCESS_TOKEN
    if not token:
        raise SwiggyNotAuthenticated()
    return {"Authorization": f"Bearer {token}"}


def _translate(exc: Exception) -> Exception:
    """Map transport failures onto our retryable/not-retryable split.

    The transport runs its reader/writer inside an anyio task group, so what
    reaches us is usually an ExceptionGroup wrapping the real httpx error —
    unwrap before matching, or every failure would escape untranslated.
    """
    if isinstance(exc, BaseExceptionGroup):
        for inner in exc.exceptions:
            if isinstance(inner, Exception):
                translated = _translate(inner)
                if translated is not inner:
                    return translated
        return exc
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == httpx.codes.UNAUTHORIZED:
            return SwiggyAuthExpired()
        if status == _REVOKED_STATUS:
            return SwiggyAuthExpired(revoked=True)
        if status >= 500:
            return SwiggyUnavailable(f"Swiggy returned {status}")
        return exc
    if isinstance(exc, httpx.HTTPError):
        # Timeouts, DNS, connection resets — all worth retrying.
        return SwiggyUnavailable(str(exc) or type(exc).__name__)
    return exc


@asynccontextmanager
async def swiggy_session(
    url: str, token: str | None = None
) -> AsyncIterator[ClientSession]:
    """Open an initialized MCP session against one Swiggy server.

    Usage:
        async with swiggy_session(config.SWIGGY_MCP_INSTAMART_URL) as session:
            result = await session.call_tool("get_orders", {})
    """
    headers = _auth_headers(token)
    try:
        async with httpx.AsyncClient(
            headers=headers, timeout=_TIMEOUT, follow_redirects=True
        ) as http_client:
            async with streamable_http_client(url, http_client=http_client) as (
                read,
                write,
                _,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session
    except Exception as exc:  # noqa: BLE001 — re-raised, translated or as-is
        translated = _translate(exc)
        if translated is exc:
            raise
        raise translated from exc


def instamart_session(token: str | None = None):
    """The Instamart server — order history, product search, cart, checkout.
    This is the only Swiggy server the MVP uses."""
    return swiggy_session(config.SWIGGY_MCP_INSTAMART_URL, token)


def run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    """Run one async call from synchronous code.

    The rest of swiggy_buzz (store/, pantry_engine/) is plain sync functions and
    stays that way; this is the single crossing point. Takes a zero-arg callable
    rather than a coroutine so nothing is created until we're inside the runner.

        orders = run(lambda: fetch_orders())
    """
    return anyio.run(coro_fn)
