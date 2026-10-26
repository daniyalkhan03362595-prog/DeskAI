# Layer 1 Technology LLD: JavaScript Client State, Streaming & DOM Architecture

Yeh document **DeskAI** ke **Layer 1 (Presentation & Client Logic)** mein use hone wali **Pure Vanilla JavaScript (ES2022 Modules)** ki mukammal **Low-Level Design (LLD)** specifications, recursive deep proxy store, CodeMirror 6 editor integration, WebSocket client with resync protocol, symmetric resizer math aur UEC finite state machine ko **Roman Urdu** mein tafseel se bayan karta hai.

---

## 1. Executive Summary & Design Constraints

DeskAI ka frontend kisi heavy framework ya bundling toolchain ke baghair **Native ES Modules** par mushtamil hai jo browser engine ke andar direct load hoti hai.

### Low-Level Technical Constraints:
1. **Zero-Bundling & Native Modules:** Direct browser ES imports (`import { store } from './state.js'`).
2. **Deep Observable Reactivity:** Recursive `Proxy` tree jo nested state mutations (`store.state.execution.state = 'PLANNING'`) ko accurately detect aur notify kare.
3. **Sub-16ms Frame Budget (60 FPS):** `requestAnimationFrame` token batching aur DOMPurify sanitization.
4. **Deterministic State Synchronization:** Backend desktop supervisor source-of-truth ke sath sequence-numbered resync.

---

## 2. Directory & Client Module Architecture

```text
src/deskai/static/js/
├── app.js                    # Entry point, bootstrapping & token reception
├── state.js                  # Deep Reactive StudioStore (Recursive Proxy Engine)
├── bridge.js                 # PyWebView Native Bridge client wrapper
├── ws.js                     # WebSocketClient (Exponential backoff, queue & resync)
├── stream.js                 # TokenStreamBuffer with DOMPurify & rAF scheduler
├── uec.js                    # UEC State Machine with Cancel & Rollback states
├── editor.js                 # CodeMirror 6 embedded editor controller
├── events.js                 # Synchronized Action Router & Dual-Sided Resizers
└── components/
    ├── filetree.js           # Directory tree renderer
    ├── telemetry.js          # Hardware gauges, GPU VRAM & host memory status
    └── diffview.js           # Side-by-side & inline diff view
```

---

## 3. Deep Reactive State Store (`state.js`)

Shallow proxy ke masle ko hal karne ke liye recursive Proxy pattern implement kiya gaya hai:

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
    this.state = this._createDeepProxy(initialData, "");
  }

  _createDeepProxy(target, path) {
    if (typeof target !== "object" || target === null) {
      return target;
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
        obj[prop] = value;
        const currentPath = path ? `${path}.${String(prop)}` : String(prop);
        self._notify(currentPath, value, oldValue);
        return true;
      }
    };

    return new Proxy(target, proxyHandler);
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
}

export const store = new StudioStore(initialState);
```

---

## 4. WebSocket Client with Resync & Offline Queue (`ws.js`)

```javascript
export class WebSocketClient {
  constructor(endpointUrl, authToken) {
    this.url = `${endpointUrl}?token=${authToken}`;
    this.socket = null;
    this.reconnectAttempts = 0;
    this.maxReconnectDelay = 10000;
    this.handlers = new Map();
    this.outboundQueue = [];
    this.watchdogTimer = null;
  }

  connect() {
    this.socket = new WebSocket(this.url);

    this.socket.onopen = () => {
      console.log("[WS] Connected & Authenticated.");
      this.reconnectAttempts = 0;
      store.state.connection.isSocketConnected = true;
      this._flushQueue();
      this._requestSnapshotResync();
      this._startWatchdog();
    };

    this.socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.seq) {
          store.state.connection.lastSeq = msg.seq;
        }
        this._routeMessage(msg);
      } catch (e) {
        console.error("[WS] JSON parse error:", e);
      }
    };

    this.socket.onclose = () => {
      store.state.connection.isSocketConnected = false;
      this._stopWatchdog();
      this._scheduleReconnect();
    };
  }

  send(type, payload = {}) {
    const frame = { type, payload, timestamp: Date.now() };
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(frame));
    } else {
      console.warn("[WS] Socket offline. Queuing message:", type);
      this.outboundQueue.push(frame);
    }
  }

  _flushQueue() {
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
    console.log(`[WS] Reconnecting in ${delay}ms...`);
    setTimeout(() => this.connect(), delay);
  }
}
```

---

## 5. Token Stream Buffer with DOMPurify (`stream.js`)

AI ke generated output ko xss-safe tareeqe se render karne ke liye `DOMPurify` use hota hai:

```javascript
export class TokenStreamBuffer {
  constructor(targetElement) {
    this.target = targetElement;
    this.queue = [];
    this.isScheduled = false;
  }

  append(chunk) {
    this.queue.push(chunk);
    if (!this.isScheduled) {
      this.isScheduled = true;
      requestAnimationFrame(() => this._flush());
    }
  }

  _flush() {
    if (this.queue.length === 0) {
      this.isScheduled = false;
      return;
    }

    const rawMarkdown = this.queue.join("");
    this.queue = [];

    // Parse markdown and sanitize via DOMPurify
    const cleanHtml = DOMPurify.sanitize(marked.parse(rawMarkdown));
    this.target.innerHTML = cleanHtml;

    this.target.parentElement.scrollTop = this.target.parentElement.scrollHeight;
    this.isScheduled = false;
  }
}
```

---

## 6. UEC Finite State Machine with Cancel & Rollback (`uec.js`)

```
[IDLE] ──(prompt.send)──► [PLANNING] ──(plan.approved)──► [EXECUTING]
  ▲                           │                                │
  │                     (user.cancel)                   (step.complete)
  │                           │                                │
  │                           ▼                                ▼
[SUCCESS] ◄──(diff.accepted)── [REVIEW_DIFF]           [REVIEW_DIFF]
  │                                   │
  ├───(diff.rejected)─────────────────┤
  │                                   ▼
  └─────────────────────────────► [ROLLBACK] ──► [IDLE]
```

```javascript
export class UECStateMachine {
  constructor() {
    this.currentState = "IDLE";
    this.transitions = {
      IDLE: ["PLANNING"],
      PLANNING: ["EXECUTING", "CANCELLED", "IDLE"],
      EXECUTING: ["REVIEW_DIFF", "FAILED", "CANCELLED"],
      REVIEW_DIFF: ["SUCCESS", "ROLLBACK", "EXECUTING"],
      SUCCESS: ["IDLE"],
      ROLLBACK: ["IDLE"],
      CANCELLED: ["IDLE"],
      FAILED: ["IDLE", "ROLLBACK"]
    };
  }

  transition(nextState, payload = {}) {
    const allowed = this.transitions[this.currentState];
    if (!allowed || !allowed.includes(nextState)) {
      console.error(`Invalid UEC transition from ${this.currentState} to ${nextState}`);
      return false;
    }

    this.currentState = nextState;
    store.state.execution.state = nextState;
    this._handleStateSideEffects(nextState, payload);
    return true;
  }

  cancel() {
    return this.transition("CANCELLED");
  }

  rollback() {
    return this.transition("ROLLBACK");
  }
}
```

---

## 7. Synchronized Event Router & Dual-Panel Resizers (`events.js`)

### 7.1 Synchronized Action Router
Action names HTML aur JS mein 100% synchronized hain:

```javascript
document.addEventListener("click", (e) => {
  const trigger = e.target.closest("[data-action]");
  if (!trigger) return;

  const action = trigger.dataset.action;
  const param = trigger.dataset.param;

  switch (action) {
    case "tab-close":
      EditorManager.closeTab(param);
      break;
    case "win-minimize":
      NativeBridge.windowControl("minimize");
      break;
    case "win-maximize":
      NativeBridge.windowControl("maximize");
      break;
    case "win-close":
      NativeBridge.windowControl("close");
      break;
    case "uec-approve":
      UEC.approvePlan();
      break;
    case "uec-reject":
      UEC.rejectPlan();
      break;
    case "uec-rollback":
      UEC.rollback();
      break;
    case "uec-cancel":
      UEC.cancel();
      break;
  }
});
```

### 7.2 Symmetric Resizer Math
Left aur right sidebar resizing ka correct mathematical formula:

```javascript
export function initResizers() {
  const leftResizer = document.getElementById("resizerLeft");
  const rightResizer = document.getElementById("resizerRight");

  // Left Sidebar Resizer
  leftResizer.addEventListener("pointerdown", (e) => {
    leftResizer.setPointerCapture(e.pointerId);
    const onMove = (ev) => {
      const newWidth = Math.max(200, Math.min(ev.clientX, 550));
      document.documentElement.style.setProperty("--sidebar-left-w", `${newWidth}px`);
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  });

  // Right Sidebar Resizer (Window Width - clientX)
  rightResizer.addEventListener("pointerdown", (e) => {
    rightResizer.setPointerCapture(e.pointerId);
    const onMove = (ev) => {
      const newWidth = Math.max(260, Math.min(window.innerWidth - ev.clientX, 650));
      document.documentElement.style.setProperty("--sidebar-right-w", `${newWidth}px`);
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  });
}
```
