"""
Test for Task 5: Truthful Telemetry & Terminal Controls.
Asserts:
1. Neutral unknown tokens exist in tokens.css (--color-unknown).
2. Telemetry initial/unknown state displays "Unavailable" with tooltip, no green "Ready", and greyed out progress bar.
3. Telemetry reactive updates truthfully show real detected metrics and format without emojis.
4. Terminal kill button is disabled with aria-disabled="true" and descriptive title when idle/dead.
5. Terminal kill button enables when session is alive, and disables again when killed/exited.
6. Buttons have tokenized hover, active, disabled, and loading states.
"""

import unittest
from playwright.sync_api import sync_playwright
import httpx
from deskai.server.supervisor import DesktopServer


class TestTask5TelemetryAndTerminalControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = sync_playwright().start()
        try:
            cls.browser = cls.p.chromium.launch(headless=True)
        except Exception as e:
            cls.p.stop()
            raise unittest.SkipTest(f"Chromium launch failed: {e}")

        cls.srv = DesktopServer()
        cls.srv.start()
        token = cls.srv.security.create_launch_token()

        with httpx.Client(follow_redirects=False) as http:
            res = http.get(
                f"http://127.0.0.1:{cls.srv.port}/auth/redeem?token={token}",
                headers={"Host": f"127.0.0.1:{cls.srv.port}"},
            )
            cls.cookie_val = res.cookies.get("deskai_session")

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "srv"):
            cls.srv.stop()
        if hasattr(cls, "browser"):
            cls.browser.close()
        if hasattr(cls, "p"):
            cls.p.stop()

    def _create_page(self):
        context = self.browser.new_context(viewport={"width": 1280, "height": 800})
        context.add_cookies([{"name": "deskai_session", "value": self.cookie_val, "domain": "127.0.0.1", "path": "/"}])
        page = context.new_page()
        page.goto(f"http://127.0.0.1:{self.srv.port}/")
        page.wait_for_selector("#appRoot")
        return context, page

    def test_tokens_contain_neutral_unknown(self):
        with open("src/deskai/static/css/tokens.css", "r", encoding="utf-8") as f:
            tokens_content = f.read()
        self.assertIn("--color-unknown:", tokens_content)
        self.assertIn("--color-unknown-subtle:", tokens_content)

    def test_telemetry_initial_state_shows_unavailable_and_no_ready(self):
        context, page = self._create_page()
        try:
            gpu_badge = page.locator("#teleGpuBadge")
            vram_text = page.locator("#teleVramText")
            ram_text = page.locator("#teleRamText")
            vram_fill = page.locator("#teleVramFill")

            # GPU badge must NOT say "Ready" when no GPU is detected
            gpu_text = gpu_badge.text_content().strip()
            self.assertNotIn("Ready", gpu_text)
            self.assertIn("Unavailable", gpu_text)

            # GPU badge must have a tooltip explaining unavailable
            gpu_title = gpu_badge.get_attribute("title") or ""
            self.assertIn("unavailable", gpu_title.lower())

            # VRAM & RAM must say "Unavailable", not "-- / -- GB"
            self.assertEqual(vram_text.text_content().strip(), "Unavailable")
            self.assertEqual(ram_text.text_content().strip(), "Unavailable")

            # Progress bar must be greyed out or at 0 width
            fill_style = vram_fill.get_attribute("style") or ""
            fill_width = page.evaluate("el => el.getBoundingClientRect().width", vram_fill.element_handle())
            self.assertTrue(fill_width == 0 or "width: 0" in fill_style)
        finally:
            context.close()

    def test_telemetry_updates_with_truthful_values_and_no_emojis(self):
        context, page = self._create_page()
        try:
            # Emit truthful telemetry through the store
            page.evaluate("""() => {
                window.store.state.telemetry = {
                    gpuName: "NVIDIA RTX 4090",
                    vramUsedMB: 4096,
                    vramTotalMB: 24576,
                    ramUsedMB: 16384
                };
            }""")
            page.wait_for_timeout(100)

            gpu_text = page.locator("#teleGpuBadge").text_content().strip()
            vram_text = page.locator("#teleVramText").text_content().strip()
            ram_text = page.locator("#teleRamText").text_content().strip()

            self.assertIn("NVIDIA RTX 4090", gpu_text)
            # Ensure no emojis (such as 🟢) were injected
            self.assertNotIn("🟢", gpu_text)
            self.assertEqual(vram_text, "4.0 / 24 GB")
            self.assertEqual(ram_text, "16.0 GB")

            # Reset to unknown
            page.evaluate("""() => {
                window.store.state.telemetry = {
                    gpuName: null,
                    vramUsedMB: null,
                    vramTotalMB: null,
                    ramUsedMB: null
                };
            }""")
            page.wait_for_timeout(100)

            gpu_text_reset = page.locator("#teleGpuBadge").text_content().strip()
            self.assertIn("Unavailable", gpu_text_reset)
        finally:
            context.close()

    def test_terminal_kill_button_disabled_state_lifecycle(self):
        context, page = self._create_page()
        try:
            kill_btn = page.locator("#terminalKillBtn")

            # 1. Initially disabled when no session is running
            self.assertTrue(kill_btn.is_disabled())
            self.assertEqual(kill_btn.get_attribute("aria-disabled"), "true")
            title = kill_btn.get_attribute("title") or ""
            self.assertIn("No active", title)

            # 2. When terminal session becomes alive, button enables
            page.evaluate("""() => {
                window.DeskAITerminal.sessionId = "test-session-123";
                window.DeskAITerminal.hasExited = false;
                window.DeskAITerminal._updateKillButtonState();
            }""")
            self.assertFalse(kill_btn.is_disabled())
            self.assertEqual(kill_btn.get_attribute("aria-disabled"), "false")

            # 3. When session ends, button disables again
            page.evaluate("""() => {
                window.DeskAITerminal.sessionId = null;
                window.DeskAITerminal.hasExited = true;
                window.DeskAITerminal._updateKillButtonState();
            }""")
            self.assertTrue(kill_btn.is_disabled())
            self.assertEqual(kill_btn.get_attribute("aria-disabled"), "true")
        finally:
            context.close()

    def test_buttons_have_hover_active_disabled_and_loading_styles(self):
        context, page = self._create_page()
        try:
            # Check button styles for .welcome-btn.primary, .welcome-btn.secondary, .terminal-kill-btn, .icon-btn
            styles = page.evaluate("""() => {
                const sheet = Array.from(document.styleSheets).find(s => s.href && s.href.includes("components.css"));
                const rules = sheet ? Array.from(sheet.cssRules).map(r => r.selectorText || "") : [];
                const hasKill = rules.some(
                    r => r.includes(".terminal-kill-btn:disabled") || r.includes(".terminal-kill-btn[aria-disabled")
                );
                const hasIconActive = rules.some(r => r.includes(".icon-btn:active"));
                const hasWelcomeActive = rules.some(r => r.includes(".welcome-btn:active"));
                const hasBtnDisabled = rules.some(
                    r => r.includes("button:disabled") || r.includes(".btn:disabled")
                        || r.includes(".icon-btn:disabled")
                );
                const hasBtnLoading = rules.some(r => r.includes(".is-loading") || r.includes("[aria-busy='true']"));
                return {
                    killBtnDisabled: hasKill,
                    iconBtnActive: hasIconActive,
                    welcomeBtnActive: hasWelcomeActive,
                    buttonDisabledRule: hasBtnDisabled,
                    buttonLoadingRule: hasBtnLoading
                };
            }""")
            self.assertTrue(styles["killBtnDisabled"])
            self.assertTrue(styles["iconBtnActive"])
            self.assertTrue(styles["welcomeBtnActive"])
            self.assertTrue(styles["buttonDisabledRule"])
            self.assertTrue(styles["buttonLoadingRule"])
        finally:
            context.close()
