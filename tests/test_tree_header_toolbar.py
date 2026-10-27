import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


class TestTreeHeaderToolbar(unittest.TestCase):
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
        self.page.wait_for_selector("#explorerToolbar")

    def tearDown(self):
        if hasattr(self, "page"):
            self.page.close()
        if hasattr(self, "context"):
            self.context.close()

    def test_tht_01_toolbar_semantics_and_a11y(self):
        """TC-THT-01: Verifies .panel-actions has role='toolbar' and accessible names."""
        toolbar = self.page.locator("#explorerToolbar")
        self.assertEqual(toolbar.get_attribute("role"), "toolbar")
        self.assertEqual(toolbar.get_attribute("aria-label"), "Explorer Actions")
        self.assertEqual(toolbar.get_attribute("aria-controls"), "fileTreeViewport")

        buttons = toolbar.locator("button.icon-btn")
        self.assertEqual(buttons.count(), 4)

        btn_new_file = toolbar.locator("#btnNewFile")
        self.assertEqual(btn_new_file.get_attribute("aria-label"), "New File")
        self.assertEqual(btn_new_file.get_attribute("tabindex"), "0")

        btn_new_folder = toolbar.locator("#btnNewFolder")
        self.assertEqual(btn_new_folder.get_attribute("aria-label"), "New Folder")
        self.assertEqual(btn_new_folder.get_attribute("tabindex"), "-1")

        btn_refresh = toolbar.locator("#btnRefreshTree")
        self.assertEqual(btn_refresh.get_attribute("aria-label"), "Refresh Tree")
        self.assertEqual(btn_refresh.get_attribute("tabindex"), "-1")

        btn_collapse = toolbar.locator("#btnCollapseAll")
        self.assertEqual(btn_collapse.get_attribute("aria-label"), "Collapse All Folders")
        self.assertEqual(btn_collapse.get_attribute("tabindex"), "-1")

    def test_tht_02_new_file_action_dispatch(self):
        """TC-THT-02: Clicking new-file prompts for filename, writes file, and opens tab."""
        res = self.page.evaluate("""async () => {
            window.prompt = () => "hello.py";
            let writtenPath = null;
            let writtenContent = null;
            let openedPath = null;

            window.NativeBridge.writeFile = async (path, content) => {
                writtenPath = path;
                writtenContent = content;
                return { status: "ok" };
            };
            window.EditorManager.openFile = async (path) => {
                openedPath = path;
                return "tab-hello";
            };

            const btn = document.getElementById("btnNewFile");
            btn.click();

            // Allow async event delegation tick
            await new Promise(r => setTimeout(r, 50));

            return {
                writtenPath,
                writtenContent,
                openedPath
            };
        }""")

        self.assertIn("hello.py", res["writtenPath"])
        self.assertEqual(res["writtenContent"], "")
        self.assertEqual(res["openedPath"], res["writtenPath"])

    def test_tht_03_new_folder_action_dispatch(self):
        """TC-THT-03: Clicking new-folder prompts for folder name and calls createDir."""
        res = self.page.evaluate("""async () => {
            window.prompt = () => "components";
            let createdPath = null;

            window.NativeBridge.createDir = async (path) => {
                createdPath = path;
                return { status: "ok" };
            };

            const btn = document.getElementById("btnNewFolder");
            btn.click();

            await new Promise(r => setTimeout(r, 50));

            return { createdPath };
        }""")

        self.assertIn("components", res["createdPath"])

    def test_tht_04_refresh_tree_action_dispatch(self):
        """TC-THT-04: Clicking refresh-tree queries NativeBridge.listDir and re-renders tree."""
        res = self.page.evaluate("""async () => {
            let listDirCalled = false;
            window.NativeBridge.listDir = async () => {
                listDirCalled = true;
                return {
                    status: "ok",
                    entries: [
                        { name: "main.py", is_dir: false, path: "/workspace/main.py" },
                        { name: "docs", is_dir: true, path: "/workspace/docs" }
                    ]
                };
            };

            const btn = document.getElementById("btnRefreshTree");
            btn.click();

            await new Promise(r => setTimeout(r, 50));

            const items = document.querySelectorAll("#fileTreeViewport .tree-item");
            return {
                listDirCalled,
                itemCount: items.length,
                labels: Array.from(items).map(i => i.querySelector(".tree-label").textContent)
            };
        }""")

        self.assertTrue(res["listDirCalled"])
        self.assertEqual(res["itemCount"], 2)
        self.assertEqual(res["labels"], ["main.py", "docs"])

    def test_tht_05_collapse_all_action_dispatch(self):
        """TC-THT-05: Clicking collapse-all-folders empties expandedDirs set and renders."""
        res = self.page.evaluate("""() => {
            window.ExplorerManager.expandedDirs.add("/workspace/docs");
            window.ExplorerManager.expandedDirs.add("/workspace/src");
            const countBefore = window.ExplorerManager.expandedDirs.size;

            const btn = document.getElementById("btnCollapseAll");
            btn.click();

            return {
                countBefore,
                countAfter: window.ExplorerManager.expandedDirs.size
            };
        }""")

        self.assertEqual(res["countBefore"], 2)
        self.assertEqual(res["countAfter"], 0)

    def test_tht_06_toolbar_roving_keyboard_navigation(self):
        """TC-THT-06: Arrow keys rove focus across toolbar buttons and update tabindex."""
        btn_new_file = self.page.locator("#btnNewFile")
        btn_new_folder = self.page.locator("#btnNewFolder")
        btn_refresh = self.page.locator("#btnRefreshTree")
        btn_collapse = self.page.locator("#btnCollapseAll")

        btn_new_file.focus()
        self.assertEqual(btn_new_file.get_attribute("tabindex"), "0")

        self.page.keyboard.press("ArrowRight")
        self.assertEqual(btn_new_folder.get_attribute("tabindex"), "0")
        self.assertEqual(btn_new_file.get_attribute("tabindex"), "-1")

        self.page.keyboard.press("ArrowRight")
        self.assertEqual(btn_refresh.get_attribute("tabindex"), "0")

        self.page.keyboard.press("End")
        self.assertEqual(btn_collapse.get_attribute("tabindex"), "0")

        self.page.keyboard.press("Home")
        self.assertEqual(btn_new_file.get_attribute("tabindex"), "0")
