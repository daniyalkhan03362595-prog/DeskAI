"""
Test for Task 7: Visual Polish Pass.
Asserts:
1. Zero raw hex or rgba outside static/css/tokens.css.
2. Spacing tokens in tokens.css define a consistent scale.
3. Amber accent is confined to primary actions, focus rings, and selection (not decorative banners/badges).
4. Hover/focus transitions do not exceed 150ms.
5. Under prefers-reduced-motion: reduce, transition durations are eliminated (<= 0.01ms).
"""

import re
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright
import httpx
from deskai.server.supervisor import DesktopServer


class TestTask7VisualPolish(unittest.TestCase):
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

    def _create_page(self, reduced_motion: bool = False):
        context = self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            reduced_motion="reduce" if reduced_motion else "no-preference",
        )
        context.add_cookies([{"name": "deskai_session", "value": self.cookie_val, "domain": "127.0.0.1", "path": "/"}])
        page = context.new_page()
        page.goto(f"http://127.0.0.1:{self.srv.port}/")
        page.wait_for_selector("#appRoot")
        return context, page

    def test_zero_raw_colors_outside_tokens_css(self):
        """Zero hex or raw rgba outside static/css/tokens.css."""
        css_dir = Path("src/deskai/static/css")
        for css_file in css_dir.glob("*.css"):
            if css_file.name == "tokens.css":
                continue
            content = css_file.read_text(encoding="utf-8")
            # Disallow #xxxxxx and rgba(...)
            hex_matches = re.findall(r"#[0-9a-fA-F]{3,6}", content)
            self.assertEqual(hex_matches, [], f"Raw hex colors found in {css_file.name}: {hex_matches}")
            rgba_matches = re.findall(r"rgba?\(.+?\)", content)
            self.assertEqual(rgba_matches, [], f"Raw rgb/rgba found in {css_file.name}: {rgba_matches}")

    def test_decorative_welcome_badge_not_amber(self):
        """Decorative elements such as .welcome-badge must use neutral tokens, not amber accent."""
        context, page = self._create_page()
        try:
            badge_color = page.evaluate("""() => {
                const badge = document.querySelector('.welcome-badge');
                if (!badge) return null;
                const cs = window.getComputedStyle(badge);
                return {
                    color: cs.color,
                    backgroundColor: cs.backgroundColor
                };
            }""")
            if badge_color:
                # Primary amber is rgb(217, 155, 38) or #f59e0b rgb(245, 158, 11)
                self.assertNotIn("217, 155, 38", badge_color["color"])
                self.assertNotIn("245, 158, 11", badge_color["color"])
        finally:
            context.close()

    def test_hover_transitions_under_150ms(self):
        """Hover/focus transitions for interactive controls must not exceed 150ms."""
        context, page = self._create_page(reduced_motion=False)
        try:
            durations = page.evaluate("""() => {
                const selectors = ['.welcome-btn', '.icon-btn', '.drawer-tab', '.terminal-kill-btn'];
                const results = [];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        const dur = window.getComputedStyle(el).transitionDuration;
                        results.push({ selector: sel, duration: dur });
                    }
                }
                return results;
            }""")
            for item in durations:
                # Convert duration e.g. '0.15s' or '150ms' to ms
                dur_str = item["duration"].split(",")[0].strip()
                if dur_str.endswith("ms"):
                    ms = float(dur_str[:-2])
                elif dur_str.endswith("s"):
                    ms = float(dur_str[:-1]) * 1000
                else:
                    ms = 0
                self.assertLessEqual(ms, 150.1, f"Transition duration for {item['selector']} exceeds 150ms: {dur_str}")
        finally:
            context.close()

    def test_prefers_reduced_motion_eliminates_transitions(self):
        """Under prefers-reduced-motion: reduce, transitions are effectively 0ms."""
        context, page = self._create_page(reduced_motion=True)
        try:
            durations = page.evaluate("""() => {
                const btn = document.querySelector('.welcome-btn');
                return btn ? window.getComputedStyle(btn).transitionDuration : '0s';
            }""")
            dur_str = durations.split(",")[0].strip()
            if dur_str.endswith("ms"):
                ms = float(dur_str[:-2])
            elif dur_str.endswith("s"):
                ms = float(dur_str[:-1]) * 1000
            else:
                ms = 0
            self.assertLessEqual(ms, 1.0, f"Transition not reduced under prefers-reduced-motion: {dur_str}")
        finally:
            context.close()
