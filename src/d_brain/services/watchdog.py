"""Liveness watchdog for the OpenCode session.

Simplified: no persistent tmux session to monitor. Just checks that
opencode is available and the bot process is alive.
"""

import logging
import shutil
from pathlib import Path
from typing import Any

from d_brain.services.systemd_notify import notify, watchdog_interval

logger = logging.getLogger(__name__)

DEFAULT_TICK = 60.0


def _telegram_alerter(settings: Any) -> Any:
    """Build an alert callable that delivers via Telegram bot API."""
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    def alert(text: str) -> None:
        import asyncio
        chat_id = settings.admin_chat_id
        if chat_id is None:
            logger.warning("no admin_chat_id — cannot deliver alert")
            return
        try:
            asyncio.run(bot.send_message(chat_id=chat_id, text=text))
        except Exception:
            logger.exception("failed to deliver alert")

    return alert


def run_watchdog(settings: Any) -> int:
    """Run a single watchdog check cycle."""
    # Check opencode binary is available
    bin_ = shutil.which(settings.opencode_bin) or settings.opencode_bin
    if not shutil.which(bin_):
        logger.error("opencode binary not found: %s", settings.opencode_bin)
        _telegram_alerter(settings)(
            f"🔴 <b>Watchdog:</b> opencode не найден ({settings.opencode_bin})"
        )
        return 1

    notify("WATCHDOG=1")
    return 0


def main_loop() -> None:
    """Run the watchdog loop forever."""
    import time
    from d_brain.config import get_settings

    settings = get_settings()
    interval = watchdog_interval() or DEFAULT_TICK
    logger.info("watchdog started (tick %.0fs)", interval)

    while True:
        try:
            run_watchdog(settings)
        except Exception:
            logger.exception("watchdog tick failed")
        time.sleep(interval)


if __name__ == "__main__":
    main_loop()
