"""Button handlers for reply keyboard.

12-button layout: each button delegates to the corresponding command handler.
"""

from aiogram import F, Router
from aiogram.types import Message

router = Router(name="buttons")


@router.message(F.text == "📊 Статус")
async def btn_status(message: Message) -> None:
    from d_brain.bot.handlers.commands import cmd_status
    await cmd_status(message)


@router.message(F.text == "📝 Обработать")
async def btn_process(message: Message) -> None:
    from d_brain.bot.handlers.process import cmd_process
    await cmd_process(message)


@router.message(F.text == "❓ Помощь")
async def btn_help(message: Message) -> None:
    from d_brain.bot.handlers.commands import cmd_help
    await cmd_help(message)


@router.message(F.text == "💬 Чат")
async def btn_chat(message: Message) -> None:
    await message.answer(
        "💬 Просто отправь сообщение — я отвечу.\n"
        "Голос, текст, фото — всё принимаю."
    )


@router.message(F.text == "📅 Неделя")
async def btn_weekly(message: Message) -> None:
    from d_brain.bot.handlers.commands import cmd_weekly
    await cmd_weekly(message)


@router.message(F.text == "📊 Месяц")
async def btn_monthly(message: Message) -> None:
    from d_brain.bot.handlers.monthly import cmd_monthly
    await cmd_monthly(message)


@router.message(F.text == "📋 План")
async def btn_plan(message: Message) -> None:
    await message.answer(
        "📋 <b>План</b>\n\n"
        "Используй /process для обработки записей дня\n"
        "или просто опиши свой план текстом."
    )


@router.message(F.text == "🔎 Поиск")
async def btn_recall(message: Message) -> None:
    from d_brain.bot.handlers.recall import cmd_recall
    from aiogram.fsm.context import FSMContext
    # FSMContext not available in plain handler, use state-less mode
    await message.answer(
        "🔍 <b>Поиск по vault</b>\n\n"
        "Отправь /recall и ключевые слова для поиска.\n"
        "Пример: /recall проект immodriver"
    )


@router.message(F.text == "❤️ Здоровье")
async def btn_health(message: Message) -> None:
    from d_brain.bot.handlers.commands import cmd_status
    await message.answer("❤️ Проверяю здоровье системы...")
    await cmd_status(message)


@router.message(F.text == "🧠 Память")
async def btn_memory(message: Message) -> None:
    await message.answer(
        "🧠 <b>Память</b>\n\n"
        "Память хранится в vault: MEMORY.md + автодекей.\n"
        "Используй /recall для поиска по заметкам."
    )


@router.message(F.text == "⚙️ Настройки")
async def btn_settings(message: Message) -> None:
    from d_brain.config import get_settings
    settings = get_settings()
    lines = [
        "⚙️ <b>Настройки</b>",
        f"• Модель: <code>{settings.opencode_model}</code>",
        f"• Часовой пояс: <code>{settings.tz}</code>",
        f"• Webhook: {'вкл' if settings.webhook_enabled else 'выкл'}",
        f"• Cron: {'вкл' if settings.cron_enabled else 'выкл'}",
        f"• Todoist: {'настроен' if settings.todoist_api_key else 'не настроен'}",
        f"• Monthly: {'вкл' if settings.monthly_enabled else 'выкл'}",
    ]
    await message.answer("\n".join(lines))
