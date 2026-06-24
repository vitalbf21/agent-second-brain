"""Process-wide singletons for the shared OpenCode session.

The bot, the daily pipeline and the watchdog all use a single OpenCodeSession
that calls ``opencode run`` directly (no persistent tmux session). An asyncio
lock serializes ask() calls within the bot process.
"""

import asyncio
from pathlib import Path

from d_brain.config import Settings
from d_brain.services.opencode_session import OpenCodeSession
from d_brain.services.processor import ClaudeProcessor

_session: OpenCodeSession | None = None
_cron_session: OpenCodeSession | None = None
_processor: ClaudeProcessor | None = None
_ask_lock = asyncio.Lock()


def reset() -> None:
    """Drop the singletons (tests only)."""
    global _session, _cron_session, _processor
    _session = None
    _cron_session = None
    _processor = None


def _build_session(settings: Settings) -> OpenCodeSession:
    return OpenCodeSession(
        settings.vault_path,
        model=settings.opencode_model,
        opencode_bin=settings.opencode_bin,
    )


def get_session(settings: Settings) -> OpenCodeSession:
    """Return the shared OpenCodeSession singleton."""
    global _session
    if _session is None:
        _session = _build_session(settings)
    return _session


def get_cron_session(settings: Settings) -> OpenCodeSession:
    """Return the cron brain — a second, isolated OpenCodeSession."""
    global _cron_session
    if _cron_session is None:
        _cron_session = _build_session(settings)
    return _cron_session


def get_processor(settings: Settings) -> ClaudeProcessor:
    global _processor
    if _processor is None:
        _processor = ClaudeProcessor(
            settings.vault_path,
            session=get_session(settings),
        )
    return _processor


def get_ask_lock() -> asyncio.Lock:
    return _ask_lock
