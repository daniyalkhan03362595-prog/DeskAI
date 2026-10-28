# Low-Level Design (LLD): Window Drag Region

**Document ID:** `ORX-LLD-WINDOW-DRAG-REGION-V1`  
**Version:** `1.0` (Window Control Bar Subcomponent Architecture)  
**Parent Document:** `ORX-HLD-WINDOW-DRAG-REGION-V1`  
**Target Codebase:** `DeskAI`  
**Target Files:**
* `src/deskai/static/index.html`
* `src/deskai/static/css/components.css`
* `src/deskai/static/css/tokens.css`
* `src/deskai/static/js/events.js`
* `src/deskai/static/js/bridge.js`
* `src/deskai/bridge/api.py`
* `tests/test_window_drag_region.py`
**Status:** Approved for Implementation  
**Date:** October 28, 2026  

---

## 1. Executive Summary & Objective

The **Window Drag Region** provides frameless window dragging and double-click maximize/restore support across the top header bar (`#appHeader`).

This Low-Level Design defines:
1. Exact CSS `-webkit-app-region` specifications and no-drag boundary classes.
2. Pointer event filtering and debounce timing in `events.js`.
3. Native bridge coordination (`windowControl("drag_start")` and `windowControl("maximize")`).
4. Automated test specifications (`TC-WDR-01` through `TC-WDR-07`).

---

## 2. DOM Structure & CSS Specifications

### 2.1 Markup Hierarchy in `src/deskai/static/index.html`

```html
<header class="app-header pywebview-drag-region" id="appHeader" role="banner">
  <div class="header-left">
    <div class="app-logo" id="appLogo" aria-label="DeskAI Studio">
      <span class="app-logo-icon" aria-hidden="true">⚡</span>
      <span class="app-logo-text">DeskAI</span>
    </div>
    <span class="workspace-pill" id="headerWorkspacePill" role="status" aria-label="Workspace: No folder opened" title="No active workspace folder">
      DeskAI / (no workspace)
    </span>
  </div>
  <div class="header-right window-controls" role="group" aria-label="Window Controls">
    <button class="win-btn win-min" data-action="win-minimize" aria-label="Minimize Window">─</button>
    <button class="win-btn win-max" data-action="win-maximize" aria-label="Maximize Window">□</button>
    <button class="win-btn win-close" data-action="win-close" aria-label="Close Window">✕</button>
  </div>
</header>
```

### 2.2 CSS Rules in `src/deskai/static/css/components.css`

```css
.app-header {
  height: var(--header-height);
  background-color: var(--bg-header);
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-3);
  z-index: var(--z-header);
  user-select: none;
  -webkit-app-region: drag;
}

.pywebview-drag-region {
  -webkit-app-region: drag;
}

.header-right,
.workspace-pill,
.win-btn {
  -webkit-app-region: no-drag;
}
```

---

## 3. JavaScript Event Implementation in `src/deskai/static/js/events.js`

```javascript
  // Header Drag (Wayland / GTK / Windows native move drag) & Double Click Maximize
  const appHeader = document.getElementById("appHeader");
  if (appHeader) {
    let lastHeaderMouseDown = 0;
    appHeader.addEventListener("mousedown", (e) => {
      // Only primary left clicks on non-interactive regions
      if (e.button === 0 && !e.target.closest("button, input, textarea, .workspace-pill, [data-action]")) {
        const now = e.timeStamp || Date.now();
        // Debounce if double-click interval or multiple clicks detected
        if (now - lastHeaderMouseDown < 350 || e.detail > 1) {
          lastHeaderMouseDown = now;
          return;
        }
        lastHeaderMouseDown = now;
        NativeBridge.windowControl("drag_start", null, now);
      }
    });

    appHeader.addEventListener("dblclick", (e) => {
      // Prevent maximize when double-clicking on buttons, inputs, or workspace-pill
      if (!e.target.closest("button, input, textarea, .workspace-pill, [data-action]")) {
        NativeBridge.windowControl("maximize");
      }
    });
  }
```

---

## 4. Backend Platform Implementations (`src/deskai/bridge/api.py`)

1. **Windows Platform:**
   Uses `_windows_native_drag(self._window, 2)` where `2` represents `HTCAPTION` (Titlebar) sent via `win32.user32.SendMessageW(hwnd, 0x00A1, 2, 0)` after calling `ReleaseCapture()`.
2. **Linux Platform (X11 / Wayland):**
   Invokes GTK native method `native.begin_move_drag(1, x, y, Gdk.CURRENT_TIME)` executed safely on the GTK main loop via `GLib.idle_add()`.
3. **Origin Protection:**
   Rejects requests with `_is_origin_allowed()`.

---

## 5. Test Specifications (`tests/test_window_drag_region.py`)

| Test Case ID | Test Case Name | Description & Verification Steps |
|---|---|---|
| **TC-WDR-01** | `test_wdr_01_drag_region_computed_styles` | Asserts `#appHeader` has `-webkit-app-region: drag` and `user-select: none`. |
| **TC-WDR-02** | `test_wdr_02_no_drag_interactive_elements` | Asserts `.workspace-pill` and `.win-btn` have `-webkit-app-region: no-drag`. |
| **TC-WDR-03** | `test_wdr_03_mousedown_triggers_drag_start` | Dispatches mousedown (`button: 0`) on `#appHeader`, asserts `NativeBridge.windowControl('drag_start')` called. |
| **TC-WDR-04** | `test_wdr_04_mousedown_on_buttons_ignored` | Dispatches mousedown on `.win-min` and `.workspace-pill`, asserts `drag_start` NOT called. |
| **TC-WDR-05** | `test_wdr_05_dblclick_triggers_maximize` | Dispatches dblclick on `#appHeader`, asserts `NativeBridge.windowControl('maximize')` called. |
| **TC-WDR-06** | `test_wdr_06_dblclick_on_interactive_ignored` | Dispatches dblclick on `.workspace-pill` and `.win-close`, asserts `maximize` NOT called. |
| **TC-WDR-07** | `test_wdr_07_right_click_ignored` | Dispatches mousedown with `button: 2`, asserts `drag_start` NOT called. |
