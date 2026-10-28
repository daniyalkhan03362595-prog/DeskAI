import unittest
from unittest.mock import MagicMock
from playwright.sync_api import sync_playwright

from deskai.bridge.api import DesktopBridgeAPI
from deskai.server.supervisor import DesktopServer


class TestFrontendStateAndTelemetry(unittest.TestCase):
    def setUp(self):
        self.mock_manager = MagicMock()
        self.mock_window = MagicMock()
        self.mock_manager.window = self.mock_window
        self.mock_manager.server.port = 8000
        self.mock_window.get_current_url.return_value = "http://127.0.0.1:8000/"

        self.api = DesktopBridgeAPI(self.mock_manager)

    def test_bridge_has_get_system_telemetry(self):
        """Bridge must provide get_system_telemetry() returning real host status."""
        self.assertTrue(hasattr(self.api, "get_system_telemetry"))
        res = self.api.get_system_telemetry()
        self.assertEqual(res.get("status"), "ok")
        self.assertIn("telemetry", res)

    def test_initial_state_has_no_hardcoded_hardware_specs_runtime(self):
        """Behavioral: Initial store state in browser runtime contains clean '--' defaults, no hardcoded specs."""
        server = DesktopServer()
        server.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(f"http://127.0.0.1:{server.port}/auth/redeem?token={server.launch_token}")
                page.wait_for_selector("#appRoot")

                telemetry = page.evaluate("() => window.store.state.telemetry")
                self.assertEqual(telemetry.get("gpuName"), "--")
                self.assertEqual(telemetry.get("cpuUsagePct"), "--")
                self.assertEqual(telemetry.get("vramUsedMB"), "--")
                self.assertEqual(telemetry.get("vramTotalMB"), "--")
                self.assertNotIn("Apple M3", str(telemetry))
                self.assertNotIn("NVIDIA RTX", str(telemetry))
                browser.close()
        finally:
            server.stop()

    def test_store_deep_reactivity_and_notifications_runtime(self):
        """Behavioral: Mutating nested store paths triggers subscribers with new and old values."""
        server = DesktopServer()
        server.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(f"http://127.0.0.1:{server.port}/auth/redeem?token={server.launch_token}")
                page.wait_for_selector("#appRoot")

                res = page.evaluate("""() => {
                    let notified = false;
                    let receivedNew = null;
                    const unsub = window.store.subscribe("workspace.rootPath", (newVal) => {
                        notified = true;
                        receivedNew = newVal;
                    });
                    window.store.state.workspace.rootPath = "/mock/workspace/active";
                    unsub();
                    return { notified, receivedNew };
                }""")
                self.assertTrue(res["notified"])
                self.assertEqual(res["receivedNew"], "/mock/workspace/active")
                browser.close()
        finally:
            server.stop()

    def test_editor_save_active_buffer_behavioral(self):
        """Behavioral: EditorManager.saveActiveBuffer saves buffer content via bridge writeFile."""
        server = DesktopServer()
        server.start()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(f"http://127.0.0.1:{server.port}/auth/redeem?token={server.launch_token}")
                page.wait_for_selector("#appRoot")

                save_res = page.evaluate("""async () => {
                    let writtenPath = null;
                    let writtenContent = null;
                    window.NativeBridge.writeFile = async (p, c) => {
                        writtenPath = p;
                        writtenContent = c;
                        return { status: "ok", path: p };
                    };

                    window.EditorManager.createBuffer("sample.py", "print('hello')");
                    const activeId = window.EditorManager.activeTabId;
                    const buf = window.EditorManager.buffers.get(activeId);
                    buf.path = "sample.py";
                    buf.content = "print('updated')";
                    buf.isDirty = true;

                    const res = await window.EditorManager.saveActiveBuffer();
                    return { res, writtenPath, writtenContent, isDirty: buf.isDirty };
                }""")
                self.assertTrue(save_res["res"])
                self.assertEqual(save_res["writtenPath"], "sample.py")
                self.assertEqual(save_res["writtenContent"], "print('updated')")
                self.assertFalse(save_res["isDirty"])
                browser.close()
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
