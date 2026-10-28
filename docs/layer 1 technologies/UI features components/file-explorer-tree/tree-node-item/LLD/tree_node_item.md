# Low-Level Design (LLD): Tree Node Item

**Document ID:** `ORX-LLD-TREE-NODE-ITEM-V1`  
**Version:** `1.0` (File Explorer Node Item Architecture)  
**Parent Document:** `ORX-HLD-TREE-NODE-ITEM-V1`  
**Target Codebase:** `DeskAI`  
**Target Files:**
* `src/deskai/static/js/explorer.js`
* `src/deskai/static/js/bridge.js`
* `src/deskai/bridge/api.py`
* `src/deskai/static/css/components.css`
* `src/deskai/static/css/tokens.css`
* `tests/test_tree_node_item.py`
**Status:** Approved for Implementation  
**Date:** October 28, 2026  

---

## 1. Executive Summary & Objective

The **Tree Node Item** (`.tree-item`) encapsulates an individual tree row within `#fileTreeViewport`.

This Low-Level Design defines:
1. Exact DOM layout, chevron handling, and semantic iconography.
2. CSS token styling for regular, hover, active, and inline-editing states.
3. Concrete JavaScript inline rename algorithm (`F2`, `Enter`, `Escape`).
4. Backend filesystem RPC `rename_path` contract.
5. Automated Playwright test suite (`TC-TNI-01` through `TC-TNI-07`).

---

## 2. DOM Structure & Component Anatomy

```html
<!-- Folder Node Item -->
<div 
  class="tree-item is-folder expanded active" 
  role="treeitem" 
  data-path="/workspace/src" 
  data-is-dir="true" 
  aria-expanded="true" 
  aria-level="1" 
  tabindex="0" 
  title="/workspace/src">
  
  <span class="tree-arrow" aria-hidden="true">▼</span>
  <span class="tree-icon" aria-hidden="true">📂</span>
  <span class="tree-label">src</span>
</div>

<!-- File Node Item (Standard Display) -->
<div 
  class="tree-item is-file" 
  role="treeitem" 
  data-path="/workspace/src/app.py" 
  data-is-dir="false" 
  aria-level="2" 
  tabindex="-1" 
  title="/workspace/src/app.py">
  
  <span class="tree-indent" style="width: 14px;" aria-hidden="true"></span>
  <span class="tree-arrow" aria-hidden="true"></span> <!-- empty placeholder -->
  <span class="tree-icon" aria-hidden="true">🐍</span>
  <span class="tree-label">app.py</span>
</div>

<!-- File Node Item (Inline Rename Mode) -->
<div 
  class="tree-item is-file is-renaming" 
  role="treeitem" 
  data-path="/workspace/src/app.py" 
  data-is-dir="false" 
  aria-level="2" 
  tabindex="0">
  
  <span class="tree-indent" style="width: 14px;" aria-hidden="true"></span>
  <span class="tree-icon" aria-hidden="true">🐍</span>
  <input 
    type="text" 
    class="tree-rename-input" 
    value="app.py" 
    aria-label="Rename file">
</div>
```

---

## 3. CSS Styling & Design Tokens

```css
.tree-item {
  display: flex;
  align-items: center;
  height: 24px;
  padding: 0 var(--space-2);
  cursor: pointer;
  user-select: none;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  border-left: 2px solid transparent;
  transition: background-color var(--transition-fast), color var(--transition-fast);
}

.tree-item:hover {
  background-color: var(--bg-hover);
  color: var(--text-primary);
}

.tree-item.active {
  background-color: var(--bg-active);
  color: var(--text-primary);
  border-left-color: var(--color-primary);
}

.tree-item:focus-visible {
  outline: 1px solid var(--color-primary);
  outline-offset: -1px;
}

.tree-item .tree-arrow {
  display: inline-block;
  width: 14px;
  font-size: 9px;
  text-align: center;
  color: var(--text-muted);
  user-select: none;
}

.tree-item .tree-icon {
  margin-right: var(--space-1);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-sm);
}

.tree-item .tree-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Inline Rename Input */
.tree-item .tree-rename-input {
  flex: 1;
  height: 20px;
  background-color: var(--bg-surface-elevated);
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-family: var(--font-sans);
  font-size: var(--text-xs);
  padding: 0 var(--space-1);
  outline: none;
}
```

---

## 4. Concrete Algorithmic Implementation

### 4.1 Inline Rename Controller in `src/deskai/static/js/explorer.js`

```javascript
startInlineRename(nodeEl) {
  if (!nodeEl || nodeEl.classList.contains("is-renaming")) return;

  const labelEl = nodeEl.querySelector(".tree-label");
  if (!labelEl) return;

  const oldName = labelEl.textContent;
  const oldPath = nodeEl.getAttribute("data-path");
  const isDir = nodeEl.getAttribute("data-is-dir") === "true";

  nodeEl.classList.add("is-renaming");
  labelEl.style.display = "none";

  const inputEl = document.createElement("input");
  inputEl.type = "text";
  inputEl.className = "tree-rename-input";
  inputEl.value = oldName;
  inputEl.setAttribute("aria-label", `Rename ${oldName}`);

  let committed = false;

  const commit = async () => {
    if (committed) return;
    committed = true;
    const newName = inputEl.value.trim();

    if (!newName || newName === oldName) {
      cancel();
      return;
    }

    const parentDir = oldPath.substring(0, oldPath.lastIndexOf("/"));
    const newPath = parentDir ? `${parentDir}/${newName}` : newName;

    const res = await NativeBridge.renamePath(oldPath, newPath);
    if (res && res.status === "ok") {
      // Re-index open editor tabs if a file was renamed
      if (!isDir && window.EditorManager) {
        for (const [id, buf] of window.EditorManager.buffers.entries()) {
          if (buf.path === oldPath) {
            buf.path = newPath;
            buf.name = newName;
            buf.language = window.EditorManager.detectLanguage(newName);
            window.EditorManager.pathToId.delete(oldPath);
            window.EditorManager.pathToId.set(newPath, id);
            window.EditorManager.renderTabs();
            window.EditorManager.syncStore();
          }
        }
      }
      await this.refresh();
    } else {
      alert(`Rename failed: ${res ? res.message : "Unknown error"}`);
      cancel();
    }
  };

  const cancel = () => {
    if (inputEl.parentElement) {
      inputEl.parentElement.removeChild(inputEl);
    }
    labelEl.style.display = "";
    nodeEl.classList.remove("is-renaming");
    nodeEl.focus();
  };

  inputEl.addEventListener("keydown", async (e) => {
    e.stopPropagation(); // Avoid triggering treeview arrow navigation
    if (e.key === "Enter") {
      e.preventDefault();
      await commit();
    } else if (e.key === "Escape") {
      e.preventDefault();
      cancel();
    }
  });

  inputEl.addEventListener("blur", async () => {
    await commit();
  });

  nodeEl.appendChild(inputEl);
  inputEl.focus();
  // Select basename without extension
  const dotIndex = oldName.lastIndexOf(".");
  if (dotIndex > 0 && !isDir) {
    inputEl.setSelectionRange(0, dotIndex);
  } else {
    inputEl.select();
  }
}
```

### 4.2 Keyboard Trigger: Binding `F2` to `startInlineRename`

In `initTreeKeyboard()`:
```javascript
case "F2": {
  e.preventDefault();
  if (currentItem) {
    this.startInlineRename(currentItem);
  }
  break;
}
```

---

## 5. Playwright Test Specifications

Test file: `tests/test_tree_node_item.py`

* **`TC-TNI-01: test_semantic_filetype_badges`**  
  Asserts correct filetype emoji badge is rendered for `.py` (🐍), `.js` (🟨), `.md` (📝), `.json` (📦), `.html` (🌐), etc.
* **`TC-TNI-02: test_folder_chevrons_and_icons`**  
  Asserts closed folder renders `► 📁` and open folder renders `▼ 📂`.
* **`TC-TNI-03: test_hierarchical_indent_level`**  
  Asserts level 1 items have no indent spacer, while level 2 and level 3 items have `.tree-indent` with computed width.
* **`TC-TNI-04: test_f2_triggers_inline_rename_input`**  
  Asserts pressing `F2` on focused item mounts `.tree-rename-input` prefilled with existing name.
* **`TC-TNI-05: test_inline_rename_commit_via_enter`**  
  Asserts typing new name and pressing `Enter` calls `NativeBridge.renamePath()`, reloads tree, and updates label.
* **`TC-TNI-06: test_inline_rename_cancel_via_escape`**  
  Asserts pressing `Escape` restores original label without triggering `renamePath`.
* **`TC-TNI-07: test_editor_buffer_sync_on_rename`**  
  Asserts renaming an open file updates `EditorManager` buffer path, name, and tab strip header.
