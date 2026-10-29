from __future__ import annotations

import ast
from .models import Diagnostic


class PythonASTLinter(ast.NodeVisitor):
    """Zero-dependency Python AST linter detecting high-value warnings:

    - W001: Unused local variables in functions
    - W002: Unused imported modules / symbols
    - W003: Duplicate dictionary keys
    """

    def __init__(self, rel_path: str) -> None:
        self.rel_path = rel_path
        self.diagnostics: list[Diagnostic] = []
        # Track module-level imports: name_to_use -> (node, lineno, col)
        self.imports: dict[str, tuple[ast.AST, int, int]] = {}
        # Track all loaded names across the whole module
        self.loaded_names: set[str] = set()
        # Track __all__ exported names
        self.exported_names: set[str] = set()

    def check(self, tree: ast.AST) -> list[Diagnostic]:
        self.visit(tree)
        # Check unused imports
        for imp_name, (node, lineno, col) in self.imports.items():
            if imp_name not in self.loaded_names and imp_name not in self.exported_names:
                self.diagnostics.append(
                    Diagnostic(
                        source="python",
                        code="W002",
                        severity="warning",
                        message=f"Import '{imp_name}' is unused",
                        file=self.rel_path,
                        start_line=lineno,
                        start_col=col,
                        end_line=lineno,
                        end_col=col + len(imp_name),
                        ai_fixable=True,
                    )
                )

        # Sort diagnostics by line, col, code
        self.diagnostics.sort(key=lambda d: (d.start_line, d.start_col, d.code))
        return self.diagnostics

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            target_name = alias.asname or alias.name.split(".")[0]
            if target_name != "*":
                lineno = getattr(alias, "lineno", node.lineno)
                col = getattr(alias, "col_offset", node.col_offset) + 1
                self.imports[target_name] = (alias, lineno, col)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "__future__":
            return
        for alias in node.names:
            if alias.name == "*":
                continue
            target_name = alias.asname or alias.name
            lineno = getattr(alias, "lineno", node.lineno)
            col = getattr(alias, "col_offset", node.col_offset) + 1
            self.imports[target_name] = (alias, lineno, col)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # Check __all__ assignments
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                    for elt in node.value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            self.exported_names.add(elt.value)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.loaded_names.add(node.id)
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:
        seen_keys: set[object] = set()
        for k in node.keys:
            if k is not None and isinstance(k, ast.Constant):
                val = k.value
                val_str = val.decode("utf-8", "replace") if isinstance(val, bytes) else str(val)
                # Key representations hashable
                if val in seen_keys:
                    self.diagnostics.append(
                        Diagnostic(
                            source="python",
                            code="W003",
                            severity="warning",
                            message=f"Duplicate dictionary key '{val_str}'",
                            file=self.rel_path,
                            start_line=k.lineno,
                            start_col=k.col_offset + 1,
                            end_line=getattr(k, "end_lineno", k.lineno),
                            end_col=getattr(k, "end_col_offset", k.col_offset + len(val_str)) + 1,
                            ai_fixable=True,
                        )
                    )
                else:
                    seen_keys.add(val)
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        for op, comparator in zip(node.ops, node.comparators):
            if isinstance(op, ast.Eq) and isinstance(comparator, ast.Constant) and comparator.value is None:
                self.diagnostics.append(
                    Diagnostic(
                        source="python",
                        code="I001",
                        severity="info",
                        message="Comparison to None should be 'cond is None' (PEP 8)",
                        file=self.rel_path,
                        start_line=node.lineno,
                        start_col=node.col_offset + 1,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        end_col=getattr(node, "end_col_offset", node.col_offset + 10) + 1,
                        ai_fixable=True,
                    )
                )
            elif isinstance(op, ast.NotEq) and isinstance(comparator, ast.Constant) and comparator.value is None:
                self.diagnostics.append(
                    Diagnostic(
                        source="python",
                        code="I001",
                        severity="info",
                        message="Comparison to None should be 'cond is not None' (PEP 8)",
                        file=self.rel_path,
                        start_line=node.lineno,
                        start_col=node.col_offset + 1,
                        end_line=getattr(node, "end_lineno", node.lineno),
                        end_col=getattr(node, "end_col_offset", node.col_offset + 10) + 1,
                        ai_fixable=True,
                    )
                )
        self.generic_visit(node)

    def _check_function_scope(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        assigned_vars: dict[str, tuple[int, int, int, int]] = {}
        used_vars: set[str] = set()

        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                if isinstance(child.ctx, ast.Store):
                    var_name = child.id
                    # Ignore private/throwaway names, self, cls
                    if not var_name.startswith("_") and var_name not in {"self", "cls"}:
                        if var_name not in assigned_vars:
                            assigned_vars[var_name] = (
                                child.lineno,
                                child.col_offset + 1,
                                getattr(child, "end_lineno", child.lineno),
                                getattr(child, "end_col_offset", child.col_offset + len(var_name)) + 1,
                            )
                elif isinstance(child.ctx, ast.Load):
                    used_vars.add(child.id)
            elif isinstance(child, (ast.Global, ast.Nonlocal)):
                for name in child.names:
                    used_vars.add(name)

        # Do not flag function argument names as unused local assignments
        arg_names: set[str] = {arg.arg for arg in node.args.args}
        arg_names.update(arg.arg for arg in getattr(node.args, "posonlyargs", []))
        arg_names.update(arg.arg for arg in node.args.kwonlyargs)
        if node.args.vararg:
            arg_names.add(node.args.vararg.arg)
        if node.args.kwarg:
            arg_names.add(node.args.kwarg.arg)

        for var_name, (s_line, s_col, e_line, e_col) in assigned_vars.items():
            if var_name in arg_names:
                continue
            if var_name not in used_vars:
                self.diagnostics.append(
                    Diagnostic(
                        source="python",
                        code="W001",
                        severity="warning",
                        message=f"Local variable '{var_name}' is assigned but never used",
                        file=self.rel_path,
                        start_line=s_line,
                        start_col=s_col,
                        end_line=e_line,
                        end_col=e_col,
                        ai_fixable=True,
                    )
                )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_function_scope(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_function_scope(node)
        self.generic_visit(node)


def check_python_ast(source: str, rel_path: str, tree: ast.AST | None = None) -> list[Diagnostic]:
    """Run AST warning and info analysis on Python source. Returns list of Diagnostic items."""
    try:
        if tree is None:
            tree = ast.parse(source, filename=rel_path, type_comments=False)
        linter = PythonASTLinter(rel_path)
        diags = linter.check(tree)

        # Check for TODO / FIXME task comments (severity: info)
        for idx, line in enumerate(source.splitlines(), start=1):
            if "#" in line:
                hash_pos = line.find("#")
                comment = line[hash_pos:]
                cmt_lower = comment.lower()
                if "todo:" in cmt_lower or "todo " in cmt_lower or "fixme:" in cmt_lower:
                    msg = comment.lstrip("#").strip()
                    diags.append(
                        Diagnostic(
                            source="python",
                            code="I002",
                            severity="info",
                            message=msg,
                            file=rel_path,
                            start_line=idx,
                            start_col=hash_pos + 1,
                            end_line=idx,
                            end_col=hash_pos + 1 + len(comment),
                            ai_fixable=False,
                        )
                    )

        diags.sort(key=lambda d: (d.start_line, d.start_col, d.code or ""))
        return diags
    except Exception:
        # If AST parsing fails or file has syntax error, syntax checker handles it
        return []
