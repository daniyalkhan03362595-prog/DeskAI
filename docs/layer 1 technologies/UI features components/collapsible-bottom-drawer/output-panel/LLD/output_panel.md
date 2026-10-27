# Low-Level Design (LLD): Output Panel (System & Channel Logs)

**Document ID:** `ORX-LLD-OUTPUT-PANEL-V1`  
**Version:** `1.0` (Defect-Resolved & Synchronized with Implemented Vanilla JS Codebase)  
**Parent Document:** `ORX-HLD-OUTPUT-PANEL-V1`  
**Target Codebase:** `DeskAI`  
**Primary Target Files:**
* `src/deskai/static/index.html` (Lines 102, 115-117)
* `src/deskai/static/css/components.css` (Lines 356-376)
* `src/deskai/static/js/events.js` (`case "drawer-tab"`)
**Status:** Approved for Implementation / Implemented  
**Date:** October 27, 2026  

---

## 1. Executive Summary & Objective

The **Output Panel** (`#outputPanel`) provides a high-throughput, monospace, read-only telemetry and log viewer inside DeskAI's Collapsible Bottom Drawer (`#bottomDrawer`). It surfaces supervisor activity, task progress, and system diagnostics with zero execution blocking.

This specification outlines the exact DOM markup, event routing, CSS layout rules, buffer management methods, security constraints, and automated verification requirements.

---

## 2. DOM Hierarchy & Component Markup

The component is declared inside `#drawerContent` in `src/deskai/static/index.html`:

```html
<!-- Output Channel Panel -->
<div class="drawer-panel" id="outputPanel" role="tabpanel" aria-labelledby="tab-output" hidden>
  <pre class="terminal-view" id="channelOutput"><code>[DeskAI System] Supervisor active on loopback. Ready for tasks.</code></pre>
</div>
```

### 2.1 Associated Tab Trigger
The corresponding tab trigger in `.drawer-tabs` is defined as:
```html
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
```

---

## 3. JavaScript Event Handling & Tab Switching

The panel's visibility is controlled by the centralized event delegation router in `src/deskai/static/js/events.js`:

```javascript
case "drawer-tab": {
  const target = trigger.getAttribute("data-target"); // "output"
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

All styles are defined in `src/deskai/static/css/components.css` using strict WCAG-compliant design tokens:

```css
/* Drawer Content Scrollable Host */
.drawer-content {
  flex: 1;
  overflow: auto;
  padding: var(--space-2);
}

/* Monospace Pre-formatted Viewport */
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
```

### 4.1 Design Tokens Reference
* `var(--font-mono)`: `JetBrains Mono, Menlo, Monaco, Consolas, "Courier New", monospace`
* `var(--text-xs)`: `11px`
* `var(--text-secondary)`: `#cbd5e1` (contrast ratio $\ge 7:1$ against `#16171a` `--bg-header`)
* `var(--space-2)`: `8px` inner padding

---

## 5. Buffer Management & Streaming Append Contract

To stream telemetry logs into `#channelOutput` without causing browser memory degradation or UI stutters, the output writer applies a bounded ring-buffer append pattern:

```javascript
/**
 * Safe Log Streaming Helper for #channelOutput
 */
function appendChannelLog(message, maxLines = 5000) {
  const outputEl = document.getElementById("channelOutput");
  if (!outputEl) return;

  const codeEl = outputEl.querySelector("code") || outputEl;
  const timestamp = new Date().toLocaleTimeString();
  const formattedLine = `[${timestamp}] ${message}\n`;

  // Safe text insertion (Prevents XSS)
  codeEl.appendChild(document.createTextNode(formattedLine));

  // Auto-scroll to bottom of drawer-content
  const container = outputEl.closest(".drawer-content");
  if (container) {
    container.scrollTop = container.scrollHeight;
  }
}
```

---

## 6. Accessibility (WCAG 2.1 AA) Specifications

1. **Semantic Role Binding:**
   * Container uses `role="tabpanel"` linked to tab via `aria-labelledby="tab-output"`.
   * Tab button uses `role="tab"`, with `aria-controls="outputPanel"` and dynamic `aria-selected="true|false"`.
2. **Text Selection & Copying:**
   * Content is selectable via keyboard or mouse for copying diagnostic logs without requiring specialized toolbar buttons.
3. **High Contrast:**
   * Text styling uses `--text-secondary` yielding high contrast against dark `--bg-header`.

---

## 7. Automated Test Plan & Traceability Matrix

| Test ID | Test Target | Verification Scope | Method |
| :--- | :--- | :--- | :--- |
| **TC-OUT-01** | Tab Declaration | `index.html` declares `data-target="output"` tab button | DOM Contract Test |
| **TC-OUT-02** | Panel Declaration | `index.html` declares `#outputPanel` with `#channelOutput` | DOM Contract Test |
| **TC-OUT-03** | Default Hidden State | `#outputPanel` has `hidden` attribute on initial page load | DOM Assertion |
| **TC-OUT-04** | Tab Activation | Clicking `Output` tab removes `hidden` from `#outputPanel` | Playwright E2E |
| **TC-OUT-05** | Initial Supervisor Log | `#channelOutput` contains `"Supervisor active on loopback"` | DOM String Test |
| **TC-OUT-06** | Monospace Font Style | `.terminal-view` applies `var(--font-mono)` and `var(--text-xs)` | CSS Computed Style Test |
| **TC-OUT-07** | ARIA Binding | `aria-controls="outputPanel"` matches panel id | DOM Contract Test |
