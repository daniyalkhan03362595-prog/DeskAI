import { store } from "./state.js";
import { NativeBridge } from "./bridge.js";

export class EditorManager {
  constructor() {
    this.buffers = new Map();
    this.activeTabId = null;
    this.tabStrip = document.getElementById("editorTabStrip");
    this.welcomeScreen = document.getElementById("welcomeScreen");
    this.editorHost = document.getElementById("codeEditorHost");

    if (this.tabStrip) {
      this.tabStrip.setAttribute("role", "tablist");
      this.tabStrip.addEventListener("keydown", (e) => {
        if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
          e.preventDefault();
          const tabIds = Array.from(this.buffers.keys());
          if (tabIds.length <= 1) return;
          const currentIndex = tabIds.indexOf(this.activeTabId);
          let newIndex = e.key === "ArrowRight" ? currentIndex + 1 : currentIndex - 1;
          if (newIndex >= tabIds.length) newIndex = 0;
          if (newIndex < 0) newIndex = tabIds.length - 1;
          const newTabId = tabIds[newIndex];
          this.selectTab(newTabId);
          const activeEl = this.tabStrip.querySelector(`[data-tab-id="${newTabId}"]`);
          if (activeEl) activeEl.focus();
        }
      });
    }
  }

  detectLanguage(filename) {
    if (!filename) return "plaintext";
    const lower = filename.toLowerCase();
    if (lower.endsWith(".py")) return "python";
    if (lower.endsWith(".js") || lower.endsWith(".mjs") || lower.endsWith(".cjs") || lower.endsWith(".json") || lower.endsWith(".ts")) return "javascript";
    if (lower.endsWith(".md") || lower.endsWith(".markdown")) return "markdown";
    return "plaintext";
  }

  createBuffer(name = "untitled.txt", content = "", path = null) {
    const id = "tab-" + crypto.randomUUID().slice(0, 8);
    const buffer = {
      id,
      name,
      path: path || null,
      content,
      isDirty: false,
      state: null,
      view: null,
      container: null
    };

    if (typeof window !== "undefined" && window.CodeMirror && window.CodeMirror.EditorState) {
      const { EditorState, EditorView, createBasicExtensions } = window.CodeMirror;
      const extensions = createBasicExtensions({
        language: this.detectLanguage(name),
        extensions: [
          EditorView.updateListener.of((update) => {
            if (update.docChanged) {
              buffer.content = update.state.doc.toString();
              if (!buffer.isDirty) {
                this.markDirty(id, true);
              }
            }
          })
        ]
      });

      buffer.state = EditorState.create({
        doc: content,
        extensions
      });

      buffer.container = document.createElement("div");
      buffer.container.className = "editor-view-container";
      buffer.container.style.width = "100%";
      buffer.container.style.height = "100%";
      buffer.container.style.display = "none";

      buffer.view = new EditorView({
        state: buffer.state,
        parent: buffer.container
      });

      if (this.editorHost) {
        this.editorHost.appendChild(buffer.container);
      }
    }

    this.buffers.set(id, buffer);
    if (store && store.state && store.state.editor) {
      store.state.editor.openTabs = Array.from(this.buffers.values()).map(b => ({
        id: b.id,
        name: b.name,
        path: b.path,
        isDirty: b.isDirty
      }));
    }
    this.renderTabs();
    this.selectTab(id);
    return id;
  }

  selectTab(id) {
    if (!this.buffers.has(id)) return;
    this.activeTabId = id;
    if (store && store.state && store.state.editor) {
      store.state.editor.activeTabId = id;
    }

    if (window.DeskAIWelcome) {
      window.DeskAIWelcome.sync();
    } else if (this.welcomeScreen) {
      this.welcomeScreen.style.display = "none";
    }

    for (const [bufId, buffer] of this.buffers.entries()) {
      if (buffer.container) {
        if (bufId === id) {
          buffer.container.style.display = "block";
          if (this.editorHost && buffer.container.parentElement !== this.editorHost) {
            this.editorHost.appendChild(buffer.container);
          }
          if (buffer.view) {
            buffer.view.focus();
          }
        } else {
          buffer.container.style.display = "none";
        }
      }
    }

    this.renderTabs();
  }

  closeTab(id) {
    if (!this.buffers.has(id)) return;
    const buffer = this.buffers.get(id);

    if (buffer.view) {
      buffer.view.destroy();
    }
    if (buffer.container && buffer.container.parentElement) {
      buffer.container.parentElement.removeChild(buffer.container);
    }

    this.buffers.delete(id);

    if (store && store.state && store.state.editor) {
      store.state.editor.openTabs = Array.from(this.buffers.values()).map(b => ({
        id: b.id,
        name: b.name,
        path: b.path,
        isDirty: b.isDirty
      }));
    }

    if (this.activeTabId === id) {
      const nextTab = this.buffers.keys().next().value;
      if (nextTab) {
        this.selectTab(nextTab);
      } else {
        this.activeTabId = null;
        if (window.DeskAIWelcome) {
          window.DeskAIWelcome.sync();
          window.DeskAIWelcome.focusPrimary();
        } else if (this.welcomeScreen) {
          this.welcomeScreen.style.display = "flex";
        }
      }
    }

    // Recompute dirty status across remaining tabs
    const hasAnyDirty = Array.from(this.buffers.values()).some(b => b.isDirty);
    NativeBridge.setDirtyStatus(hasAnyDirty);

    this.renderTabs();
  }

  async saveActiveBuffer() {
    if (!this.activeTabId || !this.buffers.has(this.activeTabId)) return false;
    const buffer = this.buffers.get(this.activeTabId);
    let filePath = buffer.path;
    if (!filePath) {
      const res = await NativeBridge.saveFileDialog(buffer.name);
      if (res && res.status === "ok" && res.path) {
        filePath = res.path;
        buffer.path = filePath;
        buffer.name = filePath.split("/").pop().split("\\").pop();
      } else {
        return false;
      }
    }
    const writeRes = await NativeBridge.writeFile(filePath, buffer.content);
    if (writeRes && writeRes.status === "ok") {
      this.markDirty(this.activeTabId, false);
      return true;
    }
    return false;
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
    this.tabStrip.replaceChildren();

    for (const [id, buffer] of this.buffers.entries()) {
      const tabEl = document.createElement("div");
      tabEl.className = "editor-tab";
      tabEl.setAttribute("role", "tab");
      tabEl.setAttribute("data-tab-id", id);
      tabEl.setAttribute("aria-selected", id === this.activeTabId ? "true" : "false");
      tabEl.setAttribute("aria-controls", "editorViewport");
      tabEl.setAttribute("tabindex", id === this.activeTabId ? "0" : "-1");
      tabEl.setAttribute("data-action", "select-tab");
      tabEl.setAttribute("data-param", id);

      const iconSpan = document.createElement("span");
      iconSpan.className = "tab-icon";
      iconSpan.textContent = "📄";
      tabEl.appendChild(iconSpan);

      const labelSpan = document.createElement("span");
      labelSpan.className = "tab-label";
      labelSpan.textContent = buffer.name;
      tabEl.appendChild(labelSpan);

      if (buffer.isDirty) {
        const dirtySpan = document.createElement("span");
        dirtySpan.className = "tab-dirty-indicator";
        dirtySpan.textContent = "●";
        tabEl.appendChild(dirtySpan);
      }

      const closeBtn = document.createElement("button");
      closeBtn.className = "tab-close-btn";
      closeBtn.setAttribute("data-action", "tab-close");
      closeBtn.setAttribute("data-param", id);
      closeBtn.setAttribute("aria-label", "Close Tab");
      closeBtn.textContent = "✕";
      tabEl.appendChild(closeBtn);

      this.tabStrip.appendChild(tabEl);
    }
  }
}
