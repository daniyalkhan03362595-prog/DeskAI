# Low-Level Design (LLD): Terminal Panel (Host Shell & Execution View)

**Document ID:** `ORX-LLD-TERMINAL-PANEL-V1`  
**Version:** `1.0` (Defect-Resolved & Synchronized with Implemented Vanilla JS Codebase)  
**Parent Document:** `ORX-HLD-TERMINAL-PANEL-V1`  
**Target Codebase:** `DeskAI`  
**Primary Target Files:**
* `src/deskai/static/index.html` (Lines 101, 109-113)
* `src/deskai/static/css/components.css` (Lines 350-376)
* `src/deskai/static/js/events.js` (`case "drawer-tab"`)
**Status:** Approved for Implementation / Implemented  
**Date:** October 27, 2026  

---

## 1. Executive Summary & Objective

The **Terminal Panel** (`#terminalPanel`) is the default visible viewport inside DeskAI's Collapsible Bottom Drawer (`#bottomDrawer`). It provides developers with an embedded command execution and shell console interface.

This specification details the concrete DOM structure, tab synchronization logic, monospace typography tokens, stream buffer appending mechanisms, accessibility bindings, and test verification strategy.

---

## 2. DOM Hierarchy & Component Markup

The component is declared as the first child of `#drawerContent` in `src/deskai/static/index.html`:

```html
<!-- Terminal Panel (Default Active) -->
<div class="drawer-panel active" id="terminalPanel" role="tabpanel" aria-labelledby="tab-terminal">
  <pre class="terminal-view" id="terminalOutput"><code>DeskAI Host Shell Ready. Workspace active.</code></pre>
</div>
```

### 2.1 Associated Tab Trigger
The corresponding tab trigger in `.drawer-tabs` is defined with initial `.active` and `aria-selected="true"`:
```html
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
```

---

## 3. JavaScript Event Handling & Tab Orchestration

The panel's state is coordinated by the event delegation router in `src/deskai/static/js/events.js`:

```javascript
case "drawer-tab": {
  const target = trigger.getAttribute("data-target"); // "terminal"
  if (!target) return;

  // 1. Update Tab Visual and ARIA Selection States
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

  // 3. Subsystem Hook (if applicable)
  if (target === "ports" && window.DeskAIPorts) {
    window.DeskAIPorts.refresh();
  }
  break;
}
```

---

## 4. CSS Styling & Layout Specifications

All styles are defined in `src/deskai/static/css/components.css` using centralized CSS variables from `tokens.css`:

```css
/* Drawer Content Scrollable Area */
.drawer-content {
  flex: 1;
  overflow: auto;
  padding: var(--space-2);
}

/* Monospace Pre-formatted Shell Viewport */
.terminal-view {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.5;
}

/* Generic Panel Container */
.drawer-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.drawer-panel[hidden] {
  display: none !important;
}

/* Active Tab Indicator */
.drawer-tab.active {
  color: var(--text-primary);
  border-bottom: 2px solid var(--color-primary);
}
```

### 4.1 Design Tokens Reference
* `var(--font-mono)`: `JetBrains Mono, Menlo, Monaco, Consolas, "Courier New", monospace`
* `var(--text-xs)`: `11px`
* `var(--text-secondary)`: `#cbd5e1` ($\ge 7:1$ contrast against `#16171a` `--bg-header`)
* `var(--color-primary)`: `#f59e0b` / `#3b82f6` (2px active bottom border indicator)

---

## 5. Streaming Output Append Helper

For streaming CLI stdout and stderr into `#terminalOutput` safely:

```javascript
/**
 * Safe Terminal Output Streaming Helper
 */
function appendTerminalOutput(text, isError = false) {
  const terminalEl = document.getElementById("terminalOutput");
  if (!terminalEl) return;

  const codeEl = terminalEl.querySelector("code") || terminalEl;
  
  if (isError) {
    const errorSpan = document.createElement("span");
    errorSpan.className = "terminal-error-line";
    errorSpan.style.color = "var(--color-error)";
    errorSpan.textContent = text;
    codeEl.appendChild(errorSpan);
  } else {
    codeEl.appendChild(document.createTextNode(text));
  }

  // Auto-scroll to latest output line
  const container = terminalEl.closest(".drawer-content");
  if (container) {
    container.scrollTop = container.scrollHeight;
  }
}
```

---

## 6. Accessibility (WCAG 2.1 AA) Specifications

1. **Semantic Role Binding:**
   * Container uses `role="tabpanel"` linked to `#tab-terminal` via `aria-labelledby`.
   * Tab button uses `role="tab"`, `aria-selected="true"`, and `aria-controls="terminalPanel"`.
2. **Accessible Monospace Display:**
   * Uses semantic `<pre><code>` hierarchy, enabling screen readers to identify pre-formatted code/command blocks.
3. **Contrast Compliance:**
   * Default text uses `--text-secondary` with contrast ratio $\ge 7:1$ against `--bg-header`.

---

## 7. Automated Test Plan & Traceability Matrix

| Test ID | Test Target | Verification Scope | Method |
| :--- | :--- | :--- | :--- |
| **TC-TRM-01** | Tab Declaration | `index.html` declares `data-target="terminal"` tab button | DOM Contract Test |
| **TC-TRM-02** | Initial Active State | `Terminal` tab has `.active` class and `aria-selected="true"` at boot | DOM Assertion |
| **TC-TRM-03** | Panel Declaration | `index.html` declares `#terminalPanel` with `.active` class | DOM Contract Test |
| **TC-TRM-04** | Default Visible | `#terminalPanel` does NOT have `hidden` attribute on initial page load | DOM Assertion |
| **TC-TRM-05** | Boot Message | `#terminalOutput` contains `"DeskAI Host Shell Ready"` | DOM String Test |
| **TC-TRM-06** | Font Family | `.terminal-view` computes to monospace font stack | CSS Computed Style Test |
| **TC-TRM-07** | ARIA Binding | `aria-controls="terminalPanel"` matches panel id | DOM Contract Test |
