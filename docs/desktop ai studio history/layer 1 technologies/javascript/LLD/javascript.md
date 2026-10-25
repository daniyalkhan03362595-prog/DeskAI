# Layer 1 Technology LLD: JavaScript Client State, Streaming & DOM Architecture

Yeh document **Desktop AI Studio** ke **Layer 1 (Frontend)** mein use hone wali **Pure Vanilla JavaScript (ES2022)** ki mukammal **Low-Level Design (LLD)** specifications, module breakdown, reactive store implementation, PyWebView bridge integration, rAF token batcher, aur UEC finite state machine ko **Roman Urdu** mein tafseel se bayan karta hai.

---

## 1. Executive Summary & Design Constraints

Desktop AI Studio ka frontend kisi bhi bhaari framework (React, Vue, Angular) ya bundling toolchain (Webpack, Vite, npm) ke baghair chalta hai. Poori application **Native ES Modules** par mushtamil hai jo browser engine ke andar direct load hoti hai.

### Low-Level Technical Constraints:
1. **Zero Runtime Dependencies:** Sirf native browser APIs (`WebSocket`, `Proxy`, `requestAnimationFrame`, `PointerEvent`, `CustomEvent`) use hoti hain.
2. **Sub-16ms Frame Budget (60 FPS):** AI text generation ke dauran 50-80 tokens/sec aane par bhi UI layout thrashing ya frame drop nahi hona chahiye.
3. **Deterministic State Synchronization:** Python backend, PyWebView bridge, aur WebSocket events ka state aik single predictable store mein synchronize hota hai.

---

## 2. Directory & Client Module Architecture

Frontend ka code modular ES6 files mein taqseem hota hai:

```text
src/deskai/static/js/
├── app.js                    # Entry point, initialization & event orchestration
├── state.js                  # Reactive StudioStore (Proxy-based observable state)
├── bridge.js                 # PyWebView Native Bridge client wrapper
├── ws.js                     # WebSocketClient (exponential backoff & message router)
├── stream.js                 # High-Speed TokenStreamBuffer & rAF scheduler
├── uec.js                    # Unified Execution Card (UEC) finite state machine
├── editor.js                 # TabManager, multi-file buffers & dirty tracking
├── events.js                 # Event delegation router, resizers & global keybindings
└── components/
    ├── filetree.js           # Virtual directory tree renderer
    ├── telemetry.js          # Hardware gauges, GPU VRAM & status pills
    └── diffview.js           # Split & inline diff rendering engine
```

---

## 3. Reactive State Store Specification (`state.js`)

Central state management ke liye lightweight `Proxy` pattern use hota hai jo mutations ko intercept kar ke registered subscriber callbacks trigger karta hai.

```javascript
/**
 * StudioState Definition
 */
export const initialState = {
  workspace: {
    rootPath: null,
    files: [],
    selectedPath: null
  },
  editor: {
    openTabs: new Map(),      // tabId -> { path, name, content, isDirty, cursor }
    activeTabId: null
  },
  telemetry: {
    gpuName: "NVIDIA RTX 2070 Super",
    vramUsedMB: 0,
    vramTotalMB: 8192,
    cpuUsagePct: 0,
    ramUsedMB: 0,
    status: "ready"
  },
  execution: {
    state: "IDLE",            // IDLE | PLANNING | EXECUTING | REVIEW_DIFF | SUCCESS | FAILED
    taskTitle: "",
    checklist: [],
    activeDiff: null
  },
  connection: {
    isSocketConnected: false,
    isBridgeReady: false
  }
};

class StudioStore {
  constructor(state) {
    this._subscribers = new Map();
    this.state = this._createProxy(state);
  }

  _createProxy(target, path = "") {
    const self = this;
    return new Proxy(target, {
      set(obj, prop, value) {
        const oldValue = obj[prop];
        obj[prop] = value;
        const currentPath = path ? `${path}.${prop}` : prop;
        self._notify(currentPath, value, oldValue);
        return true;
      }
    });
  }

  subscribe(path, callback) {
    if (!this._subscribers.has(path)) {
      this._subscribers.set(path, new Set());
    }
    this._subscribers.get(path).add(callback);
    return () => this._subscribers.get(path).delete(callback);
  }

  _notify(path, newValue, oldValue) {
    // Exact path notifications
    if (this._subscribers.has(path)) {
      this._subscribers.get(path).forEach(cb => cb(newValue, oldValue));
    }
    // Wildcard path notifications (e.g. "telemetry.*")
    const parentPath = path.substring(0, path.lastIndexOf("."));
    if (this._subscribers.has(`${parentPath}.*`)) {
      this._subscribers.get(`${parentPath}.*`).forEach(cb => cb(newValue, oldValue, path));
    }
  }
}

export const store = new StudioStore(initialState);
```

---

## 4. PyWebView Native Bridge Client (`bridge.js`)

Frontend par `window.pywebview.api` ko direct call karne ke bajaye aik guarded wrapper use kiya jata hai jo `pywebviewready` event ka intezar karta hai aur offline testing support karta hai.

```javascript
export class NativeBridge {
  static _isReady = false;
  static _readyPromise = null;

  static init() {
    if (this._readyPromise) return this._readyPromise;

    this._readyPromise = new Promise((resolve) => {
      if (window.pywebview && window.pywebview.api) {
        this._isReady = true;
        resolve(window.pywebview.api);
      } else {
        window.addEventListener("pywebviewready", () => {
          this._isReady = true;
          resolve(window.pywebview.api);
        }, { once: true });
      }
    });
    return this._readyPromise;
  }

  static async call(methodName, ...args) {
    await this.init();
    if (!window.pywebview || !window.pywebview.api[methodName]) {
      throw new Error(`NativeBridge: Method '${methodName}' not found on PyWebView API.`);
    }

    try {
      const response = await window.pywebview.api[methodName](...args);
      if (!response.success) {
        throw new Error(response.error || `Error in ${methodName}`);
      }
      return response.data;
    } catch (err) {
      console.error(`[Bridge Error] ${methodName}:`, err);
      throw err;
    }
  }

  // High-Level Helper Abstractions
  static selectFolder(title = "Select Project Folder") {
    return this.call("open_directory_dialog", title);
  }

  static selectFiles(fileTypes, allowMultiple = false) {
    return this.call("open_file_dialog", fileTypes, allowMultiple);
  }

  static saveFile(defaultFilename) {
    return this.call("save_file_dialog", defaultFilename);
  }

  static fetchTelemetry() {
    return this.call("get_hardware_telemetry");
  }

  static windowControl(action) {
    return this.call("control_window", action);
  }
}
```

---

## 5. WebSocket Client & Exponential Backoff (`ws.js`)

Real-time streaming, chat interaction aur AI coordination ke liye resilient WebSocket connection implement kiya gaya hai:

```javascript
export class WebSocketClient {
  constructor(url) {
    this.url = url;
    this.socket = null;
    this.reconnectAttempts = 0;
    this.maxReconnectDelay = 10000;
    this.handlers = new Map();
    this.heartbeatTimer = null;
  }

  connect() {
    this.socket = new WebSocket(this.url);

    this.socket.onopen = () => {
      console.log("[WS] Connected to Desktop AI Studio Gateway.");
      this.reconnectAttempts = 0;
      store.state.connection.isSocketConnected = true;
      this._startHeartbeat();
    };

    this.socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        this._routeMessage(message);
      } catch (e) {
        console.error("[WS] Malformed JSON payload:", event.data);
      }
    };

    this.socket.onclose = () => {
      store.state.connection.isSocketConnected = false;
      this._stopHeartbeat();
      this._scheduleReconnect();
    };

    this.socket.onerror = (err) => {
      console.warn("[WS] Socket encountered error:", err);
      this.socket.close();
    };
  }

  on(actionType, handler) {
    if (!this.handlers.has(actionType)) {
      this.handlers.set(actionType, []);
    }
    this.handlers.get(actionType).push(handler);
  }

  send(actionType, payload = {}) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type: actionType, payload }));
    } else {
      console.warn("[WS] Cannot send message, socket is closed.");
    }
  }

  _routeMessage(message) {
    const { type, payload } = message;
    if (this.handlers.has(type)) {
      this.handlers.get(type).forEach(fn => fn(payload));
    }
  }

  _scheduleReconnect() {
    this.reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), this.maxReconnectDelay);
    console.log(`[WS] Reconnecting in ${Math.round(delay)}ms (Attempt ${this.reconnectAttempts})...`);
    setTimeout(() => this.connect(), delay);
  }

  _startHeartbeat() {
    this.heartbeatTimer = setInterval(() => {
      this.send("ping");
    }, 15000);
  }

  _stopHeartbeat() {
    if (this.heartbeatTimer) clearInterval(this.heartbeatTimer);
  }
}
```

---

## 6. High-Speed Token Streaming & rAF Scheduler (`stream.js`)

Jab local Qwen 7B model 60+ tokens/sec stream karta hai, to har character par DOM mutation browser ko hang kar sakti hai. Iske hal ke liye **Micro-batching Engine** implement kiya gaya hai:

```javascript
export class TokenStreamBuffer {
  constructor(targetElement) {
    this.target = targetElement;
    this.chunkQueue = [];
    this.isFlushScheduled = false;
    this.isUserScrolledUp = false;

    // Detect user manual scroll to avoid disruptive auto-scrolling
    this.target.parentElement.addEventListener("scroll", () => {
      const el = this.target.parentElement;
      const atBottom = el.scrollHeight - el.scrollTop <= el.clientHeight + 30;
      this.isUserScrolledUp = !atBottom;
    });
  }

  append(tokenChunk) {
    this.chunkQueue.push(tokenChunk);
    if (!this.isFlushScheduled) {
      this.isFlushScheduled = true;
      requestAnimationFrame(() => this._flush());
    }
  }

  _flush() {
    if (this.chunkQueue.length === 0) {
      this.isFlushScheduled = false;
      return;
    }

    // Join all accumulated tokens during the frame window
    const combinedText = this.chunkQueue.join("");
    this.chunkQueue = [];

    // Fast append without re-parsing entire innerHTML
    const textNode = document.createTextNode(combinedText);
    this.target.appendChild(textNode);

    // Auto-scroll only if user is at bottom
    if (!this.isUserScrolledUp) {
      const container = this.target.parentElement;
      container.scrollTop = container.scrollHeight;
    }

    this.isFlushScheduled = false;
  }
}
```

---

## 7. Unified Execution Card (UEC) Finite State Machine (`uec.js`)

AI execution ka lifecycle aik deterministic State Machine follow karta hai:

```
[IDLE] ──(prompt.send)──► [PLANNING] ──(plan.approved)──► [EXECUTING]
  ▲                                                            │
  │                                                            ▼
[SUCCESS] ◄──(diff.accepted)── [REVIEW_DIFF] ◄──(step.complete)┘
  │                                   │
  └───(diff.rejected)─────────────────┘
```

### State Machine Implementation:
```javascript
export class UECStateMachine {
  constructor() {
    this.currentState = "IDLE";
    this.transitions = {
      IDLE: ["PLANNING"],
      PLANNING: ["EXECUTING", "IDLE"],
      EXECUTING: ["REVIEW_DIFF", "FAILED"],
      REVIEW_DIFF: ["SUCCESS", "FAILED", "EXECUTING"],
      SUCCESS: ["IDLE"],
      FAILED: ["IDLE", "PLANNING"]
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

    this._onStateChange(nextState, payload);
    return true;
  }

  _onStateChange(state, payload) {
    switch (state) {
      case "PLANNING":
        store.state.execution.checklist = payload.steps || [];
        break;
      case "EXECUTING":
        store.state.execution.currentStep = payload.activeStepIndex;
        break;
      case "REVIEW_DIFF":
        store.state.execution.activeDiff = payload.diffData;
        break;
      case "SUCCESS":
        // Auto reset after 3 seconds
        setTimeout(() => this.transition("IDLE"), 3000);
        break;
    }
  }
}
```

---

## 8. Global Event Delegation & Resizer Engine (`events.js`)

Pure DOM interaction model mein per-element listener lagane ke bajaye single global dispatcher use hota hai:

### 8.1 Action Router (Click Delegation)
```javascript
document.addEventListener("click", (e) => {
  const trigger = e.target.closest("[data-action]");
  if (!trigger) return;

  const action = trigger.dataset.action;
  const param = trigger.dataset.param;

  switch (action) {
    case "tab-close":
      TabManager.closeTab(param);
      break;
    case "diff-accept":
      UEC.acceptDiff();
      break;
    case "window-minimize":
      NativeBridge.windowControl("minimize");
      break;
  }
});
```

### 8.2 Pointer Drag Resizers
Sidebar dividers par smooth resizing ke liye `PointerEvents` use hotay hain:
```javascript
export function initResizer(resizerEl, cssVarName, minWidth = 200, maxWidth = 550) {
  resizerEl.addEventListener("pointerdown", (e) => {
    resizerEl.setPointerCapture(e.pointerId);
    resizerEl.classList.add("resizing");

    const onPointerMove = (moveEvent) => {
      const newWidth = Math.max(minWidth, Math.min(moveEvent.clientX, maxWidth));
      document.documentElement.style.setProperty(cssVarName, `${newWidth}px`);
    };

    const onPointerUp = () => {
      resizerEl.releasePointerCapture(e.pointerId);
      resizerEl.classList.remove("resizing");
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
  });
}
```
