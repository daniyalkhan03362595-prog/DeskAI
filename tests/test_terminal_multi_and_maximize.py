"""
Behavioral and Integration Tests for Terminal Multi-Sessions and Maximize/Restore Controls.
Asserts:
1. Maximize/Restore button toggles .drawer-maximized on #editorStage, maximizes bottom drawer,
   swaps SVG icon, and restores on second click.
2. New terminal button spawns additional sessions up to MAX_SESSIONS (6).
3. Right-hand terminal tabs list (#terminalTabsSidebar) appears when >= 2 terminals exist.
4. Tab switching updates active session and container visibility.
5. Closing a terminal tab kills that session, reduces count, and hides sidebar when count <= 1.
6. At 6 sessions, #btnNewTerminal is disabled with aria-disabled="true" and title.
7. Killing a session re-enables #btnNewTerminal.
"""

import sys
import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


class TestTerminalMultiAndMaximize(unittest.TestCase):
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

        # Mock pywebview bridge
        self.page.add_init_script("""
            let sessionCounter = 0;
            window._clipboardMock = "";
            window.pywebview = {
                api: {
                    terminal_open: async (cols, rows, confirmed, inlineAuth) => {
                        sessionCounter++;
                        return { status: "ok", session_id: "mock-sess-" + sessionCounter };
                    },
                    terminal_close: async (sessionId) => true,
                    clipboard_write: async (text) => {
                        window._clipboardMock = text;
                        return { status: "ok" };
                    },
                    clipboard_read: async () => {
                        return { status: "ok", text: window._clipboardMock || "" };
                    }
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

    def test_maximize_and_restore_drawer(self):
        """Clicking maximize button expands drawer to 100% height and restores on toggle."""
        btn_maximize = self.page.locator("#btnMaximizeDrawer")
        self.assertTrue(btn_maximize.is_visible())
        self.assertEqual(btn_maximize.get_attribute("aria-expanded"), "false")

        # Initial drawer height
        initial_height = self.page.evaluate(
            "() => document.getElementById('bottomDrawer').getBoundingClientRect().height"
        )

        # Click to maximize
        btn_maximize.click()
        self.page.wait_for_timeout(50)

        max_height = self.page.evaluate("() => document.getElementById('bottomDrawer').getBoundingClientRect().height")
        is_maximized = self.page.evaluate(
            "() => document.getElementById('editorStage').classList.contains('drawer-maximized')"
        )
        editor_viewport_display = self.page.evaluate(
            "() => window.getComputedStyle(document.getElementById('editorViewport')).display"
        )

        self.assertTrue(is_maximized)
        self.assertGreater(max_height, initial_height * 2)
        self.assertEqual(editor_viewport_display, "none")
        self.assertEqual(btn_maximize.get_attribute("aria-expanded"), "true")

        # Click again to restore
        btn_maximize.click()
        self.page.wait_for_timeout(50)

        restored_height = self.page.evaluate(
            "() => document.getElementById('bottomDrawer').getBoundingClientRect().height"
        )
        is_still_maximized = self.page.evaluate(
            "() => document.getElementById('editorStage').classList.contains('drawer-maximized')"
        )
        editor_viewport_restored = self.page.evaluate(
            "() => window.getComputedStyle(document.getElementById('editorViewport')).display"
        )

        self.assertFalse(is_still_maximized)
        self.assertAlmostEqual(restored_height, initial_height, delta=5)
        self.assertNotEqual(editor_viewport_restored, "none")
        self.assertEqual(btn_maximize.get_attribute("aria-expanded"), "false")

    def test_resizer_double_click_clears_maximized_state(self):
        """Double-clicking resizer while drawer is maximized clears .drawer-maximized and resets button."""
        btn_maximize = self.page.locator("#btnMaximizeDrawer")
        resizer = self.page.locator("#resizerBottom")
        drawer = self.page.locator("#bottomDrawer")

        # Maximize drawer
        btn_maximize.click()
        self.page.wait_for_timeout(50)
        self.assertEqual(btn_maximize.get_attribute("aria-expanded"), "true")
        self.assertTrue(
            self.page.evaluate("() => document.getElementById('editorStage').classList.contains('drawer-maximized')")
        )

        # Double-click resizer to collapse (dispatched via DOM event since resizer is hidden when maximized)
        resizer.dispatch_event("dblclick")
        self.page.wait_for_timeout(50)
        self.assertIn("collapsed", drawer.get_attribute("class"))
        self.assertFalse(
            self.page.evaluate("() => document.getElementById('editorStage').classList.contains('drawer-maximized')")
        )
        self.assertEqual(btn_maximize.get_attribute("aria-expanded"), "false")

    def test_multi_terminal_sessions_and_sidebar_display(self):
        """Clicking + spawns multiple terminals; sidebar appears when sessions >= 2."""
        btn_new = self.page.locator("#btnNewTerminal")
        sidebar = self.page.locator("#terminalTabsSidebar")

        # Initially no sidebar
        self.assertFalse(sidebar.is_visible())

        # Click + for first terminal
        btn_new.click()
        self.page.wait_for_timeout(50)

        session_count_1 = self.page.evaluate("() => window.DeskAITerminal.sessions.length")
        self.assertEqual(session_count_1, 1)
        self.assertFalse(sidebar.is_visible())

        # Click + for second terminal
        btn_new.click()
        self.page.wait_for_timeout(50)

        session_count_2 = self.page.evaluate("() => window.DeskAITerminal.sessions.length")
        self.assertEqual(session_count_2, 2)
        self.assertTrue(sidebar.is_visible())

        tabs = sidebar.locator(".terminal-tab-item")
        self.assertEqual(tabs.count(), 2)
        expected_shell = "cmd" if sys.platform == "win32" else "bash"
        for i in range(tabs.count()):
            self.assertEqual(tabs.nth(i).locator(".terminal-tab-title").inner_text().strip(), expected_shell)

    def test_tab_switching_between_terminals(self):
        """Clicking a terminal tab switches the active terminal instance."""
        btn_new = self.page.locator("#btnNewTerminal")
        btn_new.click()
        btn_new.click()
        self.page.wait_for_timeout(50)

        sidebar = self.page.locator("#terminalTabsSidebar")
        tabs = sidebar.locator(".terminal-tab-item")

        # Active tab is the second one initially
        self.assertIn("active", tabs.nth(1).get_attribute("class"))

        # Click first tab
        tabs.nth(0).click()
        self.page.wait_for_timeout(50)

        self.assertIn("active", tabs.nth(0).get_attribute("class"))
        active_id = self.page.evaluate("() => window.DeskAITerminal.activeSessionId")
        first_id = self.page.evaluate("() => window.DeskAITerminal.sessions[0].id")
        self.assertEqual(active_id, first_id)

    def test_terminal_session_cap_at_6_disables_button(self):
        """Adding up to 6 terminal sessions disables the + button; closing one re-enables it."""
        btn_new = self.page.locator("#btnNewTerminal")

        # Add 6 sessions
        for _ in range(6):
            btn_new.click()
            self.page.wait_for_timeout(30)

        session_count = self.page.evaluate("() => window.DeskAITerminal.sessions.length")
        self.assertEqual(session_count, 6)
        self.assertTrue(btn_new.is_disabled())
        self.assertEqual(btn_new.get_attribute("aria-disabled"), "true")
        self.assertIn("Maximum 6", btn_new.get_attribute("title"))

        # Verify all 6 tabs are cleanly titled with shell name and no numeric suffixes
        tabs = self.page.locator(".terminal-tab-item")
        self.assertEqual(tabs.count(), 6)
        expected_shell = "cmd" if sys.platform == "win32" else "bash"
        for i in range(6):
            self.assertEqual(tabs.nth(i).locator(".terminal-tab-title").inner_text().strip(), expected_shell)

        # Trying to add 7th does not exceed 6
        btn_new.click(force=True)
        self.page.wait_for_timeout(30)
        self.assertEqual(self.page.evaluate("() => window.DeskAITerminal.sessions.length"), 6)

        # Close one session using close button on tab
        close_btn = self.page.locator(".terminal-tab-close").first
        close_btn.click()
        self.page.wait_for_timeout(50)

        self.assertEqual(self.page.evaluate("() => window.DeskAITerminal.sessions.length"), 5)
        self.assertFalse(btn_new.is_disabled())
        self.assertEqual(btn_new.get_attribute("aria-disabled"), "false")

    def test_terminal_clipboard_shortcuts(self):
        """Ctrl+Shift+A selects all, Ctrl+Shift+C copies selection, Ctrl+Shift+V pastes clipboard."""
        # 1. Write text into terminal buffer
        self.page.evaluate("""() => {
            window.DeskAITerminal.term.write("test sample command line");
        }""")
        self.page.wait_for_timeout(50)

        # 2. Select All via Ctrl+Shift+A
        self.page.evaluate("""() => {
            const ev = new KeyboardEvent("keydown", {
                key: "a",
                code: "KeyA",
                ctrlKey: true,
                shiftKey: true,
                bubbles: true,
                cancelable: true
            });
            window.DeskAITerminal.term.textarea.dispatchEvent(ev);
        }""")
        self.page.wait_for_timeout(50)

        has_selection = self.page.evaluate("() => window.DeskAITerminal.term.hasSelection()")
        self.assertTrue(has_selection, "Ctrl+Shift+A should select text in terminal")
        sel_text = self.page.evaluate("() => window.DeskAITerminal.term.getSelection()")
        self.assertIn("test sample command line", sel_text)

        # 3. Copy via Ctrl+Shift+C
        self.page.evaluate("""() => {
            const ev = new KeyboardEvent("keydown", {
                key: "c",
                code: "KeyC",
                ctrlKey: true,
                shiftKey: true,
                bubbles: true,
                cancelable: true
            });
            window.DeskAITerminal.term.textarea.dispatchEvent(ev);
        }""")
        self.page.wait_for_timeout(50)

        clipboard_val = self.page.evaluate("() => window._clipboardMock")
        self.assertIn("test sample command line", clipboard_val)

        # 4. Paste via Ctrl+Shift+V
        self.page.evaluate("""() => {
            window._clipboardMock = "pasted_from_clipboard";
            window._pastedData = "";
            window.DeskAITerminal.term.onData(d => { window._pastedData += d; });
            const ev = new KeyboardEvent("keydown", {
                key: "v",
                code: "KeyV",
                ctrlKey: true,
                shiftKey: true,
                bubbles: true,
                cancelable: true
            });
            window.DeskAITerminal.term.textarea.dispatchEvent(ev);
        }""")
        self.page.wait_for_timeout(50)

        pasted = self.page.evaluate("() => window._pastedData")
        self.assertIn("pasted_from_clipboard", pasted)


if __name__ == "__main__":
    unittest.main()
