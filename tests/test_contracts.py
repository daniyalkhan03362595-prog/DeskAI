"""
Comprehensive Contract and Security Verification Suite for DeskAI Layer 1
Directly scans and validates documentation specifications and security invariants.
"""
import os
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

class TestDeskAILayer1Contracts(unittest.TestCase):

    def test_html_and_js_action_synchronization(self):
        """
        Scans HTML LLD specification for data-action attributes and verifies
        that every action has an explicit handler in JavaScript LLD specification.
        """
        html_spec_path = REPO_ROOT / "docs" / "layer 1 technologies" / "html5" / "LLD" / "html5.md"
        js_spec_path = REPO_ROOT / "docs" / "layer 1 technologies" / "javascript" / "LLD" / "javascript.md"

        self.assertTrue(html_spec_path.exists(), f"Missing HTML spec: {html_spec_path}")
        self.assertTrue(js_spec_path.exists(), f"Missing JS spec: {js_spec_path}")

        html_content = html_spec_path.read_text(encoding="utf-8")
        js_content = js_spec_path.read_text(encoding="utf-8")

        # Extract all data-action attributes from HTML
        html_actions = set(re.findall(r'data-action="([^"]+)"', html_content))
        self.assertGreater(len(html_actions), 0, "No data-action attributes found in HTML spec.")

        # Extract all case "..." action handlers from JS router
        js_handlers = set(re.findall(r'case "([^"]+)":', js_content))
        self.assertGreater(len(js_handlers), 0, "No case handlers found in JS spec.")

        # Assert every HTML action is handled in JS
        unhandled_actions = html_actions - js_handlers
        self.assertEqual(
            unhandled_actions,
            set(),
            f"The following HTML data-actions lack JavaScript handlers: {unhandled_actions}"
        )

    def test_path_sandbox_commonpath_security(self):
        """
        Verifies that the os.path.commonpath sandbox prevents path traversal
        and prefix-spoofing attacks (such as /workspace-secrets bypass).
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
        self.assertTrue(is_safe_path("/home/user/DeskAI/index.html", workspace_root))

        # Attacking paths (Must be rejected)
        self.assertFalse(is_safe_path("/home/user/DeskAI-secrets/passwords.txt", workspace_root))
        self.assertFalse(is_safe_path("/etc/passwd", workspace_root))
        self.assertFalse(is_safe_path("/home/user/DeskAI/../../etc/shadow", workspace_root))
        self.assertFalse(is_safe_path("/home/user/other_project", workspace_root))

    def test_standardized_error_taxonomy(self):
        """
        Verifies that all standardized error codes are defined in the PyWebView specification.
        """
        pywebview_spec = REPO_ROOT / "docs" / "layer 1 technologies" / "pywebview" / "LLD" / "pywebview.md"
        self.assertTrue(pywebview_spec.exists())
        content = pywebview_spec.read_text(encoding="utf-8")

        required_codes = [
            "ERR_SANDBOX_VIOLATION",
            "ERR_DIALOG_CANCELLED",
            "ERR_FILE_NOT_FOUND",
            "ERR_WIN_CONTROL_FAILED",
            "ERR_INVALID_URL",
            "ERR_INTERNAL"
        ]
        for code in required_codes:
            self.assertIn(code, content, f"ErrorCode {code} missing in PyWebView LLD.")

    def test_wcag_aa_contrast_token(self):
        """
        Verifies that --text-muted token is configured to #858fa8 (exceeding WCAG AA 4.5:1).
        """
        css_spec = REPO_ROOT / "docs" / "layer 1 technologies" / "css3" / "LLD" / "css3.md"
        self.assertTrue(css_spec.exists())
        content = css_spec.read_text(encoding="utf-8")
        self.assertIn("--text-muted: #858fa8", content)
        self.assertNotIn("--text-muted: #626b84", content)

if __name__ == "__main__":
    unittest.main()
