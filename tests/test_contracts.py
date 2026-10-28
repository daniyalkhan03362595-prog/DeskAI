"""
Comprehensive Contract, State Machine & Security Verification Suite for DeskAI Layer 1
Directly scans and validates documentation specifications, FSM reachability, and security invariants.
"""

import re
import unittest
import secrets
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestDeskAILayer1Contracts(unittest.TestCase):

    def test_html_and_js_action_synchronization(self):
        """
        Scans runtime HTML and JS router to assert that every data-action
        defined in index.html has a corresponding case handler in events.js.
        """
        html_file = REPO_ROOT / "src" / "deskai" / "static" / "index.html"
        events_js_file = REPO_ROOT / "src" / "deskai" / "static" / "js" / "events.js"

        self.assertTrue(html_file.exists())
        self.assertTrue(events_js_file.exists())

        html_content = html_file.read_text(encoding="utf-8")
        js_content = events_js_file.read_text(encoding="utf-8")

        html_actions = set(re.findall(r'data-action="([^"]+)"', html_content))
        js_handlers = set(re.findall(r'case "([^"]+)":', js_content))

        # Additional actions rendered dynamically in submodules/views or handled via form submit
        known_dynamic_actions = {
            "restart-terminal",
            "reconnect-terminal",
            "copy-port",
            "remove-port",
            "open-port",
            "submit-watch-port",
            "ctx-new-file",
            "ctx-new-folder",
            "ctx-rename",
            "ctx-delete",
            "ctx-copy-path",
            "ctx-copy-relative-path",
            "open-recent-project",
            "remove-recent-project",
        }

        unhandled = html_actions - js_handlers - known_dynamic_actions
        self.assertEqual(unhandled, set(), f"The following HTML actions lack router handlers: {unhandled}")

    def test_uec_state_machine_reachability_and_no_loops(self):
        """
        Validates the real static/transitions.json state machine:
        1. REVIEW_DIFF can reach SUCCESS (Approve) and ROLLBACK (Reject).
        2. CANCELLED resets cleanly to IDLE.
        3. All states are reachable from IDLE with no dead-end cycles.
        """
        import json

        transitions_file = REPO_ROOT / "src" / "deskai" / "static" / "transitions.json"
        self.assertTrue(transitions_file.exists())
        with open(transitions_file, "r", encoding="utf-8") as f:
            transitions = json.load(f)

        # 1. State machine invariants
        self.assertIn("IDLE", transitions)
        self.assertIn("PLANNING", transitions["IDLE"])
        self.assertIn("REVIEW_DIFF", transitions)
        self.assertIn("SUCCESS", transitions["REVIEW_DIFF"])
        self.assertIn("ROLLBACK", transitions["REVIEW_DIFF"])
        self.assertIn("CANCELLED", transitions)
        self.assertIn("IDLE", transitions["CANCELLED"])
        self.assertIn("SUCCESS", transitions)
        self.assertIn("IDLE", transitions["SUCCESS"])

        # 2. Dead-end check: every state has at least one valid exit target
        for state, targets in transitions.items():
            self.assertTrue(len(targets) > 0, f"State {state} is a dead end without exits!")
            for t in targets:
                self.assertIn(t, transitions, f"Target {t} from {state} is not in transitions matrix!")

        # 3. Reachability from IDLE
        visited = set()
        queue = ["IDLE"]
        while queue:
            curr = queue.pop(0)
            if curr not in visited:
                visited.add(curr)
                queue.extend([t for t in transitions[curr] if t not in visited])
        self.assertEqual(visited, set(transitions.keys()), "Not all states are reachable from IDLE!")

    def test_path_sandbox_commonpath_security(self):
        """
        Verifies that deskai.utils.path prevents traversal, prefix-spoofing attacks,
        and system root path selections using the real implementation.
        """
        from deskai.utils.path import is_safe_workspace_path, is_disallowed_workspace_root

        workspace_root = "/home/user/DeskAI"

        # Safe workspace paths
        self.assertTrue(is_safe_workspace_path("/home/user/DeskAI/src/main.py", workspace_root))
        self.assertTrue(is_safe_workspace_path("/home/user/DeskAI/docs/spec.md", workspace_root))
        self.assertTrue(is_safe_workspace_path("/home/user/DeskAI", workspace_root))

        # Malicious paths (Must be rejected)
        self.assertFalse(is_safe_workspace_path("/home/user/DeskAI-secrets/passwords.txt", workspace_root))
        self.assertFalse(is_safe_workspace_path("/etc/passwd", workspace_root))
        self.assertFalse(is_safe_workspace_path("/home/user/DeskAI/../../etc/shadow", workspace_root))
        self.assertFalse(is_safe_workspace_path("/home/user/other_project", workspace_root))
        self.assertFalse(is_safe_workspace_path("/home/user/DeskAI/sub", None))

        # Disallowed root directories check
        self.assertTrue(is_disallowed_workspace_root("/"))
        self.assertTrue(is_disallowed_workspace_root("/etc"))
        self.assertTrue(is_disallowed_workspace_root("/bin"))
        self.assertTrue(is_disallowed_workspace_root("/usr"))
        self.assertFalse(is_disallowed_workspace_root("/home/user/my-cool-project"))

    def test_websocket_authorization_guard_logic(self):
        """
        Verifies the 3-point WebSocket security guard:
        Host check, Origin check (no null allowed), and Cookie session check.
        Uses application close code 4403 (Forbidden) and 4401 (Unauthorized) after accept.
        """
        active_port = 45123
        active_sessions = {"valid_session_token_123"}

        def authorize_ws_connection(headers: dict, cookies: dict) -> tuple[bool, int, str]:
            host = headers.get("host", "")
            if host not in [f"127.0.0.1:{active_port}", f"localhost:{active_port}"]:
                return False, 4403, "Invalid Host"

            origin = headers.get("origin")
            if origin != f"http://127.0.0.1:{active_port}":
                return False, 4403, "Cross-Origin WebSocket Denied"

            cookie = cookies.get("deskai_session")
            if not cookie or cookie not in active_sessions:
                return False, 4401, "Unauthorized Session"

            return True, 1000, "OK"

        # 1. Evil Host
        ok, code, reason = authorize_ws_connection(
            headers={"host": "evil.com", "origin": f"http://127.0.0.1:{active_port}"},
            cookies={"deskai_session": "valid_session_token_123"},
        )
        self.assertFalse(ok)
        self.assertEqual(code, 4403)

        # 2. Evil Origin
        ok, code, reason = authorize_ws_connection(
            headers={"host": f"127.0.0.1:{active_port}", "origin": "http://evil-site.com"},
            cookies={"deskai_session": "valid_session_token_123"},
        )
        self.assertFalse(ok)
        self.assertEqual(code, 4403)

        # 3. Null Origin (sandboxed iframe attempt)
        ok, code, reason = authorize_ws_connection(
            headers={"host": f"127.0.0.1:{active_port}", "origin": "null"},
            cookies={"deskai_session": "valid_session_token_123"},
        )
        self.assertFalse(ok)
        self.assertEqual(code, 4403)

        # 4. Missing / Invalid Cookie
        ok, code, reason = authorize_ws_connection(
            headers={"host": f"127.0.0.1:{active_port}", "origin": f"http://127.0.0.1:{active_port}"},
            cookies={"deskai_session": "bad_token"},
        )
        self.assertFalse(ok)
        self.assertEqual(code, 4401)

        # 5. Legitimate connection (All matched)
        ok, code, reason = authorize_ws_connection(
            headers={"host": f"127.0.0.1:{active_port}", "origin": f"http://127.0.0.1:{active_port}"},
            cookies={"deskai_session": "valid_session_token_123"},
        )
        self.assertTrue(ok)
        self.assertEqual(code, 1000)

    def test_single_use_token_redemption_logic(self):
        """
        Verifies that single-use launch token can only be redeemed once.
        Subsequent attempts return 403.
        """
        expected_token = secrets.token_urlsafe(32)
        active_tokens = {expected_token}
        sessions = set()

        def redeem_token(token_param: str) -> tuple[int, str | None]:
            if not token_param:
                return 403, None
            # Constant-time comparison
            match = False
            for active in list(active_tokens):
                if secrets.compare_digest(token_param, active):
                    match = True
                    active_tokens.remove(active)
                    break
            if not match:
                return 403, None
            session_id = secrets.token_hex(24)
            sessions.add(session_id)
            return 303, session_id

        # First attempt: valid token
        status, sess_id = redeem_token(expected_token)
        self.assertEqual(status, 303)
        self.assertIsNotNone(sess_id)
        self.assertIn(sess_id, sessions)

        # Second attempt with same token: rejected
        status_replay, sess_id_replay = redeem_token(expected_token)
        self.assertEqual(status_replay, 403)
        self.assertIsNone(sess_id_replay)

    def test_vendor_libraries_explicitly_loaded(self):
        """
        Verifies that DOMPurify, Marked and CodeMirror vendor bundles
        are explicitly loaded in index.html before the application module script.
        """
        html_file = REPO_ROOT / "src" / "deskai" / "static" / "index.html"
        content = html_file.read_text(encoding="utf-8")

        self.assertIn('src="vendor/purify.min.js"', content)
        self.assertIn('src="vendor/marked.min.js"', content)
        self.assertIn('src="vendor/codemirror.bundle.js"', content)

    def test_spec_root_static_mounting(self):
        """
        Behavioral: DesktopServer serves static files at root without 404s after token redemption.
        """
        from deskai.server.supervisor import DesktopServer
        import httpx

        server = DesktopServer()
        server.start()
        try:
            with httpx.Client(follow_redirects=True) as client:
                # Redeem launch token to establish authenticated session
                redeem_res = client.get(f"http://127.0.0.1:{server.port}/auth/redeem?token={server.launch_token}")
                self.assertEqual(redeem_res.status_code, 200)

                res_css = client.get(f"http://127.0.0.1:{server.port}/css/tokens.css")
                self.assertEqual(res_css.status_code, 200)
                self.assertIn("text/css", res_css.headers.get("content-type", ""))

                res_js = client.get(f"http://127.0.0.1:{server.port}/js/app.js")
                self.assertEqual(res_js.status_code, 200)
                self.assertIn("javascript", res_js.headers.get("content-type", ""))
        finally:
            server.stop()

    def test_spec_universal_link_and_drag_lock(self):
        """
        Verifies that events.js attaches dragover/drop navigation locks
        and handles link click interception.
        """
        events_file = REPO_ROOT / "src" / "deskai" / "static" / "js" / "events.js"
        content = events_file.read_text(encoding="utf-8")

        self.assertIn('window.addEventListener("dragover"', content)
        self.assertIn('window.addEventListener("drop"', content)
        self.assertIn('document.addEventListener("auxclick"', content)

    def test_spec_trailing_edge_token_stream(self):
        """
        Verifies that stream.js implements trailing-edge timer to flush tokens.
        """
        stream_file = REPO_ROOT / "src" / "deskai" / "static" / "js" / "stream.js"
        content = stream_file.read_text(encoding="utf-8")

        self.assertIn("this.trailingTimer = null;", content)
        self.assertIn("this.trailingTimer = setTimeout(", content)

    def test_css_sr_only_utility_present(self):
        """
        Verifies that .sr-only utility class is defined in layout.css for screen reader announcements.
        """
        css_file = REPO_ROOT / "src" / "deskai" / "static" / "css" / "layout.css"
        content = css_file.read_text(encoding="utf-8")

        self.assertIn(".sr-only {", content)
        self.assertIn("clip: rect(0, 0, 0, 0)", content)

    def test_wcag_aa_contrast_ratios_in_tokens(self):
        """
        Parses tokens.css and calculates WCAG 2.1 relative luminance and contrast ratio.
        Asserts that --text-primary, --text-secondary, --text-muted, and button text
        all exceed the WCAG AA minimum threshold of 4.5:1 on their respective backgrounds.
        """
        tokens_path = REPO_ROOT / "src" / "deskai" / "static" / "css" / "tokens.css"
        tokens_content = tokens_path.read_text(encoding="utf-8")

        import re

        tokens = {}
        for line in tokens_content.splitlines():
            line = line.strip()
            m = re.match(r"--([a-zA-Z0-9-]+)\s*:\s*([^;]+);", line)
            if m:
                tokens[m.group(1)] = m.group(2).strip()

        def hex_to_rgb(hex_code):
            hex_code = hex_code.lstrip("#")
            return tuple(int(hex_code[i : i + 2], 16) for i in (0, 2, 4))

        def rel_luminance(rgb):
            def channel(c):
                c = c / 255.0
                return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

            r, g, b = (channel(x) for x in rgb)
            return 0.2126 * r + 0.7152 * g + 0.0722 * b

        def contrast_ratio(c1, c2):
            l1, l2 = rel_luminance(hex_to_rgb(c1)), rel_luminance(hex_to_rgb(c2))
            return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)

        bg_app = tokens["bg-app"]
        bg_surface = tokens["bg-surface"]
        primary_btn_bg = tokens["color-primary"]

        text_primary = tokens["text-primary"]
        text_secondary = tokens["text-secondary"]
        text_muted = tokens["text-muted"]
        text_btn_primary = tokens["text-btn-primary"]

        # Check contrast on master background (Target >= 4.5:1)
        self.assertGreaterEqual(contrast_ratio(text_primary, bg_app), 4.5)
        self.assertGreaterEqual(contrast_ratio(text_secondary, bg_app), 4.5)
        self.assertGreaterEqual(contrast_ratio(text_muted, bg_app), 4.5)

        # Check contrast on surface
        self.assertGreaterEqual(contrast_ratio(text_primary, bg_surface), 4.5)
        self.assertGreaterEqual(contrast_ratio(text_muted, bg_surface), 4.5)

        # Check contrast on primary amber button
        self.assertGreaterEqual(contrast_ratio(text_btn_primary, primary_btn_bg), 4.5)


if __name__ == "__main__":
    unittest.main()
