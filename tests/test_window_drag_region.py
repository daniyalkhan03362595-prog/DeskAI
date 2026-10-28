import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


class TestWindowDragRegion(unittest.TestCase):
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
        self.page.wait_for_function("typeof window.NativeBridge !== 'undefined'")

    def tearDown(self):
        if hasattr(self, "page"):
            self.page.close()
        if hasattr(self, "context"):
            self.context.close()

    def test_wdr_01_drag_region_computed_styles(self):
        """TC-WDR-01: Verifies #appHeader has webkitAppRegion 'drag' and user-select 'none'."""
        styles = self.page.evaluate("""() => {
            const h = document.getElementById('appHeader');
            const comp = window.getComputedStyle(h);
            return {
                appRegion: comp.webkitAppRegion,
                userSelect: comp.userSelect
            };
        }""")
        self.assertEqual(styles["appRegion"], "drag")
        self.assertEqual(styles["userSelect"], "none")

    def test_wdr_02_no_drag_interactive_elements(self):
        """TC-WDR-02: Verifies interactive controls in header have webkitAppRegion 'no-drag'."""
        controls_app_region = self.page.evaluate("""() => {
            const pill = document.getElementById('headerWorkspacePill');
            const winBtn = document.querySelector('.win-btn');
            const controls = document.querySelector('.header-right');
            return {
                pill: window.getComputedStyle(pill).webkitAppRegion,
                winBtn: window.getComputedStyle(winBtn).webkitAppRegion,
                controls: window.getComputedStyle(controls).webkitAppRegion
            };
        }""")
        self.assertEqual(controls_app_region["pill"], "no-drag")
        self.assertEqual(controls_app_region["winBtn"], "no-drag")
        self.assertEqual(controls_app_region["controls"], "no-drag")

    def test_wdr_03_mousedown_triggers_drag_start(self):
        """TC-WDR-03: Mousedown on empty header region dispatches drag_start."""
        self.page.evaluate("""() => {
            window._bridgeCalls = [];
            window.NativeBridge.windowControl = async (...args) => {
                window._bridgeCalls.push(args);
                return true;
            };
        }""")

        # Dispatch mousedown on #appHeader (left click, button=0)
        self.page.evaluate("""() => {
            const h = document.getElementById('appHeader');
            const evt = new MouseEvent('mousedown', {
                button: 0,
                bubbles: true,
                cancelable: true
            });
            h.dispatchEvent(evt);
        }""")

        calls = self.page.evaluate("() => window._bridgeCalls")
        self.assertTrue(len(calls) > 0)
        self.assertEqual(calls[0][0], "drag_start")

    def test_wdr_04_mousedown_on_buttons_ignored(self):
        """TC-WDR-04: Mousedown on buttons or workspace pill does NOT trigger drag_start."""
        self.page.evaluate("""() => {
            window._bridgeCalls = [];
            window.NativeBridge.windowControl = async (...args) => {
                window._bridgeCalls.push(args);
                return true;
            };
        }""")

        # Mousedown on .win-min button
        self.page.evaluate("""() => {
            const btn = document.querySelector('.win-min');
            btn.dispatchEvent(new MouseEvent('mousedown', { button: 0, bubbles: true }));
        }""")

        calls = self.page.evaluate("() => window._bridgeCalls")
        self.assertEqual(len(calls), 0)

        # Mousedown on .workspace-pill
        self.page.evaluate("""() => {
            const pill = document.getElementById('headerWorkspacePill');
            pill.dispatchEvent(new MouseEvent('mousedown', { button: 0, bubbles: true }));
        }""")

        calls_after_pill = self.page.evaluate("() => window._bridgeCalls")
        self.assertEqual(len(calls_after_pill), 0)

    def test_wdr_05_dblclick_triggers_maximize(self):
        """TC-WDR-05: Double clicking on empty header space dispatches maximize."""
        self.page.evaluate("""() => {
            window._bridgeCalls = [];
            window.NativeBridge.windowControl = async (...args) => {
                window._bridgeCalls.push(args);
                return true;
            };
        }""")

        self.page.evaluate("""() => {
            const h = document.getElementById('appHeader');
            h.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true }));
        }""")

        calls = self.page.evaluate("() => window._bridgeCalls")
        self.assertTrue(any(call[0] == "maximize" for call in calls))

    def test_wdr_06_dblclick_on_interactive_ignored(self):
        """TC-WDR-06: Double clicking on .workspace-pill or .win-close does NOT dispatch maximize."""
        self.page.evaluate("""() => {
            window._bridgeCalls = [];
            window.NativeBridge.windowControl = async (...args) => {
                window._bridgeCalls.push(args);
                return true;
            };
        }""")

        # Dblclick on workspace pill
        self.page.evaluate("""() => {
            const pill = document.getElementById('headerWorkspacePill');
            pill.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
        }""")

        # Dblclick on win-close
        self.page.evaluate("""() => {
            const closeBtn = document.querySelector('.win-close');
            closeBtn.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
        }""")

        calls = self.page.evaluate("() => window._bridgeCalls")
        self.assertEqual(len(calls), 0)

    def test_wdr_07_right_click_ignored(self):
        """TC-WDR-07: Right clicking (button: 2) on header does NOT dispatch drag_start."""
        self.page.evaluate("""() => {
            window._bridgeCalls = [];
            window.NativeBridge.windowControl = async (...args) => {
                window._bridgeCalls.push(args);
                return true;
            };
        }""")

        self.page.evaluate("""() => {
            const h = document.getElementById('appHeader');
            h.dispatchEvent(new MouseEvent('mousedown', { button: 2, bubbles: true }));
        }""")

        calls = self.page.evaluate("() => window._bridgeCalls")
        self.assertEqual(len(calls), 0)


if __name__ == "__main__":
    unittest.main()
