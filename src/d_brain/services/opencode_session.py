"""Drive the AI engine via MiMo API (OpenAI-compatible endpoint).

Uses MiMo's API at https://lizh.ai/v1 which provides mimo models
through an OpenAI-compatible chat completions endpoint.

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

MIMO_API_KEY = "sk-8IYzMTzSIFjY8OpYqUOg0QpFqKBhNME7rfLAm85xN5zQLULQ"
MIMO_BASE_URL = "https://lizh.ai/v1"


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
    """Drives AI via MiMo OpenAI-compatible API calls."""

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
        self.model = model or "mimo-v2.5"
        self._timeout = timeout

    def ask(
        self,
        prompt: str,
        *,
        timeout: float | None = None,
        request_id: str | None = None,
        wrap: bool = True,
    ) -> AskResult:
        """Send a prompt via MiMo OpenAI-compatible API and return the reply."""
        model = self.model.split("/", 1)[-1] if "/" in self.model else self.model

        logger.info("mimo ask (model=%s) len=%d", model, len(prompt))

        payload = json.dumps({
            "model": model,
            "max_tokens": 8192,
            "messages": [{"role": "user", "content": prompt}],
        })

        try:
            proc = subprocess.run(
                [
                    "curl", "-s", "-m", str(int((timeout or self._timeout) * 0.9)),
                    f"{MIMO_BASE_URL}/chat/completions",
                    "-H", "Authorization: Bearer " + MIMO_API_KEY,
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
            logger.exception("mimo api call failed")
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
        """Parse MiMo OpenAI-compatible JSON response."""
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            return AskResult("error", detail=f"invalid JSON: {e}")

        if "error" in data:
            return AskResult("error", detail=str(data["error"]))

        # OpenAI format: choices[0].message.content
        choices = data.get("choices", [])
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message", {})
            content = message.get("content", "")
            # Some reasoning models put answer in reasoning_content when content is empty
            if not content:
                content = message.get("reasoning_content", "")
            if content:
                return AskResult("ok", reply=content)

        # Fallback: try Anthropic format (content array)
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
                    f"{MIMO_BASE_URL}/models",
                    "-H", "Authorization: Bearer " + MIMO_API_KEY,
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


