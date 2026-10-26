"""
Safe Path Sandboxing & Canonicalization Helper using os.path.commonpath.
"""

import ntpath
import os
import posixpath
import sys

DISALLOWED_SYSTEM_PREFIXES = (
    "/etc",
    "/usr",
    "/var",
    "/proc",
    "/sys",
    "/dev",
    "/boot",
    "/root",
    "/run",
    "/bin",
    "/sbin",
    "/lib",
    "/lib32",
    "/lib64",
    "/opt",
    "/srv",
    "/snap",
)

SENSITIVE_HOME_SUBDIRS = ("~/.ssh", "~/.gnupg", "~/.aws", "~/.kube", "~/.config/gcloud")


def is_disallowed_workspace_root(root_path: str | None) -> bool:
    """
    Blocks picking critical OS root filesystems, sensitive system directories,
    or the bare user home root itself as the workspace root.
    """
    if not root_path:
        return True
    try:
        is_win = (
            os.name == "nt"
            or sys.platform == "win32"
            or (len(root_path) >= 2 and root_path[1] == ":" and root_path[0].isalpha())
        )

        if is_win:
            norm = ntpath.normcase(ntpath.abspath(root_path))
            drive, tail = ntpath.splitdrive(norm)
            if tail in ("\\", "/", ""):
                return True

            # Block %USERPROFILE% root itself
            userprofile = os.environ.get("USERPROFILE")
            if userprofile and norm == ntpath.normcase(ntpath.abspath(userprofile)):
                return True

            # Block Windows system directories with case-normalization
            disallowed_win = [
                os.environ.get("WINDIR", "C:\\Windows"),
                os.environ.get("SYSTEMROOT", "C:\\Windows"),
                os.environ.get("ProgramFiles", "C:\\Program Files"),
                os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
                os.environ.get("ProgramW6432", "C:\\Program Files"),
                os.environ.get("ProgramData", "C:\\ProgramData"),
                "C:\\Windows",
                "C:\\Program Files",
                "C:\\Program Files (x86)",
                "C:\\ProgramData",
            ]
            for win_target in disallowed_win:
                if win_target:
                    norm_target = ntpath.normcase(ntpath.abspath(win_target))
                    try:
                        if ntpath.commonpath([norm, norm_target]) == norm_target:
                            return True
                    except (ValueError, OSError):
                        pass

            for sensitive_rel in SENSITIVE_HOME_SUBDIRS:
                sensitive_path = ntpath.normcase(ntpath.abspath(os.path.expanduser(sensitive_rel)))
                try:
                    if ntpath.commonpath([norm, sensitive_path]) == sensitive_path:
                        return True
                except (ValueError, OSError):
                    pass
            return False

        # POSIX check
        canonical = os.path.realpath(os.path.abspath(root_path))
        if canonical == "/":
            return True
        for prefix in DISALLOWED_SYSTEM_PREFIXES:
            if canonical == prefix or canonical.startswith(prefix + "/"):
                return True

        # Block user home root itself ($HOME)
        home_dir = os.path.realpath(os.path.expanduser("~"))
        if canonical == home_dir:
            return True

        # Block sensitive subdirectories within home (~/.ssh, ~/.aws, etc.)
        for sensitive_rel in SENSITIVE_HOME_SUBDIRS:
            sensitive_path = os.path.realpath(os.path.expanduser(sensitive_rel))
            if canonical == sensitive_path or canonical.startswith(sensitive_path + "/"):
                return True

        return False
    except (ValueError, OSError):
        return True


def is_safe_workspace_path(target_path: str, workspace_root: str | None) -> bool:
    """
    Checks if target_path is safely contained within workspace_root.
    Uses realpath + commonpath to prevent prefix collisions (e.g. /workspace-secrets)
    and symlink escapes. Normalizes case on Windows.
    """
    if not workspace_root:
        return False
    try:
        is_win = (
            os.name == "nt"
            or sys.platform == "win32"
            or (len(workspace_root) >= 2 and workspace_root[1] == ":" and workspace_root[0].isalpha())
        )
        if is_win:
            real_target = ntpath.normcase(ntpath.abspath(os.path.realpath(target_path)))
            real_root = ntpath.normcase(ntpath.abspath(os.path.realpath(workspace_root)))
            return ntpath.commonpath([real_target, real_root]) == real_root

        real_target = posixpath.realpath(posixpath.abspath(target_path))
        real_root = posixpath.realpath(posixpath.abspath(workspace_root))
        return posixpath.commonpath([real_target, real_root]) == real_root
    except (ValueError, OSError):
        return False


def canonicalize_path(target_path: str) -> str:
    """Returns absolute canonicalized path."""
    return os.path.realpath(os.path.abspath(target_path))
