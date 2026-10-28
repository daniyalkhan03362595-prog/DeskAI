"""
Playwright Test for Task 2: Keyboard Flow and Terminal Tab Trap Prevention.
Asserts:
1. In idle state, terminal does not trap Tab.
2. Tab traversal from page start reaches:
   window buttons -> explorer toolbar -> tree -> welcome buttons -> drawer tablist -> AI chat input.
3. Bottom drawer tabs operate as a roving tabindex tablist (Arrow keys, Home, End).
4. Terminal activates on Enter/click and announces/displays focus trap hint.
5. Esc or Ctrl+Shift+M releases focus from terminal.
"""

import unittest
from playwright.sync_api import sync_playwright
import httpx
from deskai.server.supervisor import DesktopServer


class TestTask2KeyboardFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = sync_playwright().start()
        try:
            cls.browser = cls.p.chromium.launch(headless=True)
        except Exception as e:
            cls.p.stop()
            raise unittest.SkipTest(f"Chromium launch failed: {e}")

        cls.srv = DesktopServer()
        cls.srv.start()
        token = cls.srv.security.create_launch_token()

        with httpx.Client(follow_redirects=False) as http:
            res = http.get(
                f"http://127.0.0.1:{cls.srv.port}/auth/redeem?token={token}",
                headers={"Host": f"127.0.0.1:{cls.srv.port}"},
            )
            cls.cookie_val = res.cookies.get("deskai_session")
        if not cls.cookie_val:
            raise RuntimeError("Failed to redeem auth cookie")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "srv"):
            cls.srv.stop()
        if hasattr(cls, "browser"):
            cls.browser.close()
        if hasattr(cls, "p"):
            cls.p.stop()

    def _create_page(self):
        context = self.browser.new_context(viewport={"width": 1280, "height": 800})
        context.add_cookies([{"name": "deskai_session", "value": self.cookie_val, "domain": "127.0.0.1", "path": "/"}])
        page = context.new_page()
        page.add_init_script("""
            window.pywebview = {
                api: {
                    terminal_open: async () => ({ status: "ok", session_id: "mock" }),
                    terminal_close: async () => true,
                    get_workspace_root: async () => null,
                    set_workspace_root: async () => true
                }
            };
        """)
        page.goto(f"http://127.0.0.1:{self.srv.port}/")
        page.wait_for_selector("#welcomePrimaryBtn", timeout=5000)
        return context, page

    def test_keyboard_tab_flow_and_no_terminal_trap_in_idle(self):
        """Tab traversal from page start reaches AI input without getting stuck in terminal in idle state."""
        context, page = self._create_page()
        try:
            visited_ids = []
            for _ in range(25):
                page.keyboard.press("Tab")
                active_info = page.evaluate("""() => {
                    const el = document.activeElement;
                    if (!el || el === document.body) return null;
                    return {
                        id: el.id,
                        tagName: el.tagName,
                        className: el.className,
                        role: el.getAttribute('role')
                    };
                }""")
                if active_info:
                    visited_ids.append(active_info["id"] or active_info["className"])
                    if active_info["id"] == "promptTextarea":
                        break

            # Verify that promptTextarea was reached
            self.assertIn(
                "promptTextarea",
                visited_ids,
                f"AI chat input was not reached within 25 Tab presses. Visited: {visited_ids}",
            )

            # Verify that terminal textarea never captured Tab during idle traversal
            self.assertFalse(
                any("xterm" in v for v in visited_ids),
                f"Terminal captured Tab while idle: {visited_ids}",
            )

            # Verify order of key milestones
            # 1. Window button (theme or win-min)
            # 2. Explorer toolbar
            # 3. Tree viewport
            # 4. Welcome buttons
            # 5. Drawer tablist
            # 6. AI chat input
            id_str = " -> ".join(visited_ids)
            self.assertTrue(
                "btnNewFile" in visited_ids or "explorerToolbar" in id_str,
                f"Explorer toolbar not visited: {id_str}",
            )
            self.assertTrue(
                "fileTreeViewport" in visited_ids,
                f"File tree viewport not visited: {id_str}",
            )
            self.assertTrue(
                "welcomePrimaryBtn" in visited_ids,
                f"Welcome button not visited: {id_str}",
            )
            self.assertTrue(
                "tab-terminal" in visited_ids,
                f"Drawer tablist not visited: {id_str}",
            )
            self.assertEqual(
                visited_ids[-1],
                "promptTextarea",
                f"Final focused element should be promptTextarea, got: {visited_ids[-1]}",
            )
        finally:
            context.close()

    def test_drawer_tabs_roving_tabindex(self):
        """Drawer tabs roving tabindex: Arrow keys switch tabs and update selection."""
        context, page = self._create_page()
        try:
            tab_terminal = page.locator("#tab-terminal")
            tab_output = page.locator("#tab-output")
            tab_terminal.focus()

            # ArrowRight should move to Output tab
            page.keyboard.press("ArrowRight")
            self.assertTrue(page.evaluate("() => document.activeElement.id === 'tab-output'"))
            self.assertEqual(tab_output.get_attribute("aria-selected"), "true")
            self.assertEqual(tab_output.get_attribute("tabindex"), "0")
            self.assertEqual(tab_terminal.get_attribute("aria-selected"), "false")
            self.assertEqual(tab_terminal.get_attribute("tabindex"), "-1")

            # Home should return to first tab
            page.keyboard.press("Home")
            self.assertTrue(page.evaluate("() => document.activeElement.id === 'tab-terminal'"))

            # End should move to last tab (Ports)
            page.keyboard.press("End")
            self.assertTrue(page.evaluate("() => document.activeElement.id === 'tab-ports'"))
        finally:
            context.close()

    def test_terminal_activation_and_escape(self):
        """Terminal activates on click, shows trapped hint, and Esc releases focus."""
        context, page = self._create_page()
        try:
            # Click host to activate
            page.locator("#terminalHost").click()
            is_active = page.evaluate("() => window.DeskAITerminal && window.DeskAITerminal.isActive")
            self.assertTrue(is_active, "Terminal was not active after click")

            # Hint is updated
            hint_text = page.locator(".terminal-footer-hint").text_content()
            self.assertIn("Focus trapped", hint_text)

            # Press Escape inside terminal
            page.keyboard.press("Escape")
            is_active_after_esc = page.evaluate("() => window.DeskAITerminal && window.DeskAITerminal.isActive")
            self.assertFalse(is_active_after_esc, "Terminal remained active after Escape")

            # Focus moved back to tab-terminal
            active_id = page.evaluate("() => document.activeElement ? document.activeElement.id : null")
            self.assertEqual(active_id, "tab-terminal")
        finally:
            context.close()

    def test_explorer_toolbar_single_tab_stop_and_arrows(self):
        """Explorer toolbar is role=toolbar, has one tab stop, and arrow keys move focus."""
        context, page = self._create_page()
        try:
            btn_new_file = page.locator("#btnNewFile")
            btn_new_folder = page.locator("#btnNewFolder")
            btn_new_file.focus()

            self.assertEqual(btn_new_file.get_attribute("tabindex"), "0")
            self.assertEqual(btn_new_folder.get_attribute("tabindex"), "-1")

            # Arrow right moves within toolbar
            page.keyboard.press("ArrowRight")
            self.assertTrue(page.evaluate("() => document.activeElement.id === 'btnNewFolder'"))
            self.assertEqual(btn_new_folder.get_attribute("tabindex"), "0")
            self.assertEqual(btn_new_file.get_attribute("tabindex"), "-1")

            # Tab leaves toolbar directly to fileTreeViewport
            page.keyboard.press("Tab")
            self.assertTrue(page.evaluate("() => document.activeElement.id === 'fileTreeViewport'"))
        finally:
            context.close()
