import os
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
        # 1. DeskAI itself is a git repository within workspace root
        self.api.workspace_root = str(Path.cwd())
        res = self.api.get_git_branch(str(Path.cwd()))
        self.assertEqual(res["status"], "ok")
        self.assertIsNotNone(res["branch"])

        # 2. Non-git directory
        with tempfile.TemporaryDirectory() as tmpdir:
            self.api.workspace_root = tmpdir
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
        self.api.workspace_root = str(Path.cwd())
        self.mock_window.get_current_url.return_value = "http://evil.com/"
        res = self.api.get_git_branch(str(Path.cwd()))
        self.assertEqual(res["status"], "error")
        self.assertIsNone(res["branch"])

    def test_wbp_08_sandboxed_get_git_branch_and_gitdir(self):
        """Task 3: get_git_branch sandbox enforcement: outside repo denied, outside gitdir denied, valid worktree ok."""
        with tempfile.TemporaryDirectory() as temp_dir:
            ws_root = os.path.join(temp_dir, "workspace")
            os.makedirs(ws_root)
            self.api.workspace_root = ws_root

            outside_repo = os.path.join(temp_dir, "outside_repo")
            outside_git = os.path.join(outside_repo, ".git")
            os.makedirs(outside_git)
            (Path(outside_git) / "HEAD").write_text("ref: refs/heads/outside-branch\n", encoding="utf-8")

            # 1. Outside repo is denied
            res_outside = self.api.get_git_branch(outside_repo)
            self.assertEqual(res_outside["status"], "error")
            self.assertIn("Access denied", res_outside["message"])

            # 2. Inside repo with gitdir pointing outside is denied
            inside_repo = os.path.join(ws_root, "inside_repo")
            os.makedirs(inside_repo)
            inside_git_file = Path(inside_repo) / ".git"
            inside_git_file.write_text(f"gitdir: {outside_git}\n", encoding="utf-8")

            res_gitdir_out = self.api.get_git_branch(inside_repo)
            self.assertEqual(res_gitdir_out["status"], "error")
            self.assertIn("Access denied", res_gitdir_out["message"])

            # 3. Worktree pointing to valid gitdir inside workspace root works
            main_repo_git = os.path.join(ws_root, "main_repo", ".git")
            wt_git_dir = os.path.join(main_repo_git, "worktrees", "wt1")
            os.makedirs(wt_git_dir)
            (Path(wt_git_dir) / "HEAD").write_text("ref: refs/heads/feature-worktree\n", encoding="utf-8")

            wt_repo = os.path.join(ws_root, "wt_repo")
            os.makedirs(wt_repo)
            (Path(wt_repo) / ".git").write_text(f"gitdir: {wt_git_dir}\n", encoding="utf-8")

            res_wt = self.api.get_git_branch(wt_repo)
            self.assertEqual(res_wt["status"], "ok")
            self.assertEqual(res_wt["branch"], "feature-worktree")


if __name__ == "__main__":
    unittest.main()
