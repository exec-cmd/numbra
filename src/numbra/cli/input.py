from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable


async def timed_prompt(text: str, timeout: float, strict: bool = True) -> str | None:
    """Read an answer while continuously showing the remaining time."""
    try:
        from prompt_toolkit import PromptSession
    except ImportError:
        return input(text)
    session: PromptSession = PromptSession()
    loop = asyncio.get_running_loop()
    started = loop.time()

    def toolbar() -> str:
        elapsed = loop.time() - started
        remaining = timeout - elapsed
        if remaining >= 0:
            return f"Time left: {remaining:04.1f}s"
        return f"Overdue: {-remaining:04.1f}s"

    try:
        prompt = session.prompt_async(text, bottom_toolbar=toolbar, refresh_interval=0.1)
        if strict:
            return await asyncio.wait_for(prompt, timeout=timeout)
        return await prompt
    except TimeoutError:
        return None


async def cooldown(
    seconds: float,
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    if not 1.0 <= seconds <= 3.0:
        raise ValueError("cooldown must be between 1 and 3 seconds")
    await sleeper(seconds)
