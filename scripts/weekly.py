#!/usr/bin/env python
"""Weekly digest script — generates and sends to Telegram.

Rewritten for the v3.0.x OpenCode-backed pipeline (2026-06): the old version
imported ``settings.todoist_api_key`` and ``processor.generate_weekly()``,
both of which were removed when the brain switched from Claude CLI + Todoist
to a shared OpenCode session. The weekly digest now goes through the same
``ClaudeProcessor``/``OpenCodeSession`` path as the daily processing, driving
the ``weekly-digest`` agent instructions in the vault.

    uv run python scripts/weekly.py

Exit code 0 on success (report sent or nothing to send), 1 on error.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path so `import d_brain` resolves when run as a script.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from d_brain.config import get_settings
from d_brain.services.git import VaultGit
from d_brain.services.runtime import get_processor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Generate weekly digest and send it to the admin Telegram chat."""
    settings = get_settings()
    processor = get_processor(settings)
    git = VaultGit(settings.vault_path)

    user_id = settings.admin_chat_id
    if user_id is None:
        logger.error("No allowed user IDs configured — cannot deliver digest")
        sys.exit(1)

    logger.info("Starting weekly digest generation...")
    result = processor.process_weekly()

    if "error" in result:
        report = f"Ошибка недельного дайджеста: {result['error']}"
        logger.error("Weekly digest failed: %s", result["error"])
    else:
        report = result.get("report") or "Недельный дайджест: пустой ответ"
        logger.info("Weekly digest generated successfully")
        # Commit any vault changes the agent made, then push.
        git.commit_and_push("chore: weekly digest")

    # Send to Telegram (HTML first, plain-text fallback on parse failure).
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        try:
            await bot.send_message(chat_id=user_id, text=report)
        except Exception:
            await bot.send_message(chat_id=user_id, text=report, parse_mode=None)
        logger.info("Weekly digest sent to user %s", user_id)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
