/**
 * Ports Manager Module.
 * Discovers and manages active listening ports and port forwardings.
 */
import { NativeBridge } from "./bridge.js";
import { PortScanner } from "./ports/scanner.js";
import { PortTableRenderer } from "./ports/table.js";

export class PortsManager {
  constructor() {
    this.filterText = "";
    this.showTransient = false;
    this.sortColumn = "port";
    this.sortAsc = true;
    this._dismissedWarning = null;

    const tableBody = document.getElementById("portsTableBody");
    const countBadge = document.getElementById("portsCountBadge");
    const announcer = document.getElementById("screenReaderAnnouncer");
    this.renderer = new PortTableRenderer(tableBody, countBadge, announcer);

    this.scanner = new PortScanner({
      onRender: () => this.render(),
      onWarning: (msg, type) => this.showWarning(msg, type),
      onClearWarning: () => this.clearWarning(),
      getStorageKey: () => (typeof this.getStorageKey === "function" ? this.getStorageKey() : null),
    });

    this.setupListeners();
  }

  getStorageKey() {
    const root =
      (window.store && window.store.state && window.store.state.workspace && window.store.state.workspace.rootPath) ||
      "default";
    return `deskai_watched_ports_${root}`;
  }

  loadWatchedPorts() {
    return this.scanner.loadWatchedPorts();
  }

  saveWatchedPorts() {
    return this.scanner.saveWatchedPorts();
  }

  handleRefreshResponse(res) {
    return this.scanner.handleRefreshResponse(res);
  }

  get customPorts() {
    return this.scanner.customPorts;
  }

  set customPorts(val) {
    this.scanner.customPorts = val;
  }

  get portsList() {
    return this.scanner.portsList;
  }

  set portsList(val) {
    this.scanner.portsList = val;
  }

  get _hasError() {
    return this.scanner._hasError;
  }

  set _hasError(val) {
    this.scanner._hasError = val;
  }

  get _lastSignature() {
    return this.renderer._lastSignature;
  }

  set _lastSignature(val) {
    this.renderer._lastSignature = val;
  }

  startPolling(ms = 3000) {
    this.scanner.startPolling(ms);
  }

  stopPolling() {
    this.scanner.stopPolling();
  }

  loadWatchedPorts() {
    return this.scanner.loadWatchedPorts();
  }

  saveWatchedPorts() {
    this.scanner.saveWatchedPorts();
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
    this._dismissedWarning = null;
    this.scanner._hasError = false;
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
    this.scanner.probeSinglePort(newPort);
  }

  removePort(portNum, host = "127.0.0.1") {
    this.customPorts = this.customPorts.filter(
      (p) => !(Number(p.port) === Number(portNum) && (p.host === host || (!p.host && host === "127.0.0.1")))
    );
    this.saveWatchedPorts();
    this.showToast(`Stopped watching port ${portNum}`, "info");
    this.refresh();
  }

  async openPort(port, host = "127.0.0.1", btnElement = null) {
    if (!port) return;
    const portNum = Number(port);
    const success = await NativeBridge.openPort(portNum, host);
    if (success) {
      const announcer = document.getElementById("screenReaderAnnouncer");
      if (announcer) announcer.textContent = `Opened http://${host}:${portNum}`;
      if (btnElement && btnElement instanceof HTMLElement) {
        this.renderer.setButtonSuccessState(btnElement, 1200);
      }
    } else {
      this.showToast(`Failed to open port ${portNum} on ${host}`, "error");
    }
  }

  async copyPort(url, btnElement = null) {
    if (!url) return;
    let success = false;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(url);
        success = true;
      }
    } catch (err) {
      // Ignored
    }

    if (!success) {
      try {
        const ta = document.createElement("textarea");
        ta.value = url;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        success = document.execCommand("copy");
        document.body.removeChild(ta);
      } catch (err) {
        console.warn("[PortsManager] Clipboard copy fallback failed:", err);
      }
    }
    if (success) {
      const announcer = document.getElementById("screenReaderAnnouncer");
      if (announcer) announcer.textContent = `Copied ${url}`;
      if (btnElement && btnElement instanceof HTMLElement) {
        this.renderer.setButtonSuccessState(btnElement, 1200);
      } else {
        this.showToast(`Copied ${url}`, "success");
      }
    } else {
      this.showToast("Failed to copy address", "error");
    }
  }

  setButtonCopiedState(btnElement, duration = 1200) {
    return this.renderer.setButtonSuccessState(btnElement, duration);
  }

  setButtonSuccessState(btnElement, duration = 1200) {
    return this.renderer.setButtonSuccessState(btnElement, duration);
  }

  probeSinglePort(custom) {
    return this.scanner.probeSinglePort(custom);
  }

  probeWatchedPorts() {
    this.scanner.probeWatchedPorts();
  }

  async refresh() {
    await this.scanner.refresh();
  }

  getFilteredAndSortedPorts() {
    let list = [...this.portsList];

    if (!this.showTransient) {
      list = list.filter((p) => Number(p.port) < 32768);
    }

    if (this.filterText) {
      const query = this.filterText.toLowerCase().trim();
      list = list.filter((p) => {
        const portStr = String(p.port || "");
        const procStr = String(p.process || "").toLowerCase();
        const pidStr = p.pid != null ? String(p.pid) : "";
        return portStr.includes(query) || procStr.includes(query) || pidStr.includes(query);
      });
    }

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
    const filtered = this.getFilteredAndSortedPorts();
    this.renderer.render(
      filtered,
      this.portsList.length,
      this.filterText,
      this._hasError,
      this.sortColumn,
      this.sortAsc,
      this.showTransient
    );
  }
}

export function initPorts() {
  const manager = new PortsManager();
  manager.refresh();
  return manager;
}
