import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


class TestBottomDrawerBehavior(unittest.TestCase):
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
        self.context = self.browser.new_context(permissions=["clipboard-read", "clipboard-write"])
        self.page = self.context.new_page()
        self.page.goto(f"file://{index_file}")

    def tearDown(self):
        if hasattr(self, "page"):
            self.page.close()
        if hasattr(self, "context"):
            self.context.close()

    def test_clicking_any_tab_expands_collapsed_drawer(self):
        """Clicking any drawer tab must expand a collapsed drawer."""
        drawer = self.page.locator("#bottomDrawer")
        toggle_btn = self.page.locator("#drawerToggleBtn")

        # Collapse drawer via toggle button
        toggle_btn.click()
        self.assertIn("collapsed", drawer.get_attribute("class"))
        self.assertEqual(toggle_btn.get_attribute("aria-expanded"), "false")

        # Click ports tab -> must uncollapse
        self.page.locator("#tab-ports").click()
        self.assertNotIn("collapsed", drawer.get_attribute("class"))
        self.assertEqual(toggle_btn.get_attribute("aria-expanded"), "true")

    def test_resizer_double_click_toggle_collapse(self):
        """Double-clicking resizerBottom toggles collapsed state and restores height."""
        drawer = self.page.locator("#bottomDrawer")
        resizer = self.page.locator("#resizerBottom")
        toggle_btn = self.page.locator("#drawerToggleBtn")

        # Double click to collapse
        resizer.dblclick()
        self.assertIn("collapsed", drawer.get_attribute("class"))
        self.assertEqual(toggle_btn.get_attribute("aria-expanded"), "false")

        # Double click again to restore
        resizer.dblclick()
        self.assertNotIn("collapsed", drawer.get_attribute("class"))
        self.assertEqual(toggle_btn.get_attribute("aria-expanded"), "true")

    def test_resizer_keyboard_navigation(self):
        """Arrow keys, Home, and End on resizerBottom adjust height appropriately."""
        resizer = self.page.locator("#resizerBottom")
        drawer = self.page.locator("#bottomDrawer")

        resizer.focus()
        val_start = int(resizer.get_attribute("aria-valuenow"))

        # ArrowUp expands
        self.page.keyboard.press("ArrowUp")
        val_up = int(resizer.get_attribute("aria-valuenow"))
        self.assertGreater(val_up, val_start)

        # ArrowDown shrinks
        self.page.keyboard.press("ArrowDown")
        val_down = int(resizer.get_attribute("aria-valuenow"))
        self.assertLess(val_down, val_up)

        # Home collapses
        self.page.keyboard.press("Home")
        self.assertIn("collapsed", drawer.get_attribute("class"))
        self.assertEqual(resizer.get_attribute("aria-valuenow"), "48")

        # End expands to max
        self.page.keyboard.press("End")
        self.assertNotIn("collapsed", drawer.get_attribute("class"))
        val_max = int(resizer.get_attribute("aria-valuenow"))
        self.assertGreaterEqual(val_max, 400)

    def test_collapsed_drawer_content_not_keyboard_focusable(self):
        """When collapsed, .drawer-content has display: none so interior controls cannot be focused."""
        toggle_btn = self.page.locator("#drawerToggleBtn")
        content = self.page.locator("#drawerContent")

        toggle_btn.click()
        self.assertFalse(content.is_visible())
        display_style = self.page.evaluate("getComputedStyle(document.getElementById('drawerContent')).display")
        self.assertEqual(display_style, "none")

    def test_tablist_roving_arrow_key_focus(self):
        """ArrowLeft and ArrowRight roving focus with automatic tab activation."""
        self.page.locator("#tab-terminal").click()
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "tab-terminal")

        self.page.keyboard.press("ArrowRight")
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "tab-output")

        self.page.keyboard.press("ArrowRight")
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "tab-problems")

        self.page.keyboard.press("ArrowRight")
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "tab-ports")

        self.page.keyboard.press("ArrowLeft")
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "tab-problems")

    def test_refresh_ports_preserves_focus(self):
        """Refreshing ports preserves focus on active elements inside the ports table."""
        self.page.locator("#tab-ports").click()

        self.page.evaluate("""
            window.DeskAIPorts.customPorts.push({
                port: 8888,
                host: "127.0.0.1",
                protocol: "TCP",
                address: "http://127.0.0.1:8888",
                process: "Watched",
                status: "Listening",
                origin: "Watched",
                isCustom: true,
                exposure: "loopback",
                openable: true
            });
            window.DeskAIPorts.render();
        """)

        copy_btn = self.page.locator('button[data-action="copy-port"][data-url="http://127.0.0.1:8888"]')
        copy_btn.focus()
        self.assertEqual(self.page.evaluate("document.activeElement.getAttribute('data-action')"), "copy-port")

        self.page.evaluate("window.DeskAIPorts.render();")
        self.assertEqual(self.page.evaluate("document.activeElement.getAttribute('data-action')"), "copy-port")

    def test_copy_port_inline_checkmark_feedback(self):
        """Clicking copy-port displays inline SVG checkmark and does not show corner toast."""
        self.page.locator("#tab-ports").click()
        self.page.evaluate("""
            window.DeskAIPorts.stopPolling();
            window.DeskAIPorts.customPorts.push({
                port: 5555,
                host: "127.0.0.1",
                protocol: "TCP",
                address: "http://127.0.0.1:5555",
                process: "test_srv",
                status: "Listening",
                origin: "Watched",
                isCustom: true,
                exposure: "loopback",
                openable: true
            });
            window.DeskAIPorts.render();
        """)

        copy_btn = self.page.locator('button[data-action="copy-port"][data-url="http://127.0.0.1:5555"]')
        self.assertEqual(copy_btn.text_content().strip(), "Copy")

        # Click the copy button
        copy_btn.click()

        # Wait for async clipboard copy to complete and class + svg to be applied
        svg_icon = self.page.wait_for_selector(
            'button[data-action="copy-port"].is-copied svg.port-check-icon', timeout=2000
        )
        self.assertIsNotNone(svg_icon)

        # Confirm NO toast was shown in toastRack
        toast_count = self.page.locator("#toastRack .toast").count()
        self.assertEqual(toast_count, 0)

        # After timeout (100ms), button should revert back
        self.page.wait_for_timeout(200)
        self.assertNotIn("is-copied", copy_btn.get_attribute("class"))
        self.assertEqual(copy_btn.text_content().strip(), "Copy")

    def test_open_port_inline_checkmark_feedback(self):
        """Clicking open-port displays inline SVG checkmark and reverts within 100ms."""
        self.page.locator("#tab-ports").click()
        self.page.evaluate("""
            window.DeskAIPorts.stopPolling();
            window.DeskAIPorts.customPorts = [{
                port: 6666,
                host: "127.0.0.1",
                protocol: "TCP",
                address: "http://127.0.0.1:6666",
                process: "web_app",
                status: "Listening",
                origin: "Watched",
                isCustom: true,
                exposure: "loopback",
                openable: true
            }];
            window.pywebview = {
                api: {
                    open_port: async (port, host) => true
                }
            };
            window.DeskAIPorts.render();
        """)

        open_btn = self.page.locator('button[data-action="open-port"][data-port="6666"]')
        self.assertEqual(open_btn.text_content().strip(), "Open")

        # Click open button
        open_btn.click()

        # Should show checkmark
        self.page.wait_for_selector('button[data-action="open-port"][data-port="6666"].is-copied', timeout=2000)
        self.assertIn("is-copied", open_btn.get_attribute("class"))

        # After 200ms (> 100ms), it should revert back to "Open"
        self.page.wait_for_timeout(200)
        self.assertNotIn("is-copied", open_btn.get_attribute("class"))
        self.assertEqual(open_btn.text_content().strip(), "Open")

    def test_action_buttons_trigger_zero_layout_shift(self):
        """Action button feedback preserves exact column widths and positions (zero layout jitter)."""
        self.page.set_viewport_size({"width": 1920, "height": 1080})
        self.page.locator("#tab-ports").click()
        self.page.evaluate("""
            window.DeskAIPorts.stopPolling();
            window.DeskAIPorts.showTransient = true;
            window.DeskAIPorts.portsList = [
                {
                    port: 33901,
                    host: '127.0.0.1',
                    protocol: 'TCP',
                    address: 'http://127.0.0.1:33901',
                    process: 'antigravity',
                    pid: 6582,
                    origin: 'Local',
                    status: 'Listening',
                    openable: true
                }
            ];
            window.DeskAIPorts._lastSignature = null;
            window.DeskAIPorts.render();
            window.pywebview = { api: { open_port: async () => true } };
        """)

        # Get initial bounding rects
        measure_js = """() => {
            const ths = Array.from(document.querySelectorAll('.ports-table th')).map(th => ({
                text: th.textContent.trim(),
                width: th.getBoundingClientRect().width,
                left: th.getBoundingClientRect().left
            }));
            const copyBtn = document.querySelector('button[data-action="copy-port"]').getBoundingClientRect();
            return { ths, copyBtn };
        }"""

        before = self.page.evaluate(measure_js)

        # Trigger open action
        self.page.locator('button[data-action="open-port"]').first.click()
        self.page.wait_for_selector('button[data-action="open-port"].is-copied', timeout=2000)

        during = self.page.evaluate(measure_js)

        # Verify that all table headers and neighboring buttons maintained zero layout shift (diff < 0.05px)
        for b, d in zip(before["ths"], during["ths"]):
            self.assertAlmostEqual(b["width"], d["width"], delta=0.05, msg=f"Column width shifted for {b['text']}")
            self.assertAlmostEqual(
                b["left"], d["left"], delta=0.05, msg=f"Column left position shifted for {b['text']}"
            )

        self.assertAlmostEqual(
            before["copyBtn"]["left"],
            during["copyBtn"]["left"],
            delta=0.05,
            msg="Neighboring Copy button shifted position",
        )


if __name__ == "__main__":
    unittest.main()
