import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


class TestTreeNodeItem(unittest.TestCase):
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

    def test_tni_01_semantic_filetype_badges(self):
        """TC-TNI-01: Files render correct semantic slate SVG vector outline icons (Zed/Cursor style).
        Note: Evolved from legacy raw Unicode emojis (🐍, 🟨, 📝) to unified vector SVG outline icons
        ('file-code', 'file-text') rendered with currentColor and data-icon attributes.
        """
        res = self.page.evaluate("""() => {
            window.ExplorerManager.entries = [
                { name: "script.py", is_dir: false, path: "/workspace/script.py" },
                { name: "bundle.js", is_dir: false, path: "/workspace/bundle.js" },
                { name: "types.ts", is_dir: false, path: "/workspace/types.ts" },
                { name: "data.json", is_dir: false, path: "/workspace/data.json" },
                { name: "index.html", is_dir: false, path: "/workspace/index.html" },
                { name: "styles.css", is_dir: false, path: "/workspace/styles.css" },
                { name: "README.md", is_dir: false, path: "/workspace/README.md" },
                { name: "deploy.sh", is_dir: false, path: "/workspace/deploy.sh" },
                { name: "schema.sql", is_dir: false, path: "/workspace/schema.sql" },
                { name: "notes.txt", is_dir: false, path: "/workspace/notes.txt" },
                { name: ".gitignore", is_dir: false, path: "/workspace/.gitignore" },
                { name: "pyproject.toml", is_dir: false, path: "/workspace/pyproject.toml" }
            ];
            window.ExplorerManager.render();

            const items = document.querySelectorAll("#fileTreeViewport .tree-item");
            return Array.from(items).map(item => ({
                label: item.querySelector(".tree-label").textContent,
                icon: item.querySelector(".tree-icon").getAttribute("data-icon"),
                hasSvg: !!item.querySelector(".tree-icon svg.deskai-svg-icon")
            }));
        }""")

        badge_map = {item["label"]: item["icon"] for item in res}
        self.assertTrue(all(item["hasSvg"] for item in res))
        self.assertEqual(badge_map["script.py"], "file-code")
        self.assertEqual(badge_map["bundle.js"], "file-code")
        self.assertEqual(badge_map["types.ts"], "file-code")
        self.assertEqual(badge_map["data.json"], "file-code")
        self.assertEqual(badge_map["index.html"], "file-code")
        self.assertEqual(badge_map["styles.css"], "file-code")
        self.assertEqual(badge_map["README.md"], "file-text")
        self.assertEqual(badge_map["deploy.sh"], "file-code")
        self.assertEqual(badge_map["schema.sql"], "file-code")
        self.assertEqual(badge_map["notes.txt"], "file-text")
        self.assertEqual(badge_map[".gitignore"], "file-code")
        self.assertEqual(badge_map["pyproject.toml"], "file-code")

    def test_tni_02_folder_chevrons_and_icons(self):
        """TC-TNI-02: Folder renders ► folder when closed, and ▼ folder-open when expanded.
        Note: Evolved from legacy emojis (📁/📂) to minimalist slate outline SVG icons.
        """
        res = self.page.evaluate("""() => {
            window.ExplorerManager.entries = [
                { name: "src", is_dir: true, path: "/workspace/src" }
            ];
            window.ExplorerManager.expandedDirs.clear();
            window.ExplorerManager.render();

            const closedItem = document.querySelector("#fileTreeViewport .tree-item");
            const closedArrow = closedItem.querySelector(".tree-arrow").textContent;
            const closedIcon = closedItem.querySelector(".tree-icon").getAttribute("data-icon");
            const closedHasSvg = !!closedItem.querySelector(".tree-icon svg.deskai-svg-icon");

            // Expand folder
            window.ExplorerManager.expandedDirs.add("/workspace/src");
            window.ExplorerManager.dirChildren.set("/workspace/src", [
                { name: "nested.js", is_dir: false, path: "/workspace/src/nested.js" }
            ]);
            window.ExplorerManager.render();

            const openItem = document.querySelector("#fileTreeViewport .tree-item.is-folder");
            const openArrow = openItem.querySelector(".tree-arrow").textContent;
            const openIcon = openItem.querySelector(".tree-icon").getAttribute("data-icon");
            const openHasSvg = !!openItem.querySelector(".tree-icon svg.deskai-svg-icon");

            return {
                closedArrow,
                closedIcon,
                closedHasSvg,
                openArrow,
                openIcon,
                openHasSvg
            };
        }""")

        self.assertEqual(res["closedArrow"], "►")
        self.assertEqual(res["closedIcon"], "folder")
        self.assertTrue(res["closedHasSvg"])
        self.assertEqual(res["openArrow"], "▼")
        self.assertEqual(res["openIcon"], "folder-open")
        self.assertTrue(res["openHasSvg"])

    def test_tni_03_hierarchical_indent_level(self):
        """TC-TNI-03: Indentation spaces reflect nesting depth."""
        res = self.page.evaluate("""() => {
            window.ExplorerManager.entries = [
                { name: "src", is_dir: true, path: "/workspace/src" }
            ];
            window.ExplorerManager.expandedDirs.add("/workspace/src");
            window.ExplorerManager.dirChildren.set("/workspace/src", [
                { name: "deep", is_dir: true, path: "/workspace/src/deep" }
            ]);
            window.ExplorerManager.expandedDirs.add("/workspace/src/deep");
            window.ExplorerManager.dirChildren.set("/workspace/src/deep", [
                { name: "leaf.py", is_dir: false, path: "/workspace/src/deep/leaf.py" }
            ]);
            window.ExplorerManager.render();

            const items = document.querySelectorAll("#fileTreeViewport .tree-item");
            return Array.from(items).map(item => {
                const indent = item.querySelector(".tree-indent");
                return {
                    label: item.querySelector(".tree-label").textContent,
                    level: item.getAttribute("aria-level"),
                    indentWidth: indent ? indent.style.width : "0px"
                };
            });
        }""")

        self.assertEqual(res[0]["label"], "src")
        self.assertEqual(res[0]["level"], "1")
        self.assertEqual(res[0]["indentWidth"], "0px")

        self.assertEqual(res[1]["label"], "deep")
        self.assertEqual(res[1]["level"], "2")
        self.assertEqual(res[1]["indentWidth"], "14px")

        self.assertEqual(res[2]["label"], "leaf.py")
        self.assertEqual(res[2]["level"], "3")
        self.assertEqual(res[2]["indentWidth"], "28px")

    def test_tni_04_f2_triggers_inline_rename_input(self):
        """TC-TNI-04: Pressing F2 mounts .tree-rename-input prefilled with filename."""
        self.page.evaluate("""() => {
            window.ExplorerManager.entries = [
                { name: "server.py", is_dir: false, path: "/workspace/server.py" }
            ];
            window.ExplorerManager.render();

            const item = document.querySelector("#fileTreeViewport .tree-item");
            window.ExplorerManager.focusNode(item);
        }""")

        self.page.keyboard.press("F2")
        rename_input = self.page.locator(".tree-rename-input")
        self.assertTrue(rename_input.is_visible())
        self.assertEqual(rename_input.input_value(), "server.py")

    def test_tni_05_inline_rename_commit_via_enter(self):
        """TC-TNI-05: Editing rename input and pressing Enter invokes renamePath and reloads tree."""
        res = self.page.evaluate("""async () => {
            let renamedOld = null;
            let renamedNew = null;

            window.NativeBridge.renamePath = async (oldPath, newPath) => {
                renamedOld = oldPath;
                renamedNew = newPath;
                return { status: "ok" };
            };
            window.NativeBridge.listDir = async () => ({
                status: "ok",
                entries: [
                    { name: "app_v2.py", is_dir: false, path: "/workspace/app_v2.py" }
                ]
            });

            window.ExplorerManager.entries = [
                { name: "app.py", is_dir: false, path: "/workspace/app.py" }
            ];
            window.ExplorerManager.render();

            const item = document.querySelector("#fileTreeViewport .tree-item");
            window.ExplorerManager.focusNode(item);
            window.ExplorerManager.startInlineRename(item);

            const input = document.querySelector(".tree-rename-input");
            input.value = "app_v2.py";

            // Trigger Enter
            const enterEvt = new KeyboardEvent("keydown", { key: "Enter", bubbles: true });
            input.dispatchEvent(enterEvt);

            await new Promise(r => setTimeout(r, 50));

            return {
                renamedOld,
                renamedNew,
                newLabel: document.querySelector(".tree-label").textContent
            };
        }""")

        self.assertEqual(res["renamedOld"], "/workspace/app.py")
        self.assertEqual(res["renamedNew"], "/workspace/app_v2.py")
        self.assertEqual(res["newLabel"], "app_v2.py")

    def test_tni_06_inline_rename_cancel_via_escape(self):
        """TC-TNI-06: Pressing Escape cancels rename without calling renamePath."""
        res = self.page.evaluate("""async () => {
            let renameCalled = false;
            window.NativeBridge.renamePath = async () => {
                renameCalled = true;
                return { status: "ok" };
            };

            window.ExplorerManager.entries = [
                { name: "original.txt", is_dir: false, path: "/workspace/original.txt" }
            ];
            window.ExplorerManager.render();

            const item = document.querySelector("#fileTreeViewport .tree-item");
            window.ExplorerManager.focusNode(item);
            window.ExplorerManager.startInlineRename(item);

            const input = document.querySelector(".tree-rename-input");
            input.value = "changed.txt";

            const escEvt = new KeyboardEvent("keydown", { key: "Escape", bubbles: true });
            input.dispatchEvent(escEvt);

            return {
                renameCalled,
                inputRemoved: !document.querySelector(".tree-rename-input"),
                label: document.querySelector(".tree-label").textContent
            };
        }""")

        self.assertFalse(res["renameCalled"])
        self.assertTrue(res["inputRemoved"])
        self.assertEqual(res["label"], "original.txt")

    def test_tni_07_editor_buffer_sync_on_rename(self):
        """TC-TNI-07: Renaming a file synchronizes open editor tab path, label, and icon."""
        res = self.page.evaluate("""async () => {
            // Open file in editor first
            const tabId = window.EditorManager.createBuffer("worker.js", "console.log(1)", "/workspace/worker.js");

            window.NativeBridge.renamePath = async (oldP, newP) => ({ status: "ok" });
            window.NativeBridge.listDir = async () => ({
                status: "ok",
                entries: [
                    { name: "worker.ts", is_dir: false, path: "/workspace/worker.ts" }
                ]
            });

            window.ExplorerManager.entries = [
                { name: "worker.js", is_dir: false, path: "/workspace/worker.js" }
            ];
            window.ExplorerManager.render();

            const item = document.querySelector("#fileTreeViewport .tree-item");
            window.ExplorerManager.focusNode(item);
            window.ExplorerManager.startInlineRename(item);

            const input = document.querySelector(".tree-rename-input");
            input.value = "worker.ts";

            const enterEvt = new KeyboardEvent("keydown", { key: "Enter", bubbles: true });
            input.dispatchEvent(enterEvt);

            await new Promise(r => setTimeout(r, 50));

            const buf = window.EditorManager.buffers.get(tabId);
            const tabEl = document.querySelector(`[data-tab-id="${tabId}"]`);

            return {
                bufferPath: buf.path,
                bufferName: buf.name,
                tabLabel: tabEl.querySelector(".tab-label").textContent,
                tabIcon: tabEl.querySelector(".tab-icon").getAttribute("data-icon"),
                tabHasSvg: !!tabEl.querySelector(".tab-icon svg.deskai-svg-icon")
            };
        }""")

        self.assertEqual(res["bufferPath"], "/workspace/worker.ts")
        self.assertEqual(res["bufferName"], "worker.ts")
        self.assertEqual(res["tabLabel"], "worker.ts")
        self.assertEqual(res["tabIcon"], "file-code")
        self.assertTrue(res["tabHasSvg"])

    def test_tni_08_inline_rename_cancel_via_button_click(self):
        """TC-TNI-08: Clicking the cancel button (✖) dismisses inline rename cleanly without calling renamePath."""
        self.page.evaluate("""() => {
            window._renameCalled = false;
            window.NativeBridge.renamePath = async () => {
                window._renameCalled = true;
                return { status: "ok" };
            };
            window.ExplorerManager.entries = [
                { name: "cancel-me.txt", is_dir: false, path: "/workspace/cancel-me.txt" }
            ];
            window.ExplorerManager.render();
            const item = document.querySelector("#fileTreeViewport .tree-item");
            window.ExplorerManager.startInlineRename(item);
        }""")

        self.assertEqual(self.page.locator(".tree-rename-input").count(), 1)
        cancel_btn = self.page.locator(".tree-create-cancel").first
        cancel_btn.click()
        self.page.wait_for_timeout(200)

        self.assertEqual(self.page.locator(".tree-rename-input").count(), 0)
        rename_called = self.page.evaluate("() => window._renameCalled")
        self.assertFalse(rename_called)
        label = self.page.locator("#fileTreeViewport .tree-label").first.text_content()
        self.assertEqual(label, "cancel-me.txt")

    def test_tni_09_inline_rename_confirm_via_button_click(self):
        """TC-TNI-09: Clicking the confirm button (✔) commits inline rename via NativeBridge.renamePath."""
        self.page.evaluate("""() => {
            window._lastRename = null;
            window.NativeBridge.renamePath = async (oldP, newP) => {
                window._lastRename = { oldP, newP };
                return { status: "ok" };
            };
            window.NativeBridge.listDir = async () => ({
                status: "ok",
                entries: [
                    { name: "confirmed.txt", is_dir: false, path: "/workspace/confirmed.txt" }
                ]
            });
            window.ExplorerManager.entries = [
                { name: "old-name.txt", is_dir: false, path: "/workspace/old-name.txt" }
            ];
            window.ExplorerManager.render();
            const item = document.querySelector("#fileTreeViewport .tree-item");
            window.ExplorerManager.startInlineRename(item);
        }""")

        input_el = self.page.locator(".tree-rename-input").first
        input_el.fill("confirmed.txt")
        confirm_btn = self.page.locator(".tree-create-confirm").first
        confirm_btn.click()
        self.page.wait_for_timeout(200)

        self.assertEqual(self.page.locator(".tree-rename-input").count(), 0)
        last_rename = self.page.evaluate("() => window._lastRename")
        self.assertIsNotNone(last_rename)
        self.assertEqual(last_rename["oldP"], "/workspace/old-name.txt")
        self.assertEqual(last_rename["newP"], "/workspace/confirmed.txt")

    def test_tni_10_inline_rename_singleton_enforcement(self):
        """TC-TNI-10: Opening inline rename on an item dismisses any active inline editors (singleton rule)."""
        self.page.evaluate("""() => {
            window.ExplorerManager.entries = [
                { name: "item1.txt", is_dir: false, path: "/workspace/item1.txt" },
                { name: "item2.txt", is_dir: false, path: "/workspace/item2.txt" },
                { name: "item3.txt", is_dir: false, path: "/workspace/item3.txt" }
            ];
            window.ExplorerManager.render();
            const items = document.querySelectorAll("#fileTreeViewport .tree-item");
            window.ExplorerManager.startInlineRename(items[0]);
        }""")

        self.assertEqual(self.page.locator(".tree-rename-input").count(), 1)
        # Open rename on second item
        self.page.evaluate("""() => {
            const items = document.querySelectorAll("#fileTreeViewport .tree-item");
            window.ExplorerManager.startInlineRename(items[1]);
        }""")
        self.assertEqual(self.page.locator(".tree-rename-input").count(), 1)
        # Open rename on third item
        self.page.evaluate("""() => {
            const items = document.querySelectorAll("#fileTreeViewport .tree-item");
            window.ExplorerManager.startInlineRename(items[2]);
        }""")
        self.assertEqual(self.page.locator(".tree-rename-input").count(), 1)

        items = self.page.locator("#fileTreeViewport .tree-item")
        self.assertFalse(items.nth(0).evaluate("el => el.classList.contains('is-renaming')"))
        self.assertFalse(items.nth(1).evaluate("el => el.classList.contains('is-renaming')"))
        self.assertTrue(items.nth(2).evaluate("el => el.classList.contains('is-renaming')"))
