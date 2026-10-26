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

  detectLanguage(filename) {
    if (!filename) return "plaintext";
    const lower = filename.toLowerCase();
    if (lower.endsWith(".py")) return "python";
    if (lower.endsWith(".js") || lower.endsWith(".mjs") || lower.endsWith(".cjs") || lower.endsWith(".json") || lower.endsWith(".ts")) return "javascript";
    if (lower.endsWith(".md") || lower.endsWith(".markdown")) return "markdown";
    return "plaintext";
  }

  createBuffer(name = "untitled.txt", content = "") {
    const id = "tab-" + crypto.randomUUID().slice(0, 8);
    const buffer = {
      id,
      name,
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

    if (this.welcomeScreen) {
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

    if (this.activeTabId === id) {
      const nextTab = this.buffers.keys().next().value;
      if (nextTab) {
        this.selectTab(nextTab);
      } else {
        this.activeTabId = null;
        if (this.welcomeScreen) this.welcomeScreen.style.display = "flex";
      }
    }

    // Recompute dirty status across remaining tabs
    const hasAnyDirty = Array.from(this.buffers.values()).some(b => b.isDirty);
    NativeBridge.setDirtyStatus(hasAnyDirty);

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
    this.tabStrip.replaceChildren();

    for (const [id, buffer] of this.buffers.entries()) {
      const tabEl = document.createElement("div");
      tabEl.className = "editor-tab";
      tabEl.setAttribute("role", "tab");
      tabEl.setAttribute("data-tab-id", id);
      tabEl.setAttribute("aria-selected", id === this.activeTabId ? "true" : "false");
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
