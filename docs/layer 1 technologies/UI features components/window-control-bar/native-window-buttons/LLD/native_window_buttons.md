# Low-Level Design (LLD): Native Window Buttons

**Document ID:** `ORX-LLD-NATIVE-WINDOW-BUTTONS-V1`  
**Version:** `1.0` (Window Control Bar Subcomponent Architecture)  
**Parent Component:** `window-control-bar`  
**Target Codebase:** `DeskAI`  
**Target Files:**
* `src/deskai/static/index.html`
* `src/deskai/static/css/components.css`
* `src/deskai/static/css/tokens.css`
* `src/deskai/static/js/events.js`
* `src/deskai/static/js/bridge.js`
* `src/deskai/bridge/api.py`
**Status:** Approved  
**Date:** October 28, 2026  

---

## 1. Module Structure & Interaction

The **Native Window Buttons** implementation involves three distinct architectural layers:
1. **Markup & Accessibility Layer:** `src/deskai/static/index.html` defining the `<button>` DOM nodes, ARIA grouping, and `data-action` attributes.
2. **Presentation Layer:** `src/deskai/static/css/components.css` defining the dimensions, flex layout, hover effects, and drag isolation properties.
3. **Behavioral & Dispatch Layer:** `src/deskai/static/js/events.js` handling click delegation, dialog orchestration, and communicating with `NativeBridge.windowControl` in `src/deskai/static/js/bridge.js`.

---

## 2. DOM & CSS Specification

### 2.1 Markup Architecture
```html
<div class="header-right window-controls" role="group" aria-label="Window Controls">
  <button class="win-btn win-min" data-action="win-minimize" aria-label="Minimize Window">─</button>
  <button class="win-btn win-max" data-action="win-maximize" aria-label="Maximize Window">□</button>
  <button class="win-btn win-close" data-action="win-close" aria-label="Close Window">✕</button>
</div>
```

### 2.2 CSS Rules & Token Bindings (`components.css`)
```css
.win-btn {
  -webkit-app-region: no-drag;
  background: transparent;
  border: none;
  color: var(--text-muted);
  width: 28px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border-radius: 4px;
  font-size: 11px;
}

.win-btn:hover {
  background-color: var(--bg-hover);
  color: var(--text-primary);
}

.win-close:hover {
  background-color: var(--color-danger);
  color: var(--color-text-white);
}
```

---

## 3. Event Handling & State Machine (`events.js`)

The global click handler captures clicks matching `[data-action]`:

```javascript
switch (action) {
  case "win-minimize":
    NativeBridge.windowControl("minimize");
    break;

  case "win-maximize":
    NativeBridge.windowControl("maximize");
    break;

  case "win-close": {
    const canClose = await NativeBridge.windowControl("close_request");
    if (!canClose) {
      const confirmModal = document.getElementById("confirmModal");
      const descEl = document.getElementById("confirmModalDesc");
      const titleEl = document.getElementById("confirmModalTitle");
      const hasRunningTerminal = !!(window.DeskAITerminal && window.DeskAITerminal.sessionId);
      const isDirty = !!(window.store && window.store.state && window.store.state.dirtyTabs && window.store.state.dirtyTabs.size > 0);

      if (descEl && titleEl) {
        titleEl.textContent = "Confirm Exit";
        if (isDirty && hasRunningTerminal) {
          descEl.textContent =
            "You have unsaved changes in your open editor tabs and an active terminal running. Are you sure you want to exit?";
        } else if (hasRunningTerminal) {
          descEl.textContent =
            "You have an active terminal session running. Are you sure you want to terminate it and exit?";
        } else {
          descEl.textContent =
            "You have unsaved changes in your open editor tabs. Are you sure you want to discard them and exit?";
        }
      }

      if (confirmModal && typeof confirmModal.showModal === "function") {
        confirmModal.showModal();
      } else {
        NativeBridge.windowControl("close");
      }
    }
    break;
  }

  case "cancel-exit": {
    const confirmModal = document.getElementById("confirmModal");
    if (confirmModal && confirmModal.close) {
      confirmModal.close();
    }
    break;
  }

  case "confirm-exit": {
    const confirmModal = document.getElementById("confirmModal");
    if (confirmModal && confirmModal.close) {
      confirmModal.close();
    }
    if (window.DeskAITerminal) {
      window.DeskAITerminal.destroy();
    }
    await NativeBridge.setDirtyStatus(false);
    await NativeBridge.windowControl("close");
    break;
  }
}
```

---

## 4. Bridge & Backend Contract

### 4.1 NativeBridge Specification
In `src/deskai/static/js/bridge.js`:
* `NativeBridge.windowControl(action: "minimize" | "maximize" | "close" | "close_request")`:
  * Returns `boolean` for `close_request` (`true` if safe to close immediately, `false` if exit guard requires confirmation).
  * Returns `void` / `boolean` for `minimize`, `maximize`, and `close`.

### 4.2 DesktopBridgeAPI Backend Handler
In `src/deskai/bridge/api.py`:
* `window_control(action: str)`:
  * Dispatches to active window platform implementation (`win32`, `gtk`, or `pywebview`).
  * `close_request`: checks `self.is_dirty` and `self.terminal_manager.has_active_sessions()`.

---

## 5. Verification & Test Plan

1. **TC-NWB-01 (Markup & ARIA):** Verify `.window-controls` contains `.win-min`, `.win-max`, and `.win-close` with appropriate ARIA roles and labels.
2. **TC-NWB-02 (Minimize Dispatch):** Verify clicking `.win-min` triggers `NativeBridge.windowControl("minimize")`.
3. **TC-NWB-03 (Maximize Dispatch):** Verify clicking `.win-max` triggers `NativeBridge.windowControl("maximize")`.
4. **TC-NWB-04 (Close Unguarded):** When `close_request` returns `true`, verify window is closed immediately without displaying `#confirmModal`.
5. **TC-NWB-05 (Close Guarded - Dirty Tabs):** When dirty tabs exist, verify clicking `.win-close` opens `#confirmModal` with dirty tabs warning message.
6. **TC-NWB-06 (Close Guarded - Running Terminal):** When terminal session is active, verify clicking `.win-close` opens `#confirmModal` with running terminal warning message.
7. **TC-NWB-07 (Close Guarded - Cancel Flow):** Verify clicking `[data-action="cancel-exit"]` closes `#confirmModal` and keeps window open.
8. **TC-NWB-08 (Close Guarded - Confirm Flow):** Verify clicking `[data-action="confirm-exit"]` closes modal, destroys terminal, clears dirty status, and calls `windowControl("close")`.
