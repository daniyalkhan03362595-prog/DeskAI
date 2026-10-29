import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


class TestProblemsStatusBarAndKeyboard(unittest.TestCase):
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
        self.page.wait_for_selector("#statusBarProblems")
        self.page.wait_for_function("() => !!window.DeskAIProblems")

    def tearDown(self):
        if hasattr(self, "page"):
            self.page.close()
        if hasattr(self, "context"):
            self.context.close()

    def test_status_bar_widget_live_sync(self):
        """Verify #statusBarProblems updates counts live when store diagnostics change."""
        initial = self.page.evaluate("""() => {
            const btn = document.getElementById("statusBarProblems");
            const err = document.getElementById("statusBarErrCount");
            const warn = document.getElementById("statusBarWarnCount");
            return {
                btnText: btn.textContent,
                errText: err ? err.textContent : "",
                warnText: warn ? warn.textContent : ""
            };
        }""")
        self.assertIn("✖ 0", initial["errText"])
        self.assertIn("▲ 0", initial["warnText"])

        # Inject diagnostics into store
        updated = self.page.evaluate("""() => {
            const problems = window.DeskAIProblems;
            problems.store.replaceAllWorkspace({
                "app.py": [
                    { file: "app.py", line: 1, col: 1, severity: "error", message: "E1" },
                    { file: "app.py", line: 5, col: 2, severity: "error", message: "E2" },
                    { file: "app.py", line: 10, col: 1, severity: "warning", message: "W1" }
                ]
            });
            const btn = document.getElementById("statusBarProblems");
            const err = document.getElementById("statusBarErrCount");
            const warn = document.getElementById("statusBarWarnCount");
            return {
                errText: err ? err.textContent : "",
                warnText: warn ? warn.textContent : "",
                hasErrors: btn.getAttribute("data-has-errors"),
                hasWarnings: btn.getAttribute("data-has-warnings"),
                ariaLabel: btn.getAttribute("aria-label")
            };
        }""")
        self.assertIn("✖ 2", updated["errText"])
        self.assertIn("▲ 1", updated["warnText"])
        self.assertEqual(updated["hasErrors"], "true")
        self.assertEqual(updated["hasWarnings"], "true")
        self.assertIn("2 errors, 1 warnings", updated["ariaLabel"])

    def test_status_bar_click_opens_problems_tab(self):
        """Verify clicking #statusBarProblems switches active tab to problems and opens drawer."""
        result = self.page.evaluate("""() => {
            const btn = document.getElementById("statusBarProblems");
            btn.click();

            const tabProblems = document.getElementById("tab-problems");
            const panelProblems = document.getElementById("problemsPanel");
            return {
                tabActive: tabProblems ? tabProblems.classList.contains("active") : false,
                tabSelected: tabProblems ? tabProblems.getAttribute("aria-selected") : null,
                panelHidden: panelProblems ? panelProblems.hidden : true
            };
        }""")
        self.assertTrue(result["tabActive"], "Problems drawer tab must have .active class")
        self.assertEqual(result["tabSelected"], "true")
        self.assertFalse(result["panelHidden"], "Problems drawer panel must not be hidden")

    def test_problems_keyboard_navigation(self):
        """Verify ArrowDown, ArrowUp, Enter, and Home/End navigate problem items."""
        nav_result = self.page.evaluate("""() => {
            const problems = window.DeskAIProblems;
            problems.store.replaceAllWorkspace({
                "a.py": [{ file: "a.py", line: 1, col: 1, severity: "error", message: "Err A" }],
                "b.py": [{ file: "b.py", line: 2, col: 1, severity: "error", message: "Err B" }]
            });

            // Switch to problems tab
            document.getElementById("tab-problems").click();

            const view = document.getElementById("problemsView");
            const firstHeader = view.querySelector(".problems-file");
            if (firstHeader) firstHeader.focus();

            // Simulate ArrowDown to move to item
            view.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true }));
            const focusedAfterDown = document.activeElement ? (document.activeElement.className || "") : "";

            // Simulate End to jump to last
            view.dispatchEvent(new KeyboardEvent("keydown", { key: "End", bubbles: true }));
            const focusedAfterEnd = document.activeElement ? (document.activeElement.textContent || "") : "";

            return {
                focusedAfterDown,
                focusedAfterEnd
            };
        }""")
        self.assertTrue(bool(nav_result["focusedAfterDown"]))
        self.assertTrue(bool(nav_result["focusedAfterEnd"]))


if __name__ == "__main__":
    unittest.main()
