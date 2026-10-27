import re
import sys
import unittest
from collections import namedtuple
from pathlib import Path
from unittest.mock import MagicMock, patch

from deskai.bridge.api import DesktopBridgeAPI
from deskai.bridge.window import BG_APP

_SConn = namedtuple("_SConn", ["laddr", "status", "pid"])
_LAddr = namedtuple("_LAddr", ["ip", "port"])


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

    def test_get_listening_ports_origin_guard_subdomain_and_port(self):
        """Subdomain spoofing and wrong port must be rejected."""
        self.mock_window.get_current_url.return_value = "http://127.0.0.1:8000.evil.com/"
        res = self.api.get_listening_ports()
        self.assertEqual(res["status"], "error")

        self.mock_window.get_current_url.return_value = "http://127.0.0.1:8001/"
        res = self.api.get_listening_ports()
        self.assertEqual(res["status"], "error")

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
        self.assertEqual(supervisor["exposure"], "loopback")
        self.assertFalse(supervisor["openable"])

    def test_get_listening_ports_ipv4_and_ipv6_distinct(self):
        """IPv4 and IPv6 listeners on same port produce two distinct rows."""
        fake_conns = [
            _SConn(laddr=_LAddr("127.0.0.1", 3000), status="LISTEN", pid=101),
            _SConn(laddr=_LAddr("::1", 3000), status="LISTEN", pid=102),
        ]

        def fake_proc(pid):
            mock = MagicMock()
            mock.name.return_value = "node" if pid == 101 else "python3"
            return mock

        with patch("psutil.net_connections", return_value=fake_conns), patch("psutil.Process", side_effect=fake_proc):
            res = self.api.get_listening_ports()
            self.assertEqual(res["status"], "ok")
            p3000 = [p for p in res["ports"] if p["port"] == 3000]
            self.assertEqual(len(p3000), 2)

            ipv4_row = next(p for p in p3000 if p["host"] == "127.0.0.1")
            self.assertEqual(ipv4_row["address"], "http://127.0.0.1:3000")
            self.assertEqual(ipv4_row["process"], "node")
            self.assertEqual(ipv4_row["exposure"], "loopback")
            self.assertTrue(ipv4_row["openable"])

            ipv6_row = next(p for p in p3000 if p["host"] == "[::1]")
            self.assertEqual(ipv6_row["address"], "http://[::1]:3000")
            self.assertEqual(ipv6_row["process"], "python3")
            self.assertEqual(ipv6_row["exposure"], "loopback")
            self.assertTrue(ipv6_row["openable"])

    def test_get_listening_ports_filtering_and_unwrapping(self):
        """Filter port < 1024, LAN IPs, unwrap ::ffff:127.0.0.1, and mark 0.0.0.0 and :: as all-interfaces."""
        fake_conns = [
            _SConn(laddr=_LAddr("::ffff:127.0.0.1", 4000), status="LISTEN", pid=201),
            _SConn(laddr=_LAddr("127.0.0.1", 80), status="LISTEN", pid=202),  # < 1024 filtered
            _SConn(laddr=_LAddr("192.168.1.50", 5000), status="LISTEN", pid=203),  # LAN filtered
            _SConn(laddr=_LAddr("0.0.0.0", 6000), status="LISTEN", pid=204),  # all-interfaces
            _SConn(laddr=_LAddr("::", 7000), status="LISTEN", pid=205),  # all-interfaces
        ]

        with (
            patch("psutil.net_connections", return_value=fake_conns),
            patch("psutil.Process", side_effect=lambda pid: MagicMock(name=lambda: f"proc_{pid}")),
        ):
            res = self.api.get_listening_ports()
            ports = {p["port"]: p for p in res["ports"]}

            # 4000 unwrapped to 127.0.0.1
            self.assertIn(4000, ports)
            self.assertEqual(ports[4000]["host"], "127.0.0.1")
            self.assertEqual(ports[4000]["exposure"], "loopback")

            # 80 filtered
            self.assertNotIn(80, ports)

            # 5000 (LAN) filtered
            self.assertNotIn(5000, ports)

            # 6000 (0.0.0.0) -> all-interfaces, host 127.0.0.1
            self.assertIn(6000, ports)
            self.assertEqual(ports[6000]["host"], "127.0.0.1")
            self.assertEqual(ports[6000]["exposure"], "all-interfaces")

            # 7000 (::) -> all-interfaces, host [::1]
            self.assertIn(7000, ports)
            self.assertEqual(ports[7000]["host"], "[::1]")
            self.assertEqual(ports[7000]["exposure"], "all-interfaces")

    def test_get_listening_ports_access_denied(self):
        """AccessDenied appends socket_table_denied and returns supervisor row."""
        import psutil

        with patch("psutil.net_connections", side_effect=psutil.AccessDenied()):
            res = self.api.get_listening_ports()
            self.assertEqual(res["status"], "ok")
            self.assertIn("socket_table_denied", res["warnings"])
            self.assertTrue(any(p["port"] == 8000 for p in res["ports"]))

    def test_get_listening_ports_psutil_missing(self):
        """Missing psutil appends psutil_missing and returns supervisor row."""
        with patch.dict(sys.modules, {"psutil": None}):
            res = self.api.get_listening_ports()
            self.assertEqual(res["status"], "ok")
            self.assertIn("psutil_missing", res["warnings"])
            self.assertTrue(any(p["port"] == 8000 for p in res["ports"]))

    def test_open_port_validation_and_dispatch(self):
        """open_port enforces integer type, range, host allowlist, and rejects supervisor port."""
        # Supervisor port rejected
        self.assertFalse(self.api.open_port(8000))

        # Bool rejected (not real int)
        self.assertFalse(self.api.open_port(True))  # type: ignore
        self.assertFalse(self.api.open_port(False))  # type: ignore

        # Out-of-range ports rejected
        self.assertFalse(self.api.open_port(0))
        self.assertFalse(self.api.open_port(65536))
        self.assertFalse(self.api.open_port(-1))

        # Host allowlist
        self.assertFalse(self.api.open_port(3000, host="localhost"))
        self.assertFalse(self.api.open_port(3000, host="evil.com"))
        self.assertFalse(self.api.open_port(3000, host="192.168.1.1"))

        # Valid calls dispatch to webbrowser.open
        with patch("webbrowser.open", return_value=True) as mock_open:
            self.assertTrue(self.api.open_port(3000, host="127.0.0.1"))
            mock_open.assert_called_with("http://127.0.0.1:3000")

            self.assertTrue(self.api.open_port(5173, host="[::1]"))
            mock_open.assert_called_with("http://[::1]:5173")

    def test_open_external_url_security_hardening(self):
        """open_external_url rejects malformed, control-character, and non-whitelisted URLs."""
        # Rejections
        self.assertFalse(self.api.open_external_url(""))
        self.assertFalse(self.api.open_external_url("http://"))
        self.assertFalse(self.api.open_external_url("http://example.com/\nfoo"))
        self.assertFalse(self.api.open_external_url("javascript:alert(1)"))
        self.assertFalse(self.api.open_external_url("file:///etc/passwd"))
        self.assertFalse(self.api.open_external_url("http://user:pass@host/"))
        self.assertFalse(self.api.open_external_url("mailto:"))

        # Valid URLs
        with patch("webbrowser.open", return_value=True) as mock_open:
            self.assertTrue(self.api.open_external_url("http://127.0.0.1:3000/path?query=1"))
            mock_open.assert_called_with("http://127.0.0.1:3000/path?query=1")

            self.assertTrue(self.api.open_external_url("https://example.com/docs"))
            mock_open.assert_called_with("https://example.com/docs")

            self.assertTrue(self.api.open_external_url("mailto:support@deskai.dev"))
            mock_open.assert_called_with("mailto:support@deskai.dev")

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

    def test_horizontal_drawer_resizer_declared_in_index_html(self):
        """index.html must declare the horizontal resizerRow above bottomDrawer."""
        index_html = Path("src/deskai/static/index.html").read_text(encoding="utf-8")
        self.assertIn('id="resizerBottom"', index_html)
        self.assertIn('class="resizer-row"', index_html)
        self.assertIn('aria-orientation="horizontal"', index_html)

    def test_resizer_row_defined_in_layout_css(self):
        """layout.css must define .resizer-row with cursor: row-resize."""
        layout_css = Path("src/deskai/static/css/layout.css").read_text(encoding="utf-8")
        self.assertIn(".resizer-row", layout_css)
        self.assertIn("cursor: row-resize;", layout_css)

    def test_events_js_binds_resizer_bottom(self):
        """events.js must bind resizerBottom mouse and keyboard events."""
        events_js = Path("src/deskai/static/js/events.js").read_text(encoding="utf-8")
        self.assertIn("resizerBottom", events_js)
        self.assertIn("--bottom-drawer-h", events_js)
        self.assertIn("ArrowUp", events_js)
        self.assertIn("ArrowDown", events_js)

    def test_static_html_aria_spec_conformance(self):
        """index.html drawer structure conforms to ARIA tablist/tab/tabpanel spec."""
        index_html = Path("src/deskai/static/index.html").read_text(encoding="utf-8")

        # Resizer ARIA
        self.assertIn('id="resizerBottom"', index_html)
        self.assertIn('aria-valuenow="', index_html)
        self.assertIn('aria-valuemin="48"', index_html)
        self.assertIn('aria-valuemax="', index_html)

        # Toggle button ARIA
        self.assertIn('id="drawerToggleBtn"', index_html)
        self.assertIn('aria-expanded="true"', index_html)

        # Tabs and panels
        for name in ["terminal", "output", "problems", "ports"]:
            self.assertIn(f'id="tab-{name}"', index_html)
            self.assertIn(f'aria-controls="{name}Panel"', index_html)
            self.assertIn(f'id="{name}Panel"', index_html)
            self.assertIn(f'aria-labelledby="tab-{name}"', index_html)
            self.assertIn(f'id="{name}Panel" role="tabpanel"', index_html)

    def test_css_tokens_and_variables_hygiene(self):
        """All var(--*) references across CSS must exist in tokens.css, with zero raw colors outside tokens.css."""
        tokens_text = Path("src/deskai/static/css/tokens.css").read_text(encoding="utf-8")
        defined_tokens = set(re.findall(r"(--[a-zA-Z0-9_-]+):", tokens_text))

        css_dir = Path("src/deskai/static/css")
        for path in css_dir.glob("*.css"):
            content = path.read_text(encoding="utf-8")
            used_tokens = re.findall(r"var\(\s*(--[a-zA-Z0-9_-]+)", content)
            missing = [t for t in used_tokens if t not in defined_tokens]
            self.assertEqual(missing, [], f"Missing tokens in {path.name}: {missing}")

            if path.name != "tokens.css":
                raw_hexes = re.findall(r"#[0-9a-fA-F]{3,8}\b", content)
                self.assertEqual(raw_hexes, [], f"Raw hex found in {path.name}: {raw_hexes}")
                raw_rgbs = re.findall(r"rgba?\([^)]+\)", content)
                self.assertEqual(raw_rgbs, [], f"Raw rgba found in {path.name}: {raw_rgbs}")

    def test_window_bg_app_matches_tokens_css(self):
        """window.py BG_APP must match --bg-app in tokens.css."""
        tokens_text = Path("src/deskai/static/css/tokens.css").read_text(encoding="utf-8")
        match = re.search(r"--bg-app:\s*(#[0-9a-fA-F]{6})", tokens_text)
        self.assertIsNotNone(match)
        self.assertEqual(BG_APP.lower(), match.group(1).lower())


if __name__ == "__main__":
    unittest.main()
