"""Progress bar for long-running AI operations.

Uses a global asyncio.Lock to serialize AI calls with queue visibility.
Updates Telegram status message every 30 seconds with elapsed time.
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_claude_lock = asyncio.Lock()
_queue_size = 0
MAX_QUEUE = 2


class BusyError(Exception):
    """Raised when AI is busy and queue is full."""

    pass


async def run_with_progress(
    fn: Callable[..., Any],
    status_msg: Any,
    label: str,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Run a function with progress updates on a Telegram message.

    Args:
        fn: Synchronous function to run in thread
        status_msg: Telegram message to edit with progress
        label: Human-readable label (e.g. "Обработка")
        *args, **kwargs: Arguments to pass to fn

    Returns:
        Result of fn()

    Raises:
        BusyError: If queue is full
    """
    global _queue_size  # noqa: PLW0603

    if _queue_size >= MAX_QUEUE:
        raise BusyError("AI занят, попробуйте через минуту")

    async with _claude_lock:
        _queue_size += 1
        try:
            task = asyncio.create_task(asyncio.to_thread(fn, *args, **kwargs))
            start = asyncio.get_event_loop().time()
            elapsed = 0

            while not task.done():
                await asyncio.sleep(30)
                elapsed = int(asyncio.get_event_loop().time() - start)
                if not task.done():
                    try:
                        mins, secs = divmod(elapsed, 60)
                        queue_info = f" (очередь: {_queue_size - 1})" if _queue_size > 1 else ""
                        await status_msg.edit_text(
                            f"⏳ {label}... ({mins}м {secs}с){queue_info}"
                        )
                    except Exception:
                        pass  # Ignore edit errors (message deleted, etc.)

            return task.result()
        finally:
            _queue_size -= 1
