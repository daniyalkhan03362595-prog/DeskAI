"""
E2E Playwright Smoke Test for DesktopServer HTTP Hosting.
Verifies loading the app over HTTP with real cookie auth:
1. Launch token redemption and deskai_session cookie auth.
2. App loads over http://127.0.0.1:<port> instead of file://.
3. Header buttons exist and are visible.
4. Ports panel renders and displays table.
5. Terminal opens and echoes typed command.
"""

import tempfile
import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False

from deskai.server.supervisor import DesktopServer


class TestServerE2ESmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not _HAS_PLAYWRIGHT:
            raise unittest.SkipTest("Playwright is not installed")
        cls.p = sync_playwright().start()
        try:
            cls.browser = cls.p.chromium.launch(headless=True)
        except Exception as e:
            cls.p.stop()
            raise unittest.SkipTest(f"Chromium launch failed: {e}")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "browser"):
            cls.browser.close()
        if hasattr(cls, "p"):
            cls.p.stop()

    def test_e2e_server_smoke_terminal_ports_and_header(self):
        """Playwright E2E: Loads over HTTP (not file://), verifies header buttons, ports panel, and terminal echo."""
        import httpx

        temp_workspace = Path(tempfile.mkdtemp()).resolve()
        srv = DesktopServer()
        srv.start()
        try:
            token = srv.security.create_launch_token()
            with httpx.Client(follow_redirects=False) as http:
                res = http.get(
                    f"http://127.0.0.1:{srv.port}/auth/redeem?token={token}",
                    headers={"Host": f"127.0.0.1:{srv.port}"},
                )
                cookie_val = res.cookies.get("deskai_session")
            self.assertIsNotNone(cookie_val, "Failed to redeem session cookie")

            session1 = srv.terminal_manager.create_session(str(temp_workspace))

            context = self.browser.new_context(viewport={"width": 1280, "height": 800})
            context.add_cookies([{"name": "deskai_session", "value": cookie_val, "domain": "127.0.0.1", "path": "/"}])
            page = context.new_page()

            page.add_init_script(f"""
                window.__mockSessionId = "{session1.session_id}";
                window.pywebview = {{
                    api: {{
                        terminal_open: async (cols, rows) => ({{ status: "ok", session_id: window.__mockSessionId }}),
                        terminal_close: async (sessionId) => true
                    }}
                }};
            """)

            # Load app over real HTTP
            page.goto(f"http://127.0.0.1:{srv.port}/")

            # 1. Header buttons exist and are visible (refresh and collapse; new file/folder are inline folder actions)
            page.wait_for_selector("#btnRefreshTree", timeout=5000)
            self.assertTrue(page.locator("#btnRefreshTree").is_visible())
            self.assertTrue(page.locator("#btnCollapseAll").is_visible())

            # 2. Ports panel renders
            tab_ports = page.locator("#tab-ports")
            self.assertTrue(tab_ports.is_visible())
            tab_ports.click()
            page.wait_for_selector("#portsPanel", timeout=5000)
            self.assertTrue(page.locator("#portsPanel").is_visible())
            self.assertTrue(page.locator("#portsTableBody").is_visible())

            # 3. Terminal opens and echoes
            tab_terminal = page.locator("#tab-terminal")
            self.assertTrue(tab_terminal.is_visible())
            tab_terminal.click()

            page.locator("#terminalHost").click()
            page.wait_for_function(
                "() => window.DeskAITerminal && window.DeskAITerminal.sessionId !== null", timeout=5000
            )

            # Wait for shell output to initialize
            page.wait_for_function(
                """() => {
                const term = window.DeskAITerminal && window.DeskAITerminal.term;
                if (!term) return false;
                term.selectAll();
                const sel = term.getSelection();
                term.clearSelection();
                return sel && sel.length > 0;
            }""",
                timeout=5000,
            )

            # Type echo command and verify round-trip
            page.evaluate("() => { if (window.DeskAITerminal) window.DeskAITerminal.activate(); }")
            page.locator("#terminalHost").click()
            page.keyboard.type("echo DESKAI_HTTP_SMOKE_PASS\n", delay=10)
            page.wait_for_function(
                """() => {
                const term = window.DeskAITerminal && window.DeskAITerminal.term;
                if (!term) return false;
                term.selectAll();
                const sel = term.getSelection();
                term.clearSelection();
                return sel && sel.includes("DESKAI_HTTP_SMOKE_PASS");
            }""",
                timeout=15000,
            )

            context.close()
        finally:
            srv.stop()


if __name__ == "__main__":
    unittest.main()
