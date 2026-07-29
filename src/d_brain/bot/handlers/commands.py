"""Command handlers for /start, /help, /status, /new, /compact, /monthly, /recall, /weekly."""

import asyncio
from datetime import date

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from d_brain.bot.keyboards import get_main_keyboard
from d_brain.config import get_settings
from d_brain.services.chat_session import ChatSessionManager
from d_brain.services.session import SessionStore
from d_brain.services.storage import VaultStorage

router = Router(name="commands")


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Handle /start command."""
    await message.answer(
        "<b>d-brain</b> — персональный ассистент\n\n"
        "Просто пиши мне — я отвечу.\n"
        "Голосовые, текст, фото, пересланные — всё принимаю.\n\n"
        "<b>Команды:</b>\n"
        "/new — новый чат\n"
        "/compact — сжать контекст\n"
        "/status — статус дня\n"
        "/process — обработать записи\n"
        "/weekly — недельный дайджест\n"
        "/monthly — месячный отчёт\n"
        "/recall — поиск по vault\n"
        "/help — справка",
        reply_markup=get_main_keyboard(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Handle /help command."""
    await message.answer(
        "<b>d-brain — персональный ассистент</b>\n\n"
        "Просто отправляй что угодно — AI обработает и ответит.\n\n"
        "🎤 Голосовое — транскрибирую и обработаю\n"
        "💬 Текст — обработаю как есть\n"
        "📷 Фото — прочитаю и сохраню\n\n"
        "<b>Команды:</b>\n"
        "/new — новый чат (сброс сессии)\n"
        "/compact — сжать контекст сессии\n"
        "/status — статус сегодняшнего дня\n"
        "/process — обработать записи дня\n"
        "/weekly — недельный дайджест\n"
        "/monthly — месячный отчёт\n"
        "/recall <i>запрос</i> — поиск по vault"
    )


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    """Handle /status command."""
    user_id = message.from_user.id if message.from_user else 0
    settings = get_settings()
    storage = VaultStorage(settings.vault_path)

    session = SessionStore(settings.vault_path)
    session.append(user_id, "command", cmd="/status")

    today = date.today()
    content = storage.read_daily(today)

    if not content:
        await message.answer(f"📅 <b>{today}</b>\n\nЗаписей пока нет.")
        return

    lines = content.strip().split("\n")
    entries = [line for line in lines if line.startswith("## ")]

    voice_count = sum(1 for e in entries if "[voice]" in e)
    text_count = sum(1 for e in entries if "[text]" in e)
    photo_count = sum(1 for e in entries if "[photo]" in e)
    forward_count = sum(1 for e in entries if "[forward from:" in e)

    total = len(entries)

    week_stats = ""
    stats = session.get_stats(user_id, days=7)
    if stats:
        week_stats = "\n\n<b>За 7 дней:</b>"
        for entry_type, count in sorted(stats.items()):
            week_stats += f"\n• {entry_type}: {count}"

    await message.answer(
        f"📅 <b>{today}</b>\n\n"
        f"Всего записей: <b>{total}</b>\n"
        f"- 🎤 Голосовых: {voice_count}\n"
        f"- 💬 Текстовых: {text_count}\n"
        f"- 📷 Фото: {photo_count}\n"
        f"- ↩️ Пересланных: {forward_count}"
        f"{week_stats}"
    )


@router.message(Command("new"))
async def cmd_new(message: Message) -> None:
    """Start fresh Claude session."""
    if not message.from_user:
        return

    settings = get_settings()
    manager = ChatSessionManager(settings.vault_path)
    manager.reset(message.from_user.id)

    await message.answer(
        "🔄 <b>Новый чат</b>\n\n"
        "Контекст сброшен. Можешь начать заново."
    )


@router.message(Command("compact"))
async def cmd_compact(message: Message) -> None:
    """Compact Claude session context."""
    await message.answer(
        "📦 Контекст будет сжат при следующем сообщении.\n"
        "Просто напиши что-нибудь."
    )


@router.message(Command("weekly"))
async def cmd_weekly(message: Message) -> None:
    """Handle /weekly command - trigger weekly digest."""
    from d_brain.services.processor import ClaudeProcessor
    from d_brain.services.runtime import get_processor
    from d_brain.services.git import VaultGit
    from d_brain.bot.formatters import format_process_report

    settings = get_settings()
    processor = get_processor(settings)

    status_msg = await message.answer("📅 Генерирую недельный дайджест...")

    result = await asyncio.to_thread(processor.process_weekly)

    if "error" in result:
        await status_msg.edit_text(f"❌ {result['error']}")
        return

    report = result.get("report", "Нет данных")
    from d_brain.bot.formatters import sanitize_telegram_html, truncate_html
    sanitized = sanitize_telegram_html(report)
    truncated = truncate_html(sanitized, max_length=4000)
    await status_msg.edit_text(truncated)

    # Git commit
    git = VaultGit(settings.vault_path)
    await asyncio.to_thread(git.commit_and_push, f"chore: weekly digest {date.today()}")
