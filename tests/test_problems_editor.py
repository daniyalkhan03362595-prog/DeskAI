"""Integration tests for Problems panel editor navigation and hooks (M4)."""

import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


class TestProblemsEditor(unittest.TestCase):
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
        self.page.wait_for_function("() => !!window.EditorManager && !!window.DeskAIProblems")

    def tearDown(self):
        if hasattr(self, "page"):
            self.page.close()
        if hasattr(self, "context"):
            self.context.close()

    def test_tc_prb_editor_open_at_and_reveal(self):
        """TC-PRB-M4-01: openAt opens buffer and places CodeMirror cursor at line and column."""
        res = self.page.evaluate("""async () => {
            const content = "line 1\\nline 2 hello\\nline 3 world\\n";
            window.NativeBridge.readFile = async () => ({
                status: "ok",
                content: content,
                is_binary: false
            });

            const success = await window.EditorManager.openAt("/workspace/demo.txt", 2, 8);
            const activeId = window.EditorManager.activeTabId;
            const buf = window.EditorManager.buffers.get(activeId);
            const view = buf.view;
            const sel = view.state.selection.main;
            const lineInfo = view.state.doc.lineAt(sel.head);

            return {
                success,
                lineNumber: lineInfo.number,
                columnNumber: sel.head - lineInfo.from + 1
            };
        }""")

        self.assertTrue(res["success"])
        self.assertEqual(res["lineNumber"], 2)
        self.assertEqual(res["columnNumber"], 8)

    def test_tc_prb_editor_save_hook_triggers_problems(self):
        """TC-PRB-M4-02: saveBuffer triggers window.DeskAIProblems.onFileSaved."""
        res = self.page.evaluate("""async () => {
            window.store.state.workspace.rootPath = "/workspace";
            let savedPath = null;
            window.DeskAIProblems.onFileSaved = (p) => {
                savedPath = p;
            };

            const tabId = window.EditorManager.createBuffer("demo.py", "a = 1", "/workspace/demo.py");
            window.EditorManager.markDirty(tabId, true);

            window.NativeBridge.writeFile = async () => ({ status: "ok" });
            await window.EditorManager.saveBuffer(tabId);

            return { savedPath };
        }""")

        self.assertEqual(res["savedPath"], "/workspace/demo.py")

    def test_tc_prb_workspace_reset_clears_problems(self):
        """TC-PRB-M4-03: Changing workspace.rootPath resets ProblemsManager store."""
        res = self.page.evaluate("""() => {
            window.DeskAIProblems.store.replace("python", "test.py", [
                {
                    id: "mock1",
                    source: "python",
                    code: "E1",
                    severity: "error",
                    message: "bad",
                    file: "test.py",
                    range: { startLine: 1, startCol: 1, endLine: 1, endCol: 2 }
                }
            ]);

            const countBefore = window.DeskAIProblems.store.counts().errors;
            window.store.state.workspace.rootPath = "/new/workspace";
            const countAfter = window.DeskAIProblems.store.counts().errors;

            return { countBefore, countAfter };
        }""")

        self.assertEqual(res["countBefore"], 1)
        self.assertEqual(res["countAfter"], 0)


if __name__ == "__main__":
    unittest.main()
