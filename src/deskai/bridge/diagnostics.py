from __future__ import annotations
import logging
import os
import threading
from deskai.bridge.base import BaseBridgeModule
from deskai.diagnostics.runner import run_checks
from deskai.utils.path import canonicalize_path, is_safe_workspace_path

logger = logging.getLogger(__name__)

EXCLUDED_WORKSPACE_SCAN_DIRS = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"})


class DiagnosticsBridge(BaseBridgeModule):
    """Bridge module providing sandboxed workspace diagnostics."""

    _diag_semaphore = threading.BoundedSemaphore(3)  # S7: max 3 concurrent checks

    def _is_safe_path(self, target_path: str) -> bool:
        """Verify target path is within the active workspace sandbox."""
        return is_safe_workspace_path(target_path, self.workspace_root)

    def run_diagnostics(self, target_path: str, request_id: str = "") -> dict:
        """Run diagnostics on a specific workspace file."""
        if not self._is_origin_allowed():
            return {
                "status": "error",
                "message": "Unauthorized origin",
                "request_id": request_id,
                "diagnostics": [],
            }
        if not self.workspace_root or not self._is_safe_path(target_path):
            return {
                "status": "error",
                "message": "Access denied: Path outside workspace",
                "request_id": request_id,
                "diagnostics": [],
            }
        if not self._diag_semaphore.acquire(blocking=False):
            return {
                "status": "error",
                "message": "Busy",
                "request_id": request_id,
                "diagnostics": [],
            }
        try:
            return run_checks(canonicalize_path(target_path), self.workspace_root, request_id=request_id)
        except Exception:
            logger.exception("diagnostics failed for %s", target_path)
            return {
                "status": "error",
                "message": "Diagnostics failed",
                "request_id": request_id,
                "diagnostics": [],
            }
        finally:
            self._diag_semaphore.release()

    def run_workspace_diagnostics(self, request_id: str = "", limit: int = 200) -> dict:
        """Scan workspace files for diagnostics up to the specified limit."""
        if not self._is_origin_allowed():
            return {
                "status": "error",
                "message": "Unauthorized origin",
                "request_id": request_id,
                "files": {},
            }
        if not self.workspace_root:
            return {
                "status": "error",
                "message": "No workspace open",
                "request_id": request_id,
                "files": {},
            }
        if not self._diag_semaphore.acquire(blocking=False):
            return {
                "status": "error",
                "message": "Busy",
                "request_id": request_id,
                "files": {},
            }
        try:
            results: dict[str, list[dict]] = {}
            count = 0
            for root, dirs, files in os.walk(self.workspace_root, followlinks=False):
                dirs[:] = [d for d in dirs if d not in EXCLUDED_WORKSPACE_SCAN_DIRS]
                for file_name in files:
                    full_p = os.path.join(root, file_name)
                    if not self._is_safe_path(full_p):
                        continue
                    res = run_checks(canonicalize_path(full_p), self.workspace_root, request_id=request_id)
                    if res.get("status") == "ok" and res.get("diagnostics"):
                        results[res["file"]] = res["diagnostics"]
                    count += 1
                    if count >= limit:
                        break
                if count >= limit:
                    break
            return {"status": "ok", "request_id": request_id, "files": results}
        except Exception:
            logger.exception("workspace diagnostics failed")
            return {
                "status": "error",
                "message": "Diagnostics failed",
                "request_id": request_id,
                "files": {},
            }
        finally:
            self._diag_semaphore.release()
