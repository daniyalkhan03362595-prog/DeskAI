from __future__ import annotations

from html.parser import HTMLParser
from .models import Diagnostic, clean_text

VOID_ELEMENTS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class HTMLValidator(HTMLParser):
    def __init__(self, rel_path: str) -> None:
        super().__init__()
        self.rel_path = rel_path
        self.stack: list[tuple[str, int, int]] = []
        self.diagnostics: list[Diagnostic] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t not in VOID_ELEMENTS:
            line, col = self.getpos()
            self.stack.append((t, line, col + 1))

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in VOID_ELEMENTS:
            return
        line, col = self.getpos()
        if not self.stack:
            self.diagnostics.append(
                Diagnostic(
                    source="html",
                    code="HTML_UNEXPECTED_CLOSE",
                    severity="error",
                    message=f"Unexpected closing tag </{t}> without matching open tag",
                    file=self.rel_path,
                    start_line=line,
                    start_col=col + 1,
                    end_line=line,
                    end_col=col + len(t) + 3,
                    ai_fixable=True,
                )
            )
            return

        open_tag, o_line, o_col = self.stack.pop()
        if open_tag != t:
            self.diagnostics.append(
                Diagnostic(
                    source="html",
                    code="HTML_MISMATCHED_TAG",
                    severity="error",
                    message=f"Mismatched closing tag </{t}>; expected </{open_tag}>",
                    file=self.rel_path,
                    start_line=line,
                    start_col=col + 1,
                    end_line=line,
                    end_col=col + len(t) + 3,
                    ai_fixable=True,
                )
            )

    def finalize(self) -> None:
        for open_tag, o_line, o_col in self.stack:
            self.diagnostics.append(
                Diagnostic(
                    source="html",
                    code="HTML_UNCLOSED_TAG",
                    severity="warning",
                    message=f"Unclosed HTML tag <{open_tag}>",
                    file=self.rel_path,
                    start_line=o_line,
                    start_col=o_col,
                    end_line=o_line,
                    end_col=o_col + len(open_tag) + 2,
                    ai_fixable=True,
                )
            )


def check_html(source: str, rel_path: str) -> list[Diagnostic]:
    """Parse HTML source to detect mismatched, unexpected, and unclosed tags."""
    validator = HTMLValidator(rel_path)
    try:
        validator.feed(source)
        validator.finalize()
        validator.diagnostics.sort(key=lambda d: (d.start_line, d.start_col))
        return validator.diagnostics
    except Exception as exc:
        return [
            Diagnostic(
                source="html",
                code="HTML_PARSE_ERROR",
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
