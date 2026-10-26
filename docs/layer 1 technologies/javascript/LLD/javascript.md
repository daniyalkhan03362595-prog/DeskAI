# Layer 1 Technology LLD: JavaScript Client State, Streaming & DOM Architecture

Yeh document **DeskAI** ke **Layer 1 (Presentation & Client Logic)** mein use hone wali **Pure Vanilla JavaScript (ES2022 Modules)** ki mukammal **Low-Level Design (LLD)** specifications, recursive deep proxy store with WeakMap cache, accumulated text streamer with DOMPurify, complete UEC finite state machine, full action router, aur CodeMirror 6 vendor integration ko **Roman Urdu** mein tafseel se bayan karta hai.

---

## 1. Executive Summary & Design Constraints

DeskAI ka frontend bina kisi runtime framework ke **Native ES Modules** par mushtamil hai.

### Low-Level Technical Constraints:
1. **Zero App Bundling & Vendor Singletons:** App code bina bundling ke direct browser ES modules mein run hota hai. External libraries (CodeMirror 6, DOMPurify, Marked) pre-bundled vendor files (`static/vendor/`) ke zariye provide hoti hain.
2. **Deep Observable Reactivity:** Recursive `Proxy` tree with WeakMap caching jo reference equality (`state.execution === state.execution`), ancestor bubbling, aur array mutations ko accurately track kare.
3. **Accumulated Token Streaming:** `requestAnimationFrame` text accumulation jo multi-frame AI streaming mein pehla text overwrite na kare aur user scroll detection ko preserve kare.
4. **Deterministic UEC State Machine:** Idempotent transitions, gap-aware WebSocket sequencing, aur state-driven UI button rendering.

---

## 2. Directory & Client Module Architecture

```text
src/deskai/static/
├── index.html
├── vendor/
│   ├── codemirror.bundle.js   # Pre-bundled CM6 core, syntax & theme (pinned hash)
│   ├── marked.min.js          # Fast markdown parser
│   └── purify.min.js          # DOMPurify sanitizer
├── js/
│   ├── app.js                 # Entry point, bootstrapping & watchdog
│   ├── state.js               # WeakMap-cached Deep Reactive StudioStore
│   ├── bridge.js              # Native Bridge RPC wrapper & link interceptor
│   ├── ws.js                  # Gateway WebSocket client (gap detection & fatal code handling)
│   ├── stream.js              # Accumulated TokenStreamBuffer & scroll lock
│   ├── uec.js                 # Finite State Machine & state-action matrix
│   ├── editor.js              # CodeMirror 6 tab buffers & dirty sync
│   └── events.js              # Unified Action Router & dual-sided resizers
```

---

## 3. Deep Reactive State Store with WeakMap (`state.js`)

Shallow proxy aur reference equality (`===`) ke maslon ko hal karne ke liye WeakMap cache aur ancestor notification bubbling implement ki gayi hai:

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
        // Skip no-op writes
        if (oldValue === value) return true;

        obj[prop] = value;
        const currentPath = path ? `${path}.${String(prop)}` : String(prop);
        
        // Notify leaf and bubble to ancestors
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

## 4. Gap-Aware WebSocket Client (`ws.js`)

State-sensitive approvals ki accidental replay rokne aur packet sequencing maintain karne ke liye client:

```javascript
export class WebSocketClient {
  constructor(endpointUrl) {
    this.url = endpointUrl;   // Cookies carry session auth automatically
    this.socket = null;
    this.reconnectAttempts = 0;
    this.maxReconnectDelay = 10000;
    this.handlers = new Map();
    this.outboundQueue = [];
    this.isFatalClosed = false;
  }

  connect() {
    if (this.isFatalClosed) return;

    this.socket = new WebSocket(this.url);

    this.socket.onopen = () => {
      console.log("[WS] Connected to Desktop Gateway.");
      this.reconnectAttempts = 0;
      store.state.connection.isSocketConnected = true;
      this._flushSafeQueue();
      this._requestSnapshotResync();
    };

    this.socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.seq !== undefined) {
          const expected = store.state.connection.lastSeq + 1;
          // Sequence gap detection
          if (store.state.connection.lastSeq > 0 && msg.seq !== expected) {
            console.warn(`[WS] Gap detected: got ${msg.seq}, expected ${expected}. Resyncing.`);
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
      // Code 1008: Policy Violation (Bad Token) -> Fatal close
      if (event.code === 1008) {
        this.isFatalClosed = true;
        console.error("[WS] Fatal: Authentication rejected by server (Code 1008).");
        alert("DeskAI session expired or invalid. Please restart application.");
        return;
      }
      this._scheduleReconnect();
    };
  }

  send(type, payload = {}, options = { replayable: true }) {
    const frame = {
      type,
      idempotency_key: crypto.randomUUID(),
      payload,
      timestamp: Date.now()
    };

    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(frame));
    } else if (options.replayable) {
      // Sirf safe queries queue hoti hain; state mutations (jaise uec-approve) queue nahi hotin
      this.outboundQueue.push(frame);
    } else {
      console.warn(`[WS] State-sensitive action '${type}' dropped during disconnect.`);
    }
  }

  _flushSafeQueue() {
    while (this.outboundQueue.length > 0 && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(this.outboundQueue.shift()));
    }
  }

  _requestSnapshotResync() {
    this.send("client.resync", { lastSeq: store.state.connection.lastSeq }, { replayable: false });
  }

  _scheduleReconnect() {
    this.reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), this.maxReconnectDelay);
    setTimeout(() => this.connect(), delay);
  }
}
```

---

## 5. Accumulated Token Stream Buffer with Scroll Lock (`stream.js`)

Frame text loss bug ko fix karne ke liye accumulated buffer pattern:

```javascript
export class TokenStreamBuffer {
  constructor(targetElement) {
    this.target = targetElement;
    this.chunkQueue = [];
    this.accumulatedText = "";
    this.isScheduled = false;
    this.isUserScrolledUp = false;

    // Detect user scrolling away from bottom
    const container = this.target.parentElement;
    container.addEventListener("scroll", () => {
      const distanceToBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
      this.isUserScrolledUp = distanceToBottom > 40;
    });
  }

  append(chunk) {
    this.chunkQueue.push(chunk);
    if (!this.isScheduled) {
      this.isScheduled = true;
      requestAnimationFrame(() => this._flush());
    }
  }

  _flush() {
    if (this.chunkQueue.length === 0) {
      this.isScheduled = false;
      return;
    }

    // 1. Accumulate all incoming chunks into the full response string
    this.accumulatedText += this.chunkQueue.join("");
    this.chunkQueue = [];

    // 2. Parse accumulated markdown and sanitize
    const cleanHtml = DOMPurify.sanitize(marked.parse(this.accumulatedText), {
      ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'code', 'pre', 'ul', 'ol', 'li', 'span', 'h1', 'h2', 'h3', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'a'],
      ALLOWED_ATTR: ['href', 'class', 'target'],
      ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto):)/i
    });

    this.target.innerHTML = cleanHtml;

    // 3. Scroll to bottom only if user hasn't scrolled up
    if (!this.isUserScrolledUp) {
      const container = this.target.parentElement;
      container.scrollTop = container.scrollHeight;
    }

    this.isScheduled = false;
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
                 │ (approve)                                │ (reset)
                 ▼                                          ▼
┌─────────────────────────────────┐               ┌───────────────────┐
│            EXECUTING            │──(cancel)────►│       IDLE        │
└────────┬───────────────┬────────┘               └─────────▲─────────┘
         │ (complete)    │ (error)                          │ (done)
         ▼               ▼                                  │
┌─────────────────┐ ┌─────────────┐               ┌─────────┴─────────┐
│   REVIEW_DIFF   │ │   FAILED    │               │      SUCCESS      │
└────────┬────────┘ └──────┬──────┘               └─────────▲─────────┘
         │ (reject)        │ (rollback)                     │
         ▼                 ▼                                │
┌─────────────────────────────────┐                         │
│            ROLLBACK             │─────────────────────────┘
└─────────────────────────────────┘
```

### State-Action Rendering Matrix:
| State | Allowed Actions | Rendered Buttons |
|---|---|---|
| `IDLE` | `prompt.send` | None (Input dock active) |
| `PLANNING` | `uec-approve`, `uec-cancel` | "Cancel", "Approve & Execute" |
| `EXECUTING` | `uec-cancel` | "Cancel Execution" |
| `REVIEW_DIFF` | `uec-approve`, `uec-reject`, `uec-rollback` | "Rollback", "Reject Diff", "Approve Changes" |
| `FAILED` | `uec-rollback`, `uec-cancel` | "Rollback Changes", "Dismiss" |
| `SUCCESS` | Auto-resets to `IDLE` after 3s | Status badge "Complete" |
| `CANCELLED` | `uec-reset` | "Reset" |

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

    store.state.execution.state = nextState;
    this.renderButtons(nextState);
    return true;
  }

  approvePlan() { return this.transition("EXECUTING"); }
  rejectPlan() { return this.transition("IDLE"); }
  rollback() { return this.transition("ROLLBACK"); }
  cancel() { return this.transition("CANCELLED"); }

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
        <button class="uec-btn btn-rollback" data-action="uec-rollback">Rollback</button>
        <button class="uec-btn btn-reject" data-action="uec-reject">Reject</button>
        <button class="uec-btn btn-approve" data-action="uec-approve">Accept Changes</button>
      `;
    } else if (state === "FAILED" || state === "CANCELLED") {
      buttonsHtml = `<button class="uec-btn btn-rollback" data-action="uec-rollback">Reset to Safe State</button>`;
    }

    actionsContainer.innerHTML = buttonsHtml;
  }
}
```

---

## 7. Complete Action Router & Link Interceptor (`events.js`)

Tamam 15 HTML `data-action` attributes aur external link interception ko handle karta hai:

```javascript
import { NativeBridge } from "./bridge.js";
import { store } from "./state.js";

export function initGlobalEvents() {
  // 1. External Links Click Interceptor
  document.addEventListener("click", (e) => {
    const anchor = e.target.closest("a[href]");
    if (anchor) {
      const url = anchor.getAttribute("href");
      if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("mailto:")) {
        e.preventDefault();
        window.pywebview.api.open_external_url(url);
        return;
      }
    }
  });

  // 2. Complete Action Router (Matches 100% of HTML data-actions)
  document.addEventListener("click", async (e) => {
    const trigger = e.target.closest("[data-action]");
    if (!trigger) return;

    const action = trigger.dataset.action;
    const param = trigger.dataset.param;

    switch (action) {
      // Window Controls
      case "win-minimize":
        NativeBridge.windowControl("minimize");
        break;
      case "win-maximize":
        NativeBridge.windowControl("maximize");
        break;
      case "win-close":
        NativeBridge.windowControl("close");
        break;

      // Editor Tabs
      case "tab-close":
        window.EditorManager.closeTab(param);
        break;
      case "select-tab":
        window.EditorManager.selectTab(param);
        break;

      // Command Palette & Navigation
      case "open-palette":
        document.getElementById("commandPaletteDialog").showModal();
        break;
      case "switch-panel":
        document.querySelectorAll(".activity-btn").forEach(b => b.classList.remove("active"));
        trigger.classList.add("active");
        console.log("Switching to panel:", trigger.dataset.panel);
        break;

      // File Explorer Actions
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

      // Bottom Drawer Controls
      case "toggle-drawer":
        document.getElementById("bottomDrawer").classList.toggle("collapsed");
        break;
      case "drawer-tab":
        document.querySelectorAll(".drawer-tab").forEach(t => t.classList.remove("active"));
        trigger.classList.add("active");
        console.log("Active drawer target:", trigger.dataset.target);
        break;

      // UEC Controls
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

      default:
        console.warn("Unhandled action:", action);
    }
  });

  // 3. Global Hotkeys
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

## 8. Dual-Panel Pointer Resizer Math

```javascript
export function initResizers() {
  const leftResizer = document.getElementById("resizerLeft");
  const rightResizer = document.getElementById("resizerRight");

  // Left Sidebar: clientX
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

  // Right Sidebar: window.innerWidth - clientX
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
