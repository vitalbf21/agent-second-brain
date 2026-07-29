"""Process command handler with progress bar."""

import asyncio
import logging
from datetime import date

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from d_brain.bot.formatters import format_process_report
from d_brain.bot.progress import run_with_progress, BusyError
from d_brain.bot.undo import register_undo, build_undo_keyboard, schedule_button_removal
from d_brain.config import get_settings
from d_brain.services.git import VaultGit
from d_brain.services.runtime import get_ask_lock, get_processor

router = Router(name="process")
logger = logging.getLogger(__name__)


@router.message(Command("process"))
async def cmd_process(message: Message) -> None:
    """Handle /process command - trigger Claude processing with progress bar."""
    user_id = message.from_user.id if message.from_user else "unknown"
    logger.info("Process command triggered by user %s", user_id)

    status_msg = await message.answer("⏳ Обработка... (может занять до 10 мин)")

    settings = get_settings()
    processor = get_processor(settings)
    git = VaultGit(settings.vault_path)

    # Capture SHA before processing
    sha_before = await asyncio.to_thread(git.get_head_sha)

    try:
        async with get_ask_lock():
            report = await run_with_progress(
                processor.process_daily,
                status_msg,
                "Обработка",
                date.today(),
            )
    except BusyError:
        await status_msg.edit_text("⏳ AI занят, попробуйте через минуту.")
        return

    # Commit and push changes
    if "error" not in report:
        today = date.today().isoformat()
        commit_sha = await asyncio.to_thread(
            lambda: git.commit_and_push(f"chore: process daily {today}") or git.get_head_sha()
        )

        # Add undo button if commit was made
        sha_after = await asyncio.to_thread(git.get_head_sha)
        if sha_after and sha_after != sha_before:
            undo_key = register_undo(sha_after, f"Обработка {today}")
            undo_kb = build_undo_keyboard(undo_key)
            formatted = format_process_report(report)
            try:
                msg = await status_msg.edit_text(formatted, reply_markup=undo_kb)
                asyncio.create_task(schedule_button_removal(msg, delay_seconds=300))
            except Exception:
                await status_msg.edit_text(formatted, parse_mode=None)
            return

    # Format and send report (no undo)
    formatted = format_process_report(report)
    try:
        await status_msg.edit_text(formatted)
    except Exception:
        await status_msg.edit_text(formatted, parse_mode=None)
