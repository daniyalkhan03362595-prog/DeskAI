# High-Level Design (HLD): Native Window Buttons

**Document ID:** `ORX-HLD-NATIVE-WINDOW-BUTTONS-V1`  
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

## 1. Architectural Overview & Objective

The **Native Window Buttons** subcomponent (`.window-controls` within `#appHeader`) provides frameless desktop window state management controls for minimizing, maximizing/restoring, and safely terminating the application window across Windows, Linux, and macOS platforms.

Because DeskAI runs in a borderless, frameless native window (`easygui` / `pywebview` with GTK, Win32, or Cocoa backends), the standard OS-rendered title bar controls are suppressed. This subcomponent reinstates standard desktop window interactions while providing:
1. **Direct Bridge Dispatch:** Seamless binding between frontend UI action dispatchers and backend window control APIs (`minimize`, `maximize`, `close`).
2. **Guarded Exit Handshake:** Prevents accidental data loss or orphaned background processes when closing the application by validating unsaved dirty editor tabs and active background terminal processes before window destruction.
3. **Interactive Region Isolation:** Uses `-webkit-app-region: no-drag` so mouse clicks, drags, and hover states operate cleanly without triggering native window move operations.
4. **WAI-ARIA Accessibility & Focus Semantics:** Operates under a cohesive button group (`role="group" aria-label="Window Controls"`) with screen-reader accessible names, distinct danger hover styling, and complete keyboard operability.

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ #appHeader.app-header.pywebview-drag-region [role="banner"]                 │
│ ┌──────────────────────────────┐                ┌─────────────────────────┐ │
│ │ ⚡ DeskAI  [DeskAI / main]   │                │ .window-controls        │ │
│ │ (drag)     (no-drag)         │                │ [role="group"]          │ │
│ │                              │                │ ┌─────┐ ┌─────┐ ┌─────┐ │ │
│ │                              │                │ │  ─  │ │  □  │ │  ✕  │ │ │
│ │                              │                │ │ min │ │ max │ │close│ │ │
│ │                              │                │ └─────┘ └─────┘ └─────┘ │ │
│ └──────────────────────────────┘                └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Component Structure & Semantics

### 2.1 DOM Specification
The button strip is anchored in `.header-right` inside `#appHeader`:

```html
<div class="header-right window-controls" role="group" aria-label="Window Controls">
  <button class="win-btn win-min" data-action="win-minimize" aria-label="Minimize Window">─</button>
  <button class="win-btn win-max" data-action="win-maximize" aria-label="Maximize Window">□</button>
  <button class="win-btn win-close" data-action="win-close" aria-label="Close Window">✕</button>
</div>
```

### 2.2 Semantic Roles & ARIA Contract
* **Container Role:** `role="group"` with `aria-label="Window Controls"`. This groups the three controls logically for screen readers.
* **Control Actions:**
  * `win-minimize`: `aria-label="Minimize Window"`, glyph `─` (`\u2500` box drawings light horizontal).
  * `win-maximize`: `aria-label="Maximize Window"`, glyph `□` (`\u25A1` white square).
  * `win-close`: `aria-label="Close Window"`, glyph `✕` (`\u2715` multiplication x).
* **Keyboard Navigation:** Standard sequential tab navigation (`Tab` / `Shift+Tab`) with `Enter` or `Space` activation via native `<button>` semantics.

---

## 3. Interaction Design & Guarded Exit Flow

### 3.1 Minimize & Maximize Actions
* **Minimize (`win-minimize`):** Calls `NativeBridge.windowControl("minimize")` immediately. The native platform hides or minimizes the window to the taskbar/dock.
* **Maximize (`win-maximize`):** Calls `NativeBridge.windowControl("maximize")`. Toggles between normal windowed dimensions and maximized state.

### 3.2 Close & Guarded Exit Sequence
Closing the IDE must not discard unsaved code or leave running shell subprocesses orphaned in the background.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant WinBtn as .win-close Button
    participant Events as events.js
    participant Bridge as NativeBridge
    participant Modal as #confirmModal
    participant Terminal as DeskAITerminal

    User->>WinBtn: Click Close Window (✕)
    WinBtn->>Events: Event Delegation (data-action="win-close")
    Events->>Bridge: windowControl("close_request")
    
    alt canClose == true (No dirty tabs, no active terminal)
        Bridge-->>Events: true
        Note over Bridge: Native window destroyed immediately
    else canClose == false (Dirty tabs or active terminal)
        Bridge-->>Events: false
        Events->>Events: Inspect store.state.dirtyTabs & DeskAITerminal.sessionId
        Events->>Modal: Populate title ("Confirm Exit") & context-specific description
        Events->>Modal: modal.showModal()
        
        alt User Clicks "Cancel" (data-action="cancel-exit")
            User->>Modal: Click Cancel
            Modal->>Events: Close modal
            Note over Events: Window remains open; editing continues
        else User Clicks "Exit" (data-action="confirm-exit")
            User->>Modal: Click Exit
            Modal->>Events: Close modal
            Events->>Terminal: DeskAITerminal.destroy()
            Events->>Bridge: setDirtyStatus(false)
            Events->>Bridge: windowControl("close")
            Note over Bridge: Window destroyed cleanly
        end
    end
```

---

## 4. Visual Design & Token Alignment

All styling is strictly derived from `tokens.css`:
* **Geometry:** `width: 28px`, `height: 24px`, `border-radius: 4px`, `font-size: 11px`.
* **Standard Button Hover:**
  * Background: `var(--bg-hover)`
  * Color: `var(--text-primary)`
* **Close Button Hover:**
  * Background: `var(--color-danger)` (`#dc2626`)
  * Color: `var(--color-text-white)` (`#ffffff`)
* **Drag Isolation:** `.win-btn` specifies `-webkit-app-region: no-drag`, preventing title bar drag interception during button interaction.

---

## 5. Security & Isolation Considerations

1. **Injection Guarding:** Event delegation verifies that `data-action` triggers originate inside `#appRoot` and strictly outside `.bubble-body`, `.tab-label`, or `.markdown-surface`.
2. **Subprocess Cleanup:** On confirmed exit, `DeskAITerminal.destroy()` cleans up WebSocket connections and signals POSIX `SIGHUP` / Win32 process termination before `windowControl("close")` executes.
3. **No Unsanitized HTML:** Dialog titles and descriptions are updated solely via `.textContent`.
