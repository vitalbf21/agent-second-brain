"""Undo system for git-based vault changes.

Every AI action that creates a git commit gets an undo button with a 5-minute TTL.
The undo reverts the commit via `git revert --no-edit` and pushes.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from d_brain.services.git import VaultGit
from d_brain.config import get_settings

logger = logging.getLogger(__name__)

router = Router(name="undo")

TTL_MINUTES = 5


@dataclass
class UndoPayload:
    commit_sha: str
    description: str
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def expired(self) -> bool:
        return datetime.now() - self.created_at > timedelta(minutes=TTL_MINUTES)


# In-memory store: callback_key -> UndoPayload
_store: dict[str, UndoPayload] = {}


def register_undo(commit_sha: str, description: str) -> str:
    """Register an undoable action. Returns a callback key."""
    key = f"undo_{commit_sha[:8]}"
    _store[key] = UndoPayload(commit_sha=commit_sha, description=description)
    _cleanup_expired()
    return key


def build_undo_keyboard(
    callback_key: str, extra_buttons: list[InlineKeyboardButton] | None = None
) -> InlineKeyboardMarkup:
    """Build inline keyboard with undo button + optional extra buttons."""
    buttons = []
    if extra_buttons:
        buttons.append(extra_buttons)
    buttons.append([InlineKeyboardButton(text="↩️ Отменить (5 мин)", callback_data=callback_key)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def schedule_button_removal(message, delay_seconds: int = 300) -> None:
    """Remove inline keyboard after TTL expires."""
    await asyncio.sleep(delay_seconds)
    try:
        await message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass  # Message deleted or edited already


@router.callback_query(F.data.startswith("undo_"))
async def handle_undo(callback: CallbackQuery) -> None:
    """Handle undo button callback."""
    key = callback.data
    payload = _store.get(key)

    if payload is None:
        await callback.answer("⏱ Кнопка истекла", show_alert=True)
        return

    if payload.expired:
        _store.pop(key, None)
        await callback.answer("⏱ Время отмены истекло", show_alert=True)
        return

    settings = get_settings()
    git = VaultGit(settings.vault_path)

    success, error = await asyncio.to_thread(git.revert_commit, payload.commit_sha)

    if success:
        _store.pop(key, None)
        await callback.message.edit_text(
            f"✅ Отменено: {payload.description}\n"
            f"<code>{payload.commit_sha[:8]}</code>",
            reply_markup=None,
        )
        await callback.answer("Отменено")
    else:
        await callback.answer(f"Ошибка: {error[:100]}", show_alert=True)


def _cleanup_expired() -> None:
    """Remove expired entries from store."""
    expired = [k for k, v in _store.items() if v.expired]
    for k in expired:
        _store.pop(k, None)
