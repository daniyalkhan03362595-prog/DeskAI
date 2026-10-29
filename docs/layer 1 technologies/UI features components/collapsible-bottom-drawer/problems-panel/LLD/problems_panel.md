# Low-Level Design (LLD): Problems Panel (Workspace Diagnostics)

**Document ID:** `ORX-LLD-PROBLEMS-PANEL-V2`  
**Version:** `2.0` (supersedes `ORX-LLD-PROBLEMS-PANEL-V1`)  
**Parent Document:** `ORX-HLD-PROBLEMS-PANEL-V2`  
**Target Codebase:** `DeskAI` (verified against `main` @ `b0170b0`)  
**Status:** Proposed (ready for implementation)  
**Date:** October 29, 2026  

---

## 1. File Map

| File | Action | Purpose |
| :--- | :--- | :--- |
| `src/deskai/diagnostics/__init__.py` | NEW | Public API: `run_checks(path, root, options)` |
| `src/deskai/diagnostics/models.py` | NEW | `Diagnostic` dataclass, severity enum, fingerprint, sanitiser |
| `src/deskai/diagnostics/runner.py` | NEW | Dispatch by file type, time/size caps, subprocess helper |
| `src/deskai/diagnostics/python_syntax.py` | NEW | `ast.parse` checker (built in) |
| `src/deskai/diagnostics/json_syntax.py` | NEW | `json.loads` checker (built in) |
| `src/deskai/diagnostics/flake8_checker.py` | NEW | Optional isolated flake8 (P2) |
| `src/deskai/bridge/diagnostics.py` | NEW | `DiagnosticsBridge(BaseBridgeModule)` |
| `src/deskai/bridge/api.py` | MODIFY | Add `DiagnosticsBridge` to `DesktopBridgeAPI` bases |
| `src/deskai/static/js/problems/store.js` | NEW | `DiagnosticsStore` (replace-sets, counts, subscribe) |
| `src/deskai/static/js/problems/view.js` | NEW | Safe DOM rendering, keyboard model |
| `src/deskai/static/js/problems/index.js` | NEW | `ProblemsManager` (triggers, debounce, stale guards) exposed as `window.DeskAIProblems` |
| `src/deskai/static/js/bridge.js` | MODIFY | `runDiagnostics()`, `runWorkspaceDiagnostics()` |
| `src/deskai/static/js/editor.js` | MODIFY | `openAt()`, `revealPosition()`, save hook |
| `src/deskai/static/js/app.js` | MODIFY | Create manager, `window.DeskAIProblems = problems` |
| `src/deskai/static/js/state.js` | MODIFY | `diagnostics` slice (counts + status) |
| `src/deskai/static/js/events.js` | MODIFY | `drawer-tab` hook, toolbar `data-action`s |
| `src/deskai/static/index.html` | MODIFY | Panel markup, tab badge |
| `src/deskai/static/css/components.css`, `tokens.css` | MODIFY | Styles, `--color-info*` tokens |
| `tools/check_contrast.py` | MODIFY | Add info/danger/warning pairs |
| `tests/test_problems_*.py` | NEW | See section 10 |

---

## 2. Backend

### 2.1 `models.py`

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
    severity: str           # one of SEVERITIES
    message: str
    file: str               # workspace-relative, forward slashes
    start_line: int
    start_col: int
    end_line: int
    end_col: int

    @property
    def id(self) -> str:
        raw = f"{self.source}|{self.code}|{self.file}|{self.start_line}|{self.start_col}|{self.message}"
        return hashlib.sha1(raw.encode("utf-8", "replace")).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "id": self.id, "source": self.source, "code": self.code, "severity": self.severity,
            "message": self.message, "file": self.file,
            "range": {"startLine": self.start_line, "startCol": self.start_col,
                      "endLine": self.end_line, "endCol": self.end_col},
        }
```

Rules: lines and columns are **1-based**; `end_*` falls back to `start_*` (or `start_col + 1`) when the tool gives none; values are clamped to `>= 1`.

### 2.2 `python_syntax.py`

```python
import ast

def check_python(source: str, rel_path: str) -> list[Diagnostic]:
    try:
        ast.parse(source, filename=rel_path, type_comments=False)
        return []
    except SyntaxError as exc:             # includes IndentationError / TabError
        line = max(exc.lineno or 1, 1)
        col = max(exc.offset or 1, 1)
        end_line = max(getattr(exc, "end_lineno", None) or line, line)
        end_col = max(getattr(exc, "end_offset", None) or col + 1, 1)
        return [Diagnostic("python", exc.__class__.__name__, "error", clean_text(exc.msg or "Invalid syntax"),
                           rel_path, line, col, end_line, end_col)]
    except (RecursionError, MemoryError):
        return [Diagnostic("python", "E_COMPLEXITY", "error",
                           "File is too deeply nested or too large to analyse", rel_path, 1, 1, 1, 2)]
    except ValueError:                      # e.g. source contains null bytes
        return [Diagnostic("python", "E_VALUE", "error", "File contains invalid characters", rel_path, 1, 1, 1, 2)]
```

`ast.parse` never executes the code. The error offset can point past the end of a line for some errors; the frontend clamps cursor placement to the line length.

### 2.3 `json_syntax.py`

`json.loads(source)`; on `json.JSONDecodeError e` -> one `error` with `code="JSON"`, `line=e.lineno`, `col=e.colno`, `message=e.msg`. Files named `*.jsonc` or `tsconfig*.json` are **skipped** (comments allowed) to avoid false errors.

### 2.4 `flake8_checker.py` (Phase 2, optional)

```python
FLAKE8_ARGS = [
    sys.executable, "-m", "flake8", "--isolated",            # S2: ignore workspace config (no local plugins)
    "--max-line-length=120",
    "--format=%(row)d\t%(col)d\t%(code)s\t%(text)s",
    "--", abs_path,
]
```

* Availability probe: `importlib.util.find_spec("flake8")`; if missing, return `warnings=["flake8_unavailable"]` (not an error).
* Run through `runner.run_subprocess()` (section 2.5). Parse each stdout line by splitting on `\t` (maxsplit 3); ignore malformed lines.
* Severity map: codes starting `E9`, `F63`, `F7`, `F82` -> `error`; `C9` -> `info`; everything else -> `warning`.
* Do **not** pass `--config`, `--append-config`, or `--enable-extensions` from workspace files.

### 2.5 `runner.py`

```python
MAX_FILE_BYTES = 1_048_576          # skip larger files (warning "file_too_large")
MAX_DIAGNOSTICS_PER_FILE = 500
CHECK_TIMEOUT_S = 10.0
MAX_OUTPUT_BYTES = 1_048_576

CHECKERS_BY_EXT = {".py": ["python"], ".pyw": ["python"], ".json": ["json"]}   # + "flake8" for .py when enabled


def run_subprocess(argv, cwd, env, timeout=CHECK_TIMEOUT_S) -> tuple[int | None, str, bool]:
    """Return (returncode, stdout, timed_out). shell=False, stdin=DEVNULL, output capped, tree killed on timeout."""
    kwargs = dict(stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=cwd, env=env)
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True            # own process group so killpg works
    proc = subprocess.Popen(argv, **kwargs)
    try:
        out, _ = proc.communicate(timeout=timeout)
        return proc.returncode, out[:MAX_OUTPUT_BYTES].decode("utf-8", "replace"), False
    except subprocess.TimeoutExpired:
        _kill_tree(proc)                              # os.killpg(SIGKILL) on POSIX, taskkill /T /F on Windows
        proc.communicate()
        return None, "", True
```

`env` is built from `build_terminal_env()` (already strips `DESKAI_*` and `*TOKEN*`).

`run_checks(abs_path, root, options)` flow:
1. Compute `rel = os.path.relpath(abs_path, root).replace(os.sep, "/")`.
2. Skip with warning if not a regular file, `size > MAX_FILE_BYTES`, or the extension has no checker (`status: ok`, empty list, warning `no_checker`).
3. Read bytes, reject if `b"\x00"` in the first 8 KB for text checkers; decode `utf-8` with `errors="replace"`.
4. Run each enabled checker; collect `Diagnostic`s; **sort** by `(start_line, start_col, source)`; **dedupe** by `id`; truncate to `MAX_DIAGNOSTICS_PER_FILE` and set `truncated=True`.

### 2.6 `bridge/diagnostics.py`

```python
class DiagnosticsBridge(BaseBridgeModule):
    _diag_semaphore = threading.BoundedSemaphore(3)          # S7: max 3 concurrent checks

    def _is_safe_path(self, target_path: str) -> bool:        # same helper as GitBridge / WorkspaceFSBridge
        return is_safe_workspace_path(target_path, self.workspace_root)

    def run_diagnostics(self, target_path: str, request_id: str = "") -> dict:
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin", "request_id": request_id, "diagnostics": []}
        if not self.workspace_root or not self._is_safe_path(target_path):
            return {"status": "error", "message": "Access denied: Path outside workspace",
                    "request_id": request_id, "diagnostics": []}
        if not self._diag_semaphore.acquire(blocking=False):
            return {"status": "error", "message": "Busy", "request_id": request_id, "diagnostics": []}
        try:
            return run_checks(canonicalize_path(target_path), self.workspace_root, request_id=request_id)
        except Exception:                                     # never raise into the page
            logger.exception("diagnostics failed")
            return {"status": "error", "message": "Diagnostics failed", "request_id": request_id, "diagnostics": []}
        finally:
            self._diag_semaphore.release()

    def run_workspace_diagnostics(self, request_id: str = "", limit: int = 200) -> dict:
        ...  # walk workspace_root, skip .git, node_modules, .venv, venv, __pycache__, dist, build; do not follow symlinks;
             # at most `limit` files; each file via the same path as run_diagnostics; return {file: [diagnostics]}
```

Add the class to `DesktopBridgeAPI` bases **before** `BaseBridgeModule`. `workspace_root` is the shared attribute already set by `set_workspace_root`/`select_folder`.

### 2.7 Bridge response schema

```json
{
  "status": "ok",
  "request_id": "r-17",
  "file": "src/app.py",
  "diagnostics": [
    {"id": "9f2c1d0a4b7e3a11", "source": "python", "code": "SyntaxError", "severity": "error",
     "message": "invalid syntax", "file": "src/app.py",
     "range": {"startLine": 41, "startCol": 9, "endLine": 41, "endCol": 10}}
  ],
  "truncated": false,
  "warnings": ["flake8_unavailable"]
}
```

Error codes returned in `message`: `Unauthorized origin`, `Access denied: Path outside workspace`, `Busy`, `Diagnostics failed`. Warnings: `no_checker`, `file_too_large`, `binary_file`, `flake8_unavailable`, `checker_timeout:<name>`.

---

## 3. Frontend

### 3.1 `bridge.js` additions (same pattern as `probePort` / `getGitBranch`)

```javascript
async runDiagnostics(filePath, requestId) {
  await this.whenReady();
  if (window.pywebview && window.pywebview.api && window.pywebview.api.run_diagnostics) {
    return await window.pywebview.api.run_diagnostics(filePath, String(requestId));
  }
  return { status: "error", message: "Bridge unavailable", request_id: String(requestId), diagnostics: [] };
},
async runWorkspaceDiagnostics(requestId) {
  await this.whenReady();
  if (window.pywebview && window.pywebview.api && window.pywebview.api.run_workspace_diagnostics) {
    return await window.pywebview.api.run_workspace_diagnostics(String(requestId));
  }
  return { status: "error", message: "Bridge unavailable", request_id: String(requestId), diagnostics: [] };
},
```

The fallback object keeps browser smoke tests (no PyWebView bridge) free of console errors.

### 3.2 `state.js` slice (counts only)

```javascript
diagnostics: { errors: 0, warnings: 0, infos: 0, status: "idle", checkedAt: null }
// status: "idle" | "checking" | "done" | "unavailable"
```

### 3.3 `problems/store.js`

```javascript
export class DiagnosticsStore {
  constructor() { this._bySourceFile = new Map(); this._listeners = new Set(); this._version = 0; }
  static key(path) {                       // single normaliser (Windows: case-insensitive, slashes)
    const p = String(path).replace(/\\/g, "/");
    return navigator.platform.startsWith("Win") ? p.toLowerCase() : p;
  }
  replace(source, file, items) {           // replace-set semantics (HLD D3)
    const k = `${source}\u0000${DiagnosticsStore.key(file)}`;
    if (items.length === 0) this._bySourceFile.delete(k); else this._bySourceFile.set(k, { source, file, items });
    this._emit();
  }
  clearFile(file) { /* delete all keys whose file matches */ this._emit(); }
  clearAll() { this._bySourceFile.clear(); this._emit(); }
  counts() { /* iterate once: { errors, warnings, infos } */ }
  grouped(filter) { /* Map<file, Diagnostic[]> sorted by file then line/col, filter by severity set + text */ }
  signature() { return this._version; }    // increments only when content actually changes
  subscribe(fn) { this._listeners.add(fn); return () => this._listeners.delete(fn); }
  _emit() { this._version++; this._listeners.forEach((fn) => fn()); }
}
```

### 3.4 `problems/index.js` (`ProblemsManager`)

Responsibilities and exact behaviour:

| Trigger | Handler | Behaviour |
| :--- | :--- | :--- |
| `EditorManager.saveBuffer` success | `onFileSaved(path)` | Ignore if `path` outside `store.state.workspace.rootPath`; per-file debounce 300 ms; call `_check(path)` |
| Toolbar "Run checks" (`data-action="problems-run"`) | `runWorkspace()` | `runWorkspaceDiagnostics`, replace each file's set |
| `store.subscribe("workspace.rootPath")` | `reset()` | `generation++`, `clearAll()`, status `idle`, cancel timers |
| Explorer delete/rename | `onPathRemoved(path)` | `clearFile(path)` (rename: clear old key only; new path is checked on next save) |
| Drawer tab activated | `onShow()` | Re-render only if the store signature changed |

```javascript
async _check(path) {
  const gen = this.generation;
  const reqId = ++this._reqSeq;
  this._latest.set(DiagnosticsStore.key(path), reqId);       // latest request per file wins
  store.state.diagnostics.status = "checking";
  const res = await NativeBridge.runDiagnostics(path, reqId);
  if (gen !== this.generation) return;                        // workspace changed: drop
  if (this._latest.get(DiagnosticsStore.key(path)) !== reqId) return;   // superseded: drop
  if (res.status !== "ok") { this._setUnavailable(res); return; }
  for (const source of this._sourcesOf(res)) this.store.replace(source, res.file, res.diagnostics.filter((d) => d.source === source));
  this._syncCounts();                                         // writes store.state.diagnostics.{errors,warnings,infos}
  this._announce();                                           // debounced 500 ms
}
```

`_sourcesOf(res)` returns the union of sources present **and** the sources previously stored for that file, so a source that now reports nothing clears its old items.

### 3.5 `index.html` markup (replaces the stub, keeps `.problems-empty` and existing ARIA)

```html
<div class="drawer-panel" id="problemsPanel" role="tabpanel" aria-labelledby="tab-problems" tabindex="0" hidden>
  <div class="problems-toolbar" role="toolbar" aria-label="Problems filters and actions">
    <button type="button" class="problems-filter" data-action="problems-filter" data-severity="error" aria-pressed="true">
      <span class="problems-filter-label">Errors</span> <span class="problems-filter-count" id="problemsErrCount">0</span>
    </button>
    <button type="button" class="problems-filter" data-action="problems-filter" data-severity="warning" aria-pressed="true">
      <span class="problems-filter-label">Warnings</span> <span class="problems-filter-count" id="problemsWarnCount">0</span>
    </button>
    <button type="button" class="problems-filter" data-action="problems-filter" data-severity="info" aria-pressed="true">
      <span class="problems-filter-label">Info</span> <span class="problems-filter-count" id="problemsInfoCount">0</span>
    </button>
    <label class="sr-only" for="problemsFilterInput">Filter problems</label>
    <input type="text" id="problemsFilterInput" class="problems-filter-input" placeholder="Filter problems" autocomplete="off" />
    <button type="button" class="icon-btn" data-action="problems-collapse" aria-label="Collapse all files"></button>
    <button type="button" class="icon-btn" data-action="problems-run" id="problemsRunBtn" aria-label="Run checks"></button>
  </div>
  <div class="problems-notice" id="problemsNotice" role="status" hidden></div>
  <div class="problems-view" id="problemsView">
    <span class="problems-empty">No problems have been detected in the workspace.</span>
  </div>
</div>
```

Tab badge inside `#tab-problems`: `<span class="tab-badge" id="problemsTabBadge" hidden></span>`, and `aria-label` of the tab button updated by `_syncCounts()` (`Problems, 2 errors, 3 warnings`). The toolbar's icon buttons receive SVG icons from `createSvgIcon()` in `icons.js` (no emoji). Use `data-action` names above in the `events.js` switch; they call `window.DeskAIProblems`.

### 3.6 `problems/view.js` (safe rendering, no `innerHTML`)

```javascript
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function renderGroups(container, grouped, ui) {
  const frag = document.createDocumentFragment();
  for (const [file, items] of grouped) {
    const group = el("div", "problems-group");
    const head = el("button", "problems-file");
    head.type = "button";
    head.setAttribute("aria-expanded", String(!ui.collapsed.has(file)));
    head.setAttribute("aria-controls", `pg-${ui.idFor(file)}`);
    head.dataset.file = file;
    head.append(el("span", "problems-file-name", file), el("span", "problems-file-count", String(items.length)));
    const list = el("ul", "problems-list"); list.id = `pg-${ui.idFor(file)}`; list.hidden = ui.collapsed.has(file);
    for (const d of items) list.append(renderItem(d));
    group.append(head, list); frag.append(group);
  }
  container.replaceChildren(frag);                      // single DOM write
}

function renderItem(d) {
  const li = el("li", "problems-row"); li.setAttribute("role", "listitem");
  const btn = el("button", `problem-item severity-${d.severity}`);
  btn.type = "button"; btn.tabIndex = -1;
  btn.dataset.id = d.id; btn.dataset.file = d.file;
  btn.dataset.line = String(d.range.startLine); btn.dataset.col = String(d.range.startCol);
  btn.setAttribute("aria-label",
    `${LABEL[d.severity]}, ${d.message}, ${d.file} line ${d.range.startLine} column ${d.range.startCol}, source ${d.source}`);
  btn.append(severityIcon(d.severity), el("span", "problem-severity", LABEL[d.severity]),
             el("span", "problem-message", d.message),
             el("span", "problem-source", d.code ? `${d.source} ${d.code}` : d.source),
             el("span", "problem-location", `[${d.range.startLine}, ${d.range.startCol}]`));
  li.append(btn); return li;
}
```

`severityIcon(sev)` builds an SVG with `createElementNS` and `aria-hidden="true"`: **error = filled octagon/cross, warning = triangle, info = circle with "i"** (distinct shapes, `fill="currentColor"`).

**Keyboard model (roving tabindex):** one item has `tabIndex=0`; `ArrowUp/Down` move across visible items and group headers; `ArrowLeft` on an item focuses its group header, on a header collapses; `ArrowRight` on a header expands; `Home/End` first/last; `Enter`/`Space` activates; `Escape` focuses `#tab-problems`. After a re-render restore focus by `data-id` (fall back to the group header, then the toolbar).

### 3.7 `editor.js` additions

```javascript
async openAt(filePath, line, col) {
  const id = await this.openFile(filePath);           // existing; selects the tab if already open
  if (!id) return false;
  this.revealPosition(id, line, col);
  return true;
}

revealPosition(id, line, col) {
  const buffer = this.buffers.get(id);
  if (!buffer || !buffer.view) return;
  const doc = buffer.view.state.doc;
  const ln = Math.min(Math.max(line, 1), doc.lines);
  const info = doc.line(ln);
  const pos = info.from + Math.min(Math.max(col - 1, 0), info.length);
  buffer.view.dispatch({ selection: { anchor: pos }, scrollIntoView: true });
  buffer.view.focus();
}
```

Hook in `saveBuffer`: after `this.markDirty(id, false)` call `window.DeskAIProblems?.onFileSaved(buffer.path)`. `openFile` receives the **absolute** path, so the panel builds it as `join(workspaceRoot, relFile)` (use `/` and let the backend canonicalise).

### 3.8 `events.js`

In `case "drawer-tab"` add: `if (target === "problems" && window.DeskAIProblems) window.DeskAIProblems.onShow();`. Add cases `problems-run`, `problems-collapse`, `problems-filter` (toggle `aria-pressed`, update filter set, re-render). Keep the existing delegation guards.

---

## 4. CSS & Tokens

New tokens in `tokens.css` (dark under `:root`, light under the existing light-theme blocks):

```css
--color-info: #7aa2f7;            /* verify >= 4.5:1 on --bg-card / --bg-surface */
--color-info-subtle: rgba(122, 162, 247, 0.12);
/* light theme */
--color-info: #1d4ed8;
--color-info-subtle: rgba(29, 78, 216, 0.12);
```

(The hex values above are starting points. They must be adjusted until `python tools/check_contrast.py` passes for every new pair. Raw colours are allowed **only** in `tokens.css`.)

Add to `PAIRS_TO_CHECK`: `("color-danger","bg-card",4.5,"Text","Problem error label")`, `("color-warning","bg-card",4.5,...)`, `("color-info","bg-card",4.5,...)`, and the same three at `3.0` for icons.

```css
.problems-toolbar { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-1-5) var(--space-3);
  border-bottom: 1px solid var(--border-subtle); flex-wrap: nowrap; overflow: hidden; }
.problems-filter { min-height: 28px; padding: 0 var(--space-2); border: 1px solid var(--border-regular);
  border-radius: var(--radius-sm, 4px); background: transparent; color: var(--text-secondary); font: inherit; font-size: var(--text-xs); }
.problems-filter[aria-pressed="true"] { background: var(--bg-hover); color: var(--text-primary); border-color: var(--border-focus); }
.problems-filter-input { flex: 1; min-width: 80px; min-height: 28px; font: inherit; font-size: var(--text-xs); }
.problems-view { flex: 1; overflow-y: auto; padding: var(--space-1) 0; }             /* replaces V1 padding rule */
.problems-file { display: flex; width: 100%; min-height: 28px; align-items: center; gap: var(--space-2);
  padding: 0 var(--space-3); background: transparent; border: 0; color: var(--text-primary); font: inherit; font-size: var(--text-xs); text-align: left; }
.problem-item { display: grid; grid-template-columns: 16px auto 1fr auto auto; align-items: center; gap: var(--space-2);
  width: 100%; min-height: 28px; padding: 0 var(--space-3) 0 var(--space-6); background: transparent; border: 0;
  color: var(--text-secondary); font: inherit; font-size: var(--text-xs); text-align: left; }
.problem-item:hover { background: var(--bg-hover); }
.problem-item:focus-visible, .problems-file:focus-visible { outline: 2px solid var(--border-focus); outline-offset: -2px; }
.severity-error .problem-severity, .severity-error svg { color: var(--color-danger); }
.severity-warning .problem-severity, .severity-warning svg { color: var(--color-warning); }
.severity-info .problem-severity, .severity-info svg { color: var(--color-info); }
.problem-message { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-primary); }
.problem-source, .problem-location { color: var(--text-muted); font-family: var(--font-mono); white-space: nowrap; }
.problems-notice { padding: var(--space-1-5) var(--space-3); color: var(--text-secondary); font-size: var(--text-xs); }
.tab-badge { margin-left: var(--space-1-5); padding: 0 var(--space-1-5); border-radius: 8px; font-size: var(--text-xs); }
[data-busy="true"] .icon-btn svg { animation: problems-spin 1s linear infinite; }
@keyframes problems-spin { to { transform: rotate(360deg); } }   /* no spin keyframes exist yet in animations.css; add this there */
@media (prefers-reduced-motion: reduce) { [data-busy="true"] .icon-btn svg { animation: none; } }
```

Layout-shift rules: the toolbar has a fixed height; the notice area reserves no space when hidden (use `hidden`, and place it **above the list inside the scroll area** so showing it does not move the toolbar); count badges use `min-width` for 3 digits; the list keeps its previous content while `Checking`.

Narrow widths (<560 px panel width): the filter input hides its placeholder, counts remain; the `problem-source` column is hidden with a container query; the message ellipsizes (full text in `title` and in the accessible name).

---

## 5. Accessibility Contract (testable)

| Requirement | Implementation | Test |
| :--- | :--- | :--- |
| Tab semantics unchanged | `role="tab"`, `aria-controls="problemsPanel"` | TC-PRB-06 |
| Tab badge name | `aria-label` on `#tab-problems` updated with counts | TC-PRB-18 |
| Severity not by colour | Icon shape + visible label | TC-PRB-14 |
| One Tab stop for the list | roving `tabindex` | TC-PRB-15 |
| Arrow key model | see 3.6 | TC-PRB-15 |
| Live region summary only | `#screenReaderAnnouncer`, 500 ms debounce | TC-PRB-16 |
| Focus survives re-render | restore by `data-id` | TC-PRB-17 |
| Names on all controls | `aria-label` / `<label>` | existing a11y scan |
| Min target 28 px, text >= 12 px | CSS | size scan test |
| Contrast both themes | `check_contrast.py` pairs | CI lint job |

---

## 6. Edge Cases

| Case | Expected behaviour |
| :--- | :--- |
| Save during an in-flight check | New request supersedes; the old response is dropped (`requestId`) |
| Workspace switched mid-check | Result dropped (`generation`) |
| File deleted/renamed after save | Backend returns `File not found`; panel clears that file |
| File > 1 MB or contains NUL | Skipped, warning notice, no crash |
| Non-UTF-8 bytes | Decoded with replacement; checks still run |
| CRLF files / tabs | Columns are character offsets as reported by the tool; cursor placement is clamped to the line |
| Syntax error beyond last line | Line clamped to `doc.lines` |
| Symlink pointing outside workspace | Rejected by `_is_safe_path` |
| Sensitive dirs (`~/.ssh`) under an ancestor workspace | Rejected by the sandbox (same rule as `read_file`) |
| Checker timeout | Process tree killed, warning `checker_timeout:flake8`, built-in results still shown |
| flake8 not installed | Inline notice, built-in checks only |
| 2000+ diagnostics | Capped at 500 per file, `truncated` notice, render cap 1000 |
| Windows paths (`C:\..`, mixed case) | `DiagnosticsStore.key()` normalises; backend returns forward-slash relative paths |
| Browser smoke test (no bridge) | `runDiagnostics` returns `{status:"error"}`; panel stays in Empty state, no console errors |

---

## 7. Observability

Backend logs one line per check at `DEBUG` (`file`, `checkers`, `duration_ms`, `count`) via the `logging` module; never logs file contents. Frontend does not log diagnostics messages to the console in production.

---

## 8. Backward Compatibility

* `#problemsPanel`, `.problems-view`, `.problems-empty` and the empty-state text are unchanged, so **TC-PRB-01 to TC-PRB-06 keep passing**.
* The V1 CSS rule for `.problems-view` (padding, italics) is replaced; `.problems-empty` keeps its look.

---

## 9. Implementation Order

1. Backend `models.py`, `python_syntax.py`, `json_syntax.py`, `runner.py` + unit tests.
2. `DiagnosticsBridge` + facade wiring + path/origin tests.
3. Frontend store + manager + view + markup/CSS/tokens + contrast tool update.
4. Editor `openAt` + save hook + navigation tests.
5. A11y/keyboard tests, real-server Playwright tests, Windows-mocked tests.
6. P2 (flake8, workspace scan, squiggles) as separate commits.

**Definition of Done:** black (`--line-length 120`) and flake8 clean; `python -m unittest discover -s tests` green on Ubuntu and Windows x 3.11/3.12; zero `innerHTML` in new files (the project-wide scan test passes); `tools/check_contrast.py` passes; no raw colours outside `tokens.css`; screenshots at 900x600 and 1440x900 in dark and light themes.

---

## 10. Test Plan & Traceability Matrix

### 10.1 Backend unit tests (`tests/test_problems_backend.py`)

| ID | Target | Assertion |
| :--- | :--- | :--- |
| TC-PRB-07 | Python syntax | `def f(:` returns 1 error with correct 1-based line/col |
| TC-PRB-08 | Python valid | valid file returns `[]` |
| TC-PRB-09 | Deep nesting | 100k nested parens -> single `E_COMPLEXITY` diagnostic, no exception |
| TC-PRB-10 | JSON | `{"a":}` -> error with `JSON` code and line/col; `.jsonc` skipped |
| TC-PRB-11 | Caps | 3000 synthetic diagnostics -> 500 returned, `truncated=True` |
| TC-PRB-12 | Sanitiser | ANSI escapes and control characters removed, length <= 500 |
| TC-PRB-13 | Fingerprint | same input -> same `id`; different line -> different `id` |

### 10.2 Bridge / security tests (`tests/test_problems_bridge.py`)

| ID | Target | Assertion |
| :--- | :--- | :--- |
| TC-PRB-19 | Origin guard | wrong origin -> `Unauthorized origin` |
| TC-PRB-20 | Sandbox | outside path, `../` traversal, symlink escape, `~/.ssh` under ancestor root -> denied |
| TC-PRB-21 | No code execution | workspace with `.flake8`/`setup.cfg` declaring a local plugin that writes a marker file -> marker **not** created (flake8 runs with `--isolated`) |
| TC-PRB-22 | Timeout | fake checker sleeping 30 s is killed within timeout + 2 s, no orphan process |
| TC-PRB-23 | Concurrency | 4th concurrent request returns `Busy` |
| TC-PRB-24 | Relative paths | response never contains the absolute workspace path |
| TC-PRB-25 | Windows | with `sys.platform` mocked to `win32`: `CREATE_NO_WINDOW` flag used, path keys normalised |

### 10.3 Frontend / E2E tests (Playwright against the **real** `DesktopServer`, not `file://`)

| ID | Target | Assertion |
| :--- | :--- | :--- |
| TC-PRB-14 | Severity rendering | each severity has icon + text label; colour is not the only cue |
| TC-PRB-15 | Keyboard model | one Tab stop; arrows, Home/End, Enter, Esc behave as specified |
| TC-PRB-16 | Live region | one summary announcement per check, none per item |
| TC-PRB-17 | Focus restore | focus returns to the same item after re-render |
| TC-PRB-18 | Tab badge | counts and `aria-label` update; hidden when zero |
| TC-PRB-26 | Save flow | saving a Python file with a syntax error shows the problem within 2 s |
| TC-PRB-27 | Navigation | Enter on a problem opens the file and the CodeMirror selection is at the expected line/col |
| TC-PRB-28 | Replace semantics | fixing the error and saving clears the item and shows the empty state |
| TC-PRB-29 | Stale response | slow first check + fast second check: final list reflects the second |
| TC-PRB-30 | Workspace switch | switching root clears all problems and ignores late responses |
| TC-PRB-31 | Filters | severity toggles and text filter work, `aria-pressed` correct |
| TC-PRB-32 | Layout stability | no layout shift (CLS ~ 0) when results arrive; no horizontal overflow at 900x600 |
| TC-PRB-33 | Themes | contrast pairs pass and screenshots render in dark and light |
| TC-PRB-34 | DOM safety | message `<img src=x onerror=...>` renders as text, no element created |
| TC-PRB-35 | Static scan | no `innerHTML` / `outerHTML` / `insertAdjacentHTML` in `static/js/problems/*` |

### 10.4 Existing tests retained

TC-PRB-01 to TC-PRB-06 (tab declaration, panel declaration, default hidden, activation, empty-state text, ARIA linking) remain unchanged.
