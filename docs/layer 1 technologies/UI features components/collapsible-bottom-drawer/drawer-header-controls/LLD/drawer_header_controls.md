# Low-Level Design (LLD): Drawer Header Controls

**Document ID:** `ORX-LLD-DRAWER-HEADER-CONTROLS-V1`  
**Version:** `1.0` (Defect-Resolved & Synchronized with Implemented Vanilla JS Codebase)  
**Parent Document:** `ORX-HLD-DRAWER-HEADER-CONTROLS-V1`  
**Target Codebase:** `DeskAI`  
**Primary Target Files:**
* `src/deskai/static/index.html` (Lines 95-108)
* `src/deskai/static/css/components.css` (Lines 316-360)
* `src/deskai/static/css/layout.css` (Resizer interaction & split pane constraints)
* `src/deskai/static/js/events.js` (Event delegation & resizer initialization)
* `src/deskai/static/js/ports.js` (Ports panel lifecycle integration)
**Status:** Approved for Implementation / Implemented  
**Date:** October 27, 2026  

---

## 1. Executive Summary & Objective

The **Drawer Header Controls** component is the top 32px interactive banner of the Collapsible Bottom Drawer (`#bottomDrawer`). It provides two primary operational capabilities:
1. **Multi-Domain Tab Switching (`.drawer-tabs`):** Enables instantaneous tabbed navigation across four core IDE subsystem panels:
   * **Terminal (`terminal`):** Interactive host shell and process runner.
   * **Output (`output`):** Host supervisor telemetry and application log stream.
   * **Problems (`problems`):** Workspace diagnostic diagnostics and language server issue reports.
   * **Ports (`ports`):** Live loopback and forwarded TCP socket monitor.
2. **Drawer Collapse & Viewport Reclaim (`.close-drawer-btn`):** Enables one-click toggling of the bottom drawer between its user-configured height (default 240px) and a minimized 32px docked header, maximizing vertical code editor screen space.

---

## 2. DOM Hierarchy & Component Markup

The component is located directly inside `<section class="bottom-drawer" id="bottomDrawer">` in `src/deskai/static/index.html`:

```html
<!-- Collapsible Bottom Drawer -->
<section class="bottom-drawer" id="bottomDrawer" role="region" aria-label="Output Drawer">
  <!-- Drawer Header Controls -->
  <div class="drawer-header">
    <!-- Accessible Tab Navigation -->
    <div class="drawer-tabs" role="tablist" aria-label="Drawer Panels">
      <button 
        class="drawer-tab active" 
        data-action="drawer-tab" 
        data-target="terminal" 
        role="tab" 
        aria-selected="true" 
        aria-controls="terminalPanel"
        id="tab-terminal">
        Terminal
      </button>
      <button 
        class="drawer-tab" 
        data-action="drawer-tab" 
        data-target="output" 
        role="tab" 
        aria-selected="false" 
        aria-controls="outputPanel"
        id="tab-output">
        Output
      </button>
      <button 
        class="drawer-tab" 
        data-action="drawer-tab" 
        data-target="problems" 
        role="tab" 
        aria-selected="false" 
        aria-controls="problemsPanel"
        id="tab-problems">
        Problems
      </button>
      <button 
        class="drawer-tab" 
        data-action="drawer-tab" 
        data-target="ports" 
        role="tab" 
        aria-selected="false" 
        aria-controls="portsPanel"
        id="tab-ports">
        Ports
      </button>
    </div>

    <!-- Drawer Actions Toolbar (WAI-ARIA Roving Tabindex) -->
    <div class="drawer-actions" id="drawerActions" role="toolbar" aria-label="Panel Actions">
      <button class="icon-btn" id="btnNewTerminal" data-action="new-terminal" title="New Terminal" aria-label="New Terminal" tabindex="0">...</button>
      <button class="icon-btn" id="btnKillTerminalHeader" data-action="kill-terminal" title="No active terminal session" aria-label="Kill Active Terminal" disabled aria-disabled="true" tabindex="-1">...</button>
      <button class="icon-btn" id="btnMaximizeDrawer" data-action="maximize-drawer" title="Maximize Terminal Panel" aria-label="Maximize Terminal Panel" aria-expanded="false" tabindex="-1">...</button>
      <button class="icon-btn close-drawer-btn" id="drawerToggleBtn" data-action="toggle-drawer" aria-expanded="true" aria-label="Toggle Drawer" title="Minimize Panel" tabindex="-1">...</button>
    </div>
  </div>

  <!-- Drawer Body Content Panels -->
  <div class="drawer-content" id="drawerContent">
    <div class="drawer-panel active" id="terminalPanel" role="tabpanel" aria-labelledby="tab-terminal">...</div>
    <div class="drawer-panel" id="outputPanel" role="tabpanel" aria-labelledby="tab-output" hidden>...</div>
    <div class="drawer-panel" id="problemsPanel" role="tabpanel" aria-labelledby="tab-problems" hidden>...</div>
    <div class="drawer-panel" id="portsPanel" role="tabpanel" aria-labelledby="tab-ports" hidden>...</div>
  </div>
</section>
```

---

## 3. Concrete JavaScript Implementation

All interactions in DeskAI follow a high-performance **centralized event delegation** pattern bound to `#appRoot` inside `src/deskai/static/js/events.js`.

### 3.1 Tab Switching Action Handler (`data-action="drawer-tab"`)

```javascript
case "drawer-tab": {
  const target = trigger.getAttribute("data-target");
  if (!target) return;

  // 1. Update Tab Button Visual and ARIA Selection States
  document.querySelectorAll(".drawer-tab").forEach(t => {
    t.classList.remove("active");
    t.setAttribute("aria-selected", "false");
  });
  trigger.classList.add("active");
  trigger.setAttribute("aria-selected", "true");

  // 2. Synchronize Drawer Content Panels
  document.querySelectorAll(".drawer-panel").forEach(panel => {
    if (panel.id === `${target}Panel`) {
      panel.classList.add("active");
      panel.removeAttribute("hidden");
    } else {
      panel.classList.remove("active");
      panel.setAttribute("hidden", "");
    }
  });

  // 3. Subsystem Lifecycle & Auto-Refresh Integration
  if (target === "ports" && window.DeskAIPorts) {
    window.DeskAIPorts.refresh();
  }
  break;
}
```

### 3.2 Drawer Toggle Action Handler (`data-action="toggle-drawer"`)

```javascript
case "toggle-drawer": {
  const drawer = document.getElementById("bottomDrawer");
  if (drawer) {
    drawer.classList.toggle("collapsed");
  }
  break;
}
```

### 3.3 Resizer Coordination & Double-Click Toggle (`initResizers`)

The horizontal resizer directly above the drawer (`#resizerBottom`) coordinates with the drawer header controls to allow intuitive gestures:

```javascript
// Double-click resizer to toggle drawer collapse
resizerBottom.addEventListener("dblclick", () => {
  const isCollapsed = bottomDrawer.classList.contains("collapsed");
  if (isCollapsed) {
    bottomDrawer.classList.remove("collapsed");
    bottomDrawer.style.height = (lastDrawerHeight || 240) + "px";
  } else {
    lastDrawerHeight = bottomDrawer.offsetHeight;
    bottomDrawer.classList.add("collapsed");
  }
});
```

---

## 4. CSS Styling & Layout Specifications

All styles are defined in `src/deskai/static/css/components.css` using strict WCAG-compliant design tokens from `tokens.css`.

### 4.1 Header Container (`.drawer-header`)
```css
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
```

### 4.2 Tablist & Tab Buttons (`.drawer-tabs`, `.drawer-tab`)
```css
.drawer-tabs {
  display: flex;
  height: 100%;
  gap: 16px;
}

.drawer-tab {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  cursor: pointer;
  height: 100%;
  display: flex;
  align-items: center;
  padding: 0 4px;
  position: relative;
  transition: color var(--transition-fast);
}

.drawer-tab:hover {
  color: var(--text-primary);
}

.drawer-tab.active {
  color: var(--text-primary);
  border-bottom: 2px solid var(--accent-primary);
}
```

### 4.3 Drawer Toggle Button (`.close-drawer-btn`)
```css
.close-drawer-btn {
  font-size: 14px;
  line-height: 1;
  color: var(--text-muted);
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: var(--radius-sm);
  transition: color var(--transition-fast), background-color var(--transition-fast);
}

.close-drawer-btn:hover {
  color: var(--text-primary);
  background-color: var(--bg-hover);
}
```

### 4.4 Collapsed Viewport Rule (`.bottom-drawer.collapsed`)
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
```
*When collapsed, the height of `.bottom-drawer` is clamped to exactly `32px`, hiding `.drawer-content` while preserving `.drawer-header` fully interactive at the bottom of the window.*

---

## 5. Accessibility (WCAG 2.1 AA) Specifications

1. **Semantic Role Mapping:**
   * Container: `role="tablist"` with `aria-label="Drawer Panels"`.
   * Buttons: `role="tab"`, with dynamic `aria-selected="true|false"` reflecting the active state.
   * Target Panels: `role="tabpanel"`, dynamically bound via `aria-controls` on the tab and `aria-labelledby` on the panel.
2. **Keyboard Traversal:**
   * Tabs are reachable via `Tab`.
   * Selection can be activated with `Enter` or `Space`.
   * Arrow key support (`ArrowLeft` / `ArrowRight`) traverses sibling tabs in the tablist.
3. **High-Contrast Focus Rings:**
   * `:focus-visible` outline uses `var(--accent-primary)` (2px outline with 2px offset).
   * Forced-colors mode (`@media (forced-colors: active)`) ensures active tab indicator renders with `Highlight` color.

---

## 6. Subsystem Integration Points

| Subsystem | Integration Point | Action Triggered |
| :--- | :--- | :--- |
| **Ports Monitor** | `case "drawer-tab": if (target === "ports")` | Calls `window.DeskAIPorts.refresh()` to fetch real-time listening sockets. |
| **Terminal Shell** | `case "drawer-tab": if (target === "terminal")` | Preserves tab roving focus on `#tab-terminal` (WCAG 2.1.2; user enters terminal via `Tab`/`Enter`), adapts `xterm.fit()`, and displays running status chip (`●`). |
| **Split Resizer** | `#resizerBottom` mouseup & dblclick | Updates `lastDrawerHeight` and removes/adds `.collapsed` class. |
| **Window State** | Local storage cache | Saves drawer collapsed state across application reboots. |

---

## 7. Automated Test Plan & Traceability Matrix

| Test ID | Test Target | Verification Criteria | Test Suite |
| :--- | :--- | :--- | :--- |
| **TC-DHC-01** | Tab DOM Declaration | Index HTML contains 4 tabs with `data-target` matching existing panels | `tests/test_ports_tab.py` |
| **TC-DHC-02** | Tab Selection Logic | Clicking tab sets `.active` on tab and removes `.active` from siblings | Playwright E2E |
| **TC-DHC-03** | ARIA Synchronization | `aria-selected="true"` set exclusively on the active tab | DOM Contract Test |
| **TC-DHC-04** | Panel Visibility | Non-active panels have `hidden` attribute; active panel lacks `hidden` | Playwright E2E |
| **TC-DHC-05** | Toggle Drawer Action | Clicking `─` button adds `.collapsed` class to `#bottomDrawer` | Playwright E2E |
| **TC-DHC-06** | Height Clamping | `.bottom-drawer.collapsed` has computed height of `32px` | CSS Property Assertion |
| **TC-DHC-07** | Ports Refresh Hook | Switching to `ports` tab calls `DeskAIPorts.refresh()` | JavaScript Unit Test |
