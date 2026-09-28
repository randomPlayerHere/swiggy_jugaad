"""One-time Swiggy login. Run: uv run scripts/swiggy_login.py

No API keys. You authenticate with OAuth 2.1 + PKCE in a browser, with
phone + OTP. This script drives that flow once and prints the bearer token
to paste into .env as SWIGGY_ACCESS_TOKEN.

Token lasts ~5 days, no refresh in v1. Re-run this when it dies (before a
demo, not during one).

The localhost listener below exists only because OAuth must redirect
somewhere. It handles one request and shuts down. The app itself never
serves HTTP; see mcp_client/session.py, which only spends the token.
"""

import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import anyio
import httpx
from mcp import ClientSession
from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

from swiggy_jugaad import config

REDIRECT_URI = (
    f"http://localhost:{config.SWIGGY_OAUTH_CALLBACK_PORT}"
    f"{config.SWIGGY_OAUTH_CALLBACK_PATH}"
)

_PAGE = b"""<!doctype html><meta charset=utf-8>
<title>swiggy-jugaad</title>
<body style="font-family:system-ui;padding:3rem;max-width:32rem">
<h2>Connected.</h2>
<p>You can close this tab and go back to the terminal.</p>
"""


class _MemoryTokenStorage(TokenStorage):
    """Holds the token just long enough to print it. Nothing is written to
    disk; the token's permanent home is your .env, pasted by hand."""

    def __init__(self) -> None:
        self.tokens: OAuthToken | None = None
        self.client_info: OAuthClientInformationFull | None = None

    async def get_tokens(self) -> OAuthToken | None:
        return self.tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self.tokens = tokens

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return self.client_info

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self.client_info = client_info


class _CallbackHandler(BaseHTTPRequestHandler):
    code: str | None = None
    state: str | None = None
    error: str | None = None

    def do_GET(self) -> None:  # noqa: N802 — name fixed by BaseHTTPRequestHandler
        params = parse_qs(urlparse(self.path).query)
        _CallbackHandler.code = params.get("code", [None])[0]
        _CallbackHandler.state = params.get("state", [None])[0]
        _CallbackHandler.error = params.get("error", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(_PAGE)

    def log_message(self, *args) -> None:
        """Silence the default stderr access log — it's noise here."""


def _serve_one_request() -> None:
    server = HTTPServer(("localhost", config.SWIGGY_OAUTH_CALLBACK_PORT), _CallbackHandler)
    server.handle_request()
    server.server_close()


async def _redirect_handler(authorization_url: str) -> None:
    print("\nOpening your browser to log in to Swiggy (phone + OTP).")
    print("If it doesn't open, paste this URL yourself:\n")
    print(f"  {authorization_url}\n")
    webbrowser.open(authorization_url)


async def _callback_handler() -> tuple[str, str | None]:
    """Block until Swiggy redirects back, then hand over (code, state)."""
    print(f"Waiting for the redirect on {REDIRECT_URI} ...")
    await anyio.to_thread.run_sync(_serve_one_request)
    if _CallbackHandler.error:
        raise RuntimeError(f"Swiggy returned an error: {_CallbackHandler.error}")
    if not _CallbackHandler.code:
        raise RuntimeError("no authorization code in the callback")
    return _CallbackHandler.code, _CallbackHandler.state


async def main() -> None:
    storage = _MemoryTokenStorage()
    # The client registers itself via Dynamic Client Registration — there is no
    # client_id to apply for. See docs/start/developer.
    oauth = OAuthClientProvider(
        server_url=config.SWIGGY_MCP_INSTAMART_URL,
        client_metadata=OAuthClientMetadata(
            client_name="swiggy-jugaad",
            redirect_uris=[REDIRECT_URI],
            scope="mcp:tools",
            token_endpoint_auth_method="none",
        ),
        storage=storage,
        redirect_handler=_redirect_handler,
        callback_handler=_callback_handler,
    )

    # Since mcp 1.28 the transport takes a pre-built httpx client instead of an
    # auth= argument, so the OAuth provider attaches here. Timeouts match the
    # SDK's own defaults (long read is for SSE).
    async with httpx.AsyncClient(
        auth=oauth,
        timeout=httpx.Timeout(30.0, read=300.0),
        follow_redirects=True,
    ) as http_client:
        async with streamable_http_client(
            config.SWIGGY_MCP_INSTAMART_URL, http_client=http_client
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                # Proves the token works and shows the real tool names/params,
                # since the docs have drifted.
                tools = await session.list_tools()
                print(f"\nConnected. Instamart exposes {len(tools.tools)} tools:")
                for tool in tools.tools:
                    print(f"  - {tool.name}")

    if storage.tokens is None:
        sys.exit("\nLogged in, but no token was captured — nothing to paste.")

    print("\n" + "=" * 62)
    print("Paste this line into .env (replacing the empty SWIGGY_ACCESS_TOKEN):\n")
    print(f"SWIGGY_ACCESS_TOKEN={storage.tokens.access_token}")
    if storage.tokens.expires_in:
        days = storage.tokens.expires_in / 86400
        print(f"\nExpires in ~{days:.1f} days. Re-run this script when it does.")
    print("=" * 62)


if __name__ == "__main__":
    anyio.run(main)
