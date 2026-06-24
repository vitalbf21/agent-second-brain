"""Chat session manager backed by OpenCode run calls.

Replaced the persistent tmux-based Claude session with direct
``opencode run`` calls. No session to steer or interrupt — each
message is a fresh subprocess call.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

from d_brain.config import get_settings
from d_brain.services.runtime import get_ask_lock, get_session

logger = logging.getLogger(__name__)

_STATUS_MESSAGES = {
    "rate_limited": "⏳ Лимит исчерпан. Попробуй позже.",
    "logged_out": "🔑 Нужен повторный вход. Админу: dbrain login.",
    "timeout": "⌛ Превышено время ожидания ответа. Попробуй ещё раз.",
    "error": "❌ Ошибка. Попробуй позже.",
}


class ChatSessionManager:
    """Routes chat messages to opencode run calls."""

    def __init__(
        self,
        vault_path: Path | str,
        session: Any | None = None,
    ) -> None:
        self.vault_path = Path(vault_path)
        self._session = session if session is not None else get_session(get_settings())

    async def send_message(self, user_id: int, prompt: str) -> str:
        async with get_ask_lock():
            res = await asyncio.to_thread(self._session.ask, prompt)
        if res.ok:
            return res.reply or ""
        logger.warning("session ask for user %d returned %s", user_id, res.status)
        return _STATUS_MESSAGES.get(res.status, _STATUS_MESSAGES["error"])

    async def send_control(self, text: str) -> None:
        pass

    def is_turn_active(self) -> bool:
        return False

    def is_steerable_turn(self) -> bool:
        return False

    async def steer(self, text: str) -> None:
        pass

    async def interrupt(self) -> None:
        pass

    def reset(self, user_id: int) -> None:
        logger.info("session reset requested by user %d", user_id)

    async def compact(self, user_id: int) -> str:
        return "🧹 Сессия очищена (важные данные сохранены в файлах)."
