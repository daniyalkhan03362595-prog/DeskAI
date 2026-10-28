"""
Playwright Test for Task 4: Empty States & Onboarding.
Asserts:
1. Explorer shows empty state with "No folder open", help text, and button with Ctrl+O.
2. AI Assistant empty state shows one-line capability note and 3 suggested prompts.
3. Tab strip empty strip is removed/hidden when no editor tabs are open.
4. Explorer empty state disappears when a workspace is loaded.
5. AI empty state disappears when a message is sent.
"""

import unittest
from playwright.sync_api import sync_playwright
import httpx
from deskai.server.supervisor import DesktopServer


class TestTask4EmptyStates(unittest.TestCase):
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

    def test_explorer_empty_state_when_no_folder(self):
        """Explorer shows centered empty state with title, help text, and button with Ctrl+O."""
        context, page = self._create_page()
        try:
            empty_msg = page.locator("#treeEmptyMessage")
            self.assertTrue(empty_msg.is_visible(), "Explorer empty state #treeEmptyMessage not visible")

            text = empty_msg.text_content()
            self.assertIn("No folder open", text)
            self.assertIn("Ctrl+O", text)

            # Check for helpful description
            desc = empty_msg.locator("p, span").all_text_contents()
            has_help = any(len(d.strip()) > 20 for d in desc)
            self.assertTrue(has_help, f"No descriptive help text found in empty state: {desc}")
        finally:
            context.close()

    def test_ai_assistant_empty_state_and_prompt_chips(self):
        """AI Assistant shows empty state with 3 prompt chips that fill the textarea without sending."""
        context, page = self._create_page()
        try:
            ai_empty = page.locator("#chatEmptyState")
            self.assertTrue(ai_empty.is_visible(), "AI Assistant empty state #chatEmptyState not visible")

            # Check 3 suggested prompt buttons
            prompt_chips = page.locator("#chatEmptyState button").all()
            self.assertEqual(len(prompt_chips), 3, f"Expected 3 prompt chips, got {len(prompt_chips)}")

            textarea = page.locator("#promptTextarea")
            self.assertEqual(textarea.input_value(), "")

            # Click first prompt chip
            first_prompt_text = prompt_chips[0].text_content().strip()
            prompt_chips[0].click()

            # Textarea should be filled, but no message should have been sent
            self.assertEqual(textarea.input_value().strip(), first_prompt_text)
            user_bubbles = page.locator("#chatThread .chat-bubble").count()
            self.assertEqual(user_bubbles, 0, "Prompt chip automatically sent message instead of just filling input")
        finally:
            context.close()

    def test_tab_strip_hidden_when_no_files_open(self):
        """When no files are open, tab strip is hidden and does not leave an empty 50px strip."""
        context, page = self._create_page()
        try:
            tab_strip_visible = page.evaluate("""() => {
                const el = document.getElementById('editorTabStrip');
                if (!el) return false;
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return style.display !== 'none' && !el.hasAttribute('hidden') && rect.height > 0;
            }""")
            self.assertFalse(tab_strip_visible, "Tab strip remains visible with no tabs open")
        finally:
            context.close()

    def test_empty_states_disappear_when_workspace_or_message_exists(self):
        """Empty states disappear when workspace is loaded and when a chat message is sent."""
        context, page = self._create_page()
        try:
            # 1. Simulate workspace folder loaded
            page.evaluate("""() => {
                if (window.ExplorerManager) {
                    window.ExplorerManager.entries = [{ name: "main.py", path: "/test/main.py", is_dir: false }];
                    window.ExplorerManager.render();
                }
            }""")
            empty_msg = page.locator("#treeEmptyMessage")
            self.assertFalse(empty_msg.is_visible(), "Explorer empty state still visible after loading entries")

            # 2. Send chat prompt
            page.fill("#promptTextarea", "Hello AI")
            page.click("#promptSendBtn")

            # Chat empty state should disappear
            chat_empty = page.locator("#chatEmptyState")
            self.assertFalse(chat_empty.is_visible(), "Chat empty state still visible after sending message")
        finally:
            context.close()
