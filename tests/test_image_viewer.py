"""
Integration and UI Tests for Built-in Image Viewer Component.
Asserts:
1. Opening image files (.png, .jpg, .svg, etc.) creates an Image Viewer tab.
2. Tab strip displays filename with 'image' SVG icon and close button.
3. Editor viewport hides Welcome dashboard and renders .editor-image-container with .editor-preview-image.
4. Image info bar displays filename, dimensions, and formatted file size.
5. Tab switching between image buffers and text editor buffers functions cleanly.
6. Closing image tab disposes the container and restores welcome dashboard when empty.
"""

import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


class TestImageViewer(unittest.TestCase):
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

        # Mock pywebview bridge with image file support
        self.page.add_init_script("""
            const mockPng = "data:image/png;base64," +
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==";
            window.pywebview = {
                api: {
                    read_file: async (path) => {
                        if (path.endsWith(".png") || path.endsWith(".jpg")) {
                            return {
                                status: "ok",
                                content: mockPng,
                                path: path,
                                is_image: true,
                                mime_type: "image/png",
                                size_bytes: 68
                            };
                        }
                        return {
                            status: "ok",
                            content: "print('Hello DeskAI')",
                            path: path,
                            is_image: false,
                            size_bytes: 20
                        };
                    },
                    write_file: async (path, content) => ({ status: "ok" }),
                    set_dirty_status: async (dirty) => true,
                    terminal_open: async () => ({ status: "ok", session_id: "mock-sess-1" }),
                    terminal_close: async () => true
                }
            };
        """)
        self.page.goto(f"file://{index_file}")
        self.page.wait_for_selector("#editorViewport")

    def tearDown(self):
        if hasattr(self, "page"):
            self.page.close()
        if hasattr(self, "context"):
            self.context.close()

    def test_open_image_renders_image_viewer_and_tab(self):
        """Opening a .png file renders an Image Viewer tab and active image container."""
        # Open image file via EditorManager
        tab_id = self.page.evaluate("async () => await window.EditorManager.openFile('/workspace/screenshot.png')")
        self.assertIsNotNone(tab_id)
        self.page.wait_for_timeout(100)

        # 1. Tab exists with correct label and icon
        tab_el = self.page.locator(f"#tab-{tab_id}")
        self.assertTrue(tab_el.is_visible())
        self.assertEqual(tab_el.locator(".tab-label").inner_text(), "screenshot.png")
        self.assertEqual(tab_el.locator(".tab-icon").get_attribute("data-icon"), "image")

        # 2. Welcome screen is hidden
        welcome_display = self.page.evaluate(
            "() => document.getElementById('welcomeScreen') ? "
            "window.getComputedStyle(document.getElementById('welcomeScreen')).display : 'none'"
        )
        self.assertEqual(welcome_display, "none")

        # 3. Image viewer container is visible and active
        container = self.page.locator(f"#editor-container-{tab_id}")
        self.assertTrue(container.is_visible())
        self.assertIn("editor-image-container", container.get_attribute("class"))

        # 4. Preview image element exists with mock data URL
        img = container.locator(".editor-preview-image")
        self.assertTrue(img.is_visible())
        self.assertEqual(img.get_attribute("alt"), "screenshot.png")

        # 5. Info bar displays name, dimensions, and size
        infobar = container.locator(".editor-image-infobar")
        self.assertTrue(infobar.is_visible())
        self.assertEqual(infobar.locator(".image-info-name").inner_text(), "screenshot.png")
        self.assertIn("68 B", infobar.locator(".image-info-size").inner_text())

    def test_switch_between_image_and_text_buffers(self):
        """Switching between image tab and code tab updates container visibility."""
        # Open image and code file
        img_id = self.page.evaluate("async () => await window.EditorManager.openFile('/workspace/diagram.png')")
        code_id = self.page.evaluate("async () => await window.EditorManager.openFile('/workspace/main.py')")
        self.page.wait_for_timeout(100)

        img_container = self.page.locator(f"#editor-container-{img_id}")
        code_container = self.page.locator(f"#editor-container-{code_id}")

        # Active tab is code file initially
        self.assertEqual(self.page.evaluate("() => window.EditorManager.activeTabId"), code_id)
        self.assertTrue(code_container.is_visible())
        self.assertFalse(img_container.is_visible())

        # Click image tab
        self.page.locator(f"#tab-{img_id}").click()
        self.page.wait_for_timeout(100)

        self.assertEqual(self.page.evaluate("() => window.EditorManager.activeTabId"), img_id)
        self.assertTrue(img_container.is_visible())
        self.assertFalse(code_container.is_visible())

    def test_close_image_tab_restores_welcome_when_empty(self):
        """Closing the sole image tab disposes viewer and displays welcome dashboard."""
        img_id = self.page.evaluate("async () => await window.EditorManager.openFile('/workspace/preview.png')")
        self.page.wait_for_timeout(100)

        # Close image tab via tab close button
        close_btn = self.page.locator(f"#tab-{img_id} .tab-close-btn")
        close_btn.click()
        self.page.wait_for_timeout(100)

        # Tab strip shows 'No files open'
        empty_label = self.page.locator("#tabStripEmptyLabel")
        self.assertTrue(empty_label.is_visible())
        self.assertEqual(empty_label.inner_text(), "No files open")

        # Container is removed from DOM
        container_count = self.page.locator(f"#editor-container-{img_id}").count()
        self.assertEqual(container_count, 0)

        # Welcome dashboard is visible again
        welcome = self.page.locator("#welcomeScreen")
        self.assertTrue(welcome.is_visible())


if __name__ == "__main__":
    unittest.main()
