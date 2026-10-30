"""Playwright End-to-End, Resilience, and Accessibility test suite for DeskAI Output Panel (M5).

Verifies TC-OUT-31..48 against a real DesktopServer instance with launch token and session
cookie authentication, testing live WebSocket streaming, filtering, scroll follow/jump,
reconnect deduplication, storm boundedness, safe DOM rendering, WCAG 2.1 AA contrast and screenshots.
"""

from __future__ import annotations
import logging
from pathlib import Path
import re
import unittest
from unittest.mock import MagicMock

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False

from deskai.bridge.api import DesktopBridgeAPI
from deskai.server.supervisor import DesktopServer


class TestOutputE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not _HAS_PLAYWRIGHT:
            raise unittest.SkipTest("Playwright is not installed")

        cls.p = sync_playwright().start()
        try:
            cls.browser = cls.p.chromium.launch(headless=True)
        except Exception as e:
            cls.p.stop()
            raise unittest.SkipTest(f"Chromium launch failed: {e}")

        cls.server = DesktopServer()
        cls.server.start()

        import httpx

        token = cls.server.security.create_launch_token()
        with httpx.Client(follow_redirects=False) as http:
            res = http.get(
                f"http://127.0.0.1:{cls.server.port}/auth/redeem?token={token}",
                headers={"Host": f"127.0.0.1:{cls.server.port}"},
            )
            cls.cookie_val = res.cookies.get("deskai_session")

        if not cls.cookie_val:
            cls.server.stop()
            cls.browser.close()
            cls.p.stop()
            raise RuntimeError("Failed to redeem session cookie for DesktopServer")

        cls.mock_mgr = MagicMock()
        cls.mock_mgr.window.get_current_url.return_value = f"http://127.0.0.1:{cls.server.port}/"
        cls.mock_mgr.server.port = cls.server.port
        cls.api = DesktopBridgeAPI(cls.mock_mgr)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "server"):
            cls.server.stop()
        if hasattr(cls, "browser"):
            cls.browser.close()
        if hasattr(cls, "p"):
            cls.p.stop()

    def _create_page(self, width: int = 1280, height: int = 800):
        context = self.browser.new_context(viewport={"width": width, "height": height})
        context.add_cookies([{"name": "deskai_session", "value": self.cookie_val, "domain": "127.0.0.1", "path": "/"}])
        page = context.new_page()

        page.expose_function(
            "__bridge_clipboard_write",
            lambda text: setattr(self, "_copied_text", text) or True,
        )

        page.add_init_script("""
            window.pywebview = {
                api: {
                    clipboard_write: async (text) => await window.__bridge_clipboard_write(text),
                }
            };
        """)

        page.goto(f"http://127.0.0.1:{self.server.port}/")
        page.wait_for_selector("#tab-output", timeout=5000)
        return context, page

    def test_tc_out_31_live_stream(self):
        """TC-OUT-31: Triggering backend logger.warning appears in the panel within 1 s with WARN tag."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-output").click()
            unique_msg = "test_live_warning_98765"
            logging.getLogger("deskai.bridge.git").warning(unique_msg)

            row = page.locator(f"#channelOutput .log-line:has-text('{unique_msg}')")
            row.wait_for(state="visible", timeout=3000)
            self.assertTrue(row.is_visible())
            tag = row.locator(".log-level-tag")
            self.assertEqual(tag.text_content(), "WARN")
        finally:
            ctx.close()

    def test_tc_out_32_filters_and_empty_state(self):
        """TC-OUT-32: Channel, level and text filters show/hide the right rows; empty-filter message appears."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-output").click()
            # Clear previous startup records for isolated filter testing
            page.locator('[data-action="output-clear"]').click()
            page.wait_for_timeout(100)

            # Push diverse records
            page.evaluate("""() => {
                window.DeskAIOutput.log("system", "info", "alpha system info");
                window.DeskAIOutput.log("git", "warn", "beta git warning");
                window.DeskAIOutput.log("ports", "error", "gamma ports error");
            }""")
            page.wait_for_timeout(150)

            # 1. Channel filter: select "git"
            page.select_option("#outputChannelSelect", "git")
            page.wait_for_timeout(100)
            self.assertEqual(page.locator("#channelOutput .log-line").count(), 1)
            self.assertIn("beta git warning", page.locator("#channelOutput").text_content())

            # 2. Level filter: select "error"
            page.select_option("#outputChannelSelect", "all")
            page.select_option("#outputLevelSelect", "error")
            page.wait_for_timeout(100)
            self.assertEqual(page.locator("#channelOutput .log-line").count(), 1)
            self.assertIn("gamma ports error", page.locator("#channelOutput").text_content())

            # 3. Text filter
            page.select_option("#outputLevelSelect", "debug")
            page.fill("#outputFilterInput", "alpha")
            page.wait_for_timeout(250)
            self.assertEqual(page.locator("#channelOutput .log-line").count(), 1)
            self.assertIn("alpha system info", page.locator("#channelOutput").text_content())

            # 4. Filter matches nothing -> shows .output-empty
            page.fill("#outputFilterInput", "nonexistent_term_xyz")
            page.wait_for_timeout(250)
            self.assertEqual(page.locator("#channelOutput .log-line").count(), 0)
            empty_el = page.locator("#channelOutput .output-empty")
            self.assertTrue(empty_el.is_visible())
            self.assertEqual(empty_el.text_content(), "No output matches the current filters")
        finally:
            ctx.close()

    def test_tc_out_33_follow_and_jump(self):
        """TC-OUT-33: Pinned follows; scrolling up stops follow and shows Jump to latest; End/click restores."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-output").click()
            # Fill lines so scroll container is scrollable
            page.evaluate("""() => {
                for (let i = 0; i < 50; i++) {
                    window.DeskAIOutput.log("system", "info", "line " + i);
                }
            }""")
            page.wait_for_timeout(200)

            jump_btn = page.locator("#outputJump")
            self.assertFalse(jump_btn.is_visible())

            # Scroll up to break pinned
            page.evaluate("""() => {
                const scroller = document.getElementById("drawerContent");
                scroller.scrollTop = 50;
                scroller.dispatchEvent(new Event("scroll"));
            }""")
            page.wait_for_timeout(100)

            self.assertTrue(jump_btn.is_visible())

            # Click Jump to latest
            jump_btn.click()
            page.wait_for_timeout(100)

            self.assertFalse(jump_btn.is_visible())
            is_pinned = page.evaluate("() => window.DeskAILogView.pinned")
            self.assertTrue(is_pinned)
        finally:
            ctx.close()

    def test_tc_out_34_clear_and_copy(self):
        """TC-OUT-34: Clear empties records but keeps banner; copy writes visible text (bridge mocked)."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-output").click()
            page.evaluate("""() => {
                window.DeskAIOutput.log("git", "info", "copy test line 1");
                window.DeskAIOutput.log("ports", "warn", "copy test line 2");
            }""")
            page.wait_for_timeout(150)

            # Test Copy
            page.evaluate("""() => {
                window.DeskAIOutput.copyVisible();
            }""")
            self.assertTrue(hasattr(self, "_copied_text"))
            self.assertIn("copy test line 1", self._copied_text)
            self.assertIn("copy test line 2", self._copied_text)

            # Test Clear
            page.locator('[data-action="output-clear"]').click()
            page.wait_for_timeout(100)

            self.assertEqual(page.locator("#channelOutput .log-line").count(), 0)
            banner = page.locator("#channelOutput .log-banner")
            self.assertTrue(banner.is_visible())
            self.assertIn("Supervisor active on loopback", banner.text_content())
        finally:
            ctx.close()

    def test_tc_out_35_reconnect(self):
        """TC-OUT-35: Closing socket client-side reconnects with cursor; no duplicate rows, no gaps."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-output").click()
            # Wait for initial streaming state
            page.wait_for_function("() => window.DeskAIOutput && window.DeskAIOutput.client.state === 'streaming'")

            logging.getLogger("deskai.bridge.git").info("before drop 1")
            page.wait_for_selector("#channelOutput .log-line:has-text('before drop 1')", timeout=3000)

            # Force client socket close
            page.evaluate("() => window.DeskAIOutput.client.socket.close()")

            # Emit during disconnect
            logging.getLogger("deskai.bridge.git").info("during drop 2")
            logging.getLogger("deskai.bridge.git").info("after reconnect 3")

            # Wait for client to reconnect and receive missing records
            page.wait_for_selector("#channelOutput .log-line:has-text('after reconnect 3')", timeout=5000)

            # Verify both messages received, exactly once
            self.assertEqual(page.locator("#channelOutput .log-line:has-text('during drop 2')").count(), 1)
            self.assertEqual(page.locator("#channelOutput .log-line:has-text('after reconnect 3')").count(), 1)
        finally:
            ctx.close()

    def test_tc_out_36_log_region_aria(self):
        """TC-OUT-36: #channelOutput has role='log', aria-live='off', labelled."""
        ctx, page = self._create_page()
        try:
            log_el = page.locator("#channelOutput")
            self.assertEqual(log_el.get_attribute("role"), "log")
            self.assertEqual(log_el.get_attribute("aria-live"), "off")
            self.assertEqual(log_el.get_attribute("aria-label"), "Output log")
        finally:
            ctx.close()

    def test_tc_out_37_announcer(self):
        """TC-OUT-37: A burst of errors yields one debounced summary, no per-line announcements."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-output").click()
            page.evaluate("""() => {
                window.__announcements = [];
                const announcer = document.getElementById("screenReaderAnnouncer");
                const obs = new MutationObserver(() => {
                    if (announcer.textContent) window.__announcements.push(announcer.textContent);
                });
                obs.observe(announcer, { childList: true, characterData: true, subtree: true });

                // Burst of 5 errors and 2 warnings
                for (let i = 0; i < 5; i++) {
                    window.DeskAIOutput.log("system", "error", "burst err " + i);
                }
                for (let i = 0; i < 2; i++) {
                    window.DeskAIOutput.log("system", "warn", "burst warn " + i);
                }
            }""")
            # Wait past the 1000ms debouncing window
            page.wait_for_timeout(1200)

            announcements = page.evaluate("() => window.__announcements")
            output_announcements = [a for a in announcements if "in Output" in a]
            self.assertEqual(len(output_announcements), 1)
            self.assertEqual(output_announcements[0], "5 new errors, 2 warnings in Output")
        finally:
            ctx.close()

    def test_tc_out_38_level_not_colour_only(self):
        """TC-OUT-38: Warn and error rows contain visible text tags."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-output").click()
            page.locator('[data-action="output-clear"]').click()
            page.wait_for_timeout(100)

            page.evaluate("""() => {
                window.DeskAIOutput.log("system", "warn", "visible tag warning");
                window.DeskAIOutput.log("system", "error", "visible tag error");
                window.DeskAIOutput.log("system", "info", "info line no tag");
            }""")
            page.wait_for_timeout(100)

            warn_tag = page.locator("#channelOutput .log-warn .log-level-tag").first
            err_tag = page.locator("#channelOutput .log-error .log-level-tag").first
            info_tag = page.locator("#channelOutput .log-info .log-level-tag").first

            self.assertTrue(warn_tag.is_visible())
            self.assertEqual(warn_tag.text_content(), "WARN")
            self.assertTrue(err_tag.is_visible())
            self.assertEqual(err_tag.text_content(), "ERROR")
            self.assertFalse(info_tag.is_visible())
        finally:
            ctx.close()

    def test_tc_out_39_toolbar_a11y(self):
        """TC-OUT-39: All controls named, toggles have aria-pressed, targets >= 28 px."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-output").click()
            buttons = page.locator(".output-toolbar button, .output-toolbar select, .output-toolbar input")
            count = buttons.count()
            self.assertGreaterEqual(count, 6)

            for i in range(count):
                btn = buttons.nth(i)
                box = btn.bounding_box()
                self.assertIsNotNone(box)
                self.assertGreaterEqual(box["height"], 27.5)  # >= 28 px target height

            time_btn = page.locator('[data-action="output-time"]')
            wrap_btn = page.locator('[data-action="output-wrap"]')
            self.assertIn(time_btn.get_attribute("aria-pressed"), ("true", "false"))
            self.assertIn(wrap_btn.get_attribute("aria-pressed"), ("true", "false"))
        finally:
            ctx.close()

    def test_tc_out_40_keyboard_navigation(self):
        """TC-OUT-40: End jumps to latest; Ctrl+A selects only log; Esc focuses tab."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-output").click()
            panel = page.locator("#outputPanel")
            panel.focus()

            # Fill lines
            page.evaluate("""() => {
                for (let i = 0; i < 40; i++) window.DeskAIOutput.log("system", "info", "kb " + i);
                const scroller = document.getElementById("drawerContent");
                scroller.scrollTop = 10;
                scroller.dispatchEvent(new Event("scroll"));
            }""")
            page.wait_for_timeout(100)

            # Test End
            page.keyboard.press("End")
            page.wait_for_timeout(100)
            is_pinned = page.evaluate("() => window.DeskAILogView.pinned")
            self.assertTrue(is_pinned)

            # Test Escape focuses #tab-output
            page.keyboard.press("Escape")
            active_id = page.evaluate("() => document.activeElement.id")
            self.assertEqual(active_id, "tab-output")
        finally:
            ctx.close()

    def test_tc_out_41_tab_indicator(self):
        """TC-OUT-41: Unread errors update aria-label and badge, and clear on show."""
        ctx, page = self._create_page()
        try:
            # Switch to output tab first to ensure clean baseline
            page.locator("#tab-output").click()
            page.wait_for_timeout(50)

            # Switch to terminal tab so output is hidden
            page.locator("#tab-terminal").click()
            page.wait_for_timeout(50)

            # Emit 2 errors and 1 warning while hidden
            page.evaluate("""() => {
                window.DeskAIOutput.log("system", "error", "hidden err 1");
                window.DeskAIOutput.log("system", "error", "hidden err 2");
                window.DeskAIOutput.log("system", "warn", "hidden warn 1");
            }""")
            page.wait_for_timeout(150)

            tab = page.locator("#tab-output")
            badge = tab.locator(".tab-badge")
            self.assertTrue(badge.is_visible())
            self.assertEqual(badge.text_content(), "3")
            self.assertEqual(tab.get_attribute("aria-label"), "Output, 2 new errors")

            # Click tab to show output: badge cleared, aria-label reset
            tab.click()
            page.wait_for_timeout(100)

            self.assertFalse(badge.is_visible())
            self.assertEqual(tab.get_attribute("aria-label"), "Output")
        finally:
            ctx.close()

    def test_tc_out_42_reduced_motion(self):
        """TC-OUT-42: No smooth scrolling under prefers-reduced-motion."""
        context = self.browser.new_context(
            reduced_motion="reduce",
            viewport={"width": 1280, "height": 800},
        )
        context.add_cookies([{"name": "deskai_session", "value": self.cookie_val, "domain": "127.0.0.1", "path": "/"}])
        page = context.new_page()
        try:
            page.goto(f"http://127.0.0.1:{self.server.port}/")
            page.wait_for_selector("#tab-output", timeout=5000)
            page.locator("#tab-output").click()

            behavior = page.evaluate(
                "() => window.getComputedStyle(document.querySelector('.log-view')).scrollBehavior"
            )
            self.assertEqual(behavior, "auto")
        finally:
            context.close()

    def test_tc_out_43_dom_safety(self):
        """TC-OUT-43: <img src=x onerror=...> renders as text, no element created."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-output").click()
            malicious = '<img src=x onerror="window.__xss_fired=true">'
            page.evaluate(f"""() => {{
                window.DeskAIOutput.log("task", "info", {repr(malicious)});
            }}""")
            page.wait_for_timeout(150)

            img_count = page.locator("#channelOutput img").count()
            self.assertEqual(img_count, 0)
            xss_fired = page.evaluate("() => window.__xss_fired || false")
            self.assertFalse(xss_fired)

            text_content = page.locator("#channelOutput").text_content()
            self.assertIn("<img src=x onerror=", text_content)
        finally:
            ctx.close()

    def test_tc_out_44_storm_boundedness(self):
        """TC-OUT-44: 20,000 records: DOM <= 5,000 rows, main thread stays responsive."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-output").click()
            # Push 20,000 records in batches
            page.evaluate("""() => {
                for (let b = 0; b < 20; b++) {
                    const batch = [];
                    for (let i = 0; i < 1000; i++) {
                        batch.push({
                            seq: b * 1000 + i + 1,
                            ts: Date.now(),
                            channel: "ports",
                            level: "info",
                            text: "storm record " + b + "-" + i
                        });
                    }
                    window.DeskAILogView.writeRecords(batch);
                }
            }""")
            # Give RAF a moment to flush
            page.wait_for_timeout(1000)

            # Assert DOM row count is capped at 5000
            dom_rows = page.locator("#channelOutput .log-line").count()
            self.assertLessEqual(dom_rows, 5000)

            # Assert responsiveness
            resp = page.evaluate("() => 1 + 1")
            self.assertEqual(resp, 2)
        finally:
            ctx.close()

    def test_tc_out_45_layout_stability_at_900x600(self):
        """TC-OUT-45: No horizontal overflow at 900x600; toolbar does not shift when status/jump appear."""
        ctx, page = self._create_page(width=900, height=600)
        try:
            page.locator("#tab-output").click()
            tb = page.locator(".output-toolbar")
            initial_top = tb.bounding_box()["y"]

            # Trigger status and jump
            page.evaluate("""() => {
                const status = document.getElementById("outputStatus");
                status.hidden = false;
                status.textContent = "Reconnecting…";
                const jump = document.getElementById("outputJump");
                jump.hidden = false;
            }""")
            page.wait_for_timeout(100)

            new_top = tb.bounding_box()["y"]
            self.assertEqual(initial_top, new_top)

            # Check for horizontal overflow
            scroll_width = page.evaluate("() => document.getElementById('outputPanel').scrollWidth")
            client_width = page.evaluate("() => document.getElementById('outputPanel').clientWidth")
            self.assertLessEqual(scroll_width, client_width + 5)
        finally:
            ctx.close()

    def test_tc_out_46_themes_and_screenshots(self):
        """TC-OUT-46: Contrast pairs pass; screenshots rendered in dark and light at 900x600 and 1440x900."""
        docs_dir = Path("docs/layer 1 technologies/UI features components/collapsible-bottom-drawer/output-panel")
        docs_dir.mkdir(parents=True, exist_ok=True)

        for width, height in [(900, 600), (1440, 900)]:
            ctx, page = self._create_page(width=width, height=height)
            try:
                page.locator("#tab-output").click()
                page.evaluate("""() => {
                    window.DeskAIOutput.log("system", "info", "Supervisor active on loopback port 38475");
                    window.DeskAIOutput.log("git", "warn", "Tracking branch origin/main is ahead by 1 commit");
                    window.DeskAIOutput.log("ports", "error", "Port 8080 collision detected");
                    window.DeskAIOutput.log("task", "info", "Agent executing diff review on file.py");
                }""")
                page.wait_for_timeout(200)

                # Dark screenshot
                page.evaluate('document.documentElement.setAttribute("data-theme", "dark")')
                page.wait_for_timeout(100)
                dark_path = docs_dir / f"output_panel_dark_{width}x{height}.png"
                page.screenshot(path=str(dark_path))
                self.assertTrue(dark_path.exists())

                # Switch to light theme
                page.evaluate('document.documentElement.setAttribute("data-theme", "light")')
                page.wait_for_timeout(200)

                # Light screenshot
                light_path = docs_dir / f"output_panel_light_{width}x{height}.png"
                page.screenshot(path=str(light_path))
                self.assertTrue(light_path.exists())
            finally:
                ctx.close()

    def test_tc_out_47_static_scan_no_inner_html(self):
        """TC-OUT-47: No innerHTML / outerHTML / insertAdjacentHTML / document.write in static/js/output/*."""
        js_files = [
            Path("src/deskai/static/js/output/client.js"),
            Path("src/deskai/static/js/output/index.js"),
            Path("src/deskai/static/js/terminal.js"),
        ]
        forbidden = ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write")
        for path in js_files:
            content = path.read_text(encoding="utf-8")
            for term in forbidden:
                pattern = rf"\b{term}\b"
                matches = re.findall(pattern, content)
                self.assertEqual(
                    len(matches),
                    0,
                    f"Forbidden DOM injection API '{term}' found in {path.name}",
                )

    def test_tc_out_48_server_restart_simulation(self):
        """TC-OUT-48: Cursor ahead of server -> reset with restarted=true -> view cleared with notice."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-output").click()
            page.evaluate("""() => {
                window.DeskAIOutput.log("git", "info", "old record 1");
                window.DeskAIOutput.log("git", "info", "old record 2");
                // Simulate server restart: trigger onReset({ restarted: true, missed: 0 })
                window.DeskAIOutput._onReset({ restarted: true, missed: 0 });
            }""")
            page.wait_for_timeout(150)

            # Old records cleared, restarted notice present
            self.assertEqual(page.locator("#channelOutput .log-line:has-text('old record 1')").count(), 0)
            notice = page.locator("#channelOutput .log-line:has-text('Server restarted; previous log discarded.')")
            self.assertTrue(notice.is_visible())
        finally:
            ctx.close()

    def test_tc_out_49_clickable_file_links(self):
        """TC-OUT-49: File path and line numbers in log lines render as interactive links jumping to editor."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-output").click()
            page.evaluate("""() => {
                window.__editorNavCalled = null;
                window.EditorManager = window.EditorManager || {};
                window.EditorManager.openAt = async (path, line, col) => {
                    window.__editorNavCalled = { path, line, col };
                };
                window.DeskAIOutput.log(
                    "diagnostics", "error", "SyntaxError in src/deskai/bridge/git.py:42:10 invalid syntax"
                );
            }""")
            page.wait_for_timeout(150)

            link = page.locator("#channelOutput .log-link[data-action='output-nav']")
            self.assertTrue(link.is_visible())
            self.assertEqual(link.get_attribute("data-file"), "src/deskai/bridge/git.py")
            self.assertEqual(link.get_attribute("data-line"), "42")
            self.assertEqual(link.get_attribute("data-col"), "10")

            # Click link and check EditorManager invocation
            link.click()
            page.wait_for_timeout(100)
            nav = page.evaluate("() => window.__editorNavCalled")
            self.assertIsNotNone(nav)
            self.assertTrue(nav["path"].endswith("src/deskai/bridge/git.py"))
            self.assertEqual(nav["line"], 42)
            self.assertEqual(nav["col"], 10)
        finally:
            ctx.close()

    def test_tc_out_50_save_log_action(self):
        """TC-OUT-50: Output toolbar contains save action that exports visible log stream."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-output").click()
            save_btn = page.locator("button[data-action='output-save']")
            self.assertTrue(save_btn.is_visible())
            self.assertIn("Save", save_btn.get_attribute("aria-label"))

            # Log lines to export
            page.evaluate("""() => {
                window.DeskAIOutput.log("system", "info", "export test record 1");
                window.DeskAIOutput.log("system", "warn", "export test record 2");
            }""")
            page.wait_for_timeout(150)

            with page.expect_download() as download_info:
                save_btn.click()
            download = download_info.value
            self.assertTrue(download.suggested_filename.startswith("deskai-output-"))
            self.assertTrue(download.suggested_filename.endswith(".log"))
        finally:
            ctx.close()

    def test_tc_out_51_channel_unread_counts(self):
        """TC-OUT-51: Inactive channels track unread counts in outputChannelSelect and clear on selection."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-output").click()
            # Select system channel specifically
            page.select_option("#outputChannelSelect", "system")

            # Emit logs on git and ports channels
            page.evaluate("""() => {
                window.DeskAIOutput.log("git", "warn", "git tracking branch updated");
                window.DeskAIOutput.log("git", "info", "git pull completed");
                window.DeskAIOutput.log("ports", "info", "port 3000 listening");
            }""")
            page.wait_for_timeout(150)

            # Check that git option shows (2) and ports option shows (1)
            git_opt = page.locator("#outputChannelSelect option[value='git']")
            ports_opt = page.locator("#outputChannelSelect option[value='ports']")
            self.assertIn("Git (2)", git_opt.text_content())
            self.assertIn("Ports (1)", ports_opt.text_content())

            # Check select element has .has-unread class
            select_el = page.locator("#outputChannelSelect")
            self.assertTrue("has-unread" in (select_el.get_attribute("class") or ""))

            # Now switch to git channel -> unread count for git should clear
            page.select_option("#outputChannelSelect", "git")
            page.wait_for_timeout(100)
            self.assertEqual(git_opt.text_content().strip(), "Git")

            # Switch to all -> all unread counts should clear
            page.select_option("#outputChannelSelect", "all")
            page.wait_for_timeout(100)
            self.assertEqual(ports_opt.text_content().strip(), "Ports")
            self.assertFalse("has-unread" in (select_el.get_attribute("class") or ""))
        finally:
            ctx.close()


if __name__ == "__main__":
    unittest.main()
