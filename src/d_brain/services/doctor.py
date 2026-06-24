"""Daily self-diagnostic using OpenCode.

Once a day it asks the model a canary question, runs a handful of cheap
local checks, and reports a single 🟢/🔴 message to Telegram.
"""

import logging
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from d_brain.services.opencode_session import OpenCodeSession

logger = logging.getLogger(__name__)

CANARY_TOKEN = "DBRAIN_OK"
CANARY_TIMEOUT = 120.0


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class DoctorReport:
    ok: bool
    checks: list[CheckResult] = field(default_factory=list)

    def to_telegram(self) -> str:
        header = (
            "🟢 <b>Осмотр пройден</b>" if self.ok else "🔴 <b>Осмотр: есть проблемы</b>"
        )
        lines = [f"{'✅' if c.ok else '❌'} {c.name}: {c.detail}" for c in self.checks]
        return header + "\n" + "\n".join(lines)


class Doctor:
    def __init__(
        self,
        session: OpenCodeSession | Any,
        *,
        checks: list[Callable[[], CheckResult]] | None = None,
        canary_token: str = CANARY_TOKEN,
    ) -> None:
        self.session = session
        self._checks = checks if checks is not None else []
        self._canary_token = canary_token

    def _canary(self) -> CheckResult:
        res = self.session.ask(
            f"Reply with exactly {self._canary_token} and nothing else.",
            timeout=CANARY_TIMEOUT,
            request_id="maint-doctor",
        )
        if res.status == "logged_out":
            return CheckResult("canary", False, "нужен повторный вход")
        if res.status == "rate_limited":
            return CheckResult("canary", False, "лимит исчерпан")
        if res.ok and self._canary_token in (res.reply or ""):
            return CheckResult("canary", True, "модель отвечает")
        return CheckResult("canary", False, res.detail or res.status)

    def run(self) -> DoctorReport:
        checks = [self._canary()]
        for check in self._checks:
            try:
                checks.append(check())
            except Exception as exc:
                checks.append(
                    CheckResult(getattr(check, "__name__", "check"), False, str(exc))
                )
        return DoctorReport(ok=all(c.ok for c in checks), checks=checks)


def check_disk(runtime_dir: Path, min_bytes: int = 500_000_000) -> CheckResult:
    free = shutil.disk_usage(runtime_dir).free
    gb = free / 1_000_000_000
    return CheckResult("disk", free >= min_bytes, f"{gb:.1f} GB свободно")


def check_opencode_version(opencode_bin: str | None = None) -> CheckResult:
    bin_ = opencode_bin or shutil.which("opencode") or "opencode"
    try:
        out = subprocess.run(
            [bin_, "--version"], capture_output=True, text=True, timeout=15
        )
        return CheckResult("opencode", out.returncode == 0, out.stdout.strip() or "ok")
    except (OSError, subprocess.SubprocessError) as exc:
        return CheckResult("opencode", False, str(exc))


def check_env(settings: Any) -> CheckResult:
    missing = [
        k
        for k, v in {
            "TELEGRAM_BOT_TOKEN": settings.telegram_bot_token,
            "DEEPGRAM_API_KEY": settings.deepgram_api_key,
        }.items()
        if not v
    ]
    return CheckResult(
        "env", not missing, "все ключи на месте" if not missing else f"нет: {missing}"
    )


def run_cli(session: OpenCodeSession, *, checks: list, alert: Any) -> int:
    report = Doctor(session, checks=checks).run()
    alert(report.to_telegram())
    logger.info("doctor: ok=%s", report.ok)
    return 0 if report.ok else 1


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    from d_brain.config import get_settings
    from d_brain.services.runtime import get_session
    from d_brain.services.watchdog import _telegram_alerter

    settings = get_settings()
    session = get_session(settings)
    checks = [
        lambda: check_disk(settings.runtime_dir),
        lambda: check_opencode_version(settings.opencode_bin),
        lambda: check_env(settings),
    ]
    raise SystemExit(
        run_cli(session, checks=checks, alert=_telegram_alerter(settings))
    )


if __name__ == "__main__":
    main()
