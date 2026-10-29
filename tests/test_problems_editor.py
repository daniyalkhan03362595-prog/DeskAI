import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


class TestProblemsEditorDecorations(unittest.TestCase):
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
        self.page.wait_for_selector("#codeEditorHost")
        self.page.wait_for_function("() => !!window.EditorManager && !!window.DeskAIProblems")

    def tearDown(self):
        if hasattr(self, "page"):
            self.page.close()
        if hasattr(self, "context"):
            self.context.close()

    def test_in_editor_gutter_dot_and_squiggle(self):
        """Verify opening a file with diagnostics renders gutter dot and line squiggle."""
        result = self.page.evaluate("""() => {
            const problems = window.DeskAIProblems;
            problems.store.replace("py_syntax", "test_script.py", [
                {
                    file: "test_script.py",
                    line: 2,
                    col: 5,
                    severity: "error",
                    message: "SyntaxError: invalid syntax",
                    source: "py_syntax",
                    code: "E999",
                    ai_fixable: true
                }
            ]);

            const tabId = window.EditorManager.createBuffer(
                "test_script.py",
                "def run():\\n    x = \\n    return x\\n",
                "test_script.py"
            );
            const buf = window.EditorManager.buffers.get(tabId);

            window.DeskAIEditorDiagnostics.update(buf);

            // Check gutter
            const gutterEls = Array.from(buf.container.querySelectorAll(".cm-gutter.cm-lineNumbers .cm-gutterElement"));
            const line2Gutter = gutterEls.find(g => g.textContent.trim() === "2");
            const hasGutterDot = line2Gutter ? line2Gutter.classList.contains("cm-gutter-diagnostic-error") : false;

            // Check line squiggle
            const errorLines = buf.container.querySelectorAll(".cm-line-diagnostic-error");

            return {
                hasGutterDot,
                errorLineCount: errorLines.length,
                lineText: errorLines.length > 0 ? errorLines[0].textContent : null
            };
        }""")

        self.assertTrue(result["hasGutterDot"], "Gutter element on line 2 must have .cm-gutter-diagnostic-error")
        self.assertGreaterEqual(result["errorLineCount"], 1, "Line 2 must have .cm-line-diagnostic-error")
        self.assertIn("x =", result["lineText"])

    def test_editor_hover_tooltip_and_ai_fix(self):
        """Verify hovering over error line triggers tooltip and 'Fix with AI' button populates prompt textarea."""
        result = self.page.evaluate("""() => {
            const problems = window.DeskAIProblems;
            problems.store.replace("py_syntax", "broken.py", [
                {
                    file: "broken.py",
                    line: 1,
                    col: 10,
                    severity: "error",
                    message: "SyntaxError: unexpected EOF",
                    source: "py_syntax",
                    code: "E999",
                    ai_fixable: true
                }
            ]);

            const tabId = window.EditorManager.createBuffer("broken.py", "print('hello'\\n", "broken.py");
            const buf = window.EditorManager.buffers.get(tabId);
            window.DeskAIEditorDiagnostics.update(buf);

            const lineEl = buf.container.querySelector(".cm-line-diagnostic-error");
            window.DeskAIEditorDiagnostics.showTooltip(lineEl, lineEl._diagnosticData);

            const tooltip = document.getElementById("problemEditorTooltip");
            const isVisible = tooltip && tooltip.style.display !== "none";
            const msg = tooltip.querySelector(".problem-tooltip-message").textContent;
            const fixBtn = tooltip.querySelector(".problem-btn-ai-fix");

            fixBtn.click();

            const textarea = document.getElementById("promptTextarea");
            return {
                isVisible,
                msg,
                textareaVal: textarea ? textarea.value : ""
            };
        }""")

        self.assertTrue(result["isVisible"], "Tooltip should be visible on showTooltip")
        self.assertIn("SyntaxError", result["msg"])
        self.assertIn("Fix the following error", result["textareaVal"])
        self.assertIn("broken.py", result["textareaVal"])


if __name__ == "__main__":
    unittest.main()
