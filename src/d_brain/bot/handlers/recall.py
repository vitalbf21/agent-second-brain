"""Recall handler — search across vault with morphological Russian queries.

Uses vault_search for grep-based search + Claude for analysis.
"""

import asyncio
import logging
import re

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from d_brain.bot.formatters import sanitize_telegram_html, truncate_html, format_error
from d_brain.config import get_settings
from d_brain.services.vault_search import search_vault
from d_brain.services.runtime import get_session

logger = logging.getLogger(__name__)
router = Router(name="recall")


class RecallStates(StatesGroup):
    waiting_query = State()


_STOP_WORDS = {
    "как", "что", "где", "когда", "это", "его", "её", "их",
    "был", "была", "были", "будет", "можно", "нужно", "надо",
    "ещё", "уже", "или", "но", "а", "в", "на", "из", "по",
    "для", "от", "до", "не", "ни", "да", "нет", "ты", "я",
    "мы", "он", "она", "оно", "они", "все", "всё", "вся",
}


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from query text."""
    words = re.findall(r"[а-яА-ЯёЁa-zA-Z]{4,}", text.lower())
    return [w for w in words if w not in _STOP_WORDS][:8]


async def _run_search(message: Message, query: str) -> None:
    """Execute vault search and send results with Claude analysis."""
    settings = get_settings()
    keywords = _extract_keywords(query)

    if not keywords:
        await message.answer("🔍 Не нашёл значимых ключевых слов. Попробуйте иначе.")
        return

    status_msg = await message.answer(f"🔍 Ищу: {', '.join(keywords)}...")

    # Run grep search
    results = await asyncio.to_thread(
        search_vault, " ".join(keywords), settings.vault_path, limit=10
    )

    if not results:
        await status_msg.edit_text("🔍 Ничего не найдено по запросу.")
        return

    # Format search results
    context_parts: list[str] = []
    for r in results:
        context_parts.append(
            f"📄 {r['path']} ({r['date']}, {r['category']})\n"
            f"{r['content'][:500]}"
        )
    context = "\n\n---\n\n".join(context_parts)

    # Ask Claude to analyze
    session = get_session(settings)
    prompt = f"""Проанализируй результаты поиска по vault и дай краткий ответ.

Запрос: {query}

Найденные записи ({len(results)} шт.):
{context}

Ответь кратко на русском, выдели ключевую информацию. Telegram HTML формат."""
    result = session.ask(prompt, timeout=120, wrap=True, request_id="recall")

    if result.ok and result.reply:
        sanitized = sanitize_telegram_html(result.reply)
        truncated = truncate_html(sanitized, max_length=4000)
        # Add source list
        sources = "\n".join(f"• {r['path']}" for r in results[:5])
        truncated += f"\n\n<b>Источники:</b>\n{sources}"
        await status_msg.edit_text(truncated)
    else:
        # Fallback: show raw results
        text = f"🔍 Найдено {len(results)} записей:\n\n"
        for r in results[:5]:
            text += f"📄 <b>{r['path']}</b> ({r['date']})\n"
            preview = r["content"][:200].replace("\n", " ")
            text += f"<i>{preview}...</i>\n\n"
        await status_msg.edit_text(truncate_html(text, 4000))


@router.message(Command("recall"))
async def cmd_recall(message: Message, state: FSMContext) -> None:
    """Handle /recall command - start vault search."""
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        # Inline query: /recall что-то
        await _run_search(message, args[1])
    else:
        # FSM mode: ask for query
        await state.set_state(RecallStates.waiting_query)
        await message.answer(
            "🔍 <b>Поиск по vault</b>\n\n"
            "Отправь ключевые слова или фразу для поиска.\n"
            "Поддерживается русский язык с морфологией."
        )


@router.message(RecallStates.waiting_query)
async def handle_recall_query(message: Message, state: FSMContext) -> None:
    """Handle recall search query."""
    if not message.text:
        await message.answer("Отправь текстовый запрос.")
        return

    await state.clear()
    await _run_search(message, message.text)
