import json
import re
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from deskai.bridge.api import DesktopBridgeAPI


class TestFrontendStateAndTelemetry(unittest.TestCase):
    def setUp(self):
        self.mock_manager = MagicMock()
        self.mock_window = MagicMock()
        self.mock_manager.window = self.mock_window
        self.mock_manager.server.port = 8000
        self.mock_window.get_current_url.return_value = "http://127.0.0.1:8000/"

        self.api = DesktopBridgeAPI(self.mock_manager)

    def test_initial_state_has_no_hardcoded_hardware_specs(self):
        """state.js initialState must not contain hardcoded Apple M3 or NVIDIA specs, but '--' defaults."""
        state_js_path = Path("src/deskai/static/js/state.js")
        self.assertTrue(state_js_path.exists())
        content = state_js_path.read_text(encoding="utf-8")

        # Must not contain hardcoded hardware strings
        self.assertNotIn("Apple M3", content)
        self.assertNotIn("NVIDIA RTX", content)
        self.assertNotIn("vramUsedMB: 4710", content)
        self.assertNotIn("cpuUsagePct: 14.8", content)

        # Must have default placeholders "--"
        self.assertIn('gpuName: "--"', content)
        self.assertIn('cpuUsagePct: "--"', content)

    def test_bridge_has_get_system_telemetry(self):
        """Bridge must provide get_system_telemetry() returning real host status."""
        self.assertTrue(hasattr(self.api, "get_system_telemetry"))
        res = self.api.get_system_telemetry()
        self.assertEqual(res.get("status"), "ok")
        self.assertIn("telemetry", res)

    def test_bubble_notify_signature_in_state_js(self):
        """_bubbleNotify in state.js must support (fullPath, newValue, oldValue, parentObject, changeType)."""
        state_js_path = Path("src/deskai/static/js/state.js")
        content = state_js_path.read_text(encoding="utf-8")
        self.assertIn("_bubbleNotify(fullPath, newValue, oldValue, parentObject", content)

    def test_editor_has_save_active_buffer(self):
        """editor.js must implement saveActiveBuffer method."""
        editor_js_path = Path("src/deskai/static/js/editor.js")
        content = editor_js_path.read_text(encoding="utf-8")
        self.assertIn("saveActiveBuffer", content)


if __name__ == "__main__":
    unittest.main()
