"""E2E Playwright test for Phase 2: 'Fix with AI' and 'Explain' buttons on problems."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False

from deskai.bridge.api import DesktopBridgeAPI
from deskai.server.supervisor import DesktopServer


class TestProblemsAiActions(unittest.TestCase):
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

        cls.temp_workspace = Path(tempfile.mkdtemp()).resolve()
        cls.server = DesktopServer()
        cls.server.start()

        import httpx

        token = cls.server.security.create_launch_token()
        with httpx.Client(follow_redirects=False) as http:
            res = http.get(
                f"http://127.0.0.1:{cls.server.port}/auth/redeem?token={token}",
                headers={"Host": f"127.0.0.1:{cls.server.port}"},
            )
            cls.cookie_val = res.cookies.get("deskai_session")

        cls.mock_mgr = MagicMock()
        cls.mock_mgr.window.get_current_url.return_value = f"http://127.0.0.1:{cls.server.port}/"
        cls.mock_mgr.server.port = cls.server.port
        cls.api = DesktopBridgeAPI(cls.mock_mgr)
        cls.api.set_workspace_root(str(cls.temp_workspace))

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "server"):
            cls.server.stop()
        if hasattr(cls, "browser"):
            cls.browser.close()
        if hasattr(cls, "p"):
            cls.p.stop()
        if hasattr(cls, "temp_workspace") and cls.temp_workspace.exists():
            shutil.rmtree(cls.temp_workspace, ignore_errors=True)

    def _create_page(self):
        context = self.browser.new_context(viewport={"width": 1280, "height": 800})
        context.add_cookies([{"name": "deskai_session", "value": self.cookie_val, "domain": "127.0.0.1", "path": "/"}])
        page = context.new_page()

        page.expose_function("__bridge_run_diagnostics", lambda p, req="": self.api.run_diagnostics(p, req))
        page.expose_function(
            "__bridge_run_workspace_diagnostics", lambda req="": self.api.run_workspace_diagnostics(req)
        )
        page.expose_function("__bridge_write_file", lambda p, c: self.api.write_file(p, c))
        page.expose_function("__bridge_read_file", lambda p: self.api.read_file(p))
        page.expose_function("__bridge_set_workspace_root", lambda p: self.api.set_workspace_root(p))
        page.expose_function("__bridge_get_workspace_root", lambda: self.api.get_workspace_root())

        page.add_init_script("""
            window.pywebview = {
                api: {
                    run_diagnostics: async (path, reqId) => await window.__bridge_run_diagnostics(path, reqId),
                    run_workspace_diagnostics: async (reqId) => await window.__bridge_run_workspace_diagnostics(reqId),
                    write_file: async (path, content) => await window.__bridge_write_file(path, content),
                    read_file: async (path) => await window.__bridge_read_file(path),
                    set_workspace_root: async (path) => await window.__bridge_set_workspace_root(path),
                    get_workspace_root: async () => await window.__bridge_get_workspace_root(),
                }
            };
        """)
        page.goto(f"http://127.0.0.1:{self.server.port}/")
        page.wait_for_selector("#welcomePrimaryBtn", timeout=5000)
        return context, page

    def test_fix_with_ai_and_explain_buttons(self):
        """Hovering or inspecting a problem row shows 'Fix' and 'Explain' buttons which populate AI prompts."""
        context, page = self._create_page()
        try:
            broken = self.temp_workspace / "ai_test.py"
            broken.write_text("def broken(:\n    pass\n", encoding="utf-8")

            page.locator("#tab-problems").click()
            page.evaluate(f'window.DeskAIProblems.onFileSaved("{broken.as_posix()}");')
            page.wait_for_selector(".problem-item", timeout=3000)

            # Check action buttons exist
            fix_btn = page.locator(".problem-btn-ai-fix")
            explain_btn = page.locator(".problem-btn-explain")
            self.assertEqual(fix_btn.count(), 1, "Fix with AI button must exist")
            self.assertEqual(explain_btn.count(), 1, "Explain button must exist")

            # Click Fix button
            fix_btn.click()
            ta_val = page.locator("#promptTextarea").input_value()
            self.assertIn("Fix the following", ta_val)
            self.assertIn("ai_test.py", ta_val)

            # Click Explain button
            explain_btn.click()
            ta_val_explain = page.locator("#promptTextarea").input_value()
            self.assertIn("Explain why this error occurred", ta_val_explain)
            self.assertIn("ai_test.py", ta_val_explain)
        finally:
            context.close()


if __name__ == "__main__":
    unittest.main()
