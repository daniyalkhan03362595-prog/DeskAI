"""
Git Repository Information Bridge Module.
Resolves active branch name, detached HEAD states, git worktrees, and submodule gitdirs safely.
"""

import logging
import os
from pathlib import Path

from deskai.bridge.base import BaseBridgeModule
from deskai.utils.path import is_safe_workspace_path

logger = logging.getLogger(__name__)


class GitBridge(BaseBridgeModule):
    """Bridge methods for git repository status."""

    def _is_safe_path(self, target_path: str) -> bool:
        return is_safe_workspace_path(target_path, self.workspace_root)

    def get_git_branch(self, target_path: str | None = None) -> dict:
        """Returns the active git branch name if the path is a git repository within workspace root."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin", "branch": None}
        if not target_path:
            return {"status": "ok", "branch": None}
        if not self._is_safe_path(target_path):
            return {"status": "error", "message": "Access denied: Path outside workspace", "branch": None}
        try:
            p = Path(target_path).resolve()
            git_path = p / ".git"
            if not git_path.exists():
                return {"status": "ok", "branch": None}

            head_file = None
            if git_path.is_dir():
                head_file = git_path / "HEAD"
            elif git_path.is_file():
                # Git worktree / submodule reference pointer
                text = git_path.read_text(encoding="utf-8").strip()
                if text.startswith("gitdir:"):
                    raw_gitdir = text.split("gitdir:", 1)[1].strip()
                    gitdir = Path(raw_gitdir)
                    if not gitdir.is_absolute():
                        gitdir = (p / gitdir).resolve()
                    else:
                        gitdir = gitdir.resolve()

                    str_gitdir = str(gitdir)
                    repo_worktrees = str((p / ".git" / "worktrees").resolve())
                    repo_modules = str((p / ".git" / "modules").resolve())

                    is_inside_ws = self._is_safe_path(str_gitdir)
                    is_inside_repo_git = False
                    try:
                        if os.path.commonpath([str_gitdir, repo_worktrees]) == repo_worktrees:
                            is_inside_repo_git = True
                        elif os.path.commonpath([str_gitdir, repo_modules]) == repo_modules:
                            is_inside_repo_git = True
                    except (ValueError, OSError):
                        is_inside_repo_git = False

                    if not (is_inside_ws or is_inside_repo_git):
                        return {
                            "status": "error",
                            "message": "Access denied: gitdir outside allowed path",
                            "branch": None,
                        }

                    head_file = gitdir / "HEAD"

            if head_file and head_file.exists():
                head_content = head_file.read_text(encoding="utf-8").strip()
                if head_content.startswith("ref: refs/heads/"):
                    branch = head_content.replace("ref: refs/heads/", "").strip()
                    logger.info("Git active branch: %s", branch)
                    return {"status": "ok", "branch": branch}
                elif head_content:
                    # Detached HEAD (SHA-1 prefix)
                    short_sha = head_content[:7]
                    logger.info("Git detached HEAD: %s", short_sha)
                    return {"status": "ok", "branch": short_sha}
        except Exception as e:
            logger.debug("Failed to read git branch: %s", e)
        return {"status": "ok", "branch": None}
