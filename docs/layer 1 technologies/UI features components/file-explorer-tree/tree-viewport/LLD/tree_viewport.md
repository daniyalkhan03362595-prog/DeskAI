# Low-Level Design (LLD): Tree Viewport

**Document ID:** `ORX-LLD-TREE-VIEWPORT-V1`  
**Version:** `1.0` (File Explorer Tree Viewport Architecture)  
**Parent Document:** `ORX-HLD-TREE-VIEWPORT-V1`  
**Target Codebase:** `DeskAI`  
**Target Files:**
* `src/deskai/static/index.html`
* `src/deskai/static/js/explorer.js`
* `src/deskai/static/js/events.js`
* `src/deskai/static/css/components.css`
* `src/deskai/static/css/tokens.css`
* `tests/test_tree_viewport.py`
**Status:** Approved for Implementation  
**Date:** October 28, 2026  

---

## 1. Executive Summary & Objective

The **Tree Viewport** (`#fileTreeViewport`) is the DOM viewport in the Explorer sidebar rendering hierarchical filesystem nodes.

This Low-Level Design defines:
1. Exact HTML structure and WAI-ARIA 1.2 Tree attributes (`role="tree"`, `role="treeitem"`, `aria-expanded`, `aria-level`).
2. CSS token styling for viewport layout, scrolling, selection highlights, and keyboard focus rings.
3. Concrete JavaScript keyboard navigation state machine and event listeners in `src/deskai/static/js/explorer.js`.
4. Automated Playwright test suite (`TC-TVP-01` through `TC-TVP-08`).

---

## 2. DOM Hierarchy & Component Structure

```html
<!-- Explorer Tree Viewport Container -->
<div 
  class="tree-viewport" 
  id="fileTreeViewport" 
  role="tree" 
  tabindex="0" 
  aria-label="Project Files">
  
  <!-- Empty State (when no workspace or empty directory) -->
  <div class="tree-empty-message" id="treeEmptyMessage" hidden>
    <span class="empty-icon">📁</span>
    <p class="empty-text">No folder open</p>
    <button type="button" class="empty-action-btn" data-action="open-folder-dialog">Open Folder</button>
  </div>

  <!-- Hierarchical Node Item: Folder (Expanded) -->
  <div 
    class="tree-item is-folder expanded active" 
    role="treeitem" 
    id="tree-node-1" 
    data-path="/workspace/src" 
    data-is-dir="true" 
    aria-expanded="true" 
    aria-level="1" 
    tabindex="0">
    <span class="tree-arrow" aria-hidden="true">▼</span>
    <span class="tree-icon" aria-hidden="true">📁</span>
    <span class="tree-label">src</span>
  </div>

  <!-- Nested Items Group -->
  <div class="tree-group" role="group" id="tree-group-1">
    <!-- Child File Item -->
    <div 
      class="tree-item is-file" 
      role="treeitem" 
      id="tree-node-2" 
      data-path="/workspace/src/app.js" 
      data-is-dir="false" 
      aria-level="2" 
      tabindex="-1">
      <span class="tree-indent" style="width: 16px;" aria-hidden="true"></span>
      <span class="tree-icon" aria-hidden="true">🟨</span>
      <span class="tree-label">app.js</span>
    </div>
  </div>

  <!-- Root Level File Item -->
  <div 
    class="tree-item is-file" 
    role="treeitem" 
    id="tree-node-3" 
    data-path="/workspace/README.md" 
    data-is-dir="false" 
    aria-level="1" 
    tabindex="-1">
    <span class="tree-icon" aria-hidden="true">📝</span>
    <span class="tree-label">README.md</span>
  </div>

</div>
```

---

## 3. CSS Styling & Design Tokens

```css
.tree-viewport {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: var(--space-2) 0;
  margin: 0;
  outline: none;
  background-color: var(--bg-surface);
  scrollbar-width: thin;
  scrollbar-color: var(--border-regular) transparent;
}

.tree-viewport::-webkit-scrollbar {
  width: 6px;
}

.tree-viewport::-webkit-scrollbar-thumb {
  background-color: var(--border-regular);
  border-radius: 3px;
}

.tree-empty-message {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-6) var(--space-4);
  text-align: center;
  color: var(--text-muted);
  gap: var(--space-2);
}

.tree-empty-message .empty-icon {
  font-size: var(--text-xl);
  opacity: 0.6;
}

.tree-empty-message .empty-text {
  font-size: var(--text-xs);
  margin: 0;
}

.tree-empty-message .empty-action-btn {
  background-color: var(--bg-surface-elevated);
  border: 1px solid var(--border-regular);
  color: var(--text-primary);
  border-radius: var(--radius-sm);
  padding: var(--space-1) var(--space-3);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: background-color var(--transition-fast), border-color var(--transition-fast);
}

.tree-empty-message .empty-action-btn:hover {
  background-color: var(--bg-hover);
  border-color: var(--color-primary);
}

.tree-viewport:focus-visible {
  outline: 1px solid var(--color-primary);
}

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
```

---

## 4. Algorithmic Implementation

### 4.1 Keyboard Navigation State Machine in `ExplorerManager`

```javascript
initTreeKeyboard() {
  if (!this.viewport) return;

  this.viewport.addEventListener("keydown", (e) => {
    const visibleItems = Array.from(this.viewport.querySelectorAll(".tree-item"));
    if (visibleItems.length === 0) return;

    let currentIndex = visibleItems.indexOf(document.activeElement);
    if (currentIndex === -1) {
      const activeNode = this.viewport.querySelector(".tree-item.active");
      currentIndex = activeNode ? visibleItems.indexOf(activeNode) : 0;
    }

    const currentItem = visibleItems[currentIndex];

    switch (e.key) {
      case "ArrowDown": {
        e.preventDefault();
        const nextIndex = Math.min(currentIndex + 1, visibleItems.length - 1);
        this.focusNode(visibleItems[nextIndex]);
        break;
      }

      case "ArrowUp": {
        e.preventDefault();
        const prevIndex = Math.max(currentIndex - 1, 0);
        this.focusNode(visibleItems[prevIndex]);
        break;
      }

      case "ArrowRight": {
        e.preventDefault();
        if (currentItem && currentItem.getAttribute("data-is-dir") === "true") {
          const isExpanded = currentItem.getAttribute("aria-expanded") === "true";
          if (!isExpanded) {
            this.toggleFolder(currentItem.getAttribute("data-path"), true);
          } else {
            // Move to first child if available
            if (currentIndex + 1 < visibleItems.length) {
              this.focusNode(visibleItems[currentIndex + 1]);
            }
          }
        }
        break;
      }

      case "ArrowLeft": {
        e.preventDefault();
        if (currentItem && currentItem.getAttribute("data-is-dir") === "true") {
          const isExpanded = currentItem.getAttribute("aria-expanded") === "true";
          if (isExpanded) {
            this.toggleFolder(currentItem.getAttribute("data-path"), false);
            return;
          }
        }
        // Move to parent folder if inside a group
        const groupParent = currentItem.closest(".tree-group");
        if (groupParent) {
          const parentItem = groupParent.previousElementSibling;
          if (parentItem && parentItem.classList.contains("tree-item")) {
            this.focusNode(parentItem);
          }
        }
        break;
      }

      case "Home": {
        e.preventDefault();
        this.focusNode(visibleItems[0]);
        break;
      }

      case "End": {
        e.preventDefault();
        this.focusNode(visibleItems[visibleItems.length - 1]);
        break;
      }

      case "Enter": {
        e.preventDefault();
        if (currentItem) {
          this.activateNode(currentItem);
        }
        break;
      }

      case " ": {
        e.preventDefault();
        if (currentItem) {
          this.selectNode(currentItem);
        }
        break;
      }
    }
  });
}

focusNode(nodeEl) {
  if (!nodeEl) return;
  const allItems = this.viewport.querySelectorAll(".tree-item");
  allItems.forEach((el) => el.setAttribute("tabindex", "-1"));
  nodeEl.setAttribute("tabindex", "0");
  nodeEl.focus();
}

selectNode(nodeEl) {
  if (!nodeEl) return;
  const allItems = this.viewport.querySelectorAll(".tree-item");
  allItems.forEach((el) => el.classList.remove("active"));
  nodeEl.classList.add("active");
  this.selectedNode = {
    path: nodeEl.getAttribute("data-path"),
    isDir: nodeEl.getAttribute("data-is-dir") === "true"
  };
}

async activateNode(nodeEl) {
  this.selectNode(nodeEl);
  const isDir = nodeEl.getAttribute("data-is-dir") === "true";
  const path = nodeEl.getAttribute("data-path");
  if (isDir) {
    const isExpanded = nodeEl.getAttribute("aria-expanded") === "true";
    await this.toggleFolder(path, !isExpanded);
  } else {
    if (window.EditorManager && typeof window.EditorManager.openFile === "function") {
      await window.EditorManager.openFile(path);
    }
  }
}
```

### 4.2 Scroll Position Preservation across Tree Refresh

```javascript
async refresh() {
  const currentScrollTop = this.viewport ? this.viewport.scrollTop : 0;
  const rootPath = store && store.state && store.state.workspace ? store.state.workspace.rootPath : null;

  const res = await NativeBridge.listDir(rootPath);
  if (res && res.status === "ok" && Array.isArray(res.entries)) {
    this.entries = res.entries;
    this.render();
    if (this.viewport) {
      this.viewport.scrollTop = currentScrollTop;
    }
  }
}
```

---

## 5. Playwright Test Specifications

Test file: `tests/test_tree_viewport.py`

* **`TC-TVP-01: test_viewport_aria_tree_semantics`**  
  Asserts `#fileTreeViewport` has `role="tree"` and `aria-label="Project Files"`.
* **`TC-TVP-02: test_viewport_empty_state_prompt`**  
  Asserts empty message and "Open Folder" action button display when no entries exist.
* **`TC-TVP-03: test_roving_tabindex_lifecycle`**  
  Asserts focused item has `tabindex="0"` while others maintain `tabindex="-1"`.
* **`TC-TVP-04: test_keyboard_arrow_down_up_navigation`**  
  Asserts `ArrowDown` and `ArrowUp` move focus sequentially between nodes.
* **`TC-TVP-05: test_keyboard_home_end_navigation`**  
  Asserts `Home` moves focus to the first item and `End` moves to the last item.
* **`TC-TVP-06: test_keyboard_folder_expansion_toggle`**  
  Asserts `ArrowRight` expands folder and `ArrowLeft` collapses folder.
* **`TC-TVP-07: test_keyboard_enter_file_activation`**  
  Asserts pressing `Enter` on a file node calls `EditorManager.openFile(path)`.
* **`TC-TVP-08: test_scroll_position_preservation`**  
  Asserts `scrollTop` remains stable after invoking `refresh()`.
