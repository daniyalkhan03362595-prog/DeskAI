# Low-Level Design (LLD): Problems Panel (Workspace Diagnostics)

**Document ID:** `ORX-LLD-PROBLEMS-PANEL-V3`  
**Version:** `3.0` (Advanced Evolution, 1000x Performance & AI Integration — supersedes `ORX-LLD-PROBLEMS-PANEL-V2`)  
**Parent Document:** `ORX-HLD-PROBLEMS-PANEL-V3`  
**Target Codebase:** `DeskAI` (verified against `main` @ `6a583c0`)  
**Status:** Approved & Target Architecture  
**Date:** October 30, 2026  

---

## 1. File Map

| File | Action | Purpose | Phase |
| :--- | :--- | :--- | :--- |
| `src/deskai/diagnostics/__init__.py` | MODIFY | Public exports: `run_checks`, `DiagnosticsCache` | Phase 1 |
| `src/deskai/diagnostics/models.py` | MODIFY | `Diagnostic` dataclass, range model, `ai_fixable` flag | Phase 2 |
| `src/deskai/diagnostics/cache.py` | NEW | `DiagnosticsCache` in-memory stat-based cache (mtime + size) | Phase 1 |
| `src/deskai/diagnostics/runner.py` | MODIFY | ThreadPool multi-core parallel dispatch, zero-dep checkers router | Phase 1 & 5 |
| `src/deskai/diagnostics/python_syntax.py` | PRESERVE | `ast.parse` syntax error checker | Baseline |
| `src/deskai/diagnostics/ast_linter.py` | NEW | Zero-dep Python AST linter (unused vars, unused imports, undefined names) | Phase 4 |
| `src/deskai/diagnostics/json_syntax.py` | PRESERVE | `json.loads` checker | Baseline |
| `src/deskai/diagnostics/toml_syntax.py` | NEW | Built-in `tomllib` syntax validator | Phase 5 |
| `src/deskai/diagnostics/html_syntax.py` | NEW | Built-in `html.parser.HTMLParser` structure validator | Phase 5 |
| `src/deskai/diagnostics/xml_syntax.py` | NEW | Built-in `xml.etree.ElementTree` XML/SVG checker | Phase 5 |
| `src/deskai/bridge/diagnostics.py` | MODIFY | `DiagnosticsBridge` integration with cache, threadpool, and AI quick-fix | Phase 1 & 2 |
| `src/deskai/bridge/api.py` | PRESERVE | Facade base composition | Baseline |
| `src/deskai/static/js/problems/store.js` | MODIFY | `DiagnosticsStore` (replace-sets, signature caching, replaceAllWorkspace) | Phase 1 |
| `src/deskai/static/js/problems/view.js` | MODIFY | Safe DOM render, AI quick-fix buttons, roving tabindex keyboard model | Phase 2 & 6 |
| `src/deskai/static/js/problems/index.js` | MODIFY | `ProblemsManager` lifecycle, auto-sync hooks, UEC action dispatcher | Phase 2 |
| `src/deskai/static/js/problems/editor_decorations.js` | NEW | CodeMirror 6 inline wavy squiggles, gutter dots, and hover tooltips | Phase 3 |
| `src/deskai/static/js/problems/status_bar.js` | NEW | Persistent bottom status bar diagnostics widget `[✖ 2  ▲ 1]` | Phase 6 |
| `src/deskai/static/js/bridge.js` | MODIFY | `runDiagnostics()`, `runWorkspaceDiagnostics()`, `requestProblemAiFix()` | Phase 1 & 2 |
| `src/deskai/static/js/editor.js` | MODIFY | Register CodeMirror 6 diagnostic decoration extension | Phase 3 |
| `src/deskai/static/js/app.js` | MODIFY | Bootstrap status bar widget and editor decoration hooks | Phase 3 & 6 |
| `src/deskai/static/css/components.css` | MODIFY | Squiggle wavy lines, tooltip card, AI button styles, status pill | Phase 2, 3, 6 |
| `tests/test_problems_*.py` | MODIFY | Comprehensive test coverage for caching, parallelism, AI, and checkers | All |

---

## 2. Backend Architecture

### 2.1 Enhanced `models.py`

```python
from __future__ import annotations
import hashlib
import re
from dataclasses import dataclass, asdict

SEVERITIES = ("error", "warning", "info")
MAX_MESSAGE_LEN = 500
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]|\x1b\[[0-9;?]*[ -/]*[@-~]")


def clean_text(value: str, limit: int = MAX_MESSAGE_LEN) -> str:
    """Strip ANSI escapes and control characters; collapse to a bounded single-line message."""
    text = _CONTROL_RE.sub("", str(value)).replace("\r", " ").replace("\n", " ").strip()
    return text[:limit]


@dataclass(frozen=True)
class Diagnostic:
    source: str
    code: str | None
    severity: str           # "error" | "warning" | "info"
    message: str
    file: str               # workspace-relative, forward slashes
    start_line: int
    start_col: int
    end_line: int
    end_col: int
    ai_fixable: bool = False
    quick_fix_suggestion: str | None = None

    @property
    def id(self) -> str:
        raw = f"{self.source}|{self.code}|{self.file}|{self.start_line}|{self.start_col}|{self.message}"
        return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:16]

    def to_dict(self) -> dict:
        data = {
            "id": self.id,
            "source": self.source,
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "file": self.file,
            "range": {
                "startLine": self.start_line,
                "startCol": self.start_col,
                "endLine": self.end_line,
                "endCol": self.end_col,
            },
            "aiFixable": self.ai_fixable,
        }
        if self.quick_fix_suggestion:
            data["quickFixSuggestion"] = self.quick_fix_suggestion
        return data
```

---

### 2.2 Phase 1: MTime Stat Cache (`cache.py`)

The stat cache maps each canonicalized file path to its modification time, byte size, and pre-computed diagnostics. Because `os.stat` is executed at the kernel VFS layer without reading file bytes, checking an unchanged file takes ~1 microsecond ($0.001\text{ ms}$).

```python
import os
import threading
from typing import NamedTuple
from deskai.diagnostics.models import Diagnostic


class CacheEntry(NamedTuple):
    mtime_ns: int
    file_size: int
    diagnostics: list[Diagnostic]


class DiagnosticsCache:
    """Thread-safe in-memory cache keyed by canonical file path and os.stat metadata."""

    def __init__(self, max_entries: int = 10000):
        self._cache: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self._max_entries = max_entries

    def get_if_valid(self, abs_path: str) -> list[Diagnostic] | None:
        """Return cached diagnostics if file exists and mtime + size match; otherwise None."""
        try:
            st = os.stat(abs_path)
        except OSError:
            self.invalidate(abs_path)
            return None

        with self._lock:
            entry = self._cache.get(abs_path)
            if entry and entry.mtime_ns == st.st_mtime_ns and entry.file_size == st.st_size:
                return entry.diagnostics
        return None

    def put(self, abs_path: str, diagnostics: list[Diagnostic]) -> None:
        """Store diagnostics with current file stat."""
        try:
            st = os.stat(abs_path)
        except OSError:
            return

        with self._lock:
            if len(self._cache) >= self._max_entries:
                # Evict oldest 10%
                for k in list(self._cache.keys())[: self._max_entries // 10]:
                    del self._cache[k]
            self._cache[abs_path] = CacheEntry(
                mtime_ns=st.st_mtime_ns,
                file_size=st.st_size,
                diagnostics=list(diagnostics),
            )

    def invalidate(self, abs_path: str) -> None:
        with self._lock:
            self._cache.pop(abs_path, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
```

---

### 2.3 Phase 1: Multi-Core ThreadPool Scanner (`bridge/diagnostics.py`)

```python
import concurrent.futures
import os
import time
from deskai.diagnostics.cache import DiagnosticsCache

class DiagnosticsBridge(BaseBridgeModule):
    _diag_cache = DiagnosticsCache()
    _executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=min(32, (os.cpu_count() or 4) + 4),
        thread_name_prefix="DeskAIDiagWorker"
    )

    def run_workspace_diagnostics(self, request_id: str = "") -> dict:
        if not self.workspace_root or not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized", "request_id": request_id, "files": {}}

        t0 = time.perf_counter()
        results: dict[str, list[dict]] = {}
        cache_hits = 0
        cache_misses = 0
        missed_files: list[tuple[str, str]] = []

        # 1. Fast stat-scan pass
        for root, dirs, files in os.walk(self.workspace_root, followlinks=False):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_WORKSPACE_SCAN_DIRS]
            for file_name in files:
                full_p = os.path.join(root, file_name)
                if not self._is_safe_path(full_p):
                    continue

                cached_diags = self._diag_cache.get_if_valid(full_p)
                if cached_diags is not None:
                    cache_hits += 1
                    if cached_diags:
                        rel = os.path.relpath(full_p, self.workspace_root).replace(os.sep, "/")
                        results[rel] = [d.to_dict() for d in cached_diags]
                else:
                    cache_misses += 1
                    missed_files.append((canonicalize_path(full_p), self.workspace_root))

        # 2. Parallel cold-parse pass for modified/new files
        if missed_files:
            def _worker(item: tuple[str, str]):
                path, root = item
                res = run_checks(path, root, request_id=request_id)
                return path, res

            futures = [self._executor.submit(_worker, item) for item in missed_files]
            for f in concurrent.futures.as_completed(futures):
                try:
                    path, res = f.result()
                    diags_objs = res.get("diagnostic_objects", [])
                    self._diag_cache.put(path, diags_objs)
                    if res.get("status") == "ok" and res.get("diagnostics"):
                        results[res["file"]] = res["diagnostics"]
                except Exception as exc:
                    logger.exception("Diagnostic worker failed: %s", exc)

        duration_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "status": "ok",
            "request_id": request_id,
            "files": results,
            "scan_duration_ms": round(duration_ms, 2),
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
        }
```

---

### 2.4 Phase 4: Zero-Dependency Python AST Linter (`ast_linter.py`)

Using Python's built-in `ast.NodeVisitor`, we inspect variable scopes, imports, and definitions without executing code.

```python
import ast
from deskai.diagnostics.models import Diagnostic

class ASTLinter(ast.NodeVisitor):
    def __init__(self, rel_path: str):
        self.rel_path = rel_path
        self.diagnostics: list[Diagnostic] = []
        self._scopes: list[dict[str, tuple[int, int]]] = [{}]  # var_name -> (line, col)
        self._used: list[set[str]] = [set()]

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scopes.append({})
        self._used.append(set())
        self.generic_visit(node)
        
        # Check unused local variables on function exit
        scope = self._scopes.pop()
        used = self._used.pop()
        for var_name, (line, col) in scope.items():
            if var_name not in used and not var_name.startswith("_"):
                self.diagnostics.append(
                    Diagnostic(
                        source="ast_lint",
                        code="W001_UNUSED_VAR",
                        severity="warning",
                        message=f"Local variable '{var_name}' is assigned but never used",
                        file=self.rel_path,
                        start_line=line,
                        start_col=col,
                        end_line=line,
                        end_col=col + len(var_name),
                        ai_fixable=True,
                    )
                )

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store):
            self._scopes[-1][node.id] = (node.lineno, node.col_offset + 1)
        elif isinstance(node.ctx, ast.Load):
            for used_set in self._used:
                used_set.add(node.id)
        self.generic_visit(node)
```

---

### 2.5 Phase 5: Zero-Dependency Language Parsers

#### 1. TOML Syntax Checker (`toml_syntax.py` - Built-in Python 3.11+ `tomllib`)
```python
import tomllib
from deskai.diagnostics.models import Diagnostic, clean_text

def check_toml(source: str, rel_path: str) -> list[Diagnostic]:
    try:
        tomllib.loads(source)
        return []
    except tomllib.TOMLDecodeError as exc:
        # tomllib messages often include line and col in text
        return [
            Diagnostic(
                source="toml",
                code="TOMLDecodeError",
                severity="error",
                message=clean_text(str(exc)),
                file=rel_path,
                start_line=getattr(exc, "lineno", 1),
                start_col=getattr(exc, "colno", 1),
                end_line=getattr(exc, "lineno", 1),
                end_col=getattr(exc, "colno", 1) + 1,
                ai_fixable=True,
            )
        ]
```

#### 2. HTML Validator (`html_syntax.py` - Built-in `html.parser.HTMLParser`)
```python
from html.parser import HTMLParser
from deskai.diagnostics.models import Diagnostic

class StrictHTMLParser(HTMLParser):
    def __init__(self, rel_path: str):
        super().__init__()
        self.rel_path = rel_path
        self.stack: list[tuple[str, int, int]] = []
        self.diagnostics: list[Diagnostic] = []

    def handle_starttag(self, tag: str, attrs):
        if tag not in {"br", "img", "input", "hr", "meta", "link"}:
            line, col = self.getpos()
            self.stack.append((tag, line, col + 1))

    def handle_endtag(self, tag: str):
        if not self.stack:
            line, col = self.getpos()
            self.diagnostics.append(
                Diagnostic("html", "UNMATCHED_TAG", "warning", f"Unmatched closing tag </{tag}>", self.rel_path, line, col + 1, line, col + len(tag) + 3)
            )
        elif self.stack[-1][0] == tag:
            self.stack.pop()
```

---

## 3. Frontend Architecture

### 3.1 Phase 2: "Fix with AI" & "Explain" Actions (`view.js`)

In `renderItem(item, manager)`:
```javascript
// Render Action Button Group
const actionGroup = document.createElement("div");
actionGroup.className = "problem-item-actions";

if (item.aiFixable !== false) {
  const fixBtn = document.createElement("button");
  fixBtn.type = "button";
  fixBtn.className = "problem-action-btn problem-btn-ai-fix";
  fixBtn.title = "Fix this error automatically using DeskAI Assistant";
  fixBtn.setAttribute("aria-label", `Fix error in ${item.file} line ${item.range.startLine} with AI`);
  fixBtn.innerHTML = `<span>✨ Fix</span>`;
  fixBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    manager.triggerAiFix(item);
  });
  actionGroup.appendChild(fixBtn);
}

const explainBtn = document.createElement("button");
explainBtn.type = "button";
explainBtn.className = "problem-action-btn problem-btn-explain";
explainBtn.title = "Explain why this error occurred";
explainBtn.innerHTML = `<span>💡 Explain</span>`;
explainBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  manager.triggerAiExplain(item);
});
actionGroup.appendChild(explainBtn);
itemEl.appendChild(actionGroup);
```

#### Manager Dispatch Integration (`index.js`):
```javascript
triggerAiFix(item) {
  const prompt = `Fix the following ${item.severity} in \`${item.file}\` at line ${item.range.startLine}, col ${item.range.startCol}:\nError: ${item.message} (${item.source} ${item.code || ""})\nPlease provide the surgical patch diff to resolve this issue.`;
  if (window.UEC && typeof window.UEC.submitPrompt === "function") {
    window.UEC.submitPrompt(prompt);
  } else {
    const textarea = document.getElementById("promptTextarea");
    if (textarea) {
      textarea.value = prompt;
      textarea.focus();
    }
  }
}
```

---

### 3.2 Phase 3: CodeMirror 6 In-Editor Wavy Squiggles (`editor_decorations.js`)

CodeMirror 6 uses immutable `StateField` and `Decoration.mark` to overlay wavy underlines on token ranges.

```javascript
/**
 * Creates CodeMirror 6 StateField decoration for workspace diagnostics.
 */
export function createDiagnosticSquigglePlugin(diagnosticsStore, activeFilePath) {
  const { StateField, StateEffect, Decoration, hoverTooltip } = window.CodeMirror;

  const setDiagnosticsEffect = StateEffect.define();

  const diagnosticField = StateField.define({
    create() {
      return Decoration.none;
    },
    update(underlines, tr) {
      underlines = underlines.map(tr.changes);
      for (const e of tr.effects) {
        if (e.is(setDiagnosticsEffect)) {
          underlines = e.value;
        }
      }
      return underlines;
    },
    provide: (f) => window.CodeMirror.EditorView.decorations.from(f),
  });

  const tooltipPlugin = hoverTooltip((view, pos) => {
    const diags = diagnosticsStore.forFile(activeFilePath);
    for (const d of diags) {
      const line = view.state.doc.line(d.range.startLine);
      const from = line.from + d.range.startCol - 1;
      const to = Math.max(from + 1, line.from + d.range.endCol - 1);
      if (pos >= from && pos <= to) {
        return {
          pos: from,
          end: to,
          above: true,
          create() {
            const dom = document.createElement("div");
            dom.className = "cm-diagnostic-tooltip";
            dom.textContent = `${d.severity === "error" ? "🔴" : "⚠️"} ${d.message}`;
            return { dom };
          },
        };
      }
    }
    return null;
  });

  return [diagnosticField, tooltipPlugin];
}
```

---

### 3.3 Phase 6: Status Bar Diagnostics Widget (`status_bar.js`)

```javascript
export class StatusBarDiagnosticsWidget {
  constructor(containerEl, store) {
    this.el = containerEl;
    this.store = store;
    this.render();
    this.store.subscribe(() => this.render());
  }

  render() {
    const counts = this.store.counts();
    this.el.replaceChildren();

    const pill = document.createElement("button");
    pill.type = "button";
    pill.className = "status-bar-pill status-bar-diagnostics";
    pill.setAttribute("aria-label", `Problems: ${counts.errors} errors, ${counts.warnings} warnings. Click to open.`);
    
    if (counts.errors === 0 && counts.warnings === 0) {
      pill.classList.add("status-clean");
      pill.textContent = "✔ 0 Problems";
    } else {
      if (counts.errors > 0) pill.classList.add("has-errors");
      pill.textContent = `✖ ${counts.errors}  ▲ ${counts.warnings}`;
    }

    pill.addEventListener("click", () => {
      const tab = document.getElementById("tab-problems");
      if (tab) tab.click();
    });

    this.el.appendChild(pill);
  }
}
```

---

## 4. CSS Tokens & Visual Styling (`components.css`)

```css
/* Phase 3: CodeMirror Wavy Squiggles */
.cm-diagnostic-squiggle-error {
  text-decoration-line: underline;
  text-decoration-style: wavy;
  text-decoration-color: var(--color-danger, #ff6b6b);
  text-decoration-thickness: 1.5px;
  text-underline-offset: 3px;
}

.cm-diagnostic-squiggle-warning {
  text-decoration-line: underline;
  text-decoration-style: wavy;
  text-decoration-color: var(--color-warning, #f59e0b);
  text-decoration-thickness: 1.5px;
  text-underline-offset: 3px;
}

/* Floating Hover Tooltip */
.cm-diagnostic-tooltip {
  background: var(--bg-card, #202126);
  border: 1px solid var(--border-subtle, #333640);
  border-radius: var(--radius-sm, 4px);
  padding: 6px 10px;
  font-size: var(--text-xs, 12px);
  color: var(--text-primary, #ededed);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
  max-width: 380px;
  line-height: 1.4;
  z-index: 1000;
}

/* Phase 2: Action Buttons */
.problem-item-actions {
  display: inline-flex;
  gap: 6px;
  margin-left: auto;
  opacity: 0;
  transition: opacity 120ms ease;
}

.problem-item:hover .problem-item-actions,
.problem-item:focus-within .problem-item-actions {
  opacity: 1;
}

.problem-action-btn {
  background: var(--bg-surface, #1a1b1f);
  border: 1px solid var(--border-subtle, #333640);
  border-radius: var(--radius-xs, 3px);
  padding: 2px 7px;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-secondary, #9ca0a6);
  cursor: pointer;
}

.problem-action-btn:hover {
  background: var(--color-primary-muted, rgba(217, 155, 38, 0.2));
  color: var(--color-primary, #d99b26);
  border-color: var(--color-primary, #d99b26);
}

/* Phase 6: Status Bar Widget */
.status-bar-diagnostics {
  background: transparent;
  border: none;
  color: var(--text-secondary, #9ca0a6);
  font-family: var(--font-mono, monospace);
  font-size: 11px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 3px;
}

.status-bar-diagnostics.has-errors {
  color: var(--color-danger, #ff6b6b);
  font-weight: 600;
}
```

---

## 5. Traceability & Test Plan Matrix

| Test ID | Phase | Target | Test Specification |
| :--- | :--- | :--- | :--- |
| **TC-PRB-36** | Phase 1 | Warm Cache Benchmark | Scan a 200-file project twice; assert 2nd scan completes in **< 3ms** and `cache_hits == 200`. |
| **TC-PRB-37** | Phase 1 | Cache Invalidation | Edit `foo.py`; assert 3rd scan reports `cache_misses == 1` and `cache_hits == 199`. |
| **TC-PRB-38** | Phase 1 | ThreadPool Parallelism | Cold scan with 100 broken files completes in < 150ms on multi-core machine. |
| **TC-PRB-39** | Phase 2 | "Fix with AI" Button | Clicking `[✨ Fix]` triggers `submitPrompt` with formatted diagnostic info. |
| **TC-PRB-40** | Phase 2 | "Explain" Button | Clicking `[💡 Explain]` populates textarea with plain-English explanation prompt. |
| **TC-PRB-41** | Phase 3 | In-Editor Squiggles | Opening file with syntax error places `.cm-diagnostic-squiggle-error` on token range. |
| **TC-PRB-42** | Phase 3 | Hover Tooltip | Hovering over squiggled token instantiates `.cm-diagnostic-tooltip` containing message. |
| **TC-PRB-43** | Phase 4 | AST Warnings | Python file with unused variable displays `Warnings 1` badge and `W001_UNUSED_VAR`. |
| **TC-PRB-44** | Phase 5 | TOML/HTML/XML Checkers | Malformed `.toml`, `.html`, and `.xml` files produce valid line/column diagnostics. |
| **TC-PRB-45** | Phase 6 | Status Bar Widget | Status bar widget accurately reflects `✖ errors ▲ warnings` and toggles tab on click. |
