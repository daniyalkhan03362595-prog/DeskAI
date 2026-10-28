# Low-Level Design (LLD): Workspace Branch Pill

**Document ID:** `ORX-LLD-WORKSPACE-BRANCH-PILL-V1`  
**Version:** `1.0` (Window Control Bar Subcomponent Architecture)  
**Parent Document:** `ORX-HLD-WORKSPACE-BRANCH-PILL-V1`  
**Target Codebase:** `DeskAI`  
**Target Files:**
* `src/deskai/static/index.html`
* `src/deskai/static/css/components.css`
* `src/deskai/static/css/tokens.css`
* `src/deskai/static/js/state.js`
* `src/deskai/static/js/app.js`
* `src/deskai/static/js/bridge.js`
* `src/deskai/bridge/api.py`
* `tests/test_workspace_branch_pill.py`
**Status:** Approved for Implementation  
**Date:** October 28, 2026  

---

## 1. Executive Summary & Objective

The **Workspace Branch Pill** (`#headerWorkspacePill`) renders the active project directory and Git branch in the header bar.

This Low-Level Design defines:
1. Exact HTML structure and accessibility attributes (`role="status"`, `aria-label`, `title`).
2. CSS styling specifications with ellipsis truncation and tokens.
3. Reactive JavaScript controller (`WorkspacePillController`) subscribing to `StudioStore`.
4. Backend API endpoint (`get_git_branch`) in `DesktopBridgeAPI` and `bridge.js`.
5. Automated test specifications (`TC-WBP-01` through `TC-WBP-07`).

---

## 2. DOM Structure & Markup Specification

### 2.1 Markup in `src/deskai/static/index.html`

```html
<div class="workspace-pill-container" id="workspacePillContainer">
  <span 
    class="workspace-pill" 
    id="headerWorkspacePill" 
    role="status" 
    aria-label="Workspace: No folder opened" 
    title="No active workspace folder">
    No Folder Opened
  </span>
</div>
```

---

## 3. CSS Styling & Layout Specifications

In `src/deskai/static/css/components.css`:

```css
.workspace-pill {
  background-color: var(--bg-surface);
  color: var(--text-secondary);
  font-size: var(--text-xs);
  padding: 2px 10px;
  border-radius: 12px;
  border: 1px solid var(--border-subtle);
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  cursor: default;
  user-select: none;
  transition: border-color var(--duration-fast) ease, color var(--duration-fast) ease;
  -webkit-app-region: no-drag;
}

.workspace-pill:hover {
  border-color: var(--border-default);
  color: var(--text-primary);
}

.workspace-pill.has-workspace {
  color: var(--text-primary);
  border-color: var(--border-default);
}
```

### 3.1 Token Reference

| Property | Token Variable | Value |
|---|---|---|
| Background | `var(--bg-surface)` | `#161a23` |
| Text Color (Default) | `var(--text-secondary)` | `#94a3b8` |
| Text Color (Hover / Active) | `var(--text-primary)` | `#e6edf3` |
| Border | `var(--border-subtle)` | `#26272c` |
| Border Hover | `var(--border-regular)` | `#31333a` |
| Font Size | `var(--text-xs)` | `11px` |
| Transition | `var(--transition-fast)` | `0.15s ease` |

---

## 4. Backend Implementation (`deskai/bridge/api.py` & `bridge.js`)

### 4.1 Python Method in `DesktopBridgeAPI`

```python
    def get_git_branch(self, target_path: str | None = None) -> dict:
        """Returns the active git branch name if the path is a git repository."""
        if not self._is_origin_allowed():
            return {"status": "error", "branch": None}
        if not target_path:
            return {"status": "ok", "branch": None}
        try:
            p = Path(target_path).resolve()
            git_path = p / ".git"
            if not git_path.exists():
                return {"status": "ok", "branch": None}
            
            head_file = None
            if git_path.is_dir():
                head_file = git_path / "HEAD"
            elif git_path.is_file():
                # Git worktree / submodule reference pointer
                text = git_path.read_text(encoding="utf-8").strip()
                if text.startswith("gitdir:"):
                    gitdir = Path(text.split("gitdir:", 1)[1].strip())
                    if not gitdir.is_absolute():
                        gitdir = (p / gitdir).resolve()
                    head_file = gitdir / "HEAD"

            if head_file and head_file.exists():
                head_content = head_file.read_text(encoding="utf-8").strip()
                if head_content.startswith("ref: refs/heads/"):
                    branch = head_content.replace("ref: refs/heads/", "").strip()
                    return {"status": "ok", "branch": branch}
                elif head_content:
                    # Detached HEAD (SHA-1 prefix)
                    return {"status": "ok", "branch": head_content[:7]}
        except Exception as e:
            print(f"[DeskAI] Failed to read git branch: {e}")
        return {"status": "ok", "branch": None}
```

### 4.2 Frontend Method in `src/deskai/static/js/bridge.js`

```javascript
  async getGitBranch(targetPath) {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.get_git_branch) {
      return await window.pywebview.api.get_git_branch(targetPath);
    }
    return { status: "ok", branch: null };
  },
```

---

## 5. Frontend Reactive Controller (`src/deskai/static/js/app.js`)

```javascript
export class WorkspacePillController {
  constructor(store, bridge) {
    this.store = store;
    this.bridge = bridge;
    this.pillEl = document.getElementById("headerWorkspacePill");
    this.setupSubscriptions();
    this.sync();
  }

  setupSubscriptions() {
    if (this.store && typeof this.store.subscribe === "function") {
      this.store.subscribe("workspace.rootPath", async (newPath) => {
        if (newPath) {
          const res = await this.bridge.getGitBranch(newPath);
          this.store.state.workspace.branch = res && res.branch ? res.branch : null;
        } else {
          this.store.state.workspace.branch = null;
        }
        this.sync();
      });

      this.store.subscribe("workspace.branch", () => {
        this.sync();
      });
    }
  }

  sync() {
    if (!this.pillEl) return;
    const rootPath = this.store.state.workspace.rootPath;
    const branch = this.store.state.workspace.branch;

    if (!rootPath) {
      this.pillEl.textContent = "No Folder Opened";
      this.pillEl.title = "No active workspace folder";
      this.pillEl.setAttribute("aria-label", "Workspace: No folder opened");
      this.pillEl.classList.remove("has-workspace");
      return;
    }

    const folderName = rootPath.split("/").pop().split("\\").pop() || rootPath;
    const branchSuffix = branch ? ` / ${branch}` : "";
    this.pillEl.textContent = `${folderName}${branchSuffix}`;
    this.pillEl.title = `${rootPath}${branch ? ` (branch: ${branch})` : ""}`;
    this.pillEl.setAttribute("aria-label", `Active workspace: ${folderName}${branch ? `, branch: ${branch}` : ""}`);
    this.pillEl.classList.add("has-workspace");
  }
}
```

---

## 6. Test Specifications (`tests/test_workspace_branch_pill.py`)

| Test Case ID | Test Case Name | Description & Verification Steps |
|---|---|---|
| **TC-WBP-01** | `test_wbp_01_initial_state_markup` | Asserts `#headerWorkspacePill` renders with `role="status"`, initial text `"No Folder Opened"`, and title `"No active workspace folder"`. |
| **TC-WBP-02** | `test_wbp_02_reactive_sync_on_root_path_change` | Mutates `store.state.workspace.rootPath = "/mock/workspace/DeskAI"`, asserts pill updates to `"DeskAI"` and title shows full path. |
| **TC-WBP-03** | `test_wbp_03_branch_display_and_aria_label` | Sets `store.state.workspace.branch = "feature-v2"`, asserts text `"DeskAI / feature-v2"` and `aria-label` reflects both folder and branch. |
| **TC-WBP-04** | `test_wbp_04_no_drag_property` | Asserts `-webkit-app-region` computed style is `"no-drag"`. |
| **TC-WBP-05** | `test_wbp_05_text_truncation_styling` | Asserts computed styles: `text-overflow: ellipsis`, `overflow: hidden`, `white-space: nowrap`. |
| **TC-WBP-06** | `test_wbp_06_backend_git_branch_resolution` | Tests `DesktopBridgeAPI.get_git_branch()` on actual git repo and temporary directories with detached HEAD and submodules. |
| **TC-WBP-07** | `test_wbp_07_backend_origin_guard` | Rejects `get_git_branch()` from unauthorized origins. |
