from __future__ import annotations

import xml.etree.ElementTree as ET
from .models import Diagnostic, clean_text


def check_xml(source: str, rel_path: str) -> list[Diagnostic]:
    """Parse XML / SVG source with ElementTree to detect well-formedness errors."""
    try:
        ET.fromstring(source)
        return []
    except ET.ParseError as exc:
        msg = clean_text(str(exc))
        line, col = exc.position if exc.position else (1, 1)
        line = max(line, 1)
        col = max(col, 1)
        return [
            Diagnostic(
                source="xml",
                code="ParseError",
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
                source="xml",
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
