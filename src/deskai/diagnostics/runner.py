from __future__ import annotations
import logging
import os
import signal
import subprocess
import sys
from typing import Any
from .json_syntax import check_json
from .models import Diagnostic
from .python_syntax import check_python
from .toml_syntax import check_toml
from .html_syntax import check_html
from .xml_syntax import check_xml

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 1_048_576  # 1 MB
MAX_DIAGNOSTICS_PER_FILE = 500
CHECK_TIMEOUT_S = 10.0
MAX_OUTPUT_BYTES = 1_048_576

CHECKERS_BY_EXT = {
    ".py": ["python"],
    ".pyw": ["python"],
    ".json": ["json"],
    ".toml": ["toml"],
    ".html": ["html"],
    ".htm": ["html"],
    ".xml": ["xml"],
    ".svg": ["xml"],
}


def _kill_tree(proc: subprocess.Popen) -> None:
    """Terminate the process and any children safely across platforms."""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            try:
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
    except Exception:
        pass
    finally:
        try:
            proc.kill()
        except Exception:
            pass


def run_subprocess(
    argv: list[str], cwd: str, env: dict[str, str], timeout: float = CHECK_TIMEOUT_S
) -> tuple[int | None, str, bool]:
    """Run an isolated subprocess with shell=False, stdin=DEVNULL, output capped, process-tree kill on timeout."""
    kwargs: dict[str, Any] = dict(
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=cwd,
        env=env,
    )
    if sys.platform == "win32":
        creationflags = 0
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags |= subprocess.CREATE_NO_WINDOW
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP
        kwargs["creationflags"] = creationflags
    else:
        kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(argv, **kwargs)
    except Exception as e:
        logger.warning("Failed to start subprocess %s: %s", argv, e)
        return None, "", False

    try:
        out, _ = proc.communicate(timeout=timeout)
        return proc.returncode, out[:MAX_OUTPUT_BYTES].decode("utf-8", "replace"), False
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            proc.communicate(timeout=2.0)
        except Exception:
            pass
        return None, "", True


def run_checks(abs_path: str, root: str, request_id: str = "") -> dict:
    """Run enabled checkers against a workspace file and return a DiagnosticResult dictionary."""
    try:
        rel = os.path.relpath(abs_path, root).replace(os.sep, "/")
    except Exception:
        rel = os.path.basename(abs_path)

    if not os.path.isfile(abs_path):
        return {
            "status": "error",
            "message": "File not found",
            "request_id": request_id,
            "file": rel,
            "diagnostics": [],
            "truncated": False,
            "warnings": [],
        }

    try:
        size = os.path.getsize(abs_path)
    except OSError:
        return {
            "status": "error",
            "message": "Unable to read file size",
            "request_id": request_id,
            "file": rel,
            "diagnostics": [],
            "truncated": False,
            "warnings": [],
        }

    if size > MAX_FILE_BYTES:
        return {
            "status": "ok",
            "request_id": request_id,
            "file": rel,
            "diagnostics": [],
            "truncated": False,
            "warnings": ["file_too_large"],
        }

    ext = os.path.splitext(abs_path)[1].lower()
    checker_names = CHECKERS_BY_EXT.get(ext)
    if not checker_names:
        return {
            "status": "ok",
            "request_id": request_id,
            "file": rel,
            "diagnostics": [],
            "truncated": False,
            "warnings": ["no_checker"],
        }

    try:
        with open(abs_path, "rb") as f:
            raw = f.read(MAX_FILE_BYTES + 1)
    except OSError as e:
        return {
            "status": "error",
            "message": f"Read error: {e}",
            "request_id": request_id,
            "file": rel,
            "diagnostics": [],
            "truncated": False,
            "warnings": [],
        }

    if b"\x00" in raw[:8192]:
        return {
            "status": "ok",
            "request_id": request_id,
            "file": rel,
            "diagnostics": [],
            "truncated": False,
            "warnings": ["binary_file"],
        }

    source = raw.decode("utf-8", "replace")
    all_diags: list[Diagnostic] = []
    warnings: list[str] = []

    for name in checker_names:
        if name == "python":
            all_diags.extend(check_python(source, rel))
        elif name == "json":
            all_diags.extend(check_json(source, rel))
        elif name == "toml":
            all_diags.extend(check_toml(source, rel))
        elif name == "html":
            all_diags.extend(check_html(source, rel))
        elif name == "xml":
            all_diags.extend(check_xml(source, rel))

    # Deduplicate by id, keeping the first occurrence
    seen_ids: set[str] = set()
    deduped: list[Diagnostic] = []
    for d in all_diags:
        if d.id not in seen_ids:
            seen_ids.add(d.id)
            deduped.append(d)

    # Sort by start_line, start_col, source
    deduped.sort(key=lambda d: (d.start_line, d.start_col, d.source))

    truncated = False
    if len(deduped) > MAX_DIAGNOSTICS_PER_FILE:
        deduped = deduped[:MAX_DIAGNOSTICS_PER_FILE]
        truncated = True

    return {
        "status": "ok",
        "request_id": request_id,
        "file": rel,
        "diagnostics": [d.to_dict() for d in deduped],
        "truncated": truncated,
        "warnings": warnings,
    }
