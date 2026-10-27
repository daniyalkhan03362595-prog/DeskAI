import { store } from "./state.js";
import { NativeBridge } from "./bridge.js";

export class ExplorerManager {
  constructor() {
    this.viewport = document.getElementById("fileTreeViewport");
    this.toolbar = document.getElementById("explorerToolbar");
    this.selectedNode = null;
    this.expandedDirs = new Set();
    this.entries = [];

    this.initToolbarKeyboard();
  }

  initToolbarKeyboard() {
    if (!this.toolbar) return;
    const buttons = Array.from(this.toolbar.querySelectorAll("button.icon-btn"));
    if (buttons.length === 0) return;

    this.toolbar.addEventListener("keydown", (e) => {
      const activeEl = document.activeElement;
      const currentIndex = buttons.indexOf(activeEl);
      if (currentIndex === -1) return;

      if (e.key === "ArrowRight") {
        e.preventDefault();
        const nextIndex = (currentIndex + 1) % buttons.length;
        this.updateToolbarFocus(buttons, nextIndex);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        const prevIndex = (currentIndex - 1 + buttons.length) % buttons.length;
        this.updateToolbarFocus(buttons, prevIndex);
      } else if (e.key === "Home") {
        e.preventDefault();
        this.updateToolbarFocus(buttons, 0);
      } else if (e.key === "End") {
        e.preventDefault();
        this.updateToolbarFocus(buttons, buttons.length - 1);
      }
    });
  }

  updateToolbarFocus(buttons, targetIndex) {
    buttons.forEach((btn, i) => {
      if (i === targetIndex) {
        btn.setAttribute("tabindex", "0");
        btn.focus();
      } else {
        btn.setAttribute("tabindex", "-1");
      }
    });
  }

  async promptNewFile() {
    let targetDir = "";
    if (this.selectedNode && this.selectedNode.isDir) {
      targetDir = this.selectedNode.path;
    } else if (store && store.state && store.state.workspace && store.state.workspace.rootPath) {
      targetDir = store.state.workspace.rootPath;
    }

    const filename = prompt("Enter file name:");
    if (!filename || !filename.trim()) return;

    const trimmed = filename.trim();
    const filePath = targetDir ? `${targetDir.replace(/\/+$/, "")}/${trimmed}` : trimmed;

    const res = await NativeBridge.writeFile(filePath, "");
    if (res && res.status === "ok") {
      await this.refresh();
      if (window.EditorManager && typeof window.EditorManager.openFile === "function") {
        await window.EditorManager.openFile(filePath);
      }
    }
  }

  async promptNewFolder() {
    let targetDir = "";
    if (this.selectedNode && this.selectedNode.isDir) {
      targetDir = this.selectedNode.path;
    } else if (store && store.state && store.state.workspace && store.state.workspace.rootPath) {
      targetDir = store.state.workspace.rootPath;
    }

    const foldername = prompt("Enter folder name:");
    if (!foldername || !foldername.trim()) return;

    const trimmed = foldername.trim();
    const dirPath = targetDir ? `${targetDir.replace(/\/+$/, "")}/${trimmed}` : trimmed;

    const res = await NativeBridge.createDir(dirPath);
    if (res && res.status === "ok") {
      await this.refresh();
    }
  }

  async refresh() {
    const rootPath = store && store.state && store.state.workspace ? store.state.workspace.rootPath : null;
    const res = await NativeBridge.listDir(rootPath);
    if (res && res.status === "ok" && Array.isArray(res.entries)) {
      this.entries = res.entries;
      this.render();
    }
  }

  collapseAll() {
    this.expandedDirs.clear();
    this.render();
  }

  render() {
    if (!this.viewport) return;
    this.viewport.replaceChildren();

    if (!this.entries || this.entries.length === 0) {
      const emptyItem = document.createElement("div");
      emptyItem.className = "tree-empty-message";
      emptyItem.textContent = "No files in workspace";
      this.viewport.appendChild(emptyItem);
      return;
    }

    for (const entry of this.entries) {
      const itemEl = document.createElement("div");
      itemEl.className = "tree-item";
      itemEl.setAttribute("role", "treeitem");
      itemEl.setAttribute("data-path", entry.path);
      itemEl.setAttribute("data-is-dir", entry.is_dir ? "true" : "false");
      itemEl.setAttribute("tabindex", "-1");

      const iconSpan = document.createElement("span");
      iconSpan.className = "tree-icon";
      iconSpan.setAttribute("aria-hidden", "true");
      iconSpan.textContent = entry.is_dir ? "📁" : "📄";
      itemEl.appendChild(iconSpan);

      const labelSpan = document.createElement("span");
      labelSpan.className = "tree-label";
      labelSpan.textContent = entry.name;
      itemEl.appendChild(labelSpan);

      this.viewport.appendChild(itemEl);
    }
  }
}
