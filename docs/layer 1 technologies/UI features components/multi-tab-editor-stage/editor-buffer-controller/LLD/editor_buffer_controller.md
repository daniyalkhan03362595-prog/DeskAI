# Low-Level Design (LLD): Editor Buffer Controller

**Document ID:** `ORX-LLD-EDITOR-BUFFER-CONTROLLER-V1`  
**Version:** `1.0` (Document Memory Lifecycle & Persistence Architecture)  
**Parent Document:** `ORX-HLD-EDITOR-BUFFER-CONTROLLER-V1`  
**Target Codebase:** `DeskAI`  
**Target Files:**
* `src/deskai/static/js/editor.js`
* `src/deskai/static/js/bridge.js`
* `src/deskai/static/js/state.js`
* `src/deskai/static/js/events.js`
* `src/deskai/static/css/components.css`
* `src/deskai/static/css/tokens.css`
* `tests/test_editor_buffer_controller.py`
**Status:** Approved for Implementation  
**Date:** October 28, 2026  

---

## 1. Executive Summary & Objective

The **Editor Buffer Controller** provides headless, crash-resilient document memory and persistence management within `EditorManager` (`src/deskai/static/js/editor.js`). It coordinates between user actions (hotkeys, tab strip clicks, file explorer clicks), in-memory document structures (`BufferEntity`), the vendored CodeMirror 6 engine, the reactive state store (`StudioStore`), and the backend filesystem bridge (`NativeBridge`).

This Low-Level Design defines:
1. Exact JavaScript data models (`BufferEntity`, path registries, store schema).
2. Algorithmic implementations for buffer creation, deduplicated file opening, dirty tracking, saving, save-as, reverting, and guarded closure.
3. DOM lifecycle management and resource cleanup.
4. Comprehensive test specifications (`TC-EBC-01` through `TC-EBC-09`).

---

## 2. In-Memory Data Structures & State Schema

### 2.1 The `BufferEntity` Model

Each document buffer managed by the controller is represented by a structured `BufferEntity` object:

```typescript
interface BufferEntity {
  id: string;               // Unique identifier: "tab-" + uuid.slice(0, 8)
  name: string;             // File basename: e.g. "main.py", "untitled.txt"
  path: string | null;      // Absolute canonical disk path (null for scratch buffers)
  content: string;          // Current in-memory document text
  isDirty: boolean;         // True if document has uncommitted changes
  mtime: number | null;     // Disk modification epoch timestamp in milliseconds
  language: string;         // Syntax language ID ('python', 'javascript', 'markdown', etc.)
  state: EditorState | null;// CodeMirror 6 EditorState instance (or null in headless/fallback)
  view: EditorView | null;  // CodeMirror 6 EditorView instance (or null in headless/fallback)
  container: HTMLDivElement;// Mounted .editor-view-container DOM node
}
```

### 2.2 Controller Internal Registries

```javascript
export class EditorManager {
  constructor() {
    /** @type {Map<string, BufferEntity>} Primary registry keyed by buffer id */
    this.buffers = new Map();

    /** @type {Map<string, string>} Reverse index: canonicalPath -> bufferId */
    this.pathToId = new Map();

    /** @type {string | null} Currently active tab ID */
    this.activeTabId = null;

    /** @type {HTMLElement | null} DOM references */
    this.tabStrip = document.getElementById("editorTabStrip");
    this.welcomeScreen = document.getElementById("welcomeScreen");
    this.editorHost = document.getElementById("codeEditorHost");
  }
}
```

### 2.3 Reactive Store Synchronization Schema

The buffer controller keeps `store.state.editor` strictly synchronized:

```javascript
store.state.editor = {
  activeTabId: "tab-8f3b211a", // or null
  openTabs: [
    {
      id: "tab-8f3b211a",
      name: "main.py",
      path: "/home/user/workspace/main.py",
      isDirty: false
    },
    {
      id: "tab-b4a1c92d",
      name: "untitled-1.txt",
      path: null,
      isDirty: true
    }
  ]
};
```

---

## 3. Concrete Algorithmic Implementation

### 3.1 Path Normalization & Canonicalization

To guarantee duplicate prevention across different path representations:

```javascript
normalizePath(filePath) {
  if (!filePath || typeof filePath !== "string") return null;
  // Replace Windows backslashes with forward slashes for internal index consistency
  let normalized = filePath.replace(/\\/g, "/");
  // Strip trailing slashes
  while (normalized.length > 1 && normalized.endsWith("/")) {
    normalized = normalized.slice(0, -1);
  }
  return normalized;
}
```

### 3.2 Buffer Creation: `createBuffer(name, content, path)`

```javascript
createBuffer(name = "untitled.txt", content = "", path = null) {
  const id = "tab-" + crypto.randomUUID().slice(0, 8);
  const normalizedPath = this.normalizePath(path);

  // If path is specified and already open, return existing buffer ID
  if (normalizedPath && this.pathToId.has(normalizedPath)) {
    const existingId = this.pathToId.get(normalizedPath);
    this.selectTab(existingId);
    return existingId;
  }

  const buffer = {
    id,
    name,
    path: normalizedPath,
    content: String(content ?? ""),
    isDirty: false,
    mtime: Date.now(),
    language: this.detectLanguage(name),
    state: null,
    view: null,
    container: null
  };

  // Mount CodeMirror surface if engine available
  if (typeof window !== "undefined" && window.CodeMirror && window.CodeMirror.EditorState) {
    const { EditorState, EditorView, createBasicExtensions } = window.CodeMirror;

    const keyboardTrapHandler = EditorView.domEventHandlers({
      keydown: (e, view) => {
        if (e.key === "Escape") {
          view.contentDOM.blur();
          if (this.tabStrip) {
            const activeTab = this.tabStrip.querySelector(`[data-tab-id="${id}"]`);
            if (activeTab) activeTab.focus();
          }
          return true;
        }
        return false;
      }
    });

    const extensions = createBasicExtensions({
      language: buffer.language,
      extensions: [
        EditorView.updateListener.of((update) => {
          if (update.docChanged) {
            buffer.content = update.state.doc.toString();
            if (!buffer.isDirty) {
              this.markDirty(id, true);
            }
          }
        }),
        keyboardTrapHandler
      ]
    });

    buffer.state = EditorState.create({
      doc: buffer.content,
      extensions
    });

    buffer.container = document.createElement("div");
    buffer.container.className = "editor-view-container";
    buffer.container.id = `editor-container-${id}`;
    buffer.container.setAttribute("data-buffer-id", id);
    buffer.container.style.width = "100%";
    buffer.container.style.height = "100%";
    buffer.container.style.display = "none";

    buffer.view = new EditorView({
      state: buffer.state,
      parent: buffer.container
    });

    if (this.editorHost) {
      this.editorHost.appendChild(buffer.container);
    }
  }

  this.buffers.set(id, buffer);
  if (normalizedPath) {
    this.pathToId.set(normalizedPath, id);
  }

  this.syncStore();
  this.renderTabs();
  this.selectTab(id);
  return id;
}
```

### 3.3 Deduplicated File Opening: `openFile(filePath)`

```javascript
async openFile(filePath) {
  if (!filePath) return null;
  const normalizedPath = this.normalizePath(filePath);

  // 1. Duplicate check: If already open, switch to it immediately
  if (this.pathToId.has(normalizedPath)) {
    const existingId = this.pathToId.get(normalizedPath);
    this.selectTab(existingId);
    return existingId;
  }

  // 2. Read file from disk via NativeBridge
  try {
    const res = await NativeBridge.readFile(filePath);
    if (!res || res.status !== "ok") {
      console.error(`Failed to read file: ${filePath}`, res ? res.error : "Unknown error");
      return null;
    }

    const filename = filePath.split("/").pop().split("\\").pop();
    const id = this.createBuffer(filename, res.content, filePath);
    return id;
  } catch (err) {
    console.error(`Exception opening file: ${filePath}`, err);
    return null;
  }
}
```

### 3.4 Saving & Save-As Workflows

```javascript
async saveBuffer(id) {
  if (!id || !this.buffers.has(id)) return false;
  const buffer = this.buffers.get(id);

  // If buffer has no disk path, invoke Save As workflow
  if (!buffer.path) {
    return await this.saveBufferAs(id);
  }

  try {
    const res = await NativeBridge.writeFile(buffer.path, buffer.content);
    if (res && res.status === "ok") {
      buffer.mtime = Date.now();
      this.markDirty(id, false);
      return true;
    }
    console.error(`Save failed for ${buffer.path}:`, res ? res.error : "Unknown error");
    return false;
  } catch (err) {
    console.error(`Exception saving buffer ${id}:`, err);
    return false;
  }
}

async saveBufferAs(id) {
  if (!id || !this.buffers.has(id)) return false;
  const buffer = this.buffers.get(id);

  try {
    const res = await NativeBridge.saveFileDialog(buffer.name);
    if (res && res.status === "ok" && res.path) {
      const oldNormalizedPath = buffer.path;
      const newNormalizedPath = this.normalizePath(res.path);

      // Re-index path maps
      if (oldNormalizedPath) {
        this.pathToId.delete(oldNormalizedPath);
      }
      this.pathToId.set(newNormalizedPath, id);

      buffer.path = newNormalizedPath;
      buffer.name = res.path.split("/").pop().split("\\").pop();
      buffer.language = this.detectLanguage(buffer.name);

      const writeRes = await NativeBridge.writeFile(newNormalizedPath, buffer.content);
      if (writeRes && writeRes.status === "ok") {
        buffer.mtime = Date.now();
        this.markDirty(id, false);
        this.renderTabs();
        this.syncStore();
        return true;
      }
    }
    return false;
  } catch (err) {
    console.error(`Exception during saveBufferAs for ${id}:`, err);
    return false;
  }
}

async saveActiveBuffer() {
  if (!this.activeTabId) return false;
  return await this.saveBuffer(this.activeTabId);
}
```

### 3.5 Guarded Tab Teardown: `closeTab(id, force)`

```javascript
async closeTab(id, force = false) {
  if (!this.buffers.has(id)) return false;
  const buffer = this.buffers.get(id);

  // Unsaved changes confirmation gate
  if (!force && buffer.isDirty) {
    const confirmed = confirm(`Save changes to ${buffer.name} before closing?`);
    if (!confirmed) {
      return false; // User aborted closure
    }
    const saved = await this.saveBuffer(id);
    if (!saved) return false; // Abort if save failed or cancelled
  }

  // 1. Destroy CodeMirror instance
  if (buffer.view) {
    buffer.view.destroy();
  }

  // 2. Remove DOM container
  if (buffer.container && buffer.container.parentElement) {
    buffer.container.parentElement.removeChild(buffer.container);
  }

  // 3. Clear path registry
  if (buffer.path) {
    this.pathToId.delete(buffer.path);
  }

  // 4. Delete from buffer map
  this.buffers.delete(id);
  this.syncStore();

  // 5. Select adjacent tab or transition to Welcome Screen
  if (this.activeTabId === id) {
    const remainingIds = Array.from(this.buffers.keys());
    if (remainingIds.length > 0) {
      this.selectTab(remainingIds[remainingIds.length - 1]);
    } else {
      this.activeTabId = null;
      if (window.DeskAIWelcome) {
        window.DeskAIWelcome.sync();
        window.DeskAIWelcome.focusPrimary();
      } else if (this.welcomeScreen) {
        this.welcomeScreen.style.display = "flex";
      }
    }
  }

  // 6. Update native dirty status & rerender
  this.notifyNativeDirty();
  this.renderTabs();
  return true;
}

async closeAllTabs(force = false) {
  const ids = Array.from(this.buffers.keys());
  for (const id of ids) {
    const closed = await this.closeTab(id, force);
    if (!closed && !force) {
      return false; // Abort bulk closure if user cancels any dirty prompt
    }
  }
  return true;
}
```

### 3.6 Revert Buffer: `revertBuffer(id)`

```javascript
async revertBuffer(id) {
  if (!id || !this.buffers.has(id)) return false;
  const buffer = this.buffers.get(id);
  if (!buffer.path) return false; // Untitled buffers cannot be reverted

  try {
    const res = await NativeBridge.readFile(buffer.path);
    if (res && res.status === "ok") {
      buffer.content = res.content;
      buffer.mtime = Date.now();

      // Dispatch document update to CodeMirror if view is active
      if (buffer.view) {
        buffer.view.dispatch({
          changes: { from: 0, to: buffer.view.state.doc.length, insert: buffer.content }
        });
      }

      this.markDirty(id, false);
      return true;
    }
    return false;
  } catch (err) {
    console.error(`Exception reverting buffer ${id}:`, err);
    return false;
  }
}
```

### 3.7 State Synchronization Helpers

```javascript
markDirty(id, isDirty) {
  const buffer = this.buffers.get(id);
  if (buffer) {
    buffer.isDirty = Boolean(isDirty);
    this.renderTabs();
    this.syncStore();
    this.notifyNativeDirty();
  }
}

notifyNativeDirty() {
  const hasAnyDirty = Array.from(this.buffers.values()).some((b) => b.isDirty);
  NativeBridge.setDirtyStatus(hasAnyDirty);
}

syncStore() {
  if (store && store.state && store.state.editor) {
    store.state.editor.activeTabId = this.activeTabId;
    store.state.editor.openTabs = Array.from(this.buffers.values()).map((b) => ({
      id: b.id,
      name: b.name,
      path: b.path,
      isDirty: b.isDirty
    }));
  }
}
```

---

## 4. Error Handling & Edge Cases

| Scenario | Handled Condition | Controller Action |
| :--- | :--- | :--- |
| **Duplicate Path Open** | `pathToId.has(normalizedPath)` | Focuses existing tab, does not duplicate buffer or add tab. |
| **Save As Cancelled** | `res.status !== "ok"` or `!res.path` | Aborts save, leaves buffer dirty, no changes to tab strip. |
| **Disk Read Failure** | File missing / permission denied | Logs error, returns `null`, avoids creating broken empty tab. |
| **Disk Write Failure** | Disk full / read-only filesystem | Returns `false`, leaves buffer dirty, alerts developer. |
| **Teardown Aborted** | User cancels dirty save prompt | Aborts `closeTab()`, keeps tab open, active, and dirty. |
| **Non-CodeMirror Fallback** | `window.CodeMirror` undefined | Operates transparently as a headless buffer model. |

---

## 5. Playwright Test Specifications

The buffer controller test suite (`tests/test_editor_buffer_controller.py`) executes automated verification in Chromium:

* **`TC-EBC-01: test_create_buffer_scratch_model`**  
  Asserts creating untitled buffers generates unique IDs, registers in `buffers` map, sets default `name`, and renders in DOM.
* **`TC-EBC-02: test_duplicate_file_open_prevention`**  
  Asserts opening the same canonical path twice returns the existing tab ID and maintains exactly 1 tab in `#editorTabStrip`.
* **`TC-EBC-03: test_dirty_state_tracking_and_native_sync`**  
  Asserts modifying text transitions `isDirty: true`, renders `●`, and dispatches `NativeBridge.setDirtyStatus(true)`.
* **`TC-EBC-04: test_clean_save_workflow`**  
  Asserts saving a modified buffer invokes `NativeBridge.writeFile`, resets `isDirty: false`, removes `●`, and sends `setDirtyStatus(false)`.
* **`TC-EBC-05: test_save_as_untitled_buffer`**  
  Asserts saving an untitled buffer invokes `saveFileDialog`, updates `buffer.path`, `buffer.name`, and file badge icon.
* **`TC-EBC-06: test_guarded_close_cancellation`**  
  Asserts rejecting the unsaved changes dialog prevents tab closure and keeps content intact.
* **`TC-EBC-07: test_view_destruction_and_memory_reclaim`**  
  Asserts closing a tab calls `view.destroy()`, removes container from `#codeEditorHost`, and removes entries from `buffers` and `pathToId`.
* **`TC-EBC-08: test_revert_buffer_from_disk`**  
  Asserts calling `revertBuffer()` reloads original file content from `NativeBridge.readFile` and clears dirty status.
* **`TC-EBC-09: test_bulk_close_and_welcome_screen_sync`**  
  Asserts `closeAllTabs()` prompts appropriately, tears down all views, and displays `#welcomeScreen`.
