# Layer 1 Technology HLD: JavaScript Client State & Streaming Architecture

Yeh document **DeskAI** ke **Layer 1 (Presentation & Client Logic)** mein use hone wali **Vanilla JavaScript (ES2022 Modules)** ki mukammal **High-Level Design (HLD)** architecture, reactive state store, CodeMirror 6 vendor integration aur WebSocket streaming engine ko **Roman Urdu** mein bayan karta hai.

---

## 1. Executive Summary (Client Logic Falsafa)
DeskAI mein heavy application-level compilation frameworks ke bajaye **Native ES Modules + Pre-bundled Vendor Singletons** approach istemal ki gayi hai.

### Is Architecture ke Fawaid:
1. **Zero App Bundling Overhead:** Application ka apna code bina kisi npm build ya dev server ke direct browser ES modules mein run hota hai.
2. **Deterministic CodeMirror 6 Vendor Bundle:** CodeMirror 6 ke npm modular packages ko single, self-contained vendor file (`static/vendor/codemirror.bundle.js`) mein bundle kar ke version-hash ke sath load kiya jata hai.
3. **Accumulated Token Streaming:** Local AI streaming ke dauran tokens ko accumulate kiya jata hai taake previous frames overwrite na hon aur user scroll position lock rahe.
4. **WeakMap-Cached Reactivity:** Central store reference equality (`===`) aur ancestor path notifications ensure karta hai.

---

## 2. Central State Store Architecture (`StudioState`)

Application ka runtime state observable store mein synchronize hota hai:

```javascript
const StudioState = {
  // Workspace & File System
  workspace: {
    rootPath: null,
    fileTree: [],
    selectedPath: null
  },

  // Editor State (CodeMirror 6 buffers)
  editor: {
    openTabs: [],             // Array of { id, path, name, isDirty }
    activeTabId: null
  },

  // Real-time Host Telemetry (Initialized with truthful neutral defaults, populated dynamically via NativeBridge)
  telemetry: {
    gpuName: "--",
    vramUsedMB: "--",
    vramTotalMB: "--",
    cpuUsagePct: "--",
    ramUsedMB: "--",
    status: "idle"
  },

  // Execution & Agent Lifecycle State
  execution: {
    state: "IDLE",            // IDLE | PLANNING | EXECUTING | REVIEW_DIFF | SUCCESS | FAILED | ROLLBACK | CANCELLED
    currentStep: null,
    checklist: [],
    activeDiff: null
  },

  // WebSocket Connection
  connection: {
    isSocketConnected: false,
    lastSeq: 0
  }
};
```

---

## 3. Char Bunyadi JavaScript HLD Engines

### Engine 1: Gap-Aware WebSocket Client (`ws.js`)
* **Cookie-Based Seamless Authentication:** Launch par receive hone wali session cookie automatically WebSocket upgrade par sath jati hai (WS URL clean rehti hai).
* **Gap Detection & Fatal Codes:** Har packet ka sequence number (`seq`) verify hota hai. Agar gap detect ho to client foran snapshot resync request karta hai. Code 1008 (Auth Failure) aane par reconnect loop foran stop ho jata hai.
* **Safe Queue:** Reconnect ke waqt sirf safe queries queue hoti hain; state mutations (jaise approve plan) stale state mein dobara trigger nahi hotin.

### Engine 2: Accumulated Token Streaming & DOMPurify (`stream.js`)
* **Full Text Accumulation:** Tokens append hone par pichla text wipe nahi hota; full accumulated string maintain hoti hai.
* **Scroll Protection:** User ke manually up-scroll karne par auto-scroll lock khud ba khud pause ho jata hai.
* **XSS Defense:** Har frame par DOMPurify ke strict allowed tags aur URL regex ke mutabiq HTML sanitize hota hai.

### Engine 3: Unified Execution Card (UEC) State Machine (`uec.js`)
* **Finite State Transitions:** `IDLE -> PLANNING -> EXECUTING -> REVIEW_DIFF -> SUCCESS / FAILED / ROLLBACK / CANCELLED`.
* **State-Driven UI Rendering:** Sirf active state ke mutabiq action buttons (Approve, Reject, Cancel, Rollback) render hotay hain.

### Engine 4: DOM Event Delegation & Link Interception (`events.js`)
* **Complete Action Router:** HTML ke tamam `data-action` attributes (`tab-close`, `win-minimize`, `new-file`, `toggle-drawer`, etc.) centrally handle hotay hain.
* **External Link Sandbox:** Web links (`<a href="...">`) ko intercept kar ke PyWebView ke bajaye OS ke default external browser mein open kiya jata hai.
* **Symmetric Resizers:** Left (`clientX`) aur Right (`window.innerWidth - clientX`) panels ka smooth resizing math.
