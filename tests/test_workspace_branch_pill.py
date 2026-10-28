import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from deskai.bridge.api import DesktopBridgeAPI

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


class TestWorkspaceBranchPillPlaywright(unittest.TestCase):
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
        self.page.wait_for_selector("#headerWorkspacePill")

    def tearDown(self):
        if hasattr(self, "page"):
            self.page.close()
        if hasattr(self, "context"):
            self.context.close()

    def test_wbp_01_initial_state_markup(self):
        """TC-WBP-01: Verifies initial markup: role='status', title, and initial empty text."""
        pill = self.page.locator("#headerWorkspacePill")
        self.assertEqual(pill.get_attribute("role"), "status")
        self.assertEqual(pill.get_attribute("title"), "No active workspace folder")
        self.assertEqual(pill.text_content().strip(), "DeskAI / (no workspace)")
        self.assertEqual(pill.get_attribute("aria-label"), "Workspace: No folder opened")

    def test_wbp_02_reactive_sync_on_root_path_change(self):
        """TC-WBP-02: Verifies reactive update when store.state.workspace.rootPath changes."""
        self.page.evaluate("""() => {
            window.store.state.workspace.branch = null;
            window.store.state.workspace.rootPath = '/mock/workspace/DeskAI';
        }""")

        pill = self.page.locator("#headerWorkspacePill")
        self.assertEqual(pill.text_content().strip(), "DeskAI")
        self.assertEqual(pill.get_attribute("title"), "/mock/workspace/DeskAI")
        self.assertEqual(pill.get_attribute("aria-label"), "Active workspace: DeskAI")
        self.assertIn("has-workspace", pill.get_attribute("class"))

    def test_wbp_03_branch_display_and_aria_label(self):
        """TC-WBP-03: Verifies branch display formatting and accessibility labels."""
        self.page.evaluate("""() => {
            window.store.state.workspace.rootPath = '/mock/workspace/DeskAI';
            window.store.state.workspace.branch = 'feature-awesome';
        }""")

        pill = self.page.locator("#headerWorkspacePill")
        self.assertEqual(pill.text_content().strip(), "DeskAI / feature-awesome")
        self.assertIn("(branch: feature-awesome)", pill.get_attribute("title"))
        self.assertEqual(pill.get_attribute("aria-label"), "Active workspace: DeskAI, branch: feature-awesome")

        # Nested project path
        self.page.evaluate("""() => {
            window.store.state.workspace.rootPath = '/home/user/code/my-project';
            window.store.state.workspace.branch = 'main';
        }""")
        self.assertEqual(pill.text_content().strip(), "DeskAI / my-project / main")

    def test_wbp_04_no_drag_property(self):
        """TC-WBP-04: Verifies -webkit-app-region is 'no-drag' so pill does not capture window drag."""
        drag_prop = self.page.evaluate("""() => {
            const el = document.getElementById('headerWorkspacePill');
            return window.getComputedStyle(el).webkitAppRegion;
        }""")
        self.assertEqual(drag_prop, "no-drag")

    def test_wbp_05_text_truncation_styling(self):
        """TC-WBP-05: Verifies CSS text-overflow ellipsis and whitespace nowrap."""
        truncation = self.page.evaluate("""() => {
            const el = document.getElementById('headerWorkspacePill');
            const comp = window.getComputedStyle(el);
            return {
                textOverflow: comp.textOverflow,
                whiteSpace: comp.whiteSpace,
                overflow: comp.overflow
            };
        }""")
        self.assertEqual(truncation["textOverflow"], "ellipsis")
        self.assertEqual(truncation["whiteSpace"], "nowrap")
        self.assertEqual(truncation["overflow"], "hidden")


class TestWorkspaceBranchPillBackend(unittest.TestCase):
    def setUp(self):
        self.mock_manager = MagicMock()
        self.mock_window = MagicMock()
        self.mock_window.title = "DeskAI Window"
        self.mock_manager.window = self.mock_window
        self.mock_manager.server.port = 8000
        self.mock_window.get_current_url.return_value = "http://127.0.0.1:8000/"
        self.api = DesktopBridgeAPI(self.mock_manager)

    def test_wbp_06_backend_git_branch_resolution(self):
        """TC-WBP-06: Verifies get_git_branch on current repository, non-git dir, and detached HEAD."""
        # 1. DeskAI itself is a git repository
        res = self.api.get_git_branch(str(Path.cwd()))
        self.assertEqual(res["status"], "ok")
        self.assertIsNotNone(res["branch"])

        # 2. Non-git directory
        with tempfile.TemporaryDirectory() as tmpdir:
            res_non_git = self.api.get_git_branch(tmpdir)
            self.assertEqual(res_non_git["status"], "ok")
            self.assertIsNone(res_non_git["branch"])

            # 3. Simulated git repo with branch
            git_dir = Path(tmpdir) / ".git"
            git_dir.mkdir()
            (git_dir / "HEAD").write_text("ref: refs/heads/release-1.0\n", encoding="utf-8")
            res_branch = self.api.get_git_branch(tmpdir)
            self.assertEqual(res_branch["status"], "ok")
            self.assertEqual(res_branch["branch"], "release-1.0")

            # 4. Simulated detached HEAD
            (git_dir / "HEAD").write_text("1a2b3c4d5e6f7a8b9c0d\n", encoding="utf-8")
            res_detached = self.api.get_git_branch(tmpdir)
            self.assertEqual(res_detached["status"], "ok")
            self.assertEqual(res_detached["branch"], "1a2b3c4")

    def test_wbp_07_backend_origin_guard(self):
        """TC-WBP-07: Verifies get_git_branch rejects calls from unauthorized origin."""
        self.mock_window.get_current_url.return_value = "http://evil.com/"
        res = self.api.get_git_branch(str(Path.cwd()))
        self.assertEqual(res["status"], "error")
        self.assertIsNone(res["branch"])


if __name__ == "__main__":
    unittest.main()
