"""Processing service backed by OpenCode session.

Drives daily processing via OpenCode run calls.
"""

import logging
from datetime import date
from pathlib import Path
from typing import Any

from d_brain.services.opencode_session import DEFAULT_TIMEOUT, AskResult, OpenCodeSession

logger = logging.getLogger(__name__)

_STATUS_MESSAGES = {
    "rate_limited": "⏳ <b>Лимит исчерпан.</b> Вернусь, когда он обновится.",
    "logged_out": "🔑 <b>Нужен повторный вход.</b> Админу: <code>dbrain login</code>.",
    "timeout": "⌛ <b>Превышено время ожидания ответа.</b> Попробуйте ещё раз.",
    "error": "❌ <b>Ошибка.</b> Попробуйте позже.",
}


class ClaudeProcessor:
    """Builds prompts and runs them through OpenCodeSession."""

    def __init__(
        self,
        vault_path: Path,
        session: OpenCodeSession | None = None,
    ) -> None:
        self.vault_path = Path(vault_path)
        self.session = session

    def _to_report(self, res: AskResult) -> dict[str, Any]:
        if res.ok:
            return {"report": res.reply or "", "processed_entries": 1}
        logger.error("session returned %s: %s", res.status, res.detail)
        return {
            "error": _STATUS_MESSAGES.get(res.status, res.detail or "session error"),
            "processed_entries": 0,
        }

    def _ask(self, prompt: str, *, wrap: bool = True) -> dict[str, Any]:
        if self.session is None:
            return {"error": "session not configured", "processed_entries": 0}
        return self._to_report(
            self.session.ask(
                prompt, timeout=DEFAULT_TIMEOUT, wrap=wrap,
                request_id="maint-process",
            )
        )

    def _load_skill_content(self) -> str:
        skill_path = self.vault_path / ".claude/skills/dbrain-processor/SKILL.md"
        return skill_path.read_text() if skill_path.exists() else ""

    def _load_agent_content(self, name: str) -> str:
        """Read an agent instruction file from vault/.claude/agents/."""
        agent_path = self.vault_path / ".claude/agents" / f"{name}.md"
        return agent_path.read_text() if agent_path.exists() else ""

    def process_daily(self, day: date | None = None) -> dict[str, Any]:
        if day is None:
            day = date.today()
        daily_file = self.vault_path / "daily" / f"{day.isoformat()}.md"
        if not daily_file.exists():
            logger.warning("No daily file for %s", day)
            return {"error": f"No daily file for {day}", "processed_entries": 0}

        skill_content = self._load_skill_content()
        prompt = f"""Сегодня {day}. Выполни ежедневную обработку.

=== SKILL INSTRUCTIONS ===
{skill_content}
=== END SKILL ===

ЯДРО ОБРАБОТКИ:
1. Создай карточки из заметок дня по шаблону autograph
2. Свяжи карточки wiki-ссылками с хабами и соседями
3. Сформируй саммари дня → обнови MEMORY.md / handoff.md

CRITICAL OUTPUT FORMAT:
- Return ONLY raw HTML for Telegram (parse_mode=HTML)
- NO markdown: no **, no ## , no ```, no tables
- Start directly with 📊 <b>Обработка за {day}</b>
- Allowed tags: <b>, <i>, <code>, <s>, <u>
- If entries already processed, return status report in same HTML format"""
        return self._ask(prompt, wrap=True)

    def process_weekly(self) -> dict[str, Any]:
        """Generate the weekly digest through the shared OpenCode session.

        Mirrors :meth:`process_daily` but drives the ``weekly-digest`` agent
        instructions and analyses the last 7 days instead of a single day.
        """
        agent_content = self._load_agent_content("weekly-digest")

        prompt = f"""Выполни генерацию недельного дайджеста за последнюю неделю.

=== WEEKLY DIGEST AGENT ===
{agent_content}
=== END AGENT ===

ЯДРО ДАЙДЖЕСТА:
1. Проанализируй daily-заметки за последние 7 дней (daily/YYYY-MM-DD.md)
2. Оцени прогресс по целям (goals/) — победы, вызовы, динамику
3. Предложи ONE Big Thing и топ-3 приоритета на следующую неделю
4. При наличии архивируй текущий goals/3-weekly.md и создай новый

CRITICAL OUTPUT FORMAT:
- Return ONLY raw HTML for Telegram (parse_mode=HTML)
- NO markdown: no **, no ## , no ```, no tables
- Start directly with 📅 <b>Недельный дайджест</b>
- Allowed tags: <b>, <i>, <code>, <s>, <u>
- If there is nothing to digest (нет данных за неделю), return a short
  status note in the same HTML format instead of an empty report."""
        return self._ask(prompt, wrap=True)
