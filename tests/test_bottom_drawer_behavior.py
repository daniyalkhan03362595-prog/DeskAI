import pytest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


@pytest.mark.skipif(not _HAS_PLAYWRIGHT, reason="Playwright is not installed")
class TestBottomDrawerBehavior:
    @pytest.fixture(autouse=True)
    def setup_browser(self):
        index_file = Path("src/deskai/static/index.html").resolve()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--allow-file-access-from-files"])
            page = browser.new_page()
            page.goto(f"file://{index_file}")
            self.browser = browser
            self.page = page
            yield
            browser.close()

    def test_clicking_any_tab_expands_collapsed_drawer(self):
        """Clicking any drawer tab must expand a collapsed drawer."""
        drawer = self.page.locator("#bottomDrawer")
        toggle_btn = self.page.locator("#drawerToggleBtn")

        # Collapse drawer via toggle button
        toggle_btn.click()
        assert "collapsed" in drawer.get_attribute("class")
        assert toggle_btn.get_attribute("aria-expanded") == "false"

        # Click ports tab -> must uncollapse
        self.page.locator("#tab-ports").click()
        assert "collapsed" not in drawer.get_attribute("class")
        assert toggle_btn.get_attribute("aria-expanded") == "true"

    def test_resizer_double_click_toggle_collapse(self):
        """Double-clicking resizerBottom toggles collapsed state and restores height."""
        drawer = self.page.locator("#bottomDrawer")
        resizer = self.page.locator("#resizerBottom")
        toggle_btn = self.page.locator("#drawerToggleBtn")

        # Double click to collapse
        resizer.dblclick()
        assert "collapsed" in drawer.get_attribute("class")
        assert toggle_btn.get_attribute("aria-expanded") == "false"

        # Double click again to restore
        resizer.dblclick()
        assert "collapsed" not in drawer.get_attribute("class")
        assert toggle_btn.get_attribute("aria-expanded") == "true"

    def test_resizer_keyboard_navigation(self):
        """Arrow keys, Home, and End on resizerBottom adjust height appropriately."""
        resizer = self.page.locator("#resizerBottom")
        drawer = self.page.locator("#bottomDrawer")

        resizer.focus()
        val_start = int(resizer.get_attribute("aria-valuenow"))

        # ArrowUp expands
        self.page.keyboard.press("ArrowUp")
        val_up = int(resizer.get_attribute("aria-valuenow"))
        assert val_up > val_start

        # ArrowDown shrinks
        self.page.keyboard.press("ArrowDown")
        val_down = int(resizer.get_attribute("aria-valuenow"))
        assert val_down < val_up

        # Home collapses
        self.page.keyboard.press("Home")
        assert "collapsed" in drawer.get_attribute("class")
        assert resizer.get_attribute("aria-valuenow") == "48"

        # End expands to max
        self.page.keyboard.press("End")
        assert "collapsed" not in drawer.get_attribute("class")
        val_max = int(resizer.get_attribute("aria-valuenow"))
        assert val_max >= 400

    def test_collapsed_drawer_content_not_keyboard_focusable(self):
        """When collapsed, .drawer-content has display: none so interior controls cannot be focused."""
        toggle_btn = self.page.locator("#drawerToggleBtn")
        content = self.page.locator("#drawerContent")

        toggle_btn.click()
        assert not content.is_visible()
        # Ensure display is none
        display_style = self.page.evaluate("getComputedStyle(document.getElementById('drawerContent')).display")
        assert display_style == "none"

    def test_tablist_roving_arrow_key_focus(self):
        """ArrowLeft and ArrowRight roving focus with automatic tab activation."""
        self.page.locator("#tab-terminal").click()
        assert self.page.evaluate("document.activeElement.id") == "tab-terminal"

        self.page.keyboard.press("ArrowRight")
        assert self.page.evaluate("document.activeElement.id") == "tab-output"

        self.page.keyboard.press("ArrowRight")
        assert self.page.evaluate("document.activeElement.id") == "tab-problems"

        self.page.keyboard.press("ArrowRight")
        assert self.page.evaluate("document.activeElement.id") == "tab-ports"

        self.page.keyboard.press("ArrowLeft")
        assert self.page.evaluate("document.activeElement.id") == "tab-problems"

    def test_refresh_ports_preserves_focus(self):
        """Refreshing ports preserves focus on active elements inside the ports table."""
        # Open ports tab
        self.page.locator("#tab-ports").click()

        # Add a custom watched port
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

        # Focus the copy button of port 8888
        copy_btn = self.page.locator('button[data-action="copy-port"][data-url="http://127.0.0.1:8888"]')
        copy_btn.focus()
        assert self.page.evaluate("document.activeElement.getAttribute('data-action')") == "copy-port"

        # Trigger re-render / refresh
        self.page.evaluate("window.DeskAIPorts.render();")
        assert self.page.evaluate("document.activeElement.getAttribute('data-action')") == "copy-port"
