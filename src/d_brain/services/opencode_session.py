"""Drive the AI engine via direct Z.AI Anthropic-compatible API calls.

Uses Z.AI's API at https://api.z.ai/api/anthropic which provides GLM models
through an Anthropic-compatible chat completions endpoint.

The interface mirrors AskResult so the rest of the app
works without changes.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 600

ZAI_API_KEY = "ad48e79723774b20a1456939b208b0de.9MB26qdS3G5Ipu3H"
ZAI_BASE_URL = "https://api.z.ai/api/anthropic"


class AskResult:
    """Outcome of a single ask() round (mirrors ClaudeSession.AskResult)."""

    def __init__(self, status: str, reply: str | None = None, detail: str | None = None) -> None:
        self.status = status
        self.reply = reply
        self.detail = detail

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class OpenCodeSession:
    """Drives AI via direct Z.AI Anthropic-compatible API calls."""

    def __init__(
        self,
        work_dir: Path,
        *,
        model: str = "",
        opencode_bin: str = "",
        mcp_config: Path | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.work_dir = Path(work_dir)
        self.model = model or "claude-sonnet-4-20250514"
        self._timeout = timeout

    def ask(
        self,
        prompt: str,
        *,
        timeout: float | None = None,
        request_id: str | None = None,
        wrap: bool = True,
    ) -> AskResult:
        """Send a prompt via Z.AI Anthropic-compatible API and return the reply."""
        model = self.model.split("/", 1)[-1] if "/" in self.model else self.model

        logger.info("zai ask (model=%s) len=%d", model, len(prompt))

        payload = json.dumps({
            "model": model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        })

        try:
            proc = subprocess.run(
                [
                    "curl", "-s", "-m", str(int((timeout or self._timeout) * 0.9)),
                    f"{ZAI_BASE_URL}/v1/messages",
                    "-H", "x-api-key: " + ZAI_API_KEY,
                    "-H", "anthropic-version: 2023-06-01",
                    "-H", "content-type: application/json",
                    "-d", payload,
                ],
                capture_output=True,
                text=True,
                timeout=timeout or self._timeout,
            )
        except subprocess.TimeoutExpired:
            return AskResult("timeout", detail=f"no reply in {timeout or self._timeout}s")
        except Exception as exc:
            logger.exception("zai api call failed")
            return AskResult("error", detail=str(exc))

        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            logger.error("curl exit %s: %s", proc.returncode, stderr)
            return AskResult("error", detail=stderr or f"exit code {proc.returncode}")

        stdout = (proc.stdout or "").strip()
        if not stdout:
            return AskResult("error", detail="empty reply")

        return self._parse_response(stdout)

    def _parse_response(self, text: str) -> AskResult:
        """Parse Z.AI Anthropic-compatible JSON response."""
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            return AskResult("error", detail=f"invalid JSON: {e}")

        if "error" in data:
            return AskResult("error", detail=str(data["error"]))

        content = data.get("content", [])
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))

        reply = "\n".join(parts) if parts else text
        return AskResult("ok", reply=reply)

    def send_control(self, text: str) -> None:
        pass

    def is_turn_active(self) -> bool:
        return False

    def is_steerable_turn(self) -> bool:
        return False

    def steer(self, text: str) -> None:
        pass

    def interrupt(self) -> None:
        pass

    def clear(self) -> None:
        pass

    def is_healthy(self) -> bool:
        try:
            proc = subprocess.run(
                [
                    "curl", "-s", "-m", "5",
                    f"{ZAI_BASE_URL}/v1/models",
                    "-H", "x-api-key: " + ZAI_API_KEY,
                ],
                capture_output=True, text=True, timeout=10,
            )
            return proc.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def current_state(self) -> str:
        return "ready"

    def is_working(self) -> bool:
        return False

    def force_recover(self) -> bool:
        return True

    def kill(self) -> None:
        pass

    def ensure_session(self) -> None:
        pass
