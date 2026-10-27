# Low-Level Design (LLD): Collapsible Bottom Drawer

**Document ID:** `ORX-LLD-COLLAPSIBLE-BOTTOM-DRAWER-V1`  
**Version:** `1.1` (Synchronized with Implemented Vanilla JS & PyWebView Architecture)  
**Parent Document:** `ORX-HLD-COLLAPSIBLE-BOTTOM-DRAWER-V1`  
**Target Codebase:** `DeskAI`  
**Primary Target Files:**
* `src/deskai/static/index.html`
* `src/deskai/static/css/components.css`
* `src/deskai/static/css/layout.css`
* `src/deskai/static/js/events.js` (`initResizers` & centralized delegation)
**Status:** Approved for Implementation / Implemented  
**Date:** October 27, 2026  

---

## 1. Executive Summary & Objective

The **Collapsible Bottom Drawer** (`#bottomDrawer`) is the unified parent layout container for all secondary operational panels in DeskAI (`Terminal`, `Output`, `Problems`, `Ports`). Situated beneath `#editorStage`, it provides bidirectional horizontal split-pane resizing, instant collapse/restore capabilities, and seamless panel synchronization.

This document details the concrete DOM hierarchy, pointer drag and keyboard math algorithms, CSS layout rules, design token bindings, and automated test specifications.

---

## 2. DOM Hierarchy & Component Layout

```html
<!-- Horizontal Draggable Resizer Boundary -->
<div 
  class="resizer-row" 
  id="resizerBottom" 
  role="separator" 
  aria-orientation="horizontal" 
  tabindex="0" 
  aria-label="Resize Bottom Drawer"
  aria-valuenow="220"
  aria-valuemin="48"
  aria-valuemax="800">
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
    <button class="icon-btn close-drawer-btn" id="drawerToggleBtn" data-action="toggle-drawer" aria-expanded="true" aria-label="Toggle Drawer" title="Toggle Drawer">─</button>
  </div>

  <!-- 2. Scrollable Drawer Viewport Hosting Subsystem Panels -->
  <div class="drawer-content" id="drawerContent">
    <div class="drawer-panel active" id="terminalPanel" role="tabpanel" aria-labelledby="tab-terminal">
      <div id="terminalHost" role="log" aria-label="Terminal output" aria-live="off"></div>
      <div class="terminal-footer-hint" aria-hidden="true">
        <span>Ctrl+Shift+M: Move focus to tab</span>
      </div>
    </div>

    <div class="drawer-panel" id="outputPanel" role="tabpanel" aria-labelledby="tab-output" tabindex="0" hidden>
      <pre class="terminal-view" id="channelOutput"><code>[DeskAI System] Supervisor active on loopback. Ready for tasks.</code></pre>
    </div>

    <div class="drawer-panel" id="problemsPanel" role="tabpanel" aria-labelledby="tab-problems" tabindex="0" hidden>
      <div class="problems-view">
        <span class="problems-empty">No problems have been detected in the workspace.</span>
      </div>
    </div>

    <div class="drawer-panel" id="portsPanel" role="tabpanel" aria-labelledby="tab-ports" tabindex="0" hidden>
      <!-- Defined in ports-panel LLD -->
    </div>
  </div>
</section>
```

---

## 3. Implementation Details & Algorithms (`src/deskai/static/js/events.js`)

### 3.1 Pointer Capture Resizer Algorithm

```javascript
// Inside initResizers() in events.js
const resizerBottom = document.getElementById("resizerBottom");
const bottomDrawer = document.getElementById("bottomDrawer");
const drawerToggleBtn = document.getElementById("drawerToggleBtn");

if (resizerBottom && bottomDrawer) {
  let lastExpandedHeight = 220;
  try {
    const stored = localStorage.getItem("deskai_bottom_drawer_h");
    if (stored) {
      const parsed = parseFloat(stored);
      if (!isNaN(parsed) && parsed >= 48) {
        lastExpandedHeight = parsed;
        root.style.setProperty("--bottom-drawer-h", `${parsed}px`);
      }
    }
  } catch (e) {
    console.warn("Failed to load bottom drawer height", e);
  }

  const getMaxH = () => Math.round(window.innerHeight * 0.8);

  resizerBottom.setAttribute("aria-valuemin", "48");
  resizerBottom.setAttribute("aria-valuemax", String(getMaxH()));
  const initialH = parseFloat(getComputedStyle(root).getPropertyValue("--bottom-drawer-h")) || lastExpandedHeight;
  resizerBottom.setAttribute("aria-valuenow", String(Math.round(initialH)));

  let isResizing = false;
  let startY = 0;
  let startHeight = 0;
  let rafId = null;

  resizerBottom.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    try {
      resizerBottom.setPointerCapture(e.pointerId);
    } catch (err) {}
    isResizing = true;
    resizerBottom.classList.add("is-resizing", "resizing");
    startY = e.clientY;
    startHeight = parseFloat(getComputedStyle(root).getPropertyValue("--bottom-drawer-h")) || lastExpandedHeight || 220;
  });

  resizerBottom.addEventListener("pointermove", (e) => {
    if (!isResizing) return;
    e.preventDefault();

    if (rafId) cancelAnimationFrame(rafId);
    rafId = requestAnimationFrame(() => {
      const rawH = startHeight + (startY - e.clientY);
      const maxH = getMaxH();

      if (rawH < 50) {
        // Snap to collapsed floor
        bottomDrawer.classList.add("collapsed");
        if (drawerToggleBtn) drawerToggleBtn.setAttribute("aria-expanded", "false");
        root.style.setProperty("--bottom-drawer-h", "48px");
        resizerBottom.setAttribute("aria-valuenow", "48");
        if (window.DeskAIPorts) window.DeskAIPorts.stopPolling();
      } else {
        const clampedH = Math.max(48, Math.min(maxH, rawH));
        if (bottomDrawer.classList.contains("collapsed")) {
          bottomDrawer.classList.remove("collapsed");
          if (drawerToggleBtn) drawerToggleBtn.setAttribute("aria-expanded", "true");
        }
        root.style.setProperty("--bottom-drawer-h", `${clampedH}px`);
        resizerBottom.setAttribute("aria-valuenow", String(Math.round(clampedH)));
        lastExpandedHeight = clampedH;
      }
    });
  });

  const endResize = (e) => {
    if (!isResizing) return;
    isResizing = false;
    if (rafId) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    try {
      if (resizerBottom.hasPointerCapture && resizerBottom.hasPointerCapture(e.pointerId)) {
        resizerBottom.releasePointerCapture(e.pointerId);
      }
    } catch (err) {}
    resizerBottom.classList.remove("is-resizing", "resizing");
    if (!bottomDrawer.classList.contains("collapsed")) {
      try {
        localStorage.setItem("deskai_bottom_drawer_h", String(lastExpandedHeight));
      } catch (e) {}
    }
  };

  resizerBottom.addEventListener("pointerup", endResize);
  resizerBottom.addEventListener("pointercancel", endResize);
}
```

### 3.2 Keyboard Navigation & Roving Focus

1. **Resizer Key Handling:**
   * `ArrowUp`: Step height +16px (or uncollapse if currently collapsed).
   * `ArrowDown`: Step height -16px (snaps to collapsed if $< 50\text{px}$).
   * `Home`: Snap to minimum / collapsed state (`48px`).
   * `End`: Expand to maximum allowable height ($0.8 \times \text{viewport}$).
   * `Enter` / `Space`: Toggle collapse state.
2. **Tabstrip Roving Focus:**
   * `ArrowLeft` / `ArrowRight` on `.drawer-tab[role="tab"]`: Shifts focus to previous/next tab and automatically activates the panel.

---

## 4. CSS Token & Layout Architecture

```css
/* src/deskai/static/css/components.css */
.bottom-drawer {
  height: var(--bottom-drawer-h);
  background-color: var(--bg-header);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.bottom-drawer.collapsed {
  height: 32px;
}

.bottom-drawer.collapsed .drawer-content {
  display: none;
}

/* src/deskai/static/css/layout.css */
.resizer-row {
  width: 100%;
  height: 1px;
  background-color: var(--border-subtle);
  cursor: row-resize;
  position: relative;
  z-index: var(--z-resizer);
  transition: background-color 0.15s ease;
  user-select: none;
  flex-shrink: 0;
}

.resizer-row::before {
  content: "";
  position: absolute;
  left: 0;
  right: 0;
  top: -3px;
  bottom: -3px;
  cursor: row-resize;
  z-index: 1;
}

.resizer-row:hover,
.resizer-row.resizing,
.resizer-row.is-resizing {
  background-color: var(--color-primary);
}
```

---

## 5. Verification & Traceability Matrix

| Test ID | Test Target | Verification Description | Status |
| :--- | :--- | :--- | :--- |
| `TEST-DRAWER-RESIZER-DECL` | `tests/test_ports_tab.py` | Confirms `#resizerBottom` declared with ARIA attributes | Passed |
| `TEST-DRAWER-CSS-DEF` | `tests/test_ports_tab.py` | Confirms `.resizer-row` defined with `cursor: row-resize` | Passed |
| `TEST-DRAWER-KEY-BINDINGS` | `tests/test_ports_tab.py` | Confirms ArrowUp/ArrowDown bound in `events.js` | Passed |
| `TEST-DRAWER-ARIA-SPEC` | `tests/test_ports_tab.py` | Confirms `aria-valuenow`, `aria-valuemin="48"`, `aria-valuemax` | Passed |
| `TEST-PW-TAB-EXPANDS` | `tests/test_bottom_drawer_behavior.py` | Playwright test: clicking tab expands collapsed drawer | Passed |
| `TEST-PW-RESIZER-DBLCLICK` | `tests/test_bottom_drawer_behavior.py` | Playwright test: double-click toggles collapse / restore | Passed |
| `TEST-PW-RESIZER-KEYS` | `tests/test_bottom_drawer_behavior.py` | Playwright test: ArrowUp, ArrowDown, Home, End resize behavior | Passed |
| `TEST-PW-COLLAPSED-A11Y` | `tests/test_bottom_drawer_behavior.py` | Playwright test: `.drawer-content` has `display: none` when collapsed | Passed |
| `TEST-PW-TAB-ROVING` | `tests/test_bottom_drawer_behavior.py` | Playwright test: ArrowLeft/ArrowRight roving focus | Passed |
| `TEST-PW-FOCUS-RESTORE` | `tests/test_bottom_drawer_behavior.py` | Playwright test: re-render restores active button focus | Passed |
