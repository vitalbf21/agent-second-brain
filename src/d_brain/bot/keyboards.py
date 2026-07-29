"""Reply keyboards for Telegram bot.

12-button layout (4x3) inspired by Life Pilot Agent.
"""

from aiogram.types import ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Main reply keyboard with 12 commands in 4x3 grid."""
    builder = ReplyKeyboardBuilder()

    # Row 1: Core actions
    builder.button(text="🔍 Найти")
    builder.button(text="📝 Обработать")
    builder.button(text="💬 Чат")

    # Row 2: Reports
    builder.button(text="📅 Неделя")
    builder.button(text="📊 Месяц")
    builder.button(text="📋 План")

    # Row 3: Info
    builder.button(text="📊 Статус")
    builder.button(text="❓ Помощь")
    builder.button(text="🔎 Поиск")

    # Row 4: System
    builder.button(text="❤️ Здоровье")
    builder.button(text="🧠 Память")
    builder.button(text="⚙️ Настройки")

    builder.adjust(3, 3, 3, 3)
    return builder.as_markup(resize_keyboard=True, is_persistent=True)
