/**
 * Ports Manager Module
 * Discovers and manages active listening ports and port forwardings.
 */
import { NativeBridge } from "./bridge.js";

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

  getStorageKey() {
    const root =
      (window.store && window.store.state && window.store.state.workspace && window.store.state.workspace.rootPath) ||
      "default";
    return `deskai_watched_ports_${root}`;
  }

  loadWatchedPorts() {
    try {
      const raw = localStorage.getItem(this.getStorageKey());
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          return parsed.map((p) => ({
            port: Number(p.port),
            host: p.host || "127.0.0.1",
            protocol: p.protocol || "TCP",
            address: p.address || `http://${p.host || "127.0.0.1"}:${p.port}`,
            process: p.process || "Watched",
            status: p.status || "Probing...",
            origin: "Watched",
            isCustom: true,
            exposure: p.exposure || "loopback",
            openable: p.openable !== false
          }));
        }
      }
    } catch (e) {
      console.warn("[PortsManager] Failed to read watched ports from localStorage", e);
    }
    return [];
  }

  saveWatchedPorts() {
    try {
      const data = this.customPorts.map((p) => ({
        port: p.port,
        host: p.host,
        protocol: p.protocol,
        address: p.address,
        process: p.process,
        origin: p.origin,
        exposure: p.exposure,
        openable: p.openable
      }));
      localStorage.setItem(this.getStorageKey(), JSON.stringify(data));
    } catch (e) {
      console.warn("[PortsManager] Failed to persist watched ports to localStorage", e);
    }
  }

  startPolling(ms = 3000) {
    this.stopPolling();
    this._isPollingActive = true;
    this._pollIntervalMs = ms;

    const scheduleNext = () => {
      if (!this._isPollingActive) return;
      this._pollingTimer = setTimeout(async () => {
        if (!this._isPollingActive) return;
        if (document.visibilityState === "visible") {
          await this.refresh();
        }
        scheduleNext();
      }, this._pollIntervalMs);
    };

    scheduleNext();
  }

  stopPolling() {
    this._isPollingActive = false;
    if (this._pollingTimer) {
      clearTimeout(this._pollingTimer);
      this._pollingTimer = null;
    }
  }

  setupListeners() {
    const table = document.getElementById("portsTable");
    if (table) {
      const headers = table.querySelectorAll("th[data-sort]");
      headers.forEach((th) => {
        const handleSort = () => {
          const col = th.getAttribute("data-sort");
          if (this.sortColumn === col) {
            this.sortAsc = !this.sortAsc;
          } else {
            this.sortColumn = col;
            this.sortAsc = true;
          }
          headers.forEach((h) => {
            if (h === th) {
              h.setAttribute("aria-sort", this.sortAsc ? "ascending" : "descending");
            } else {
              h.setAttribute("aria-sort", "none");
            }
          });
          this.render();
        };
        th.addEventListener("click", handleSort);
        th.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            handleSort();
          }
        });
      });
    }

    const filterInput = document.getElementById("portsFilterInput");
    if (filterInput) {
      filterInput.addEventListener("input", (e) => {
        this.filterText = e.target.value;
        this.render();
      });
    }

    const transientToggle = document.getElementById("portsTransientToggle");
    if (transientToggle) {
      transientToggle.addEventListener("change", (e) => {
        this.showTransient = e.target.checked;
        this.render();
      });
    }

    const dismissBtn = document.getElementById("portsWarningDismissBtn");
    if (dismissBtn) {
      dismissBtn.addEventListener("click", () => {
        const msg = document.getElementById("portsWarningMessage");
        if (msg) this._dismissedWarning = msg.textContent;
        this.clearWarning();
      });
    }

    const watchForm = document.getElementById("watchPortForm");
    if (watchForm) {
      watchForm.addEventListener("submit", (e) => {
        e.preventDefault();
        this.submitWatchPort();
      });
    }

    document.addEventListener("visibilitychange", () => {
      if (this._isPollingActive && document.visibilityState === "visible") {
        this.refresh();
      }
    });
  }

  showWarning(text, type = "warning") {
    const banner = document.getElementById("portsWarningBanner");
    const msg = document.getElementById("portsWarningMessage");
    if (!banner || !msg) return;
    if (this._dismissedWarning === text) return;

    msg.textContent = text;
    banner.removeAttribute("hidden");
    if (type === "error") {
      banner.classList.add("banner-error");
    } else {
      banner.classList.remove("banner-error");
    }
  }

  clearWarning() {
    const banner = document.getElementById("portsWarningBanner");
    if (banner) {
      banner.setAttribute("hidden", "");
    }
  }

  showToast(message, type = "info", duration = 3000) {
    const rack = document.getElementById("toastRack");
    if (!rack) return;

    const toast = document.createElement("div");
    toast.className = `toast-item toast-${type}`;

    const textSpan = document.createElement("span");
    textSpan.textContent = message;
    toast.appendChild(textSpan);

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "ports-warning-dismiss";
    closeBtn.setAttribute("aria-label", "Dismiss notification");
    closeBtn.textContent = "✕";
    closeBtn.addEventListener("click", () => {
      if (toast.parentNode === rack) rack.removeChild(toast);
    });
    toast.appendChild(closeBtn);

    rack.appendChild(toast);

    setTimeout(() => {
      if (toast.parentNode === rack) {
        toast.style.opacity = "0";
        setTimeout(() => {
          if (toast.parentNode === rack) rack.removeChild(toast);
        }, 200);
      }
    }, duration);
  }

  promptAddPort() {
    const modal = document.getElementById("watchPortModal");
    const input = document.getElementById("watchPortNumberInput");
    const errSpan = document.getElementById("watchPortError");
    const hostSelect = document.getElementById("watchPortHostSelect");

    if (!modal) return;
    if (input) input.value = "";
    if (errSpan) errSpan.textContent = "";
    if (hostSelect) hostSelect.value = "127.0.0.1";

    if (typeof modal.showModal === "function") {
      modal.showModal();
      if (input) input.focus();
    }
  }

  submitWatchPort() {
    const input = document.getElementById("watchPortNumberInput");
    const hostSelect = document.getElementById("watchPortHostSelect");
    const errSpan = document.getElementById("watchPortError");
    const modal = document.getElementById("watchPortModal");
    if (!input || !modal) return;

    const val = input.value.trim();
    if (!/^\d{1,5}$/.test(val)) {
      if (errSpan) errSpan.textContent = "Port must be digits only (1 to 65535).";
      input.focus();
      return;
    }

    const portNum = parseInt(val, 10);
    if (portNum < 1 || portNum > 65535) {
      if (errSpan) errSpan.textContent = "Port number must be between 1 and 65535.";
      input.focus();
      return;
    }

    const host = hostSelect ? hostSelect.value : "127.0.0.1";

    const exists = this.portsList.some(
      (p) => Number(p.port) === portNum && (p.host === host || (!p.host && host === "127.0.0.1"))
    );
    if (exists) {
      if (errSpan) errSpan.textContent = `Port ${portNum} on ${host} is already in the list.`;
      input.focus();
      return;
    }

    if (errSpan) errSpan.textContent = "";
    if (typeof modal.close === "function") {
      modal.close();
    }

    const newPort = {
      port: portNum,
      host: host,
      protocol: "TCP",
      address: `http://${host}:${portNum}`,
      process: "Watched",
      status: "Probing...",
      origin: "Watched",
      isCustom: true,
      exposure: "loopback",
      openable: true
    };

    this.customPorts.push(newPort);
    this.saveWatchedPorts();
    this.showToast(`Watching port ${portNum} on ${host}`, "info");
    this.refresh();
    this.probeSinglePort(newPort);
  }

  removePort(portNum, host = "127.0.0.1") {
    this.customPorts = this.customPorts.filter(
      (p) => !(Number(p.port) === Number(portNum) && (p.host === host || (!p.host && host === "127.0.0.1")))
    );
    this.saveWatchedPorts();
    this.showToast(`Stopped watching port ${portNum}`, "info");
    this.refresh();
  }

  async openPort(port, host = "127.0.0.1") {
    if (!port) return;
    const portNum = Number(port);
    const success = await NativeBridge.openPort(portNum, host);
    if (!success) {
      this.showToast(`Failed to open port ${portNum} on ${host}`, "error");
    }
  }

  async copyPort(url) {
    if (!url) return;
    let success = false;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(url);
        success = true;
      } else {
        const ta = document.createElement("textarea");
        ta.value = url;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        success = document.execCommand("copy");
        document.body.removeChild(ta);
      }
    } catch (err) {
      console.warn("[PortsManager] Clipboard copy failed:", err);
    }
    if (success) {
      this.showToast(`Copied ${url}`, "success");
    } else {
      this.showToast(`Failed to copy address`, "error");
    }
  }

  async probeSinglePort(custom) {
    try {
      const isAlive = await NativeBridge.probePort(custom.port, custom.host);
      const newStatus = isAlive ? "Listening" : "Not responding";
      if (custom.status !== newStatus) {
        custom.status = newStatus;
        const match = this.portsList.find(
          (p) => p.isCustom && Number(p.port) === Number(custom.port) && p.host === custom.host
        );
        if (match) match.status = newStatus;
        this.render();
      }
    } catch (err) {
      console.warn("[PortsManager] Port probe failed:", err);
    }
  }

  probeWatchedPorts() {
    for (const custom of this.customPorts) {
      this.probeSinglePort(custom);
    }
  }

  async refresh() {
    if (this._inflight) {
      this._again = true;
      return;
    }
    this._inflight = true;

    try {
      const res = await NativeBridge.listPorts();
      this.handleRefreshResponse(res);
    } catch (err) {
      console.error("[PortsManager] Failed to refresh ports:", err);
      this.showWarning("Failed to query listening ports from supervisor.", "error");
    } finally {
      this._inflight = false;
      if (this._again) {
        this._again = false;
        this.refresh();
      }
    }
  }

  handleRefreshResponse(res) {
    if (!res || res.status !== "ok") {
      const msg = res && res.message ? res.message : "Unable to retrieve active ports.";
      this.showWarning(msg, "error");
      this.portsList = [];
      this.render();
      return;
    }

    if (res.warnings && res.warnings.length > 0) {
      const warningTexts = res.warnings.map((w) => {
        if (w === "psutil_missing") {
          return "Port scanning unavailable: psutil is not installed.";
        }
        if (w === "socket_table_denied") {
          return "Limited view: the OS denied access to the socket table (macOS needs elevated privileges).";
        }
        return `Warning: ${w}`;
      });
      this.showWarning(warningTexts.join(" "), "warning");
    } else {
      this.clearWarning();
    }

    const detected = Array.isArray(res.ports) ? res.ports : [];

    const combined = [...detected];
    for (const custom of this.customPorts) {
      const alreadyDetected = detected.some(
        (p) => Number(p.port) === Number(custom.port) && (p.host === custom.host || (!p.host && custom.host === "127.0.0.1"))
      );
      if (!alreadyDetected) {
        combined.push(custom);
      }
    }

    this.portsList = combined;
    this.render();
    this.probeWatchedPorts();
  }

  getFilteredAndSortedPorts() {
    let list = [...this.portsList];

    // 1. Ephemeral range toggle: hide >= 32768 by default
    if (!this.showTransient) {
      list = list.filter((p) => Number(p.port) < 32768);
    }

    // 2. Text filter (port, process, PID)
    if (this.filterText) {
      const query = this.filterText.toLowerCase().trim();
      list = list.filter((p) => {
        const portStr = String(p.port || "");
        const procStr = String(p.process || "").toLowerCase();
        const pidStr = p.pid != null ? String(p.pid) : "";
        return portStr.includes(query) || procStr.includes(query) || pidStr.includes(query);
      });
    }

    // 3. Sort
    const col = this.sortColumn;
    const asc = this.sortAsc ? 1 : -1;
    list.sort((a, b) => {
      if (col === "port") {
        const valA = Number(a.port) || 0;
        const valB = Number(b.port) || 0;
        if (valA !== valB) return (valA - valB) * asc;
        return String(a.host || "").localeCompare(String(b.host || "")) * asc;
      } else if (col === "pid") {
        const valA = a.pid != null ? Number(a.pid) : -1;
        const valB = b.pid != null ? Number(b.pid) : -1;
        return (valA - valB) * asc;
      } else {
        const valA = String(a[col] || "").toLowerCase();
        const valB = String(b[col] || "").toLowerCase();
        return valA.localeCompare(valB) * asc;
      }
    });

    return list;
  }

  render() {
    const tableBody = document.getElementById("portsTableBody");
    const countBadge = document.getElementById("portsCountBadge");
    const announcer = document.getElementById("screenReaderAnnouncer");

    if (countBadge) {
      countBadge.textContent = `${this.portsList.length} active`;
    }

    if (this._lastCount !== this.portsList.length) {
      this._lastCount = this.portsList.length;
      if (announcer) {
        announcer.textContent = `${this.portsList.length} active listening ports`;
      }
    }

    const filtered = this.getFilteredAndSortedPorts();
    const signature =
      JSON.stringify(filtered.map((p) => [p.port, p.host, p.process, p.status, p.pid, p.exposure, p.openable])) +
      `:${this.filterText}:${this.sortColumn}:${this.sortAsc}:${this.showTransient}`;

    if (signature === this._lastSignature) {
      return;
    }
    this._lastSignature = signature;

    if (!tableBody) return;

    let restoreFocus = null;
    if (tableBody.contains(document.activeElement)) {
      const activeEl = document.activeElement;
      const action = activeEl.getAttribute("data-action");
      const port = activeEl.getAttribute("data-port");
      const host = activeEl.getAttribute("data-host");
      if (action && port) {
        restoreFocus = { action, port, host };
      }
    }

    while (tableBody.firstChild) {
      tableBody.removeChild(tableBody.firstChild);
    }

    if (filtered.length === 0) {
      const emptyRow = document.createElement("tr");
      const emptyCell = document.createElement("td");
      emptyCell.colSpan = 8;
      emptyCell.className = "ports-empty";
      emptyCell.textContent = this.filterText
        ? "No ports match the filter."
        : 'No active listening ports detected. Click "+ Watch Port" to add one.';
      emptyRow.appendChild(emptyCell);
      tableBody.appendChild(emptyRow);
      return;
    }

    for (const item of filtered) {
      const row = document.createElement("tr");

      // 1. Port + Network-exposed badge
      const tdPort = document.createElement("td");
      const portBadge = document.createElement("span");
      portBadge.className = "port-num-badge";
      portBadge.textContent = String(item.port);
      tdPort.appendChild(portBadge);

      if (item.exposure === "all-interfaces") {
        const exposedBadge = document.createElement("span");
        exposedBadge.className = "port-badge-exposed";
        exposedBadge.title = "Listening on all network interfaces (0.0.0.0 or [::])";
        exposedBadge.textContent = "Network-exposed";
        tdPort.appendChild(exposedBadge);
      }

      // 2. Protocol
      const tdProto = document.createElement("td");
      const protoBadge = document.createElement("span");
      protoBadge.className = "port-protocol-badge";
      protoBadge.textContent = item.protocol || "TCP";
      tdProto.appendChild(protoBadge);

      // 3. Local Address
      const tdAddr = document.createElement("td");
      tdAddr.className = "port-addr-cell";
      tdAddr.textContent = item.address;

      // 4. Process / Service
      const tdProc = document.createElement("td");
      tdProc.textContent = item.process || "--";

      // 5. PID
      const tdPid = document.createElement("td");
      tdPid.textContent = item.pid != null ? String(item.pid) : "--";

      // 6. Origin
      const tdOrigin = document.createElement("td");
      tdOrigin.textContent = item.origin || "Local";

      // 7. Status
      const tdStatus = document.createElement("td");
      const statusPill = document.createElement("span");
      statusPill.className = "port-status-pill";
      const statusText = item.status || "Listening";
      statusPill.textContent = statusText;
      if (statusText === "Not responding") {
        statusPill.classList.add("status-inactive");
      } else if (statusText === "Probing...") {
        statusPill.classList.add("status-probing");
      }
      tdStatus.appendChild(statusPill);

      // 8. Actions
      const tdActions = document.createElement("td");

      // Open button
      const openBtn = document.createElement("button");
      openBtn.className = "port-action-btn";
      openBtn.setAttribute("data-action", "open-port");
      openBtn.setAttribute("data-port", String(item.port));
      openBtn.setAttribute("data-host", item.host || "127.0.0.1");
      openBtn.setAttribute("aria-label", `Open port ${item.port} on ${item.host || "127.0.0.1"}`);
      openBtn.textContent = "🌐 Open";

      if (item.openable === false) {
        openBtn.disabled = true;
        openBtn.classList.add("disabled");
        openBtn.title =
          item.origin === "System" || item.process === "DeskAI Supervisor"
            ? "Supervisor port requires session authentication; open via DeskAI UI"
            : "Not an openable HTTP port";
      } else {
        openBtn.title = "Open in Default Browser";
      }
      tdActions.appendChild(openBtn);

      // Copy button
      const copyBtn = document.createElement("button");
      copyBtn.className = "port-action-btn";
      copyBtn.setAttribute("data-action", "copy-port");
      copyBtn.setAttribute("data-url", item.address);
      copyBtn.setAttribute("aria-label", `Copy address for port ${item.port}`);
      copyBtn.title = "Copy Address to Clipboard";
      copyBtn.textContent = "📋 Copy";
      tdActions.appendChild(copyBtn);

      // Remove button for watched custom ports
      if (item.isCustom) {
        const delBtn = document.createElement("button");
        delBtn.className = "port-action-btn";
        delBtn.setAttribute("data-action", "remove-port");
        delBtn.setAttribute("data-port", String(item.port));
        delBtn.setAttribute("data-host", item.host || "127.0.0.1");
        delBtn.setAttribute("aria-label", `Stop watching port ${item.port} on ${item.host || "127.0.0.1"}`);
        delBtn.title = "Stop Watching Port";
        delBtn.textContent = "✕";
        tdActions.appendChild(delBtn);
      }

      row.appendChild(tdPort);
      row.appendChild(tdProto);
      row.appendChild(tdAddr);
      row.appendChild(tdProc);
      row.appendChild(tdPid);
      row.appendChild(tdOrigin);
      row.appendChild(tdStatus);
      row.appendChild(tdActions);

      tableBody.appendChild(row);
    }

    if (restoreFocus) {
      const selector = `button[data-action="${restoreFocus.action}"][data-port="${restoreFocus.port}"]`;
      const btn = tableBody.querySelector(selector);
      if (btn) btn.focus();
    }
  }
}

export function initPorts() {
  const manager = new PortsManager();
  manager.refresh();
  return manager;
}
