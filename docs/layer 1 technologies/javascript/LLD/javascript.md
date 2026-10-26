# Layer 1 Technology LLD: JavaScript Client State, Streaming & DOM Architecture

Yeh document **DeskAI** ke **Layer 1 (Presentation & Client Logic)** mein use hone wali **Pure Vanilla JavaScript (ES2022 Modules)** ki mukammal **Low-Level Design (LLD)** specifications, recursive deep proxy store with WeakMap cache, trailing-edge throttled markdown streamer, message router, complete UEC finite state machine, full action router, aur vendor library integration ko **Roman Urdu** mein tafseel se bayan karta hai.

---

## 1. Executive Summary & Design Constraints

DeskAI ka frontend bina kisi runtime framework ke **Native ES Modules** par mushtamil hai.

### Low-Level Technical Constraints:
1. **Zero App Bundling & Vendor Singletons:** App code bina bundling ke direct browser ES modules mein run hota hai. External libraries (DOMPurify, Marked, CodeMirror 6) vendor directory (`vendor/`) se load hoti hain.
2. **Deep Observable Reactivity:** Recursive `Proxy` tree with WeakMap caching jo reference equality (`state.execution === state.execution`), ancestor bubbling, aur array mutations ko accurately track kare.
3. **Trailing-Edge Throttled Streaming (10 Hz):** 100ms throttle buffer with timer fallback taake aakhri tokens stall na hon aur CPU overhead sub-16ms frame budget mein rahe.
4. **Deterministic UEC State Machine:** Idempotent transitions, network-validated state changes (offline status par fake success block), aur server-notified action triggers.
5. **Universal Link & Drag Lock:** Left-click, middle-click (`auxclick`), aur drag-and-drop navigation attempts ko `preventDefault()` se block kiya jata hai.

---

## 2. Directory & Client Module Architecture

```text
src/deskai/static/
├── index.html                 # Loads vendor scripts & app.js module
├── vendor/
│   ├── codemirror.bundle.js   # CM6 core & extensions (CodeMirror 6.0.1)
│   ├── marked.min.js          # Fast markdown parser (Marked 12.0.0)
│   └── purify.min.js          # DOMPurify sanitizer (DOMPurify 3.1.7)
├── js/
│   ├── app.js                 # Entry point, bootstrapping, global assignments & server event wiring
│   ├── state.js               # WeakMap-cached Deep Reactive StudioStore
│   ├── bridge.js              # Native Bridge RPC wrapper & link interceptor
│   ├── ws.js                  # Gateway WebSocket client (message router & code 4403/1006 handling)
│   ├── stream.js              # 10 Hz Throttled TokenStreamBuffer with trailing-edge timer
│   ├── uec.js                 # Complete UEC State Machine with WebSocket dispatch
│   ├── editor.js              # CodeMirror 6 tab buffers & dirty sync
│   └── events.js              # Unified Action Router, auxclick, drag-lock & dual resizers
```

---

## 3. Deep Reactive State Store with WeakMap (`state.js`)

```javascript
export const initialState = {
  workspace: {
    rootPath: null,
    files: [],
    selectedPath: null
  },
  editor: {
    openTabs: [],             // Array of { id, path, name, isDirty }
    activeTabId: null
  },
  telemetry: {
    gpuName: "NVIDIA RTX 2070 Super",
    vramUsedMB: 4710,
    vramTotalMB: 8192,
    cpuUsagePct: 14.8,
    ramUsedMB: 5820,
    status: "ready"
  },
  execution: {
    state: "IDLE",            // IDLE | PLANNING | EXECUTING | REVIEW_DIFF | SUCCESS | FAILED | ROLLBACK | CANCELLED
    taskTitle: "",
    checklist: [],
    activeDiff: null
  },
  connection: {
    isSocketConnected: false,
    lastSeq: 0
  }
};

export class StudioStore {
  constructor(initialData) {
    this._subscribers = new Map();
    this._proxyCache = new WeakMap();
    this.state = this._createDeepProxy(initialData, "");
  }

  _createDeepProxy(target, path) {
    if (typeof target !== "object" || target === null) {
      return target;
    }

    if (this._proxyCache.has(target)) {
      return this._proxyCache.get(target);
    }

    const self = this;
    const proxyHandler = {
      get(obj, prop) {
        const val = obj[prop];
        if (typeof val === "object" && val !== null) {
          const nestedPath = path ? `${path}.${String(prop)}` : String(prop);
          return self._createDeepProxy(val, nestedPath);
        }
        return val;
      },
      set(obj, prop, value) {
        const oldValue = obj[prop];
        if (oldValue === value) return true;

        obj[prop] = value;
        const currentPath = path ? `${path}.${String(prop)}` : String(prop);
        
        self._notify(currentPath, value, oldValue);
        self._bubbleNotify(currentPath, value);
        return true;
      }
    };

    const proxy = new Proxy(target, proxyHandler);
    this._proxyCache.set(target, proxy);
    return proxy;
  }

  subscribe(path, callback) {
    if (!this._subscribers.has(path)) {
      this._subscribers.set(path, new Set());
    }
    this._subscribers.get(path).add(callback);
    return () => this._subscribers.get(path).delete(callback);
  }

  _notify(path, newValue, oldValue) {
    if (this._subscribers.has(path)) {
      for (const cb of this._subscribers.get(path)) {
        cb(newValue, oldValue);
      }
    }
  }

  _bubbleNotify(fullPath, value) {
    const parts = fullPath.split(".");
    while (parts.length > 1) {
      parts.pop();
      const parentPath = parts.join(".");
      this._notify(parentPath, value, undefined);
    }
  }
}

export const store = new StudioStore(initialState);
```

---

## 4. Hardened WebSocket Client with Message Router (`ws.js`)

```javascript
export class WebSocketClient {
  constructor(endpointUrl) {
    this.url = endpointUrl;   // Cookies carry session auth automatically
    this.socket = null;
    this.reconnectAttempts = 0;
    this.maxReconnectDelay = 10000;
    this.consecutive1006 = 0;
    this.handlers = new Map();
    this.outboundQueue = [];
    this.isFatalClosed = false;
  }

  on(actionType, handler) {
    if (!this.handlers.has(actionType)) {
      this.handlers.set(actionType, []);
    }
    this.handlers.get(actionType).push(handler);
  }

  _routeMessage(msg) {
    if (!msg || !msg.type) return;
    const handlers = this.handlers.get(msg.type);
    if (handlers) {
      for (const h of handlers) {
        try {
          h(msg.payload || msg);
        } catch (err) {
          console.error(`[WS] Handler error on ${msg.type}:`, err);
        }
      }
    }
  }

  connect() {
    if (this.isFatalClosed) return;

    this.socket = new WebSocket(this.url);

    this.socket.onopen = () => {
      console.log("[WS] Connected to Desktop Gateway.");
      this.reconnectAttempts = 0;
      this.consecutive1006 = 0;
      store.state.connection.isSocketConnected = true;
      this._flushSafeQueue();
      this._requestSnapshotResync();
    };

    this.socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.seq !== undefined) {
          const expected = store.state.connection.lastSeq + 1;
          if (store.state.connection.lastSeq > 0 && msg.seq !== expected) {
            console.warn(`[WS] Gap detected: got ${msg.seq}, expected ${expected}. Resyncing.`);
            store.state.connection.lastSeq = msg.seq;
            this._requestSnapshotResync();
            return;
          }
          store.state.connection.lastSeq = msg.seq;
        }
        this._routeMessage(msg);
      } catch (e) {
        console.error("[WS] Parse error:", e);
      }
    };

    this.socket.onclose = (event) => {
      store.state.connection.isSocketConnected = false;
      
      // Code 4401/4403/1008: Explicit Security Rejection -> Fatal halt
      if (event.code === 4401 || event.code === 4403 || event.code === 1008) {
        this.isFatalClosed = true;
        console.error(`[WS] Fatal: Authentication rejected by server (Code ${event.code}).`);
        alert("DeskAI security validation failed. Please restart application.");
        return;
      }

      // Code 1006: Handshake rejected or aborted
      if (event.code === 1006) {
        this.consecutive1006++;
        if (this.consecutive1006 >= 3) {
          this.isFatalClosed = true;
          console.error("[WS] Fatal: Repeated handshake failures (Code 1006). Halting.");
          return;
        }
      }

      this._scheduleReconnect();
    };
  }

  // Returns boolean status so caller knows if message was sent
  send(type, payload = {}, options = { replayable: false }) {
    const frame = {
      type,
      idempotency_key: crypto.randomUUID(),
      payload,
      timestamp: Date.now()
    };

    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(frame));
      return true;
    } else if (options.replayable) {
      this.outboundQueue.push(frame);
      return false;
    } else {
      console.warn(`[WS] Non-replayable action '${type}' dropped during disconnect.`);
      return false;
    }
  }

  _flushSafeQueue() {
    while (this.outboundQueue.length > 0 && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(this.outboundQueue.shift()));
    }
  }

  _requestSnapshotResync() {
    this.send("client.resync", { lastSeq: store.state.connection.lastSeq });
  }

  _scheduleReconnect() {
    this.reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), this.maxReconnectDelay);
    setTimeout(() => this.connect(), delay);
  }
}
```

---

## 5. Throttled Token Stream Buffer with Trailing-Edge Timer (`stream.js`)

Trailing-edge timer se aakhri token chunks kabhi stall nahi hotay:

```javascript
export class TokenStreamBuffer {
  constructor(targetElement) {
    this.target = targetElement;
    this.chunkQueue = [];
    this.accumulatedText = "";
    this.isScheduled = false;
    this.lastRenderTime = 0;
    this.renderIntervalMs = 100; // 10 Hz throttle
    this.trailingTimer = null;
    this.isUserScrolledUp = false;

    const container = this.target.parentElement;
    container.addEventListener("scroll", () => {
      const distanceToBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
      this.isUserScrolledUp = distanceToBottom > 40;
    });
  }

  append(chunk) {
    this.chunkQueue.push(chunk);
    this._scheduleFlush();
  }

  _scheduleFlush() {
    if (this.isScheduled) return;
    this.isScheduled = true;

    const now = performance.now();
    const elapsed = now - this.lastRenderTime;

    if (elapsed >= this.renderIntervalMs) {
      requestAnimationFrame(() => this._flush());
    } else {
      clearTimeout(this.trailingTimer);
      this.trailingTimer = setTimeout(() => {
        requestAnimationFrame(() => this._flush());
      }, this.renderIntervalMs - elapsed);
      this.isScheduled = false;
    }
  }

  _flush() {
    if (this.chunkQueue.length > 0) {
      this.accumulatedText += this.chunkQueue.join("");
      this.chunkQueue = [];
    }

    // Sanitize with DOMPurify 3.1.7
    const cleanHtml = DOMPurify.sanitize(marked.parse(this.accumulatedText), {
      ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'code', 'pre', 'ul', 'ol', 'li', 'span', 'h1', 'h2', 'h3', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'a'],
      ALLOWED_ATTR: ['href', 'class', 'target'],
      ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto):)/i
    });

    this.target.innerHTML = cleanHtml;
    this.lastRenderTime = performance.now();

    if (!this.isUserScrolledUp) {
      const container = this.target.parentElement;
      container.scrollTop = container.scrollHeight;
    }

    this.isScheduled = false;
  }

  complete() {
    clearTimeout(this.trailingTimer);
    this._flush();
    const announcer = document.getElementById("screenReaderAnnouncer");
    if (announcer) {
      announcer.textContent = "AI generation complete.";
    }
  }
}
```

---

## 6. Complete UEC Finite State Machine & Action Matrix (`uec.js`)

```
                  ┌──────────────(prompt.send)──────────────┐
                  │                                         │
                  ▼                                         ▼
┌─────────────────────────────────┐               ┌───────────────────┐
│            PLANNING             │──(cancel)────►│     CANCELLED     │
└────────────────┬────────────────┘               └─────────┬─────────┘
                 │ (approve)                                │ (uec-reset)
                 ▼                                          │
┌─────────────────────────────────┐                         │
│            EXECUTING            │──(cancel)───────────────┤
└────────┬───────────────┬────────┘                         │
         │ (complete)    │ (error)                          │
         ▼               ▼                                  │
┌─────────────────┐ ┌─────────────┐                         │
│   REVIEW_DIFF   │ │   FAILED    │                         │
└────────┬───┬────┘ └──────┬──────┘                         │
 (approve│   │(reject)     │ (rollback)                     │
         │   ▼             ▼                                │
         │  ┌─────────────────────┐                         │
         │  │      ROLLBACK       │                         │
         │  └──────────┬──────────┘                         │
         │             │ (complete)                         │
         ▼             ▼                                    ▼
┌─────────────────────────────────┐               ┌───────────────────┐
│             SUCCESS             │               │       IDLE        │
└────────────────┬────────────────┘               └─────────▲─────────┘
                 │ (auto-reset 3s)                          │
                 └──────────────────────────────────────────┘
```

### Complete Transitions Table & Action Mapping:
| State | Allowed Transitions | Trigger Actions | Buttons Rendered |
|---|---|---|---|
| `IDLE` | `PLANNING` | `prompt.send` | None (Input dock active) |
| `PLANNING` | `EXECUTING`, `CANCELLED`, `IDLE` | `uec-approve`, `uec-cancel` | "Approve & Execute", "Cancel" |
| `EXECUTING` | `REVIEW_DIFF`, `FAILED`, `CANCELLED` | `step.complete`, `step.error`, `uec-cancel` | "Cancel Execution" |
| `REVIEW_DIFF` | `SUCCESS`, `ROLLBACK`, `EXECUTING` | `uec-approve`, `uec-reject`, `uec-rollback` | "Accept Changes", "Reject Diff", "Rollback Changes" |
| `FAILED` | `ROLLBACK`, `CANCELLED`, `IDLE` | `uec-rollback`, `uec-cancel` | "Rollback to Safe State", "Dismiss" |
| `ROLLBACK` | `IDLE` | `rollback.done` | In-progress rollback spinner |
| `CANCELLED` | `IDLE` | `uec-reset` | "Reset" |
| `SUCCESS` | `IDLE` | Auto 3s | Success status badge |

```javascript
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
```

---

## 7. Action Router, Universal Link Interceptor & Drag-Lock (`events.js`)

```javascript
import { NativeBridge } from "./bridge.js";
import { store } from "./state.js";

export function initGlobalEvents() {
  // 1. Drag & Drop Navigation Lock
  window.addEventListener("dragover", (e) => e.preventDefault(), false);
  window.addEventListener("drop", (e) => e.preventDefault(), false);

  // 2. Universal Link Click Interceptor (click & auxclick for middle click)
  function handleLinkClick(e) {
    const anchor = e.target.closest("a[href]");
    if (anchor) {
      const url = anchor.getAttribute("href");
      if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("mailto:")) {
        e.preventDefault();
        window.pywebview.api.open_external_url(url);
      }
    }
  }
  document.addEventListener("click", handleLinkClick);
  document.addEventListener("auxclick", (e) => {
    if (e.button === 1) handleLinkClick(e);
  });

  // 3. Complete Action Router (All 16 actions)
  document.addEventListener("click", async (e) => {
    const trigger = e.target.closest("[data-action]");
    if (!trigger) return;

    const action = trigger.dataset.action;
    const param = trigger.dataset.param;

    switch (action) {
      case "win-minimize":
        NativeBridge.windowControl("minimize");
        break;
      case "win-maximize":
        NativeBridge.windowControl("maximize");
        break;
      case "win-close":
        NativeBridge.windowControl("close");
        break;

      case "tab-close":
        window.EditorManager.closeTab(param);
        break;
      case "select-tab":
        window.EditorManager.selectTab(param);
        break;

      case "open-palette":
        document.getElementById("commandPaletteDialog").showModal();
        break;
      case "switch-panel":
        document.querySelectorAll(".activity-btn").forEach(b => b.classList.remove("active"));
        trigger.classList.add("active");
        break;

      case "open-folder-dialog":
        const dir = await NativeBridge.selectFolder();
        if (dir && dir.path) {
          store.state.workspace.rootPath = dir.path;
        }
        break;
      case "new-file":
        const fileName = prompt("Enter new file name:");
        if (fileName) window.EditorManager.createBuffer(fileName);
        break;
      case "new-folder":
        prompt("Enter folder name:");
        break;
      case "refresh-tree":
        console.log("Refreshing workspace tree...");
        break;

      case "toggle-drawer":
        document.getElementById("bottomDrawer").classList.toggle("collapsed");
        break;
      case "drawer-tab":
        document.querySelectorAll(".drawer-tab").forEach(t => t.classList.remove("active"));
        trigger.classList.add("active");
        break;

      case "uec-approve":
        window.UEC.approvePlan();
        break;
      case "uec-reject":
        window.UEC.rejectPlan();
        break;
      case "uec-rollback":
        window.UEC.rollback();
        break;
      case "uec-cancel":
        window.UEC.cancel();
        break;
      case "uec-reset":
        window.UEC.reset();
        break;

      default:
        console.warn("Unhandled action:", action);
    }
  });

  // 4. Global Hotkeys
  window.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key === "p") {
      e.preventDefault();
      document.getElementById("commandPaletteDialog").showModal();
    } else if (e.ctrlKey && e.key === "s") {
      e.preventDefault();
      console.log("Saving active buffer...");
    } else if (e.ctrlKey && e.key === "Enter") {
      e.preventDefault();
      document.getElementById("promptForm").requestSubmit();
    }
  });
}
```

---

## 8. Application Bootstrap & Event Wiring (`app.js`)

```javascript
import { WebSocketClient } from "./ws.js";
import { UECStateMachine } from "./uec.js";
import { store } from "./state.js";
import { initGlobalEvents } from "./events.js";

// Global singletons instantiated and wired
window.wsClient = new WebSocketClient(`ws://${location.host}/ws`);
window.UEC = new UECStateMachine();

// Wire incoming server push events to UEC state machine
window.wsClient.on("agent.plan", (payload) => {
  window.UEC.transition("PLANNING", payload);
});
window.wsClient.on("agent.executing", (payload) => {
  window.UEC.transition("EXECUTING", payload);
});
window.wsClient.on("agent.diff", (payload) => {
  window.UEC.transition("REVIEW_DIFF", payload);
});
window.wsClient.on("agent.failed", (payload) => {
  window.UEC.transition("FAILED", payload);
});

// Initialize event router & connect socket
initGlobalEvents();
window.wsClient.connect();
```
