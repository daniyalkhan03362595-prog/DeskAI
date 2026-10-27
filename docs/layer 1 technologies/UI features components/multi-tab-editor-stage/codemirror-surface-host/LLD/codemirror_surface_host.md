# Low-Level Design (LLD): CodeMirror Surface Host

**Document ID:** `ORX-LLD-CODEMIRROR-SURFACE-HOST-V1`  
**Version:** `1.0` (Vendored CodeMirror 6 Studio Surface Architecture)  
**Parent Document:** `ORX-HLD-CODEMIRROR-SURFACE-HOST-V1`  
**Target Codebase:** `DeskAI`  
**Target Files:**
* `src/deskai/static/index.html`
* `src/deskai/static/vendor/codemirror.bundle.js`
* `src/deskai/static/vendor/MANIFEST.json`
* `src/deskai/static/js/editor.js`
* `src/deskai/static/js/events.js`
* `src/deskai/static/css/components.css`
* `src/deskai/static/css/tokens.css`
* `tests/test_codemirror_surface_host.py`
**Status:** Approved for Implementation  
**Date:** October 28, 2026  

---

## 1. Executive Summary & Objective

The **CodeMirror Surface Host** (`#codeEditorHost`) is the mounting container inside `#editorViewport` that encapsulates CodeMirror 6 `EditorView` surfaces for each open editor buffer.

This Low-Level Design specifies:
1. The concrete DOM hierarchy of `#codeEditorHost` and child `.editor-view-container` elements.
2. Complete CSS token mappings adhering to the Obsidian Matte + Warm Amber palette.
3. JavaScript algorithms in `EditorManager` (`createBuffer()`, `selectTab()`, `closeTab()`, `detectLanguage()`).
4. Automatic layout reflow via `ResizeObserver` calling `requestMeasure()`.
5. Keyboard trap avoidance mechanisms (WCAG 2.1 AA).
6. 9 automated Playwright and unit test specifications (`TC-CMH-01` through `TC-CMH-09`).

---

## 2. DOM Hierarchy & Component Structure

```html
<!-- Viewport container hosting Welcome Screen and Code Surface -->
<div class="editor-viewport" id="editorViewport" role="tabpanel" aria-label="Active File Editor">
  
  <!-- Welcome Screen Overlay (Visible when openTabs.length === 0) -->
  <div class="welcome-screen" id="welcomeScreen" role="region" aria-label="Welcome and Quick Actions" hidden>
    <!-- Welcome card content -->
  </div>

  <!-- CodeMirror Surface Host (Hosts open document buffers) -->
  <div 
    class="codemirror-host" 
    id="codeEditorHost" 
    role="region" 
    aria-label="Code Surface" 
    tabindex="-1">
    
    <!-- Buffer 1 View Container (Active) -->
    <div 
      class="editor-view-container" 
      id="editor-container-tab-8f3b211a" 
      data-buffer-id="tab-8f3b211a" 
      style="display: block;">
      
      <div class="cm-editor cm-focused cm-deskai-theme">
        <!-- Gutters (Line Numbers) -->
        <div class="cm-gutters" aria-hidden="true">
          <div class="cm-gutter cm-lineNumbers">
            <div class="cm-gutterElement">1</div>
            <div class="cm-gutterElement">2</div>
            <div class="cm-gutterElement">3</div>
          </div>
        </div>
        
        <!-- Scrollable Surface -->
        <div class="cm-scroller" tabindex="0">
          <div 
            class="cm-content" 
            role="textbox" 
            aria-multiline="true" 
            aria-label="Code Editor" 
            contenteditable="true" 
            spellcheck="false" 
            autocorrect="off" 
            autocapitalize="off">
            <div class="cm-line"><span class="tok-keyword">import</span> <span class="tok-variableName">os</span></div>
            <div class="cm-line"><span class="tok-keyword">def</span> <span class="tok-variableName">run</span>():</div>
            <div class="cm-line">    <span class="tok-keyword">return</span> <span class="tok-number">True</span></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Buffer 2 View Container (Inactive - Retained in DOM) -->
    <div 
      class="editor-view-container" 
      id="editor-container-tab-a4c19d20" 
      data-buffer-id="tab-a4c19d20" 
      style="display: none;">
      <!-- Preserved cm-editor DOM tree -->
    </div>
  </div>
</div>
```

---

## 3. Visual Styling & CSS Token Bindings (`src/deskai/static/css/components.css`)

```css
/* ==========================================================================
   CodeMirror 6 Surface Host & Workbench Theming
   ========================================================================== */

.codemirror-host {
  width: 100%;
  height: 100%;
  position: relative;
  overflow: hidden;
  background-color: var(--bg-surface);
}

.editor-view-container {
  width: 100%;
  height: 100%;
  position: absolute;
  inset: 0;
}

/* Master CodeMirror Container */
.editor-view-container .cm-editor {
  height: 100%;
  background-color: var(--bg-surface);
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  outline: none !important;
}

/* Scroller & Content */
.editor-view-container .cm-scroller {
  overflow: auto;
  font-family: var(--font-mono);
  line-height: 1.6;
  scrollbar-width: thin;
  scrollbar-color: var(--border-regular) transparent;
}

.editor-view-container .cm-scroller::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.editor-view-container .cm-scroller::-webkit-scrollbar-thumb {
  background-color: var(--border-regular);
  border-radius: 3px;
}

.editor-view-container .cm-content {
  padding: var(--space-2) 0;
  caret-color: var(--color-primary);
}

/* Gutters & Line Numbers */
.editor-view-container .cm-gutters {
  background-color: var(--bg-header);
  color: var(--text-muted);
  border-right: 1px solid var(--border-subtle);
  user-select: none;
}

.editor-view-container .cm-gutterElement {
  padding: 0 var(--space-2) 0 var(--space-3);
  min-width: 24px;
  text-align: right;
  font-size: var(--text-xs);
  line-height: 1.6;
}

.editor-view-container .cm-activeLineGutter {
  color: var(--color-amber);
  font-weight: 600;
  background-color: var(--bg-hover);
}

/* Active Line & Selection */
.editor-view-container .cm-activeLine {
  background-color: rgba(255, 255, 255, 0.03);
}

.editor-view-container .cm-selectionBackground,
.editor-view-container ::selection {
  background-color: rgba(217, 155, 38, 0.25) !important;
}

/* Focus Ring */
.editor-view-container .cm-focused {
  outline: none;
}
```

---

## 4. Implementation Details in `EditorManager` (`src/deskai/static/js/editor.js`)

### 4.1 Surface Mount & Buffer Initialization

```javascript
createBuffer(name = "untitled.txt", content = "", path = null) {
  const id = "tab-" + crypto.randomUUID().slice(0, 8);
  const buffer = {
    id,
    name,
    path: path || null,
    content,
    isDirty: false,
    state: null,
    view: null,
    container: null
  };

  if (typeof window !== "undefined" && window.CodeMirror && window.CodeMirror.EditorState) {
    const { EditorState, EditorView, createBasicExtensions } = window.CodeMirror;
    
    // Keyboard trap escape extension
    const keyboardTrapHandler = EditorView.domEventHandlers({
      keydown: (e, view) => {
        if (e.key === "Escape") {
          // Blur editor surface to allow standard Tab navigation
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
      language: this.detectLanguage(name),
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
      doc: content,
      extensions
    });

    buffer.container = document.createElement("div");
    buffer.container.className = "editor-view-container";
    buffer.container.id = `editor-container-${id}`;
    buffer.container.setAttribute("data-buffer-id", id);
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

  if (store && store.state && store.state.editor) {
    store.state.editor.openTabs = Array.from(this.buffers.values()).map(b => ({
      id: b.id,
      name: b.name,
      path: b.path,
      isDirty: b.isDirty
    }));
  }

  this.renderTabs();
  this.selectTab(id);
  return id;
}
```

### 4.2 Viewport Switching & Geometry Reflow

```javascript
selectTab(id) {
  if (!this.buffers.has(id)) return;
  this.activeTabId = id;
  if (store && store.state && store.state.editor) {
    store.state.editor.activeTabId = id;
  }

  if (window.DeskAIWelcome) {
    window.DeskAIWelcome.sync();
  } else if (this.welcomeScreen) {
    this.welcomeScreen.style.display = "none";
  }

  for (const [bufId, buffer] of this.buffers.entries()) {
    if (buffer.container) {
      if (bufId === id) {
        buffer.container.style.display = "block";
        if (this.editorHost && buffer.container.parentElement !== this.editorHost) {
          this.editorHost.appendChild(buffer.container);
        }
        if (buffer.view) {
          buffer.view.focus();
          if (typeof buffer.view.requestMeasure === "function") {
            buffer.view.requestMeasure();
          }
        }
      } else {
        buffer.container.style.display = "none";
      }
    }
  }

  this.renderTabs();

  if (this.tabStrip) {
    const activeEl = this.tabStrip.querySelector(`[data-tab-id="${id}"]`);
    if (activeEl && typeof activeEl.scrollIntoView === "function") {
      activeEl.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
    }
  }
}
```

### 4.3 Container ResizeObserver Setup

```javascript
// Inside constructor of EditorManager
if (this.editorHost && typeof ResizeObserver !== "undefined") {
  this.resizeObserver = new ResizeObserver(() => {
    if (this.activeTabId && this.buffers.has(this.activeTabId)) {
      const activeBuf = this.buffers.get(this.activeTabId);
      if (activeBuf.view && typeof activeBuf.view.requestMeasure === "function") {
        requestAnimationFrame(() => activeBuf.view.requestMeasure());
      }
    }
  });
  this.resizeObserver.observe(this.editorHost);
}
```

---

## 5. Detailed Automated Test Specifications (`tests/test_codemirror_surface_host.py`)

### `TC-CMH-01`: Accessible Host Semantics
* **Setup:** Load `index.html` in headless Chromium.
* **Assertions:**
  1. `#codeEditorHost` possesses `role="region"`.
  2. Attribute `aria-label="Code Surface"` is present.

### `TC-CMH-02`: CodeMirror 6 Mounting
* **Setup:** Call `window.EditorManager.createBuffer("demo.py", "x = 10")`.
* **Assertions:**
  1. `.editor-view-container` is created inside `#codeEditorHost`.
  2. `.cm-editor` is mounted inside container.
  3. `.cm-content` has `contenteditable="true"` and `role="textbox"`.

### `TC-CMH-03`: Gutters & Line Number Rendering
* **Setup:** Create a buffer with 5 lines of code.
* **Assertions:**
  1. `.cm-gutters` exists.
  2. `.cm-lineNumbers` has 5 `.cm-gutterElement` elements with text `1`, `2`, `3`, `4`, `5`.

### `TC-CMH-04`: Token Syntax Highlighting
* **Setup:** Create a Python buffer: `def calc(): return 42`.
* **Assertions:**
  1. Keyword token `def` has syntax highlight span with class `.tok-keyword`.
  2. Function identifier `calc` has `.tok-variableName` or `.tok-definition`.
  3. Literal `42` has `.tok-number`.

### `TC-CMH-05`: View State & History Retention Across Tab Switches
* **Setup:**
  1. Create `tabA` and type text.
  2. Create `tabB`.
  3. Switch back to `tabA`.
* **Assertions:**
  1. `tabA`'s content and DOM structure were NOT recreated.
  2. Undo history in `tabA` functions via `history` extension without data loss.

### `TC-CMH-06`: ResizeObserver Geometry Reflow
* **Setup:** Change `#codeEditorHost` width from 600px to 800px.
* **Assertions:**
  1. `requestMeasure()` is executed.
  2. Line widths and scroller geometry adapt without DOM errors.

### `TC-CMH-07`: Keyboard Trap Escape Handler
* **Setup:** Focus `.cm-content`. Press `Escape`.
* **Assertions:**
  1. `.cm-content` loses active keyboard lock.
  2. Focus transfers back to the active tab in `#editorTabStrip`.

### `TC-CMH-08`: Teardown & View Destruction
* **Setup:** Create a buffer, then close it via `closeTab(id)`.
* **Assertions:**
  1. `buffer.view.destroy()` was called.
  2. `.editor-view-container` is removed from `#codeEditorHost`.

### `TC-CMH-09`: Safe Plaintext Rendering (XSS Invariant)
* **Setup:** Create buffer containing `<script id="cmXss">window._cmXss=true;</script>`.
* **Assertions:**
  1. No script executes (`window._cmXss === undefined`).
  2. Text is rendered strictly as plain text nodes inside `.cm-line`.

---

## 6. Implementation Checklist

- [ ] Verify `codemirror.bundle.js` exports `EditorView`, `EditorState`, `createBasicExtensions`.
- [ ] Add `keyboardTrapHandler` (`Escape` key disengagement) into `createBasicExtensions` in `src/deskai/static/js/editor.js`.
- [ ] Add `ResizeObserver` on `#codeEditorHost` triggering `requestMeasure()` on the active view.
- [ ] Enhance CSS in `src/deskai/static/css/components.css` with active line gutter, selection, and scrollbar styling.
- [ ] Create automated test suite in `tests/test_codemirror_surface_host.py`.
