# Low-Level Design (LLD): Ports Panel & Listening Ports Monitor

**Document ID:** `ORX-LLD-PORTS-PANEL-V1`  
**Version:** `1.1` (Synchronized with Implemented Vanilla JS & Python Bridge Architecture)  
**Parent Document:** `ORX-HLD-PORTS-PANEL-V1`  
**Target Codebase:** `DeskAI`  
**Primary Target Files:**
* `src/deskai/static/index.html`
* `src/deskai/static/js/ports.js`
* `src/deskai/static/js/bridge.js`
* `src/deskai/static/js/events.js`
* `src/deskai/static/css/components.css`
* `src/deskai/bridge/api.py` (`get_listening_ports`, `open_port`, `probe_port`, `open_external_url`)
**Status:** Approved for Implementation / Implemented  
**Date:** October 27, 2026  

---

## 1. Executive Summary & Objective

The **Ports Panel** (`#portsPanel`) is an embedded subsystem within DeskAI's Collapsible Bottom Drawer (`#bottomDrawer`). It surfaces active TCP listening sockets, identifies host processes, facilitates user-defined port monitoring, provides native browser launching, clipboard copying, and live status probing.

This document details the concrete class structures, IPC protocols, DOM rendering algorithms, CSS token integration, and automated verification tests.

---

## 2. DOM Hierarchy & Component Layout

```html
<!-- Ports Panel -->
<div class="drawer-panel" id="portsPanel" role="tabpanel" aria-labelledby="tab-ports" tabindex="0" hidden>
  <div class="ports-toolbar">
    <div class="ports-toolbar-left">
      <span class="ports-title">Forwarded &amp; Local Ports</span>
      <span class="ports-count" id="portsCountBadge">0 active</span>
      <div class="ports-filter-wrapper">
        <input type="text" id="portsFilterInput" class="ports-filter-input" placeholder="Filter ports, process, PID..." aria-label="Filter ports by port number, process name, or PID" />
      </div>
      <label class="ports-toggle-label">
        <input type="checkbox" id="portsTransientToggle" />
        <span>Show transient ports (32768+)</span>
      </label>
    </div>
    <div class="ports-toolbar-right">
      <button class="ports-btn" id="addPortBtn" data-action="add-port" data-action-alias="watch-port" title="Watch a Port" aria-label="Watch a Port">
        <span class="ports-btn-icon">+</span> Watch Port
      </button>
      <button class="ports-btn icon-only" id="refreshPortsBtn" data-action="refresh-ports" title="Refresh Ports" aria-label="Refresh Ports">
        ↻
      </button>
    </div>
  </div>

  <div id="portsWarningBanner" class="ports-warning-banner" hidden role="region" aria-label="Port Scanner Notice">
    <span id="portsWarningMessage" class="ports-warning-text"></span>
    <button type="button" id="portsWarningDismissBtn" class="ports-warning-dismiss" aria-label="Dismiss notice">✕</button>
  </div>

  <div class="ports-table-container">
    <table class="ports-table" id="portsTable">
      <thead>
        <tr>
          <th scope="col" data-sort="port" aria-sort="ascending" tabindex="0" role="columnheader">Port</th>
          <th scope="col" data-sort="protocol" aria-sort="none" tabindex="0" role="columnheader">Protocol</th>
          <th scope="col" data-sort="address" aria-sort="none" tabindex="0" role="columnheader">Local Address</th>
          <th scope="col" data-sort="process" aria-sort="none" tabindex="0" role="columnheader">Process / Service</th>
          <th scope="col" data-sort="pid" aria-sort="none" tabindex="0" role="columnheader">PID</th>
          <th scope="col" data-sort="origin" aria-sort="none" tabindex="0" role="columnheader">Origin</th>
          <th scope="col" data-sort="status" aria-sort="none" tabindex="0" role="columnheader">Status</th>
          <th scope="col">Actions</th>
        </tr>
      </thead>
      <tbody id="portsTableBody">
        <!-- Dynamically rendered by PortsManager -->
      </tbody>
    </table>
  </div>
</div>
```

---

## 3. Class Structure & State Model (`src/deskai/static/js/ports.js`)

```javascript
export class PortsManager {
  constructor() {
    this.customPorts = this.loadWatchedPorts();
    this.portsList = [];
    this.filterText = "";
    this.showTransient = false;
    this.sortColumn = "port";
    this.sortAsc = true;

    this._inflight = false;
    this._again = false;
    this._lastSignature = null;
    this._lastCount = null;
    this._dismissedWarning = null;
    this._pollingTimer = null;
    this._isPollingActive = false;
    this._pollIntervalMs = 3000;

    this.setupListeners();
  }

  getStorageKey();
  loadWatchedPorts();
  saveWatchedPorts();
  startPolling(ms = 3000);
  stopPolling();
  setupListeners();
  showWarning(text, type = "warning");
  clearWarning();
  showToast(message, type = "info", duration = 3000);
  promptAddPort();
  submitWatchPort();
  removePort(portNum, host = "127.0.0.1");
  async openPort(port, host = "127.0.0.1", btnElement = null);
  async copyPort(url, btnElement = null);
  setButtonSuccessState(btnElement, duration = 300);
  setButtonCopiedState(btnElement, duration = 300);
  async probeSinglePort(custom);
  probeWatchedPorts();
  async refresh();
  handleRefreshResponse(res);
  getFilteredAndSortedPorts();
  render();
}
```

### 3.1 Field Specifications

| Property | Type | Description |
| :--- | :--- | :--- |
| `this.customPorts` | `Array<PortItem>` | User-watched ports loaded from `localStorage`. |
| `this.portsList` | `Array<PortItem>` | Merged array of OS-discovered + watched ports. |
| `this.filterText` | `string` | Query string matching port number, process name, or PID. |
| `this.showTransient` | `boolean` | When false, hides ephemeral ports $\ge 32768$. |
| `this.sortColumn` | `string` | Active sort column key (e.g. `"port"`, `"pid"`, `"process"`). |
| `this.sortAsc` | `boolean` | Direction of active column sort. |
| `this._inflight` | `boolean` | Flag indicating an asynchronous backend scan is currently running. |
| `this._again` | `boolean` | Coalescing flag indicating a queued refresh should execute once inflight finishes. |
| `this._lastSignature` | `string` | Serialized signature used to skip redundant DOM re-renders. |

### 3.2 Action Button Inline Feedback (`openPort`, `copyPort`, `setButtonSuccessState`)

To eliminate distracting corner toast popups and provide immediate interaction feedback:
* `openPort(port, host, btnElement)` calls `NativeBridge.openPort` and on success triggers `setButtonSuccessState(btnElement, 300)`.
* `copyPort(url, btnElement)` writes the target URL to clipboard via modern `navigator.clipboard.writeText` with a sandboxed `<textarea>` + `document.execCommand("copy")` fallback, and on success triggers `setButtonSuccessState(btnElement, 300)`.
* On success, `setButtonSuccessState(btnElement, duration = 300)` transforms the clicked button into a sleek vector SVG checkmark (`<svg class="port-check-icon">`) with `var(--color-success)` borders and `var(--color-success-subtle)` background.
* The button's rendered width is temporarily locked via `minWidth` to prevent table column layout shift (CLS).
* After a snappy 300ms (0.3s), the button smoothly reverts to its resting label (`🌐 Open` or `📋 Copy`) and original ARIA attributes.

---

## 4. NativeBridge Integration (`src/deskai/static/js/bridge.js`)

```javascript
export const NativeBridge = {
  whenReady(): Promise<void>,
  async openPort(port: number, host: string = "127.0.0.1"): Promise<boolean>,
  async probePort(port: number, host: string = "127.0.0.1"): Promise<boolean>,
  async openExternalUrl(url: string): Promise<boolean>,
  async listPorts(): Promise<{ status: string, ports: Array<PortItem>, warnings: Array<string> }>
};
```

---

## 5. Python Bridge Backend Implementation (`src/deskai/bridge/api.py`)

### 5.1 Methods Summary

```python
class DesktopBridgeAPI:
    def get_listening_ports(self) -> dict:
        """Origin-guarded listening port enumeration."""
        ...

    def open_port(self, port: int, host: str = "127.0.0.1") -> bool:
        """Secure port launch into system browser."""
        ...

    def probe_port(self, port: int, host: str = "127.0.0.1") -> bool:
        """150ms TCP connect probe."""
        ...

    def open_external_url(self, url: str) -> bool:
        """Hardened external URL launch; returns bool."""
        ...
```

---

## 6. Verification & Traceability Matrix

| Test ID | File | Description | Status |
| :--- | :--- | :--- | :--- |
| `TEST-PORT-ORIGIN` | `tests/test_ports_tab.py` | Validates origin guard rejects unauthorized origins & subdomains | Passed |
| `TEST-PORT-SUPERVISOR` | `tests/test_ports_tab.py` | Asserts supervisor row present, `openable: false`, `exposure: loopback` | Passed |
| `TEST-PORT-DUAL-STACK` | `tests/test_ports_tab.py` | Asserts IPv4 and IPv6 listeners on same port produce distinct rows | Passed |
| `TEST-PORT-FILTERING` | `tests/test_ports_tab.py` | Validates $<1024$ noise filter, LAN IP exclusion, `::ffff:x` unwrap | Passed |
| `TEST-PORT-ACCESS-DENIED` | `tests/test_ports_tab.py` | Validates `psutil.AccessDenied` appends `socket_table_denied` warning | Passed |
| `TEST-PORT-MISSING-PSUTIL` | `tests/test_ports_tab.py` | Validates missing psutil appends `psutil_missing` warning | Passed |
| `TEST-OPEN-PORT-VALIDATION` | `tests/test_ports_tab.py` | Validates `open_port` rejects bools, 0, 65536, supervisor port, non-loopback | Passed |
| `TEST-OPEN-URL-HARDENING` | `tests/test_ports_tab.py` | Validates `open_external_url` rejects control chars, userinfo, scheme escapes | Passed |
| `TEST-STATIC-ARIA-SPEC` | `tests/test_ports_tab.py` | Verifies `aria-valuenow`, `aria-expanded`, tab/tabpanel role relationships | Passed |
| `TEST-CSS-TOKEN-HYGIENE` | `tests/test_ports_tab.py` | Verifies zero undefined `var(--*)` and zero raw colors outside tokens.css | Passed |
| `TEST-WINDOW-BG-MATCH` | `tests/test_ports_tab.py` | Verifies `BG_APP` constant in window.py matches `--bg-app` in tokens.css | Passed |
| `TEST-PW-TAB-EXPANDS` | `tests/test_bottom_drawer_behavior.py` | Verifies clicking tab expands collapsed drawer | Passed |
| `TEST-PW-RESIZER-DBLCLICK` | `tests/test_bottom_drawer_behavior.py` | Verifies double-click resizer toggles collapse and restores height | Passed |
| `TEST-PW-RESIZER-KEYBOARD` | `tests/test_bottom_drawer_behavior.py` | Verifies ArrowUp/ArrowDown, Home, End keyboard handling on resizer | Passed |
| `TEST-PW-COLLAPSED-A11Y` | `tests/test_bottom_drawer_behavior.py` | Verifies `.drawer-content` has `display: none` when collapsed | Passed |
| `TEST-PW-TAB-ROVING` | `tests/test_bottom_drawer_behavior.py` | Verifies ArrowLeft/ArrowRight roving focus across drawer tabs | Passed |
| `TEST-PW-FOCUS-PRESERVED` | `tests/test_bottom_drawer_behavior.py` | Verifies re-render restores active button focus inside ports table | Passed |

---

## 7. Future Work (Out of Scope for Layer 1)

1. **Process Termination (`kill_port`):** Bridge endpoint with OS-level confirmation dialog allowing users to kill orphan background processes.
2. **Framework Heuristics:** Identifying frameworks by scanning process execution arguments or inspecting known ports (e.g. 5173 -> Vite, 3000 -> Next.js).
3. **HTTP Title Probing:** Background probe sending `HEAD` request to HTTP listeners to retrieve page title for display in the table.
