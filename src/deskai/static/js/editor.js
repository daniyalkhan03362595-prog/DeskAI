import { store } from "./state.js";
import { NativeBridge } from "./bridge.js";
import { createSvgIcon } from "./icons.js";
import { detectFileIcon as resolveFileIcon } from "./explorer/tree.js";

export class EditorManager {
  constructor() {
    this.buffers = new Map();
    this.pathToId = new Map();
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

  normalizePath(filePath) {
    if (!filePath || typeof filePath !== "string") return null;
    let normalized = filePath.replace(/\\/g, "/");
    while (normalized.length > 1 && normalized.endsWith("/")) {
      normalized = normalized.slice(0, -1);
    }
    return normalized;
  }

  detectFileIcon(filename) {
    return resolveFileIcon(filename, false);
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
    const normalizedPath = this.normalizePath(path);
    if (normalizedPath && this.pathToId.has(normalizedPath)) {
      const existingId = this.pathToId.get(normalizedPath);
      this.selectTab(existingId);
      return existingId;
    }

    const id = "tab-" + crypto.randomUUID().slice(0, 8);
    const buffer = {
      id,
      name,
      path: normalizedPath,
      content: String(content ?? ""),
      isDirty: false,
      mtime: Date.now(),
      language: this.detectLanguage(name),
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
        doc: buffer.content,
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
    if (normalizedPath) {
      this.pathToId.set(normalizedPath, id);
    }

    this.syncStore();
    this.renderTabs();
    this.selectTab(id);
    return id;
  }

  async openFile(filePath) {
    if (!filePath) return null;
    const normalizedPath = this.normalizePath(filePath);

    if (this.pathToId.has(normalizedPath)) {
      const existingId = this.pathToId.get(normalizedPath);
      this.selectTab(existingId);
      return existingId;
    }

    try {
      const res = await NativeBridge.readFile(filePath);
      if (!res || res.status !== "ok") {
        console.error(`Failed to read file: ${filePath}`, res ? res.error : "Unknown error");
        return null;
      }

      const filename = filePath.split("/").pop().split("\\").pop();
      return this.createBuffer(filename, res.content, filePath);
    } catch (err) {
      console.error(`Exception opening file: ${filePath}`, err);
      return null;
    }
  }

  selectTab(id) {
    if (!this.buffers.has(id)) return;
    this.activeTabId = id;
    this.syncStore();

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
    if (!this.buffers.has(id)) return false;
    const buffer = this.buffers.get(id);

    if (!force && buffer.isDirty) {
      const confirmed = confirm(`Save changes to ${buffer.name} before closing?`);
      if (!confirmed) {
        return false;
      }
      const saved = await this.saveBuffer(id);
      if (!saved) return false;
    }

    if (buffer.view) {
      buffer.view.destroy();
    }
    if (buffer.container && buffer.container.parentElement) {
      buffer.container.parentElement.removeChild(buffer.container);
    }

    if (buffer.path) {
      this.pathToId.delete(buffer.path);
    }
    this.buffers.delete(id);
    this.syncStore();

    if (this.activeTabId === id) {
      const remainingIds = Array.from(this.buffers.keys());
      if (remainingIds.length > 0) {
        this.selectTab(remainingIds[remainingIds.length - 1]);
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

    this.notifyNativeDirty();
    this.renderTabs();
    return true;
  }

  async closeAllTabs(force = false) {
    const ids = Array.from(this.buffers.keys());
    for (const id of ids) {
      const closed = await this.closeTab(id, force);
      if (!closed && !force) {
        return false;
      }
    }
    return true;
  }

  async saveBuffer(id) {
    if (!id || !this.buffers.has(id)) return false;
    const buffer = this.buffers.get(id);

    if (!buffer.path) {
      return await this.saveBufferAs(id);
    }

    try {
      const writeRes = await NativeBridge.writeFile(buffer.path, buffer.content);
      if (writeRes && writeRes.status === "ok") {
        buffer.mtime = Date.now();
        this.markDirty(id, false);
        return true;
      }
      return false;
    } catch (err) {
      console.error(`Exception saving buffer ${id}:`, err);
      return false;
    }
  }

  async saveBufferAs(id) {
    if (!id || !this.buffers.has(id)) return false;
    const buffer = this.buffers.get(id);

    try {
      const res = await NativeBridge.saveFileDialog(buffer.name);
      if (res && res.status === "ok" && res.path) {
        const oldNormalizedPath = buffer.path;
        const newNormalizedPath = this.normalizePath(res.path);

        if (oldNormalizedPath) {
          this.pathToId.delete(oldNormalizedPath);
        }
        this.pathToId.set(newNormalizedPath, id);

        buffer.path = newNormalizedPath;
        buffer.name = res.path.split("/").pop().split("\\").pop();
        buffer.language = this.detectLanguage(buffer.name);

        const writeRes = await NativeBridge.writeFile(newNormalizedPath, buffer.content);
        if (writeRes && writeRes.status === "ok") {
          buffer.mtime = Date.now();
          this.markDirty(id, false);
          this.renderTabs();
          this.syncStore();
          return true;
        }
      }
      return false;
    } catch (err) {
      console.error(`Exception during saveBufferAs for ${id}:`, err);
      return false;
    }
  }

  async saveActiveBuffer() {
    return await this.saveBuffer(this.activeTabId);
  }

  async revertBuffer(id) {
    if (!id || !this.buffers.has(id)) return false;
    const buffer = this.buffers.get(id);
    if (!buffer.path) return false;

    try {
      const res = await NativeBridge.readFile(buffer.path);
      if (res && res.status === "ok") {
        buffer.content = res.content;
        buffer.mtime = Date.now();

        if (buffer.view && buffer.view.state) {
          buffer.view.dispatch({
            changes: { from: 0, to: buffer.view.state.doc.length, insert: buffer.content }
          });
        }

        this.markDirty(id, false);
        return true;
      }
      return false;
    } catch (err) {
      console.error(`Exception reverting buffer ${id}:`, err);
      return false;
    }
  }

  markDirty(id, isDirty) {
    const buffer = this.buffers.get(id);
    if (buffer) {
      buffer.isDirty = Boolean(isDirty);
      this.renderTabs();
      this.syncStore();
      this.notifyNativeDirty();
    }
  }

  notifyNativeDirty() {
    const hasAnyDirty = Array.from(this.buffers.values()).some((b) => b.isDirty);
    NativeBridge.setDirtyStatus(hasAnyDirty);
  }

  syncStore() {
    if (store && store.state && store.state.editor) {
      store.state.editor.activeTabId = this.activeTabId;
      store.state.editor.openTabs = Array.from(this.buffers.values()).map((b) => ({
        id: b.id,
        name: b.name,
        path: b.path,
        isDirty: b.isDirty
      }));
    }
  }

  renderTabs() {
    if (!this.tabStrip) return;
    this.tabStrip.replaceChildren();

    if (this.buffers.size === 0) {
      const emptyLabel = document.createElement("span");
      emptyLabel.className = "tab-strip-empty-label";
      emptyLabel.id = "tabStripEmptyLabel";
      emptyLabel.textContent = "No files open";
      this.tabStrip.appendChild(emptyLabel);
      return;
    }

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
      const iconName = this.detectFileIcon(buffer.name);
      iconSpan.setAttribute("data-icon", iconName);
      iconSpan.appendChild(createSvgIcon(iconName, 14, "deskai-svg-icon tab-svg-icon"));
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
      closeBtn.appendChild(createSvgIcon("close", 12));
      tabEl.appendChild(closeBtn);

      this.tabStrip.appendChild(tabEl);
    }
  }
}
