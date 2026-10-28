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

// Global singletons instantiated and wired
window.store = store;
window.NativeBridge = NativeBridge;
window.wsClient = new WebSocketClient(`ws://${location.host}/ws`);
window.UEC = new UECStateMachine();
window.EditorManager = new EditorManager();
window.DeskAIPorts = initPorts();
window.DeskAITerminal = new TerminalView();
window.DeskAIWelcome = new WelcomeScreenController();
window.ExplorerManager = new ExplorerManager();

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

window.WorkspacePill = new WorkspacePillController(store, NativeBridge);

const channelOutputEl = document.getElementById("channelOutput");
if (channelOutputEl) {
  window.DeskAILogView = new LogView(channelOutputEl);
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
  const vramFill = document.getElementById("teleVramFill");

  if (gpuBadge && data.gpuName) gpuBadge.textContent = "🟢 " + data.gpuName;
  if (vramText && data.vramUsedMB) vramText.textContent = `${(data.vramUsedMB / 1024).toFixed(1)} / ${(data.vramTotalMB / 1024).toFixed(0)} GB`;
  if (ramText && data.ramUsedMB) ramText.textContent = `${(data.ramUsedMB / 1024).toFixed(1)} GB`;
  if (vramFill && data.vramUsedMB && data.vramTotalMB) {
    const pct = Math.min(100, (data.vramUsedMB / data.vramTotalMB) * 100);
    vramFill.style.width = `${pct}%`;
  }
});

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

// Connect WebSocket
window.wsClient.connect();
console.log("[DeskAI] Application bootstrapped successfully.");
