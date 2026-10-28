import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


class TestEditorBufferController(unittest.TestCase):
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

    def tearDown(self):
        if hasattr(self, "page"):
            self.page.close()
        if hasattr(self, "context"):
            self.context.close()

    def test_ebc_01_create_buffer_scratch_model(self):
        """TC-EBC-01: Verifies creating untitled scratch buffer without disk path."""
        res = self.page.evaluate("""() => {
            const id = window.EditorManager.createBuffer();
            const buf = window.EditorManager.buffers.get(id);
            return {
                id,
                name: buf.name,
                path: buf.path,
                isDirty: buf.isDirty,
                content: buf.content,
                storeOpenTabsCount: window.store.state.editor.openTabs.length,
                activeTabId: window.store.state.editor.activeTabId
            };
        }""")

        self.assertTrue(res["id"].startswith("tab-"))
        self.assertEqual(res["name"], "untitled.txt")
        self.assertIsNone(res["path"])
        self.assertFalse(res["isDirty"])
        self.assertEqual(res["content"], "")
        self.assertEqual(res["storeOpenTabsCount"], 1)
        self.assertEqual(res["activeTabId"], res["id"])

    def test_ebc_02_duplicate_path_prevention(self):
        """TC-EBC-02: Opening the same path twice returns existing ID without duplicating buffer or tab."""
        res = self.page.evaluate("""() => {
            const id1 = window.EditorManager.createBuffer("server.py", "import os", "/workspace/server.py");
            const id2 = window.EditorManager.createBuffer("server.py", "import os", "/workspace/server.py");
            const id3 = window.EditorManager.createBuffer("server.py", "import os", "/workspace/server.py/");

            return {
                id1,
                id2,
                id3,
                bufferCount: window.EditorManager.buffers.size,
                tabCount: document.getElementById("editorTabStrip").children.length,
                pathToIdSize: window.EditorManager.pathToId.size
            };
        }""")

        self.assertEqual(res["id1"], res["id2"])
        self.assertEqual(res["id1"], res["id3"])
        self.assertEqual(res["bufferCount"], 1)
        self.assertEqual(res["tabCount"], 1)
        self.assertEqual(res["pathToIdSize"], 1)

    def test_ebc_03_open_file_via_native_bridge(self):
        """TC-EBC-03: openFile reads disk content via NativeBridge and mounts buffer."""
        res = self.page.evaluate("""async () => {
            window.NativeBridge.readFile = async (path) => {
                return { status: "ok", content: "def main(): pass" };
            };

            const id = await window.EditorManager.openFile("/workspace/src/app.py");
            const buf = window.EditorManager.buffers.get(id);

            return {
                id,
                name: buf.name,
                path: buf.path,
                content: buf.content,
                language: buf.language,
                isDirty: buf.isDirty
            };
        }""")

        self.assertTrue(res["id"].startswith("tab-"))
        self.assertEqual(res["name"], "app.py")
        self.assertEqual(res["path"], "/workspace/src/app.py")
        self.assertEqual(res["content"], "def main(): pass")
        self.assertEqual(res["language"], "python")
        self.assertFalse(res["isDirty"])

    def test_ebc_04_dirty_tracking_and_native_bridge_notification(self):
        """TC-EBC-04: Document mutation updates isDirty, renders ● badge, and calls setDirtyStatus(true)."""
        res = self.page.evaluate("""() => {
            let lastDirtyStatus = null;
            window.NativeBridge.setDirtyStatus = (val) => {
                lastDirtyStatus = val;
            };

            const id = window.EditorManager.createBuffer("test.js", "console.log('clean');");
            const tabBefore = document.querySelector(`[data-tab-id="${id}"]`);
            const dirtyBefore = tabBefore.querySelector(".tab-dirty-indicator");

            // Dispatch modification
            const buf = window.EditorManager.buffers.get(id);
            buf.view.dispatch({
                changes: { from: 0, insert: "// header\\n" }
            });

            const tabAfter = document.querySelector(`[data-tab-id="${id}"]`);
            const dirtyAfter = tabAfter.querySelector(".tab-dirty-indicator");

            return {
                dirtyBefore: !!dirtyBefore,
                dirtyAfter: !!dirtyAfter,
                isDirty: buf.isDirty,
                lastDirtyStatus
            };
        }""")

        self.assertFalse(res["dirtyBefore"])
        self.assertTrue(res["dirtyAfter"])
        self.assertTrue(res["isDirty"])
        self.assertTrue(res["lastDirtyStatus"])

    def test_ebc_05_clean_save_workflow(self):
        """TC-EBC-05: saveBuffer writes file to disk, clears dirty flag and notifies setDirtyStatus(false)."""
        res = self.page.evaluate("""async () => {
            let writtenPath = null;
            let writtenContent = null;
            let lastDirtyStatus = null;

            window.NativeBridge.writeFile = async (path, content) => {
                writtenPath = path;
                writtenContent = content;
                return { status: "ok" };
            };
            window.NativeBridge.setDirtyStatus = (val) => {
                lastDirtyStatus = val;
            };

            const id = window.EditorManager.createBuffer("math.py", "x = 1", "/workspace/math.py");
            const buf = window.EditorManager.buffers.get(id);
            buf.view.dispatch({ changes: { from: 5, insert: "00" } }); // x = 100

            const dirtyBeforeSave = buf.isDirty;
            const saved = await window.EditorManager.saveBuffer(id);

            const tabEl = document.querySelector(`[data-tab-id="${id}"]`);
            const dirtyDot = tabEl.querySelector(".tab-dirty-indicator");

            return {
                dirtyBeforeSave,
                saved,
                dirtyAfterSave: buf.isDirty,
                dirtyDotPresent: !!dirtyDot,
                writtenPath,
                writtenContent,
                lastDirtyStatus
            };
        }""")

        self.assertTrue(res["dirtyBeforeSave"])
        self.assertTrue(res["saved"])
        self.assertFalse(res["dirtyAfterSave"])
        self.assertFalse(res["dirtyDotPresent"])
        self.assertEqual(res["writtenPath"], "/workspace/math.py")
        self.assertEqual(res["writtenContent"], "x = 100")
        self.assertFalse(res["lastDirtyStatus"])

    def test_ebc_06_save_as_untitled_buffer(self):
        """TC-EBC-06: saveBuffer on scratch untitled buffer triggers saveFileDialog and re-indexes path."""
        res = self.page.evaluate("""async () => {
            window.NativeBridge.saveFileDialog = async (defaultName) => {
                return { status: "ok", path: "/workspace/config.json" };
            };
            window.NativeBridge.writeFile = async (path, content) => {
                return { status: "ok" };
            };

            const id = window.EditorManager.createBuffer("untitled.txt", '{"env":"test"}');
            const saved = await window.EditorManager.saveBuffer(id);

            const buf = window.EditorManager.buffers.get(id);
            const tabEl = document.querySelector(`[data-tab-id="${id}"]`);
            const iconEl = tabEl.querySelector(".tab-icon");
            const labelEl = tabEl.querySelector(".tab-label");

            return {
                saved,
                path: buf.path,
                name: buf.name,
                language: buf.language,
                iconData: iconEl.getAttribute("data-icon"),
                iconHasSvg: !!tabEl.querySelector(".tab-icon svg.deskai-svg-icon"),
                labelText: labelEl.textContent,
                pathToIdHasNew: window.EditorManager.pathToId.has("/workspace/config.json")
            };
        }""")

        self.assertTrue(res["saved"])
        self.assertEqual(res["path"], "/workspace/config.json")
        self.assertEqual(res["name"], "config.json")
        self.assertEqual(res["language"], "javascript")
        self.assertEqual(res["iconData"], "file-code")
        self.assertTrue(res["iconHasSvg"])
        self.assertEqual(res["labelText"], "config.json")
        self.assertTrue(res["pathToIdHasNew"])

    def test_ebc_07_guarded_close_cancellation(self):
        """TC-EBC-07: Rejecting confirmation prompt when closing dirty tab cancels teardown."""
        res = self.page.evaluate("""async () => {
            window.confirm = () => false; // User clicks Cancel on confirm modal

            const id = window.EditorManager.createBuffer("draft.md", "# Draft", "/workspace/draft.md");
            window.EditorManager.markDirty(id, true);

            const closed = await window.EditorManager.closeTab(id, false);
            const stillExists = window.EditorManager.buffers.has(id);
            const tabStillInDOM = !!document.querySelector(`[data-tab-id="${id}"]`);

            return {
                closed,
                stillExists,
                tabStillInDOM
            };
        }""")

        self.assertFalse(res["closed"])
        self.assertTrue(res["stillExists"])
        self.assertTrue(res["tabStillInDOM"])

    def test_ebc_08_revert_buffer_from_disk(self):
        """TC-EBC-08: revertBuffer reloads disk content via NativeBridge and clears dirty state."""
        res = self.page.evaluate("""async () => {
            const initialDiskContent = "DATABASE_URL=sqlite:///test.db";
            window.NativeBridge.readFile = async () => {
                return { status: "ok", content: initialDiskContent };
            };

            const id = window.EditorManager.createBuffer(".env", initialDiskContent, "/workspace/.env");
            const buf = window.EditorManager.buffers.get(id);

            // Developer made unwanted edits
            buf.view.dispatch({ changes: { from: 0, insert: "CORRUPTED " } });
            const dirtyBefore = buf.isDirty;
            const textBefore = buf.content;

            const reverted = await window.EditorManager.revertBuffer(id);

            return {
                dirtyBefore,
                textBefore,
                reverted,
                dirtyAfter: buf.isDirty,
                textAfter: buf.content,
                viewText: buf.view.state.doc.toString()
            };
        }""")

        self.assertTrue(res["dirtyBefore"])
        self.assertTrue(res["textBefore"].startswith("CORRUPTED"))
        self.assertTrue(res["reverted"])
        self.assertFalse(res["dirtyAfter"])
        self.assertEqual(res["textAfter"], "DATABASE_URL=sqlite:///test.db")
        self.assertEqual(res["viewText"], "DATABASE_URL=sqlite:///test.db")

    def test_ebc_09_close_all_tabs_and_welcome_screen_sync(self):
        """TC-EBC-09: closeAllTabs cleans up all views, unmounts containers, and syncs Welcome screen."""
        res = self.page.evaluate("""async () => {
            window.EditorManager.createBuffer("tab1.py", "1");
            window.EditorManager.createBuffer("tab2.js", "2");
            window.EditorManager.createBuffer("tab3.md", "3");

            const countBefore = window.EditorManager.buffers.size;
            const closedAll = await window.EditorManager.closeAllTabs(true);
            const countAfter = window.EditorManager.buffers.size;
            const hostChildCount = document.getElementById("codeEditorHost").children.length;
            const welcomeVisible = document.getElementById("welcomeScreen").style.display !== "none";

            return {
                countBefore,
                closedAll,
                countAfter,
                hostChildCount,
                welcomeVisible,
                activeTabId: window.EditorManager.activeTabId
            };
        }""")

        self.assertEqual(res["countBefore"], 3)
        self.assertTrue(res["closedAll"])
        self.assertEqual(res["countAfter"], 0)
        self.assertEqual(res["hostChildCount"], 0)
        self.assertTrue(res["welcomeVisible"])
        self.assertIsNone(res["activeTabId"])
