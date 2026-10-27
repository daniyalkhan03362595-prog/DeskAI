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
        const tabIds = Array.from(this.buffers.keys());
        if (tabIds.length === 0) return;
        const currentIndex = tabIds.indexOf(this.activeTabId);

        if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
          e.preventDefault();
          if (tabIds.length <= 1) return;
          let newIndex = e.key === "ArrowRight" ? currentIndex + 1 : currentIndex - 1;
          if (newIndex >= tabIds.length) newIndex = 0;
          if (newIndex < 0) newIndex = tabIds.length - 1;
          const newTabId = tabIds[newIndex];
          this.selectTab(newTabId);
          const activeEl = this.tabStrip.querySelector(`[data-tab-id="${newTabId}"]`);
          if (activeEl) activeEl.focus();
        } else if (e.key === "Home") {
          e.preventDefault();
          const firstId = tabIds[0];
          this.selectTab(firstId);
          const activeEl = this.tabStrip.querySelector(`[data-tab-id="${firstId}"]`);
          if (activeEl) activeEl.focus();
        } else if (e.key === "End") {
          e.preventDefault();
          const lastId = tabIds[tabIds.length - 1];
          this.selectTab(lastId);
          const activeEl = this.tabStrip.querySelector(`[data-tab-id="${lastId}"]`);
          if (activeEl) activeEl.focus();
        } else if (e.key === "Delete") {
          e.preventDefault();
          if (this.activeTabId) {
            this.closeTab(this.activeTabId);
          }
        }
      });
    }

    if (this.editorHost && typeof ResizeObserver !== "undefined") {
      this.resizeObserver = new ResizeObserver(() => {
        if (this.activeTabId && this.buffers.has(this.activeTabId)) {
          const activeBuf = this.buffers.get(this.activeTabId);
          if (activeBuf.view && typeof activeBuf.view.requestMeasure === "function") {
            requestAnimationFrame(() => activeBuf.view.requestMeasure());
          }
        }
      });
      this.resizeObserver.observe(this.editorHost);
    }
  }

  detectFileIcon(filename) {
    if (!filename) return "📄";
    const lower = filename.toLowerCase();
    if (lower.endsWith(".py") || lower.endsWith(".pyw")) return "🐍";
    if (lower.endsWith(".js") || lower.endsWith(".mjs") || lower.endsWith(".cjs")) return "🟨";
    if (lower.endsWith(".ts") || lower.endsWith(".tsx")) return "🔷";
    if (lower.endsWith(".json")) return "📦";
    if (lower.endsWith(".html") || lower.endsWith(".htm")) return "🌐";
    if (lower.endsWith(".css") || lower.endsWith(".scss")) return "🎨";
    if (lower.endsWith(".md") || lower.endsWith(".markdown")) return "📝";
    if (lower.endsWith(".sh") || lower.endsWith(".bash") || lower.endsWith(".zsh")) return "🐚";
    if (lower.endsWith(".sql")) return "🗄️";
    return "📄";
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

      const keyboardTrapHandler = EditorView.domEventHandlers({
        keydown: (e, view) => {
          if (e.key === "Escape") {
            view.contentDOM.blur();
            if (this.tabStrip) {
              const activeTab = this.tabStrip.querySelector(`[data-tab-id="${id}"]`);
              if (activeTab) activeTab.focus();
            }
            return true;
          }
          return false;
        }
      });

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
          }),
          keyboardTrapHandler
        ]
      });

      buffer.state = EditorState.create({
        doc: content,
        extensions
      });

      buffer.container = document.createElement("div");
      buffer.container.className = "editor-view-container";
      buffer.container.id = `editor-container-${id}`;
      buffer.container.setAttribute("data-buffer-id", id);
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
            if (typeof buffer.view.requestMeasure === "function") {
              buffer.view.requestMeasure();
            }
          }
        } else {
          buffer.container.style.display = "none";
        }
      }
    }

    this.renderTabs();

    if (this.tabStrip) {
      const activeEl = this.tabStrip.querySelector(`[data-tab-id="${id}"]`);
      if (activeEl && typeof activeEl.scrollIntoView === "function") {
        activeEl.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
      }
    }
  }

  async closeTab(id, force = false) {
    if (!this.buffers.has(id)) return;
    const buffer = this.buffers.get(id);

    if (!force && buffer.isDirty) {
      const confirmed = confirm(`Save changes to ${buffer.name} before closing?`);
      if (!confirmed) {
        return;
      }
      const saved = await this.saveBuffer(id);
      if (!saved) return;
    }

    if (buffer.view) {
      buffer.view.destroy();
    }
    if (buffer.container && buffer.container.parentElement) {
      buffer.container.parentElement.removeChild(buffer.container);
    }

    this.buffers.delete(id);

    if (store && store.state && store.state.editor) {
      store.state.editor.openTabs = Array.from(this.buffers.values()).map((b) => ({
        id: b.id,
        name: b.name,
        path: b.path,
        isDirty: b.isDirty,
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
    const hasAnyDirty = Array.from(this.buffers.values()).some((b) => b.isDirty);
    NativeBridge.setDirtyStatus(hasAnyDirty);

    this.renderTabs();
  }

  async saveBuffer(id) {
    if (!id || !this.buffers.has(id)) return false;
    const buffer = this.buffers.get(id);
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
      this.markDirty(id, false);
      return true;
    }
    return false;
  }

  async saveActiveBuffer() {
    return await this.saveBuffer(this.activeTabId);
  }

  markDirty(id, isDirty) {
    const buffer = this.buffers.get(id);
    if (buffer) {
      buffer.isDirty = Boolean(isDirty);
      this.renderTabs();

      const hasAnyDirty = Array.from(this.buffers.values()).some((b) => b.isDirty);
      NativeBridge.setDirtyStatus(hasAnyDirty);
    }
  }

  renderTabs() {
    if (!this.tabStrip) return;
    this.tabStrip.replaceChildren();

    for (const [id, buffer] of this.buffers.entries()) {
      const isSelected = id === this.activeTabId;

      const tabEl = document.createElement("div");
      tabEl.className = isSelected ? "editor-tab active" : "editor-tab";
      tabEl.setAttribute("role", "tab");
      tabEl.id = `tab-${id}`;
      tabEl.setAttribute("data-tab-id", id);
      tabEl.setAttribute("aria-selected", isSelected ? "true" : "false");
      tabEl.setAttribute("aria-controls", "editorViewport");
      tabEl.setAttribute("tabindex", isSelected ? "0" : "-1");
      tabEl.setAttribute("data-action", "select-tab");
      tabEl.setAttribute("data-param", id);
      tabEl.setAttribute("title", buffer.path || buffer.name);

      const iconSpan = document.createElement("span");
      iconSpan.className = "tab-icon";
      iconSpan.setAttribute("aria-hidden", "true");
      iconSpan.textContent = this.detectFileIcon(buffer.name);
      tabEl.appendChild(iconSpan);

      const labelSpan = document.createElement("span");
      labelSpan.className = "tab-label";
      labelSpan.textContent = buffer.name;
      tabEl.appendChild(labelSpan);

      if (buffer.isDirty) {
        const dirtySpan = document.createElement("span");
        dirtySpan.className = "tab-dirty-indicator";
        dirtySpan.setAttribute("aria-label", "Unsaved changes");
        dirtySpan.textContent = "●";
        tabEl.appendChild(dirtySpan);
      }

      const closeBtn = document.createElement("button");
      closeBtn.type = "button";
      closeBtn.className = "tab-close-btn";
      closeBtn.setAttribute("data-action", "tab-close");
      closeBtn.setAttribute("data-param", id);
      closeBtn.setAttribute("aria-label", `Close ${buffer.name}`);
      closeBtn.setAttribute("tabindex", "-1");
      closeBtn.textContent = "✕";
      tabEl.appendChild(closeBtn);

      this.tabStrip.appendChild(tabEl);
    }
  }
}
