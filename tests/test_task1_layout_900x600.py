"""
Playwright Test for Task 1: Responsive Layout at Minimum Window Size (900x600, 1280x800, 1920x1080).
Asserts against live DesktopServer over HTTP with cookie auth:
1. Center column width >= 480px at 900x600 window width.
2. No horizontal window scrolling at 900x600, 1280x800, 1920x1080.
3. No element's right edge exceeds its parent container.
4. Welcome screen stacks Get Started and Keyboard Shortcuts vertically below 560px center width.
5. All three welcome buttons are visible and fully inside the viewport.
6. Terminal footer is single line without wrapping.
"""

import unittest

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False

from deskai.server.supervisor import DesktopServer


class TestTask1LayoutResponsive(unittest.TestCase):
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

        cls.srv = DesktopServer()
        cls.srv.start()
        token = cls.srv.security.create_launch_token()

        import httpx

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

    def _create_page(self, width: int, height: int):
        context = self.browser.new_context(viewport={"width": width, "height": height})
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

    def test_layout_at_900x600(self):
        """At 900x600, center >= 480px, welcome stacks vertically, buttons visible, no overflow."""
        context, page = self._create_page(900, 600)
        try:
            # 1. No horizontal window scroll
            has_h_scroll = page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth")
            self.assertFalse(has_h_scroll, "Page has horizontal window scrollbar at 900x600")

            # 2. Center column maintains at least ~480px width
            center_width = page.evaluate("() => document.getElementById('editorStage').getBoundingClientRect().width")
            self.assertGreaterEqual(
                center_width,
                480,
                f"Center column width is {center_width}px, expected at least 480px at 900px window width",
            )

            # 3. Welcome grid stacks vertically into 1 column
            grid_cols = page.evaluate("""() => {
                const grid = document.getElementById('welcomeGrid');
                return window.getComputedStyle(grid).gridTemplateColumns.split(' ').length;
            }""")
            self.assertEqual(grid_cols, 1, f"Expected 1-column welcome grid, got {grid_cols} columns")

            # 4. All three welcome buttons are visible and fully inside viewport
            buttons = page.locator("#welcomeGrid .welcome-action-stack button").all()
            self.assertGreaterEqual(len(buttons), 3, "Expected at least 3 welcome buttons")
            for i, btn in enumerate(buttons):
                box = btn.bounding_box()
                self.assertIsNotNone(box, f"Welcome button {i} has no bounding box")
                self.assertGreaterEqual(box["x"], 0, f"Button {i} left outside viewport")
                self.assertLessEqual(box["x"] + box["width"], 900, f"Button {i} right outside viewport")
                self.assertGreaterEqual(box["y"], 0, f"Button {i} top outside viewport")
                self.assertLessEqual(box["y"] + box["height"], 600, f"Button {i} bottom outside viewport")

            # 5. Buttons must not wrap their label; shortcut badges stay on one line
            btn_labels_wrapped = page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('.welcome-btn'));
                return btns.some(b => {
                    const label = b.querySelector('.welcome-btn-label');
                    if (!label) return false;
                    return label.getClientRects().length > 1;
                });
            }""")
            self.assertFalse(btn_labels_wrapped, "Welcome button labels wrapped across multiple lines")

            # 6. Terminal footer: single line (height <= 32px), no wrapping
            footer_height = page.evaluate("""() => {
                const footer = document.querySelector('.terminal-footer');
                return footer ? footer.getBoundingClientRect().height : 0;
            }""")
            self.assertLessEqual(footer_height, 32, f"Terminal footer wrapped to height {footer_height}px")

            # 7. No element's right edge exceeds its container
            overflows = page.evaluate("""() => {
                const culprits = [];
                const checkElements = document.querySelectorAll(
                    '.welcome-card, .welcome-btn, .terminal-footer, .header-left, .header-right'
                );
                for (const el of checkElements) {
                    if (el.scrollWidth > el.clientWidth + 2) {
                        culprits.push(el.className + ' (' + el.scrollWidth + ' > ' + el.clientWidth + ')');
                    }
                }
                return culprits;
            }""")
            self.assertEqual(overflows, [], f"Elements overflow their container: {overflows}")
        finally:
            context.close()

    def test_layout_at_1280x800_and_1920x1080(self):
        """At 1280x800 and 1920x1080, center is spacious, buttons are fully inside viewport, no horizontal scroll."""
        for w, h in [(1280, 800), (1920, 1080)]:
            with self.subTest(width=w, height=h):
                context, page = self._create_page(w, h)
                try:
                    has_h_scroll = page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth")
                    self.assertFalse(has_h_scroll, f"Page has horizontal scroll at {w}x{h}")

                    center_width = page.evaluate(
                        "() => document.getElementById('editorStage').getBoundingClientRect().width"
                    )
                    self.assertGreaterEqual(center_width, 600, f"Center width {center_width} too small at {w}x{h}")

                    buttons = page.locator("#welcomeGrid .welcome-action-stack button").all()
                    self.assertGreaterEqual(len(buttons), 3)
                    for i, btn in enumerate(buttons):
                        box = btn.bounding_box()
                        self.assertIsNotNone(box)
                        self.assertGreaterEqual(box["x"], 0)
                        self.assertLessEqual(box["x"] + box["width"], w)
                        self.assertGreaterEqual(box["y"], 0)
                        self.assertLessEqual(box["y"] + box["height"], h)
                finally:
                    context.close()
