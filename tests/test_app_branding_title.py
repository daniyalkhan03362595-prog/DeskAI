import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


class TestAppBrandingTitle(unittest.TestCase):
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

    def tearDown(self):
        if hasattr(self, "page"):
            self.page.close()
        if hasattr(self, "context"):
            self.context.close()

    def test_abt_01_accessible_markup_and_semantics(self):
        """TC-ABT-01: Verifies #appHeader has role='banner', #appLogo has accessible label, and icon is aria-hidden."""
        header = self.page.locator("#appHeader")
        self.assertEqual(header.get_attribute("role"), "banner")

        logo = self.page.locator("#appLogo")
        self.assertEqual(logo.count(), 1)
        self.assertEqual(logo.get_attribute("aria-label"), "DeskAI Studio")

        icon = self.page.locator("#appLogo .app-logo-icon")
        self.assertEqual(icon.count(), 1)
        self.assertEqual(icon.get_attribute("aria-hidden"), "true")

    def test_abt_02_brand_text_and_icon_content(self):
        """TC-ABT-02: Verifies brand logotype and symbol text values."""
        logo_text = self.page.locator("#appLogo .app-logo-text").text_content().strip()
        self.assertEqual(logo_text, "DeskAI")

        icon_text = self.page.locator("#appLogo .app-logo-icon").text_content().strip()
        self.assertEqual(icon_text, "⚡")

    def test_abt_03_token_styles_and_colors(self):
        """TC-ABT-03: Verifies computed styles match tokens (color-amber, user-select: none, font-weight: 700)."""
        styles = self.page.evaluate("""() => {
            const el = document.getElementById('appLogo');
            const comp = window.getComputedStyle(el);
            return {
                color: comp.color,
                fontWeight: comp.fontWeight,
                userSelect: comp.userSelect
            };
        }""")
        # --color-amber is #f59e0b -> rgb(245, 158, 11)
        self.assertEqual(styles["color"], "rgb(245, 158, 11)")
        self.assertEqual(styles["fontWeight"], "700")
        self.assertEqual(styles["userSelect"], "none")

    def test_abt_04_drag_region_inheritance(self):
        """TC-ABT-04: Verifies #appHeader is a drag region and #appLogo does not disable dragging."""
        app_region = self.page.evaluate("""() => {
            const header = document.getElementById('appHeader');
            const logo = document.getElementById('appLogo');
            return {
                headerDrag: window.getComputedStyle(header).webkitAppRegion,
                logoDrag: window.getComputedStyle(logo).webkitAppRegion
            };
        }""")
        self.assertEqual(app_region["headerDrag"], "drag")
        self.assertNotEqual(app_region["logoDrag"], "no-drag")

    def test_abt_05_keyboard_tab_traversal_skips_logo(self):
        """TC-ABT-05: Verifies pressing Tab skips the branding logo and lands on interactive elements."""
        self.page.evaluate("() => document.body.focus()")
        self.page.keyboard.press("Tab")

        active_id = self.page.evaluate("() => document.activeElement ? document.activeElement.id : null")
        self.assertNotEqual(active_id, "appLogo")


if __name__ == "__main__":
    unittest.main()
