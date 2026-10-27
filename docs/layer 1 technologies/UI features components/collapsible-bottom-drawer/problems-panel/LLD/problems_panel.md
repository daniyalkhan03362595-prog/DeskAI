# Low-Level Design (LLD): Problems Panel (Workspace Diagnostics)

**Document ID:** `ORX-LLD-PROBLEMS-PANEL-V1`  
**Version:** `1.0` (Defect-Resolved & Synchronized with Implemented Vanilla JS Codebase)  
**Parent Document:** `ORX-HLD-PROBLEMS-PANEL-V1`  
**Target Codebase:** `DeskAI`  
**Primary Target Files:**
* `src/deskai/static/index.html` (Lines 103, 120-124)
* `src/deskai/static/css/components.css` (Lines 368-386)
* `src/deskai/static/js/events.js` (`case "drawer-tab"`)
**Status:** Approved for Implementation / Implemented  
**Date:** October 27, 2026  

---

## 1. Executive Summary & Objective

The **Problems Panel** (`#problemsPanel`) provides a standardized diagnostics display inside the Collapsible Bottom Drawer (`#bottomDrawer`). It surfaces syntax errors, linting warnings, and diagnostic telemetry from language servers and workspace file watchers.

This specification details the DOM structure, tab synchronization logic, CSS layout tokens, data structures for issue rendering, and test verification requirements.

---

## 2. DOM Hierarchy & Component Markup

The component is located directly inside `#drawerContent` in `src/deskai/static/index.html`:

```html
<!-- Problems Panel -->
<div class="drawer-panel" id="problemsPanel" role="tabpanel" aria-labelledby="tab-problems" hidden>
  <div class="problems-view">
    <span class="problems-empty">No problems have been detected in the workspace.</span>
  </div>
</div>
```

### 2.1 Associated Tab Trigger
The corresponding tab trigger in `.drawer-tabs` is defined as:
```html
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
```

---

## 3. JavaScript Event Handling & Tab Synchronization

Tab activation and panel visibility are orchestrated by the centralized event delegation router in `src/deskai/static/js/events.js`:

```javascript
case "drawer-tab": {
  const target = trigger.getAttribute("data-target"); // "problems"
  if (!target) return;

  // 1. Deselect sibling tabs and select clicked tab
  document.querySelectorAll(".drawer-tab").forEach(t => {
    t.classList.remove("active");
    t.setAttribute("aria-selected", "false");
  });
  trigger.classList.add("active");
  trigger.setAttribute("aria-selected", "true");

  // 2. Hide inactive panels and reveal target panel
  document.querySelectorAll(".drawer-panel").forEach(panel => {
    if (panel.id === `${target}Panel`) {
      panel.classList.add("active");
      panel.removeAttribute("hidden");
    } else {
      panel.classList.remove("active");
      panel.setAttribute("hidden", "");
    }
  });

  // 3. Subsystem hook (if special initialization is required)
  if (target === "ports" && window.DeskAIPorts) {
    window.DeskAIPorts.refresh();
  }
  break;
}
```

---

## 4. CSS Styling & Design Token Specifications

Styles are defined in `src/deskai/static/css/components.css` using centralized CSS variables from `tokens.css`:

```css
/* Generic Drawer Panel Container */
.drawer-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.drawer-panel[hidden] {
  display: none !important;
}

/* Problems Viewport */
.problems-view {
  padding: var(--space-3);
  font-size: var(--text-xs);
  color: var(--text-muted);
  overflow-y: auto;
  flex: 1;
}

/* Empty State Label */
.problems-empty {
  color: var(--text-muted);
  font-style: italic;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
```

### 4.1 Design Tokens Reference
* `var(--space-3)`: `12px` padding.
* `var(--text-xs)`: `11px` font size.
* `var(--text-muted)`: `#8b949e` (satisfies $\ge 4.5:1$ contrast against `#16171a` `--bg-header`).

---

## 5. Data Schema & Diagnostics Rendering Contract

When diagnostics are streamed from language servers, linters, or file watchers, items are rendered according to the following contract:

```typescript
interface DiagnosticEntry {
  id: string;                      // Unique ID (e.g. "diag_01")
  source: string;                  // e.g. "flake8", "tsc", "eslint"
  code: string;                    // e.g. "F401", "TS2304"
  message: string;                 // Diagnostic description
  severity: "error" | "warning" | "info";
  file: string;                    // File path (e.g. "src/deskai/server/supervisor.py")
  range: {
    startLine: number;             // 1-based
    startCol: number;              // 1-based
    endLine: number;
    endCol: number;
  };
}
```

### 5.1 Rendered Item Structure (Target Format)
```html
<div class="problem-item" data-file="src/deskai/server/supervisor.py" data-line="20" data-col="5">
  <span class="problem-icon severity-error" aria-hidden="true">●</span>
  <span class="problem-message">Module 'sys' imported but unused</span>
  <span class="problem-location">src/deskai/server/supervisor.py [20, 5]</span>
  <span class="problem-source">flake8 (F401)</span>
</div>
```

---

## 6. Accessibility (WCAG 2.1 AA) Specifications

1. **Role Semantics:**
   * Container: `role="tabpanel"` linked to tab via `aria-labelledby="tab-problems"`.
   * Tab button: `role="tab"` with `aria-controls="problemsPanel"` and dynamic `aria-selected`.
2. **Accessible Empty State:**
   * Screen readers announce the clean workspace state (`"No problems have been detected in the workspace."`) immediately when the tab is focused.
3. **Keyboard Navigation:**
   * Tab is reachable via standard `Tab` / `ArrowRight` / `ArrowLeft` navigation within `.drawer-tabs`.
   * Activating with `Enter` or `Space` reveals the panel without moving focus unexpectedly.

---

## 7. Automated Test Plan & Traceability Matrix

| Test ID | Test Target | Verification Scope | Method |
| :--- | :--- | :--- | :--- |
| **TC-PRB-01** | Tab Declaration | `index.html` declares `data-target="problems"` tab | Static DOM / Unit Test |
| **TC-PRB-02** | Panel Declaration | `index.html` declares `#problemsPanel` with `.problems-view` | Static DOM / Unit Test |
| **TC-PRB-03** | Default Hidden State | `#problemsPanel` contains `hidden` attribute on initial page load | DOM Assertion |
| **TC-PRB-04** | Panel Activation | Clicking `Problems` tab removes `hidden` from `#problemsPanel` | Playwright E2E |
| **TC-PRB-05** | Empty State Text | `.problems-empty` text contains `"No problems have been detected"` | DOM String Test |
| **TC-PRB-06** | WCAG ARIA Linking | `aria-controls="problemsPanel"` matches panel id | DOM Contract Test |
