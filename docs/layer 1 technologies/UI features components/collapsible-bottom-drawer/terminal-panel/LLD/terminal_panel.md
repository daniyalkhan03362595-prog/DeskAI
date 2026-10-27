# Low-Level Design (LLD): Terminal Panel (Host Shell & Execution View)

**Document ID:** `ORX-LLD-TERMINAL-PANEL-V1`  
**Version:** `1.2` (Implemented Interactive PTY-Backed Architecture)  
**Parent Document:** `ORX-HLD-TERMINAL-PANEL-V1`  
**Target Codebase:** `DeskAI`  
**Primary Target Files:**
* `src/deskai/static/index.html`
* `src/deskai/static/css/tokens.css`
* `src/deskai/static/css/components.css`
* `src/deskai/static/js/events.js`
* `src/deskai/static/js/terminal.js`
* `src/deskai/server/terminal.py`
* `src/deskai/server/supervisor.py`
* `src/deskai/bridge/api.py`
* `src/deskai/bridge/lifecycle.py`
**Status:** Implemented  
**Date:** October 28, 2026  

---

## 1. Executive Summary & Objective

The **Terminal Panel** (`#terminalPanel`) is the default visible viewport inside DeskAI's Collapsible Bottom Drawer (`#bottomDrawer`). It provides developers with an embedded command execution and shell console interface.

DeskAI implements a fully interactive, secure, PTY-backed host terminal powered by vendored **`xterm.js`** 5.3.0 (with fit addon 0.8.0), connecting via binary WebSocket to `src/deskai/server/terminal.py`. The legacy static placeholder `<pre><code>` has been completely replaced with `#terminalHost`, strict threat modeling, dedicated binary WebSocket transport, zero layout shift, and WCAG 2.1 AA accessibility.

---

## 2. Architectural Decisions & Scope (D1 - D3)

1. **D1 (User-Only Interactive Shell):** The terminal provides an interactive shell for the user. AI/agent command execution is strictly out of scope; agent commands will be routed through the UEC approval flow in a separate review/phase and never typed directly into the user's shell.
2. **D2 (Vendored xterm.js):** Zero frameworks. `xterm.js` (and the `fit` addon) is vendored under `static/vendor/` with an integrity-checked entry in `MANIFEST.json`, identical to the integration of `CodeMirror` and `DOMPurify`. No hand-rolled VT emulator.
3. **D3 (CSP Policy):** `'unsafe-eval'` remains in the CSP for now, but Phase 5 includes an empirical backend spike across PyWebView engines to verify whether it can be safely removed.

---

## 3. Threat Model & Security Controls (P0)

A terminal exposes arbitrary shell execution and is the highest-privilege surface in DeskAI:

1. **Origin & Privilege Boundaries:**
   * An XSS attack in the frontend must not trivially gain host RCE.
   * Spawning a shell requires an explicit native confirmation dialog on first run per app session: `"Open a host shell in <workspace name>?"`.
   * Bridge APIs (`terminal_open`, `terminal_close`) enforce `self._is_origin_allowed()` with verified local origin checks.
   * Transport routes strictly validate `Host: 127.0.0.1:{port}`, `Origin: http://127.0.0.1:{port}`, and cryptographic session cookies.
2. **Server-Side `cwd` Binding:**
   * Working directory is strictly resolved from `bridge.get_workspace_root()`.
   * Enforces `is_disallowed_workspace_root(root) == False` and `is_safe_workspace_path(root) == True`.
   * Any client-provided `cwd` is rejected.
3. **Child Environment Sanitization:**
   * Only explicit allowlisted variables are passed to child processes:
     `HOME`, `USER`, `LOGNAME`, `LANG`, `LC_*`, `PATH`, `SHELL`, `TERM=xterm-256color`, `COLORTERM=truecolor` (Windows also: `SystemRoot`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `TEMP`, `TMP`, `ComSpec`, `PATHEXT`).
   * Explicitly strips all `DESKAI_*` secrets and internal launch tokens.
4. **Concurrency & Resource Limits:**
   * Maximum 4 concurrent terminal sessions per application.
   * Unguessable session IDs (`secrets.token_urlsafe(32)`).
   * 256 KB bounded server-side ring replay buffer per session for client resynchronization.
5. **Teardown & Reaping:**
   * Graceful `SIGHUP` to the process group, escalating to `SIGKILL` after 3 seconds, followed by zombie process reaping.
   * Registered with `DesktopServer.stop()` and `WindowLifecycleHandler`.
   * Dirty-exit confirmation dialog prompts if an active terminal is running.

---

## 4. DOM Hierarchy & Component Markup

### 4.1 Terminal Panel Container (Phase 3 Target)
Declared within `#drawerContent` in `src/deskai/static/index.html`:

```html
<!-- Terminal Panel (Default Active) -->
<div class="drawer-panel active" id="terminalPanel" role="tabpanel" aria-labelledby="tab-terminal">
  <div id="terminalHost" role="log" aria-label="Terminal output" aria-live="off"></div>
  <div class="terminal-footer-hint" aria-hidden="true">
    <span>Ctrl+Shift+M: Move focus to tab</span>
  </div>
</div>
```

### 4.2 Associated Tab Trigger
Declared in `.drawer-tabs` in `src/deskai/static/index.html`:
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

## 5. CSS Styling & Layout Specifications

Styles are maintained in `src/deskai/static/css/components.css` referencing centralized CSS variables from `tokens.css`:

```css
/* Drawer Content Scrollable Area */
.drawer-content {
  flex: 1;
  overflow: auto;
  padding: var(--space-2);
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

/* Terminal Host Container */
#terminalHost {
  flex: 1;
  width: 100%;
  height: 100%;
  background-color: var(--terminal-bg);
  overflow: hidden;
}

/* Terminal Footer Accessibility Hint */
.terminal-footer-hint {
  padding: 2px var(--space-2);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-muted);
  border-top: 1px solid var(--border-subtle);
  background-color: var(--bg-surface);
}

/* Read-Only Output Log View (Output Panel) */
.terminal-view {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.5;
}
```

### 5.1 Design Tokens Reference
* `var(--font-mono)`: `"JetBrains Mono", "Fira Code", "Cascadia Code", monospace`
* `var(--text-xs)`: `11px`
* `var(--text-secondary)`: `#9ca0a6` (6.76:1 contrast against `#17181b` `--bg-header`, passing WCAG AA 4.5:1)
* `var(--color-primary)`: `#d99b26` (2px active bottom border indicator)
* `var(--color-danger)`: `#ef4444` (error states; note `--color-error` does not exist)
* Terminal ANSI palette (Phase 3 addition to `tokens.css`): `--terminal-bg`, `--terminal-fg`, `--terminal-cursor`, `--terminal-selection`, `--ansi-black`, `--ansi-red`, `--ansi-green`, `--ansi-yellow`, `--ansi-blue`, `--ansi-magenta`, `--ansi-cyan`, `--ansi-white` (+ bright variants), each audited $\ge 4.5:1$ contrast against `--terminal-bg`.

---

## 6. Read-Only Output Panel LogView (Phase 3)

For `#channelOutput` (read-only output log view):
* Replaces naive string concatenation with a batched `LogView` component.
* Batched via `requestAnimationFrame`.
* Uses `document.createElement("span")` and `textContent` (never `innerHTML`).
* Caps buffer at 10,000 lines (counting lines, not spans).
* Auto-scrolls only if user is within 40px of bottom (`scrollHeight - scrollTop - clientHeight < 40`).
* Strips ANSI escape sequences rather than misinterpreting them.

---

## 7. Accessibility (WCAG 2.1 AA) Specifications

1. **Focus Management:**
   * Selecting the Terminal tab does **NOT** steal focus into the terminal (preserves roving tabindex; verified by `test_tablist_roving_arrow_key_focus`).
   * Focus enters terminal on `Tab` from tablist or `Enter` on panel.
2. **Keyboard Trap Escape (WCAG 2.1.2):**
   * `Ctrl+Shift+M` (macOS `Cmd+Shift+M`) shifts focus back to the `Terminal` tab button.
   * Visible hint is displayed in `.terminal-footer-hint`.
3. **Hotkey Isolation:**
   * While `#terminalHost` or xterm textarea is focused, global event listeners for `Ctrl+S`, `Ctrl+W`, and `Ctrl+Enter` in `events.js` are suppressed, allowing shell line editing and hotkeys to pass through.
4. **Clipboard:**
   * `Ctrl+Shift+C` copies selection.
   * `Ctrl+Shift+V` pastes clipboard.
   * Plain `Ctrl+C` sends byte `0x03` (SIGINT) to PTY master when no text is selected.
5. **Screen Readers:**
   * Container uses `role="log"` and `aria-live="off"`.
   * Discrete lifecycle events announced via polite `#screenReaderAnnouncer`.

---

## 8. Automated Test Plan & Traceability Matrix

| Test ID | Test Target | Verification Scope | Method | Status |
| :--- | :--- | :--- | :--- | :--- |
| **TC-TRM-01** | Tab Declaration | `index.html` declares `data-target="terminal"` tab button | DOM Contract Test | Implemented |
| **TC-TRM-02** | Initial Active State | `Terminal` tab has `.active` class and `aria-selected="true"` at boot | DOM Assertion | Implemented |
| **TC-TRM-03** | Panel Declaration | `index.html` declares `#terminalPanel` with `.active` class | DOM Contract Test | Implemented |
| **TC-TRM-04** | Default Visible | `#terminalPanel` does NOT have `hidden` attribute on initial page load | DOM Assertion | Implemented |
| **TC-TRM-05** | Host Element | `#terminalHost` has `role="log"`, accessible name, and `aria-live="off"` | DOM Assertion | Implemented |
| **TC-TRM-06** | Font Family | `.terminal-view` computes to monospace font stack (`JetBrains Mono`, `Fira Code`, monospace) | CSS Computed Style Test | Implemented |
| **TC-TRM-07** | ARIA Binding | `aria-controls="terminalPanel"` matches panel id | DOM Contract Test | Implemented |
| **TC-TRM-08** | Spawn Gate & Security | Workspace check, origin validation, env token stripping | Backend Unit Test (`test_terminal_backend.py`) | Implemented |
| **TC-TRM-09** | PTY Lifecycle & Signals | Resize (`TIOCSWINSZ`), SIGINT (0x03), clean close / reap | Backend Unit Test (`test_terminal_backend.py`) | Implemented |
| **TC-TRM-10** | Transport Flow Control | Binary stream over `/ws/terminal/{id}`, high/low watermarks, resync | Backend Unit Test (`test_terminal_transport.py`) | Implemented |
| **TC-TRM-11** | Keyboard Trap Escape | `Ctrl+Shift+M` moves focus out to tablist; `Tab` enters xterm | Playwright Behavioral (`test_bottom_drawer_behavior.py`) | Implemented |
| **TC-TRM-12** | Hotkey Isolation | `Ctrl+W` and `Ctrl+S` suppressed when terminal focused (passes to shell) | Playwright Behavioral (`test_bottom_drawer_behavior.py`) | Implemented |
| **TC-TRM-13** | Scrollback Clamp | Max lines clamped to 10,000; zero `innerHTML` in terminal modules | Playwright Behavioral (`test_bottom_drawer_behavior.py`) | Implemented |
| **TC-TRM-14** | WCAG Contrast | ANSI palette & terminal tokens meet $\ge 4.5:1$ against `--terminal-bg` | Static CSS Audit (`test_task10_theme_a11y.py`) | Implemented |
| **TC-TRM-15** | Exit Lifecycle | Running status chip (`●`), dirty-exit confirmation warning, graceful kill | Backend / E2E Test (`test_bottom_drawer_behavior.py`) | Implemented |
| **TC-TRM-16** | CSP Backend Spike | PyWebView engine eval dependency audit across backends | Architecture Spike (`pywebview.md`) | Implemented |

---

## 9. Future Work

1. **Multi-Session Terminal Tabs:**
   * Support multiple concurrent shells via a `+` button in the drawer header and session switcher tabs/dropdown.
   * Session tabs with renameable titles, per-session scrollback buffers, and kill buttons.
2. **AI / Agent Command Execution Flow:**
   * Automated command proposals from AI agents routed exclusively through the UEC (Unified Execution Context) state machine and explicit user approval modal (`uec.approve` / `uec.reject`).
   * Agent execution rendered in distinct, read-only audit cards or dedicated non-interactive run targets; never typed silently into the user's interactive shell.
3. **Dynamic Terminal Configuration:**
   * User preference controls for font family, line height, cursor blink, and custom ANSI color themes synchronized via `tokens.css`.

