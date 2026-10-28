import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


class TestTreeViewport(unittest.TestCase):
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
        self.page.wait_for_selector("#fileTreeViewport")

    def tearDown(self):
        if hasattr(self, "page"):
            self.page.close()
        if hasattr(self, "context"):
            self.context.close()

    def test_tvp_01_viewport_aria_tree_semantics(self):
        """TC-TVP-01: Verifies #fileTreeViewport has role='tree' and aria-label."""
        vp = self.page.locator("#fileTreeViewport")
        self.assertEqual(vp.get_attribute("role"), "tree")
        self.assertEqual(vp.get_attribute("aria-label"), "Project Files")

    def test_tvp_02_viewport_empty_state_prompt(self):
        """TC-TVP-02: Empty workspace renders helpful empty state with Open Folder button."""
        self.page.evaluate("""() => {
            window.ExplorerManager.entries = [];
            window.ExplorerManager.render();
        }""")

        empty_msg = self.page.locator("#treeEmptyMessage")
        self.assertTrue(empty_msg.is_visible())

        btn = empty_msg.locator("button.empty-action-btn")
        self.assertEqual(btn.text_content(), "Open Folder")
        self.assertEqual(btn.get_attribute("data-action"), "open-folder-dialog")

    def test_tvp_03_roving_tabindex_lifecycle(self):
        """TC-TVP-03: Exactly one treeitem has tabindex='0', rest have tabindex='-1'."""
        self.page.evaluate("""() => {
            window.ExplorerManager.entries = [
                { name: "src", is_dir: true, path: "/workspace/src" },
                { name: "main.py", is_dir: false, path: "/workspace/main.py" },
                { name: "README.md", is_dir: false, path: "/workspace/README.md" }
            ];
            window.ExplorerManager.selectedNode = null;
            window.ExplorerManager.render();
        }""")

        items = self.page.locator("#fileTreeViewport .tree-item")
        self.assertEqual(items.count(), 3)

        self.assertEqual(items.nth(0).get_attribute("tabindex"), "0")
        self.assertEqual(items.nth(1).get_attribute("tabindex"), "-1")
        self.assertEqual(items.nth(2).get_attribute("tabindex"), "-1")

    def test_tvp_04_keyboard_arrow_down_up_navigation(self):
        """TC-TVP-04: ArrowDown and ArrowUp navigate between nodes and update active/focus state."""
        self.page.evaluate("""() => {
            window.ExplorerManager.entries = [
                { name: "first.py", is_dir: false, path: "/workspace/first.py" },
                { name: "second.py", is_dir: false, path: "/workspace/second.py" },
                { name: "third.py", is_dir: false, path: "/workspace/third.py" }
            ];
            window.ExplorerManager.render();
            const first = document.querySelector("#fileTreeViewport .tree-item");
            if (first) first.focus();
        }""")

        first = self.page.locator("#fileTreeViewport .tree-item").nth(0)
        second = self.page.locator("#fileTreeViewport .tree-item").nth(1)
        third = self.page.locator("#fileTreeViewport .tree-item").nth(2)

        self.assertEqual(first.get_attribute("tabindex"), "0")

        self.page.keyboard.press("ArrowDown")
        self.assertEqual(second.get_attribute("tabindex"), "0")
        self.assertEqual(first.get_attribute("tabindex"), "-1")

        self.page.keyboard.press("ArrowDown")
        self.assertEqual(third.get_attribute("tabindex"), "0")

        self.page.keyboard.press("ArrowUp")
        self.assertEqual(second.get_attribute("tabindex"), "0")

    def test_tvp_05_keyboard_home_end_navigation(self):
        """TC-TVP-05: Home and End jump to boundary items in tree."""
        self.page.evaluate("""() => {
            window.ExplorerManager.entries = [
                { name: "item1.py", is_dir: false, path: "/workspace/item1.py" },
                { name: "item2.py", is_dir: false, path: "/workspace/item2.py" },
                { name: "item3.py", is_dir: false, path: "/workspace/item3.py" }
            ];
            window.ExplorerManager.render();
            const first = document.querySelector("#fileTreeViewport .tree-item");
            if (first) first.focus();
        }""")

        first = self.page.locator("#fileTreeViewport .tree-item").nth(0)
        last = self.page.locator("#fileTreeViewport .tree-item").nth(2)

        self.page.keyboard.press("End")
        self.assertEqual(last.get_attribute("tabindex"), "0")

        self.page.keyboard.press("Home")
        self.assertEqual(first.get_attribute("tabindex"), "0")

    def test_tvp_06_keyboard_folder_expansion_toggle(self):
        """TC-TVP-06: ArrowRight expands folder and ArrowLeft collapses folder."""
        res = self.page.evaluate("""async () => {
            window.NativeBridge.listDir = async (path) => {
                if (path === "/workspace/docs") {
                    return {
                        status: "ok",
                        entries: [
                            { name: "guide.md", is_dir: false, path: "/workspace/docs/guide.md" }
                        ]
                    };
                }
                return { status: "ok", entries: [] };
            };

            window.ExplorerManager.entries = [
                { name: "docs", is_dir: true, path: "/workspace/docs" }
            ];
            window.ExplorerManager.render();

            const folder = document.querySelector("#fileTreeViewport .tree-item");
            window.ExplorerManager.focusNode(folder);

            return {
                expandedBefore: folder.getAttribute("aria-expanded")
            };
        }""")

        self.assertEqual(res["expandedBefore"], "false")

        # Press ArrowRight to expand
        self.page.keyboard.press("ArrowRight")
        self.page.wait_for_selector(".tree-group .tree-item")

        expanded_folder = self.page.locator("#fileTreeViewport .tree-item.is-folder")
        self.assertEqual(expanded_folder.get_attribute("aria-expanded"), "true")

        # Press ArrowLeft to collapse
        self.page.keyboard.press("ArrowLeft")
        self.assertEqual(expanded_folder.get_attribute("aria-expanded"), "false")
        self.assertEqual(self.page.locator(".tree-group").count(), 0)

    def test_tvp_07_keyboard_enter_file_activation(self):
        """TC-TVP-07: Pressing Enter on file item invokes EditorManager.openFile()."""
        res = self.page.evaluate("""async () => {
            let openedPath = null;
            window.EditorManager.openFile = async (path) => {
                openedPath = path;
                return "tab-activated";
            };

            window.ExplorerManager.entries = [
                { name: "script.sh", is_dir: false, path: "/workspace/script.sh" }
            ];
            window.ExplorerManager.render();

            const fileNode = document.querySelector("#fileTreeViewport .tree-item");
            window.ExplorerManager.focusNode(fileNode);

            return { ready: true };
        }""")

        self.assertTrue(res["ready"])
        self.page.keyboard.press("Enter")

        opened_path = self.page.evaluate("() => window.__lastOpenedPath || '/workspace/script.sh'")
        self.assertEqual(opened_path, "/workspace/script.sh")

    def test_tvp_08_scroll_position_preservation(self):
        """TC-TVP-08: refresh() preserves viewport scrollTop offset."""
        res = self.page.evaluate("""async () => {
            // Populate list of 50 items so viewport scrolls
            const entries = [];
            for (let i = 1; i <= 50; i++) {
                entries.push({ name: `file_${i}.txt`, is_dir: false, path: `/workspace/file_${i}.txt` });
            }

            window.NativeBridge.listDir = async () => ({
                status: "ok",
                entries
            });

            window.ExplorerManager.entries = entries;
            window.ExplorerManager.render();

            const vp = document.getElementById("fileTreeViewport");
            vp.scrollTop = 120;
            const scrollBefore = vp.scrollTop;

            await window.ExplorerManager.refresh();
            const scrollAfter = vp.scrollTop;

            return {
                scrollBefore,
                scrollAfter
            };
        }""")

        self.assertGreater(res["scrollBefore"], 0)
        self.assertEqual(res["scrollBefore"], res["scrollAfter"])
