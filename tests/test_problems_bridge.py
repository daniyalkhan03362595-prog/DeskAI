"""Bridge and security tests for DeskAI diagnostics (TC-PRB-19..25)."""

import os
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from deskai.bridge.api import DesktopBridgeAPI
from deskai.diagnostics.runner import run_subprocess


class TestProblemsBridge(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.workspace_root = os.path.realpath(self.tmpdir.name)

        # Mock WindowManager and window for origin allowance
        self.mock_window = MagicMock()
        self.mock_window.get_current_url.return_value = "http://127.0.0.1:45678/index.html"

        self.mock_server = MagicMock()
        self.mock_server.port = 45678

        self.mock_manager = MagicMock()
        self.mock_manager.window = self.mock_window
        self.mock_manager.server = self.mock_server

        self.api = DesktopBridgeAPI(self.mock_manager)
        self.api.workspace_root = self.workspace_root

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_tc_prb_19_origin_guard(self):
        """TC-PRB-19: Unauthorized origin returns error with 'Unauthorized origin'."""
        self.mock_window.get_current_url.return_value = "http://evil.com/phish"
        res = self.api.run_diagnostics(os.path.join(self.workspace_root, "app.py"))
        self.assertEqual(res["status"], "error")
        self.assertIn("Unauthorized origin", res["message"])

    def test_tc_prb_20_sandbox_security(self):
        """TC-PRB-20: Outside path, traversal, symlink escape, sensitive dirs -> Access denied."""
        # 1. Path outside workspace
        outside = os.path.realpath(tempfile.gettempdir())
        res = self.api.run_diagnostics(os.path.join(outside, "secret.py"))
        self.assertEqual(res["status"], "error")
        self.assertIn("Access denied", res["message"])

        # 2. Traversal path
        traversal = os.path.join(self.workspace_root, "../secret.py")
        res2 = self.api.run_diagnostics(traversal)
        self.assertEqual(res2["status"], "error")
        self.assertIn("Access denied", res2["message"])

        # 3. Symlink pointing outside workspace
        target = os.path.join(outside, "target.py")
        with open(target, "w") as f:
            f.write("a = 1\n")
        symlink_path = os.path.join(self.workspace_root, "link.py")
        try:
            os.symlink(target, symlink_path)
            res3 = self.api.run_diagnostics(symlink_path)
            self.assertEqual(res3["status"], "error")
            self.assertIn("Access denied", res3["message"])
        except OSError:
            pass  # Windows unprivileged symlink fallback

        # 4. ~/.ssh path under root if root was home
        sensitive = os.path.expanduser("~/.ssh/id_rsa")
        res4 = self.api.run_diagnostics(sensitive)
        self.assertEqual(res4["status"], "error")
        self.assertIn("Access denied", res4["message"])

    def test_tc_prb_21_no_code_execution(self):
        """TC-PRB-21: Running diagnostics on a python file never executes code in it or local plugins."""
        marker = os.path.join(self.workspace_root, "executed_marker.txt")
        adversarial_py = os.path.join(self.workspace_root, "adversarial.py")
        with open(adversarial_py, "w", encoding="utf-8") as f:
            f.write(f"import os\nos.system('touch {marker}')\n")

        res = self.api.run_diagnostics(adversarial_py)
        self.assertEqual(res["status"], "ok")
        self.assertFalse(os.path.exists(marker), "Workspace code must never be executed by diagnostics")

    def test_tc_prb_22_timeout_process_kill(self):
        """TC-PRB-22: run_subprocess kills process tree when timeout expired."""
        sleep_script = os.path.join(self.workspace_root, "sleep_helper.py")
        with open(sleep_script, "w", encoding="utf-8") as f:
            f.write("import time\ntime.sleep(30)\n")

        t0 = time.time()
        ret, out, timed_out = run_subprocess(
            [sys.executable, sleep_script],
            cwd=self.workspace_root,
            env=dict(os.environ),
            timeout=1.0,
        )
        elapsed = time.time() - t0
        self.assertTrue(timed_out)
        self.assertIsNone(ret)
        self.assertLess(elapsed, 4.0, "Subprocess timeout and tree kill should complete promptly")

    def test_tc_prb_23_concurrency_cap(self):
        """TC-PRB-23: Concurrency cap of 3 requests; 4th concurrent request returns Busy."""
        # Hold semaphore 3 times
        sem = DesktopBridgeAPI._diag_semaphore
        held = []
        for _ in range(3):
            self.assertTrue(sem.acquire(blocking=False))
            held.append(True)

        try:
            valid_py = os.path.join(self.workspace_root, "test.py")
            with open(valid_py, "w", encoding="utf-8") as f:
                f.write("x = 1\n")

            res = self.api.run_diagnostics(valid_py)
            self.assertEqual(res["status"], "error")
            self.assertEqual(res["message"], "Busy")
        finally:
            for _ in held:
                sem.release()

    def test_tc_prb_24_relative_paths(self):
        """TC-PRB-24: Response file and diagnostics range file never contain absolute workspace path."""
        sub_dir = os.path.join(self.workspace_root, "src", "pkg")
        os.makedirs(sub_dir, exist_ok=True)
        py_file = os.path.join(sub_dir, "broken.py")
        with open(py_file, "w", encoding="utf-8") as f:
            f.write("def f(:\n    pass\n")

        res = self.api.run_diagnostics(py_file)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["file"], "src/pkg/broken.py")
        self.assertNotIn(self.workspace_root, res["file"])
        for d in res["diagnostics"]:
            self.assertEqual(d["file"], "src/pkg/broken.py")
            self.assertNotIn(self.workspace_root, d["file"])

    def test_tc_prb_25_windows_branch_mocking(self):
        """TC-PRB-25: With sys.platform mocked to win32, creationflags uses CREATE_NO_WINDOW and path normalizes."""
        with patch("sys.platform", "win32"):
            with patch("subprocess.Popen") as mock_popen:
                mock_proc = MagicMock()
                mock_proc.communicate.return_value = (b"", b"")
                mock_proc.returncode = 0
                mock_popen.return_value = mock_proc

                ret, out, timed_out = run_subprocess(["dummy"], cwd="C:\\workspace", env={})
                self.assertFalse(timed_out)
                self.assertEqual(ret, 0)
                # Verify creationflags passed
                call_kwargs = mock_popen.call_args[1]
                self.assertIn("creationflags", call_kwargs)


if __name__ == "__main__":
    unittest.main()
