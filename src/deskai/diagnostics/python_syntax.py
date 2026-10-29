import ast
from .ast_linter import check_python_ast
from .models import Diagnostic, clean_text


def check_python(source: str, rel_path: str) -> list[Diagnostic]:
    """Parse Python source with ast.parse to detect syntax errors and AST warnings without executing code."""
    try:
        tree = ast.parse(source, filename=rel_path, type_comments=False)
        return check_python_ast(source, rel_path, tree)
    except SyntaxError as exc:  # includes IndentationError / TabError
        msg = clean_text(exc.msg or "Invalid syntax")
        if "too many nested" in msg.lower():
            return [
                Diagnostic(
                    "python",
                    "E_COMPLEXITY",
                    "error",
                    "File is too deeply nested or too large to analyse",
                    rel_path,
                    1,
                    1,
                    1,
                    2,
                )
            ]
        line = max(exc.lineno or 1, 1)
        col = max(exc.offset or 1, 1)
        end_line = max(getattr(exc, "end_lineno", None) or line, line)
        end_col = max(getattr(exc, "end_offset", None) or col + 1, 1)
        return [
            Diagnostic(
                "python",
                exc.__class__.__name__,
                "error",
                msg,
                rel_path,
                line,
                col,
                end_line,
                end_col,
            )
        ]
    except (RecursionError, MemoryError):
        return [
            Diagnostic(
                "python",
                "E_COMPLEXITY",
                "error",
                "File is too deeply nested or too large to analyse",
                rel_path,
                1,
                1,
                1,
                2,
            )
        ]
    except ValueError:  # e.g. source contains null bytes
        return [Diagnostic("python", "E_VALUE", "error", "File contains invalid characters", rel_path, 1, 1, 1, 2)]
