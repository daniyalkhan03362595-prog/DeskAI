from __future__ import annotations

import tomllib
from .models import Diagnostic, clean_text


def check_toml(source: str, rel_path: str) -> list[Diagnostic]:
    """Parse TOML source with standard library tomllib to detect syntax errors."""
    try:
        tomllib.loads(source)
        return []
    except tomllib.TOMLDecodeError as exc:
        msg = clean_text(str(exc))
        line = max(getattr(exc, "lineno", None) or 1, 1)
        col = max(getattr(exc, "colno", None) or 1, 1)
        return [
            Diagnostic(
                source="toml",
                code="TOMLDecodeError",
                severity="error",
                message=msg,
                file=rel_path,
                start_line=line,
                start_col=col,
                end_line=line,
                end_col=col + 1,
                ai_fixable=True,
            )
        ]
    except Exception as exc:
        return [
            Diagnostic(
                source="toml",
                code="E_UNKNOWN",
                severity="error",
                message=clean_text(str(exc)),
                file=rel_path,
                start_line=1,
                start_col=1,
                end_line=1,
                end_col=2,
                ai_fixable=True,
            )
        ]
