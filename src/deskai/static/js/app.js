import { WebSocketClient } from "./ws.js";
import { UECStateMachine } from "./uec.js";
import { EditorManager } from "./editor.js";
import { store } from "./state.js";
import { initGlobalEvents } from "./events.js";
import { TokenStreamBuffer } from "./stream.js";
import { initPorts } from "./ports.js";
import { TerminalView, LogView } from "./terminal.js";
import { NativeBridge } from "./bridge.js";
import { WelcomeScreenController } from "./welcome.js";
import { ExplorerManager } from "./explorer.js";
import { initTheme } from "./theme.js";
import { initProblems } from "./problems/index.js";
import { editorDiagnostics } from "./problems/editor_decorations.js";
import { OutputManager } from "./output/index.js";

// Global singletons instantiated and wired
const wsClient = new WebSocketClient(`ws://${location.host}/ws`);
const uec = new UECStateMachine();
const editorManager = new EditorManager();
const ports = initPorts();
const terminal = new TerminalView();
const welcome = new WelcomeScreenController();
const explorer = new ExplorerManager();
const problems = initProblems();

export class WorkspacePillController {
  constructor(store, bridge) {
    this.store = store;
    this.bridge = bridge;
    this.pillEl = document.getElementById("headerWorkspacePill");
    this.setupSubscriptions();
    this.sync();
  }

  setupSubscriptions() {
    if (this.store && typeof this.store.subscribe === "function") {
      this.store.subscribe("workspace.rootPath", async (newPath) => {
        this.sync();
        if (newPath) {
          try {
            const res = await this.bridge.getGitBranch(newPath);
            if (res && res.branch && this.store.state.workspace.rootPath === newPath) {
              this.store.state.workspace.branch = res.branch;
            }
          } catch (e) {
            // ignore
          }
        } else {
          this.store.state.workspace.branch = null;
          this.sync();
        }
      });

      this.store.subscribe("workspace.branch", () => {
        this.sync();
      });
    }
  }

  sync() {
    if (!this.pillEl) return;
    const rootPath = this.store.state.workspace.rootPath;
    const branch = this.store.state.workspace.branch;

    if (!rootPath) {
      this.pillEl.textContent = "DeskAI / (no workspace)";
      this.pillEl.title = "No active workspace folder";
      this.pillEl.setAttribute("aria-label", "Workspace: No folder opened");
      this.pillEl.classList.remove("has-workspace");
      return;
    }

    const folderName = rootPath.split("/").pop().split("\\").pop() || rootPath;
    let label;
    if (folderName === "DeskAI") {
      label = branch ? `DeskAI / ${branch}` : "DeskAI";
    } else {
      label = branch ? `DeskAI / ${folderName} / ${branch}` : `DeskAI / ${folderName}`;
    }
    this.pillEl.textContent = label;
    this.pillEl.title = `${rootPath}${branch ? ` (branch: ${branch})` : ""}`;
    this.pillEl.setAttribute("aria-label", `Active workspace: ${folderName}${branch ? `, branch: ${branch}` : ""}`);
    this.pillEl.classList.add("has-workspace");
  }
}

const workspacePill = new WorkspacePillController(store, NativeBridge);

// Unified DeskAI Architecture Namespace
window.DeskAI = {
  store,
  NativeBridge,
  wsClient,
  UEC: uec,
  EditorManager: editorManager,
  Ports: ports,
  Terminal: terminal,
  Welcome: welcome,
  Explorer: explorer,
  WorkspacePill: workspacePill,
};

// Aliases for test runners
window.store = store;
window.NativeBridge = NativeBridge;
window.wsClient = wsClient;
window.UEC = uec;
window.EditorManager = editorManager;
window.DeskAIPorts = ports;
window.DeskAITerminal = terminal;
window.DeskAIWelcome = welcome;
window.ExplorerManager = explorer;
window.DeskAIExplorer = explorer;
window.DeskAIProblems = problems;
window.DeskAIEditorDiagnostics = editorDiagnostics;
window.WorkspacePill = workspacePill;

const channelOutputEl = document.getElementById("channelOutput");
if (channelOutputEl) {
  window.DeskAILogView = new LogView(channelOutputEl);
  const outputPanelEl = document.getElementById("outputPanel");
  if (outputPanelEl) {
    const outputManager = new OutputManager(outputPanelEl, window.DeskAILogView);
    outputManager.start();
  }
}

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
window.wsClient.on("uec.ack", (payload) => {
  if (payload && payload.state) {
    window.UEC.transition(payload.state, payload);
  }
});

// Setup Prompt Input Form
const promptForm = document.getElementById("promptForm");
const promptTextarea = document.getElementById("promptTextarea");
const chatThread = document.getElementById("chatThread");

function renderChatEmptyState() {
  if (!chatThread) return;
  chatThread.replaceChildren();

  const emptyState = document.createElement("div");
  emptyState.className = "chat-empty-state";
  emptyState.id = "chatEmptyState";

  const note = document.createElement("p");
  note.className = "chat-empty-note";
  note.textContent = "DeskAI is ready to analyze code, explain architecture, and suggest fixes.";
  emptyState.appendChild(note);

  const chipsContainer = document.createElement("div");
  chipsContainer.className = "chat-prompt-chips";

  const prompts = [
    "Explain the active file and its architecture",
    "Find potential bugs and propose optimizations",
    "Generate comprehensive unit tests for this module",
  ];

  prompts.forEach((promptText) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chat-prompt-chip";
    chip.textContent = promptText;
    chip.setAttribute("aria-label", `Use prompt: ${promptText}`);
    chip.addEventListener("click", () => {
      if (promptTextarea) {
        promptTextarea.value = promptText;
        promptTextarea.focus();
      }
    });
    chipsContainer.appendChild(chip);
  });

  emptyState.appendChild(chipsContainer);
  chatThread.appendChild(emptyState);
}

if (chatThread) {
  renderChatEmptyState();
}

if (promptForm && promptTextarea && chatThread) {
  promptForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const prompt = promptTextarea.value.trim();
    if (!prompt) return;

    const emptyState = document.getElementById("chatEmptyState");
    if (emptyState) {
      emptyState.remove();
    }

    // Render User Message Bubble safely via DOM construction & textContent
    const userBubble = document.createElement("article");
    userBubble.className = "chat-bubble";
    userBubble.setAttribute("data-role", "user");

    const userHeader = document.createElement("div");
    userHeader.className = "bubble-header";
    const userAuthor = document.createElement("span");
    userAuthor.className = "bubble-author";
    userAuthor.textContent = "User";
    const userTime = document.createElement("time");
    userTime.className = "bubble-time";
    userTime.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    userHeader.appendChild(userAuthor);
    userHeader.appendChild(userTime);

    const userBody = document.createElement("div");
    userBody.className = "bubble-body markdown-surface";
    const userP = document.createElement("p");
    userP.textContent = prompt;
    userBody.appendChild(userP);

    userBubble.appendChild(userHeader);
    userBubble.appendChild(userBody);
    chatThread.appendChild(userBubble);
    promptTextarea.value = "";

    // Render Assistant Response Container safely
    const aiBubble = document.createElement("article");
    aiBubble.className = "chat-bubble";
    aiBubble.setAttribute("data-role", "assistant");

    const aiHeader = document.createElement("div");
    aiHeader.className = "bubble-header";
    const aiAuthor = document.createElement("span");
    aiAuthor.className = "bubble-author";
    aiAuthor.textContent = "DeskAI";
    const aiTime = document.createElement("time");
    aiTime.className = "bubble-time";
    aiTime.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    aiHeader.appendChild(aiAuthor);
    aiHeader.appendChild(aiTime);

    const aiBody = document.createElement("div");
    aiBody.className = "bubble-body markdown-surface stream-target";

    aiBubble.appendChild(aiHeader);
    aiBubble.appendChild(aiBody);
    chatThread.appendChild(aiBubble);
    chatThread.scrollTop = chatThread.scrollHeight;

    const streamTarget = aiBubble.querySelector(".stream-target");
    const streamer = new TokenStreamBuffer(streamTarget);

    // Transition UEC to PLANNING
    window.UEC.transition("PLANNING", { prompt });

    // Send prompt over WebSocket
    window.wsClient.send("agent.prompt", { prompt });

    // Simulating initial ACK response stream
    streamer.append("Analyzing request and planning execution...\n\n");
    setTimeout(() => {
      streamer.append("Task initialized. Reviewing workspace structure.");
      streamer.complete();
    }, 400);
  });
}

// Telemetry Store Subscription
store.subscribe("telemetry", (data) => {
  if (!data) return;
  const gpuBadge = document.getElementById("teleGpuBadge");
  const vramText = document.getElementById("teleVramText");
  const ramText = document.getElementById("teleRamText");
  const vramTrack = document.getElementById("teleVramTrack");
  const vramFill = document.getElementById("teleVramFill");

  if (gpuBadge) {
    while (gpuBadge.firstChild) {
      gpuBadge.removeChild(gpuBadge.firstChild);
    }
    const hasGpu = data.gpuName && data.gpuName !== "--";
    const dot = document.createElement("span");
    dot.className = hasGpu ? "status-dot ready" : "status-dot unknown";
    gpuBadge.appendChild(dot);
    gpuBadge.appendChild(document.createTextNode(" " + (hasGpu ? data.gpuName : "Unavailable")));
    if (hasGpu) {
      gpuBadge.classList.remove("unknown");
      gpuBadge.title = data.gpuName;
    } else {
      gpuBadge.classList.add("unknown");
      gpuBadge.title = "Hardware telemetry unavailable on this host";
    }
  }

  const hasVram = typeof data.vramUsedMB === "number" && !isNaN(data.vramUsedMB) && typeof data.vramTotalMB === "number" && data.vramTotalMB > 0;
  if (vramText) {
    if (hasVram) {
      const usedGb = (data.vramUsedMB / 1024).toFixed(1);
      const totalGb = (data.vramTotalMB / 1024).toFixed(0);
      vramText.textContent = `${usedGb} / ${totalGb} GB`;
      vramText.classList.remove("unknown");
      vramText.removeAttribute("title");
    } else {
      vramText.textContent = "Unavailable";
      vramText.classList.add("unknown");
      vramText.title = "Hardware telemetry unavailable on this host";
    }
  }
  if (vramTrack) {
    if (hasVram) {
      vramTrack.classList.remove("unknown");
      const pct = Math.min(100, (data.vramUsedMB / data.vramTotalMB) * 100);
      vramTrack.setAttribute("aria-valuenow", Math.round(pct).toString());
      if (vramFill) {
        vramFill.classList.remove("unknown");
        vramFill.style.width = `${pct}%`;
      }
    } else {
      vramTrack.classList.add("unknown");
      vramTrack.setAttribute("aria-valuenow", "0");
      if (vramFill) {
        vramFill.classList.add("unknown");
        vramFill.style.width = "0%";
      }
    }
  }

  const hasRam = typeof data.ramUsedMB === "number" && !isNaN(data.ramUsedMB);
  if (ramText) {
    if (hasRam) {
      const usedGb = (data.ramUsedMB / 1024).toFixed(1);
      if (typeof data.ramTotalMB === "number" && data.ramTotalMB > 0) {
        const totalGb = (data.ramTotalMB / 1024).toFixed(0);
        ramText.textContent = `${usedGb} / ${totalGb} GB`;
      } else {
        ramText.textContent = `${usedGb} GB`;
      }
      ramText.classList.remove("unknown");
      ramText.removeAttribute("title");
    } else {
      ramText.textContent = "Unavailable";
      ramText.classList.add("unknown");
      ramText.title = "Hardware telemetry unavailable on this host";
    }
  }
});

// Host Hardware Telemetry Lifecycle Manager
export const DeskAITelemetry = {
  timer: null,
  async sync() {
    if (
      window.pywebview &&
      window.pywebview.api &&
      typeof window.pywebview.api.get_system_telemetry === "function"
    ) {
      try {
        const res = await NativeBridge.getSystemTelemetry();
        if (res && res.status === "ok" && res.telemetry) {
          store.state.telemetry = res.telemetry;
          return res.telemetry;
        }
      } catch (err) {
        console.warn("[Telemetry] Sync error:", err);
      }
    }
    return null;
  },
  startPolling(intervalMs = 5000) {
    this.stopPolling();
    if (!window.pywebview || !window.pywebview.api) return;
    this.sync();
    this.timer = setInterval(() => {
      if (!document.hidden) {
        this.sync();
      }
    }, intervalMs);
  },
  stopPolling() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }
};

window.DeskAITelemetry = DeskAITelemetry;
window.addEventListener("pywebviewready", () => {
  DeskAITelemetry.startPolling(5000);
});
DeskAITelemetry.startPolling(5000);

// Initialize theme, global hotkeys, router & resizers
initTheme();
initGlobalEvents();

const initialDrawerTab = document.querySelector(".drawer-tab.active");
if (initialDrawerTab && initialDrawerTab.getAttribute("data-target") === "terminal") {
  window.DeskAITerminal.init();
}

// Initialize Welcome Screen Overlay
window.DeskAIWelcome.sync();

// Sync initial workspace from backend if set
NativeBridge.getWorkspaceRoot().then(async (res) => {
  if (res && res.path && !store.state.workspace.rootPath) {
    store.state.workspace.rootPath = res.path;
  }
  if (store.state.workspace.rootPath && window.ExplorerManager) {
    await window.ExplorerManager.refresh();
  }
});

// Resync explorer and diagnostics when window gains focus
window.addEventListener("focus", () => {
  const rootPath = store && store.state && store.state.workspace ? store.state.workspace.rootPath : null;
  if (rootPath) {
    if (window.ExplorerManager && typeof window.ExplorerManager.pollWorkspaceChanges === "function") {
      window.ExplorerManager.pollWorkspaceChanges();
    }
    if (window.DeskAIProblems && typeof window.DeskAIProblems.runWorkspace === "function") {
      window.DeskAIProblems.runWorkspace({ silent: true });
    }
  }
});

// Connect WebSocket
window.wsClient.connect();
console.log("[DeskAI] Application bootstrapped successfully.");
