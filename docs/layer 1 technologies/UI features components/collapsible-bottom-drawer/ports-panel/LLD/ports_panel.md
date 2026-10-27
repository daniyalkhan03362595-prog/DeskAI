# Low-Level Design (LLD): Ports Panel & Listening Ports Monitor

**Document ID:** `ORX-LLD-PORTS-PANEL-V1`  
**Version:** `1.0` (Defect-Resolved & Synchronized with Implemented Vanilla JS & Python Bridge Architecture)  
**Parent Document:** `ORX-HLD-PORTS-PANEL-V1`  
**Target Codebase:** `DeskAI`  
**Primary Target Files:**
* `src/deskai/static/index.html` (Lines 126-160)
* `src/deskai/static/js/ports.js`
* `src/deskai/static/js/bridge.js`
* `src/deskai/static/js/events.js`
* `src/deskai/static/css/components.css` (Lines 389-550)
* `src/deskai/bridge/api.py` (`get_listening_ports`)
**Status:** Approved for Implementation / Implemented  
**Date:** October 27, 2026  

---

## 1. Executive Summary & Objective

The **Ports Panel** (`#portsPanel`) is an embedded subsystem within DeskAI's Collapsible Bottom Drawer (`#bottomDrawer`). It surfaces active TCP listening sockets, identifies host processes, facilitates user-defined port monitoring, and provides native browser launching and clipboard copying.

This document details the concrete class structures, IPC protocols, DOM rendering algorithms, CSS token integration, and automated verification tests.

---

## 2. DOM Hierarchy & Component Layout

The panel is declared inside `#drawerContent` in `src/deskai/static/index.html`:

```html
<!-- Ports Panel -->
<div class="drawer-panel" id="portsPanel" hidden>
  <!-- Toolbar Header -->
  <div class="ports-toolbar">
    <div class="ports-toolbar-left">
      <span class="ports-title">Forwarded &amp; Local Ports</span>
      <span class="ports-count" id="portsCountBadge">0 active</span>
    </div>
    <div class="ports-toolbar-right">
      <button class="ports-btn" id="addPortBtn" data-action="add-port" title="Forward a Port">
        <span class="ports-btn-icon">+</span> Forward Port
      </button>
      <button class="ports-btn icon-only" id="refreshPortsBtn" data-action="refresh-ports" title="Refresh Ports" aria-label="Refresh Ports">
        ↻
      </button>
    </div>
  </div>

  <!-- Scrollable Table Container -->
  <div class="ports-table-container">
    <table class="ports-table" id="portsTable">
      <thead>
        <tr>
          <th scope="col">Port</th>
          <th scope="col">Protocol</th>
          <th scope="col">Local Address</th>
          <th scope="col">Process / Service</th>
          <th scope="col">Origin</th>
          <th scope="col">Status</th>
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

The client-side ports lifecycle is managed by the `PortsManager` class:

```javascript
export class PortsManager {
  constructor() {
    this.customPorts = []; // Array of user-forwarded port objects
    this.portsList = [];   // Merged, deduplicated, sorted active ports
    this.tableBody = document.getElementById("portsTableBody");
    this.countBadge = document.getElementById("portsCountBadge");
  }

  async refresh();
  promptAddPort();
  removePort(portNum);
  async openPort(url);
  async copyPort(url);
  render();
}
```

### 3.1 Field Specifications

| Property | Type | Description |
| :--- | :--- | :--- |
| `this.customPorts` | `Array<PortItem>` | User-added ports created via `promptAddPort()`. Persists for session duration. |
| `this.portsList` | `Array<PortItem>` | Combined array of detected and custom ports, sorted numerically ascending by port. |
| `this.tableBody` | `HTMLTableSectionElement` | Cached reference to `<tbody>` element for dynamic rendering. |
| `this.countBadge` | `HTMLSpanElement` | Badge indicating the total number of active ports (e.g. `7 active`). |

### 3.2 Port Item Schema
```typescript
interface PortItem {
  port: number;          // Port number (1 - 65535)
  protocol: string;      // "HTTP" | "HTTPS" | "TCP"
  address: string;       // e.g. "http://127.0.0.1:35635" or "http://localhost:3000"
  process: string;       // Friendly process name, "DeskAI Supervisor", or "PID <n>"
  status: string;        // "Listening" | "Monitored"
  origin: string;        // "System" | "Local" | "Forwarded"
  isCustom?: boolean;    // true if added via + Forward Port
}
```

---

## 4. Algorithmic Workflows & Concrete Implementations

### 4.1 Refresh & Deduplication Algorithm
```javascript
async refresh() {
  try {
    const res = await NativeBridge.listPorts();
    const detected = (res && res.ports) ? res.ports : [];
    
    // Merge detected with custom user forwarded ports
    const combined = [...detected];
    const seen = new Set(detected.map(p => Number(p.port)));

    for (const custom of this.customPorts) {
      if (!seen.has(Number(custom.port))) {
        combined.push(custom);
        seen.add(Number(custom.port));
      }
    }

    this.portsList = combined.sort((a, b) => Number(a.port) - Number(b.port));
    this.render();
  } catch (err) {
    console.error("[PortsManager] Failed to refresh ports:", err);
  }
}
```

### 4.2 Safe DOM Rendering Pipeline (XSS Prevention)
The `render()` method explicitly constructs DOM elements using `document.createElement()` and `element.textContent`, completely avoiding `innerHTML` vulnerabilities:

```javascript
render() {
  if (!this.tableBody) this.tableBody = document.getElementById("portsTableBody");
  if (!this.countBadge) this.countBadge = document.getElementById("portsCountBadge");

  if (this.countBadge) {
    this.countBadge.textContent = `${this.portsList.length} active`;
  }

  if (!this.tableBody) return;

  // Clear existing rows safely
  while (this.tableBody.firstChild) {
    this.tableBody.removeChild(this.tableBody.firstChild);
  }

  if (this.portsList.length === 0) {
    const emptyRow = document.createElement("tr");
    const emptyCell = document.createElement("td");
    emptyCell.colSpan = 7;
    emptyCell.className = "ports-empty";
    emptyCell.textContent = 'No active listening ports detected. Click "+ Forward Port" to add one.';
    emptyRow.appendChild(emptyCell);
    this.tableBody.appendChild(emptyRow);
    return;
  }

  for (const item of this.portsList) {
    const row = document.createElement("tr");

    // 1. Port Number Badge
    const tdPort = document.createElement("td");
    const portBadge = document.createElement("span");
    portBadge.className = "port-num-badge";
    portBadge.textContent = String(item.port);
    tdPort.appendChild(portBadge);

    // 2. Protocol Badge
    const tdProto = document.createElement("td");
    const protoBadge = document.createElement("span");
    protoBadge.className = "port-protocol-badge";
    protoBadge.textContent = item.protocol || "HTTP";
    tdProto.appendChild(protoBadge);

    // 3. Local Address Cell
    const tdAddr = document.createElement("td");
    tdAddr.className = "port-addr-cell";
    tdAddr.textContent = item.address;

    // 4. Process Name Cell
    const tdProc = document.createElement("td");
    tdProc.textContent = item.process || "--";

    // 5. Origin Cell
    const tdOrigin = document.createElement("td");
    tdOrigin.textContent = item.origin || "Local";

    // 6. Status Pill
    const tdStatus = document.createElement("td");
    const statusPill = document.createElement("span");
    statusPill.className = "port-status-pill";
    statusPill.textContent = item.status || "Listening";
    tdStatus.appendChild(statusPill);

    // 7. Actions Cell
    const tdActions = document.createElement("td");
    
    const openBtn = document.createElement("button");
    openBtn.className = "port-action-btn";
    openBtn.setAttribute("data-action", "open-port");
    openBtn.setAttribute("data-url", item.address);
    openBtn.title = "Open in Default Browser";
    openBtn.textContent = "🌐 Open";
    tdActions.appendChild(openBtn);

    const copyBtn = document.createElement("button");
    copyBtn.className = "port-action-btn";
    copyBtn.setAttribute("data-action", "copy-port");
    copyBtn.setAttribute("data-url", item.address);
    copyBtn.title = "Copy Address to Clipboard";
    copyBtn.textContent = "📋 Copy";
    tdActions.appendChild(copyBtn);

    if (item.isCustom) {
      const delBtn = document.createElement("button");
      delBtn.className = "port-action-btn";
      delBtn.setAttribute("data-action", "remove-port");
      delBtn.setAttribute("data-port", String(item.port));
      delBtn.title = "Stop Monitoring Port";
      delBtn.textContent = "✕";
      tdActions.appendChild(delBtn);
    }

    row.appendChild(tdPort);
    row.appendChild(tdProto);
    row.appendChild(tdAddr);
    row.appendChild(tdProc);
    row.appendChild(tdOrigin);
    row.appendChild(tdStatus);
    row.appendChild(tdActions);

    this.tableBody.appendChild(row);
  }
}
```

---

## 5. Backend Bridge Implementation (`src/deskai/bridge/api.py`)

The backend implementation enumerates network sockets using `psutil`, performs origin verification, and injects the active supervisor port:

```python
def get_listening_ports(self) -> dict:
    """
    Enumerates active local listening ports on loopback and host interfaces.
    Always includes the DeskAI supervisor port.
    """
    if not self._is_origin_allowed():
        return {"status": "error", "message": "Unauthorized origin", "ports": []}

    ports = []
    seen_ports = set()
    supervisor_port = getattr(getattr(self._manager, "server", None), "port", None)
    if supervisor_port:
        seen_ports.add(supervisor_port)
        ports.append(
            {
                "port": supervisor_port,
                "protocol": "HTTP",
                "address": f"http://127.0.0.1:{supervisor_port}",
                "process": "DeskAI Supervisor",
                "status": "Listening",
                "origin": "System",
            }
        )

    try:
        import psutil

        for conn in psutil.net_connections(kind="inet"):
            if conn.status == "LISTEN" and conn.laddr:
                ip = conn.laddr.ip
                port = conn.laddr.port
                if port in seen_ports:
                    continue
                # Restrict to local loopback/all-interface unprivileged ports
                if ip in ("127.0.0.1", "::1", "0.0.0.0", "::") and port >= 1024:
                    seen_ports.add(port)
                    proc_name = "Process"
                    if conn.pid:
                        try:
                            proc = psutil.Process(conn.pid)
                            proc_name = proc.name()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            proc_name = f"PID {conn.pid}"

                    ports.append(
                        {
                            "port": port,
                            "protocol": "HTTP",
                            "address": f"http://localhost:{port}",
                            "process": proc_name,
                            "status": "Listening",
                            "origin": "Local",
                        }
                    )
    except Exception:
        pass

    ports.sort(key=lambda x: x["port"])
    return {"status": "ok", "ports": ports}
```

---

## 6. CSS Specifications (`src/deskai/static/css/components.css`)

All elements leverage centralized CSS custom properties from `tokens.css`:

```css
/* Toolbar */
.ports-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-1) var(--space-1) var(--space-2);
  border-bottom: 1px solid var(--border-subtle);
  margin-bottom: var(--space-1);
}

.ports-title {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.ports-count {
  font-size: 10px;
  background: var(--bg-card);
  border: 1px solid var(--border-regular);
  color: var(--color-primary);
  border-radius: 10px;
  padding: 1px 6px;
}

/* Action Buttons */
.ports-btn {
  background: var(--bg-card);
  border: 1px solid var(--border-regular);
  color: var(--text-secondary);
  font-size: var(--text-xs);
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  transition: all var(--transition-fast);
}

.ports-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
  border-color: var(--border-input);
}

/* Table Styling */
.ports-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-xs);
  text-align: left;
}

.ports-table th {
  padding: 6px var(--space-2);
  color: var(--text-muted);
  font-weight: 500;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-header);
  position: sticky;
  top: 0;
  z-index: 1;
}

.ports-table td {
  padding: 6px var(--space-2);
  color: var(--text-primary);
  border-bottom: 1px solid var(--border-subtle);
  font-family: var(--font-mono);
  vertical-align: middle;
}

.port-status-pill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: 10.5px;
  color: var(--color-success);
}

.port-status-pill::before {
  content: "";
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-success);
}
```

---

## 7. Automated Test Plan & Traceability Matrix

Automated verification is anchored in `tests/test_ports_tab.py`:

| Test ID | Test Method | Verification Scope |
| :--- | :--- | :--- |
| **TC-PORT-01** | `test_get_listening_ports_origin_guarded` | Confirms bridge rejects unauthorized caller origins with `status: error`. |
| **TC-PORT-02** | `test_get_listening_ports_includes_supervisor` | Asserts Supervisor port is unconditionally present with `origin: System`. |
| **TC-PORT-03** | `test_index_html_declares_ports_tab_and_panel` | Confirms `#portsPanel`, `#portsTable`, `addPortBtn`, and `refreshPortsBtn` exist in HTML. |
| **TC-PORT-04** | `test_ports_js_module_exists_and_exports_manager` | Verifies `PortsManager` and `initPorts` are exported and contain action methods. |
| **TC-PORT-05** | `test_bridge_js_exposes_list_ports` | Validates `NativeBridge.listPorts()` is bound to window bridge. |
| **TC-PORT-06** | `test_horizontal_drawer_resizer_declared_in_index_html` | Verifies `#resizerBottom` exists with horizontal ARIA attributes. |
| **TC-PORT-07** | `test_resizer_row_defined_in_layout_css` | Verifies `.resizer-row` CSS cursor and hover rules. |
| **TC-PORT-08** | `test_events_js_binds_resizer_bottom` | Validates mouse drag and keyboard arrow event bindings in `events.js`. |
