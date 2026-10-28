"""
Unit tests for split bridge modules:
WindowChromeBridge, WorkspaceFSBridge, PortsBridge, GitBridge, TelemetryBridge, TerminalBridge,
and DesktopBridgeAPI facade reflection.
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock

from deskai.bridge.api import DesktopBridgeAPI
from deskai.bridge.git import GitBridge
from deskai.bridge.ports import PortsBridge, _is_safe_external_url, _reachable_host
from deskai.bridge.telemetry import TelemetryBridge
from deskai.bridge.terminal import TerminalBridge
from deskai.bridge.window_chrome import WindowChromeBridge
from deskai.bridge.workspace_fs import WorkspaceFSBridge


class TestBridgeSplitModules(unittest.TestCase):
    def setUp(self):
        self.mock_manager = MagicMock()
        self.mock_window = MagicMock()
        self.mock_manager.window = self.mock_window
        self.mock_manager.server.port = 8000
        self.mock_window.get_current_url.return_value = "http://127.0.0.1:8000/"

    def test_facade_reflection_and_dir(self):
        """DesktopBridgeAPI inherits all methods across modules and exposes them to reflection."""
        api = DesktopBridgeAPI(self.mock_manager)
        expected_methods = [
            "select_folder",
            "select_file",
            "save_file_dialog",
            "set_workspace_root",
            "get_workspace_root",
            "read_file",
            "write_file",
            "create_dir",
            "rename_path",
            "delete_path",
            "list_dir",
            "open_external_url",
            "open_port",
            "probe_port",
            "get_listening_ports",
            "get_git_branch",
            "get_system_telemetry",
            "terminal_open",
            "terminal_close",
            "drag_window",
            "resize_window",
            "resize_window_absolute",
            "window_control",
            "set_dirty_status",
            "_is_origin_allowed",
        ]
        api_dir = dir(api)
        for method in expected_methods:
            self.assertIn(method, api_dir, f"Missing {method} on DesktopBridgeAPI")
            self.assertTrue(callable(getattr(api, method)), f"{method} is not callable")

    def test_window_chrome_bridge_isolated(self):
        """WindowChromeBridge directly handles resize_window_absolute and dirty status."""
        chrome = WindowChromeBridge(self.mock_manager)
        # Invalid origin
        self.mock_window.get_current_url.return_value = "http://evil.com/"
        self.assertFalse(chrome.window_control("minimize"))
        self.assertEqual(chrome.resize_window_absolute(800, 600)["status"], "error")

        # Valid origin
        self.mock_window.get_current_url.return_value = "http://127.0.0.1:8000/"
        res = chrome.resize_window_absolute(900, 700)
        self.assertEqual(res["status"], "ok")
        self.mock_window.resize.assert_called_with(900, 700)

        # Invalid bounds
        self.assertEqual(chrome.resize_window_absolute(50, 50)["status"], "error")

        # Dirty status
        chrome.set_dirty_status(True)
        self.assertTrue(self.mock_manager.lifecycle.has_dirty_tabs)

    def test_workspace_fs_bridge_isolated(self):
        """WorkspaceFSBridge handles file read/write within workspace."""
        with tempfile.TemporaryDirectory() as td:
            ws_root = os.path.realpath(td)
            fs = WorkspaceFSBridge(self.mock_manager)
            fs.workspace_root = ws_root

            file_path = os.path.join(ws_root, "test.txt")
            w_res = fs.write_file(file_path, "Hello FS")
            self.assertEqual(w_res["status"], "ok")

            r_res = fs.read_file(file_path)
            self.assertEqual(r_res["status"], "ok")
            self.assertEqual(r_res["content"], "Hello FS")

    def test_ports_bridge_isolated(self):
        """PortsBridge handles URL safety and reachable hosts."""
        ports = PortsBridge(self.mock_manager)
        self.assertTrue(_is_safe_external_url("https://github.com"))
        self.assertFalse(_is_safe_external_url("javascript:alert(1)"))
        self.assertFalse(_is_safe_external_url("file:///etc/passwd"))

        # Reachable host
        host, exposure = _reachable_host("127.0.0.1")
        self.assertEqual(host, "127.0.0.1")
        self.assertEqual(exposure, "loopback")

        # Disallowed origin blocks ports
        self.mock_window.get_current_url.return_value = "http://attacker.com"
        self.assertFalse(ports.open_port(3000))
        self.assertFalse(ports.probe_port(3000))

    def test_git_bridge_isolated(self):
        """GitBridge returns None when path is not a git repo."""
        with tempfile.TemporaryDirectory() as td:
            git_b = GitBridge(self.mock_manager)
            git_b.workspace_root = td
            res = git_b.get_git_branch(td)
            self.assertEqual(res["status"], "ok")
            self.assertIsNone(res["branch"])

    def test_telemetry_bridge_isolated(self):
        """TelemetryBridge returns system telemetry metrics."""
        telem = TelemetryBridge(self.mock_manager)
        res = telem.get_system_telemetry()
        self.assertEqual(res["status"], "ok")
        self.assertIn("status", res["telemetry"])
        self.assertIn("platform", res["telemetry"])

    def test_terminal_bridge_isolated(self):
        """TerminalBridge checks workspace root and dimensions."""
        term = TerminalBridge(self.mock_manager)
        # Root not set
        res = term.terminal_open(cols=80, rows=24)
        self.assertEqual(res["status"], "error")
        self.assertIn("Workspace root not set", res["message"])

        # Invalid rows
        term.workspace_root = "/tmp"
        res2 = term.terminal_open(cols=1, rows=24)
        self.assertEqual(res2["status"], "error")


if __name__ == "__main__":
    unittest.main()
