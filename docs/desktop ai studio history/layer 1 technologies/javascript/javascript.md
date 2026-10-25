# Layer 1 Technology HLD: JavaScript Client State & Streaming Architecture

Yeh document **Desktop AI Studio** ke **Layer 1 (Frontend)** mein use hone wali **Vanilla JavaScript** ki mukammal **High-Level Design (HLD)** architecture, reactive state store aur WebSocket streaming engine ko **Roman Urdu** mein bayan karta hai.

---

## 1. Executive Summary (Client Logic Falsafa)
Desktop AI Studio mein React, Redux, Node ya Webpack jaisi bhaari libraries ke bajaye **Pure Vanilla JavaScript (ES2022)** istemal ki gayi thi.

### Is Architecture ke Fawaid:
1. **Zero Bundling / Compilation Step:** Browser bina kisi npm build ya node_modules ke direct JavaScript ko execute karta tha.
2. **Instant Event Loop:** Memory par koi virtual DOM layer nahi thi, direct real DOM mutations hoti theen jo 10x fast theen.
3. **Micro-task Stream Batching:** Local AI se aane wale tez-tareen text tokens ko `requestAnimationFrame` ke zariye batch kar ke screen freeze hone se bachaya gaya.

---

## 2. Central State Store Architecture (`StudioState`)

Application ka poora state aik centralized object mein rehta tha jisko event listeners update karte the:

```javascript
const StudioState = {
  // Workspace & File System
  workspaceRoot: null,
  fileTree: [],
  openTabs: new Map(),        // tabId -> { path, name, isDirty, scrollPos }
  activeTabId: null,

  // Real-time Hardware Telemetry (Req 20)
  telemetry: {
    gpu: { name: "RTX 2070 Super", active: true },
    vram: { usedGB: 1.8, totalGB: 8.0, percent: 22.5 },
    brain: { model: "Qwen 2.5 Coder 7B", offline: true },
    db: { engine: "pgvector", version: "0.8.7", status: "ready" }
  },

  // Execution & Agent Lifecycle State
  execution: {
    state: "IDLE",            // IDLE | PLANNING | EXECUTING | REVIEW | SUCCESS | FAILED
    currentStep: null,
    checklist: [],
    diffBuffer: null
  },

  // WebSocket Connection State
  socket: {
    instance: null,
    isConnected: false,
    reconnectAttempts: 0
  }
};
```

---

## 3. Char Bunyadi JavaScript HLD Engines

### Engine 1: WebSocket Real-time Protocol Bridge
* **Connection Lifecycle:** App load hote hi `ws://127.0.0.1:8000/ws` par connection establish hota tha. Agar connection drop ho jaye to automatically 1.5s ke interval par reconnect hota tha.
* **Message Routing:** Backend se aane wale JSON payloads ko unke action type ke mutabiq dispatch karta tha:
  * `telemetry.update`: Footer ke 4 counters aur progress bar ko update karna.
  * `agent.chunk`: Naye aane wale AI tokens ko buffer mein daalna.
  * `agent.plan`: Plan checklist ko render karna.
  * `agent.diff`: Diff view trigger karna.
* **Bi-directional Control:** User ke prompts, prompt cancellations aur user approvals ko instant backend par bhejna.

### Engine 2: High-Speed Token Streaming & rAF Scheduler
* **Masla:** Jab local GPU par Qwen 7B model 50-80 tokens per second phenkta hai, to har token par DOM update karne se browser freeze ho jata hai.
* **Hal (rAF Batching):**
  * Naye tokens ko pehle memory queue (`tokenBuffer = []`) mein jama kiya jata tha.
  * `window.requestAnimationFrame()` ke zariye monitor ke 60Hz frame tick par aik hi dafa poora buffer DOM mein append kiya jata tha.
* **Auto-Scroll Engine:** Chat window ko scroll lock rakhta tha; agar developer scroll up kar ke purana code parhay to auto-scroll khud hi pause ho jata tha.

### Engine 3: Unified Execution Card (UEC) State Machine
* **Deterministic Flow:** AI ke tasks ko 5 predictable phases mein chalata tha:
  1. `PLANNING`: Checklists create karna.
  2. `EXECUTING`: Terminal commands aur code modifications run karna.
  3. `REVIEW_DIFF`: User ke samne tabdeelian green/red format mein pesh karna.
  4. `SUCCESS`: Verified code commit karna.
  5. `FAILED / ROLLBACK`: Error aane par purana state restore karna.
* **Action Handlers:** "Accept All Changes", "Reject Diff", aur "Retry" ke user interactions ko handle karna.

### Engine 4: DOM Event Delegation & Global Hotkeys
* **Global Click Delegation:** Har file node par alag listener lagane ke bajaye `#appContainer` par aik hi `click` event listener laga tha jo `e.target.closest('[data-action]')` se click handle karta tha.
* **Interactive Resizers:** Drag karte waqt `pointermove` par clientX measure kar ke `--sidebar-left-w` ki CSS value real-time calculate karta tha.
* **Global Keybindings:**
  * `Ctrl + P`: Command Palette open karna.
  * `Ctrl + S`: Active file buffer save karna.
  * `Ctrl + Enter`: Prompt send karna.
