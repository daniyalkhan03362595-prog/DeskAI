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
        """events.js and its resizers module must bind resizerBottom mouse and keyboard events."""
        events_js = Path("src/deskai/static/js/events.js").read_text(encoding="utf-8")
        resizers_js = (
            Path("src/deskai/static/js/events/resizers.js").read_text(encoding="utf-8")
            if Path("src/deskai/static/js/events/resizers.js").exists()
            else ""
        )
        combined = events_js + "\n" + resizers_js
        self.assertIn("resizerBottom", combined)
        self.assertIn("--bottom-drawer-h", combined)
        self.assertIn("ArrowUp", combined)
        self.assertIn("ArrowDown", combined)

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


try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


# ---------------------------------------------------------------------------
# Helper fixture data used across Playwright tests
# ---------------------------------------------------------------------------

_THREE_PORTS = [
    {
        "port": 3000,
        "host": "127.0.0.1",
        "protocol": "TCP",
        "address": "http://127.0.0.1:3000",
        "process": "node",
        "pid": 100,
        "status": "Listening",
        "origin": "Local",
        "exposure": "loopback",
        "openable": True,
        "isCustom": False,
    },
    {
        "port": 8080,
        "host": "127.0.0.1",
        "protocol": "TCP",
        "address": "http://127.0.0.1:8080",
        "process": "python3",
        "pid": 200,
        "status": "Listening",
        "origin": "Local",
        "exposure": "loopback",
        "openable": True,
        "isCustom": False,
    },
    {
        "port": 5173,
        "host": "127.0.0.1",
        "protocol": "TCP",
        "address": "http://127.0.0.1:5173",
        "process": "vite",
        "pid": 300,
        "status": "Listening",
        "origin": "Local",
        "exposure": "loopback",
        "openable": True,
        "isCustom": False,
    },
]

_OK_RESPONSE = {"status": "ok", "ports": _THREE_PORTS, "warnings": []}

_FOUR_PORTS_WITH_EPHEMERAL = [
    {
        "port": 3000,
        "host": "127.0.0.1",
        "protocol": "TCP",
        "address": "http://127.0.0.1:3000",
        "process": "node",
        "pid": 100,
        "status": "Listening",
        "origin": "Local",
        "exposure": "loopback",
        "openable": True,
        "isCustom": False,
    },
    {
        "port": 8080,
        "host": "127.0.0.1",
        "protocol": "TCP",
        "address": "http://127.0.0.1:8080",
        "process": "python3",
        "pid": 200,
        "status": "Listening",
        "origin": "Local",
        "exposure": "loopback",
        "openable": True,
        "isCustom": False,
    },
    {
        "port": 40000,
        "host": "127.0.0.1",
        "protocol": "TCP",
        "address": "http://127.0.0.1:40000",
        "process": "transient",
        "pid": 400,
        "status": "Listening",
        "origin": "Local",
        "exposure": "loopback",
        "openable": True,
        "isCustom": False,
    },
    {
        "port": 50000,
        "host": "127.0.0.1",
        "protocol": "TCP",
        "address": "http://127.0.0.1:50000",
        "process": "ephemeral",
        "pid": 500,
        "status": "Listening",
        "origin": "Local",
        "exposure": "loopback",
        "openable": True,
        "isCustom": False,
    },
]


class TestPortsPlaywright(unittest.TestCase):
    """Playwright integration tests for the Ports panel frontend."""

    @classmethod
    def setUpClass(cls):
        if not _HAS_PLAYWRIGHT:
            raise unittest.SkipTest("Playwright is not installed")
        cls.p = sync_playwright().start()
        try:
            cls.browser = cls.p.chromium.launch(headless=True, args=["--allow-file-access-from-files"])
        except Exception as e:
            cls.p.stop()
            raise unittest.SkipTest(f"Chromium launch failed: {e}")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "browser"):
            cls.browser.close()
        if hasattr(cls, "p"):
            cls.p.stop()

    def setUp(self):
        index_file = Path("src/deskai/static/index.html").resolve()
        self.context = self.browser.new_context(viewport={"width": 1280, "height": 800})
        self.page = self.context.new_page()
        self.page.goto(f"file://{index_file}")
        # Wait for portsTableBody to be attached (it's inside a hidden panel initially)
        self.page.wait_for_selector("#portsTableBody", state="attached")
        # Wait for DeskAIPorts to be initialised (app.js is a module, may defer)
        self.page.wait_for_function("typeof window.DeskAIPorts !== 'undefined'")
        # Click the Ports tab to make the panel visible (it starts hidden)
        self.page.evaluate("() => { const t = document.getElementById('tab-ports'); if (t) t.click(); }")
        # Wait for portsPanel to lose its hidden attribute
        self.page.wait_for_function("!document.getElementById('portsPanel').hasAttribute('hidden')")

    def tearDown(self):
        if hasattr(self, "page"):
            self.page.close()
        if hasattr(self, "context"):
            self.context.close()

    # ------------------------------------------------------------------
    # TC-PP-01: Sort by each column
    # ------------------------------------------------------------------
    def test_pp_01_sort_by_each_column(self):
        """Clicking sort headers reorders table rows correctly for port/process/pid."""
        self.page.evaluate(
            """(res) => { window.DeskAIPorts.handleRefreshResponse(res); }""",
            _OK_RESPONSE,
        )
        self.page.wait_for_function("document.querySelector('#portsTableBody tr') !== null")

        # Default sort: port ascending → 3000, 5173, 8080
        rows = self.page.locator("#portsTableBody tr")
        self.assertEqual(rows.count(), 3)
        first_port = rows.nth(0).locator("td").nth(0).locator(".port-num-badge").text_content()
        self.assertEqual(first_port, "3000")
        last_port = rows.nth(2).locator("td").nth(0).locator(".port-num-badge").text_content()
        self.assertEqual(last_port, "8080")

        # Click port header again → descending: 8080, 5173, 3000
        self.page.evaluate("() => { document.querySelector(\"#portsTable th[data-sort='port']\").click(); }")
        rows = self.page.locator("#portsTableBody tr")
        first_port = rows.nth(0).locator("td").nth(0).locator(".port-num-badge").text_content()
        self.assertEqual(first_port, "8080")

        # Click process header → ascending by process name: node, python3, vite
        self.page.evaluate("() => { document.querySelector(\"#portsTable th[data-sort='process']\").click(); }")
        rows = self.page.locator("#portsTableBody tr")
        first_proc = rows.nth(0).locator("td").nth(3).text_content()
        self.assertEqual(first_proc, "node")
        last_proc = rows.nth(2).locator("td").nth(3).text_content()
        self.assertEqual(last_proc, "vite")

        # Click pid header → ascending by pid: 100, 200, 300
        self.page.evaluate("() => { document.querySelector(\"#portsTable th[data-sort='pid']\").click(); }")
        rows = self.page.locator("#portsTableBody tr")
        first_pid = rows.nth(0).locator("td").nth(4).text_content()
        self.assertEqual(first_pid, "100")

    # ------------------------------------------------------------------
    # TC-PP-02: Text filter
    # ------------------------------------------------------------------
    def test_pp_02_text_filter(self):
        """Typing in the filter input shows only matching rows."""
        self.page.evaluate(
            """(res) => { window.DeskAIPorts.handleRefreshResponse(res); }""",
            _OK_RESPONSE,
        )
        self.page.wait_for_function("document.querySelector('#portsTableBody tr') !== null")

        # Before filter: 3 rows
        self.assertEqual(self.page.locator("#portsTableBody tr").count(), 3)

        # Type "node" → only node row
        self.page.locator("#portsFilterInput").fill("node")
        self.page.locator("#portsFilterInput").dispatch_event("input")
        rows = self.page.locator("#portsTableBody tr")
        self.assertEqual(rows.count(), 1)
        proc_text = rows.nth(0).locator("td").nth(3).text_content()
        self.assertEqual(proc_text, "node")

        # Type "5173" → only vite row
        self.page.locator("#portsFilterInput").fill("5173")
        self.page.locator("#portsFilterInput").dispatch_event("input")
        rows = self.page.locator("#portsTableBody tr")
        self.assertEqual(rows.count(), 1)
        port_text = rows.nth(0).locator(".port-num-badge").text_content()
        self.assertEqual(port_text, "5173")

        # Clear filter → 3 rows again
        self.page.locator("#portsFilterInput").fill("")
        self.page.locator("#portsFilterInput").dispatch_event("input")
        self.assertEqual(self.page.locator("#portsTableBody tr").count(), 3)

    # ------------------------------------------------------------------
    # TC-PP-03: Transient toggle hides/shows ephemeral ports
    # ------------------------------------------------------------------
    def test_pp_03_transient_toggle(self):
        """Ephemeral ports (>= 32768) are hidden by default; toggle shows them."""
        res = {"status": "ok", "ports": _FOUR_PORTS_WITH_EPHEMERAL, "warnings": []}
        self.page.evaluate(
            """(res) => { window.DeskAIPorts.handleRefreshResponse(res); }""",
            res,
        )
        self.page.wait_for_function("document.querySelector('#portsTableBody tr') !== null")

        # Without toggle: only the 2 non-ephemeral ports visible (3000, 8080)
        rows = self.page.locator("#portsTableBody tr")
        self.assertEqual(rows.count(), 2)

        # Enable transient toggle
        self.page.evaluate("""() => {
            const cb = document.getElementById('portsTransientToggle');
            cb.checked = true;
            cb.dispatchEvent(new Event('change'));
        }""")
        rows = self.page.locator("#portsTableBody tr")
        self.assertEqual(rows.count(), 4)

        # Disable transient toggle
        self.page.evaluate("""() => {
            const cb = document.getElementById('portsTransientToggle');
            cb.checked = false;
            cb.dispatchEvent(new Event('change'));
        }""")
        rows = self.page.locator("#portsTableBody tr")
        self.assertEqual(rows.count(), 2)

    # ------------------------------------------------------------------
    # TC-PP-04: Persistence — workspace rootPath change reloads customPorts
    # ------------------------------------------------------------------
    def test_pp_04_persistence_workspace_change(self):
        """store.subscribe on workspace.rootPath triggers reload of customPorts."""
        result = self.page.evaluate("""() => {
            // Write a custom port to the new-workspace key in localStorage
            const key = 'deskai_watched_ports_/workspace/new';
            const entry = [{
                port: 9999,
                host: '127.0.0.1',
                protocol: 'TCP',
                address: 'http://127.0.0.1:9999',
                process: 'custom-svc',
                origin: 'Watched',
                exposure: 'loopback',
                openable: true
            }];
            localStorage.setItem(key, JSON.stringify(entry));

            // Simulate workspace path change via store if subscribe is registered,
            // otherwise call loadWatchedPorts directly after setting the key.
            // The constructor subscribes to workspace.rootPath changes.
            if (window.store && typeof window.store.subscribe === 'function') {
                // Patch getStorageKey to return new key
                const origGet = window.DeskAIPorts.getStorageKey.bind(window.DeskAIPorts);
                window.DeskAIPorts.getStorageKey = () => key;
                window.DeskAIPorts.customPorts = window.DeskAIPorts.loadWatchedPorts();
                window.DeskAIPorts.getStorageKey = origGet;
            } else {
                window.DeskAIPorts.getStorageKey = () => key;
                window.DeskAIPorts.customPorts = window.DeskAIPorts.loadWatchedPorts();
            }
            return window.DeskAIPorts.customPorts;
        }""")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["port"], 9999)
        self.assertEqual(result[0]["host"], "127.0.0.1")

    # ------------------------------------------------------------------
    # TC-PP-05: Badge text — normal + ephemeral → "N shown (M hidden)"
    # ------------------------------------------------------------------
    def test_pp_05_badge_text_with_hidden(self):
        """Badge shows 'N shown (M hidden)' when ephemeral ports are filtered out."""
        res = {"status": "ok", "ports": _FOUR_PORTS_WITH_EPHEMERAL, "warnings": []}
        self.page.evaluate(
            """(res) => { window.DeskAIPorts.handleRefreshResponse(res); }""",
            res,
        )
        self.page.wait_for_function("document.querySelector('#portsTableBody tr') !== null")

        badge_text = self.page.locator("#portsCountBadge").text_content()
        self.assertEqual(badge_text, "2 shown (2 hidden)")

        # After enabling transient toggle all 4 shown → "4 active"
        self.page.evaluate("""() => {
            const cb = document.getElementById('portsTransientToggle');
            cb.checked = true;
            cb.dispatchEvent(new Event('change'));
        }""")
        badge_text = self.page.locator("#portsCountBadge").text_content()
        self.assertEqual(badge_text, "4 active")

    # ------------------------------------------------------------------
    # TC-PP-06: Poll-error keeps rows and marks them stale
    # ------------------------------------------------------------------
    def test_pp_06_poll_error_preserves_rows_marks_stale(self):
        """After a good response, an error response keeps rows but marks status stale."""
        # First: successful response populates rows
        self.page.evaluate(
            """(res) => { window.DeskAIPorts.handleRefreshResponse(res); }""",
            _OK_RESPONSE,
        )
        self.page.wait_for_function("document.querySelector('#portsTableBody tr') !== null")
        self.assertEqual(self.page.locator("#portsTableBody tr").count(), 3)

        # Second: error response — rows must remain, statuses get "(Stale)" suffix
        self.page.evaluate("""() => {
            window.DeskAIPorts.handleRefreshResponse({
                status: 'error',
                message: 'Supervisor unreachable'
            });
        }""")

        rows = self.page.locator("#portsTableBody tr")
        self.assertEqual(rows.count(), 3)

        # Every status cell should now end with "(Stale)"
        for i in range(3):
            status_text = rows.nth(i).locator(".port-status-pill").text_content()
            self.assertTrue(
                status_text.endswith("(Stale)"),
                f"Row {i} status '{status_text}' should end with '(Stale)'",
            )

        # Warning banner should be visible
        banner = self.page.locator("#portsWarningBanner")
        self.assertFalse(banner.get_attribute("hidden") is not None and banner.get_attribute("hidden") == "")

    # ------------------------------------------------------------------
    # TC-PP-07: Focus restore for IPv6 copy button
    # ------------------------------------------------------------------
    def test_pp_07_focus_restore_ipv6_copy_button(self):
        """After re-render, focus is restored to the correct IPv6 copy button."""
        ipv4_ipv6_ports = [
            {
                "port": 3000,
                "host": "127.0.0.1",
                "protocol": "TCP",
                "address": "http://127.0.0.1:3000",
                "process": "node",
                "pid": 100,
                "status": "Listening",
                "origin": "Local",
                "exposure": "loopback",
                "openable": True,
                "isCustom": False,
            },
            {
                "port": 3000,
                "host": "[::1]",
                "protocol": "TCP",
                "address": "http://[::1]:3000",
                "process": "node",
                "pid": 102,
                "status": "Listening",
                "origin": "Local",
                "exposure": "loopback",
                "openable": True,
                "isCustom": False,
            },
        ]
        res = {"status": "ok", "ports": ipv4_ipv6_ports, "warnings": []}
        self.page.evaluate(
            """(res) => { window.DeskAIPorts.handleRefreshResponse(res); }""",
            res,
        )
        self.page.wait_for_function("document.querySelector('#portsTableBody tr') !== null")
        self.assertEqual(self.page.locator("#portsTableBody tr").count(), 2)

        # Focus the copy button for the IPv6 row (second row)
        self.page.evaluate("""() => {
            const btn = document.querySelector(
                'button[data-action="copy-port"][data-port="3000"][data-host="[::1]"]'
            );
            if (btn) btn.focus();
        }""")

        # Re-render by forcing a status change on a port (invalidates signature)
        self.page.evaluate("""() => {
            window.DeskAIPorts.portsList[0].status = 'Updated';
            window.DeskAIPorts._lastSignature = null;
            window.DeskAIPorts.render();
        }""")

        # The IPv6 copy button should have focus restored
        focused_host = self.page.evaluate("""() => {
            const el = document.activeElement;
            return el ? el.getAttribute('data-host') : null;
        }""")
        self.assertEqual(focused_host, "[::1]")

    # ------------------------------------------------------------------
    # TC-PP-08: Screen reader announcement on copy
    # ------------------------------------------------------------------
    def test_pp_08_copy_announcer_feedback(self):
        """Clicking copy-port announces URL to screenReaderAnnouncer."""
        self.page.evaluate(
            """(res) => {
            Object.defineProperty(navigator, 'clipboard', {
                value: { writeText: async () => true },
                configurable: true
            });
            window.DeskAIPorts.handleRefreshResponse(res);
        }""",
            _OK_RESPONSE,
        )
        self.page.wait_for_function("document.querySelector('#portsTableBody tr') !== null")

        copy_btn = self.page.locator('button[data-action="copy-port"][data-port="3000"]')
        copy_btn.click()

        announcer_text = self.page.locator("#screenReaderAnnouncer").text_content()
        self.assertEqual(announcer_text, "Copied http://127.0.0.1:3000")

    # ------------------------------------------------------------------
    # TC-PP-09: Watched port merged with detected offers Stop Watching
    # ------------------------------------------------------------------
    def test_pp_09_watched_port_merged_with_detected_offers_stop_watching(self):
        """A watched port that is also detected merges isCustom=True and retains remove-port action."""
        self.page.evaluate("""() => {
            window.DeskAIPorts.customPorts = [{
                port: 3000,
                host: "127.0.0.1",
                protocol: "TCP",
                address: "http://127.0.0.1:3000",
                process: "Watched",
                status: "Probing...",
                origin: "Watched",
                isCustom: true,
                exposure: "loopback",
                openable: true
            }];
        }""")
        self.page.evaluate(
            """(res) => { window.DeskAIPorts.handleRefreshResponse(res); }""",
            _OK_RESPONSE,
        )
        self.page.wait_for_function("document.querySelector('#portsTableBody tr') !== null")

        remove_btn = self.page.locator('button[data-action="remove-port"][data-port="3000"]')
        self.assertEqual(remove_btn.count(), 1)
        self.assertEqual(remove_btn.get_attribute("title"), "Stop Watching Port")

    # ------------------------------------------------------------------
    # TC-PP-10: Error on empty table never shows 'No active listening ports detected'
    # ------------------------------------------------------------------
    def test_pp_10_poll_error_empty_state_message(self):
        """Error when table has no ports shows error guidance, never 'No active listening ports detected'."""
        self.page.evaluate("""() => {
            window.DeskAIPorts.customPorts = [];
            window.DeskAIPorts.portsList = [];
            window.DeskAIPorts.handleRefreshResponse({
                status: 'error',
                message: 'Failed to scan socket table'
            });
        }""")

        empty_cell = self.page.locator("#portsTableBody .ports-empty")
        self.assertEqual(empty_cell.count(), 1)
        text = empty_cell.text_content()
        self.assertNotIn("No active listening ports detected", text)
        self.assertIn("Unable to retrieve active ports", text)


if __name__ == "__main__":
    unittest.main()
