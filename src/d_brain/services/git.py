"""Git automation service for vault.

Extended with get_head_sha() and revert_commit() for the undo system.
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class VaultGit:
    """Service for git operations on vault."""

    def __init__(self, vault_path: Path) -> None:
        self.vault_path = Path(vault_path)

    def _run_git(self, *args: str) -> subprocess.CompletedProcess[str]:
        """Run git command in vault directory."""
        return subprocess.run(
            ["git", *args],
            cwd=self.vault_path,
            capture_output=True,
            text=True,
            check=False,
        )

    def get_status(self) -> str:
        """Get git status."""
        result = self._run_git("status", "--porcelain")
        return result.stdout

    def has_changes(self) -> bool:
        """Check if there are uncommitted changes."""
        return bool(self.get_status().strip())

    def get_head_sha(self) -> str:
        """Return current HEAD commit SHA."""
        result = self._run_git("rev-parse", "HEAD")
        return result.stdout.strip() if result.returncode == 0 else ""

    def commit_changes(self, message: str) -> bool:
        """Stage all changes and commit."""
        if not self.has_changes():
            logger.info("No changes to commit")
            return False

        add_result = self._run_git("add", "-A")
        if add_result.returncode != 0:
            logger.error("Git add failed: %s", add_result.stderr)
            return False

        commit_result = self._run_git("commit", "-m", message)
        if commit_result.returncode != 0:
            logger.error("Git commit failed: %s", commit_result.stderr)
            return False

        logger.info("Committed: %s", message)
        return True

    def push(self) -> tuple[bool, str]:
        """Push to remote. Returns (success, error_message)."""
        result = self._run_git("push")
        if result.returncode != 0:
            error = result.stderr.strip()
            logger.error("Git push failed: %s", error)
            return False, error

        logger.info("Pushed to remote")
        return True, ""

    def commit_and_push(self, message: str) -> bool:
        """Commit all changes and push."""
        if self.commit_changes(message):
            success, _ = self.push()
            return success
        return True  # No changes is not an error

    def revert_commit(self, sha: str) -> tuple[bool, str]:
        """Revert a specific commit and push. Returns (success, error)."""
        # Revert
        result = self._run_git("revert", "--no-edit", sha)
        if result.returncode != 0:
            error = result.stderr.strip()
            logger.error("Git revert failed: %s", error)
            return False, error

        # Push the revert
        success, push_error = self.push()
        if not success:
            return False, f"Revert committed but push failed: {push_error}"

        logger.info("Reverted commit %s", sha[:8])
        return True, ""
