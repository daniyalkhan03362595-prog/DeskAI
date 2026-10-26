"""
Safe Path Sandboxing & Canonicalization Helper using os.path.commonpath.
"""
import os


DISALLOWED_SYSTEM_PREFIXES = (
    "/etc", "/usr", "/var", "/proc", "/sys", "/dev", "/boot", "/root", "/run"
)


def is_disallowed_workspace_root(root_path: str | None) -> bool:
    """Blocks picking critical OS root filesystems as workspace root."""
    if not root_path:
        return True
    try:
        canonical = os.path.realpath(os.path.abspath(root_path))
        if os.name != "nt":
            if canonical == "/":
                return True
            for prefix in DISALLOWED_SYSTEM_PREFIXES:
                if canonical == prefix or canonical.startswith(prefix + "/"):
                    return True
        else:
            drive, tail = os.path.splitdrive(canonical)
            if tail in ("\\", "/", ""):
                return True
            win_dir = os.environ.get("WINDIR", "C:\\Windows")
            try:
                if os.path.commonpath([canonical, win_dir]) == win_dir:
                    return True
            except (ValueError, OSError):
                pass
        return False
    except (ValueError, OSError):
        return True


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
