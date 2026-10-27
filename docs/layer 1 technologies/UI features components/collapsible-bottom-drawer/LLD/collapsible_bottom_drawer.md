# Low-Level Design (LLD): Collapsible Bottom Drawer

**Document ID:** `ORX-LLD-COLLAPSIBLE-BOTTOM-DRAWER-V1`  
**Version:** `1.0` (Defect-Resolved & Synchronized with Implemented Vanilla JS & PyWebView Architecture)  
**Parent Document:** `ORX-HLD-COLLAPSIBLE-BOTTOM-DRAWER-V1`  
**Target Codebase:** `DeskAI`  
**Primary Target Files:**
* `src/deskai/static/index.html` (Lines 95-163)
* `src/deskai/static/css/components.css` (Lines 316-360)
* `src/deskai/static/css/layout.css` (Lines 118-142)
* `src/deskai/static/js/events.js` (`initResizers` & centralized delegation)
**Status:** Approved for Implementation / Implemented  
**Date:** October 27, 2026  

---

## 1. Executive Summary & Objective

The **Collapsible Bottom Drawer** (`#bottomDrawer`) is the unified parent layout container for all secondary operational panels in DeskAI (`Terminal`, `Output`, `Problems`, `Ports`). Situated beneath `#editorStage`, it provides bidirectional horizontal split-pane resizing, instant collapse/restore capabilities, and seamless panel synchronization.

This document details the concrete DOM hierarchy, mouse drag and keyboard math algorithms, CSS layout rules, design token bindings, and automated test specifications.

---

## 2. DOM Hierarchy & Component Layout

The parent container and horizontal split resizer reside inside `<section class="center-workspace">` in `src/deskai/static/index.html`:

```html
<!-- Horizontal Draggable Resizer Boundary -->
<div 
  class="resizer-row" 
  id="resizerBottom" 
  role="separator" 
  aria-orientation="horizontal" 
  tabindex="0" 
  aria-label="Resize Bottom Drawer"
  aria-valuenow="240"
  aria-valuemin="60">
</div>

<!-- Collapsible Bottom Drawer Parent Region -->
<section class="bottom-drawer" id="bottomDrawer" role="region" aria-label="Output Drawer">
  <!-- 1. Drawer Header (32px Fixed Strip) -->
  <div class="drawer-header">
    <div class="drawer-tabs" role="tablist" aria-label="Drawer Panels">
      <button class="drawer-tab active" data-action="drawer-tab" data-target="terminal" role="tab" aria-selected="true" aria-controls="terminalPanel" id="tab-terminal">Terminal</button>
      <button class="drawer-tab" data-action="drawer-tab" data-target="output" role="tab" aria-selected="false" aria-controls="outputPanel" id="tab-output">Output</button>
      <button class="drawer-tab" data-action="drawer-tab" data-target="problems" role="tab" aria-selected="false" aria-controls="problemsPanel" id="tab-problems">Problems</button>
      <button class="drawer-tab" data-action="drawer-tab" data-target="ports" role="tab" aria-selected="false" aria-controls="portsPanel" id="tab-ports">Ports</button>
    </div>
    <button class="icon-btn close-drawer-btn" data-action="toggle-drawer" aria-label="Toggle Drawer" title="Toggle Drawer">─</button>
  </div>

  <!-- 2. Scrollable Drawer Viewport Hosting Subsystem Panels -->
  <div class="drawer-content" id="drawerContent">
    <!-- Sub-Panel 1: Terminal -->
    <div class="drawer-panel active" id="terminalPanel" role="tabpanel" aria-labelledby="tab-terminal">
      <pre class="terminal-view" id="terminalOutput"><code>DeskAI Host Shell Ready. Workspace active.</code></pre>
    </div>

    <!-- Sub-Panel 2: Output -->
    <div class="drawer-panel" id="outputPanel" role="tabpanel" aria-labelledby="tab-output" hidden>
      <pre class="terminal-view" id="channelOutput"><code>[DeskAI System] Supervisor active on loopback. Ready for tasks.</code></pre>
    </div>

    <!-- Sub-Panel 3: Problems -->
    <div class="drawer-panel" id="problemsPanel" role="tabpanel" aria-labelledby="tab-problems" hidden>
      <div class="problems-view">
        <span class="problems-empty">No problems have been detected in the workspace.</span>
      </div>
    </div>

    <!-- Sub-Panel 4: Ports -->
    <div class="drawer-panel" id="portsPanel" role="tabpanel" aria-labelledby="tab-ports" hidden>
      <div class="ports-toolbar">...</div>
      <div class="ports-table-container">...</div>
    </div>
  </div>
</section>
```

---

## 3. Concrete JavaScript Implementation (`src/deskai/static/js/events.js`)

Interactive resizing and collapse transitions are managed in `initResizers()` and the root event delegation handler:

### 3.1 Resizer Mouse & Keyboard Orchestration
```javascript
export function initResizers() {
  const resizerBottom = document.getElementById("resizerBottom");
  const bottomDrawer = document.getElementById("bottomDrawer");
  let lastDrawerHeight = 240;

  if (resizerBottom && bottomDrawer) {
    let isDraggingY = false;
    let startY = 0;
    let startHeight = 0;

    // 1. Mouse Drag Start
    resizerBottom.addEventListener("mousedown", (e) => {
      isDraggingY = true;
      startY = e.clientY;
      startHeight = bottomDrawer.offsetHeight;
      document.body.classList.add("resizing-row");
      e.preventDefault();
    });

    // 2. Global Mouse Drag Tracking
    window.addEventListener("mousemove", (e) => {
      if (!isDraggingY) return;
      const deltaY = startY - e.clientY; // Dragging UP increases bottom drawer height
      let newHeight = startHeight + deltaY;

      // Auto-collapse snap threshold
      if (newHeight < 50) {
        bottomDrawer.classList.add("collapsed");
        return;
      }

      // Clamping limits
      bottomDrawer.classList.remove("collapsed");
      const minHeight = 60;
      const maxHeight = window.innerHeight - 150;
      newHeight = Math.max(minHeight, Math.min(newHeight, maxHeight));

      bottomDrawer.style.height = `${newHeight}px`;
      resizerBottom.setAttribute("aria-valuenow", String(Math.round(newHeight)));
      lastDrawerHeight = newHeight;
    });

    // 3. Mouse Drag End
    window.addEventListener("mouseup", () => {
      if (isDraggingY) {
        isDraggingY = false;
        document.body.classList.remove("resizing-row");
      }
    });

    // 4. Double-Click Toggle
    resizerBottom.addEventListener("dblclick", () => {
      const isCollapsed = bottomDrawer.classList.contains("collapsed");
      if (isCollapsed) {
        bottomDrawer.classList.remove("collapsed");
        bottomDrawer.style.height = `${lastDrawerHeight || 240}px`;
        resizerBottom.setAttribute("aria-valuenow", String(Math.round(lastDrawerHeight || 240)));
      } else {
        lastDrawerHeight = bottomDrawer.offsetHeight;
        bottomDrawer.classList.add("collapsed");
        resizerBottom.setAttribute("aria-valuenow", "32");
      }
    });

    // 5. Accessible Keyboard Step Resizing
    resizerBottom.addEventListener("keydown", (e) => {
      if (e.key === "ArrowUp" || e.key === "ArrowDown") {
        e.preventDefault();
        bottomDrawer.classList.remove("collapsed");
        const currentH = bottomDrawer.offsetHeight;
        const step = e.key === "ArrowUp" ? 20 : -20;
        const minHeight = 60;
        const maxHeight = window.innerHeight - 150;
        const newH = Math.max(minHeight, Math.min(currentH + step, maxHeight));
        
        bottomDrawer.style.height = `${newH}px`;
        resizerBottom.setAttribute("aria-valuenow", String(Math.round(newH)));
        lastDrawerHeight = newH;
      }
    });
  }
}
```

### 3.2 Action Delegation Handlers
```javascript
// Toggle Drawer via Minimize Button (─)
case "toggle-drawer": {
  const drawer = document.getElementById("bottomDrawer");
  if (drawer) {
    drawer.classList.toggle("collapsed");
  }
  break;
}

// Drawer Tab Switching
case "drawer-tab": {
  const target = trigger.getAttribute("data-target");
  if (!target) return;

  // Visual & ARIA Tab Selection
  document.querySelectorAll(".drawer-tab").forEach(t => {
    t.classList.remove("active");
    t.setAttribute("aria-selected", "false");
  });
  trigger.classList.add("active");
  trigger.setAttribute("aria-selected", "true");

  // Panel Activation
  document.querySelectorAll(".drawer-panel").forEach(panel => {
    if (panel.id === `${target}Panel`) {
      panel.classList.add("active");
      panel.removeAttribute("hidden");
    } else {
      panel.classList.remove("active");
      panel.setAttribute("hidden", "");
    }
  });

  if (target === "ports" && window.DeskAIPorts) {
    window.DeskAIPorts.refresh();
  }
  break;
}
```

---

## 4. CSS Styling & Layout Specifications

Styles are partitioned cleanly between `layout.css` (split-pane positioning & resizer) and `components.css` (drawer internals):

### 4.1 Resizer Row Styling (`src/deskai/static/css/layout.css`)
```css
.resizer-row {
  height: 4px;
  cursor: row-resize;
  background-color: transparent;
  position: relative;
  z-index: 10;
  flex-shrink: 0;
  transition: background-color var(--transition-fast);
}

.resizer-row:hover,
body.resizing-row .resizer-row {
  background-color: var(--accent-primary);
}

.resizer-row:focus-visible {
  outline: 2px solid var(--accent-primary);
  outline-offset: -1px;
}

body.resizing-row {
  cursor: row-resize !important;
  user-select: none;
}
```

### 4.2 Drawer Container Styling (`src/deskai/static/css/components.css`)
```css
.bottom-drawer {
  height: 240px;
  background-color: var(--bg-header);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.bottom-drawer.collapsed {
  height: 32px;
}

.drawer-header {
  height: 32px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 12px;
  background-color: var(--bg-header);
  border-bottom: 1px solid var(--border-subtle);
  user-select: none;
  flex-shrink: 0;
}

.drawer-content {
  flex: 1;
  overflow: auto;
  padding: var(--space-2);
}
```

---

## 5. Accessibility (WCAG 2.1 AA) Specifications

1. **Semantic Landmark & Separator Roles:**
   * Container: `<section class="bottom-drawer" id="bottomDrawer" role="region" aria-label="Output Drawer">`.
   * Separator: `<div class="resizer-row" role="separator" aria-orientation="horizontal" tabindex="0">` with live `aria-valuenow` updates.
2. **Keyboard Operability:**
   * `ArrowUp` expands drawer by 20px; `ArrowDown` shrinks drawer by 20px.
   * `Tab` key reaches both the resizer separator and the drawer tablist sequentially.
3. **Focus Indication:**
   * High-contrast focus outline on `#resizerBottom` via `:focus-visible` without displacing neighboring layout elements.

---

## 6. Automated Test Plan & Traceability Matrix

Automated verification is covered across unit, contract, and end-to-end tests:

| Test ID | Test Target | Verification Scope | Reference Test |
| :--- | :--- | :--- | :--- |
| **TC-CBD-01** | Resizer Declaration | `index.html` declares `#resizerBottom` with `role="separator"` and `aria-orientation="horizontal"` | `test_ports_tab.py` |
| **TC-CBD-02** | CSS Resizer Rule | `layout.css` defines `.resizer-row` with `cursor: row-resize;` | `test_ports_tab.py` |
| **TC-CBD-03** | Resizer Event Binding | `events.js` binds `#resizerBottom` mouse, keyboard, and dblclick events | `test_ports_tab.py` |
| **TC-CBD-04** | Collapsed Height Rule | `.bottom-drawer.collapsed` has explicit `height: 32px;` | CSS Inspection Test |
| **TC-CBD-05** | Drag Calculation Math | Dragging upwards increases drawer height; dragging below 50px adds `.collapsed` | Playwright E2E Test |
| **TC-CBD-06** | Double-Click Reset | Double-clicking `#resizerBottom` toggles between 32px and last drawer height | Playwright E2E Test |
| **TC-CBD-07** | Keyboard Arrow Steps | `ArrowUp`/`ArrowDown` steps drawer height by $\pm 20\text{px}$ | Playwright E2E Test |
