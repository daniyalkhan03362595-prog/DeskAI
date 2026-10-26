"""
Safe Path Sandboxing & Canonicalization Helper using os.path.commonpath.
"""
import os


def is_safe_workspace_path(target_path: str, workspace_root: str | None) -> bool:
    """
    Checks if target_path is safely contained within workspace_root.
    Uses realpath + commonpath to prevent prefix collisions (e.g. /workspace-secrets)
    and symlink escapes.
    """
    if not workspace_root:
        return False
    try:
        real_target = os.path.realpath(target_path)
        real_root = os.path.realpath(workspace_root)
        return os.path.commonpath([real_target, real_root]) == real_root
    except (ValueError, OSError):
        return False


def canonicalize_path(target_path: str) -> str:
    """Returns absolute canonicalized path."""
    return os.path.realpath(os.path.abspath(target_path))
