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
    "/private/etc",
    "/private/var",
    "/private/tmp",
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

            # Also block POSIX root / or system prefixes even if passed on Windows
            clean_posix = root_path.replace("\\", "/")
            if clean_posix in ("/", ""):
                return True
            for prefix in DISALLOWED_SYSTEM_PREFIXES:
                if clean_posix == prefix or clean_posix.startswith(prefix + "/"):
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
                rel_win = sensitive_rel.replace("/", "\\")
                sensitive_raw = ntpath.expanduser(rel_win)
                sensitive_path = ntpath.normcase(ntpath.realpath(ntpath.abspath(sensitive_raw)))
                try:
                    if ntpath.commonpath([norm, sensitive_path]) == sensitive_path:
                        return True
                except (ValueError, OSError):
                    pass
            return False

        # POSIX check
        import posixpath

        is_darwin = sys.platform == "darwin"
        clean_root = root_path.replace("\\", "/")
        canonical = posixpath.realpath(posixpath.abspath(clean_root))
        if canonical == "/":
            return True
        canonical_check = canonical.lower() if is_darwin else canonical
        for prefix in DISALLOWED_SYSTEM_PREFIXES:
            prefix_check = prefix.lower() if is_darwin else prefix
            if canonical_check == prefix_check or canonical_check.startswith(prefix_check + "/"):
                return True

        # Block user home root itself ($HOME)
        home_raw = os.environ.get("HOME", os.path.expanduser("~")).replace("\\", "/")
        home_dir = posixpath.realpath(posixpath.abspath(home_raw))
        home_check = home_dir.lower() if is_darwin else home_dir
        if canonical_check == home_check:
            return True

        # Block sensitive subdirectories within home (~/.ssh, ~/.aws, etc.)
        for sensitive_rel in SENSITIVE_HOME_SUBDIRS:
            rel_posix = sensitive_rel.replace("\\", "/").lstrip("~/")
            sensitive_path = posixpath.realpath(posixpath.join(home_dir, rel_posix))
            sensitive_check = sensitive_path.lower() if is_darwin else sensitive_path
            if canonical_check == sensitive_check or canonical_check.startswith(sensitive_check + "/"):
                return True

        return False
    except (ValueError, OSError):
        return True


def is_safe_workspace_path(target_path: str, workspace_root: str | None) -> bool:
    """
    Checks if target_path is safely contained within workspace_root.
    Uses realpath + commonpath to prevent prefix collisions (e.g. /workspace-secrets)
    and symlink escapes.
    Rejects any resolved target inside SENSITIVE_HOME_SUBDIRS, DISALLOWED_SYSTEM_PREFIXES,
    or platform-specific disallowed system directories, even when inside workspace_root.
    Normalizes case on Windows and case-insensitive macOS filesystems.
    """
    if not workspace_root or not target_path:
        return False
    try:
        is_win = (
            os.name == "nt"
            or sys.platform == "win32"
            or (len(workspace_root) >= 2 and workspace_root[1] == ":" and workspace_root[0].isalpha())
        )
        if is_win:
            real_target = ntpath.normcase(ntpath.realpath(ntpath.abspath(target_path)))
            real_root = ntpath.normcase(ntpath.realpath(ntpath.abspath(workspace_root)))
            if ntpath.commonpath([real_target, real_root]) != real_root:
                return False

            # Check SENSITIVE_HOME_SUBDIRS on Windows
            for sensitive_rel in SENSITIVE_HOME_SUBDIRS:
                rel_win = sensitive_rel.replace("/", "\\")
                sensitive_raw = ntpath.expanduser(rel_win)
                sensitive_path = ntpath.normcase(ntpath.realpath(ntpath.abspath(sensitive_raw)))
                try:
                    if ntpath.commonpath([real_target, sensitive_path]) == sensitive_path:
                        return False
                except (ValueError, OSError):
                    pass

            # Check Windows system directories
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
                    norm_win = ntpath.normcase(ntpath.realpath(ntpath.abspath(win_target)))
                    try:
                        if ntpath.commonpath([real_target, norm_win]) == norm_win:
                            return False
                    except (ValueError, OSError):
                        pass

            # Check forward-slash system prefixes if passed on Windows
            clean_target = real_target.replace("\\", "/")
            for prefix in DISALLOWED_SYSTEM_PREFIXES:
                if clean_target == prefix or clean_target.startswith(prefix + "/"):
                    return False

            return True

        is_darwin = sys.platform == "darwin"
        real_target = posixpath.realpath(posixpath.abspath(target_path))
        real_root = posixpath.realpath(posixpath.abspath(workspace_root))

        if is_darwin:
            if posixpath.commonpath([real_target.lower(), real_root.lower()]) != real_root.lower():
                return False
        else:
            if posixpath.commonpath([real_target, real_root]) != real_root:
                return False

        target_check = real_target.lower() if is_darwin else real_target

        # Check DISALLOWED_SYSTEM_PREFIXES
        for prefix in DISALLOWED_SYSTEM_PREFIXES:
            prefix_check = prefix.lower() if is_darwin else prefix
            if target_check == prefix_check or target_check.startswith(prefix_check + "/"):
                return False

        # Check SENSITIVE_HOME_SUBDIRS
        for sensitive_rel in SENSITIVE_HOME_SUBDIRS:
            sensitive_path = posixpath.realpath(posixpath.abspath(os.path.expanduser(sensitive_rel)))
            sensitive_check = sensitive_path.lower() if is_darwin else sensitive_path
            if target_check == sensitive_check or target_check.startswith(sensitive_check + "/"):
                return False

        return True
    except (ValueError, OSError):
        return False


def canonicalize_path(target_path: str) -> str:
    """Returns absolute canonicalized path."""
    if not target_path:
        return ""
    is_win = (
        os.name == "nt"
        or sys.platform == "win32"
        or (len(target_path) >= 2 and target_path[1] == ":" and target_path[0].isalpha())
    )
    if is_win:
        return ntpath.realpath(ntpath.abspath(target_path))
    return os.path.realpath(os.path.abspath(target_path))
