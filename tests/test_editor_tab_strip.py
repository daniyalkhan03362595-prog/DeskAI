import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


class TestEditorTabStrip(unittest.TestCase):
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
        self.page.wait_for_selector("#editorTabStrip")

    def tearDown(self):
        if hasattr(self, "page"):
            self.page.close()
        if hasattr(self, "context"):
            self.context.close()

    def test_ets_01_accessible_markup_and_semantics(self):
        """TC-ETS-01: Verifies #editorTabStrip has role='tablist' and accessible label."""
        tab_strip = self.page.locator("#editorTabStrip")
        self.assertEqual(tab_strip.get_attribute("role"), "tablist")
        self.assertEqual(tab_strip.get_attribute("aria-label"), "Open Files")
        # Initially empty
        tabs = self.page.locator(".editor-tab")
        self.assertEqual(tabs.count(), 0)

    def test_ets_02_dynamic_tab_creation_and_extension_icons(self):
        """TC-ETS-02: Creating buffers renders tabs with semantic vector SVG icons (Zed/Cursor style).
        Note: Evolved from legacy emojis (🐍, 🟨, 📝) to unified vector SVG outline icons ('file-code', 'file-text').
        """
        self.page.evaluate("""() => {
            window.EditorManager.createBuffer('script.py', 'print(1)');
            window.EditorManager.createBuffer('app.js', 'console.log(2)');
            window.EditorManager.createBuffer('notes.md', '# Header');
        }""")

        tabs = self.page.locator(".editor-tab")
        self.assertEqual(tabs.count(), 3)

        # Inspect icons and labels
        py_icon = self.page.locator(".editor-tab:nth-child(1) .tab-icon").get_attribute("data-icon")
        py_has_svg = self.page.locator(".editor-tab:nth-child(1) .tab-icon svg.deskai-svg-icon").is_visible()
        self.assertEqual(py_icon, "file-code")
        self.assertTrue(py_has_svg)
        py_label = self.page.locator(".editor-tab:nth-child(1) .tab-label").text_content()
        self.assertEqual(py_label, "script.py")

        js_icon = self.page.locator(".editor-tab:nth-child(2) .tab-icon").get_attribute("data-icon")
        js_has_svg = self.page.locator(".editor-tab:nth-child(2) .tab-icon svg.deskai-svg-icon").is_visible()
        self.assertEqual(js_icon, "file-code")
        self.assertTrue(js_has_svg)
        js_label = self.page.locator(".editor-tab:nth-child(2) .tab-label").text_content()
        self.assertEqual(js_label, "app.js")

        md_icon = self.page.locator(".editor-tab:nth-child(3) .tab-icon").get_attribute("data-icon")
        md_has_svg = self.page.locator(".editor-tab:nth-child(3) .tab-icon svg.deskai-svg-icon").is_visible()
        self.assertEqual(md_icon, "file-text")
        self.assertTrue(md_has_svg)
        md_label = self.page.locator(".editor-tab:nth-child(3) .tab-label").text_content()
        self.assertEqual(md_label, "notes.md")

    def test_ets_03_tab_selection_switching(self):
        """TC-ETS-03: Selecting a tab updates aria-selected, class, and active buffer."""
        tab_ids = self.page.evaluate("""() => {
            const id1 = window.EditorManager.createBuffer('first.py', 'first');
            const id2 = window.EditorManager.createBuffer('second.py', 'second');
            return [id1, id2];
        }""")

        tab1 = self.page.locator(f'[data-tab-id="{tab_ids[0]}"]')
        tab2 = self.page.locator(f'[data-tab-id="{tab_ids[1]}"]')

        # Initially tab 2 was created last and is active
        self.assertEqual(tab2.get_attribute("aria-selected"), "true")
        self.assertIn("active", tab2.get_attribute("class"))
        self.assertEqual(tab1.get_attribute("aria-selected"), "false")

        # Click tab 1
        tab1.click()
        self.assertEqual(tab1.get_attribute("aria-selected"), "true")
        self.assertIn("active", tab1.get_attribute("class"))
        self.assertEqual(tab2.get_attribute("aria-selected"), "false")
        self.assertNotIn("active", tab2.get_attribute("class"))

    def test_ets_04_keyboard_roving_navigation(self):
        """TC-ETS-04: Arrow, Home, and End keys navigate between tabs with roving tabindex."""
        self.page.evaluate("""() => {
            window.EditorManager.createBuffer('tab1.py', '1');
            window.EditorManager.createBuffer('tab2.py', '2');
            window.EditorManager.createBuffer('tab3.py', '3');
            // Select tab 1 initially
            const firstId = Array.from(window.EditorManager.buffers.keys())[0];
            window.EditorManager.selectTab(firstId);
            const firstEl = document.querySelector(`[data-tab-id="${firstId}"]`);
            firstEl.focus();
        }""")

        # Press ArrowRight -> tab 2
        self.page.keyboard.press("ArrowRight")
        active_tab_label = self.page.locator('.editor-tab[aria-selected="true"] .tab-label').text_content()
        self.assertEqual(active_tab_label, "tab2.py")

        # Press End -> tab 3
        self.page.keyboard.press("End")
        active_tab_label = self.page.locator('.editor-tab[aria-selected="true"] .tab-label').text_content()
        self.assertEqual(active_tab_label, "tab3.py")

        # Press Home -> tab 1
        self.page.keyboard.press("Home")
        active_tab_label = self.page.locator('.editor-tab[aria-selected="true"] .tab-label').text_content()
        self.assertEqual(active_tab_label, "tab1.py")

    def test_ets_05_middle_click_tab_closure(self):
        """TC-ETS-05: Middle-clicking (button 1 / auxclick) on a tab closes it."""
        tab_ids = self.page.evaluate("""() => {
            const id1 = window.EditorManager.createBuffer('delete_me.py', 'content');
            const id2 = window.EditorManager.createBuffer('keep_me.py', 'content');
            return [id1, id2];
        }""")

        self.assertEqual(self.page.locator(".editor-tab").count(), 2)

        # Dispatch middle-click auxclick on tab 1
        self.page.evaluate(
            """(tabId) => {
            const el = document.querySelector(`[data-tab-id="${tabId}"]`);
            const evt = new MouseEvent('auxclick', { button: 1, bubbles: true, cancelable: true });
            el.dispatchEvent(evt);
        }""",
            tab_ids[0],
        )

        tabs = self.page.locator(".editor-tab")
        self.assertEqual(tabs.count(), 1)
        remaining_label = self.page.locator(".editor-tab .tab-label").text_content()
        self.assertEqual(remaining_label, "keep_me.py")

    def test_ets_06_dirty_indicator_lifecycle(self):
        """TC-ETS-06: Modifying buffer renders dirty indicator dot and sets dirty status."""
        tab_id = self.page.evaluate("""() => {
            return window.EditorManager.createBuffer('clean.py', 'initial text');
        }""")

        tab = self.page.locator(f'[data-tab-id="{tab_id}"]')
        self.assertEqual(tab.locator(".tab-dirty-indicator").count(), 0)

        # Mark dirty
        self.page.evaluate(
            """(id) => {
            window.EditorManager.markDirty(id, true);
        }""",
            tab_id,
        )

        self.assertEqual(tab.locator(".tab-dirty-indicator").count(), 1)
        self.assertEqual(tab.locator(".tab-dirty-indicator").text_content(), "●")
        self.assertEqual(tab.locator(".tab-dirty-indicator").get_attribute("aria-label"), "Unsaved changes")

        # Mark clean
        self.page.evaluate(
            """(id) => {
            window.EditorManager.markDirty(id, false);
        }""",
            tab_id,
        )

        self.assertEqual(tab.locator(".tab-dirty-indicator").count(), 0)

    def test_ets_07_guarded_teardown_with_unsaved_edits(self):
        """TC-ETS-07: Closing an unsaved tab prompts user; cancelling aborts close."""
        tab_id = self.page.evaluate("""() => {
            const id = window.EditorManager.createBuffer('unsaved.py', 'dirty code');
            window.EditorManager.markDirty(id, true);
            // Mock confirm to return false (user cancelled)
            window.confirm = () => false;
            return id;
        }""")

        # Attempt to close tab
        self.page.evaluate(
            """(id) => {
            window.EditorManager.closeTab(id);
        }""",
            tab_id,
        )

        # Tab should NOT have been deleted
        self.assertEqual(self.page.locator(f'[data-tab-id="{tab_id}"]').count(), 1)

        # Change mock confirm to return true (user approves discard/proceed)
        self.page.evaluate(
            """(id) => {
            window.confirm = () => true;
            // mock saveBuffer to return true
            window.EditorManager.saveBuffer = async () => true;
            window.EditorManager.closeTab(id);
        }""",
            tab_id,
        )

        self.assertEqual(self.page.locator(f'[data-tab-id="{tab_id}"]').count(), 0)

    def test_ets_08_empty_state_handoff(self):
        """TC-ETS-08: Closing the last open tab restores #welcomeScreen."""
        tab_id = self.page.evaluate("""() => {
            return window.EditorManager.createBuffer('only_tab.py', 'hello');
        }""")

        welcome = self.page.locator("#welcomeScreen")
        self.assertFalse(welcome.is_visible())

        # Close the only tab
        self.page.locator(f'[data-tab-id="{tab_id}"] .tab-close-btn').click()

        self.assertEqual(self.page.locator(".editor-tab").count(), 0)
        self.assertTrue(welcome.is_visible())

    def test_ets_09_safe_dom_injection_on_malicious_filenames(self):
        """TC-ETS-09: Filenames containing HTML payloads render safely as text entities."""
        malicious_name = "<script id='tabXss'>window._tabXss=true;</script><img src='x' onerror='alert(1)'>.py"

        self.page.evaluate(
            """(name) => {
            window.EditorManager.createBuffer(name, 'safe content');
        }""",
            malicious_name,
        )

        # Check no script tag injected into DOM
        script_tag = self.page.locator("#tabXss")
        self.assertEqual(script_tag.count(), 0)

        # Check label contains text verbatim
        label = self.page.locator(".editor-tab .tab-label").text_content()
        self.assertEqual(label, malicious_name)

    def test_ets_10_tab_strip_clears_sidebar_expand_pill(self):
        """TC-ETS-10: When sidebar is collapsed, tab strip provides dedicated offset so tabs do not collide."""
        self.page.evaluate("""() => {
            window.EditorManager.createBuffer('config.toml', 'test content');
        }""")
        self.page.wait_for_selector(".editor-tab")

        # Collapse sidebar
        overlap = self.page.evaluate("""async () => {
            const toggle = document.getElementById("btnToggleSidebar");
            if (toggle) toggle.click();
            await new Promise(r => setTimeout(r, 200));

            const pill = document.getElementById("btnExpandSidebar");
            const firstTab = document.querySelector(".editor-tab");
            const pillRect = pill.getBoundingClientRect();
            const tabRect = firstTab.getBoundingClientRect();

            return {
                pillRight: pillRect.right,
                tabLeft: tabRect.left,
                isCollapsed: document.getElementById("appBody").classList.contains("sidebar-left-collapsed"),
                isPillVisible: pill.offsetParent !== null
            };
        }""")

        self.assertTrue(overlap["isCollapsed"])
        self.assertTrue(overlap["isPillVisible"])
        # The first tab must start strictly to the right of the expand pill with clearance
        self.assertGreater(overlap["tabLeft"], overlap["pillRight"], "First tab overlaps with expand pill!")

        # Restore sidebar
        self.page.evaluate("""() => {
            const pill = document.getElementById("btnExpandSidebar");
            if (pill) pill.click();
        }""")
