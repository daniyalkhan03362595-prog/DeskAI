# Layer 1 Technology HLD: JavaScript Client State & Streaming Architecture

Yeh document **DeskAI** ke **Layer 1 (Presentation & Client Logic)** mein use hone wali **Vanilla JavaScript (ES2022 Modules)** ki mukammal **High-Level Design (HLD)** architecture, reactive state store, CodeMirror 6 editor integration aur WebSocket streaming engine ko **Roman Urdu** mein bayan karta hai.

---

## 1. Executive Summary (Client Logic Falsafa)
DeskAI mein React, Redux, ya Webpack jaisi bhaari frameworks ke bajaye **Native ES Modules** istemal kiye gaye hain.

### Is Architecture ke Fawaid:
1. **Zero Runtime Bundling Overhead:** Browser bina kisi npm build ya node_modules complexity ke direct JavaScript execute karta hai.
2. **Instant Event Loop:** Memory par koi virtual DOM reconciliation layer nahi hai; direct real DOM mutations 10x tezi se run hoti hain.
3. **rAF Stream Batching:** Local AI se 50-80 tokens/sec aane par bhi `requestAnimationFrame` ke zariye UI 60 FPS smooth rehti hai.
4. **CodeMirror 6 Core:** Hand-rolled contenteditable editor ke bug-prone traps se bachne ke liye CodeMirror 6 ko embedded editor banaya gaya hai.

---

## 2. Central State Store Architecture (`StudioState`)

Application ka runtime state aik deep observable store mein synchronize hota hai:

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

  // Real-time Hardware Telemetry (Realistic GPU & DB info)
  telemetry: {
    gpu: { name: "NVIDIA RTX 2070 Super", active: true },
    vram: { usedGB: 4.7, totalGB: 8.0, percent: 58.7 },
    brain: { model: "Qwen 2.5 Coder 7B", offline: true },
    db: { engine: "SQLite 3 (WAL)", vectorPlugin: "sqlite-vec", status: "ready" }
  },

  // Execution & Agent Lifecycle State
  execution: {
    state: "IDLE",            // IDLE | PLANNING | EXECUTING | REVIEW_DIFF | SUCCESS | FAILED | ROLLBACK | CANCELLED
    currentStep: null,
    checklist: [],
    diffBuffer: null
  },

  // WebSocket Connection & Authentication
  socket: {
    instance: null,
    isConnected: false,
    sessionToken: null,
    lastSeq: 0
  }
};
```

---

## 3. Char Bunyadi JavaScript HLD Engines

### Engine 1: Authenticated WebSocket Client (`ws.js`)
* **Dynamic Connection:** Launch ke waqt window initialization se dynamic port aur secret token receive hota hai (`ws://127.0.0.1:{dynamic_port}/ws?token={token}`).
* **Exponential Backoff Reconnect:** Connection drop hone par instant fixed retry ke bajaye exponential backoff (`Math.min(1000 * 2 ** attempts, 10000)`) use hota hai with ping/pong timeout detection.
* **Resync Protocol:** Reconnect hone par client `lastSeq` bhej kar backend se snapshot state fetch karta hai taake koi data loss na ho.

### Engine 2: High-Speed Token Streaming & rAF Scheduler (`stream.js`)
* **rAF Batching:** Naye aane wale text chunks pehle memory queue mein store hotay hain aur monitor ke 60Hz tick par batch append hotay hain.
* **Sanitized Rendering:** Token chunks ko render karte waqt **DOMPurify** se sanitize kiya jata hai taake XSS script injection ka khatra na rahe.
* **Auto-Scroll Engine:** Chat window scroll-locked rehti hai; agar developer manually scroll up kare to auto-scroll pause ho jata hai.

### Engine 3: Unified Execution Card (UEC) State Machine (`uec.js`)
* **Deterministic Flow with Rollback & Cancel:**
  1. `PLANNING`: Task checklists create karna.
  2. `EXECUTING`: Code modifications aur sandboxed terminal commands chalana.
  3. `REVIEW_DIFF`: User ke samne unified diffs pesh karna.
  4. `SUCCESS`: Approved changes apply karna.
  5. `ROLLBACK`: User rejection ya critical error par workspace ka pre-execution snapshot restore karna.
  6. `CANCELLED`: Running AI stream ya task ko beech mein safely abort karna.

### Engine 4: DOM Event Delegation & Dual-Panel Resizers (`events.js`)
* **Global Action Router:** Single event listener `data-action` attributes ke zariye tamam buttons (`tab-close`, `win-minimize`, `uec-approve`, etc.) ko synchronize handle karta hai.
* **Symmetric Resizer Math:**
  * Left sidebar width: `moveEvent.clientX`
  * Right sidebar width: `window.innerWidth - moveEvent.clientX`
