import json
import os
from .models import Diagnostic, clean_text


def check_json(source: str, rel_path: str) -> list[Diagnostic]:
    """Parse JSON source with json.loads. Skip .jsonc and tsconfig*.json."""
    base = os.path.basename(rel_path).lower()
    if rel_path.lower().endswith(".jsonc") or base.startswith("tsconfig"):
        return []

    try:
        json.loads(source)
        return []
    except json.JSONDecodeError as exc:
        line = max(exc.lineno, 1)
        col = max(exc.colno, 1)
        return [
            Diagnostic(
                "json",
                "JSON",
                "error",
                clean_text(exc.msg),
                rel_path,
                line,
                col,
                line,
                col + 1,
            )
        ]
