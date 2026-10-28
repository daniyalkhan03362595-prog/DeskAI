# Low-Level Design (LLD): Context Menu Actions

**Document ID:** `ORX-LLD-CONTEXT-MENU-ACTIONS-V1`  
**Version:** `1.0` (File Explorer Context Menu Architecture)  
**Parent Document:** `ORX-HLD-CONTEXT-MENU-ACTIONS-V1`  
**Target Codebase:** `DeskAI`  
**Target Files:**
* `src/deskai/static/index.html`
* `src/deskai/static/js/explorer.js`
* `src/deskai/static/js/bridge.js`
* `src/deskai/bridge/api.py`
* `src/deskai/static/css/components.css`
* `src/deskai/static/css/tokens.css`
* `tests/test_context_menu_actions.py`
**Status:** Approved for Implementation  
**Date:** October 28, 2026  

---

## 1. Executive Summary & Objective

The **Context Menu Actions** subsystem (`#treeContextMenu`) manages right-click popup operations in `#fileTreeViewport`.

This Low-Level Design defines:
1. Exact HTML structure and WAI-ARIA 1.2 Menu markup (`role="menu"`, `role="menuitem"`).
2. CSS token styling for floating elevation, borders, separators, hover highlights, and destructive items.
3. JavaScript algorithms in `ExplorerManager` for coordinate clamping, action delegation, clipboard writing, and guarded deletion.
4. Backend `delete_path` RPC implementation in `api.py`.
5. Automated Playwright test suite (`TC-CMA-01` through `TC-CMA-07`).

---

## 2. DOM Structure & Accessibility Markup

```html
<!-- Floating Context Menu Portal -->
<div 
  class="context-menu" 
  id="treeContextMenu" 
  role="menu" 
  aria-label="File Actions" 
  hidden>
  
  <div class="menu-item" role="menuitem" data-action="ctx-new-file" tabindex="-1">
    <span class="menu-icon" aria-hidden="true">📄</span>
    <span class="menu-label">New File...</span>
  </div>
  
  <div class="menu-item" role="menuitem" data-action="ctx-new-folder" tabindex="-1">
    <span class="menu-icon" aria-hidden="true">📁</span>
    <span class="menu-label">New Folder...</span>
  </div>
  
  <div class="menu-separator" role="separator" aria-hidden="true"></div>
  
  <div class="menu-item" role="menuitem" data-action="ctx-rename" tabindex="-1">
    <span class="menu-icon" aria-hidden="true">✏️</span>
    <span class="menu-label">Rename</span>
    <span class="menu-shortcut">F2</span>
  </div>
  
  <div class="menu-item destructive" role="menuitem" data-action="ctx-delete" tabindex="-1">
    <span class="menu-icon" aria-hidden="true">🗑️</span>
    <span class="menu-label">Delete</span>
    <span class="menu-shortcut">Del</span>
  </div>
  
  <div class="menu-separator" role="separator" aria-hidden="true"></div>
  
  <div class="menu-item" role="menuitem" data-action="ctx-copy-path" tabindex="-1">
    <span class="menu-icon" aria-hidden="true">📋</span>
    <span class="menu-label">Copy Path</span>
  </div>
  
  <div class="menu-item" role="menuitem" data-action="ctx-copy-relative-path" tabindex="-1">
    <span class="menu-icon" aria-hidden="true">🔗</span>
    <span class="menu-label">Copy Relative Path</span>
  </div>
</div>
```

---

## 3. CSS Styling & Design Tokens

```css
.context-menu {
  position: fixed;
  z-index: var(--z-modal, 500);
  min-width: 180px;
  background-color: var(--bg-surface-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-md);
  padding: var(--space-1) 0;
  user-select: none;
  outline: none;
}

.context-menu .menu-item {
  display: flex;
  align-items: center;
  height: 28px;
  padding: 0 var(--space-3);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  cursor: pointer;
  transition: background-color var(--transition-fast), color var(--transition-fast);
}

.context-menu .menu-item:hover,
.context-menu .menu-item:focus {
  background-color: var(--bg-hover);
  color: var(--text-primary);
  outline: none;
}

.context-menu .menu-item.destructive {
  color: var(--color-error);
}

.context-menu .menu-item.destructive:hover,
.context-menu .menu-item.destructive:focus {
  background-color: var(--bg-hover);
  color: var(--color-error);
}

.context-menu .menu-icon {
  margin-right: var(--space-2);
  width: 14px;
  text-align: center;
}

.context-menu .menu-label {
  flex: 1;
}

.context-menu .menu-shortcut {
  font-size: 10px;
  color: var(--text-muted);
  margin-left: var(--space-3);
}

.context-menu .menu-separator {
  height: 1px;
  background-color: var(--border-subtle);
  margin: var(--space-1) 0;
}
```

---

## 4. Concrete Algorithmic Implementation

### 4.1 Coordinate Clamping Algorithm in `src/deskai/static/js/explorer.js`

```javascript
showContextMenu(x, y, targetNode) {
  if (!this.contextMenu) return;
  this.contextTarget = targetNode;

  this.contextMenu.style.display = "block";
  this.contextMenu.removeAttribute("hidden");

  // Clamp within viewport
  const menuW = this.contextMenu.offsetWidth || 180;
  const menuH = this.contextMenu.offsetHeight || 200;
  const maxX = window.innerWidth - menuW - 8;
  const maxY = window.innerHeight - menuH - 8;

  const clampedX = Math.max(8, Math.min(x, maxX));
  const clampedY = Math.max(8, Math.min(y, maxY));

  this.contextMenu.style.left = `${clampedX}px`;
  this.contextMenu.style.top = `${clampedY}px`;

  // Focus first menu item
  const firstItem = this.contextMenu.querySelector(".menu-item");
  if (firstItem) firstItem.focus();
}

hideContextMenu() {
  if (!this.contextMenu) return;
  this.contextMenu.style.display = "none";
  this.contextMenu.setAttribute("hidden", "");
  this.contextTarget = null;
}
```

### 4.2 Action Dispatcher

```javascript
async handleContextAction(action) {
  const target = this.contextTarget || this.selectedNode;
  this.hideContextMenu();
  if (!target) return;

  switch (action) {
    case "ctx-new-file":
      await this.promptNewFile();
      break;

    case "ctx-new-folder":
      await this.promptNewFolder();
      break;

    case "ctx-rename": {
      const nodeEl = this.viewport.querySelector(`[data-path="${target.path}"]`);
      if (nodeEl) this.startInlineRename(nodeEl);
      break;
    }

    case "ctx-delete":
      await this.deleteNode(target);
      break;

    case "ctx-copy-path":
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(target.path);
      }
      break;

    case "ctx-copy-relative-path": {
      const root = store && store.state && store.state.workspace ? store.state.workspace.rootPath : "";
      let relPath = target.path;
      if (root && relPath.startsWith(root)) {
        relPath = relPath.substring(root.length).replace(/^\/+/, "");
      }
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(relPath);
      }
      break;
    }
  }
}

async deleteNode(target) {
  const isDir = target.isDir;
  const confirmed = confirm(`Are you sure you want to delete ${target.name || "this item"}?`);
  if (!confirmed) return;

  const res = await NativeBridge.deletePath(target.path);
  if (res && res.status === "ok") {
    // If open in editor, close tab
    if (!isDir && window.EditorManager && window.EditorManager.buffers) {
      for (const [id, buf] of window.EditorManager.buffers.entries()) {
        if (buf.path === target.path) {
          await window.EditorManager.closeTab(id, true);
        }
      }
    }
    await this.refresh();
  } else {
    alert(`Delete failed: ${res ? res.message : "Unknown error"}`);
  }
}
```

### 4.3 Backend Python RPC `delete_path` in `src/deskai/bridge/api.py`

```python
def delete_path(self, target_path: str) -> dict:
    """Safely deletes a file or directory within workspace root."""
    if not self._is_origin_allowed():
        return {"status": "error", "message": "Unauthorized origin"}
    if not self._is_safe_path(target_path):
        return {"status": "error", "message": "Access denied: Path outside workspace"}

    canonical = canonicalize_path(target_path)
    if canonical == canonicalize_path(self.workspace_root):
        return {"status": "error", "message": "Cannot delete workspace root"}

    if not os.path.exists(canonical):
        return {"status": "error", "message": "Path not found"}

    try:
        if os.path.isdir(canonical):
            shutil.rmtree(canonical)
        else:
            os.remove(canonical)
        return {"status": "ok", "path": canonical}
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

---

## 5. Playwright Test Specifications

Test file: `tests/test_context_menu_actions.py`

* **`TC-CMA-01: test_context_menu_right_click_invocation`**  
  Asserts right-clicking `.tree-item` prevents native context menu and displays `#treeContextMenu` at coordinates.
* **`TC-CMA-02: test_context_menu_keyboard_shift_f10`**  
  Asserts pressing `Shift+F10` on focused node opens context menu and sets focus to first item.
* **`TC-CMA-03: test_context_menu_clamping_to_viewport`**  
  Asserts opening menu near viewport edge clamps `left` and `top` so menu remains fully visible.
* **`TC-CMA-04: test_copy_path_and_relative_path`**  
  Asserts clicking "Copy Path" and "Copy Relative Path" writes to clipboard.
* **`TC-CMA-05: test_rename_action_invokes_inline_rename`**  
  Asserts clicking "Rename" dismisses menu and triggers `.tree-rename-input`.
* **`TC-CMA-06: test_guarded_delete_action`**  
  Asserts clicking "Delete" prompts user, calls `NativeBridge.deletePath()`, closes open editor tab, and refreshes tree.
* **`TC-CMA-07: test_menu_dismissal_on_escape_and_outside_click`**  
  Asserts pressing `Escape` or clicking outside hides `#treeContextMenu`.
