import { store } from "./state.js";
import { NativeBridge } from "./bridge.js";

export class EditorManager {
  constructor() {
    this.buffers = new Map();
    this.activeTabId = null;
    this.tabStrip = document.getElementById("editorTabStrip");
    this.welcomeScreen = document.getElementById("welcomeScreen");
    this.editorHost = document.getElementById("codeEditorHost");
  }

  createBuffer(name = "untitled.txt", content = "") {
    const id = "tab-" + crypto.randomUUID().slice(0, 8);
    const buffer = { id, name, content, isDirty: false };
    this.buffers.set(id, buffer);
    this.renderTabs();
    this.selectTab(id);
    return id;
  }

  selectTab(id) {
    if (!this.buffers.has(id)) return;
    this.activeTabId = id;
    store.state.editor.activeTabId = id;

    if (this.welcomeScreen) {
      this.welcomeScreen.style.display = "none";
    }

    const buffer = this.buffers.get(id);
    if (this.editorHost) {
      this.editorHost.innerHTML = `<textarea class="editor-textarea" style="width:100%;height:100%;background:transparent;border:none;color:var(--text-primary);font-family:var(--font-mono);font-size:var(--text-sm);padding:var(--space-3);resize:none;outline:none;">${buffer.content}</textarea>`;
      const textarea = this.editorHost.querySelector("textarea");
      textarea.addEventListener("input", (e) => {
        buffer.content = e.target.value;
        this.markDirty(id, true);
      });
    }

    this.renderTabs();
  }

  closeTab(id) {
    if (!this.buffers.has(id)) return;
    this.buffers.delete(id);

    if (this.activeTabId === id) {
      const nextTab = this.buffers.keys().next().value;
      if (nextTab) {
        this.selectTab(nextTab);
      } else {
        this.activeTabId = null;
        if (this.welcomeScreen) this.welcomeScreen.style.display = "flex";
        if (this.editorHost) this.editorHost.innerHTML = "";
        NativeBridge.setDirtyStatus(false);
      }
    }
    this.renderTabs();
  }

  markDirty(id, isDirty) {
    const buffer = this.buffers.get(id);
    if (buffer) {
      buffer.isDirty = Boolean(isDirty);
      this.renderTabs();

      const hasAnyDirty = Array.from(this.buffers.values()).some(b => b.isDirty);
      NativeBridge.setDirtyStatus(hasAnyDirty);
    }
  }

  renderTabs() {
    if (!this.tabStrip) return;
    this.tabStrip.innerHTML = "";

    for (const [id, buffer] of this.buffers.entries()) {
      const tabEl = document.createElement("div");
      tabEl.className = "editor-tab";
      tabEl.setAttribute("role", "tab");
      tabEl.setAttribute("data-tab-id", id);
      tabEl.setAttribute("aria-selected", id === this.activeTabId ? "true" : "false");
      tabEl.setAttribute("data-action", "select-tab");
      tabEl.setAttribute("data-param", id);

      tabEl.innerHTML = `
        <span class="tab-icon">📄</span>
        <span class="tab-label">${buffer.name}</span>
        ${buffer.isDirty ? '<span class="tab-dirty-indicator">●</span>' : ''}
        <button class="tab-close-btn" data-action="tab-close" data-param="${id}" aria-label="Close Tab">✕</button>
      `;

      this.tabStrip.appendChild(tabEl);
    }
  }
}
