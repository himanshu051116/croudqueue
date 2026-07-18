from __future__ import annotations

import asyncio
import sys


def configure_event_loop_policy() -> None:
    """Use the selector policy required by psycopg's async implementation on Windows."""

    if sys.platform == "win32":
        # The policy exists at runtime on Windows but is omitted from portable stubs.
        policy_factory = getattr(asyncio, "WindowsSelectorEventLoopPolicy")
        asyncio.set_event_loop_policy(policy_factory())


def selector_event_loop() -> asyncio.AbstractEventLoop:
    """Create Uvicorn's psycopg-compatible Windows event loop."""

    return asyncio.SelectorEventLoop()
