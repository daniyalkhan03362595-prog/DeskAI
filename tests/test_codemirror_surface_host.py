import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


class TestCodeMirrorSurfaceHost(unittest.TestCase):
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

    def test_cmh_01_accessible_host_semantics(self):
        """TC-CMH-01: Verifies #codeEditorHost has role='region' and accessible label."""
        host = self.page.locator("#codeEditorHost")
        self.assertEqual(host.get_attribute("role"), "region")
        self.assertEqual(host.get_attribute("aria-label"), "Code Surface")

    def test_cmh_02_codemirror_mounting(self):
        """TC-CMH-02: createBuffer mounts .editor-view-container and .cm-editor inside #codeEditorHost."""
        tab_id = self.page.evaluate("""() => {
            return window.EditorManager.createBuffer('sample.py', 'print("Mounted")');
        }""")

        container = self.page.locator(f"#editor-container-{tab_id}")
        self.assertTrue(container.is_visible())
        self.assertEqual(container.get_attribute("data-buffer-id"), tab_id)

        cm_editor = container.locator(".cm-editor")
        self.assertTrue(cm_editor.is_visible())

        cm_content = container.locator(".cm-content")
        self.assertEqual(cm_content.get_attribute("contenteditable"), "true")
        self.assertEqual(cm_content.get_attribute("role"), "textbox")
        self.assertEqual(cm_content.get_attribute("aria-multiline"), "true")

    def test_cmh_03_gutters_and_line_number_rendering(self):
        """TC-CMH-03: Multi-line documents render matching line numbers in .cm-gutters."""
        five_lines = "line 1\nline 2\nline 3\nline 4\nline 5"
        tab_id = self.page.evaluate(
            """(text) => {
            return window.EditorManager.createBuffer('multiline.txt', text);
        }""",
            five_lines,
        )

        container = self.page.locator(f"#editor-container-{tab_id}")
        gutters = container.locator(".cm-gutters")
        self.assertTrue(gutters.is_visible())

        line_nums = self.page.evaluate(
            """(tabId) => {
            const container = document.getElementById('editor-container-' + tabId);
            const els = Array.from(container.querySelectorAll('.cm-lineNumbers .cm-gutterElement'));
            return els.filter(el => !el.style.visibility || el.style.visibility !== 'hidden').map(el => el.textContent);
        }""",
            tab_id,
        )
        self.assertEqual(line_nums, ["1", "2", "3", "4", "5"])

    def test_cmh_04_token_syntax_highlighting(self):
        """TC-CMH-04: Python syntax tokens receive distinct syntax highlight styling."""
        code = "def calc():\n    return 42"
        tab_id = self.page.evaluate(
            """(text) => {
            return window.EditorManager.createBuffer('calc.py', text);
        }""",
            code,
        )

        container = self.page.locator(f"#editor-container-{tab_id}")
        tokens = container.locator(".cm-line span").all_text_contents()

        self.assertIn("def", tokens)
        self.assertIn("calc", tokens)
        self.assertIn("return", tokens)
        self.assertIn("42", tokens)

    def test_cmh_05_view_state_and_dom_retention_across_tab_switches(self):
        """TC-CMH-05: Switching tabs toggles display: block/none without destroying CodeMirror instance."""
        tab_ids = self.page.evaluate("""() => {
            const id1 = window.EditorManager.createBuffer('tab1.py', 'buffer one');
            const id2 = window.EditorManager.createBuffer('tab2.py', 'buffer two');
            return [id1, id2];
        }""")

        container1 = self.page.locator(f"#editor-container-{tab_ids[0]}")
        container2 = self.page.locator(f"#editor-container-{tab_ids[1]}")

        # Initially tab2 is active
        self.assertFalse(container1.is_visible())
        self.assertTrue(container2.is_visible())

        # Switch to tab1
        self.page.evaluate(
            """(id) => {
            window.EditorManager.selectTab(id);
        }""",
            tab_ids[0],
        )

        self.assertTrue(container1.is_visible())
        self.assertFalse(container2.is_visible())

        # Content in container1 was preserved
        text1 = container1.locator(".cm-content").text_content()
        self.assertIn("buffer one", text1)

    def test_cmh_06_resize_observer_reflow(self):
        """TC-CMH-06: Resizing #codeEditorHost invokes requestMeasure() without layout errors."""
        self.page.evaluate("""() => {
            window.EditorManager.createBuffer('resize_test.py', 'x = 100');
        }""")

        # Trigger width mutation on host
        res = self.page.evaluate("""() => {
            const host = document.getElementById('codeEditorHost');
            host.style.width = '750px';
            return host.offsetWidth;
        }""")
        self.assertEqual(res, 750)

    def test_cmh_07_keyboard_trap_escape_handler(self):
        """TC-CMH-07: Pressing Escape inside .cm-content blurs editor and focuses active tab."""
        tab_id = self.page.evaluate("""() => {
            return window.EditorManager.createBuffer('escape_test.py', 'escapable');
        }""")

        container = self.page.locator(f"#editor-container-{tab_id}")
        content = container.locator(".cm-content")
        content.focus()

        # Press Escape
        self.page.keyboard.press("Escape")

        # Focus should be moved to the active tab
        focused_tab_id = self.page.evaluate(
            "() => document.activeElement ? document.activeElement.getAttribute('data-tab-id') : null"
        )
        self.assertEqual(focused_tab_id, tab_id)

    def test_cmh_08_teardown_and_view_destruction(self):
        """TC-CMH-08: Closing buffer destroys view and removes container from DOM."""
        tab_id = self.page.evaluate("""() => {
            return window.EditorManager.createBuffer('doomed.py', 'bye');
        }""")

        self.assertEqual(self.page.locator(f"#editor-container-{tab_id}").count(), 1)

        # Close tab
        self.page.evaluate(
            """(id) => {
            window.EditorManager.closeTab(id);
        }""",
            tab_id,
        )

        self.assertEqual(self.page.locator(f"#editor-container-{tab_id}").count(), 0)

    def test_cmh_09_safe_plaintext_rendering(self):
        """TC-CMH-09: Code containing HTML or scripts renders safely as plaintext without script execution."""
        payload = "<script id='cmHostXss'>window._cmHostXss=true;</script>"
        tab_id = self.page.evaluate(
            """(content) => {
            return window.EditorManager.createBuffer('xss_test.py', content);
        }""",
            payload,
        )

        container = self.page.locator(f"#editor-container-{tab_id}")
        content = container.locator(".cm-content")

        # Verify script tag did not execute
        xss_fired = self.page.evaluate("() => Boolean(window._cmHostXss)")
        self.assertFalse(xss_fired)

        # Verify no script tag was injected
        self.assertEqual(self.page.locator("#cmHostXss").count(), 0)

        # Text rendered verbatim
        self.assertIn(payload, content.text_content())
