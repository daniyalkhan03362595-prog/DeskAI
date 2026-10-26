import unittest
from pathlib import Path
from unittest.mock import MagicMock
from deskai.bridge.api import DesktopBridgeAPI


class TestPortsDrawerTab(unittest.TestCase):
    def setUp(self):
        self.mock_manager = MagicMock()
        self.mock_window = MagicMock()
        self.mock_manager.window = self.mock_window
        self.mock_manager.server.port = 8000
        self.mock_window.get_current_url.return_value = "http://127.0.0.1:8000/"
        self.api = DesktopBridgeAPI(self.mock_manager)

    def test_get_listening_ports_origin_guarded(self):
        """Unauthorized origins must be rejected with an error status."""
        self.mock_window.get_current_url.return_value = "http://evil.com/"
        res = self.api.get_listening_ports()
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["ports"], [])

    def test_get_listening_ports_includes_supervisor(self):
        """Authorized calls must include the DeskAI supervisor port."""
        res = self.api.get_listening_ports()
        self.assertEqual(res["status"], "ok")
        ports = res["ports"]
        self.assertIsInstance(ports, list)
        supervisor = next((p for p in ports if p["port"] == 8000), None)
        self.assertIsNotNone(supervisor)
        self.assertEqual(supervisor["process"], "DeskAI Supervisor")
        self.assertEqual(supervisor["address"], "http://127.0.0.1:8000")
        self.assertEqual(supervisor["origin"], "System")

    def test_index_html_declares_ports_tab_and_panel(self):
        """index.html must declare the Ports tab and portsPanel structure."""
        index_html = Path("src/deskai/static/index.html").read_text(encoding="utf-8")
        self.assertIn('data-target="ports"', index_html)
        self.assertIn('id="portsPanel"', index_html)
        self.assertIn('id="portsTable"', index_html)
        self.assertIn('data-action="add-port"', index_html)
        self.assertIn('data-action="refresh-ports"', index_html)

    def test_ports_js_module_exists_and_exports_manager(self):
        """ports.js must exist and export PortsManager and initPorts."""
        ports_js = Path("src/deskai/static/js/ports.js")
        self.assertTrue(ports_js.exists())
        content = ports_js.read_text(encoding="utf-8")
        self.assertIn("class PortsManager", content)
        self.assertIn("function initPorts", content)
        self.assertIn("promptAddPort", content)
        self.assertIn("openPort", content)

    def test_bridge_js_exposes_list_ports(self):
        """bridge.js NativeBridge must expose listPorts method."""
        bridge_js = Path("src/deskai/static/js/bridge.js").read_text(encoding="utf-8")
        self.assertIn("listPorts()", bridge_js)


if __name__ == "__main__":
    unittest.main()
