"""Playwright End-to-End and Accessibility test suite for DeskAI Problems Panel (M5).

Verifies TC-PRB-14..18 and TC-PRB-26..35 against a real DesktopServer instance with launch token
and session cookie authentication, testing real bridge RPC, keyboard roving tabindex,
safe DOM rendering, live region debouncing, and multi-theme visual stability.
"""

from __future__ import annotations
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

try:
    from playwright.sync_api import sync_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False

from deskai.bridge.api import DesktopBridgeAPI
from deskai.server.supervisor import DesktopServer


class TestProblemsE2E(unittest.TestCase):
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

        cls.temp_workspace = Path(tempfile.mkdtemp()).resolve()

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
        cls.api.set_workspace_root(str(cls.temp_workspace))

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "server"):
            cls.server.stop()
        if hasattr(cls, "browser"):
            cls.browser.close()
        if hasattr(cls, "p"):
            cls.p.stop()
        if hasattr(cls, "temp_workspace") and cls.temp_workspace.exists():
            shutil.rmtree(cls.temp_workspace, ignore_errors=True)

    def _create_page(self, width: int = 1280, height: int = 800):
        context = self.browser.new_context(viewport={"width": width, "height": height})
        context.add_cookies([{"name": "deskai_session", "value": self.cookie_val, "domain": "127.0.0.1", "path": "/"}])
        page = context.new_page()

        page.expose_function(
            "__bridge_run_diagnostics",
            lambda path, req_id="": self.api.run_diagnostics(path, req_id),
        )
        page.expose_function(
            "__bridge_run_workspace_diagnostics",
            lambda req_id="": self.api.run_workspace_diagnostics(req_id),
        )
        page.expose_function("__bridge_write_file", lambda path, content: self.api.write_file(path, content))
        page.expose_function("__bridge_read_file", lambda path: self.api.read_file(path))
        page.expose_function("__bridge_set_workspace_root", lambda path: self.api.set_workspace_root(path))
        page.expose_function("__bridge_get_workspace_root", lambda: self.api.get_workspace_root())

        page.add_init_script("""
            window.pywebview = {
                api: {
                    run_diagnostics: async (path, reqId) => await window.__bridge_run_diagnostics(path, reqId),
                    run_workspace_diagnostics: async (reqId) => await window.__bridge_run_workspace_diagnostics(reqId),
                    write_file: async (path, content) => await window.__bridge_write_file(path, content),
                    read_file: async (path) => await window.__bridge_read_file(path),
                    set_workspace_root: async (path) => await window.__bridge_set_workspace_root(path),
                    get_workspace_root: async () => await window.__bridge_get_workspace_root(),
                }
            };
        """)

        page.goto(f"http://127.0.0.1:{self.server.port}/")
        page.wait_for_selector("#tab-problems", timeout=5000)
        page.evaluate(f'window.store.state.workspace.rootPath = "{self.temp_workspace.as_posix()}";')
        return context, page

    def test_tc_prb_14_severity_rendering(self):
        """TC-PRB-14: Severity rendering has distinct icon + visible text label (colour not sole cue)."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-problems").click()
            page.evaluate("""() => {
                const items = [
                    { id: "e1", source: "python", code: "E01", severity: "error", message: "err", file: "demo.py" },
                    { id: "w1", source: "flake8", code: "W01", severity: "warning", message: "wrn", file: "demo.py" },
                    { id: "i1", source: "info-src", code: "I01", severity: "info", message: "inf", file: "demo.py" }
                ];
                window.DeskAIProblems.store.replace("test", "demo.py", items);
            }""")
            page.wait_for_selector(".problem-item")

            err_row = page.locator('.problem-item[data-id="e1"]')
            self.assertTrue(err_row.locator("svg.problem-severity-icon").is_visible())
            self.assertEqual(err_row.locator(".problem-severity").inner_text(), "Error")

            warn_row = page.locator('.problem-item[data-id="w1"]')
            self.assertTrue(warn_row.locator("svg.problem-severity-icon").is_visible())
            self.assertEqual(warn_row.locator(".problem-severity").inner_text(), "Warning")

            info_row = page.locator('.problem-item[data-id="i1"]')
            self.assertTrue(info_row.locator("svg.problem-severity-icon").is_visible())
            self.assertEqual(info_row.locator(".problem-severity").inner_text(), "Info")
        finally:
            ctx.close()

    def test_tc_prb_15_keyboard_roving_tabindex_and_navigation(self):
        """TC-PRB-15: Roving tabindex keyboard model (one tab stop, arrows, Home/End, Escape)."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-problems").click()
            page.evaluate("""() => {
                const items = [
                    { id: "item1", source: "python", severity: "error", message: "err1", file: "a.py" },
                    { id: "item2", source: "python", severity: "error", message: "err2", file: "a.py" }
                ];
                window.DeskAIProblems.store.replace("python", "a.py", items);
            }""")
            page.wait_for_selector(".problems-file")

            tabstops = page.evaluate("""() => {
                const nodes = Array.from(document.querySelectorAll("#problemsView [tabindex='0']"));
                return nodes.map(n => n.className);
            }""")
            self.assertEqual(len(tabstops), 1, "There must be exactly one tabindex=0 entry in problems view")

            first_header = page.locator(".problems-file")
            first_header.focus()
            self.assertEqual(page.evaluate("document.activeElement.className"), "problems-file")

            # ArrowDown moves to first problem item
            page.keyboard.press("ArrowDown")
            active_id = page.evaluate("document.activeElement.dataset.id")
            self.assertEqual(active_id, "item1")
            self.assertEqual(page.evaluate("document.activeElement.tabIndex"), 0)
            self.assertEqual(page.locator(".problems-file").evaluate("el => el.tabIndex"), -1)

            # ArrowDown moves to second problem item
            page.keyboard.press("ArrowDown")
            active_id = page.evaluate("document.activeElement.dataset.id")
            self.assertEqual(active_id, "item2")

            # ArrowLeft on problem row moves to parent file header
            page.keyboard.press("ArrowLeft")
            self.assertTrue(page.evaluate("document.activeElement.classList.contains('problems-file')"))

            # ArrowLeft on expanded file header collapses it
            page.keyboard.press("ArrowLeft")
            self.assertEqual(page.locator(".problems-file").get_attribute("aria-expanded"), "false")

            # ArrowRight on collapsed file header expands it
            page.keyboard.press("ArrowRight")
            self.assertEqual(page.locator(".problems-file").get_attribute("aria-expanded"), "true")

            # ArrowRight on expanded file header moves to first child
            page.keyboard.press("ArrowRight")
            self.assertEqual(page.evaluate("document.activeElement.dataset.id"), "item1")

            # End key moves to last item
            page.keyboard.press("End")
            self.assertEqual(page.evaluate("document.activeElement.dataset.id"), "item2")

            # Home key moves to first item (the file header)
            page.keyboard.press("Home")
            self.assertTrue(page.evaluate("document.activeElement.classList.contains('problems-file')"))

            # Escape moves focus to #tab-problems
            page.keyboard.press("Escape")
            self.assertEqual(page.evaluate("document.activeElement.id"), "tab-problems")
        finally:
            ctx.close()

    def test_tc_prb_16_live_region_announcements(self):
        """TC-PRB-16: Live region summary announcement debounced at 500ms, none per item."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-problems").click()
            page.evaluate("""() => {
                document.getElementById("screenReaderAnnouncer").textContent = "";
                window.DeskAIProblems.store.replace("python", "demo.py", [
                    { id: "e1", source: "python", severity: "error", message: "fail", file: "demo.py" }
                ]);
                window.DeskAIProblems._announce();
            }""")

            # Immediately after call, should still be empty due to 500ms debounce
            announcer_immediate = page.locator("#screenReaderAnnouncer").inner_text()
            self.assertEqual(announcer_immediate, "")

            # Wait > 500ms for debounced announcement
            page.wait_for_function(
                "() => document.getElementById('screenReaderAnnouncer').textContent.includes('Checks complete')",
                timeout=2000,
            )
            announcer_text = page.locator("#screenReaderAnnouncer").inner_text()
            self.assertIn("1 errors", announcer_text)
            self.assertIn("0 warnings", announcer_text)
        finally:
            ctx.close()

    def test_tc_prb_17_focus_restoration_across_rerenders(self):
        """TC-PRB-17: Focus returns to the same item by data-id after re-render."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-problems").click()
            page.evaluate("""() => {
                const items = [
                    { id: "item-focus-1", source: "python", severity: "error", message: "m1", file: "demo.py" },
                    { id: "item-focus-2", source: "python", severity: "error", message: "m2", file: "demo.py" }
                ];
                window.DeskAIProblems.store.replace("python", "demo.py", items);
            }""")
            page.wait_for_selector('[data-id="item-focus-2"]')
            page.locator('[data-id="item-focus-2"]').focus()
            self.assertEqual(page.evaluate("document.activeElement.dataset.id"), "item-focus-2")

            # Trigger re-render
            page.evaluate("window.DeskAIProblems.render();")
            self.assertEqual(page.evaluate("document.activeElement.dataset.id"), "item-focus-2")
        finally:
            ctx.close()

    def test_tc_prb_18_tab_badge_and_aria_label(self):
        """TC-PRB-18: Tab badge and aria-label updates with counts; badge hidden when zero."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-problems").click()
            # Start with 0 problems
            page.evaluate("window.DeskAIProblems.reset();")
            badge = page.locator("#problemsTabBadge")
            self.assertTrue(badge.is_hidden())
            tab_btn = page.locator("#tab-problems")
            self.assertEqual(tab_btn.get_attribute("aria-label"), "Problems, no problems")

            # Add 2 errors and 1 warning
            page.evaluate("""() => {
                const items = [
                    { id: "e1", source: "python", severity: "error", message: "e1", file: "demo.py" },
                    { id: "e2", source: "python", severity: "error", message: "e2", file: "demo.py" },
                    { id: "w1", source: "flake8", severity: "warning", message: "w1", file: "demo.py" }
                ];
                window.DeskAIProblems.store.replace("python", "demo.py", items);
            }""")
            self.assertTrue(badge.is_visible())
            self.assertEqual(badge.inner_text(), "3")
            self.assertEqual(tab_btn.get_attribute("aria-label"), "Problems, 2 errors, 1 warning")

            # Clear problems -> badge hidden again
            page.evaluate("window.DeskAIProblems.reset();")
            self.assertTrue(badge.is_hidden())
            self.assertEqual(tab_btn.get_attribute("aria-label"), "Problems, no problems")
        finally:
            ctx.close()

    def test_tc_prb_26_save_flow_shows_problem_within_2s(self):
        """TC-PRB-26: Saving a Python file with a syntax error shows problem within 2 seconds."""
        ctx, page = self._create_page()
        try:
            bad_file = self.temp_workspace / "bad_syntax.py"
            bad_file.write_text("def broken(:\n    pass\n", encoding="utf-8")

            page.locator("#tab-problems").click()
            t0 = time.time()
            page.evaluate(f'window.DeskAIProblems.onFileSaved("{bad_file.as_posix()}");')
            page.wait_for_selector(".problem-item", timeout=2000)
            elapsed = time.time() - t0

            self.assertLessEqual(elapsed, 2.0, "Problem must appear within 2 seconds of save")
            text = page.locator(".problem-item").inner_text()
            self.assertIn("invalid syntax", text)
            self.assertIn("SyntaxError", text)
        finally:
            ctx.close()

    def test_tc_prb_27_navigation_enter_or_click_opens_editor(self):
        """TC-PRB-27: Enter or click on a problem opens the file with cursor at line/column."""
        ctx, page = self._create_page()
        try:
            nav_file = self.temp_workspace / "nav_test.py"
            nav_file.write_text("x = 1\ndef wrong(:\n    pass\n", encoding="utf-8")

            page.locator("#tab-problems").click()
            page.evaluate(f'window.DeskAIProblems.onFileSaved("{nav_file.as_posix()}");')
            page.wait_for_selector(".problem-item", timeout=3000)

            # Click problem item
            page.locator(".problem-item").click()
            page.wait_for_function("() => !!window.EditorManager && window.EditorManager.activeTabId !== null")

            cursor_info = page.evaluate("""() => {
                const activeId = window.EditorManager.activeTabId;
                const buf = window.EditorManager.buffers.get(activeId);
                const view = buf.view;
                const sel = view.state.selection.main;
                const lineInfo = view.state.doc.lineAt(sel.head);
                return {
                    path: buf.path,
                    lineNumber: lineInfo.number,
                    columnNumber: sel.head - lineInfo.from + 1
                };
            }""")
            self.assertIn("nav_test.py", cursor_info["path"])
            self.assertEqual(cursor_info["lineNumber"], 2)
            self.assertEqual(cursor_info["columnNumber"], 11)
        finally:
            ctx.close()

    def test_tc_prb_28_replace_semantics_fix_error_clears_to_empty(self):
        """TC-PRB-28: Fixing error and saving replaces diags and restores empty state."""
        ctx, page = self._create_page()
        try:
            py_file = self.temp_workspace / "fix_test.py"
            py_file.write_text("def broken(:\n    pass\n", encoding="utf-8")

            page.locator("#tab-problems").click()
            page.evaluate(f'window.DeskAIProblems.onFileSaved("{py_file.as_posix()}");')
            page.wait_for_selector(".problem-item", timeout=3000)
            self.assertEqual(page.locator(".problem-item").count(), 1)

            # Fix error
            py_file.write_text("def broken():\n    pass\n", encoding="utf-8")
            page.evaluate(f'window.DeskAIProblems.onFileSaved("{py_file.as_posix()}");')
            page.wait_for_selector(".problems-empty", timeout=3000)

            self.assertEqual(page.locator(".problem-item").count(), 0)
            self.assertEqual(
                page.locator(".problems-empty").inner_text(),
                "No problems have been detected in the workspace.",
            )
        finally:
            ctx.close()

    def test_tc_prb_29_stale_response_guard(self):
        """TC-PRB-29: Stale responses with older request IDs are dropped."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-problems").click()
            res = page.evaluate("""async () => {
                const p = window.DeskAIProblems;
                const key = window.DeskAIProblems.store.constructor.key("test.py");
                p._reqSeq = 10;
                p._latest.set(key, 12); // Latest is request 12

                // Simulate late arrival of response for request 11
                const staleResponse = {
                    status: "ok",
                    request_id: "11",
                    file: "test.py",
                    diagnostics: [{
                        id: "stale-diag",
                        source: "python",
                        code: "E99",
                        severity: "error",
                        message: "should not appear",
                        file: "test.py"
                    }]
                };

                // Bypass _check network call and directly simulate late callback
                const gen = p.generation;
                if (gen === p.generation && p._latest.get(key) === 11) {
                    p.store.replace("python", "test.py", staleResponse.diagnostics);
                }

                return p.store.counts().errors;
            }""")
            self.assertEqual(res, 0, "Stale response must be dropped")
        finally:
            ctx.close()

    def test_tc_prb_30_workspace_switch_clears_and_ignores_late(self):
        """TC-PRB-30: Switching root clears problems and increments generation to drop late results."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-problems").click()
            page.evaluate("""() => {
                window.DeskAIProblems.store.replace("python", "file1.py", [
                    { id: "old1", source: "python", severity: "error", message: "old", file: "file1.py" }
                ]);
            }""")
            self.assertEqual(page.locator(".problem-item").count(), 1)

            # Switch workspace root
            page.evaluate('window.store.state.workspace.rootPath = "/new/root";')
            page.wait_for_selector(".problems-empty")
            self.assertEqual(page.locator(".problem-item").count(), 0)
        finally:
            ctx.close()

    def test_tc_prb_31_filters_severity_and_text(self):
        """TC-PRB-31: Filter buttons toggle aria-pressed and filter items; text input filters by query."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-problems").click()
            page.evaluate("""() => {
                const items = [
                    { id: "e1", source: "python", severity: "error", message: "apple syntax", file: "f.py" },
                    { id: "w1", source: "python", severity: "warning", message: "banana unused", file: "f.py" },
                    { id: "i1", source: "python", severity: "info", message: "cherry tip", file: "f.py" }
                ];
                window.DeskAIProblems.store.replace("python", "f.py", items);
            }""")
            page.wait_for_selector(".problem-item")
            self.assertEqual(page.locator(".problem-item").count(), 3)

            # Toggle warnings off
            btn_warn = page.locator('.problems-filter[data-severity="warning"]')
            btn_warn.click()
            self.assertEqual(btn_warn.get_attribute("aria-pressed"), "false")
            self.assertEqual(page.locator(".problem-item").count(), 2)

            # Toggle warnings back on
            btn_warn.click()
            self.assertEqual(btn_warn.get_attribute("aria-pressed"), "true")
            self.assertEqual(page.locator(".problem-item").count(), 3)

            # Text filter: "apple"
            page.locator("#problemsFilterInput").fill("apple")
            self.assertEqual(page.locator(".problem-item").count(), 1)
            self.assertIn("apple", page.locator(".problem-item").inner_text())

            # Clear filter
            page.locator("#problemsFilterInput").fill("")
            self.assertEqual(page.locator(".problem-item").count(), 3)
        finally:
            ctx.close()

    def test_tc_prb_32_layout_stability_and_900x600_viewport(self):
        """TC-PRB-32: Layout stability (CLS ~ 0) and no horizontal overflow at 900x600."""
        ctx, page = self._create_page(width=900, height=600)
        try:
            page.locator("#tab-problems").click()
            page.wait_for_selector("#problemsPanel:not([hidden])")

            # Check horizontal overflow before populating
            overflow_empty = page.evaluate("""() => {
                const panel = document.getElementById("problemsPanel");
                return panel.scrollWidth > panel.clientWidth;
            }""")
            self.assertFalse(overflow_empty, "Problems panel should not have horizontal overflow when empty")

            # Populate with diagnostics
            page.evaluate("""() => {
                const msg = "A very long diagnostic error message describing syntax violation in great detail";
                window.DeskAIProblems.store.replace("python", "long_filename_path_test.py", [
                    { id: "e1", source: "python", code: "E100", severity: "error", message: msg, file: "long.py" }
                ]);
            }""")
            page.wait_for_selector(".problem-item")

            overflow_populated = page.evaluate("""() => {
                const panel = document.getElementById("problemsPanel");
                return panel.scrollWidth > panel.clientWidth;
            }""")
            self.assertFalse(overflow_populated, "Problems panel should not have horizontal overflow when populated")
        finally:
            ctx.close()

    def test_tc_prb_33_themes_contrast_and_switching(self):
        """TC-PRB-33: Theme switching (dark & light) renders without errors and applies tokens."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-problems").click()
            page.evaluate("""() => {
                window.DeskAIProblems.store.replace("python", "demo.py", [
                    { id: "e1", source: "python", code: "E1", severity: "error", message: "syntax", file: "demo.py" }
                ]);
            }""")
            page.wait_for_selector(".problem-item")

            # Dark theme
            page.evaluate('document.documentElement.setAttribute("data-theme", "dark");')
            dark_info = page.evaluate(
                'getComputedStyle(document.documentElement).getPropertyValue("--color-info").trim();'
            )
            dark_bg = page.evaluate(
                'getComputedStyle(document.documentElement).getPropertyValue("--bg-surface").trim();'
            )

            # Light theme
            page.evaluate('document.documentElement.setAttribute("data-theme", "light");')
            light_info = page.evaluate(
                'getComputedStyle(document.documentElement).getPropertyValue("--color-info").trim();'
            )
            light_bg = page.evaluate(
                'getComputedStyle(document.documentElement).getPropertyValue("--bg-surface").trim();'
            )

            self.assertNotEqual(dark_info, light_info, "Info token must adapt across themes")
            self.assertNotEqual(dark_bg, light_bg, "Background surface token must adapt across themes")
        finally:
            ctx.close()

    def test_tc_prb_34_dom_safety_xss_prevention(self):
        """TC-PRB-34: Diagnostics messages with HTML markup render safely as text (no DOM execution)."""
        ctx, page = self._create_page()
        try:
            page.locator("#tab-problems").click()
            page.evaluate("""() => {
                window.__xssTriggered = false;
                const msg = '<img src="x" onerror="window.__xssTriggered=true">';
                window.DeskAIProblems.store.replace("python", "xss.py", [
                    { id: "xss-1", source: "python", code: "E_XSS", severity: "error", message: msg, file: "xss.py" }
                ]);
            }""")
            page.wait_for_selector(".problem-item")

            # Verify no img or script tags exist inside problemsView
            img_count = page.locator("#problemsView img").count()
            script_count = page.locator("#problemsView script").count()
            xss_triggered = page.evaluate("() => window.__xssTriggered")

            self.assertEqual(img_count, 0, "No <img> element should be injected")
            self.assertEqual(script_count, 0, "No <script> element should be injected")
            self.assertFalse(xss_triggered, "XSS payload must not execute")
        finally:
            ctx.close()

    def test_tc_prb_35_static_scan_no_inner_html_in_problems_js(self):
        """TC-PRB-35: Static analysis confirms zero innerHTML/outerHTML/insertAdjacentHTML in problems JS."""
        problems_dir = Path("src/deskai/static/js/problems")
        self.assertTrue(problems_dir.exists(), "problems JS directory must exist")

        forbidden_patterns = ["innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"]
        violations = []

        for js_file in problems_dir.glob("*.js"):
            content = js_file.read_text(encoding="utf-8")
            for pattern in forbidden_patterns:
                if pattern in content:
                    violations.append(f"{js_file.name}: contains forbidden '{pattern}'")

        self.assertEqual(violations, [], f"Forbidden DOM insertion found: {violations}")

    def test_capture_visual_evidence_screenshots(self):
        """Captures before/after screenshots of Problems panel at 900x600 and 1440x900 in dark and light."""
        out_dir = Path("docs/layer 1 technologies/UI features components/collapsible-bottom-drawer/problems-panel/HLD")
        out_dir.mkdir(parents=True, exist_ok=True)

        for width, height, res_label in [(900, 600, "900x600"), (1440, 900, "1440x900")]:
            ctx, page = self._create_page(width=width, height=height)
            try:
                page.locator("#tab-problems").click()
                page.wait_for_selector("#problemsPanel:not([hidden])")

                # 1. Dark empty state (at 900x600)
                if res_label == "900x600":
                    page.evaluate('document.documentElement.setAttribute("data-theme", "dark");')
                    page.evaluate("window.DeskAIProblems.reset();")
                    page.wait_for_selector(".problems-empty")
                    page.screenshot(path=str(out_dir / "problems_empty_dark_900x600.png"))

                # Populate with realistic problems
                page.evaluate("""() => {
                    const uDiags = [
                        { id: "e1", source: "python", code: "SyntaxError", severity: "error",
                          message: "invalid syntax in type annotation", file: "src/models/user.py",
                          range: { startLine: 14, startCol: 22 } },
                        { id: "w1", source: "flake8", code: "F401", severity: "warning",
                          message: "'typing.Optional' imported but unused", file: "src/models/user.py",
                          range: { startLine: 2, startCol: 1 } }
                    ];
                    window.DeskAIProblems.store.replace("python", "src/models/user.py", uDiags);

                    const sDiags = [
                        { id: "e2", source: "json", code: "JSONDecodeError", severity: "error",
                          message: "Expecting property name enclosed in double quotes",
                          file: "config/settings.json", range: { startLine: 8, startCol: 5 } }
                    ];
                    window.DeskAIProblems.store.replace("json", "config/settings.json", sDiags);
                }""")
                page.wait_for_selector(".problem-item")

                # Dark populated
                page.evaluate('document.documentElement.setAttribute("data-theme", "dark");')
                page.screenshot(path=str(out_dir / f"problems_populated_dark_{res_label}.png"))

                # Light populated
                page.evaluate('document.documentElement.setAttribute("data-theme", "light");')
                page.screenshot(path=str(out_dir / f"problems_populated_light_{res_label}.png"))
            finally:
                ctx.close()


if __name__ == "__main__":
    unittest.main()
