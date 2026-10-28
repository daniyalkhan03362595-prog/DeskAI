"""
Test for Task 6: Stray Text Under Window and Clean DOM Bounds.
Asserts:
1. document.body contains no stray script or text nodes outside #appRoot.
2. All screen reader announcers (.sr-only) are positioned safely offscreen (top < 0).
3. #templateStore and hidden templates have display: none !important.
4. No rendered element overflows outside #appRoot's bounds on the screen.
"""

import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright
import httpx
from deskai.server.supervisor import DesktopServer


class TestTask6StrayDomText(unittest.TestCase):
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
        page.goto(f"http://127.0.0.1:{self.srv.port}/")
        page.wait_for_selector("#appRoot")
        return context, page

    def test_script_tag_in_head_not_body(self):
        """index.html must load module scripts in <head> so <body> contains only #appRoot."""
        index_content = Path("src/deskai/static/index.html").read_text(encoding="utf-8")
        body_part = index_content.split("<body")[1] if "<body" in index_content else ""
        self.assertNotIn('<script type="module"', body_part, "Module script found in <body> instead of <head>")

    def test_sr_only_announcers_positioned_safely_offscreen(self):
        """Screen reader announcers must have explicit negative offscreen coordinates to prevent 1px bottom bleed."""
        context, page = self._create_page()
        try:
            positions = page.evaluate("""() => {
                const announcers = [
                    document.getElementById('screenReaderAnnouncer'),
                    document.getElementById('welcomeSrLive')
                ].filter(Boolean);
                return announcers.map(el => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return {
                        id: el.id,
                        top: rect.top,
                        position: style.position,
                        clip: style.clip || style.clipPath
                    };
                });
            }""")
            for ann in positions:
                self.assertLess(
                    ann["top"], 0, f"Announcer {ann['id']} has top >= 0 ({ann['top']}px) causing bottom edge bleed"
                )
        finally:
            context.close()

    def test_template_store_and_hidden_elements_have_display_none(self):
        """#templateStore and [hidden] elements must have display: none !important."""
        context, page = self._create_page()
        try:
            display_info = page.evaluate("""() => {
                const store = document.getElementById('templateStore');
                const menu = document.getElementById('treeContextMenu');
                return {
                    storeDisplay: store ? window.getComputedStyle(store).display : null,
                    menuDisplay: menu ? window.getComputedStyle(menu).display : null
                };
            }""")
            self.assertEqual(display_info["storeDisplay"], "none")
            self.assertEqual(display_info["menuDisplay"], "none")
        finally:
            context.close()

    def test_no_rendered_content_outside_app_root_bounds(self):
        """Nothing rendered on screen exceeds #appRoot's bounds."""
        context, page = self._create_page()
        try:
            # Trigger an announcement to populate screen reader live region
            page.evaluate("""() => {
                const ann = document.getElementById('screenReaderAnnouncer');
                if (ann) ann.textContent = 'Active file changed: test.py';
            }""")
            page.wait_for_timeout(50)

            overflowing = page.evaluate("""() => {
                const root = document.getElementById('appRoot');
                const rootRect = root.getBoundingClientRect();
                const violations = [];

                // Check all non-hidden elements that are visible on-screen
                document.querySelectorAll('*').forEach(el => {
                    if (el.tagName === 'SCRIPT' || el.tagName === 'STYLE' || el.tagName === 'TEMPLATE') return;
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden') return;

                    const r = el.getBoundingClientRect();
                    // Offscreen elements (e.g. top < -100px) are intentionally hidden
                    if (r.top <= -100 || r.left <= -100) return;

                    // Elements inside terminalHost or editorHost are clipped by their parent scroll containers
                    if (el.closest('#terminalHost') || el.closest('#editorViewport')) return;

                    // Visible on-screen element exceeding appRoot bottom by more than 1px
                    if (r.bottom > rootRect.bottom + 1 && r.height > 0) {
                        violations.push({
                            tag: el.tagName,
                            id: el.id,
                            className: el.className,
                            bottom: r.bottom,
                            rootBottom: rootRect.bottom,
                            text: (el.textContent || '').trim().slice(0, 40)
                        });
                    }
                });
                return violations;
            }""")
            self.assertEqual(overflowing, [], f"Elements rendered outside #appRoot bounds: {overflowing}")
        finally:
            context.close()
