# Workspace Sandbox Architecture & Sensitive Directory Protection

## Overview

DeskAI restricts all file system access from the desktop bridge to the designated `workspace_root`. To prevent security vulnerabilities where ancestor directories or symbolic links could expose sensitive user credentials or system directories, DeskAI implements multi-layered target sandboxing.

## Architectural Decision: Target-Level Sandboxing

When sandboxing file access, two approaches were considered:
1. **Coarse Root Rejection**: Rejecting any directory at select time that happens to be an ancestor of `$HOME` or sensitive directories.
2. **Target-Level Sandboxing**: Enforcing safe path containment and denying any resolved target that lies inside sensitive user directories or system prefixes across all bridge operations, combined with filtering in `list_dir`.

### Why Target-Level Sandboxing Was Chosen

DeskAI adopts **Target-Level Sandboxing** inside `is_safe_workspace_path` and `DesktopBridgeAPI.list_dir`:
- **Symlink Protection**: If a project inside a user directory contains a symbolic link pointing to `~/.ssh` or `/etc`, coarse root rejection would not prevent access because the workspace root itself is legitimate. Target-level sandboxing resolves canonical paths via `realpath` before checking containment, catching symlink escapes regardless of the root.
- **Ancestor Root Safety**: If an ancestor directory (such as a multi-repo root) is opened as a workspace, any operations targeting sensitive directories (`~/.ssh`, `~/.gnupg`, `~/.aws`, `~/.kube`, `~/.config/gcloud`) or system directories (`/etc`, `/var`, `/usr`, `/private/etc`, `C:\Windows`) are rejected with `Access denied`.
- **Enumeration Prevention**: `list_dir` filters out child entries that fail `is_safe_workspace_path`, ensuring sensitive directories are never enumerated in the file explorer.
- **Cross-Platform Canonicalization**:
  - **POSIX / Linux**: Canonicalizes via `posixpath.realpath` and verifies against system and user sensitive prefixes.
  - **macOS**: Explicitly denies `/private/etc`, `/private/var`, and `/private/tmp`, and performs case-insensitive comparisons on case-insensitive filesystems.
  - **Windows**: Uses `os.path.realpath` (available on Python 3.8+) and `ntpath.normcase` to ensure drive letters, casing, and NTFS reparse points/symlinks are securely evaluated against Windows system directories (`C:\Windows`, `C:\Program Files`, `C:\ProgramData`).
