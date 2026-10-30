import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


class TestPanelResizersDrag(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not _HAS_PLAYWRIGHT:
            raise unittest.SkipTest("Playwright is not installed")
        cls.p = sync_playwright().start()
        try:
            cls.browser = cls.p.chromium.launch(
                headless=True,
                args=["--allow-file-access-from-files"]
            )
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
        self.context = self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            permissions=["clipboard-read", "clipboard-write"]
        )
        self.page = self.context.new_page()
        self.page.goto(f"file://{index_file}")
        self.page.wait_for_selector("#resizerLeft")
        self.page.wait_for_selector("#resizerRight")
        self.page.wait_for_selector("#resizerBottom")

    def tearDown(self):
        if hasattr(self, "page"):
            self.page.close()
        if hasattr(self, "context"):
            self.context.close()

    def test_left_resizer_pointer_drag_updates_css_and_aria(self):
        """Pointer dragging #resizerLeft smoothly updates --sidebar-left-w and aria-valuenow."""
        resizer = self.page.locator("#resizerLeft")
        self.assertTrue(resizer.is_visible())

        box = resizer.bounding_box()
        self.assertIsNotNone(box)

        # Mouse down and drag right to 320px
        self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 100)
        self.page.mouse.down()

        # Check that html has class is-resizing-col while dragging
        has_resizing_class = self.page.evaluate("document.documentElement.classList.contains('is-resizing-col')")
        self.assertTrue(has_resizing_class, "html should have is-resizing-col class during drag")

        self.page.mouse.move(320, box["y"] + 100)
        self.page.wait_for_timeout(50)  # Allow RAF to process

        # Verify width updated
        left_w = self.page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--sidebar-left-w')")
        self.assertEqual(left_w.strip(), "320px")
        self.assertEqual(resizer.get_attribute("aria-valuenow"), "320")

        # Mouse up
        self.page.mouse.up()
        has_resizing_class_after = self.page.evaluate("document.documentElement.classList.contains('is-resizing-col')")
        self.assertFalse(has_resizing_class_after, "html is-resizing-col class should be removed after drag")

        # Check localStorage persistence
        saved = self.page.evaluate("localStorage.getItem('deskai_sidebar_left_w')")
        self.assertEqual(saved, "320")

    def test_left_resizer_keyboard_navigation(self):
        """Keyboard ArrowLeft, ArrowRight, Home, End adjust left sidebar width."""
        resizer = self.page.locator("#resizerLeft")
        resizer.focus()

        initial_w = int(resizer.get_attribute("aria-valuenow"))

        # ArrowRight expands by 16px
        self.page.keyboard.press("ArrowRight")
        w_right = int(resizer.get_attribute("aria-valuenow"))
        self.assertEqual(w_right, initial_w + 16)

        # ArrowLeft shrinks by 16px
        self.page.keyboard.press("ArrowLeft")
        w_left = int(resizer.get_attribute("aria-valuenow"))
        self.assertEqual(w_left, initial_w)

        # Home sets to min (180px)
        self.page.keyboard.press("Home")
        self.assertEqual(resizer.get_attribute("aria-valuenow"), "180")

        # End sets to max available (clamped by editor min-width 480px, in 1280px screen max is 438px)
        self.page.keyboard.press("End")
        val_end = int(resizer.get_attribute("aria-valuenow"))
        self.assertGreaterEqual(val_end, 400)
        self.assertLessEqual(val_end, 450)

    def test_left_resizer_double_click_toggle_collapse(self):
        """Double clicking #resizerLeft toggles sidebar collapse."""
        resizer = self.page.locator("#resizerLeft")
        app_body = self.page.locator("#appBody")

        # Double click to collapse
        resizer.dblclick()
        self.assertIn("sidebar-left-collapsed", app_body.get_attribute("class"))

        # Expand via expand pill
        expand_btn = self.page.locator("#btnExpandSidebar")
        expand_btn.click()
        self.assertNotIn("sidebar-left-collapsed", app_body.get_attribute("class"))

    def test_right_resizer_pointer_drag_updates_css_and_aria(self):
        """Pointer dragging #resizerRight smoothly updates --sidebar-right-w and aria-valuenow."""
        resizer = self.page.locator("#resizerRight")
        self.assertTrue(resizer.is_visible())

        box = resizer.bounding_box()
        self.assertIsNotNone(box)

        # Mouse down on right resizer
        self.page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 100)
        self.page.mouse.down()

        # Check html has is-resizing-col
        self.assertTrue(self.page.evaluate("document.documentElement.classList.contains('is-resizing-col')"))

        # Drag left to increase right sidebar width (viewport 1280, drag to x=900 => width 380)
        self.page.mouse.move(900, box["y"] + 100)
        self.page.wait_for_timeout(50)

        right_w = self.page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--sidebar-right-w')")
        self.assertEqual(right_w.strip(), "380px")
        self.assertEqual(resizer.get_attribute("aria-valuenow"), "380")

        self.page.mouse.up()
        self.assertFalse(self.page.evaluate("document.documentElement.classList.contains('is-resizing-col')"))

        # Check localStorage persistence
        saved = self.page.evaluate("localStorage.getItem('deskai_sidebar_right_w')")
        self.assertEqual(saved, "380")

    def test_right_resizer_keyboard_navigation(self):
        """Keyboard ArrowLeft, ArrowRight, Home, End adjust right sidebar width."""
        resizer = self.page.locator("#resizerRight")
        resizer.focus()

        initial_w = int(resizer.get_attribute("aria-valuenow"))

        # ArrowLeft expands right sidebar width by 16px
        self.page.keyboard.press("ArrowLeft")
        w_left = int(resizer.get_attribute("aria-valuenow"))
        self.assertEqual(w_left, initial_w + 16)

        # ArrowRight shrinks right sidebar width by 16px
        self.page.keyboard.press("ArrowRight")
        w_right = int(resizer.get_attribute("aria-valuenow"))
        self.assertEqual(w_right, initial_w)

        # Home sets to min (200px)
        self.page.keyboard.press("Home")
        self.assertEqual(resizer.get_attribute("aria-valuenow"), "200")

        # End sets to max (500px)
        self.page.keyboard.press("End")
        self.assertEqual(resizer.get_attribute("aria-valuenow"), "500")

    def test_right_resizer_double_click_resets_default(self):
        """Double clicking #resizerRight resets right sidebar width to 360px default."""
        resizer = self.page.locator("#resizerRight")
        resizer.focus()

        # Change width to min 200px
        self.page.keyboard.press("Home")
        self.assertEqual(resizer.get_attribute("aria-valuenow"), "200")

        # Double click to reset to 360px
        resizer.dblclick()
        right_w = self.page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--sidebar-right-w')")
        self.assertEqual(right_w.strip(), "360px")
        self.assertEqual(resizer.get_attribute("aria-valuenow"), "360")

    def test_bottom_resizer_drag_and_class(self):
        """Pointer dragging #resizerBottom adds is-resizing-row and updates --bottom-drawer-h."""
        resizer = self.page.locator("#resizerBottom")
        box = resizer.bounding_box()
        self.assertIsNotNone(box)

        start_x = int(box["x"]) + 100
        start_y = int(box["y"])

        self.page.mouse.move(start_x, start_y)
        self.page.mouse.down()

        self.assertTrue(self.page.evaluate("document.documentElement.classList.contains('is-resizing-row')"))

        # Move mouse up by 50px (y decreases by 50, height increases by 50)
        self.page.mouse.move(start_x, start_y - 50)
        self.page.wait_for_timeout(50)

        drawer_h = self.page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--bottom-drawer-h')")
        self.assertEqual(drawer_h.strip(), "270px")
        self.assertEqual(resizer.get_attribute("aria-valuenow"), "270")

        self.page.mouse.up()
        self.assertFalse(self.page.evaluate("document.documentElement.classList.contains('is-resizing-row')"))

    def test_resizing_isolation_css(self):
        """CSS rules isolate pointer-events during resizing."""
        # Add is-resizing-col class to root
        self.page.evaluate("document.documentElement.classList.add('is-resizing-col')")
        cursor = self.page.evaluate("getComputedStyle(document.body).cursor")
        self.assertEqual(cursor, "col-resize")

        # Remove class
        self.page.evaluate("document.documentElement.classList.remove('is-resizing-col')")

        # Add is-resizing-row class to root
        self.page.evaluate("document.documentElement.classList.add('is-resizing-row')")
        cursor_row = self.page.evaluate("getComputedStyle(document.body).cursor")
        self.assertEqual(cursor_row, "row-resize")

        self.page.evaluate("document.documentElement.classList.remove('is-resizing-row')")

    def test_sidebar_dimensions_restoration_from_local_storage(self):
        """Pre-existing localStorage values for left and right sidebars are restored on load."""
        index_file = Path("src/deskai/static/index.html").resolve()
        new_page = self.context.new_page()

        # Seed localStorage on about:blank or via add_init_script
        new_page.add_init_script("""
            localStorage.setItem('deskai_sidebar_left_w', '310');
            localStorage.setItem('deskai_sidebar_right_w', '390');
            localStorage.setItem('deskai_bottom_drawer_h', '260');
        """)
        new_page.goto(f"file://{index_file}")
        new_page.wait_for_selector("#resizerLeft")

        left_w = new_page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--sidebar-left-w')")
        right_w = new_page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--sidebar-right-w')")
        drawer_h = new_page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--bottom-drawer-h')")

        self.assertEqual(left_w.strip(), "310px")
        self.assertEqual(right_w.strip(), "390px")
        self.assertEqual(drawer_h.strip(), "260px")

        res_left = new_page.locator("#resizerLeft")
        res_right = new_page.locator("#resizerRight")
        res_bottom = new_page.locator("#resizerBottom")

        self.assertEqual(res_left.get_attribute("aria-valuenow"), "310")
        self.assertEqual(res_right.get_attribute("aria-valuenow"), "390")
        self.assertEqual(res_bottom.get_attribute("aria-valuenow"), "260")

        new_page.close()
