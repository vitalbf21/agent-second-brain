"""Monthly report handler and scheduler.

Generates comprehensive monthly reports analyzing goals, weekly summaries,
and vault content. Triggered by /monthly command or APScheduler on the 1st.
"""

import asyncio
import logging
from pathlib import Path

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from d_brain.bot.formatters import sanitize_telegram_html, truncate_html, format_error
from d_brain.config import get_settings
from d_brain.services.git import VaultGit
from d_brain.services.processor import ClaudeProcessor
from d_brain.services.runtime import get_session

logger = logging.getLogger(__name__)
router = Router(name="monthly")


def _collect_monthly_context(vault_path: Path) -> str:
    """Collect context for monthly report: last 4 weekly summaries + goals."""
    parts: list[str] = []

    # Last 4 weekly summaries
    summaries_dir = vault_path / "summaries"
    if summaries_dir.exists():
        summary_files = sorted(summaries_dir.glob("*-summary.md"), reverse=True)[:4]
        for sf in summary_files:
            try:
                content = sf.read_text(encoding="utf-8")[:2000]
                parts.append(f"=== {sf.stem} ===\n{content}")
            except OSError:
                continue

    # Goals
    goals_dir = vault_path / "goals"
    for goal_file in ["0-vision-3y.md", "1-yearly-2025.md", "2-monthly.md", "3-weekly.md"]:
        path = goals_dir / goal_file
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8")[:1500]
                parts.append(f"=== {goal_file} ===\n{content}")
            except OSError:
                continue

    # Today's date context
    from datetime import date
    today = date.today()
    parts.append(f"Сегодня: {today}, конец месяца: {today.month}/12")

    return "\n\n".join(parts)


async def _generate_and_send_monthly(bot, chat_id: int) -> None:
    """Generate monthly report and send to chat."""
    settings = get_settings()
    session = get_session(settings)
    processor = ClaudeProcessor(settings.vault_path, session=session)
    git = VaultGit(settings.vault_path)

    status_msg = await bot.send_message(chat_id, "📊 Генерирую месячный отчёт...")

    # Collect context
    context = await asyncio.to_thread(_collect_monthly_context, settings.vault_path)

    prompt = f"""Сгенерируй месячный отчёт на основе данных:

{context}

ФОРМАТ ОТЧЁТА (Telegram HTML):
- Начни с 📊 <b>Месячный отчёт</b>
- Разделы: Цели, Достижено, Вызовы, Статистика, План на следующий месяц
- Используй только <b>, <i>, <code>, <s>, <u> теги
- Без markdown: без **, ##, ```, таблиц
- Кратко и по существу, до 3000 символов"""

    result = processor._ask(prompt, wrap=True)

    if "error" in result:
        await status_msg.edit_text(format_error(result["error"]))
        return

    report = result.get("report", "Нет данных для отчёта")
    sanitized = sanitize_telegram_html(report)
    truncated = truncate_html(sanitized, max_length=4000)

    await status_msg.edit_text(truncated)

    # Save to vault
    from datetime import date
    today = date.today()
    summary_path = settings.vault_path / "summaries" / f"{today.year}-{today.month:02d}-monthly.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(report, encoding="utf-8")

    # Git commit
    await asyncio.to_thread(git.commit_and_push, f"chore: monthly report {today}")


@router.message(Command("monthly"))
async def cmd_monthly(message: Message) -> None:
    """Handle /monthly command - generate monthly report."""
    await _generate_and_send_monthly(message.bot, message.chat.id)


async def scheduled_monthly_report(bot, chat_id: int) -> None:
    """APScheduler job: generate monthly report on the 1st."""
    try:
        await _generate_and_send_monthly(bot, chat_id)
    except Exception as e:
        logger.exception("Monthly report generation failed")
        try:
            await bot.send_message(chat_id, f"❌ Ошибка генерации месячного отчёта: {e}")
        except Exception:
            pass


async def scheduled_monthly_reminder(bot, chat_id: int) -> None:
    """APScheduler job: remind about monthly report on 2nd-3rd."""
    from datetime import date
    today = date.today()
    settings = get_settings()

    # Check if report already exists
    summary_path = settings.vault_path / "summaries" / f"{today.year}-{today.month:02d}-monthly.md"
    if summary_path.exists() and summary_path.stat().st_size > 100:
        return  # Already processed

    try:
        await bot.send_message(
            chat_id,
            "📊 Напоминание: месячный отчёт ещё не сгенерирован.\n"
            "Отправь /monthly чтобы создать его."
        )
    except Exception:
        pass
