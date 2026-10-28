/**
 * Ports Scanner & Storage Module.
 * Manages watched ports persistence, active probing, and polling intervals.
 */
import { NativeBridge } from "../bridge.js";

export class PortScanner {
  constructor(callbacks) {
    this.callbacks = callbacks;
    this.customPorts = this.loadWatchedPorts();
    this.portsList = [];
    this._pollingTimer = null;
    this._isPollingActive = false;
    this._pollIntervalMs = 3000;
    this._inflight = false;
    this._again = false;
    this._hasError = false;
    this._activeStorageKey = null;

    if (window.store && typeof window.store.subscribe === "function") {
      window.store.subscribe("workspace.rootPath", (newPath) => {
        if (newPath) {
          this.customPorts = this.loadWatchedPorts();
          this.refresh();
        }
      });
    }

    document.addEventListener("visibilitychange", () => {
      if (this._isPollingActive && document.visibilityState === "visible") {
        this.refresh();
      }
    });
  }

  getStorageKey() {
    if (this.callbacks && typeof this.callbacks.getStorageKey === "function") {
      const customKey = this.callbacks.getStorageKey();
      if (customKey) return customKey;
    }
    const root =
      (window.store && window.store.state && window.store.state.workspace && window.store.state.workspace.rootPath) ||
      "default";
    return `deskai_watched_ports_${root}`;
  }

  loadWatchedPorts() {
    const key = this.getStorageKey();
    this._activeStorageKey = key;
    try {
      const raw = localStorage.getItem(key);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          return parsed
            .map((p) => ({
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
            }))
            .filter((p) => {
              const validHost = p.host === "127.0.0.1" || p.host === "[::1]";
              const validPort = Number.isInteger(p.port) && p.port >= 1 && p.port <= 65535;
              return validHost && validPort;
            });
        }
      }
    } catch (e) {
      console.warn("[PortScanner] Failed to read watched ports from localStorage", e);
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
      const key = this._activeStorageKey || this.getStorageKey();
      localStorage.setItem(key, JSON.stringify(data));
    } catch (e) {
      console.warn("[PortScanner] Failed to persist watched ports to localStorage", e);
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
        if (this.callbacks.onRender) this.callbacks.onRender();
      }
    } catch (err) {
      console.warn("[PortScanner] Port probe failed:", err);
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
      console.error("[PortScanner] Failed to refresh ports:", err);
      if (this.callbacks.onWarning) {
        this.callbacks.onWarning("Failed to query listening ports from supervisor.", "error");
      }
      this._hasError = true;
      this.portsList = this.portsList.map((p) => ({
        ...p,
        status: p.status && p.status.endsWith(" (Stale)") ? p.status : (p.status || "Listening") + " (Stale)"
      }));
      if (this.callbacks.onRender) this.callbacks.onRender();
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
      if (this.callbacks.onWarning) this.callbacks.onWarning(msg, "error");
      this._hasError = true;
      this.portsList = this.portsList.map((p) => ({
        ...p,
        status: p.status && p.status.endsWith(" (Stale)") ? p.status : (p.status || "Listening") + " (Stale)"
      }));
      if (this.callbacks.onRender) this.callbacks.onRender();
      return;
    }
    this._hasError = false;

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
      if (this.callbacks.onWarning) this.callbacks.onWarning(warningTexts.join(" "), "warning");
    } else {
      if (this.callbacks.onClearWarning) this.callbacks.onClearWarning();
    }

    const detected = Array.isArray(res.ports) ? res.ports : [];
    const combined = [...detected];
    for (const custom of this.customPorts) {
      const detectedIdx = detected.findIndex(
        (p) => Number(p.port) === Number(custom.port) && (p.host === custom.host || (!p.host && custom.host === "127.0.0.1"))
      );
      if (detectedIdx >= 0) {
        combined[detectedIdx] = { ...combined[detectedIdx], isCustom: true };
      } else {
        combined.push(custom);
      }
    }

    this.portsList = combined;
    if (this.callbacks.onRender) this.callbacks.onRender();
    this.probeWatchedPorts();
  }
}
