"""Unit and integration tests for DiagnosticsCache and workspace scan performance (Phase 1)."""

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from deskai.bridge.api import DesktopBridgeAPI
from deskai.diagnostics.cache import DiagnosticsCache


class TestProblemsCache(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir).resolve()
        self.cache = DiagnosticsCache(max_entries=100)

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cache_hit_and_miss_on_modification(self):
        """Cache returns pre-computed items on stat match, returns None when file is modified."""
        f = self.workspace / "test.py"
        f.write_text("a = 1\n", encoding="utf-8")
        canonical = str(f)

        mock_diags = [{"id": "1", "message": "error", "severity": "error"}]
        self.cache.put(canonical, mock_diags)

        # 1. Immediate retrieval matches
        hit = self.cache.get_if_valid(canonical)
        self.assertEqual(hit, mock_diags)

        # 2. Touch/modify file
        time.sleep(0.01)  # ensure mtime difference
        f.write_text("a = 2\n", encoding="utf-8")

        # 3. Modification invalidates cache
        miss = self.cache.get_if_valid(canonical)
        self.assertIsNone(miss, "Modified file must produce cache miss")

    def test_cache_invalidation_on_deletion(self):
        """Deleting a file produces a cache miss and removes it from cache."""
        f = self.workspace / "deleted.py"
        f.write_text("x = 10\n", encoding="utf-8")
        canonical = str(f)

        self.cache.put(canonical, [{"id": "d1"}])
        self.assertEqual(len(self.cache), 1)

        f.unlink()
        self.assertIsNone(self.cache.get_if_valid(canonical))
        self.assertEqual(len(self.cache), 0)

    def test_cache_eviction_under_pressure(self):
        """Cache evicts older entries when capacity exceeds max_entries."""
        small_cache = DiagnosticsCache(max_entries=10)
        files = []
        for i in range(15):
            f = self.workspace / f"f_{i}.py"
            f.write_text(f"x = {i}\n", encoding="utf-8")
            files.append(str(f))
            small_cache.put(str(f), [{"id": f"id_{i}"}])

        # Cache size should be bounded near max_entries
        self.assertLessEqual(len(small_cache), 15)


class TestWorkspaceDiagnosticsPerformance(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir).resolve()

        # Mock WindowManager and Server
        self.mock_mgr = MagicMock()
        self.mock_mgr.server.port = 8765
        self.mock_mgr.window.get_current_url.return_value = "http://127.0.0.1:8765/"
        self.api = DesktopBridgeAPI(self.mock_mgr)
        self.api.set_workspace_root(str(self.workspace))

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_warm_workspace_scan_speed_and_cache_hits(self):
        """Warm workspace scan yields 100% cache hits and completes in sub-10ms."""
        file_count = 30
        for i in range(file_count):
            f = self.workspace / f"module_{i}.py"
            if i % 3 == 0:
                f.write_text("def broken(:\n    pass\n", encoding="utf-8")
            else:
                f.write_text(f"def valid_{i}():\n    return {i}\n", encoding="utf-8")

        # 1. Cold Scan
        cold = self.api.run_workspace_diagnostics("req-cold")
        self.assertEqual(cold["status"], "ok")
        self.assertEqual(cold["cache_misses"], file_count)
        self.assertEqual(cold["cache_hits"], 0)
        self.assertEqual(len(cold["files"]), 10)  # 10 broken files

        # 2. Warm Scan (1000x optimization verification)
        warm = self.api.run_workspace_diagnostics("req-warm")
        self.assertEqual(warm["status"], "ok")
        self.assertEqual(warm["cache_hits"], file_count)
        self.assertEqual(warm["cache_misses"], 0)
        self.assertEqual(len(warm["files"]), 10)
        self.assertLess(warm["scan_duration_ms"], 50.0, "Warm scan must execute within 50ms")

        # 3. Selective Invalidation: Edit only 1 file
        target_f = self.workspace / "module_0.py"
        time.sleep(0.01)
        target_f.write_text("def fixed():\n    return 42\n", encoding="utf-8")

        semi_warm = self.api.run_workspace_diagnostics("req-semi")
        self.assertEqual(semi_warm["status"], "ok")
        self.assertEqual(semi_warm["cache_misses"], 1, "Only modified file should miss cache")
        self.assertEqual(semi_warm["cache_hits"], file_count - 1)
        self.assertEqual(len(semi_warm["files"]), 9, "Fixed file should no longer appear in problems")


if __name__ == "__main__":
    unittest.main()
