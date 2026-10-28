# Low-Level Design (LLD): Window Control Bar

**Document ID:** `ORX-LLD-WINDOW-CONTROL-BAR-V1`  
**Version:** `1.0` (Core Layer 1 UI Component Architecture)  
**Parent Component:** `UI features components`  
**Target Codebase:** `DeskAI`  
**Target Files:**
* `src/deskai/static/index.html`
* `src/deskai/static/css/components.css`
* `src/deskai/static/css/tokens.css`
* `src/deskai/static/js/app.js`
* `src/deskai/static/js/events.js`
* `src/deskai/static/js/bridge.js`
* `src/deskai/bridge/api.py`
**Status:** Approved  
**Date:** October 28, 2026  

---

## 1. Concrete Layout & DOM Hierarchy

The Window Control Bar is declared in `src/deskai/static/index.html`:

```html
<header class="app-header pywebview-drag-region" id="appHeader" role="banner">
  <div class="header-left">
    <div class="app-logo" id="appLogo" aria-label="DeskAI Studio">
      <span class="app-logo-icon" aria-hidden="true">⚡</span>
      <span class="app-logo-text">DeskAI</span>
    </div>
    <span class="workspace-pill" id="headerWorkspacePill" role="status" aria-label="Workspace: No folder opened" title="No active workspace folder">DeskAI / (no workspace)</span>
  </div>
  <div class="header-right window-controls" role="group" aria-label="Window Controls">
    <button class="win-btn win-min" data-action="win-minimize" aria-label="Minimize Window">─</button>
    <button class="win-btn win-max" data-action="win-maximize" aria-label="Maximize Window">□</button>
    <button class="win-btn win-close" data-action="win-close" aria-label="Close Window">✕</button>
  </div>
</header>
```

---

## 2. Presentation Layer & Token Bindings (`components.css`)

```css
.app-header {
  height: var(--header-height);
  background-color: var(--bg-header);
  border-bottom: var(--border-regular);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-3);
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

.header-left {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.app-logo {
  font-weight: 700;
  font-size: var(--text-base);
  font-family: var(--font-mono);
  color: var(--color-amber);
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.workspace-pill {
  font-size: var(--text-xs);
  color: var(--text-muted);
  background-color: var(--bg-surface);
  padding: 2px 8px;
  border-radius: 12px;
  border: var(--border-regular);
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-block;
  vertical-align: middle;
  transition: border-color var(--transition-fast), color var(--transition-fast);
}

.workspace-pill:hover {
  border-color: var(--border-focus);
  color: var(--text-primary);
}

.win-btn {
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

## 3. Behavioral Orchestration

### 3.1 WorkspacePillController (`app.js`)
* Subscribes to `workspace.rootPath` and `workspace.branch`.
* Derives folder name via regex or string splitting (`rootPath.split(/[/\\]/).filter(Boolean).pop()`).
* Queries Git branch via `NativeBridge.getGitBranch(rootPath)` if branch is not yet populated.
* Updates DOM attributes via `.textContent`, `.title`, and `setAttribute("aria-label", ...)`.

### 3.2 Double-Click Maximize & Drag Regions (`events.js`)
* Detects double-click on `#appHeader` outside `.workspace-pill` and `[data-action]`.
* Dispatches `NativeBridge.windowControl("maximize")`.
* Debounces mousedown interactions to avoid spurious maximizes during initial app load.

### 3.3 Guarded Close Sequence (`events.js`)
* Queries `NativeBridge.windowControl("close_request")`.
* If blocked:
  * Reads `store.state.dirtyTabs` and `DeskAITerminal.sessionId`.
  * Dynamically populates `#confirmModalTitle` and `#confirmModalDesc`.
  * Invokes `confirmModal.showModal()`.
* On cancel (`cancel-exit`): Closes modal; window remains open.
* On confirm (`confirm-exit`): Destroys terminal, resets dirty status, and calls `NativeBridge.windowControl("close")`.

---

## 4. Test Suite Matrix

The entire Window Control Bar is verified by 4 comprehensive Playwright test suites:

1. `tests/test_app_branding_title.py` (5 tests): Branding mark, text, styling, semantics, non-interactive keyboard skips.
2. `tests/test_workspace_branch_pill.py` (7 tests): Path updates, git branch synchronization, truncation, tooltips, ARIA labels.
3. `tests/test_window_drag_region.py` (7 tests): Drag computed styles, no-drag interactive exclusions, double-click maximize dispatch, exclusion zones.
4. `tests/test_native_window_buttons.py` (9 tests): Button semantics, minimize/maximize dispatch, guarded exit confirmation flows, cancel/confirm exit pathways.
