#!/usr/bin/env python
"""Monthly digest script — generates and sends to Telegram.

Analogous to weekly.py but for monthly reports.
Triggered by d-brain-monthly.timer on the 1st of each month.

    uv run python scripts/monthly.py

Exit code 0 on success, 1 on error.
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from d_brain.config import get_settings
from d_brain.services.git import VaultGit
from d_brain.services.runtime import get_session, get_processor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _collect_monthly_context(vault_path: Path) -> str:
    """Collect context for monthly report."""
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

    from datetime import date
    today = date.today()
    parts.append(f"Сегодня: {today}, конец месяца: {today.month}/12")

    return "\n\n".join(parts)


async def main() -> None:
    """Generate monthly digest and send it to the admin Telegram chat."""
    settings = get_settings()
    processor = get_processor(settings)
    git = VaultGit(settings.vault_path)

    user_id = settings.admin_chat_id
    if user_id is None:
        logger.error("No allowed user IDs configured — cannot deliver report")
        sys.exit(1)

    logger.info("Starting monthly report generation...")

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
        report = f"Ошибка месячного отчёта: {result['error']}"
        logger.error("Monthly report failed: %s", result["error"])
    else:
        report = result.get("report") or "Месячный отчёт: пустой ответ"
        logger.info("Monthly report generated successfully")
        git.commit_and_push("chore: monthly report")

    # Save to vault
    from datetime import date
    today = date.today()
    summary_path = settings.vault_path / "summaries" / f"{today.year}-{today.month:02d}-monthly.md"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(report, encoding="utf-8")

    # Send to Telegram
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        try:
            await bot.send_message(chat_id=user_id, text=report)
        except Exception:
            await bot.send_message(chat_id=user_id, text=report, parse_mode=None)
        logger.info("Monthly report sent to user %s", user_id)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
