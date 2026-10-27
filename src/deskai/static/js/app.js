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

if (promptForm && promptTextarea && chatThread) {
  promptForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const prompt = promptTextarea.value.trim();
    if (!prompt) return;

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
    aiAuthor.textContent = "⚡ DeskAI";
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

// Initialize global hotkeys, router & resizers
initGlobalEvents();

const initialDrawerTab = document.querySelector(".drawer-tab.active");
if (initialDrawerTab && initialDrawerTab.getAttribute("data-target") === "terminal") {
  window.DeskAITerminal.init();
}

// Initialize Welcome Screen Overlay
window.DeskAIWelcome.sync();

// Connect WebSocket
window.wsClient.connect();
console.log("[DeskAI] Application bootstrapped successfully.");
