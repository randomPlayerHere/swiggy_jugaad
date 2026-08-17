"""CLI adapter (v1) + the agent loop (plain Python, no LangChain):
LLM → tool call → result → repeat.

Telegram/WhatsApp is a later interface on the same agent loop, not part
of v1.
"""

from .cli import main

__all__ = ["main"]
