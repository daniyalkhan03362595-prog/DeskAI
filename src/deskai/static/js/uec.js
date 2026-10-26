import { store } from "./state.js";

export class UECStateMachine {
  constructor() {
    this.transitions = {
      IDLE: ["PLANNING"],
      PLANNING: ["EXECUTING", "CANCELLED", "IDLE"],
      EXECUTING: ["REVIEW_DIFF", "FAILED", "CANCELLED"],
      REVIEW_DIFF: ["SUCCESS", "ROLLBACK", "EXECUTING"],
      FAILED: ["ROLLBACK", "CANCELLED", "IDLE"],
      ROLLBACK: ["IDLE", "FAILED"],
      CANCELLED: ["IDLE"],
      SUCCESS: ["IDLE"]
    };
    this._loadTransitions();
  }

  async _loadTransitions() {
    try {
      if (typeof fetch === "function") {
        const res = await fetch("/transitions.json");
        if (res.ok) {
          this.transitions = await res.json();
        }
      }
    } catch {
      // Retain in-memory fallback
    }
  }

  _showError(message) {
    if (typeof document === "undefined") return;
    const banner = document.getElementById("connectionBanner");
    if (banner) {
      banner.textContent = message;
      banner.className = "connection-banner warning";
      banner.style.display = "block";
      setTimeout(() => {
        if (banner.textContent === message) banner.style.display = "none";
      }, 4000);
    } else {
      console.error(message);
    }
  }

  _ensureUecMounted() {
    if (typeof document === "undefined") return null;
    const container = document.getElementById("uecContainer");
    if (!container) return null;
    let card = container.querySelector(".uec-card");
    if (!card) {
      const tpl = document.getElementById("tplUecCard");
      if (tpl) {
        container.appendChild(tpl.content.cloneNode(true));
        card = container.querySelector(".uec-card");
      }
    }
    return card;
  }

  transition(nextState, payload = {}) {
    const current = store && store.state && store.state.execution ? store.state.execution.state : "IDLE";
    const allowed = this.transitions[current];
    if (!allowed || !allowed.includes(nextState)) {
      const errMsg = `Invalid UEC transition from ${current} to ${nextState}`;
      console.error(errMsg);
      this._showError(errMsg);
      return false;
    }

    if (store && store.state && store.state.execution) {
      store.state.execution.state = nextState;
    }
    this.renderButtons(nextState);

    // Broadcast client-initiated transitions to backend (e.g. PLANNING, CANCELLED)
    // Server ACKs for SUCCESS / ROLLBACK are the authority and never re-broadcast
    if (window.wsClient && nextState !== "SUCCESS" && nextState !== "ROLLBACK") {
      window.wsClient.send("uec.transition", { from: current, to: nextState, payload }, { replayable: false });
    }

    if (nextState === "SUCCESS") {
      setTimeout(() => this.transition("IDLE"), 3000);
    }
    return true;
  }

  approvePlan() {
    const current = store && store.state && store.state.execution ? store.state.execution.state : "IDLE";
    if (current === "PLANNING" || current === "REVIEW_DIFF") {
      if (!window.wsClient || !store.state.connection.isSocketConnected) {
        this._showError("Cannot accept changes while offline. Please wait for reconnection.");
        return false;
      }
      const requestId = crypto.randomUUID();
      const sent = window.wsClient.send("uec.approve", { request_id: requestId }, { replayable: false });
      if (!sent) {
        this._showError("Cannot accept changes while offline. Please wait for reconnection.");
        return false;
      }
      return true;
    }
    return false;
  }

  rejectPlan() {
    const current = store && store.state && store.state.execution ? store.state.execution.state : "IDLE";
    if (current === "REVIEW_DIFF" || current === "PLANNING" || current === "EXECUTING") {
      if (!window.wsClient || !store.state.connection.isSocketConnected) {
        this._showError("Cannot reject changes while offline. Please wait for reconnection.");
        return false;
      }
      const requestId = crypto.randomUUID();
      const sent = window.wsClient.send("uec.reject", { request_id: requestId }, { replayable: false });
      if (!sent) {
        this._showError("Cannot reject changes while offline. Please wait for reconnection.");
        return false;
      }
      return true;
    }
    return false;
  }

  rollback() { return this.transition("ROLLBACK"); }
  cancel() { return this.transition("CANCELLED"); }
  reset() { return this.transition("IDLE"); }

  renderButtons(state) {
    this._ensureUecMounted();
    const actionsContainer = document.querySelector("#uecContainer .uec-actions");
    if (!actionsContainer) return;

    let buttonsHtml = "";
    if (state === "PLANNING") {
      buttonsHtml = `
        <button class="uec-btn btn-cancel" data-action="uec-cancel">Cancel</button>
        <button class="uec-btn btn-approve" data-action="uec-approve">Approve & Execute</button>
      `;
    } else if (state === "EXECUTING") {
      buttonsHtml = `<button class="uec-btn btn-cancel" data-action="uec-cancel">Cancel Execution</button>`;
    } else if (state === "REVIEW_DIFF") {
      buttonsHtml = `
        <button class="uec-btn btn-rollback" data-action="uec-rollback">Rollback Changes</button>
        <button class="uec-btn btn-reject" data-action="uec-reject">Reject Diff</button>
        <button class="uec-btn btn-approve" data-action="uec-approve">Accept Changes</button>
      `;
    } else if (state === "CANCELLED") {
      buttonsHtml = `<button class="uec-btn btn-reset" data-action="uec-reset">Reset</button>`;
    } else if (state === "FAILED") {
      buttonsHtml = `
        <button class="uec-btn btn-rollback" data-action="uec-rollback">Rollback to Safe State</button>
        <button class="uec-btn btn-cancel" data-action="uec-cancel">Dismiss</button>
      `;
    }

    actionsContainer.innerHTML = buttonsHtml;
  }
}
