"""
Playwright and DOM Audit Test for Task 3:
1. Every visible interactive element has a hit area >= 28x28px.
2. Every computed font-size is at least 12px (>= 12px).
3. Font inheritance ensures no interactive element resolves to Arial.
4. Zero emoji characters in static/index.html and rendered Explorer toolbar.
"""

import re
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright
import httpx
from deskai.server.supervisor import DesktopServer


class TestTask3TypographyTargetsIcons(unittest.TestCase):
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

    def test_zero_emojis_in_index_html(self):
        """static/index.html must not contain any emoji characters."""
        index_path = Path("src/deskai/static/index.html")
        text = index_path.read_text(encoding="utf-8")
        emoji_pattern = re.compile(
            r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\u2300-\u23ff]|[\u2b50-\u2b55]|[\u203c-\u2049]"
        )
        matches = emoji_pattern.findall(text)
        self.assertEqual(matches, [], f"Found emoji characters in index.html: {set(matches)}")

    def test_zero_emojis_in_rendered_toolbar(self):
        """Rendered Explorer toolbar must use inline SVGs, not emojis."""
        context, page = self._create_page()
        try:
            toolbar_text = page.locator("#explorerToolbar").text_content()
            emoji_pattern = re.compile(
                r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\u2300-\u23ff]|[\u2b50-\u2b55]|[\u203c-\u2049]"
            )
            matches = emoji_pattern.findall(toolbar_text)
            self.assertEqual(matches, [], f"Found emojis in rendered toolbar: {matches}")
        finally:
            context.close()

    def test_interactive_elements_hit_area_at_least_28px(self):
        """Every visible interactive control must have width and height >= 28px."""
        context, page = self._create_page()
        try:
            small_elements = page.evaluate("""() => {
                const results = [];
                const sel = (
                    'button, [role="button"], input, select, ' +
                    'textarea:not(.xterm-helper-textarea), summary, .icon-btn, .win-btn'
                );
                const interactives = document.querySelectorAll(sel);
                for (const el of interactives) {
                    if (el.offsetParent === null) continue; // skip hidden
                    const rect = el.getBoundingClientRect();
                    if (rect.width < 27.5 || rect.height < 27.5) {
                        results.push({
                            id: el.id,
                            className: el.className,
                            width: rect.width,
                            height: rect.height,
                            text: (el.textContent || '').trim().substring(0, 20)
                        });
                    }
                }
                return results;
            }""")
            self.assertEqual(small_elements, [], f"Interactive elements smaller than 28x28: {small_elements}")
        finally:
            context.close()

    def test_minimum_computed_font_size_12px(self):
        """Every visible element's computed font-size must be at least 12px."""
        context, page = self._create_page()
        try:
            tiny_texts = page.evaluate("""() => {
                const results = [];
                const all = document.querySelectorAll('#appRoot *');
                for (const el of all) {
                    if (el.offsetParent === null) continue; // skip hidden
                    const text = el.textContent ? el.textContent.trim() : '';
                    if (!text) continue;
                    const fs = parseFloat(window.getComputedStyle(el).fontSize);
                    if (fs < 11.5) {
                        results.push({
                            tag: el.tagName,
                            id: el.id,
                            className: el.className,
                            fontSize: fs,
                            text: text.substring(0, 25)
                        });
                    }
                }
                return results;
            }""")
            self.assertEqual(tiny_texts, [], f"Elements with font-size < 12px: {tiny_texts}")
        finally:
            context.close()

    def test_no_arial_font_inheritance(self):
        """button, input, select, textarea must inherit font-family and not resolve to Arial."""
        context, page = self._create_page()
        try:
            arial_elements = page.evaluate("""() => {
                const results = [];
                const inputs = document.querySelectorAll('button, input, select, textarea');
                for (const el of inputs) {
                    if (el.offsetParent === null) continue;
                    const ff = window.getComputedStyle(el).fontFamily.toLowerCase();
                    if (ff.startsWith('arial') || ff === 'arial') {
                        results.push({
                            id: el.id,
                            className: el.className,
                            fontFamily: ff
                        });
                    }
                }
                return results;
            }""")
            self.assertEqual(arial_elements, [], f"Form elements resolved to Arial: {arial_elements}")
        finally:
            context.close()
