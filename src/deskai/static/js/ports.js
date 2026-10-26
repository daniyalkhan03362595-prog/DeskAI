/**
 * Ports Manager Module
 * Discovers and manages active listening ports and port forwardings.
 */
import { NativeBridge } from "./bridge.js";

export class PortsManager {
  constructor() {
    this.customPorts = [];
    this.portsList = [];
    this.tableBody = document.getElementById("portsTableBody");
    this.countBadge = document.getElementById("portsCountBadge");
  }

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

  promptAddPort() {
    const input = prompt("Enter port number to monitor (e.g. 3000, 5173, 8080):");
    if (!input) return;

    const portNum = parseInt(input.trim(), 10);
    if (isNaN(portNum) || portNum < 1 || portNum > 65535) {
      alert("Invalid port number. Must be between 1 and 65535.");
      return;
    }

    const exists = this.portsList.some(p => Number(p.port) === portNum);
    if (exists) {
      alert(`Port ${portNum} is already in the list.`);
      return;
    }

    this.customPorts.push({
      port: portNum,
      protocol: "HTTP",
      address: `http://localhost:${portNum}`,
      process: "User Forwarded",
      status: "Monitored",
      origin: "Forwarded",
      isCustom: true
    });

    this.refresh();
  }

  removePort(portNum) {
    this.customPorts = this.customPorts.filter(p => Number(p.port) !== Number(portNum));
    this.refresh();
  }

  async openPort(url) {
    if (!url) return;
    const dispatched = await NativeBridge.openExternalUrl(url);
    if (!dispatched) {
      window.open(url, "_blank", "noopener,noreferrer");
    }
  }

  async copyPort(url) {
    if (!url) return;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(url);
      } else {
        const ta = document.createElement("textarea");
        ta.value = url;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
    } catch (err) {
      console.warn("[PortsManager] Clipboard copy failed:", err);
    }
  }

  render() {
    if (!this.tableBody) {
      this.tableBody = document.getElementById("portsTableBody");
    }
    if (!this.countBadge) {
      this.countBadge = document.getElementById("portsCountBadge");
    }

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
      emptyCell.textContent = "No active listening ports detected. Click \"+ Forward Port\" to add one.";
      emptyRow.appendChild(emptyCell);
      this.tableBody.appendChild(emptyRow);
      return;
    }

    for (const item of this.portsList) {
      const row = document.createElement("tr");

      // 1. Port
      const tdPort = document.createElement("td");
      const portBadge = document.createElement("span");
      portBadge.className = "port-num-badge";
      portBadge.textContent = String(item.port);
      tdPort.appendChild(portBadge);

      // 2. Protocol
      const tdProto = document.createElement("td");
      const protoBadge = document.createElement("span");
      protoBadge.className = "port-protocol-badge";
      protoBadge.textContent = item.protocol || "HTTP";
      tdProto.appendChild(protoBadge);

      // 3. Local Address
      const tdAddr = document.createElement("td");
      tdAddr.className = "port-addr-cell";
      tdAddr.textContent = item.address;

      // 4. Process / Service
      const tdProc = document.createElement("td");
      tdProc.textContent = item.process || "--";

      // 5. Origin
      const tdOrigin = document.createElement("td");
      tdOrigin.textContent = item.origin || "Local";

      // 6. Status
      const tdStatus = document.createElement("td");
      const statusPill = document.createElement("span");
      statusPill.className = "port-status-pill";
      statusPill.textContent = item.status || "Listening";
      tdStatus.appendChild(statusPill);

      // 7. Actions
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
}

export function initPorts() {
  const manager = new PortsManager();
  manager.refresh();
  return manager;
}
