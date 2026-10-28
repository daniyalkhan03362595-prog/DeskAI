import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


class TestContextMenuActions(unittest.TestCase):
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

    def test_cma_01_context_menu_right_click_invocation(self):
        """TC-CMA-01: Right-clicking treeitem opens #treeContextMenu at pointer coordinates."""
        self.page.evaluate("""() => {
            window.ExplorerManager.entries = [
                { name: "main.py", is_dir: false, path: "/workspace/main.py" }
            ];
            window.ExplorerManager.render();
        }""")

        item = self.page.locator("#fileTreeViewport .tree-item").first
        item.click(button="right")

        menu = self.page.locator("#treeContextMenu")
        self.assertTrue(menu.is_visible())
        self.assertEqual(menu.get_attribute("role"), "menu")
        self.assertEqual(menu.get_attribute("aria-label"), "File Actions")

        menu_items = menu.locator(".menu-item")
        self.assertEqual(menu_items.count(), 6)

    def test_cma_02_context_menu_keyboard_shift_f10(self):
        """TC-CMA-02: Pressing Shift+F10 on focused tree item opens context menu."""
        self.page.evaluate("""() => {
            window.ExplorerManager.entries = [
                { name: "config.json", is_dir: false, path: "/workspace/config.json" }
            ];
            window.ExplorerManager.render();
            const node = document.querySelector("#fileTreeViewport .tree-item");
            window.ExplorerManager.focusNode(node);
        }""")

        self.page.keyboard.press("Shift+F10")
        menu = self.page.locator("#treeContextMenu")
        self.assertTrue(menu.is_visible())

    def test_cma_03_context_menu_clamping_to_viewport(self):
        """TC-CMA-03: Context menu coordinates clamp so popup remains within viewport bounds."""
        res = self.page.evaluate("""() => {
            // Request coordinates near bottom-right edge of 1280x800 viewport
            window.ExplorerManager.showContextMenu(1270, 790, { path: "/workspace/a.txt", isDir: false });

            const menu = document.getElementById("treeContextMenu");
            const rect = menu.getBoundingClientRect();
            return {
                right: rect.right,
                bottom: rect.bottom,
                windowWidth: window.innerWidth,
                windowHeight: window.innerHeight
            };
        }""")

        self.assertLessEqual(res["right"], res["windowWidth"])
        self.assertLessEqual(res["bottom"], res["windowHeight"])

    def test_cma_04_copy_path_and_relative_path(self):
        """TC-CMA-04: Clicking Copy Path and Copy Relative Path writes to clipboard."""
        res = self.page.evaluate("""async () => {
            let lastCopied = null;
            Object.defineProperty(navigator, 'clipboard', {
                value: {
                    writeText: async (text) => {
                        lastCopied = text;
                    }
                },
                configurable: true,
                writable: true
            });
            window.store.state.workspace.rootPath = "/workspace";

            window.ExplorerManager.entries = [
                { name: "test.py", is_dir: false, path: "/workspace/tests/test.py" }
            ];
            window.ExplorerManager.render();

            const target = { path: "/workspace/tests/test.py", isDir: false };

            // Copy Path
            window.ExplorerManager.showContextMenu(100, 100, target);
            await window.ExplorerManager.handleContextAction("ctx-copy-path");
            const fullPath = lastCopied;

            // Copy Relative Path
            window.ExplorerManager.showContextMenu(100, 100, target);
            await window.ExplorerManager.handleContextAction("ctx-copy-relative-path");
            const relPath = lastCopied;

            return {
                fullPath,
                relPath
            };
        }""")

        self.assertEqual(res["fullPath"], "/workspace/tests/test.py")
        self.assertEqual(res["relPath"], "tests/test.py")

    def test_cma_05_rename_action_invokes_inline_rename(self):
        """TC-CMA-05: Clicking Rename action dismisses menu and mounts inline rename input."""
        self.page.evaluate("""() => {
            window.ExplorerManager.entries = [
                { name: "file.js", is_dir: false, path: "/workspace/file.js" }
            ];
            window.ExplorerManager.render();

            const item = document.querySelector("#fileTreeViewport .tree-item");
            window.ExplorerManager.selectNode(item);
            window.ExplorerManager.showContextMenu(100, 100, window.ExplorerManager.selectedNode);
        }""")

        rename_btn = self.page.locator("#treeContextMenu .menu-item[data-action='ctx-rename']")
        rename_btn.click()

        # Context menu should be hidden
        menu = self.page.locator("#treeContextMenu")
        self.assertFalse(menu.is_visible())

        # Inline rename input should be visible
        rename_input = self.page.locator(".tree-rename-input")
        self.assertTrue(rename_input.is_visible())
        self.assertEqual(rename_input.input_value(), "file.js")

    def test_cma_06_guarded_delete_action(self):
        """TC-CMA-06: Clicking Delete prompts confirmation, calls deletePath, and closes tab."""
        res = self.page.evaluate("""async () => {
            window.confirm = () => true;
            let deletedPath = null;
            window.NativeBridge.deletePath = async (p) => {
                deletedPath = p;
                return { status: "ok" };
            };
            window.NativeBridge.listDir = async () => ({
                status: "ok",
                entries: []
            });

            // Open buffer in editor
            const tabId = window.EditorManager.createBuffer("junk.txt", "123", "/workspace/junk.txt");

            window.ExplorerManager.entries = [
                { name: "junk.txt", is_dir: false, path: "/workspace/junk.txt" }
            ];
            window.ExplorerManager.render();

            const item = document.querySelector("#fileTreeViewport .tree-item");
            window.ExplorerManager.selectNode(item);
            window.ExplorerManager.showContextMenu(100, 100, window.ExplorerManager.selectedNode);

            await window.ExplorerManager.handleContextAction("ctx-delete");

            return {
                deletedPath,
                bufferClosed: !window.EditorManager.buffers.has(tabId),
                itemCount: document.querySelectorAll("#fileTreeViewport .tree-item").length
            };
        }""")

        self.assertEqual(res["deletedPath"], "/workspace/junk.txt")
        self.assertTrue(res["bufferClosed"])
        self.assertEqual(res["itemCount"], 0)

    def test_cma_07_menu_dismissal_on_escape_and_outside_click(self):
        """TC-CMA-07: Pressing Escape or clicking outside dismisses context menu."""
        self.page.evaluate("""() => {
            window.ExplorerManager.showContextMenu(100, 100, { path: "/workspace/test.txt", isDir: false });
        }""")

        menu = self.page.locator("#treeContextMenu")
        self.assertTrue(menu.is_visible())

        # Press Escape
        self.page.keyboard.press("Escape")
        self.assertFalse(menu.is_visible())

        # Re-open and click outside
        self.page.evaluate("""() => {
            window.ExplorerManager.showContextMenu(100, 100, { path: "/workspace/test.txt", isDir: false });
        }""")
        self.assertTrue(menu.is_visible())

        self.page.mouse.click(500, 500)
        self.assertFalse(menu.is_visible())
