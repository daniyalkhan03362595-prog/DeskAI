"""DeskAI Diagnostics Package.

Provides isolated syntax and linting diagnostics for workspace files.
"""

from .models import Diagnostic, clean_text
from .runner import run_checks
from .cache import DiagnosticsCache
from .ast_linter import PythonASTLinter, check_python_ast
from .toml_syntax import check_toml
from .html_syntax import check_html
from .xml_syntax import check_xml

__all__ = [
    "Diagnostic",
    "clean_text",
    "run_checks",
    "DiagnosticsCache",
    "PythonASTLinter",
    "check_python_ast",
    "check_toml",
    "check_html",
    "check_xml",
]
