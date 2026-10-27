"""
Unit & Behavioral Tests for Terminal Backend (Phase 1).
Verifies TerminalSession, TerminalManager, spawn gates, environment allowlisting,
signal handling (0x03 / SIGINT), resize notifications, process cleanup, and bridge guards.
"""

import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

import psutil

from deskai.bridge.api import DesktopBridgeAPI
from deskai.server.terminal import (
    ReplayBuffer,
    TerminalManager,
    build_terminal_env,
)


class TestTerminalBackend(unittest.TestCase):
    def setUp(self):
        self.temp_workspace = os.path.realpath(
            os.path.join(os.path.dirname(__file__), "..", "tests", "_test_workspace")
        )
        os.makedirs(self.temp_workspace, exist_ok=True)
        self.manager = TerminalManager()

    def tearDown(self):
        self.manager.close_all()
        if os.path.exists(self.temp_workspace):
            try:
                os.rmdir(self.temp_workspace)
            except OSError:
                pass

    def test_spawn_refused_with_no_workspace_root(self):
        """TerminalManager refuses to spawn when workspace_root is empty or None."""
        with self.assertRaises(ValueError):
            self.manager.create_session(workspace_root="")

        with self.assertRaises(ValueError):
            self.manager.create_session(workspace_root=None)  # type: ignore

    def test_spawn_refused_with_disallowed_root(self):
        """TerminalManager refuses to spawn in sensitive root directories (e.g. /etc, /bin, /)."""
        disallowed = ["/", "/etc", "/bin", "/usr", "/boot"]
        if sys.platform == "win32":
            disallowed = ["C:\\", "C:\\Windows", "C:\\Program Files"]

        for root in disallowed:
            with self.subTest(root=root):
                with self.assertRaises(ValueError):
                    self.manager.create_session(workspace_root=root)

    def test_spawn_refused_with_client_supplied_cwd(self):
        """TerminalManager strictly rejects client-supplied cwd argument."""
        with self.assertRaises(ValueError) as ctx:
            self.manager.create_session(workspace_root=self.temp_workspace, client_cwd="/tmp/arbitrary")
        self.assertIn("Client-supplied cwd is strictly forbidden", str(ctx.exception))

    def test_child_env_contains_none_of_deskai_secrets_or_launch_token(self):
        """Child environment allowlist strips all DESKAI_* keys and internal tokens."""
        with patch.dict(
            os.environ,
            {
                "DESKAI_SECRET_KEY": "super_secret_value",
                "DESKAI_LAUNCH_TOKEN": "token_xyz123",
                "MY_AUTH_TOKEN": "secret_token_abc",
                "USER": "deskai_user",
                "PATH": "/usr/bin:/bin",
            },
        ):
            env = build_terminal_env()
            self.assertEqual(env.get("TERM"), "xterm-256color")
            self.assertEqual(env.get("COLORTERM"), "truecolor")
            self.assertEqual(env.get("USER"), "deskai_user")
            self.assertNotIn("DESKAI_SECRET_KEY", env)
            self.assertNotIn("DESKAI_LAUNCH_TOKEN", env)
            self.assertNotIn("MY_AUTH_TOKEN", env)

            # Ensure no key contains DESKAI_ or TOKEN
            for key in env:
                self.assertFalse(key.startswith("DESKAI_"))
                self.assertNotIn("TOKEN", key.upper())

    @unittest.skipIf(sys.platform == "win32", "POSIX ptyprocess test")
    def test_close_leaves_no_child_process(self):
        """Closing a session leaves no zombie or orphan child processes."""
        session = self.manager.create_session(workspace_root=self.temp_workspace)
        pid = session._process.pid
        self.assertTrue(psutil.pid_exists(pid))

        # Spawn a long sleep command inside the shell
        session.write(b"sleep 300\n")
        time.sleep(0.2)

        # Close session
        session.close()
        time.sleep(0.3)

        self.assertFalse(session.alive)
        self.assertFalse(psutil.pid_exists(pid))

    @unittest.skipIf(sys.platform == "win32", "POSIX ptyprocess test")
    def test_resize_is_observable_inside_pty(self):
        """Resizing session window size is immediately reflected via stty size in kernel."""
        session = self.manager.create_session(workspace_root=self.temp_workspace, cols=80, rows=24)
        time.sleep(0.2)

        # Change dimensions to 132 columns, 42 rows
        session.resize(cols=132, rows=42)
        session.write(b"echo RESIZED:$(stty size)\n")
        time.sleep(0.3)

        output = session.replay_buffer.get_snapshot().decode("utf-8", errors="replace")
        self.assertIn("42 132", output)
        session.close()

    @unittest.skipIf(sys.platform == "win32", "POSIX ptyprocess test")
    def test_writing_0x03_interrupts_running_sleep(self):
        """Writing 0x03 (ETX / Ctrl+C) to PTY delivers SIGINT to foreground process."""
        session = self.manager.create_session(workspace_root=self.temp_workspace)
        time.sleep(0.2)

        marker_file = os.path.join(self.temp_workspace, "should_not_exist.txt")
        if os.path.exists(marker_file):
            os.remove(marker_file)

        # Launch sleep and only touch file if sleep completes without interruption
        session.write(f"sleep 20 && touch '{marker_file}'\n".encode("utf-8"))
        time.sleep(0.2)

        # Send Ctrl+C (0x03)
        session.write(b"\x03")
        time.sleep(0.2)

        # Verify shell is back to prompt by echoing marker
        session.write(b"echo CANCEL_SUCCESSFUL\n")
        time.sleep(0.3)

        output = session.replay_buffer.get_snapshot().decode("utf-8", errors="replace")
        self.assertIn("^C", output)
        self.assertIn("CANCEL_SUCCESSFUL", output)
        self.assertFalse(os.path.exists(marker_file))
        session.close()

    def test_fifth_concurrent_session_is_refused(self):
        """TerminalManager caps concurrent active sessions at 4."""
        sessions = []
        try:
            for _ in range(4):
                s = self.manager.create_session(workspace_root=self.temp_workspace)
                sessions.append(s)

            with self.assertRaises(RuntimeError) as ctx:
                self.manager.create_session(workspace_root=self.temp_workspace)
            self.assertIn("Concurrent session limit reached", str(ctx.exception))
        finally:
            for s in sessions:
                s.close()

    def test_bridge_terminal_open_validation_and_origin_guard(self):
        """DesktopBridgeAPI.terminal_open validates types, bounds, origins, and confirmation."""
        mock_window = MagicMock()
        mock_manager = MagicMock()
        mock_server = MagicMock()
        mock_server.port = 8765
        mock_server.terminal_manager = self.manager
        mock_manager.window = mock_window
        mock_manager.server = mock_server

        api = DesktopBridgeAPI(mock_manager)
        api.workspace_root = self.temp_workspace

        # 1. Unauthorized origin
        mock_window.get_current_url.return_value = "http://evil.com/app"
        res = api.terminal_open(cols=80, rows=24)
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["message"], "Unauthorized origin")

        # Set valid origin
        mock_window.get_current_url.return_value = "http://127.0.0.1:8765/"

        # 2. Rejects bool types (which are int subclasses in Python)
        res_bool_cols = api.terminal_open(cols=True, rows=24)  # type: ignore
        self.assertEqual(res_bool_cols["status"], "error")
        self.assertIn("must be integers", res_bool_cols["message"])

        res_bool_rows = api.terminal_open(cols=80, rows=False)  # type: ignore
        self.assertEqual(res_bool_rows["status"], "error")
        self.assertIn("must be integers", res_bool_rows["message"])

        # 3. Dimension bounds (cols in 10..500, rows in 2..200)
        res_zero = api.terminal_open(cols=0, rows=24)
        self.assertEqual(res_zero["status"], "error")
        self.assertIn("cols must be in 10..500", res_zero["message"])

        res_huge = api.terminal_open(cols=9999, rows=24)
        self.assertEqual(res_huge["status"], "error")
        self.assertIn("cols must be in 10..500", res_huge["message"])

        # 4. Native confirmation prompt
        mock_window.create_confirmation_dialog.return_value = False
        res_declined = api.terminal_open(cols=80, rows=24)
        self.assertEqual(res_declined["status"], "error")
        self.assertIn("declined", res_declined["message"])

        # 5. User accepts confirmation
        mock_window.create_confirmation_dialog.return_value = True
        res_ok = api.terminal_open(cols=80, rows=24)
        self.assertEqual(res_ok["status"], "ok")
        session_id = res_ok["session_id"]
        self.assertIsNotNone(self.manager.get_session(session_id))

        # Subsequent call should NOT re-prompt confirmation
        mock_window.create_confirmation_dialog.reset_mock()
        res_subsequent = api.terminal_open(cols=80, rows=24)
        self.assertEqual(res_subsequent["status"], "ok")
        mock_window.create_confirmation_dialog.assert_not_called()

        # 6. terminal_close
        close_res = api.terminal_close(session_id)
        self.assertTrue(close_res)
        self.assertIsNone(self.manager.get_session(session_id))

    def test_replay_buffer_ring_bounding(self):
        """ReplayBuffer clamps retained bytes to max_bytes in a ring fashion."""
        buf = ReplayBuffer(max_bytes=100)
        buf.append(b"A" * 80)
        self.assertEqual(len(buf), 80)
        buf.append(b"B" * 40)
        self.assertEqual(len(buf), 100)
        snapshot = buf.get_snapshot()
        self.assertEqual(len(snapshot), 100)
        self.assertTrue(snapshot.startswith(b"A" * 60))
        self.assertTrue(snapshot.endswith(b"B" * 40))


if __name__ == "__main__":
    unittest.main()
