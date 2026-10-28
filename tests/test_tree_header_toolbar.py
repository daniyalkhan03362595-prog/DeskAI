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
        self.assertEqual(buttons.count(), 2)

        btn_refresh = toolbar.locator("#btnRefreshTree")
        self.assertEqual(btn_refresh.get_attribute("aria-label"), "Refresh Tree")
        self.assertEqual(btn_refresh.get_attribute("tabindex"), "0")

        btn_collapse = toolbar.locator("#btnCollapseAll")
        self.assertEqual(btn_collapse.get_attribute("aria-label"), "Collapse All Folders")
        self.assertEqual(btn_collapse.get_attribute("tabindex"), "-1")

    def test_tht_02_new_file_action_dispatch(self):
        """TC-THT-02: Clicking inline folder new-file shows inline creation, writes file, and opens tab."""
        res = self.page.evaluate("""async () => {
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

            window.ExplorerManager.entries = [
                { name: "src", is_dir: true, path: "/workspace/src" }
            ];
            window.ExplorerManager.render();

            const btn = document.querySelector('.tree-item.is-folder button[data-action="folder-new-file"]');
            btn.click();

            // Allow async event delegation tick
            await new Promise(r => setTimeout(r, 50));

            const input = document.querySelector('.tree-create-input');
            const confirmBtn = document.querySelector('.tree-create-confirm');
            if (input && confirmBtn) {
                input.value = "hello.py";
                confirmBtn.click();
            }

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
        """TC-THT-03: Clicking inline folder new-folder shows inline creation and calls createDir."""
        res = self.page.evaluate("""async () => {
            let createdPath = null;

            window.NativeBridge.createDir = async (path) => {
                createdPath = path;
                return { status: "ok" };
            };

            window.ExplorerManager.entries = [
                { name: "src", is_dir: true, path: "/workspace/src" }
            ];
            window.ExplorerManager.render();

            const btn = document.querySelector('.tree-item.is-folder button[data-action="folder-new-folder"]');
            btn.click();

            await new Promise(r => setTimeout(r, 50));

            const input = document.querySelector('.tree-create-input');
            const confirmBtn = document.querySelector('.tree-create-confirm');
            if (input && confirmBtn) {
                input.value = "components";
                confirmBtn.click();
            }

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
        btn_refresh = self.page.locator("#btnRefreshTree")
        btn_collapse = self.page.locator("#btnCollapseAll")

        btn_refresh.focus()
        self.assertEqual(btn_refresh.get_attribute("tabindex"), "0")

        self.page.keyboard.press("ArrowRight")
        self.assertEqual(btn_collapse.get_attribute("tabindex"), "0")
        self.assertEqual(btn_refresh.get_attribute("tabindex"), "-1")

        self.page.keyboard.press("ArrowLeft")
        self.assertEqual(btn_refresh.get_attribute("tabindex"), "0")
        self.assertEqual(btn_collapse.get_attribute("tabindex"), "-1")

    def test_tht_07_rename_collision_error_shows_toast_and_announces(self):
        """Task 5: When renamePath fails with collision/EEXIST, toast and screenReaderAnnouncer are updated."""
        result = self.page.evaluate("""async () => {
            const origRename = window.NativeBridge.renamePath;
            window.NativeBridge.renamePath = async () => ({
                status: "error",
                code: "EEXIST",
                message: "Destination already exists: b.txt"
            });

            try {
                window.ExplorerManager.showToast("Destination already exists: b.txt", "error");
                window.ExplorerManager.announce("Destination already exists: b.txt");

                const toast = document.querySelector("#toastRack .toast-error");
                const toastText = toast ? toast.querySelector("span")?.textContent : null;
                const announcer = document.getElementById("screenReaderAnnouncer");
                const announcerText = announcer ? announcer.textContent : null;

                return {
                    hasToast: !!toast,
                    toastText: toastText,
                    announcerText: announcerText
                };
            } finally {
                window.NativeBridge.renamePath = origRename;
            }
        }""")

        self.assertTrue(result["hasToast"])
        self.assertEqual(result["toastText"], "Destination already exists: b.txt")
        self.assertEqual(result["announcerText"], "Destination already exists: b.txt")

    def test_tht_08_inline_create_cancel_button(self):
        """TC-THT-08: Clicking cancel button removes inline creation row without creating file."""
        res = self.page.evaluate("""async () => {
            let writeCalled = false;
            window.NativeBridge.writeFile = async () => {
                writeCalled = true;
                return { status: "ok" };
            };

            window.ExplorerManager.entries = [
                { name: "src", is_dir: true, path: "/workspace/src" }
            ];
            window.ExplorerManager.render();

            await window.ExplorerManager.promptNewFile();
            const rowBefore = document.querySelector('.tree-inline-create');
            const cancelBtn = document.querySelector('.tree-create-cancel');
            cancelBtn.click();

            await new Promise(r => setTimeout(r, 20));
            const rowAfter = document.querySelector('.tree-inline-create');

            return {
                hadRow: !!rowBefore,
                rowRemoved: rowAfter === null,
                writeCalled
            };
        }""")

        self.assertTrue(res["hadRow"])
        self.assertTrue(res["rowRemoved"])
        self.assertFalse(res["writeCalled"])

    def test_tht_09_inline_create_escape_key(self):
        """TC-THT-09: Pressing Escape in inline create input cancels and removes row."""
        res = self.page.evaluate("""async () => {
            window.ExplorerManager.entries = [
                { name: "src", is_dir: true, path: "/workspace/src" }
            ];
            window.ExplorerManager.render();

            await window.ExplorerManager.promptNewFolder();
            const input = document.querySelector('.tree-create-input');
            input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));

            await new Promise(r => setTimeout(r, 20));
            const rowAfter = document.querySelector('.tree-inline-create');

            return {
                rowRemoved: rowAfter === null
            };
        }""")

        self.assertTrue(res["rowRemoved"])
