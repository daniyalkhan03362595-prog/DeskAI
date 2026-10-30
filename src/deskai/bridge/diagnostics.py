from __future__ import annotations
import concurrent.futures
import logging
import os
import threading
import time
from deskai.bridge.base import BaseBridgeModule
from deskai.diagnostics.cache import DiagnosticsCache
from deskai.diagnostics.runner import run_checks
from deskai.utils.path import canonicalize_path, is_safe_workspace_path

logger = logging.getLogger(__name__)

EXCLUDED_WORKSPACE_SCAN_DIRS = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"})


class DiagnosticsBridge(BaseBridgeModule):
    """Bridge module providing sandboxed workspace diagnostics with MTime caching and parallelism."""

    _diag_semaphore = threading.BoundedSemaphore(3)  # S7: max 3 concurrent checks
    _diag_cache = DiagnosticsCache()
    _executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=min(32, (os.cpu_count() or 4) + 4), thread_name_prefix="DeskAIDiagWorker"
    )

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
            canonical_p = canonicalize_path(target_path)
            res = run_checks(canonical_p, self.workspace_root, request_id=request_id)
            if res.get("status") == "ok":
                diags = res.get("diagnostics", [])
                self._diag_cache.put(canonical_p, diags)
                err_cnt = sum(1 for d in diags if d.get("severity") == "error")
                warn_cnt = sum(1 for d in diags if d.get("severity") == "warning")
                fname = os.path.basename(target_path)
                if err_cnt > 0:
                    logger.error("Diagnostics [%s]: %d syntax error(s) found", fname, err_cnt)
                elif warn_cnt > 0:
                    logger.warning("Diagnostics [%s]: %d warning(s) found", fname, warn_cnt)
                else:
                    logger.info("Diagnostics [%s]: Clean, 0 errors/warnings", fname)
            return res
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

    def run_workspace_diagnostics(self, request_id: str = "", limit: int = 10000) -> dict:
        """Scan workspace files for diagnostics with stat-based caching and parallel execution."""
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
        root_dir = self.workspace_root
        if not self._diag_semaphore.acquire(blocking=False):
            return {
                "status": "error",
                "message": "Busy",
                "request_id": request_id,
                "files": {},
            }
        try:
            t0 = time.perf_counter()
            results: dict[str, list[dict]] = {}
            count = 0
            cache_hits = 0
            cache_misses = 0
            missed_files: list[tuple[str, str]] = []

            # 1. Fast stat-scan pass (1 microsecond per unchanged file)
            for root, dirs, files in os.walk(self.workspace_root, followlinks=False):
                dirs[:] = [d for d in dirs if d not in EXCLUDED_WORKSPACE_SCAN_DIRS]
                for file_name in files:
                    full_p = os.path.join(root, file_name)
                    if not self._is_safe_path(full_p):
                        continue

                    canonical_p = canonicalize_path(full_p)
                    rel_p = os.path.relpath(canonical_p, self.workspace_root).replace(os.sep, "/")

                    cached = self._diag_cache.get_if_valid(canonical_p)
                    if cached is not None:
                        cache_hits += 1
                        if cached:
                            results[rel_p] = cached
                    else:
                        cache_misses += 1
                        missed_files.append((canonical_p, rel_p))

                    count += 1
                    if count >= limit:
                        break
                if count >= limit:
                    break

            # 2. Parallel cold-parse pass for modified or new files
            if missed_files:

                def _worker(item: tuple[str, str]) -> tuple[str, str, dict]:
                    path, rel_file = item
                    r = run_checks(path, root_dir, request_id=request_id)
                    return path, rel_file, r

                futures = [self._executor.submit(_worker, item) for item in missed_files]
                for f in concurrent.futures.as_completed(futures):
                    path, rel_file, r = f.result()
                    diags = r.get("diagnostics", [])
                    self._diag_cache.put(path, diags)
                    if r.get("status") == "ok" and diags:
                        results[rel_file] = diags

            duration_ms = (time.perf_counter() - t0) * 1000.0
            return {
                "status": "ok",
                "request_id": request_id,
                "files": results,
                "scan_duration_ms": round(duration_ms, 2),
                "cache_hits": cache_hits,
                "cache_misses": cache_misses,
            }
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
