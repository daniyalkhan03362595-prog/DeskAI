import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False

from deskai.bridge.api import DesktopBridgeAPI
from deskai.bridge.telemetry import TelemetryBridge, detect_host_gpu


class TestHardwareTelemetryDock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not _HAS_PLAYWRIGHT:
            raise unittest.SkipTest("Playwright is not installed")
        cls.p = sync_playwright().start()
        try:
            cls.browser = cls.p.chromium.launch(
                headless=True,
                args=["--allow-file-access-from-files"]
            )
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
        self.context = self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            permissions=["clipboard-read", "clipboard-write"]
        )
        self.page = self.context.new_page()
        self.page.goto(f"file://{index_file}")
        self.page.wait_for_selector("#hardwareDock")

    def tearDown(self):
        if hasattr(self, "page"):
            self.page.close()
        if hasattr(self, "context"):
            self.context.close()

    def test_backend_detect_host_gpu_structure(self):
        """detect_host_gpu returns a dict containing gpuName, vramUsedMB, and vramTotalMB."""
        gpu = detect_host_gpu()
        self.assertIsInstance(gpu, dict)
        self.assertIn("gpuName", gpu)
        self.assertIn("vramUsedMB", gpu)
        self.assertIn("vramTotalMB", gpu)

    def test_backend_telemetry_bridge_includes_gpu_and_ram(self):
        """TelemetryBridge.get_system_telemetry returns full hardware telemetry."""
        mock_mgr = MagicMock()
        mock_mgr.server.port = 8000
        mock_mgr.window.get_current_url.return_value = "http://127.0.0.1:8000/"

        api = DesktopBridgeAPI(mock_mgr)
        res = api.get_system_telemetry()

        self.assertEqual(res.get("status"), "ok")
        telem = res.get("telemetry", {})
        self.assertIn("gpuName", telem)
        self.assertIn("vramUsedMB", telem)
        self.assertIn("vramTotalMB", telem)
        self.assertIn("ramUsedMB", telem)
        self.assertIn("ramTotalMB", telem)
        self.assertIn("cpuUsagePct", telem)

    def test_hardware_dock_layout_in_flow_not_absolute(self):
        """CSS audit: #hardwareDock is position: relative (in-flow) so tree items are not occluded."""
        dock_pos = self.page.evaluate("getComputedStyle(document.getElementById('hardwareDock')).position")
        self.assertEqual(dock_pos, "relative", "#hardwareDock must be position: relative (not absolute)")

        sidebar_flex = self.page.evaluate("getComputedStyle(document.getElementById('sidebarLeft')).flexDirection")
        self.assertEqual(sidebar_flex, "column", "#sidebarLeft must be flex-direction: column")

        # Verify explorer-container takes remaining space
        explorer_flex = self.page.evaluate("getComputedStyle(document.querySelector('.explorer-container')).flexGrow")
        self.assertEqual(explorer_flex, "1", ".explorer-container must have flex-grow: 1")

    def test_hardware_dock_accessibility_attributes(self):
        """Accessibility audit: role=region, aria-label, progressbar labeling, and aria-live."""
        dock = self.page.locator("#hardwareDock")
        self.assertEqual(dock.get_attribute("role"), "region")
        self.assertEqual(dock.get_attribute("aria-label"), "Host System Telemetry")

        vram_track = self.page.locator("#teleVramTrack")
        self.assertEqual(vram_track.get_attribute("role"), "progressbar")
        self.assertEqual(vram_track.get_attribute("aria-label"), "VRAM Usage")

        gpu_badge = self.page.locator("#teleGpuBadge")
        self.assertEqual(gpu_badge.get_attribute("aria-live"), "polite")

    def test_frontend_bridge_has_get_system_telemetry_method(self):
        """NativeBridge exports getSystemTelemetry function."""
        has_method = self.page.evaluate("typeof window.NativeBridge.getSystemTelemetry === 'function'")
        self.assertTrue(has_method, "window.NativeBridge.getSystemTelemetry must be a function")

    def test_deskai_telemetry_sync_updates_dom_truthfully(self):
        """DeskAITelemetry.sync() updates store.state.telemetry and DOM elements."""
        self.page.evaluate("""() => {
            window.pywebview = {
                api: {
                    get_system_telemetry: async () => ({
                        status: "ok",
                        telemetry: {
                            gpuName: "NVIDIA GeForce RTX 4080",
                            vramUsedMB: 3072,
                            vramTotalMB: 16384,
                            ramUsedMB: 8192,
                            ramTotalMB: 32768,
                            cpuUsagePct: "12.4%",
                            status: "ready"
                        }
                    })
                }
            };
        }""")

        # Trigger sync
        self.page.evaluate("() => window.DeskAITelemetry.sync()")
        self.page.wait_for_timeout(50)

        gpu_text = self.page.locator("#teleGpuBadge").text_content().strip()
        vram_text = self.page.locator("#teleVramText").text_content().strip()
        vram_val = self.page.locator("#teleVramTrack").get_attribute("aria-valuenow")
        ram_text = self.page.locator("#teleRamText").text_content().strip()

        self.assertIn("NVIDIA GeForce RTX 4080", gpu_text)
        self.assertEqual(vram_text, "3.0 / 16 GB")
        self.assertEqual(vram_val, "19")  # 3072 / 16384 = ~18.75% -> 19
        self.assertEqual(ram_text, "8.0 / 32 GB")

    def test_deskai_telemetry_reset_to_unavailable(self):
        """When hardware telemetry returns unavailable or null, the UI gracefully resets."""
        self.page.evaluate("""() => {
            window.store.state.telemetry = {
                gpuName: "--",
                vramUsedMB: "--",
                vramTotalMB: "--",
                ramUsedMB: "--"
            };
        }""")
        self.page.wait_for_timeout(50)

        gpu_text = self.page.locator("#teleGpuBadge").text_content().strip()
        vram_text = self.page.locator("#teleVramText").text_content().strip()
        ram_text = self.page.locator("#teleRamText").text_content().strip()

        self.assertIn("Unavailable", gpu_text)
        self.assertEqual(vram_text, "Unavailable")
        self.assertEqual(ram_text, "Unavailable")
