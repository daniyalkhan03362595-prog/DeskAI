/**
 * Ports Table View Renderer Module.
 * Renders data rows, status badges, accessibility announcements, and click feedback icons.
 */

export class PortTableRenderer {
  constructor(tableBody, countBadge, announcer) {
    this.tableBody = tableBody;
    this.countBadge = countBadge;
    this.announcer = announcer;
    this._lastSignature = null;
    this._lastCount = null;
    this._lastHiddenCount = null;
  }

  setButtonSuccessState(btnElement, duration = 1200) {
    if (!btnElement) return;

    if (btnElement._feedbackTimeout) {
      clearTimeout(btnElement._feedbackTimeout);
    }

    const prevContent = btnElement._originalContent || btnElement.textContent || "";
    const prevAriaLabel = btnElement._originalAriaLabel || btnElement.getAttribute("aria-label") || "";
    const prevTitle = btnElement._originalTitle || btnElement.title || "";

    btnElement._originalContent = prevContent;
    btnElement._originalAriaLabel = prevAriaLabel;
    btnElement._originalTitle = prevTitle;

    while (btnElement.firstChild) {
      btnElement.removeChild(btnElement.firstChild);
    }

    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("width", "12");
    svg.setAttribute("height", "12");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2.2");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("aria-hidden", "true");
    svg.classList.add("port-check-icon");

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", "M3.5 8.5L6.5 11.5L12.5 4.5");
    svg.appendChild(path);

    btnElement.appendChild(svg);
    btnElement.classList.add("is-copied");

    const isCopy = btnElement.getAttribute("data-action") === "copy-port";
    btnElement.title = isCopy ? "Copied to Clipboard" : "Opened in Browser";
    btnElement.setAttribute("aria-label", isCopy ? "Copied to clipboard" : "Opened in browser");

    btnElement._feedbackTimeout = setTimeout(() => {
      btnElement.classList.remove("is-copied");
      while (btnElement.firstChild) {
        btnElement.removeChild(btnElement.firstChild);
      }
      btnElement.textContent = btnElement._originalContent;
      btnElement.title = btnElement._originalTitle;
      if (btnElement._originalAriaLabel) {
        btnElement.setAttribute("aria-label", btnElement._originalAriaLabel);
      }
      btnElement._feedbackTimeout = null;
    }, duration);
  }

  render(filtered, totalCount, filterText, hasError, sortColumn, sortAsc, showTransient) {
    const shownCount = filtered.length;
    const hiddenCount = totalCount - shownCount;

    let badgeText;
    if (hiddenCount > 0) {
      badgeText = `${shownCount} shown (${hiddenCount} hidden)`;
    } else {
      badgeText = `${shownCount} active`;
    }

    if (this.countBadge) {
      this.countBadge.textContent = badgeText;
    }

    if (this._lastCount !== shownCount || this._lastHiddenCount !== hiddenCount) {
      this._lastCount = shownCount;
      this._lastHiddenCount = hiddenCount;
      if (this.announcer) {
        this.announcer.textContent = badgeText + " listening ports";
      }
    }

    const signature =
      JSON.stringify(filtered.map((p) => [p.port, p.host, p.process, p.status, p.pid, p.exposure, p.openable])) +
      `:${filterText}:${sortColumn}:${sortAsc}:${showTransient}`;

    if (signature === this._lastSignature) {
      return;
    }
    this._lastSignature = signature;

    if (!this.tableBody) return;

    let restoreFocus = null;
    if (this.tableBody.contains(document.activeElement)) {
      const activeEl = document.activeElement;
      const action = activeEl.getAttribute("data-action");
      const port = activeEl.getAttribute("data-port");
      const host = activeEl.getAttribute("data-host");
      if (action && port) {
        restoreFocus = { action, port, host };
      }
    }

    while (this.tableBody.firstChild) {
      this.tableBody.removeChild(this.tableBody.firstChild);
    }

    if (filtered.length === 0) {
      const emptyRow = document.createElement("tr");
      const emptyCell = document.createElement("td");
      emptyCell.colSpan = 8;
      emptyCell.className = "ports-empty";
      if (filterText) {
        emptyCell.textContent = "No ports match the filter.";
      } else if (hasError) {
        emptyCell.textContent = "Unable to retrieve active ports. See notice above.";
      } else {
        emptyCell.textContent = 'No active listening ports detected. Click "+ Watch Port" to add one.';
      }
      emptyRow.appendChild(emptyCell);
      this.tableBody.appendChild(emptyRow);
      return;
    }

    for (const item of filtered) {
      const row = document.createElement("tr");

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

      const tdProto = document.createElement("td");
      const protoBadge = document.createElement("span");
      protoBadge.className = "port-protocol-badge";
      protoBadge.textContent = item.protocol || "TCP";
      tdProto.appendChild(protoBadge);

      const tdAddr = document.createElement("td");
      tdAddr.className = "port-addr-cell";
      tdAddr.textContent = item.address;

      const tdProc = document.createElement("td");
      tdProc.textContent = item.process || "--";

      const tdPid = document.createElement("td");
      tdPid.textContent = item.pid != null ? String(item.pid) : "--";

      const tdOrigin = document.createElement("td");
      tdOrigin.textContent = item.origin || "Local";

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

      const tdActions = document.createElement("td");

      const openBtn = document.createElement("button");
      openBtn.className = "port-action-btn";
      openBtn.setAttribute("data-action", "open-port");
      openBtn.setAttribute("data-port", String(item.port));
      openBtn.setAttribute("data-host", item.host || "127.0.0.1");
      openBtn.setAttribute("aria-label", `Open port ${item.port} on ${item.host || "127.0.0.1"}`);
      openBtn.textContent = "Open";

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

      const copyBtn = document.createElement("button");
      copyBtn.className = "port-action-btn";
      copyBtn.setAttribute("data-action", "copy-port");
      copyBtn.setAttribute("data-url", item.address);
      copyBtn.setAttribute("data-port", String(item.port));
      copyBtn.setAttribute("data-host", item.host || "127.0.0.1");
      copyBtn.setAttribute("aria-label", `Copy address for port ${item.port}`);
      copyBtn.title = "Copy Address to Clipboard";
      copyBtn.textContent = "Copy";
      tdActions.appendChild(copyBtn);

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

      this.tableBody.appendChild(row);
    }

    if (restoreFocus) {
      let selector = `button[data-action="${restoreFocus.action}"][data-port="${restoreFocus.port}"]`;
      if (restoreFocus.host) {
        selector += `[data-host="${restoreFocus.host}"]`;
      }
      const btn = this.tableBody.querySelector(selector);
      if (btn) btn.focus();
    }
  }
}
