from __future__ import annotations

import unittest
from deskai.diagnostics.ast_linter import check_python_ast
from deskai.diagnostics.python_syntax import check_python


class TestProblemsASTWarnings(unittest.TestCase):
    def test_unused_local_variable_w001(self) -> None:
        source = """
def calc(a, b):
    result = a + b
    unused_val = 99
    _throwaway = 1
    return result
"""
        diags = check_python_ast(source, "math_helpers.py")
        w001 = [d for d in diags if d.code == "W001"]
        self.assertEqual(len(w001), 1)
        self.assertEqual(w001[0].severity, "warning")
        self.assertIn("unused_val", w001[0].message)
        self.assertEqual(w001[0].start_line, 4)

    def test_unused_import_w002(self) -> None:
        source = """
import os
import sys as system
from math import sin, cos

def compute(x):
    return sin(x)
"""
        diags = check_python_ast(source, "trig.py")
        w002 = [d for d in diags if d.code == "W002"]
        unused_names = {d.message for d in w002}
        self.assertEqual(len(w002), 3)
        self.assertTrue(any("os" in msg for msg in unused_names))
        self.assertTrue(any("system" in msg for msg in unused_names))
        self.assertTrue(any("cos" in msg for msg in unused_names))
        self.assertFalse(any("sin" in msg for msg in unused_names))

    def test_all_exports_suppress_unused_import(self) -> None:
        source = """
import os
from pathlib import Path

__all__ = ["os", "Path"]
"""
        diags = check_python_ast(source, "pkg/__init__.py")
        w002 = [d for d in diags if d.code == "W002"]
        self.assertEqual(len(w002), 0)

    def test_duplicate_dict_key_w003(self) -> None:
        source = """
data = {
    "key1": "first",
    "key2": "second",
    "key1": "overwrite",
}
"""
        diags = check_python_ast(source, "config.py")
        w003 = [d for d in diags if d.code == "W003"]
        self.assertEqual(len(w003), 1)
        self.assertEqual(w003[0].severity, "warning")
        self.assertIn("key1", w003[0].message)
        self.assertEqual(w003[0].start_line, 5)

    def test_clean_file_no_warnings(self) -> None:
        source = """
import os

def get_cwd():
    path = os.getcwd()
    return path
"""
        diags = check_python(source, "clean.py")
        self.assertEqual(len(diags), 0)

    def test_syntax_error_takes_precedence_over_warnings(self) -> None:
        source = """
import os
def broken():
    unused = 12
    return (
"""
        diags = check_python(source, "syntax_err.py")
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0].severity, "error")

    def test_info_comparison_to_none_i001(self) -> None:
        source = """
def is_empty(val):
    if val == None:
        return True
    return False
"""
        diags = check_python_ast(source, "checks.py")
        i001 = [d for d in diags if d.code == "I001"]
        self.assertEqual(len(i001), 1)
        self.assertEqual(i001[0].severity, "info")
        self.assertIn("cond is None", i001[0].message)

    def test_info_todo_comment_i002(self) -> None:
        source = """
def connect():
    # TODO: add retry logic with exponential backoff
    pass
"""
        diags = check_python_ast(source, "net.py")
        i002 = [d for d in diags if d.code == "I002"]
        self.assertEqual(len(i002), 1)
        self.assertEqual(i002[0].severity, "info")
        self.assertIn("add retry logic", i002[0].message)


if __name__ == "__main__":
    unittest.main()
