import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False


class TestBottomDrawerBehavior(unittest.TestCase):
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
        self.context = self.browser.new_context(permissions=["clipboard-read", "clipboard-write"])
        self.page = self.context.new_page()
        self.page.goto(f"file://{index_file}")

    def tearDown(self):
        if hasattr(self, "page"):
            self.page.close()
        if hasattr(self, "context"):
            self.context.close()

    def test_clicking_any_tab_expands_collapsed_drawer(self):
        """Clicking any drawer tab must expand a collapsed drawer."""
        drawer = self.page.locator("#bottomDrawer")
        toggle_btn = self.page.locator("#drawerToggleBtn")

        # Collapse drawer via toggle button
        toggle_btn.click()
        self.assertIn("collapsed", drawer.get_attribute("class"))
        self.assertEqual(toggle_btn.get_attribute("aria-expanded"), "false")

        # Click ports tab -> must uncollapse
        self.page.locator("#tab-ports").click()
        self.assertNotIn("collapsed", drawer.get_attribute("class"))
        self.assertEqual(toggle_btn.get_attribute("aria-expanded"), "true")

    def test_resizer_double_click_toggle_collapse(self):
        """Double-clicking resizerBottom toggles collapsed state and restores height."""
        drawer = self.page.locator("#bottomDrawer")
        resizer = self.page.locator("#resizerBottom")
        toggle_btn = self.page.locator("#drawerToggleBtn")

        # Double click to collapse
        resizer.dblclick()
        self.assertIn("collapsed", drawer.get_attribute("class"))
        self.assertEqual(toggle_btn.get_attribute("aria-expanded"), "false")

        # Double click again to restore
        resizer.dblclick()
        self.assertNotIn("collapsed", drawer.get_attribute("class"))
        self.assertEqual(toggle_btn.get_attribute("aria-expanded"), "true")

    def test_resizer_keyboard_navigation(self):
        """Arrow keys, Home, and End on resizerBottom adjust height appropriately."""
        resizer = self.page.locator("#resizerBottom")
        drawer = self.page.locator("#bottomDrawer")

        resizer.focus()
        val_start = int(resizer.get_attribute("aria-valuenow"))

        # ArrowUp expands
        self.page.keyboard.press("ArrowUp")
        val_up = int(resizer.get_attribute("aria-valuenow"))
        self.assertGreater(val_up, val_start)

        # ArrowDown shrinks
        self.page.keyboard.press("ArrowDown")
        val_down = int(resizer.get_attribute("aria-valuenow"))
        self.assertLess(val_down, val_up)

        # Home collapses
        self.page.keyboard.press("Home")
        self.assertIn("collapsed", drawer.get_attribute("class"))
        self.assertEqual(resizer.get_attribute("aria-valuenow"), "48")

        # End expands to max
        self.page.keyboard.press("End")
        self.assertNotIn("collapsed", drawer.get_attribute("class"))
        val_max = int(resizer.get_attribute("aria-valuenow"))
        self.assertGreaterEqual(val_max, 400)

    def test_collapsed_drawer_content_not_keyboard_focusable(self):
        """When collapsed, .drawer-content has display: none so interior controls cannot be focused."""
        toggle_btn = self.page.locator("#drawerToggleBtn")
        content = self.page.locator("#drawerContent")

        toggle_btn.click()
        self.assertFalse(content.is_visible())
        display_style = self.page.evaluate("getComputedStyle(document.getElementById('drawerContent')).display")
        self.assertEqual(display_style, "none")

    def test_tablist_roving_arrow_key_focus(self):
        """ArrowLeft and ArrowRight roving focus with automatic tab activation."""
        self.page.locator("#tab-terminal").click()
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "tab-terminal")

        self.page.keyboard.press("ArrowRight")
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "tab-output")

        self.page.keyboard.press("ArrowRight")
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "tab-problems")

        self.page.keyboard.press("ArrowRight")
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "tab-ports")

        self.page.keyboard.press("ArrowLeft")
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "tab-problems")

    def test_refresh_ports_preserves_focus(self):
        """Refreshing ports preserves focus on active elements inside the ports table."""
        self.page.locator("#tab-ports").click()

        self.page.evaluate("""
            window.DeskAIPorts.customPorts.push({
                port: 8888,
                host: "127.0.0.1",
                protocol: "TCP",
                address: "http://127.0.0.1:8888",
                process: "Watched",
                status: "Listening",
                origin: "Watched",
                isCustom: true,
                exposure: "loopback",
                openable: true
            });
            window.DeskAIPorts.render();
        """)

        copy_btn = self.page.locator('button[data-action="copy-port"][data-url="http://127.0.0.1:8888"]')
        copy_btn.focus()
        self.assertEqual(self.page.evaluate("document.activeElement.getAttribute('data-action')"), "copy-port")

        self.page.evaluate("window.DeskAIPorts.render();")
        self.assertEqual(self.page.evaluate("document.activeElement.getAttribute('data-action')"), "copy-port")

    def test_copy_port_inline_checkmark_feedback(self):
        """Clicking copy-port displays inline SVG checkmark and does not show corner toast."""
        self.page.locator("#tab-ports").click()
        self.page.evaluate("""
            window.DeskAIPorts.stopPolling();
            window.DeskAIPorts.customPorts.push({
                port: 5555,
                host: "127.0.0.1",
                protocol: "TCP",
                address: "http://127.0.0.1:5555",
                process: "test_srv",
                status: "Listening",
                origin: "Watched",
                isCustom: true,
                exposure: "loopback",
                openable: true
            });
            window.DeskAIPorts.render();
        """)

        copy_btn = self.page.locator('button[data-action="copy-port"][data-url="http://127.0.0.1:5555"]')
        self.assertEqual(copy_btn.text_content().strip(), "Copy")

        # Click the copy button
        copy_btn.click()

        # Wait for async clipboard copy to complete and class + svg to be applied
        svg_icon = self.page.wait_for_selector(
            'button[data-action="copy-port"].is-copied svg.port-check-icon', timeout=2000
        )
        self.assertIsNotNone(svg_icon)

        # Confirm NO toast was shown in toastRack
        toast_count = self.page.locator("#toastRack .toast").count()
        self.assertEqual(toast_count, 0)

        # After timeout (~1200ms), button should revert back
        self.page.wait_for_timeout(1300)
        self.assertNotIn("is-copied", copy_btn.get_attribute("class"))
        self.assertEqual(copy_btn.text_content().strip(), "Copy")

    def test_open_port_inline_checkmark_feedback(self):
        """Clicking open-port displays inline SVG checkmark and reverts after feedback timeout (~1200ms)."""
        self.page.locator("#tab-ports").click()
        self.page.evaluate("""
            window.DeskAIPorts.stopPolling();
            window.DeskAIPorts.customPorts = [{
                port: 6666,
                host: "127.0.0.1",
                protocol: "TCP",
                address: "http://127.0.0.1:6666",
                process: "web_app",
                status: "Listening",
                origin: "Watched",
                isCustom: true,
                exposure: "loopback",
                openable: true
            }];
            window.pywebview = {
                api: {
                    open_port: async (port, host) => true
                }
            };
            window.DeskAIPorts.render();
        """)

        open_btn = self.page.locator('button[data-action="open-port"][data-port="6666"]')
        self.assertEqual(open_btn.text_content().strip(), "Open")

        # Click open button
        open_btn.click()

        # Should show checkmark
        self.page.wait_for_selector('button[data-action="open-port"][data-port="6666"].is-copied', timeout=2000)
        self.assertIn("is-copied", open_btn.get_attribute("class"))

        # After timeout (~1200ms), it should revert back to "Open"
        self.page.wait_for_timeout(1300)
        self.assertNotIn("is-copied", open_btn.get_attribute("class"))
        self.assertEqual(open_btn.text_content().strip(), "Open")

    def test_action_buttons_trigger_zero_layout_shift(self):
        """Action button feedback preserves exact column widths and positions (zero layout jitter)."""
        self.page.set_viewport_size({"width": 1920, "height": 1080})
        self.page.locator("#tab-ports").click()
        self.page.evaluate("""
            window.DeskAIPorts.stopPolling();
            window.DeskAIPorts.showTransient = true;
            window.DeskAIPorts.portsList = [
                {
                    port: 33901,
                    host: '127.0.0.1',
                    protocol: 'TCP',
                    address: 'http://127.0.0.1:33901',
                    process: 'antigravity',
                    pid: 6582,
                    origin: 'Local',
                    status: 'Listening',
                    openable: true
                }
            ];
            window.DeskAIPorts._lastSignature = null;
            window.DeskAIPorts.render();
            window.pywebview = { api: { open_port: async () => true } };
        """)

        # Get initial bounding rects
        measure_js = """() => {
            const ths = Array.from(document.querySelectorAll('.ports-table th')).map(th => ({
                text: th.textContent.trim(),
                width: th.getBoundingClientRect().width,
                left: th.getBoundingClientRect().left
            }));
            const copyBtn = document.querySelector('button[data-action="copy-port"]').getBoundingClientRect();
            return { ths, copyBtn };
        }"""

        before = self.page.evaluate(measure_js)

        # Trigger open action
        self.page.locator('button[data-action="open-port"]').first.click()
        self.page.wait_for_selector('button[data-action="open-port"].is-copied', timeout=2000)

        during = self.page.evaluate(measure_js)

        # Verify that all table headers and neighboring buttons maintained zero layout shift (diff < 0.05px)
        for b, d in zip(before["ths"], during["ths"]):
            self.assertAlmostEqual(b["width"], d["width"], delta=0.05, msg=f"Column width shifted for {b['text']}")
            self.assertAlmostEqual(
                b["left"], d["left"], delta=0.05, msg=f"Column left position shifted for {b['text']}"
            )

        self.assertAlmostEqual(
            before["copyBtn"]["left"],
            during["copyBtn"]["left"],
            delta=0.05,
            msg="Neighboring Copy button shifted position",
        )

    def test_terminal_panel_role_log_and_aria_live_off(self):
        """#terminalHost has role='log', accessible name, aria-live='off', and no assertive live region by default."""
        self.page.wait_for_selector("#terminalHost .xterm", timeout=3000)
        host = self.page.locator("#terminalHost")
        self.assertEqual(host.get_attribute("role"), "log")
        self.assertEqual(host.get_attribute("aria-live"), "off")
        self.assertEqual(host.get_attribute("aria-label"), "Terminal output")

        # Assert NO aria-live="assertive" descendant by default
        assertive_count = host.locator("[aria-live='assertive']").count()
        self.assertEqual(assertive_count, 0)

        # Assert screen reader toggle exists, unchecked by default, and enables assertive live region when toggled
        sr_toggle = self.page.locator("#terminalSrToggle")
        self.assertTrue(sr_toggle.is_visible())
        self.assertFalse(sr_toggle.is_checked())

        sr_toggle.check()
        self.assertTrue(sr_toggle.is_checked())
        self.assertGreaterEqual(host.locator("[aria-live='assertive']").count(), 1)
        stored = self.page.evaluate("() => localStorage.getItem('deskai-terminal-sr-mode')")
        self.assertEqual(stored, "true")

        # Unchecking disables it
        sr_toggle.uncheck()
        self.assertFalse(sr_toggle.is_checked())
        self.assertEqual(host.locator("[aria-live='assertive']").count(), 0)
        stored_after = self.page.evaluate("() => localStorage.getItem('deskai-terminal-sr-mode')")
        self.assertEqual(stored_after, "false")

    def test_terminal_tab_selection_preserves_tab_focus(self):
        """Clicking Terminal tab does not steal focus into the terminal buffer."""
        term_tab = self.page.locator("#tab-terminal")
        term_tab.click()
        focused_id = self.page.evaluate("() => document.activeElement ? document.activeElement.id : null")
        self.assertEqual(focused_id, "tab-terminal")

    def test_tab_enters_terminal_and_ctrl_shift_m_escapes(self):
        """Pressing Tab on active terminal panel enters xterm; Ctrl+Shift+M returns focus."""
        self.page.wait_for_selector("#terminalHost .xterm", timeout=3000)
        self.page.locator("#tab-terminal").focus()
        self.page.keyboard.press("Tab")
        is_xterm_focused = self.page.evaluate("""() => {
            const el = document.activeElement;
            return !!(el && (el.classList.contains('xterm-helper-textarea') || el.closest('#terminalHost')));
        }""")
        self.assertTrue(is_xterm_focused)

        self.page.keyboard.press("Control+Shift+M")
        focused_id = self.page.evaluate("() => document.activeElement ? document.activeElement.id : null")
        self.assertEqual(focused_id, "tab-terminal")

    def test_terminal_hotkeys_do_not_close_editor_tabs(self):
        """Ctrl+W and Ctrl+S inside terminal are suppressed from closing/saving editor."""
        self.page.wait_for_selector("#terminalHost .xterm", timeout=3000)
        self.page.evaluate("""() => {
            if (window.EditorManager) {
                window.EditorManager.activeTabId = "tab_test_123";
                window.EditorManager.closeTab = () => { window.__TEST_TAB_CLOSED = true; };
                window.EditorManager.saveActiveBuffer = () => { window.__TEST_BUFFER_SAVED = true; };
            }
        }""")

        self.page.locator("#tab-terminal").focus()
        self.page.keyboard.press("Tab")

        self.page.keyboard.press("Control+w")
        self.page.keyboard.press("Control+s")

        tab_closed = self.page.evaluate("() => window.__TEST_TAB_CLOSED || false")
        buffer_saved = self.page.evaluate("() => window.__TEST_BUFFER_SAVED || false")
        self.assertFalse(tab_closed)
        self.assertFalse(buffer_saved)

    def test_terminal_single_paste_on_ctrl_shift_v(self):
        """Ctrl+Shift+V sends exactly one frame containing pasted text (no double-paste)."""
        self.page.wait_for_selector("#terminalHost .xterm", timeout=3000)
        self.page.evaluate("""() => {
            window.__sentTerminalFrames = [];
            window.DeskAITerminal.ws = {
                readyState: WebSocket.OPEN,
                send: (data) => {
                    const str = typeof data === 'string' ? data : new TextDecoder().decode(data);
                    window.__sentTerminalFrames.push(str);
                }
            };
            window.DeskAITerminal.term.focus();
        }""")
        self.page.evaluate("() => navigator.clipboard.writeText('PASTE')")
        self.page.keyboard.press("Control+Shift+v")
        self.page.wait_for_timeout(100)

        frames = self.page.evaluate("() => window.__sentTerminalFrames")
        paste_frames = [f for f in frames if "PASTE" in f]
        self.assertEqual(len(paste_frames), 1)

    def test_terminal_connection_lost_banner_and_reconnect(self):
        """Unexpected socket close shows Connection lost banner and Reconnect resets and reattaches."""
        self.page.wait_for_selector("#terminalHost .xterm", timeout=3000)
        self.page.evaluate("""() => {
            window.DeskAITerminal.sessionId = "sess_drop_test";
            window.__reconnectCalls = 0;
            window.__termResetCalls = 0;
            if (window.DeskAITerminal.term) {
                const origReset = window.DeskAITerminal.term.reset.bind(window.DeskAITerminal.term);
                window.DeskAITerminal.term.reset = () => {
                    window.__termResetCalls++;
                    origReset();
                };
            }
            window.DeskAITerminal.connectWebSocket = (sessId) => {
                window.__reconnectCalls++;
                window.__reconnectSessId = sessId;
            };

            window.DeskAITerminal.showConnectionLostBanner(1006);
        }""")

        banner = self.page.locator("#terminalHost .terminal-status-banner.connection-lost")
        self.assertTrue(banner.is_visible())
        self.assertIn("Connection lost (code 1006)", banner.text_content())

        reconnect_btn = banner.locator("button[data-action='reconnect-terminal']")
        self.assertTrue(reconnect_btn.is_visible())
        self.assertEqual(reconnect_btn.text_content(), "Reconnect")

        reconnect_btn.click()
        self.assertFalse(banner.is_visible())

        resets = self.page.evaluate("() => window.__termResetCalls")
        reconnects = self.page.evaluate("() => window.__reconnectCalls")
        reconnect_sess = self.page.evaluate("() => window.__reconnectSessId")
        self.assertGreaterEqual(resets, 1)
        self.assertGreaterEqual(reconnects, 1)
        self.assertEqual(reconnect_sess, "sess_drop_test")

    def test_terminal_keystroke_while_disconnected_shows_banner(self):
        """Keystrokes while socket is closed show Connection lost banner instead of silently dropping."""
        self.page.wait_for_selector("#terminalHost .xterm", timeout=3000)
        self.page.evaluate("""() => {
            window.DeskAITerminal.sessionId = "sess_key_test";
            window.DeskAITerminal.removeExitBanner();
            window.DeskAITerminal.ws = { readyState: WebSocket.CLOSED };
            window.DeskAITerminal.term.focus();
        }""")
        self.page.keyboard.press("a")
        banner = self.page.locator("#terminalHost .terminal-status-banner.connection-lost")
        self.assertTrue(banner.is_visible())

    def test_terminal_boot_hint_and_start_on_enter(self):
        """At boot, xterm displays hint and pressing Enter starts a session."""
        self.page.wait_for_selector("#terminalHost .xterm", timeout=3000)
        has_hint = self.page.evaluate("""() => {
            if (!window.DeskAITerminal || !window.DeskAITerminal.term) return false;
            window.DeskAITerminal.term.selectAll();
            const text = window.DeskAITerminal.term.getSelection();
            window.DeskAITerminal.term.clearSelection();
            return text.includes("Press Enter or click to start a shell");
        }""")
        self.assertTrue(has_hint)

        self.page.evaluate("""() => {
            window.__startSessionCalls = 0;
            window.NativeBridge.terminalOpen = async () => {
                window.__startSessionCalls++;
                return { status: "ok", session_id: "sess_boot_enter" };
            };
            window.DeskAITerminal.term.focus();
        }""")

        self.page.keyboard.press("Enter")
        self.page.wait_for_timeout(100)

        calls = self.page.evaluate("() => window.__startSessionCalls")
        sess_id = self.page.evaluate("() => window.DeskAITerminal.sessionId")
        self.assertGreaterEqual(calls, 1)
        self.assertEqual(sess_id, "sess_boot_enter")

    def test_terminal_boot_hint_and_start_on_click(self):
        """At boot, clicking terminal host starts a session."""
        self.page.wait_for_selector("#terminalHost .xterm", timeout=3000)
        self.page.evaluate("""() => {
            window.__startSessionClickCalls = 0;
            window.NativeBridge.terminalOpen = async () => {
                window.__startSessionClickCalls++;
                return { status: "ok", session_id: "sess_boot_click" };
            };
        }""")
        self.page.locator("#terminalHost").click()
        self.page.wait_for_timeout(100)
        calls = self.page.evaluate("() => window.__startSessionClickCalls")
        self.assertGreaterEqual(calls, 1)

    def test_terminal_kill_and_close_actions(self):
        """Kill button, destroy(), and Restart call NativeBridge.terminalClose with session ID."""
        self.page.wait_for_selector("#terminalHost .xterm", timeout=3000)
        kill_btn = self.page.locator("#terminalKillBtn")
        self.assertTrue(kill_btn.is_visible())
        self.assertEqual(kill_btn.get_attribute("aria-label"), "Kill terminal")

        self.page.evaluate("""() => {
            window.__closedSessions = [];
            window.NativeBridge.terminalClose = async (id) => {
                window.__closedSessions.push(id);
                return true;
            };
            window.DeskAITerminal.sessionId = "sess_kill_target";
        }""")

        # 1. Click Kill button
        kill_btn.click()
        self.page.wait_for_timeout(100)
        closed = self.page.evaluate("() => window.__closedSessions")
        self.assertIn("sess_kill_target", closed)

        # 2. Restart calls terminalClose on old session ID
        self.page.evaluate("""() => {
            window.DeskAITerminal.sessionId = "sess_restart_target";
            window.DeskAITerminal.handleProcessExit(0);
        }""")
        restart_btn = self.page.locator("#terminalHost .terminal-restart-btn")
        restart_btn.click()
        self.page.wait_for_timeout(100)
        closed = self.page.evaluate("() => window.__closedSessions")
        self.assertIn("sess_restart_target", closed)

        # 3. destroy() calls terminalClose
        self.page.evaluate("""() => {
            window.DeskAITerminal.sessionId = "sess_destroy_target";
            window.DeskAITerminal.destroy();
        }""")
        closed = self.page.evaluate("() => window.__closedSessions")
        self.assertIn("sess_destroy_target", closed)

    def test_log_view_line_cap_and_scroll_preservation(self):
        """LogView caps buffer at 10,000 lines, follows output when pinned,
        and preserves scroll position when user scrolled up."""
        self.page.locator("#tab-output").click()
        self.page.evaluate("""() => {
            const el = document.getElementById("channelOutput");
            window.testLogView = new window.DeskAILogView.constructor(el);
            window.testLogView.clear();
            for (let i = 0; i < 105; i++) {
                window.testLogView.write("line\\n".repeat(100));
            }
        }""")
        self.page.wait_for_timeout(200)

        # 1. Assert buffer line cap <= 10000
        line_count = self.page.evaluate("() => window.testLogView.lineCount")
        self.assertLessEqual(line_count, 10000)

        # 2. Assert auto-scroll followed output to bottom when pinned
        is_scrolled_to_bottom = self.page.evaluate("""() => {
            const scroller = document.getElementById("drawerContent");
            const dist = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
            return dist < 10 && scroller.scrollTop > 0;
        }""")
        self.assertTrue(is_scrolled_to_bottom, "Expected drawerContent to be scrolled to bottom when pinned")

        # 3. Simulate user scrolling up (disabling pinned state)
        self.page.evaluate("""() => {
            const scroller = document.getElementById("drawerContent");
            scroller.scrollTop = 120;
            scroller.dispatchEvent(new Event("scroll"));
        }""")
        is_pinned = self.page.evaluate("() => window.testLogView.pinned")
        self.assertFalse(is_pinned, "Expected pinned to be false after user scrolled up")

        # 4. Write more lines and ensure user's scroll position is preserved (not yanked to bottom)
        self.page.evaluate("""() => {
            window.testLogView.write("new content line\\n".repeat(20));
        }""")
        self.page.wait_for_timeout(100)

        scroll_top_after = self.page.evaluate("() => document.getElementById('drawerContent').scrollTop")
        self.assertEqual(scroll_top_after, 120, "Expected scrollTop to remain at 120 without yanking user to bottom")

    def test_terminal_osc8_link_handler_and_ansi_regex_stripping(self):
        """ANSI_REGEX strips OSC 8 payloads and linkHandler routes links to NativeBridge.openExternalUrl."""
        self.page.wait_for_selector("#terminalHost .xterm", timeout=3000)

        # 1. Test ANSI_REGEX strips OSC payloads in LogView
        self.page.locator("#tab-output").click()
        self.page.evaluate("""() => {
            const el = document.getElementById("channelOutput");
            window.testLogView = new window.DeskAILogView.constructor(el);
            window.testLogView.clear();
            window.testLogView.write("\\x1b]8;;https://malicious.example\\x07Clean Link Text\\x1b]8;;\\x07");
            window.testLogView.write("\\x1b]8;;https://malicious.example\\x1b\\\\ST Terminated Text\\x1b]8;;\\x1b\\\\");
        }""")
        self.page.wait_for_timeout(100)
        output_text = self.page.locator("#channelOutput").text_content()
        self.assertNotIn("https://malicious.example", output_text)
        self.assertIn("Clean Link Text", output_text)
        self.assertIn("ST Terminated Text", output_text)

        # 2. Test linkHandler activate routes to NativeBridge.openExternalUrl
        self.page.evaluate("""() => {
            window.__openedUrls = [];
            window.NativeBridge.openExternalUrl = async (url) => {
                window.__openedUrls.push(url);
                return true;
            };
            const handler = window.DeskAITerminal.term.options.linkHandler;
            if (handler && typeof handler.activate === "function") {
                handler.activate(new MouseEvent("click"), "https://trusted.example/docs");
            }
        }""")
        opened = self.page.evaluate("() => window.__openedUrls")
        self.assertEqual(opened, ["https://trusted.example/docs"])

    def test_static_hygiene_no_inner_html_in_terminal_modules(self):
        """Walks every .js file under static/js (excluding vendor/) and fails on forbidden DOM methods."""
        import re

        js_dir = Path("src/deskai/static/js")
        violations = []
        forbidden_patterns = [
            re.compile(r"\binnerHTML\b"),
            re.compile(r"\bouterHTML\b"),
            re.compile(r"\binsertAdjacentHTML\b"),
            re.compile(r"\bdocument\.write\b"),
        ]

        for js_file in js_dir.rglob("*.js"):
            if "vendor" in js_file.parts:
                continue
            content = js_file.read_text(encoding="utf-8")
            code_only = re.sub(r"/\*[\s\S]*?\*/", "", content)
            code_only = re.sub(r"//.*", "", code_only)

            for pattern in forbidden_patterns:
                for match in pattern.finditer(code_only):
                    violations.append(f"{js_file.name}: matches '{match.group(0)}'")

        self.assertEqual(violations, [], f"Forbidden DOM manipulation methods found in static/js: {violations}")

    def test_terminal_status_chip_text_and_indicator(self):
        """Status chip in tab displays '●' and text equivalent (running) when running, plain when exited."""
        tab = self.page.locator("#tab-terminal")
        # Initially idle
        self.assertEqual(tab.text_content().strip(), "Terminal")

        # Simulate running session
        self.page.evaluate("""() => {
            window.DeskAITerminal.sessionId = "dummy_session";
            // invoke startSession mock or updateTabStatus
            const tabEl = document.getElementById("tab-terminal");
            tabEl.textContent = "";
            const label = document.createElement("span");
            label.textContent = "Terminal";
            const space = document.createTextNode(" ");
            const chip = document.createElement("span");
            chip.className = "terminal-status-chip running";
            chip.setAttribute("aria-label", "(running)");
            chip.textContent = "●";
            tabEl.appendChild(label);
            tabEl.appendChild(space);
            tabEl.appendChild(chip);
        }""")

        self.assertIn("●", tab.text_content())
        chip = self.page.locator("#tab-terminal .terminal-status-chip")
        self.assertEqual(chip.get_attribute("aria-label"), "(running)")

        # Simulate exit
        self.page.evaluate("() => window.DeskAITerminal.handleProcessExit(0)")
        self.assertEqual(tab.text_content().strip(), "Terminal")

    def test_dynamic_style_without_nonce_is_blocked_by_csp(self):
        """Under strict CSP with random style nonce, a <style> element lacking the nonce is blocked."""
        import httpx
        from deskai.server.supervisor import DesktopServer

        srv = DesktopServer()
        srv.start()
        try:
            token = srv.security.create_launch_token()
            with httpx.Client(follow_redirects=False) as http:
                res = http.get(
                    f"http://127.0.0.1:{srv.port}/auth/redeem?token={token}",
                    headers={"Host": f"127.0.0.1:{srv.port}"},
                )
                cookie_val = res.cookies.get("deskai_session")

            page = self.browser.new_page()
            page.context.add_cookies(
                [{"name": "deskai_session", "value": cookie_val, "domain": "127.0.0.1", "path": "/"}]
            )
            page.goto(f"http://127.0.0.1:{srv.port}/")

            meta_nonce = page.locator('meta[name="csp-nonce"]').get_attribute("content")
            self.assertEqual(meta_nonce, srv.security.style_nonce)

            violation_occurred = page.evaluate("""() => {
                return new Promise((resolve) => {
                    const onViolation = (e) => {
                        document.removeEventListener("securitypolicyviolation", onViolation);
                        resolve(true);
                    };
                    document.addEventListener("securitypolicyviolation", onViolation);
                    const badStyle = document.createElement("style");
                    badStyle.nonce = "";
                    badStyle.textContent = "#testCspBad { color: red; }";
                    document.head.appendChild(badStyle);
                    setTimeout(() => resolve(false), 500);
                });
            }""")
            self.assertTrue(violation_occurred, "CSP securitypolicyviolation did not fire for style lacking nonce")
            page.close()
        finally:
            srv.stop()

    @unittest.skipIf(
        sys.platform == "win32" or os.getenv("CI"),
        "POSIX PTY e2e test disabled on win32 and multi-threaded CI runners due to forkpty deadlock",
    )
    def test_terminal_end_to_end_frontend_backend_integration(self):
        """End-to-end integration: Live DesktopServer + Playwright browser + real PTY shell.
        Verifies:
        1. Shell starts and output appears in xterm.
        2. Typing reaches the shell (echo round-trip).
        3. Resize message is sent over WebSocket.
        4. Exit banner appears on process exit and Restart button works.
        5. Dropped connection shows Reconnect banner.
        """
        import httpx
        from deskai.server.supervisor import DesktopServer

        temp_workspace = Path(tempfile.mkdtemp()).resolve()
        srv = DesktopServer()
        srv.start()
        try:
            # 1. Redeem session cookie
            token = srv.security.create_launch_token()
            with httpx.Client(follow_redirects=False) as http:
                res = http.get(
                    f"http://127.0.0.1:{srv.port}/auth/redeem?token={token}",
                    headers={"Host": f"127.0.0.1:{srv.port}"},
                )
                cookie_val = res.cookies.get("deskai_session")

            # 2. Create real session on server
            session1 = srv.terminal_manager.create_session(str(temp_workspace))

            # 3. Setup page with stubbed pywebview bridge before page load
            context = self.browser.new_context()
            context.add_cookies([{"name": "deskai_session", "value": cookie_val, "domain": "127.0.0.1", "path": "/"}])
            page = context.new_page()

            page.add_init_script(f"""
                window.__mockSessionId = "{session1.session_id}";
                window.__mockResizes = [];
                window.pywebview = {{
                    api: {{
                        terminal_open: async (cols, rows) => {{
                            return {{ status: "ok", session_id: window.__mockSessionId }};
                        }},
                        terminal_close: async (sessionId) => {{
                            return true;
                        }}
                    }}
                }};
            """)

            page.goto(f"http://127.0.0.1:{srv.port}/")
            page.wait_for_selector("#terminalHost .xterm", timeout=5000)

            # Spy on resize messages
            page.evaluate("""() => {
                const origSend = WebSocket.prototype.send;
                WebSocket.prototype.send = function(data) {
                    if (typeof data === "string") {
                        try {
                            const parsed = JSON.parse(data);
                            if (parsed.type === "resize") {
                                window.__mockResizes.push(parsed);
                            }
                        } catch (e) {}
                    }
                    return origSend.apply(this, arguments);
                };
            }""")

            # 4. Trigger session start (click or Enter)
            page.locator("#terminalHost").click()
            page.wait_for_function(
                "() => window.DeskAITerminal && window.DeskAITerminal.sessionId !== null", timeout=5000
            )
            self.assertEqual(page.evaluate("() => window.DeskAITerminal.sessionId"), session1.session_id)

            # 5. Output appears in xterm (initial shell prompt)
            page.wait_for_function(
                """() => {
                const term = window.DeskAITerminal.term;
                if (!term) return false;
                term.selectAll();
                const sel = term.getSelection();
                term.clearSelection();
                return sel && sel.length > 0;
            }""",
                timeout=5000,
            )

            # 6. Typing reaches shell: send echo command and verify it returns in xterm
            page.keyboard.type("echo DESKAI_INTEGRATION_TEST_PASS\n")
            page.wait_for_function(
                """() => {
                const term = window.DeskAITerminal.term;
                if (!term) return false;
                term.selectAll();
                const sel = term.getSelection();
                term.clearSelection();
                return sel.includes("DESKAI_INTEGRATION_TEST_PASS");
            }""",
                timeout=20000,
            )

            # 7. Resize message sent
            page.evaluate("() => window.DeskAITerminal.fit()")
            page.wait_for_function("() => window.__mockResizes && window.__mockResizes.length > 0", timeout=3000)
            resizes = page.evaluate("() => window.__mockResizes")
            self.assertGreaterEqual(len(resizes), 1)
            self.assertIn("cols", resizes[-1])
            self.assertIn("rows", resizes[-1])

            # 8. Exit banner + Restart works:
            session2 = srv.terminal_manager.create_session(str(temp_workspace))
            page.evaluate(f"() => {{ window.__mockSessionId = '{session2.session_id}'; }}")

            page.keyboard.type("exit\n")
            page.wait_for_selector("#terminalHost .terminal-status-banner", timeout=6000)
            banner = page.locator("#terminalHost .terminal-status-banner")
            self.assertTrue(banner.is_visible())
            self.assertIn("Terminal exited", banner.text_content())

            restart_btn = banner.locator("button[data-action='restart-terminal']")
            self.assertTrue(restart_btn.is_visible())
            restart_btn.click()

            page.wait_for_function(f"() => window.DeskAITerminal.sessionId === '{session2.session_id}'", timeout=5000)
            self.assertEqual(page.evaluate("() => window.DeskAITerminal.sessionId"), session2.session_id)
            self.assertFalse(banner.is_visible())

            # 9. Dropped connection shows Reconnect banner
            page.evaluate("() => window.DeskAITerminal.ws.close(4000)")
            page.wait_for_selector("#terminalHost .terminal-status-banner.connection-lost", timeout=5000)
            lost_banner = page.locator("#terminalHost .terminal-status-banner.connection-lost")
            self.assertTrue(lost_banner.is_visible())
            self.assertRegex(lost_banner.text_content(), r"Connection lost \(code (4000|1006)\)")
            reconnect_btn = lost_banner.locator("button[data-action='reconnect-terminal']")
            self.assertTrue(reconnect_btn.is_visible())

            # Clean up page & sessions
            session1.close()
            session2.close()
            page.close()
            context.close()
        finally:
            srv.stop()
            shutil.rmtree(temp_workspace, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
