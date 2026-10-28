import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


class TestNativeWindowButtons(unittest.TestCase):
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
        self.page.wait_for_selector("#appHeader")
        self.page.wait_for_function("typeof window.NativeBridge !== 'undefined'")

        # Mock NativeBridge.windowControl spy
        self.page.evaluate("""() => {
            window.__mockWindowControlCalls = [];
            window.__mockSetDirtyCalls = [];
            window.NativeBridge.windowControl = async (action) => {
                window.__mockWindowControlCalls.push(action);
                if (action === "close_request") {
                    const hasRunningTerminal = !!(window.DeskAITerminal && window.DeskAITerminal.sessionId);
                    const isDirty = !!(
                        window.store &&
                        window.store.state &&
                        window.store.state.dirtyTabs &&
                        window.store.state.dirtyTabs.size > 0
                    );
                    return !(hasRunningTerminal || isDirty);
                }
                return true;
            };
            window.NativeBridge.setDirtyStatus = async (status) => {
                window.__mockSetDirtyCalls.push(status);
                return true;
            };
        }""")

    def tearDown(self):
        if hasattr(self, "page"):
            self.page.close()
        if hasattr(self, "context"):
            self.context.close()

    def test_nwb_01_markup_and_aria_attributes(self):
        """TC-NWB-01: Verifies .window-controls container and button semantics, ARIA roles, and labels."""
        controls = self.page.locator(".window-controls")
        self.assertTrue(controls.is_visible())
        self.assertEqual(controls.get_attribute("role"), "group")
        self.assertEqual(controls.get_attribute("aria-label"), "Window Controls")

        min_btn = self.page.locator('.win-btn[data-action="win-minimize"]')
        max_btn = self.page.locator('.win-btn[data-action="win-maximize"]')
        close_btn = self.page.locator('.win-btn[data-action="win-close"]')

        self.assertTrue(min_btn.is_visible())
        self.assertTrue(max_btn.is_visible())
        self.assertTrue(close_btn.is_visible())

        self.assertEqual(min_btn.get_attribute("aria-label"), "Minimize Window")
        self.assertEqual(max_btn.get_attribute("aria-label"), "Maximize Window")
        self.assertEqual(close_btn.get_attribute("aria-label"), "Close Window")

    def test_nwb_02_minimize_dispatches_bridge(self):
        """TC-NWB-02: Verifies clicking minimize button calls NativeBridge.windowControl('minimize')."""
        self.page.click('.win-btn[data-action="win-minimize"]')
        calls = self.page.evaluate("() => window.__mockWindowControlCalls")
        self.assertIn("minimize", calls)

    def test_nwb_03_maximize_dispatches_bridge(self):
        """TC-NWB-03: Verifies clicking maximize button calls NativeBridge.windowControl('maximize')."""
        self.page.click('.win-btn[data-action="win-maximize"]')
        calls = self.page.evaluate("() => window.__mockWindowControlCalls")
        self.assertIn("maximize", calls)

    def test_nwb_04_close_unguarded_when_clean(self):
        """TC-NWB-04: When no dirty tabs and no active terminal, close proceeds without opening confirm modal."""
        self.page.evaluate("""() => {
            if (window.store && window.store.state) {
                window.store.state.dirtyTabs = new Set();
            }
            if (window.DeskAITerminal) {
                window.DeskAITerminal.sessionId = null;
            }
        }""")

        self.page.click('.win-btn[data-action="win-close"]')

        # Confirm modal should not be opened
        modal_open = self.page.evaluate("""() => {
            const modal = document.getElementById("confirmModal");
            return modal && modal.open;
        }""")
        self.assertFalse(modal_open)

        calls = self.page.evaluate("() => window.__mockWindowControlCalls")
        self.assertIn("close_request", calls)

    def test_nwb_05_close_guarded_when_tabs_dirty(self):
        """TC-NWB-05: When open editor tabs are dirty, clicking close opens confirm modal with dirty tabs message."""
        self.page.evaluate("""() => {
            if (window.store && window.store.state) {
                window.store.state.dirtyTabs = new Set(["/workspace/test.py"]);
            }
            if (window.DeskAITerminal) {
                window.DeskAITerminal.sessionId = null;
            }
        }""")

        self.page.click('.win-btn[data-action="win-close"]')

        modal_open = self.page.evaluate("""() => {
            const modal = document.getElementById("confirmModal");
            return modal && modal.open;
        }""")
        self.assertTrue(modal_open)

        title = self.page.text_content("#confirmModalTitle")
        desc = self.page.text_content("#confirmModalDesc")
        self.assertEqual(title, "Confirm Exit")
        self.assertIn("unsaved changes", desc)
        self.assertNotIn("terminal", desc.lower())

    def test_nwb_06_close_guarded_when_terminal_active(self):
        """TC-NWB-06: When terminal is running, clicking close opens confirm modal with terminal message."""
        self.page.evaluate("""() => {
            if (window.store && window.store.state) {
                window.store.state.dirtyTabs = new Set();
            }
            if (window.DeskAITerminal) {
                window.DeskAITerminal.sessionId = "mock_term_sess_123";
            }
        }""")

        self.page.click('.win-btn[data-action="win-close"]')

        modal_open = self.page.evaluate("""() => {
            const modal = document.getElementById("confirmModal");
            return modal && modal.open;
        }""")
        self.assertTrue(modal_open)

        desc = self.page.text_content("#confirmModalDesc")
        self.assertIn("active terminal session", desc)
        self.assertNotIn("unsaved changes", desc)

    def test_nwb_07_close_guarded_when_both_dirty_and_terminal_active(self):
        """TC-NWB-07: When both dirty tabs and terminal are active, confirm modal describes both."""
        self.page.evaluate("""() => {
            if (window.store && window.store.state) {
                window.store.state.dirtyTabs = new Set(["/workspace/main.py"]);
            }
            if (window.DeskAITerminal) {
                window.DeskAITerminal.sessionId = "mock_term_sess_456";
            }
        }""")

        self.page.click('.win-btn[data-action="win-close"]')

        modal_open = self.page.evaluate("""() => {
            const modal = document.getElementById("confirmModal");
            return modal && modal.open;
        }""")
        self.assertTrue(modal_open)

        desc = self.page.text_content("#confirmModalDesc")
        self.assertIn("unsaved changes", desc)
        self.assertIn("active terminal", desc)

    def test_nwb_08_cancel_exit_flow(self):
        """TC-NWB-08: Clicking cancel inside confirm modal closes modal and keeps window open."""
        self.page.evaluate("""() => {
            if (window.store && window.store.state) {
                window.store.state.dirtyTabs = new Set(["/workspace/main.py"]);
            }
        }""")

        self.page.click('.win-btn[data-action="win-close"]')
        self.page.wait_for_selector("#confirmModal[open]")

        # Click Cancel
        self.page.click('#confirmModal button[data-action="cancel-exit"]')

        modal_open = self.page.evaluate("""() => {
            const modal = document.getElementById("confirmModal");
            return modal && modal.open;
        }""")
        self.assertFalse(modal_open)

        calls = self.page.evaluate("() => window.__mockWindowControlCalls")
        self.assertNotIn("close", calls)

    def test_nwb_09_confirm_exit_flow(self):
        """TC-NWB-09: Clicking confirm exit destroys terminal, resets dirty status, and calls close."""
        self.page.evaluate("""() => {
            window.__mockTerminalDestroyed = false;
            if (window.store && window.store.state) {
                window.store.state.dirtyTabs = new Set(["/workspace/main.py"]);
            }
            if (window.DeskAITerminal) {
                window.DeskAITerminal.sessionId = "active_session";
                window.DeskAITerminal.destroy = () => {
                    window.__mockTerminalDestroyed = true;
                };
            }
        }""")

        self.page.click('.win-btn[data-action="win-close"]')
        self.page.wait_for_selector("#confirmModal[open]")

        # Click Confirm Exit
        self.page.click('#confirmModal button[data-action="confirm-exit"]')

        modal_open = self.page.evaluate("""() => {
            const modal = document.getElementById("confirmModal");
            return modal && modal.open;
        }""")
        self.assertFalse(modal_open)

        term_destroyed = self.page.evaluate("() => window.__mockTerminalDestroyed")
        self.assertTrue(term_destroyed)

        dirty_calls = self.page.evaluate("() => window.__mockSetDirtyCalls")
        self.assertIn(False, dirty_calls)

        calls = self.page.evaluate("() => window.__mockWindowControlCalls")
        self.assertIn("close", calls)


if __name__ == "__main__":
    unittest.main()
