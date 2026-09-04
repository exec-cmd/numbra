from __future__ import annotations

import asyncio


async def timed_prompt(text: str, timeout: float) -> str | None:
    """Read an answer while continuously showing the remaining time."""
    try:
        from prompt_toolkit import PromptSession
    except ImportError:
        return input(text)
    session: PromptSession = PromptSession()
    loop = asyncio.get_running_loop()
    started = loop.time()

    def toolbar() -> str:
        remaining = max(0.0, timeout - (loop.time() - started))
        return f"Time left: {remaining:04.1f}s"

    try:
        return await asyncio.wait_for(
            session.prompt_async(text, bottom_toolbar=toolbar, refresh_interval=0.1),
            timeout=timeout,
        )
    except TimeoutError:
        return None
