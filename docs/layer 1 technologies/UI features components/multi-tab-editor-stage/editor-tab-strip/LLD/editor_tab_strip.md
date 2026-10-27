# Low-Level Design (LLD): Editor Tab Strip

**Document ID:** `ORX-LLD-EDITOR-TAB-STRIP-V1`  
**Version:** `1.0` (Multi-Buffer Tab Navigation & Dirty Tracking Architecture)  
**Parent Document:** `ORX-HLD-EDITOR-TAB-STRIP-V1`  
**Target Codebase:** `DeskAI`  
**Target Files:**
* `src/deskai/static/index.html`
* `src/deskai/static/js/editor.js`
* `src/deskai/static/js/events.js`
* `src/deskai/static/js/bridge.js`
* `src/deskai/static/js/state.js`
* `src/deskai/static/css/components.css`
* `src/deskai/static/css/tokens.css`
* `tests/test_editor_tab_strip.py`
**Status:** Approved for Implementation  
**Date:** October 28, 2026  

---

## 1. Executive Summary & Objective

The **Editor Tab Strip** (`#editorTabStrip`) is the horizontal tab container situated at the top of `#editorStage`. It renders open file buffers, manages active CodeMirror 6 viewport switching, displays unsaved dirty indicators, and facilitates keyboard-accessible buffer navigation.

This Low-Level Design details:
1. The exact DOM specification and accessible attributes for tab elements.
2. The CSS token mappings adhering to the Obsidian Matte + Warm Amber design system.
3. The JavaScript algorithms in `EditorManager` (`renderTabs()`, `detectFileIcon()`, `selectTab()`, and guarded `closeTab()`).
4. Mouse ergonomic bindings (middle-click tab teardown and horizontal wheel scrolling).
5. Comprehensive automated test specifications (`TC-ETS-01` through `TC-ETS-09`).

---

## 2. DOM Hierarchy & Component Layout

```html
<!-- Tab Strip Container inside #editorStage -->
<div 
  class="tab-strip" 
  id="editorTabStrip" 
  role="tablist" 
  aria-label="Open Files" 
  tabindex="-1">
  
  <!-- Active Tab Example -->
  <div 
    class="editor-tab active" 
    role="tab" 
    id="tab-tab-a1b2c3d4"
    data-tab-id="tab-a1b2c3d4" 
    aria-selected="true" 
    aria-controls="editorViewport" 
    tabindex="0" 
    data-action="select-tab" 
    data-param="tab-a1b2c3d4"
    title="/home/user/projects/app/main.py">
    
    <span class="tab-icon" aria-hidden="true">🐍</span>
    <span class="tab-label">main.py</span>
    <!-- Rendered only if buffer.isDirty === true -->
    <span class="tab-dirty-indicator" aria-label="Unsaved changes">●</span>
    
    <button 
      type="button" 
      class="tab-close-btn" 
      data-action="tab-close" 
      data-param="tab-a1b2c3d4" 
      aria-label="Close main.py"
      tabindex="-1">✕</button>
  </div>

  <!-- Inactive Tab Example -->
  <div 
    class="editor-tab" 
    role="tab" 
    id="tab-tab-e5f6a7b8"
    data-tab-id="tab-e5f6a7b8" 
    aria-selected="false" 
    aria-controls="editorViewport" 
    tabindex="-1" 
    data-action="select-tab" 
    data-param="tab-e5f6a7b8"
    title="/home/user/projects/app/app.js">
    
    <span class="tab-icon" aria-hidden="true">🟨</span>
    <span class="tab-label">app.js</span>
    
    <button 
      type="button" 
      class="tab-close-btn" 
      data-action="tab-close" 
      data-param="tab-e5f6a7b8" 
      aria-label="Close app.js"
      tabindex="-1">✕</button>
  </div>
</div>
```

---

## 3. Visual Styling & CSS Token Bindings (`src/deskai/static/css/components.css`)

```css
/* ==========================================================================
   Editor Tab Strip Component
   ========================================================================== */

.tab-strip {
  height: 34px;
  background-color: var(--bg-header);
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  align-items: center;
  overflow-x: auto;
  overflow-y: hidden;
  user-select: none;
  scrollbar-width: thin;
  scrollbar-color: var(--border-regular) transparent;
}

.tab-strip::-webkit-scrollbar {
  height: 3px;
}

.tab-strip::-webkit-scrollbar-thumb {
  background-color: var(--border-regular);
  border-radius: 2px;
}

.tab-strip::-webkit-scrollbar-thumb:hover {
  background-color: var(--text-muted);
}

.editor-tab {
  height: 100%;
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 0 var(--space-3);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  border-right: 1px solid var(--border-subtle);
  border-top: 2px solid transparent;
  cursor: pointer;
  background-color: transparent;
  transition: all var(--transition-fast);
  white-space: nowrap;
  flex-shrink: 0;
  box-sizing: border-box;
}

.editor-tab:hover {
  background-color: var(--bg-hover);
  color: var(--text-primary);
}

.editor-tab[aria-selected="true"] {
  background-color: var(--bg-surface);
  color: var(--color-primary);
  border-top: 2px solid var(--color-primary);
  font-weight: 600;
}

.tab-icon {
  font-size: var(--text-xs);
  display: inline-flex;
  align-items: center;
}

.tab-label {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tab-dirty-indicator {
  font-size: 8px;
  color: var(--color-warning);
  line-height: 1;
}

.tab-close-btn {
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-size: 11px;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: var(--radius-sm);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
}

.tab-close-btn:hover {
  background-color: var(--bg-hover);
  color: var(--color-danger);
}

.tab-close-btn:focus-visible {
  outline: 2px solid var(--border-focus);
}

@media (forced-colors: active) {
  .editor-tab[aria-selected="true"] {
    border-top: 2px solid Highlight;
  }
}
```

---

## 4. Implementation Details (`src/deskai/static/js/editor.js`)

### 4.1 Semantic File Icon Mapping
Different file extensions are paired with distinct semantic icon identifiers:

```javascript
detectFileIcon(filename) {
  if (!filename) return "📄";
  const lower = filename.toLowerCase();
  if (lower.endsWith(".py") || lower.endsWith(".pyw")) return "🐍";
  if (lower.endsWith(".js") || lower.endsWith(".mjs") || lower.endsWith(".cjs")) return "🟨";
  if (lower.endsWith(".ts") || lower.endsWith(".tsx")) return "🔷";
  if (lower.endsWith(".json")) return "📦";
  if (lower.endsWith(".html") || lower.endsWith(".htm")) return "🌐";
  if (lower.endsWith(".css") || lower.endsWith(".scss")) return "🎨";
  if (lower.endsWith(".md") || lower.endsWith(".markdown")) return "📝";
  if (lower.endsWith(".sh") || lower.endsWith(".bash") || lower.endsWith(".zsh")) return "🐚";
  if (lower.endsWith(".sql")) return "🗄️";
  return "📄";
}
```

### 4.2 Tab Rendering Implementation (`renderTabs()`)

```javascript
renderTabs() {
  if (!this.tabStrip) return;
  this.tabStrip.replaceChildren();

  for (const [id, buffer] of this.buffers.entries()) {
    const isSelected = id === this.activeTabId;

    const tabEl = document.createElement("div");
    tabEl.className = isSelected ? "editor-tab active" : "editor-tab";
    tabEl.setAttribute("role", "tab");
    tabEl.id = `tab-${id}`;
    tabEl.setAttribute("data-tab-id", id);
    tabEl.setAttribute("aria-selected", isSelected ? "true" : "false");
    tabEl.setAttribute("aria-controls", "editorViewport");
    tabEl.setAttribute("tabindex", isSelected ? "0" : "-1");
    tabEl.setAttribute("data-action", "select-tab");
    tabEl.setAttribute("data-param", id);
    if (buffer.path) {
      tabEl.setAttribute("title", buffer.path);
    }

    // 1. Icon badge
    const iconSpan = document.createElement("span");
    iconSpan.className = "tab-icon";
    iconSpan.setAttribute("aria-hidden", "true");
    iconSpan.textContent = this.detectFileIcon(buffer.name);
    tabEl.appendChild(iconSpan);

    // 2. Filename label (strictly textContent)
    const labelSpan = document.createElement("span");
    labelSpan.className = "tab-label";
    labelSpan.textContent = buffer.name;
    tabEl.appendChild(labelSpan);

    // 3. Unsaved dirty indicator dot
    if (buffer.isDirty) {
      const dirtySpan = document.createElement("span");
      dirtySpan.className = "tab-dirty-indicator";
      dirtySpan.setAttribute("aria-label", "Unsaved changes");
      dirtySpan.textContent = "●";
      tabEl.appendChild(dirtySpan);
    }

    // 4. Close button
    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "tab-close-btn";
    closeBtn.setAttribute("data-action", "tab-close");
    closeBtn.setAttribute("data-param", id);
    closeBtn.setAttribute("aria-label", `Close ${buffer.name}`);
    closeBtn.setAttribute("tabindex", "-1");
    closeBtn.textContent = "✕";
    tabEl.appendChild(closeBtn);

    this.tabStrip.appendChild(tabEl);
  }
}
```

### 4.3 Tab Selection & Smooth Scrolling (`selectTab()`)

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
        }
      } else {
        buffer.container.style.display = "none";
      }
    }
  }

  this.renderTabs();

  // Smoothly scroll active tab into view if overflowing
  if (this.tabStrip) {
    const activeEl = this.tabStrip.querySelector(`[data-tab-id="${id}"]`);
    if (activeEl && typeof activeEl.scrollIntoView === "function") {
      activeEl.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
    }
  }
}
```

### 4.4 Guarded Tab Teardown (`closeTab()`)

```javascript
async closeTab(id) {
  if (!this.buffers.has(id)) return;
  const buffer = this.buffers.get(id);

  // If dirty, prompt before destroying
  if (buffer.isDirty) {
    const shouldSave = confirm(`Do you want to save the changes you made to ${buffer.name}?`);
    if (shouldSave) {
      const saved = await this.saveBuffer(id);
      if (!saved) return; // User cancelled save dialog or write failed
    }
  }

  if (buffer.view) {
    buffer.view.destroy();
  }
  if (buffer.container && buffer.container.parentElement) {
    buffer.container.parentElement.removeChild(buffer.container);
  }

  this.buffers.delete(id);

  if (store && store.state && store.state.editor) {
    store.state.editor.openTabs = Array.from(this.buffers.values()).map(b => ({
      id: b.id,
      name: b.name,
      path: b.path,
      isDirty: b.isDirty
    }));
  }

  if (this.activeTabId === id) {
    const nextTab = this.buffers.keys().next().value;
    if (nextTab) {
      this.selectTab(nextTab);
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

  const hasAnyDirty = Array.from(this.buffers.values()).some(b => b.isDirty);
  NativeBridge.setDirtyStatus(hasAnyDirty);

  this.renderTabs();
}
```

### 4.5 Keyboard Roving Focus Navigation

```javascript
// Inside constructor of EditorManager
if (this.tabStrip) {
  this.tabStrip.addEventListener("keydown", (e) => {
    const tabIds = Array.from(this.buffers.keys());
    if (tabIds.length === 0) return;
    const currentIndex = tabIds.indexOf(this.activeTabId);

    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      if (tabIds.length <= 1) return;
      let newIndex = e.key === "ArrowRight" ? currentIndex + 1 : currentIndex - 1;
      if (newIndex >= tabIds.length) newIndex = 0;
      if (newIndex < 0) newIndex = tabIds.length - 1;
      const newTabId = tabIds[newIndex];
      this.selectTab(newTabId);
      const activeEl = this.tabStrip.querySelector(`[data-tab-id="${newTabId}"]`);
      if (activeEl) activeEl.focus();
    } else if (e.key === "Home") {
      e.preventDefault();
      const firstId = tabIds[0];
      this.selectTab(firstId);
      const activeEl = this.tabStrip.querySelector(`[data-tab-id="${firstId}"]`);
      if (activeEl) activeEl.focus();
    } else if (e.key === "End") {
      e.preventDefault();
      const lastId = tabIds[tabIds.length - 1];
      this.selectTab(lastId);
      const activeEl = this.tabStrip.querySelector(`[data-tab-id="${lastId}"]`);
      if (activeEl) activeEl.focus();
    } else if (e.key === "Delete") {
      e.preventDefault();
      if (this.activeTabId) {
        this.closeTab(this.activeTabId);
      }
    }
  });
}
```

---

## 5. Mouse Ergonomics & Wheel Translation (`src/deskai/static/js/events.js`)

### 5.1 Middle-Click (Button 1) Tab Closure
```javascript
// Inside initGlobalEvents() in events.js
document.addEventListener("auxclick", (e) => {
  if (e.button === 1) { // Middle click / wheel button
    const tabEl = e.target.closest(".editor-tab");
    if (tabEl) {
      e.preventDefault();
      const tabId = tabEl.getAttribute("data-tab-id");
      if (tabId && window.EditorManager) {
        window.EditorManager.closeTab(tabId);
      }
    }
  }
});
```

### 5.2 Horizontal Wheel Scrolling Translation
```javascript
const tabStrip = document.getElementById("editorTabStrip");
if (tabStrip) {
  tabStrip.addEventListener("wheel", (e) => {
    if (e.deltaY !== 0) {
      e.preventDefault();
      tabStrip.scrollLeft += e.deltaY;
    }
  }, { passive: false });
}
```

---

## 6. Detailed Automated Test Specifications (`tests/test_editor_tab_strip.py`)

### `TC-ETS-01`: Accessible Markup & Semantics
* **Setup:** Load `index.html` in headless Chromium.
* **Assertions:**
  1. `#editorTabStrip` has `role="tablist"` and `aria-label="Open Files"`.
  2. Tab strip is initially empty (0 child `.editor-tab` elements).

### `TC-ETS-02`: Dynamic Tab Creation & Extension Icons
* **Setup:** Create buffers `script.py`, `app.js`, `doc.md`.
* **Assertions:**
  1. Tab strip contains 3 `.editor-tab` elements.
  2. `script.py` tab has icon `🐍`.
  3. `app.js` tab has icon `🟨`.
  4. `doc.md` tab has icon `📝`.

### `TC-ETS-03`: Tab Selection Switching
* **Setup:** Open 2 tabs (`tabA`, `tabB`). Click `tabA`.
* **Assertions:**
  1. `tabA` has `aria-selected="true"`, `tabindex="0"`, `.active`.
  2. `tabB` has `aria-selected="false"`, `tabindex="-1"`.
  3. Corresponding CodeMirror container is visible.

### `TC-ETS-04`: Keyboard Roving Navigation (Arrows, Home, End)
* **Setup:** Open 3 tabs (`tab1`, `tab2`, `tab3`). Focus `tab1`.
* **Assertions:**
  1. Press `ArrowRight` -> `tab2` becomes active and focused.
  2. Press `End` -> `tab3` becomes active and focused.
  3. Press `Home` -> `tab1` becomes active and focused.

### `TC-ETS-05`: Middle-Click Tab Closure
* **Setup:** Open 2 tabs. Simulate `auxclick` with `button: 1` on tab 1.
* **Assertions:**
  1. Tab 1 is closed.
  2. Tab 2 becomes active.
  3. Tab count is 1.

### `TC-ETS-06`: Dirty Indicator Lifecycle
* **Setup:** Open tab `test.py`. Mark buffer dirty via `markDirty(tabId, true)`.
* **Assertions:**
  1. `.tab-dirty-indicator` (`●`) is visible inside tab.
  2. Has `aria-label="Unsaved changes"`.
  3. Calling `markDirty(tabId, false)` removes the dirty dot.

### `TC-ETS-07`: Guarded Teardown with Unsaved Edits
* **Setup:** Open dirty tab. Mock `window.confirm = () => false`. Call `closeTab(tabId)`.
* **Assertions:**
  1. Tab remains open (close aborted).
  2. Change mock to `true`. Tab is closed cleanly.

### `TC-ETS-08`: Empty State Handoff
* **Setup:** Open 1 tab, then close it.
* **Assertions:**
  1. `#editorTabStrip` has 0 tabs.
  2. `#welcomeScreen` is displayed and active.

### `TC-ETS-09`: Safe DOM Injection (Strict XSS Defense)
* **Setup:** Create buffer named `<script>alert(1)</script><img src=x onerror=alert(2)>.py`.
* **Assertions:**
  1. No scripts execute.
  2. No `<img>` elements created.
  3. `.tab-label` text content matches raw string verbatim.

---

## 7. Implementation Checklist

- [ ] Update `detectFileIcon()` in `src/deskai/static/js/editor.js`.
- [ ] Enhance `renderTabs()` in `src/deskai/static/js/editor.js` with semantic icons, titles, and dirty indicator accessibility.
- [ ] Implement `Home`, `End`, and `Delete` keyboard handlers on `#editorTabStrip`.
- [ ] Add `auxclick` middle-click tab closure listener in `src/deskai/static/js/events.js`.
- [ ] Add horizontal wheel scroll translation on `#editorTabStrip` in `src/deskai/static/js/events.js`.
- [ ] Enhance `closeTab()` with dirty confirmation gate.
- [ ] Update `components.css` with active top border indicator and scrollbar styling.
- [ ] Create automated test suite in `tests/test_editor_tab_strip.py`.
