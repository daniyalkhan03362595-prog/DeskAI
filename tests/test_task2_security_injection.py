from pathlib import Path
from unittest.mock import MagicMock
import unittest
from playwright.sync_api import sync_playwright

from deskai.bridge.api import DesktopBridgeAPI


class TestTask2OriginGuardUnit(unittest.TestCase):
    def test_origin_guard_blocks_unauthorized_origin(self):
        """Unit test: DesktopBridgeAPI rejects all calls when current window URL origin != app origin."""
        mock_manager = MagicMock()
        mock_manager.server.port = 8080
        mock_window = MagicMock()
        mock_manager.window = mock_window

        api = DesktopBridgeAPI(mock_manager)

        # 1. Foreign origin
        mock_window.get_current_url.return_value = "http://attacker.com/evil"
        self.assertEqual(api.select_folder()["status"], "error")
        self.assertEqual(api.select_file()["status"], "error")
        self.assertEqual(api.save_file_dialog()["status"], "error")
        self.assertFalse(api.open_external_url("https://example.com"))
        self.assertFalse(api.window_control("minimize"))

        # 2. Loopback with wrong port
        mock_window.get_current_url.return_value = "http://127.0.0.1:9999/app"
        self.assertEqual(api.select_folder()["status"], "error")
        self.assertEqual(api.select_file()["status"], "error")
        self.assertEqual(api.save_file_dialog()["status"], "error")
        self.assertFalse(api.open_external_url("https://example.com"))
        self.assertFalse(api.window_control("minimize"))

        # 3. Authorized origin
        mock_window.get_current_url.return_value = "http://127.0.0.1:8080/"
        mock_window.create_file_dialog.return_value = None
        # With authorized origin, select_folder runs and returns cancelled (not error)
        self.assertEqual(api.select_folder()["status"], "cancelled")


class TestTask2HtmlInjectionPlaywright(unittest.TestCase):
    def test_prompt_injection_payloads_neutralized(self):
        """Playwright test: injecting meta-refresh, action-button, and hostile tags."""
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()

            # Navigate to the app via local server or page content
            from deskai.server.supervisor import DesktopServer

            server = DesktopServer()
            server.start()
            try:
                redeem_url = f"http://127.0.0.1:{server.port}/auth/redeem?token={server.launch_token}"
                page.goto(redeem_url)
                page.wait_for_selector("#promptForm")

                initial_url = page.url
                self.assertTrue(initial_url.startswith(f"http://127.0.0.1:{server.port}"))

                # Payload 1: <meta http-equiv="refresh">
                page.fill("#promptTextarea", '<meta http-equiv="refresh" content="0;url=http://127.0.0.2:9/x">')
                page.click("#promptSendBtn")
                page.wait_for_timeout(300)

                # Assert URL was not changed / hijacked
                self.assertTrue(page.url.startswith(f"http://127.0.0.1:{server.port}"), f"URL hijacked: {page.url}")
                # Assert no meta refresh in DOM
                meta_tags = page.locator("meta[http-equiv='refresh']").count()
                self.assertEqual(meta_tags, 0, "Hostile meta tag was rendered in DOM")

                # Payload 2: <button data-action="win-close">
                page.fill("#promptTextarea", '<button id="injectedClose" data-action="win-close">Injected</button>')
                page.click("#promptSendBtn")
                page.wait_for_timeout(300)

                # The button should either not exist or be inside .bubble-body and ignored
                injected_btn = page.locator("#injectedClose")
                # When using textContent or safe DOM, #injectedClose does not exist as an element
                self.assertEqual(injected_btn.count(), 0, "Injected HTML button element exists in DOM")

                # Payload 3: <img src="http://127.0.0.2:9/x" onerror="...">
                page.fill("#promptTextarea", '<img src="http://127.0.0.2:9/x" onerror="window.__injected=1">')
                page.click("#promptSendBtn")
                page.wait_for_timeout(300)

                img_count = page.locator("article[data-role='user'] img").count()
                self.assertEqual(img_count, 0, "Hostile img tag was injected into user bubble")
            finally:
                browser.close()
                server.stop()

    def test_events_js_external_link_interceptor(self):
        """events.js must intercept http and https URLs and dispatch to NativeBridge."""
        events_js = Path("src/deskai/static/js/events.js").read_text(encoding="utf-8")
        self.assertIn('url.startsWith("http://")', events_js)
        self.assertIn('url.startsWith("https://")', events_js)


if __name__ == "__main__":
    unittest.main()
