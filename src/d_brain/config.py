"""Application configuration using Pydantic Settings."""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str = Field(description="Telegram Bot API token")
    deepgram_api_key: str = Field(description="Deepgram API key for transcription")
    vault_path: Path = Field(
        default=Path("./vault"),
        description="Path to Obsidian vault directory",
    )
    allowed_user_ids: list[int] = Field(
        default_factory=list,
        description="List of Telegram user IDs allowed to use the bot",
    )
    allow_all_users: bool = Field(
        default=False,
        description="Whether to allow access to all users (security risk!)",
    )

    # ── Todoist integration ────────────────────────────────────────
    todoist_api_key: str = Field(
        default="",
        description="Todoist REST API key for task management",
    )

    # ── Feature flags ──────────────────────────────────────────────
    monthly_enabled: bool = Field(
        default=True,
        description="Enable monthly report generation",
    )
    recall_enabled: bool = Field(
        default=True,
        description="Enable vault search (/recall)",
    )

    # ── OpenCode settings ────────────────────────────────────────────
    opencode_model: str = Field(
        default="opencode/big-pickle",
        description="Model for opencode (format: provider/model)",
    )
    opencode_bin: str = Field(
        default="opencode",
        description="Path to opencode binary",
    )
    runtime_dir: Path = Field(
        default_factory=lambda: Path.home() / ".dbrain",
        description="Runtime dir for state files",
    )
    tz: str = Field(default="UTC", description="Timezone for timers/reports")

    # ── webhook settings ──────────────────────────────────────────────
    webhook_enabled: bool = Field(
        default=True,
        description="Use webhook instead of polling",
    )
    webhook_host: str = Field(
        default="https://bot.immooff.online",
        description="Public URL for Telegram webhook (https://...)",
    )
    webhook_port: int = Field(
        default=8443,
        description="Local port for webhook server",
    )

    # ── cron (scheduled jobs in the second brain session) ────────────
    cron_enabled: bool = Field(
        default=True,
        description="Run the in-bot cron ticker",
    )
    cron_tick_seconds: float = Field(
        default=60.0,
        description="Ticker interval; jobs.json is re-read every tick",
    )
    cron_job_timeout: float = Field(
        default=600.0,
        description="Per-job ask() timeout in the cron session",
    )
    cron_max_consecutive_errors: int = Field(
        default=3,
        description="Consecutive failures before a job is auto-disabled",
    )
    cron_retry_seconds: float = Field(
        default=300.0,
        description="Retry delay for a failed one-shot ('at') job",
    )

    @field_validator("runtime_dir", "vault_path", mode="after")
    @classmethod
    def _expand_user(cls, v: Path) -> Path:
        return v.expanduser().resolve()

    @property
    def cron_dir(self) -> Path:
        """Cron state dir: jobs.json + the cron session's runtime files."""
        return self.runtime_dir / "cron"

    @property
    def admin_chat_id(self) -> int | None:
        """First allowed user — destination for health alerts / reports."""
        return self.allowed_user_ids[0] if self.allowed_user_ids else None

    @property
    def daily_path(self) -> Path:
        """Path to daily notes directory."""
        return self.vault_path / "daily"

    @property
    def attachments_path(self) -> Path:
        """Path to attachments directory."""
        return self.vault_path / "attachments"

    @property
    def thoughts_path(self) -> Path:
        """Path to thoughts directory."""
        return self.vault_path / "thoughts"


def get_settings() -> Settings:
    """Get application settings instance."""
    return Settings()
