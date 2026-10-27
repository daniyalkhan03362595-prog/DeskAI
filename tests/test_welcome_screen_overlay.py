import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


class TestWelcomeScreenOverlay(unittest.TestCase):
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
        self.page.wait_for_selector("#welcomeScreen")

    def tearDown(self):
        if hasattr(self, "page"):
            self.page.close()
        if hasattr(self, "context"):
            self.context.close()

    def test_wso_01_accessible_markup_and_semantics(self):
        """TC-WSO-01: Verifies #welcomeScreen has role='region' and accessible label."""
        welcome = self.page.locator("#welcomeScreen")
        self.assertTrue(welcome.is_visible())
        self.assertEqual(welcome.get_attribute("role"), "region")
        self.assertEqual(welcome.get_attribute("aria-label"), "Welcome and Quick Actions")

    def test_wso_02_initial_state_empty_no_workspace(self):
        """TC-WSO-02: Verifies initial state renders brand, Open Folder CTA, and shortcuts."""
        title = self.page.locator("#welcomeTitle").text_content()
        self.assertIn("Welcome to DeskAI", title)

        primary_btn = self.page.locator("#welcomePrimaryBtn")
        self.assertTrue(primary_btn.is_visible())
        self.assertEqual(primary_btn.get_attribute("data-action"), "open-folder-dialog")

        # Verify shortcut cheatsheet
        shortcuts = self.page.locator(".welcome-shortcut-key").all_text_contents()
        self.assertTrue(any("Ctrl + O" in s for s in shortcuts))
        self.assertTrue(any("Ctrl + N" in s for s in shortcuts))

    def test_wso_03_transition_to_workspace_no_tabs(self):
        """TC-WSO-03: Setting workspace.rootPath switches to WORKSPACE_NO_TABS hub."""
        self.page.evaluate("""() => {
            window.store.state.workspace.rootPath = '/home/user/projects/my-sample-app';
            window.DeskAIWelcome.sync();
        }""")

        title = self.page.locator("#welcomeTitle").text_content()
        self.assertIn("Workspace: my-sample-app", title)

        # Active workspace banner present
        ws_banner = self.page.locator(".welcome-workspace-banner")
        self.assertTrue(ws_banner.is_visible())
        self.assertIn("my-sample-app", ws_banner.text_content())
        self.assertIn("/home/user/projects/my-sample-app", ws_banner.text_content())

        # Primary CTA changes to New File
        primary_btn = self.page.locator("#welcomePrimaryBtn")
        self.assertEqual(primary_btn.get_attribute("data-action"), "new-file")

        # Secondary actions present
        open_file_btn = self.page.locator('.welcome-btn[data-action="open-file-dialog"]')
        self.assertTrue(open_file_btn.is_visible())
        open_term_btn = self.page.locator('.welcome-btn[data-action="drawer-tab"][data-target="terminal"]')
        self.assertTrue(open_term_btn.is_visible())

    def test_wso_04_transition_to_hidden_on_buffer_creation(self):
        """TC-WSO-04: Creating an editor buffer hides #welcomeScreen."""
        self.page.evaluate("""() => {
            window.EditorManager.createBuffer('test.py', 'print("hello")');
        }""")

        welcome = self.page.locator("#welcomeScreen")
        self.assertFalse(welcome.is_visible())
        self.assertEqual(welcome.get_attribute("aria-hidden"), "true")

    def test_wso_05_transition_back_on_tab_closure(self):
        """TC-WSO-05: Closing the only open tab restores #welcomeScreen."""
        # Setup with workspace root and create a buffer
        self.page.evaluate("""() => {
            window.store.state.workspace.rootPath = '/home/user/projects/deskai-demo';
            const tabId = window.EditorManager.createBuffer('demo.js', 'console.log(123)');
            window.currentDemoTabId = tabId;
        }""")

        welcome = self.page.locator("#welcomeScreen")
        self.assertFalse(welcome.is_visible())

        # Close the tab
        self.page.evaluate("""() => {
            window.EditorManager.closeTab(window.currentDemoTabId);
        }""")

        # Welcome screen must be restored
        self.assertTrue(welcome.is_visible())
        title = self.page.locator("#welcomeTitle").text_content()
        self.assertIn("Workspace: deskai-demo", title)

    def test_wso_06_native_bridge_readiness_and_select_folder(self):
        """TC-WSO-06: Clicking open-folder-dialog updates workspace root and header pill."""
        self.page.evaluate("""() => {
            window.pywebview = {
                api: {
                    select_folder: async () => ({
                        status: 'ok',
                        path: '/mock/workspace/project-alpha',
                        name: 'project-alpha'
                    })
                }
            };
        }""")

        self.page.locator('#welcomePrimaryBtn[data-action="open-folder-dialog"]').click()

        # Wait for state update
        self.page.wait_for_function("() => window.store.state.workspace.rootPath === '/mock/workspace/project-alpha'")

        pill = self.page.locator("#headerWorkspacePill").text_content()
        self.assertEqual(pill, "DeskAI / project-alpha")

        # Verify welcome screen transitioned to workspace hub
        title = self.page.locator("#welcomeTitle").text_content()
        self.assertIn("Workspace: project-alpha", title)

    def test_wso_07_keyboard_roving_and_focus(self):
        """TC-WSO-07: focusPrimary() puts focus on primary CTA button."""
        self.page.evaluate("""() => {
            window.DeskAIWelcome.focusPrimary();
        }""")

        active_id = self.page.evaluate("() => document.activeElement ? document.activeElement.id : null")
        self.assertEqual(active_id, "welcomePrimaryBtn")

    def test_wso_08_strict_xss_mitigation_on_malicious_paths(self):
        """TC-WSO-08: Malicious folder paths render strictly as text and do not execute scripts."""
        malicious_path = (
            "<script id='xssProbe'>window._xssFired=true;</script><img src='invalid' onerror='window._xssImg=true;' />"
        )

        self.page.evaluate(
            """(badPath) => {
            window.store.state.workspace.rootPath = badPath;
            window.DeskAIWelcome.sync();
        }""",
            malicious_path,
        )

        # Check no XSS execution happened
        xss_fired = self.page.evaluate("() => Boolean(window._xssFired || window._xssImg)")
        self.assertFalse(xss_fired)

        # Ensure no <script id='xssProbe'> exists in the DOM
        script_probe = self.page.locator("#xssProbe")
        self.assertEqual(script_probe.count(), 0)

        # Ensure the malicious string was safely rendered as textContent
        path_text = self.page.locator(".welcome-workspace-path").text_content()
        self.assertEqual(path_text, malicious_path)
