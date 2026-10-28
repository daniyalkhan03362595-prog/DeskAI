import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


class TestTerminalInlineAuth(unittest.TestCase):
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
        self.context = self.browser.new_context()
        self.page = self.context.new_page()

        # Mock pywebview bridge
        self.page.add_init_script("""
            window.__openCallLog = [];
            window.pywebview = {
                api: {
                    terminal_open: async (cols, rows, confirmed, inlineAuth) => {
                        window.__openCallLog.push({ cols, rows, confirmed, inlineAuth });
                        if (!confirmed && inlineAuth) {
                            return { status: "auth_required", workspace: "DeskAI" };
                        }
                        return { status: "ok", session_id: "mock-session-123" };
                    },
                    terminal_close: async (sessionId) => true
                }
            };
        """)
        self.page.goto(f"file://{index_file}")
        self.page.wait_for_selector("#terminalHost")

    def tearDown(self):
        if hasattr(self, "page"):
            self.page.close()
        if hasattr(self, "context"):
            self.context.close()

    def test_terminal_inline_auth_banner_displayed_on_click(self):
        """Clicking on terminal triggers inline auth banner with confirm and cancel buttons."""
        host = self.page.locator("#terminalHost")
        host.click()

        banner = self.page.locator("#terminalAuthBanner")
        self.assertTrue(banner.is_visible())
        self.assertEqual(banner.get_attribute("role"), "alertdialog")
        self.assertIn("DeskAI", banner.locator(".terminal-auth-text").text_content())

        confirm_btn = self.page.locator(".terminal-auth-confirm")
        cancel_btn = self.page.locator(".terminal-auth-cancel")
        self.assertTrue(confirm_btn.is_visible())
        self.assertTrue(cancel_btn.is_visible())
        self.assertEqual(confirm_btn.get_attribute("aria-label"), "Authorize host shell")
        self.assertEqual(cancel_btn.get_attribute("aria-label"), "Cancel authorization")

    def test_terminal_inline_auth_cancel_button(self):
        """Clicking the Red Cross (Cancel) removes prompt and cancels authorization."""
        host = self.page.locator("#terminalHost")
        host.click()

        cancel_btn = self.page.locator(".terminal-auth-cancel")
        self.assertTrue(cancel_btn.is_visible())
        cancel_btn.click()

        # Banner should be removed
        banner = self.page.locator("#terminalAuthBanner")
        self.assertEqual(banner.count(), 0)

        # Terminal writes cancellation notice to xterm buffer
        self.page.wait_for_function(
            """() => {
            const term = window.DeskAITerminal && window.DeskAITerminal.term;
            if (!term) return false;
            term.selectAll();
            const sel = term.getSelection();
            term.clearSelection();
            return sel && sel.includes("Terminal authorization cancelled");
        }""",
            timeout=5000,
        )

    def test_terminal_inline_auth_confirm_button(self):
        """Clicking the Green Tick (Confirm) authorizes and spawns session."""
        host = self.page.locator("#terminalHost")
        host.click()

        confirm_btn = self.page.locator(".terminal-auth-confirm")
        self.assertTrue(confirm_btn.is_visible())
        confirm_btn.click()

        # Banner should be removed
        banner = self.page.locator("#terminalAuthBanner")
        self.assertEqual(banner.count(), 0)

        # Verify bridge called with confirmed=True
        log = self.page.evaluate("() => window.__openCallLog")
        self.assertEqual(len(log), 2)
        self.assertFalse(log[0]["confirmed"])
        self.assertTrue(log[1]["confirmed"])

    def test_terminal_inline_auth_keyboard_navigation(self):
        """Escape cancels authorization and Enter confirms authorization."""
        host = self.page.locator("#terminalHost")
        host.click()

        # Escape should cancel
        self.page.keyboard.press("Escape")
        banner = self.page.locator("#terminalAuthBanner")
        self.assertEqual(banner.count(), 0)

        # Re-trigger and test Enter confirms
        host.click()
        banner = self.page.locator("#terminalAuthBanner")
        self.assertTrue(banner.is_visible())

        self.page.keyboard.press("Enter")
        self.assertEqual(banner.count(), 0)

        log = self.page.evaluate("() => window.__openCallLog")
        # First attempt: unconfirmed (index 0), Second attempt: unconfirmed (index 1), confirmed (index 2)
        self.assertTrue(log[-1]["confirmed"])

    def test_terminal_inline_auth_tab_focus_cycle(self):
        """Tab and Shift+Tab cycle focus between confirm and cancel buttons."""
        host = self.page.locator("#terminalHost")
        host.click()

        confirm_btn = self.page.locator(".terminal-auth-confirm")
        cancel_btn = self.page.locator(".terminal-auth-cancel")

        # Confirm button receives initial focus
        self.assertEqual(
            self.page.evaluate("() => document.activeElement.className"), confirm_btn.get_attribute("class")
        )

        # Tab moves to Cancel
        self.page.keyboard.press("Tab")
        self.assertEqual(
            self.page.evaluate("() => document.activeElement.className"), cancel_btn.get_attribute("class")
        )

        # Tab cycles back to Confirm
        self.page.keyboard.press("Tab")
        self.assertEqual(
            self.page.evaluate("() => document.activeElement.className"), confirm_btn.get_attribute("class")
        )

        # Shift+Tab cycles to Cancel
        self.page.keyboard.press("Shift+Tab")
        self.assertEqual(
            self.page.evaluate("() => document.activeElement.className"), cancel_btn.get_attribute("class")
        )


if __name__ == "__main__":
    unittest.main()
