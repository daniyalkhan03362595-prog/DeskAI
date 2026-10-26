import { store } from "./state.js";

export class UECStateMachine {
  constructor() {
    this.transitions = {
      IDLE: ["PLANNING"],
      PLANNING: ["EXECUTING", "CANCELLED", "IDLE"],
      EXECUTING: ["REVIEW_DIFF", "FAILED", "CANCELLED"],
      REVIEW_DIFF: ["SUCCESS", "ROLLBACK", "EXECUTING"],
      FAILED: ["ROLLBACK", "CANCELLED", "IDLE"],
      ROLLBACK: ["IDLE"],
      CANCELLED: ["IDLE"],
      SUCCESS: ["IDLE"]
    };
  }

  transition(nextState, payload = {}) {
    const current = store.state.execution.state;
    const allowed = this.transitions[current];
    if (!allowed || !allowed.includes(nextState)) {
      console.error(`Invalid UEC transition from ${current} to ${nextState}`);
      return false;
    }

    // Network guard: If transitioning via user approval, verify socket is connected
    if (nextState === "SUCCESS" && current === "REVIEW_DIFF") {
      const sent = window.wsClient.send("uec.approve", payload, { replayable: false });
      if (!sent) {
        alert("Cannot accept changes while offline. Please wait for reconnection.");
        return false;
      }
    }

    store.state.execution.state = nextState;
    this.renderButtons(nextState);
    
    // Broadcast transition to backend
    if (window.wsClient && nextState !== "SUCCESS") {
      window.wsClient.send("uec.transition", { from: current, to: nextState, payload }, { replayable: false });
    }

    if (nextState === "SUCCESS") {
      setTimeout(() => this.transition("IDLE"), 3000);
    }
    return true;
  }

  approvePlan() { 
    const current = store.state.execution.state;
    if (current === "PLANNING") return this.transition("EXECUTING");
    if (current === "REVIEW_DIFF") return this.transition("SUCCESS");
    return false;
  }

  rejectPlan() { return this.transition("ROLLBACK"); }
  rollback() { return this.transition("ROLLBACK"); }
  cancel() { return this.transition("CANCELLED"); }
  reset() { return this.transition("IDLE"); }

  renderButtons(state) {
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
