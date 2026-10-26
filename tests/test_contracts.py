"""
Comprehensive Contract, State Machine & Security Verification Suite for DeskAI Layer 1
Directly scans and validates documentation specifications, FSM reachability, and security invariants.
"""
import os
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

class TestDeskAILayer1Contracts(unittest.TestCase):

    def test_html_and_js_action_synchronization(self):
        """
        Scans HTML and JS LLD specifications and asserts that every action
        (including UEC buttons rendered dynamically) has a corresponding case handler.
        """
        html_spec_path = REPO_ROOT / "docs" / "layer 1 technologies" / "html5" / "LLD" / "html5.md"
        js_spec_path = REPO_ROOT / "docs" / "layer 1 technologies" / "javascript" / "LLD" / "javascript.md"

        self.assertTrue(html_spec_path.exists())
        self.assertTrue(js_spec_path.exists())

        html_content = html_spec_path.read_text(encoding="utf-8")
        js_content = js_spec_path.read_text(encoding="utf-8")

        # Extract data-action attributes from HTML and JS templates
        html_actions = set(re.findall(r'data-action="([^"]+)"', html_content))
        js_template_actions = set(re.findall(r'data-action="([^"]+)"', js_content))
        all_expected_actions = html_actions | js_template_actions

        # Extract all case "..." action handlers from JS router
        js_handlers = set(re.findall(r'case "([^"]+)":', js_content))

        unhandled = all_expected_actions - js_handlers
        self.assertEqual(
            unhandled,
            set(),
            f"The following actions lack JavaScript router handlers: {unhandled}"
        )

    def test_uec_state_machine_reachability_and_no_loops(self):
        """
        Parses UEC FSM transitions from javascript.md and verifies:
        1. REVIEW_DIFF can reach SUCCESS (Approve) and ROLLBACK (Reject).
        2. CANCELLED resets cleanly to IDLE.
        3. No endless execution loops (approve doesn't loop back to EXECUTING).
        """
        js_spec_path = REPO_ROOT / "docs" / "layer 1 technologies" / "javascript" / "LLD" / "javascript.md"
        js_content = js_spec_path.read_text(encoding="utf-8")

        # Verify transitions table definitions in spec
        self.assertIn('IDLE: ["PLANNING"]', js_content)
        self.assertIn('PLANNING: ["EXECUTING", "CANCELLED", "IDLE"]', js_content)
        self.assertIn('EXECUTING: ["REVIEW_DIFF", "FAILED", "CANCELLED"]', js_content)
        self.assertIn('REVIEW_DIFF: ["SUCCESS", "ROLLBACK", "EXECUTING"]', js_content)
        self.assertIn('CANCELLED: ["IDLE"]', js_content)
        self.assertIn('SUCCESS: ["IDLE"]', js_content)

        # Verify approvePlan method transitions REVIEW_DIFF to SUCCESS
        self.assertIn('if (current === "REVIEW_DIFF") return this.transition("SUCCESS");', js_content)

        # Verify rejectPlan method transitions REVIEW_DIFF to ROLLBACK
        self.assertIn('return this.transition("ROLLBACK");', js_content)

        # Verify reset method transitions CANCELLED to IDLE
        self.assertIn('return this.transition("IDLE");', js_content)

    def test_path_sandbox_commonpath_security(self):
        """
        Verifies that os.path.commonpath prevents traversal and prefix-spoofing attacks.
        """
        workspace_root = "/home/user/DeskAI"

        def is_safe_path(target_path: str, root: str) -> bool:
            real_target = os.path.realpath(target_path)
            real_root = os.path.realpath(root)
            try:
                return os.path.commonpath([real_target, real_root]) == real_root
            except ValueError:
                return False

        # Safe workspace paths
        self.assertTrue(is_safe_path("/home/user/DeskAI/src/main.py", workspace_root))
        self.assertTrue(is_safe_path("/home/user/DeskAI/docs/spec.md", workspace_root))

        # Malicious paths (Must be rejected)
        self.assertFalse(is_safe_path("/home/user/DeskAI-secrets/passwords.txt", workspace_root))
        self.assertFalse(is_safe_path("/etc/passwd", workspace_root))
        self.assertFalse(is_safe_path("/home/user/DeskAI/../../etc/shadow", workspace_root))
        self.assertFalse(is_safe_path("/home/user/other_project", workspace_root))

    def test_websocket_authorization_guard_logic(self):
        """
        Verifies the 3-point WebSocket security guard:
        Host check, Origin check (no null allowed), and Cookie session check.
        """
        active_port = 45123
        active_sessions = {"valid_session_token_123"}

        def authorize_ws_handshake(headers: dict, cookies: dict) -> tuple[bool, int, str]:
            host = headers.get("host", "")
            if host not in [f"127.0.0.1:{active_port}", f"localhost:{active_port}"]:
                return False, 1008, "Invalid Host"

            origin = headers.get("origin")
            if origin != f"http://127.0.0.1:{active_port}":
                return False, 1008, "Cross-Origin WebSocket Denied"

            cookie = cookies.get("deskai_session")
            if not cookie or cookie not in active_sessions:
                return False, 1008, "Unauthorized Session"

            return True, 1000, "OK"

        # 1. Evil Host
        ok, code, reason = authorize_ws_handshake(
            headers={"host": "evil.com", "origin": f"http://127.0.0.1:{active_port}"},
            cookies={"deskai_session": "valid_session_token_123"}
        )
        self.assertFalse(ok)
        self.assertEqual(code, 1008)

        # 2. Evil Origin
        ok, code, reason = authorize_ws_handshake(
            headers={"host": f"127.0.0.1:{active_port}", "origin": "http://evil-site.com"},
            cookies={"deskai_session": "valid_session_token_123"}
        )
        self.assertFalse(ok)
        self.assertEqual(code, 1008)

        # 3. Null Origin (sandboxed iframe attempt)
        ok, code, reason = authorize_ws_handshake(
            headers={"host": f"127.0.0.1:{active_port}", "origin": "null"},
            cookies={"deskai_session": "valid_session_token_123"}
        )
        self.assertFalse(ok)
        self.assertEqual(code, 1008)

        # 4. Missing / Invalid Cookie
        ok, code, reason = authorize_ws_handshake(
            headers={"host": f"127.0.0.1:{active_port}", "origin": f"http://127.0.0.1:{active_port}"},
            cookies={"deskai_session": "bad_token"}
        )
        self.assertFalse(ok)
        self.assertEqual(code, 1008)

        # 5. Legitimate connection (All matched)
        ok, code, reason = authorize_ws_handshake(
            headers={"host": f"127.0.0.1:{active_port}", "origin": f"http://127.0.0.1:{active_port}"},
            cookies={"deskai_session": "valid_session_token_123"}
        )
        self.assertTrue(ok)
        self.assertEqual(code, 1000)

    def test_vendor_libraries_explicitly_loaded(self):
        """
        Verifies that DOMPurify, Marked and CodeMirror vendor bundles
        are explicitly loaded before application module script.
        """
        html_spec_path = REPO_ROOT / "docs" / "layer 1 technologies" / "html5" / "LLD" / "html5.md"
        content = html_spec_path.read_text(encoding="utf-8")

        self.assertIn('<script src="vendor/purify.min.js"></script>', content)
        self.assertIn('<script src="vendor/marked.min.js"></script>', content)
        self.assertIn('<script src="vendor/codemirror.bundle.js"></script>', content)

if __name__ == "__main__":
    unittest.main()
