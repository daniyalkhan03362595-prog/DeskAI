"""DeskAI Diagnostics Package.

Provides isolated syntax and linting diagnostics for workspace files.
"""

from .models import Diagnostic, clean_text
from .runner import run_checks

__all__ = ["Diagnostic", "clean_text", "run_checks"]
