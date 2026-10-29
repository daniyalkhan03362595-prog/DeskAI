from __future__ import annotations
import hashlib
import re
from dataclasses import dataclass

SEVERITIES = ("error", "warning", "info")
MAX_MESSAGE_LEN = 500
_CONTROL_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(value: str, limit: int = MAX_MESSAGE_LEN) -> str:
    """Strip ANSI escapes and control characters; collapse to a bounded single-line message."""
    text = _CONTROL_RE.sub("", str(value)).replace("\r", " ").replace("\n", " ").strip()
    return text[:limit]


@dataclass(frozen=True)
class Diagnostic:
    source: str
    code: str | None
    severity: str  # one of SEVERITIES
    message: str
    file: str  # workspace-relative, forward slashes
    start_line: int
    start_col: int
    end_line: int
    end_col: int
    ai_fixable: bool = True
    quick_fix_suggestion: str | None = None

    @property
    def id(self) -> str:
        raw = f"{self.source}|{self.code}|{self.file}|{self.start_line}|{self.start_col}|{self.message}"
        return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:16]

    def to_dict(self) -> dict:
        data = {
            "id": self.id,
            "source": self.source,
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "file": self.file,
            "range": {
                "startLine": max(self.start_line, 1),
                "startCol": max(self.start_col, 1),
                "endLine": max(self.end_line, self.start_line, 1),
                "endCol": max(self.end_col, self.start_col + 1, 1),
            },
            "aiFixable": self.ai_fixable,
        }
        if self.quick_fix_suggestion:
            data["quickFixSuggestion"] = self.quick_fix_suggestion
        return data
