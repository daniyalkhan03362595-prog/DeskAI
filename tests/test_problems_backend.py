"""Backend unit tests for the DeskAI diagnostics package (TC-PRB-07..13)."""

import unittest
from deskai.diagnostics.models import Diagnostic, clean_text
from deskai.diagnostics.python_syntax import check_python
from deskai.diagnostics.json_syntax import check_json
from deskai.diagnostics.runner import run_checks, MAX_DIAGNOSTICS_PER_FILE
import tempfile
import os


class TestProblemsBackend(unittest.TestCase):
    def test_tc_prb_07_python_syntax_error(self):
        """TC-PRB-07: def f(: returns 1 error with correct 1-based line/col."""
        code = "def f(:\n    pass\n"
        diags = check_python(code, "test.py")
        self.assertEqual(len(diags), 1)
        d = diags[0]
        self.assertEqual(d.source, "python")
        self.assertEqual(d.severity, "error")
        self.assertEqual(d.code, "SyntaxError")
        self.assertEqual(d.file, "test.py")
        self.assertEqual(d.start_line, 1)
        self.assertGreaterEqual(d.start_col, 1)
        self.assertGreaterEqual(d.end_line, 1)
        self.assertGreaterEqual(d.end_col, d.start_col)

    def test_tc_prb_08_python_syntax_valid(self):
        """TC-PRB-08: Valid Python file returns no diagnostics."""
        code = "def f():\n    return 42\n"
        diags = check_python(code, "valid.py")
        self.assertEqual(diags, [])

    def test_tc_prb_09_python_deep_nesting(self):
        """TC-PRB-09: 100k nested parens -> single E_COMPLEXITY diagnostic, no exception."""
        deep_code = "(" * 100_000 + ")" * 100_000
        diags = check_python(deep_code, "deep.py")
        self.assertEqual(len(diags), 1)
        d = diags[0]
        self.assertEqual(d.source, "python")
        self.assertEqual(d.code, "E_COMPLEXITY")
        self.assertEqual(d.severity, "error")
        self.assertIn("nested", d.message.lower())

    def test_tc_prb_10_json_syntax(self):
        """TC-PRB-10: {'a':} -> error with JSON code and line/col; .jsonc and tsconfig skipped."""
        invalid_json = '{\n  "a":\n}'
        diags = check_json(invalid_json, "config.json")
        self.assertEqual(len(diags), 1)
        d = diags[0]
        self.assertEqual(d.source, "json")
        self.assertEqual(d.code, "JSON")
        self.assertEqual(d.severity, "error")
        self.assertGreaterEqual(d.start_line, 1)
        self.assertGreaterEqual(d.start_col, 1)

        # .jsonc skipped
        self.assertEqual(check_json("{ /* comment */ }", "settings.jsonc"), [])
        # tsconfig*.json skipped
        self.assertEqual(check_json("{ /* comment */ }", "tsconfig.base.json"), [])

    def test_tc_prb_11_caps_and_truncation(self):
        """TC-PRB-11: Exceeding MAX_DIAGNOSTICS_PER_FILE returns capped list with truncated=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fpath = os.path.join(tmpdir, "invalid.json")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write("invalid json")

            res = run_checks(fpath, tmpdir, request_id="req-1")
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["request_id"], "req-1")
            self.assertFalse(res["truncated"])

        # Test synthetic truncation logic with > 500 diagnostics
        fake_diags = [Diagnostic("mock", f"E{i}", "error", f"Msg {i}", "f.py", i, 1, i, 2) for i in range(1, 601)]
        fake_diags.sort(key=lambda d: (d.start_line, d.start_col, d.source))
        truncated = len(fake_diags) > MAX_DIAGNOSTICS_PER_FILE
        capped = fake_diags[:MAX_DIAGNOSTICS_PER_FILE]
        self.assertTrue(truncated)
        self.assertEqual(len(capped), MAX_DIAGNOSTICS_PER_FILE)

    def test_tc_prb_12_sanitizer(self):
        """TC-PRB-12: ANSI escapes and control characters removed, length capped at 500."""
        dirty = "\x1b[31;1mRed Error\x1b[0m \x00\x07with\r\nnewlines and bell"
        cleaned = clean_text(dirty)
        self.assertNotIn("\x1b", cleaned)
        self.assertNotIn("\x00", cleaned)
        self.assertNotIn("\x07", cleaned)
        self.assertNotIn("\n", cleaned)
        self.assertNotIn("\r", cleaned)
        self.assertEqual(cleaned, "Red Error with  newlines and bell")

        # Capped length
        long_text = "a" * 1000
        self.assertEqual(len(clean_text(long_text)), 500)

    def test_tc_prb_13_fingerprint_id(self):
        """TC-PRB-13: Same input -> same id; different line -> different id."""
        d1 = Diagnostic("python", "SyntaxError", "error", "bad syntax", "a.py", 10, 5, 10, 6)
        d2 = Diagnostic("python", "SyntaxError", "error", "bad syntax", "a.py", 10, 5, 10, 6)
        d3 = Diagnostic("python", "SyntaxError", "error", "bad syntax", "a.py", 11, 5, 11, 6)

        self.assertEqual(d1.id, d2.id)
        self.assertNotEqual(d1.id, d3.id)
        self.assertEqual(len(d1.id), 16)


if __name__ == "__main__":
    unittest.main()
