# Low-Level Design (LLD): Tree Header Toolbar

**Document ID:** `ORX-LLD-TREE-HEADER-TOOLBAR-V1`  
**Version:** `1.0` (File Explorer Toolbar Architecture)  
**Parent Document:** `ORX-HLD-TREE-HEADER-TOOLBAR-V1`  
**Target Codebase:** `DeskAI`  
**Target Files:**
* `src/deskai/static/index.html`
* `src/deskai/static/js/events.js`
* `src/deskai/static/js/explorer.js`
* `src/deskai/static/css/components.css`
* `src/deskai/static/css/tokens.css`
* `tests/test_tree_header_toolbar.py`
**Status:** Approved for Implementation  
**Date:** October 28, 2026  

---

## 1. Executive Summary & Objective

The **Tree Header Toolbar** (`.panel-header`) provides workspace navigation controls above `#fileTreeViewport`.

This Low-Level Design defines:
1. Exact DOM layout and accessibility markup (`role="toolbar"`, `aria-label`).
2. CSS token mappings (`--bg-header`, `--border-subtle`, `--text-muted`, `--color-primary`).
3. JavaScript event handling in `events.js` and `ExplorerManager`.
4. Keyboard roving focus logic across toolbar buttons.
5. Automated Playwright test specifications (`TC-THT-01` through `TC-THT-06`).

---

## 2. DOM Structure & Accessibility Markup

```html
<div class="panel-header" id="explorerHeader">
  <span class="panel-title" id="explorerPanelTitle">EXPLORER</span>
  <div 
    class="panel-actions" 
    id="explorerToolbar" 
    role="toolbar" 
    aria-label="Explorer Actions" 
    aria-controls="fileTreeViewport">
    
    <button 
      type="button" 
      class="icon-btn" 
      id="btnNewFile" 
      data-action="new-file" 
      title="New File" 
      aria-label="New File" 
      tabindex="0">📄+</button>
      
    <button 
      type="button" 
      class="icon-btn" 
      id="btnNewFolder" 
      data-action="new-folder" 
      title="New Folder" 
      aria-label="New Folder" 
      tabindex="-1">📁+</button>
      
    <button 
      type="button" 
      class="icon-btn" 
      id="btnRefreshTree" 
      data-action="refresh-tree" 
      title="Refresh Tree" 
      aria-label="Refresh Tree" 
      tabindex="-1">🔄</button>
      
    <button 
      type="button" 
      class="icon-btn" 
      id="btnCollapseAll" 
      data-action="collapse-all-folders" 
      title="Collapse Folders" 
      aria-label="Collapse All Folders" 
      tabindex="-1">⊟</button>
  </div>
</div>
```

---

## 3. CSS Styling & Token Bindings

```css
.explorer-container .panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--header-height, 36px);
  padding: 0 var(--space-3);
  background-color: var(--bg-header);
  border-bottom: 1px solid var(--border-subtle);
  user-select: none;
}

.explorer-container .panel-title {
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
}

.explorer-container .panel-actions {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.explorer-container .panel-actions .icon-btn {
  background: transparent;
  border: 1px solid transparent;
  color: var(--text-secondary);
  border-radius: var(--radius-sm);
  padding: 2px 4px;
  font-size: var(--text-xs);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background-color var(--transition-fast), color var(--transition-fast);
}

.explorer-container .panel-actions .icon-btn:hover {
  background-color: var(--bg-hover);
  color: var(--text-primary);
}

.explorer-container .panel-actions .icon-btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 1px;
}
```

---

## 4. Implementation Details: JavaScript Event Delegation & Toolbar Roving Focus

### 4.1 Roving Focus on `.panel-actions[role="toolbar"]`

```javascript
export function initToolbarKeyboard(toolbarEl) {
  if (!toolbarEl) return;
  const buttons = Array.from(toolbarEl.querySelectorAll("button.icon-btn"));
  if (buttons.length === 0) return;

  toolbarEl.addEventListener("keydown", (e) => {
    const currentIndex = buttons.indexOf(document.activeElement);
    if (currentIndex === -1) return;

    if (e.key === "ArrowRight") {
      e.preventDefault();
      const nextIndex = (currentIndex + 1) % buttons.length;
      updateToolbarFocus(buttons, nextIndex);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      const prevIndex = (currentIndex - 1 + buttons.length) % buttons.length;
      updateToolbarFocus(buttons, prevIndex);
    } else if (e.key === "Home") {
      e.preventDefault();
      updateToolbarFocus(buttons, 0);
    } else if (e.key === "End") {
      e.preventDefault();
      updateToolbarFocus(buttons, buttons.length - 1);
    }
  });
}

function updateToolbarFocus(buttons, targetIndex) {
  buttons.forEach((btn, i) => {
    if (i === targetIndex) {
      btn.setAttribute("tabindex", "0");
      btn.focus();
    } else {
      btn.setAttribute("tabindex", "-1");
    }
  });
}
```

### 4.2 Action Handlers in `src/deskai/static/js/events.js`

```javascript
case "new-file": {
  if (window.ExplorerManager && typeof window.ExplorerManager.promptNewFile === "function") {
    await window.ExplorerManager.promptNewFile();
  }
  break;
}

case "new-folder": {
  if (window.ExplorerManager && typeof window.ExplorerManager.promptNewFolder === "function") {
    await window.ExplorerManager.promptNewFolder();
  }
  break;
}

case "refresh-tree": {
  if (window.ExplorerManager && typeof window.ExplorerManager.refresh === "function") {
    await window.ExplorerManager.refresh();
  }
  break;
}

case "collapse-all-folders": {
  if (window.ExplorerManager && typeof window.ExplorerManager.collapseAll === "function") {
    window.ExplorerManager.collapseAll();
  }
  break;
}
```

---

## 5. Playwright Test Specifications

Test file: `tests/test_tree_header_toolbar.py`

* **`TC-THT-01: test_toolbar_semantics_and_a11y`**  
  Asserts `.panel-actions` has `role="toolbar"`, `aria-label="Explorer Actions"`, and all buttons have valid labels and icons.
* **`TC-THT-02: test_new_file_action_dispatch`**  
  Asserts clicking `new-file` triggers `promptNewFile()`, creates file via `NativeBridge.writeFile()`, reloads tree, and opens active tab.
* **`TC-THT-03: test_new_folder_action_dispatch`**  
  Asserts clicking `new-folder` prompts for directory name, executes directory creation, and refreshes tree.
* **`TC-THT-04: test_refresh_tree_action_dispatch`**  
  Asserts clicking `refresh-tree` triggers `ExplorerManager.refresh()` and queries `NativeBridge.listDir()`.
* **`TC-THT-05: test_collapse_all_action_dispatch`**  
  Asserts clicking `collapse-all-folders` calls `ExplorerManager.collapseAll()`, setting all folder nodes to collapsed state.
* **`TC-THT-06: test_toolbar_roving_keyboard_navigation`**  
  Asserts `ArrowRight`, `ArrowLeft`, `Home`, and `End` rove focus across toolbar buttons and manage `tabindex="0"`.
