"""Todoist REST API wrapper.

Direct integration with Todoist API v1 for task management.
Replaces the less reliable mcp-cli approach.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.todoist.com/api/v1"


class TodoistService:
    """Todoist REST API client."""

    def __init__(self, api_key: str, timeout: int = 10) -> None:
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.timeout = timeout

    def fetch_active_tasks(self) -> list[dict[str, Any]]:
        """Fetch all active tasks with cursor-based pagination."""
        tasks: list[dict[str, Any]] = []
        cursor: str | None = None

        with httpx.Client(timeout=self.timeout) as client:
            while True:
                params: dict[str, Any] = {"limit": 100}
                if cursor:
                    params["cursor"] = cursor

                resp = client.get(
                    f"{BASE_URL}/tasks",
                    headers=self.headers,
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()

                tasks.extend(data.get("results", []))
                cursor = data.get("next_cursor")
                if not cursor:
                    break

        return tasks

    def fetch_completed_today(self, today_str: str | None = None) -> int:
        """Count completed tasks for a given date (YYYY-MM-DD)."""
        if today_str is None:
            from datetime import date
            today_str = date.today().isoformat()

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.get(
                f"{BASE_URL}/tasks",
                headers=self.headers,
                params={"filter": f"completed today", "limit": 100},
            )
            if resp.status_code != 200:
                return 0
            data = resp.json()
            return len(data.get("results", []))

    def create_task(
        self,
        content: str,
        due_date: str | None = None,
        priority: int = 1,
        project_id: str | None = None,
    ) -> tuple[bool, str]:
        """Create a new task. Returns (success, error_message)."""
        payload: dict[str, Any] = {"content": content, "priority": priority}
        if due_date:
            payload["due"] = {"date": due_date}
        if project_id:
            payload["project_id"] = project_id

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{BASE_URL}/tasks",
                    headers=self.headers,
                    json=payload,
                )
                if resp.status_code in (200, 201):
                    return True, ""
                return False, resp.text[:200]
        except Exception as e:
            logger.error("Todoist create_task failed: %s", e)
            return False, str(e)[:200]

    def complete_task(self, task_id: str) -> tuple[bool, str]:
        """Mark a task as completed."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{BASE_URL}/tasks/{task_id}/close",
                    headers=self.headers,
                )
                if resp.status_code in (200, 204):
                    return True, ""
                return False, resp.text[:200]
        except Exception as e:
            logger.error("Todoist complete_task failed: %s", e)
            return False, str(e)[:200]

    def delete_task(self, task_id: str) -> tuple[bool, str]:
        """Delete a task."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.delete(
                    f"{BASE_URL}/tasks/{task_id}",
                    headers=self.headers,
                )
                if resp.status_code in (200, 204):
                    return True, ""
                return False, resp.text[:200]
        except Exception as e:
            logger.error("Todoist delete_task failed: %s", e)
            return False, str(e)[:200]

    def reschedule_to_today(self, task_id: str) -> tuple[bool, str]:
        """Reschedule a task to today."""
        from datetime import date
        today = date.today().isoformat()
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{BASE_URL}/tasks/{task_id}/move",
                    headers=self.headers,
                    json={"due": {"date": today}},
                )
                if resp.status_code in (200, 204):
                    return True, ""
                return False, resp.text[:200]
        except Exception as e:
            logger.error("Todoist reschedule failed: %s", e)
            return False, str(e)[:200]

    def update_content(self, task_id: str, content: str) -> tuple[bool, str]:
        """Update task content (reformulate)."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{BASE_URL}/tasks/{task_id}",
                    headers=self.headers,
                    json={"content": content},
                )
                if resp.status_code in (200, 204):
                    return True, ""
                return False, resp.text[:200]
        except Exception as e:
            logger.error("Todoist update_content failed: %s", e)
            return False, str(e)[:200]


def get_todoist() -> TodoistService | None:
    """Get TodoistService if API key is configured, else None."""
    from d_brain.config import get_settings
    settings = get_settings()
    if not settings.todoist_api_key:
        return None
    return TodoistService(settings.todoist_api_key)
