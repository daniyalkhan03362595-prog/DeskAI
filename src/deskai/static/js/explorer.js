/**
 * File Explorer Controller Module.
 * Integrates Tree View rendering, inline editing, and Context Menu actions.
 */
import { store } from "./state.js";
import { NativeBridge } from "./bridge.js";
import { createSvgIcon } from "./icons.js";
import { detectFileIcon, initToolbarKeyboard, initTreeKeyboard, renderTreeNodes } from "./explorer/tree.js";
import { ContextMenuManager } from "./explorer/contextmenu.js";

export { detectFileIcon };

export class ExplorerManager {
  constructor() {
    this.viewport = document.getElementById("fileTreeViewport");
    this.toolbar = document.getElementById("explorerToolbar");
    this.selectedNode = null;
    this.expandedDirs = new Set();
    this.dirChildren = new Map();
    this.entries = [];
    this.contextMenu = document.getElementById("treeContextMenu");

    initToolbarKeyboard(this.toolbar);
    this.initKeyboardAndClicks();
    this.contextMenuManager = new ContextMenuManager(this.viewport, this.contextMenu, {
      selectNode: (nodeEl) => this.selectNode(nodeEl),
      getSelectedNode: () => this.selectedNode,
      executeContextAction: (action, target) => this.handleContextAction(action, target)
    });

    this.setupWorkspaceSubscription();

    const initialRoot = store && store.state && store.state.workspace ? store.state.workspace.rootPath : null;
    if (initialRoot) {
      this.refresh();
    } else {
      this.render();
    }
  }

  detectFileIcon(filename, isDir) {
    return detectFileIcon(filename, isDir);
  }

  setupWorkspaceSubscription() {
    if (store && typeof store.subscribe === "function") {
      store.subscribe("workspace.rootPath", async (newPath) => {
        if (newPath) {
          await NativeBridge.setWorkspaceRoot(newPath);
          await this.refresh();
        } else {
          this.entries = [];
          this.render();
        }
      });
    }
  }

  initKeyboardAndClicks() {
    initTreeKeyboard(this.viewport, {
      focusNode: (nodeEl) => this.focusNode(nodeEl),
      selectNode: (nodeEl) => this.selectNode(nodeEl),
      activateNode: (nodeEl) => this.activateNode(nodeEl),
      toggleFolder: (path, expand) => this.toggleFolder(path, expand),
      startInlineRename: (nodeEl) => this.startInlineRename(nodeEl),
      showContextMenu: (x, y, target) => this.showContextMenu(x, y, target),
      getSelectedNode: () => this.selectedNode
    });

    if (this.viewport) {
      this.viewport.addEventListener("click", async (e) => {
        const itemEl = e.target.closest(".tree-item");
        if (!itemEl) return;
        await this.activateNode(itemEl);
      });
    }
  }

  showContextMenu(x, y, targetNode) {
    this.contextTarget = targetNode;
    if (this.contextMenuManager) {
      this.contextMenuManager.show(x, y, targetNode);
    }
  }

  hideContextMenu() {
    this.contextTarget = null;
    if (this.contextMenuManager) {
      this.contextMenuManager.hide();
    }
  }

  async handleContextAction(action, target) {
    const targetNode =
      target || this.contextTarget || (this.contextMenuManager ? this.contextMenuManager.contextTarget : null);
    if (!targetNode) return;
    target = targetNode;

    switch (action) {
      case "ctx-new-file":
        await this.promptNewFile();
        break;

      case "ctx-new-folder":
        await this.promptNewFolder();
        break;

      case "ctx-rename": {
        const nodeEl = this.viewport.querySelector(`[data-path="${target.path}"]`);
        if (nodeEl) this.startInlineRename(nodeEl);
        break;
      }

      case "ctx-delete":
        await this.deleteNode(target);
        break;

      case "ctx-copy-path":
        if (navigator.clipboard) {
          await navigator.clipboard.writeText(target.path);
        }
        break;

      case "ctx-copy-relative-path": {
        const root = store && store.state && store.state.workspace ? store.state.workspace.rootPath : "";
        let relPath = target.path;
        if (root && relPath.startsWith(root)) {
          relPath = relPath.substring(root.length).replace(/^\/+/, "");
        }
        if (navigator.clipboard) {
          await navigator.clipboard.writeText(relPath);
        }
        break;
      }
    }
  }

  async deleteNode(target) {
    const isDir = target.isDir;
    const confirmed = confirm(`Are you sure you want to delete ${target.name || "this item"}?`);
    if (!confirmed) return;

    const res = await NativeBridge.deletePath(target.path);
    if (res && res.status === "ok") {
      if (!isDir && window.EditorManager && window.EditorManager.buffers) {
        for (const [id, buf] of window.EditorManager.buffers.entries()) {
          if (buf.path === target.path) {
            await window.EditorManager.closeTab(id, true);
          }
        }
      }
      await this.refresh();
    } else {
      alert(`Delete failed: ${res ? res.message : "Unknown error"}`);
    }
  }

  focusNode(nodeEl) {
    if (!nodeEl) return;
    const allItems = this.viewport.querySelectorAll(".tree-item");
    allItems.forEach((el) => el.setAttribute("tabindex", "-1"));
    nodeEl.setAttribute("tabindex", "0");
    nodeEl.focus();
    this.selectNode(nodeEl);
  }

  selectNode(nodeEl) {
    if (!nodeEl) return;
    const allItems = this.viewport.querySelectorAll(".tree-item");
    allItems.forEach((el) => el.classList.remove("active"));
    nodeEl.classList.add("active");
    this.selectedNode = {
      path: nodeEl.getAttribute("data-path"),
      isDir: nodeEl.getAttribute("data-is-dir") === "true",
      name: nodeEl.querySelector(".tree-label") ? nodeEl.querySelector(".tree-label").textContent : ""
    };
  }

  async activateNode(nodeEl) {
    this.selectNode(nodeEl);
    const isDir = nodeEl.getAttribute("data-is-dir") === "true";
    const path = nodeEl.getAttribute("data-path");
    if (isDir) {
      const isExpanded = nodeEl.getAttribute("aria-expanded") === "true";
      await this.toggleFolder(path, !isExpanded);
    } else {
      if (window.EditorManager && typeof window.EditorManager.openFile === "function") {
        await window.EditorManager.openFile(path);
      }
    }
  }

  async toggleFolder(dirPath, expand) {
    const shouldExpand = expand !== undefined ? expand : !this.expandedDirs.has(dirPath);
    if (shouldExpand) {
      this.expandedDirs.add(dirPath);
      if (!this.dirChildren.has(dirPath)) {
        const res = await NativeBridge.listDir(dirPath);
        if (res && res.status === "ok" && Array.isArray(res.entries)) {
          this.dirChildren.set(dirPath, res.entries);
        } else {
          this.dirChildren.set(dirPath, []);
        }
      }
    } else {
      this.expandedDirs.delete(dirPath);
    }
    this.render();
    if (this.selectedNode) {
      const match = this.viewport.querySelector(`[data-path="${this.selectedNode.path}"]`);
      if (match) this.focusNode(match);
    }
  }

  startInlineRename(nodeEl) {
    if (!nodeEl || nodeEl.classList.contains("is-renaming")) return;

    const labelEl = nodeEl.querySelector(".tree-label");
    if (!labelEl) return;

    const oldName = labelEl.textContent;
    const oldPath = nodeEl.getAttribute("data-path");
    const isDir = nodeEl.getAttribute("data-is-dir") === "true";

    nodeEl.classList.add("is-renaming");
    labelEl.style.display = "none";

    const inputEl = document.createElement("input");
    inputEl.type = "text";
    inputEl.className = "tree-rename-input";
    inputEl.value = oldName;
    inputEl.setAttribute("aria-label", `Rename ${oldName}`);

    let committed = false;
    let cancelled = false;

    const commit = async () => {
      if (committed || cancelled) return;
      committed = true;
      const newName = inputEl.value.trim();

      if (!newName || newName === oldName) {
        cancel();
        return;
      }

      const parentDir = oldPath.includes("/") ? oldPath.substring(0, oldPath.lastIndexOf("/")) : "";
      const newPath = parentDir ? `${parentDir}/${newName}` : newName;

      const res = await NativeBridge.renamePath(oldPath, newPath);
      if (res && res.status === "ok") {
        if (!isDir && window.EditorManager && window.EditorManager.buffers) {
          for (const [id, buf] of window.EditorManager.buffers.entries()) {
            if (buf.path === oldPath) {
              buf.path = newPath;
              buf.name = newName;
              buf.language = window.EditorManager.detectLanguage(newName);
              if (window.EditorManager.pathToId) {
                window.EditorManager.pathToId.delete(oldPath);
                window.EditorManager.pathToId.set(newPath, id);
              }
              window.EditorManager.renderTabs();
              window.EditorManager.syncStore();
            }
          }
        }
        await this.refresh();
      } else {
        const errorMsg = res && res.message ? res.message : `Failed to rename ${oldName}`;
        this.showToast(errorMsg, "error");
        this.announce(errorMsg);
        cancel();
      }
    };

    const cancel = () => {
      if (committed || cancelled) return;
      cancelled = true;
      if (inputEl.parentElement) {
        inputEl.parentElement.removeChild(inputEl);
      }
      labelEl.style.display = "";
      nodeEl.classList.remove("is-renaming");
      nodeEl.focus();
    };

    inputEl.addEventListener("keydown", async (e) => {
      e.stopPropagation();
      if (e.key === "Enter") {
        e.preventDefault();
        await commit();
      } else if (e.key === "Escape") {
        e.preventDefault();
        cancel();
      }
    });

    inputEl.addEventListener("blur", async () => {
      await commit();
    });

    nodeEl.appendChild(inputEl);
    inputEl.focus();
    const dotIndex = oldName.lastIndexOf(".");
    if (dotIndex > 0 && !isDir) {
      inputEl.setSelectionRange(0, dotIndex);
    } else {
      inputEl.select();
    }
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
      if (targetDir && this.dirChildren.has(targetDir)) {
        this.dirChildren.delete(targetDir);
      }
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
      if (targetDir && this.dirChildren.has(targetDir)) {
        this.dirChildren.delete(targetDir);
      }
      await this.refresh();
    }
  }

  async refresh() {
    const currentScrollTop = this.viewport ? this.viewport.scrollTop : 0;
    const rootPath = store && store.state && store.state.workspace ? store.state.workspace.rootPath : null;

    const res = await NativeBridge.listDir(rootPath);
    if (res && res.status === "ok" && Array.isArray(res.entries)) {
      this.entries = res.entries;
      this.render();
      if (this.viewport) {
        this.viewport.scrollTop = currentScrollTop;
      }
    } else {
      this.entries = [];
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
      const emptyContainer = document.createElement("div");
      emptyContainer.className = "tree-empty-message";
      emptyContainer.id = "treeEmptyMessage";

      const emptyIcon = document.createElement("span");
      emptyIcon.className = "empty-icon";
      emptyIcon.setAttribute("aria-hidden", "true");
      emptyIcon.appendChild(createSvgIcon("folder", 32));
      emptyContainer.appendChild(emptyIcon);

      const emptyTitle = document.createElement("h3");
      emptyTitle.className = "empty-title";
      emptyTitle.textContent = "No folder open";
      emptyContainer.appendChild(emptyTitle);

      const emptyDesc = document.createElement("p");
      emptyDesc.className = "empty-desc";
      emptyDesc.textContent = "Open a local project directory to browse files, run tests, and build with DeskAI.";
      emptyContainer.appendChild(emptyDesc);

      const actionBtn = document.createElement("button");
      actionBtn.type = "button";
      actionBtn.className = "empty-action-btn welcome-btn secondary";
      actionBtn.setAttribute("data-action", "open-folder-dialog");
      actionBtn.setAttribute("aria-label", "Open Project Folder (Ctrl+O)");
      actionBtn.textContent = "Open Folder";

      const btnKey = document.createElement("span");
      btnKey.className = "welcome-btn-shortcut";
      btnKey.textContent = "Ctrl+O";

      emptyContainer.appendChild(actionBtn);
      emptyContainer.appendChild(btnKey);

      this.viewport.appendChild(emptyContainer);
      return;
    }

    renderTreeNodes(this.entries, this.viewport, 1, {
      expandedDirs: this.expandedDirs,
      selectedNode: this.selectedNode,
      dirChildren: this.dirChildren
    });
  }

  showToast(message, type = "info", duration = 3000) {
    const rack = document.getElementById("toastRack");
    if (!rack) return;

    const toast = document.createElement("div");
    toast.className = `toast-item toast-${type}`;

    const textSpan = document.createElement("span");
    textSpan.textContent = message;
    toast.appendChild(textSpan);

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "toast-dismiss-btn";
    closeBtn.setAttribute("aria-label", "Dismiss notification");
    closeBtn.textContent = "✕";
    closeBtn.addEventListener("click", () => {
      if (toast.parentNode === rack) rack.removeChild(toast);
    });
    toast.appendChild(closeBtn);

    rack.appendChild(toast);

    setTimeout(() => {
      if (toast.parentNode === rack) {
        toast.style.opacity = "0";
        setTimeout(() => {
          if (toast.parentNode === rack) rack.removeChild(toast);
        }, 300);
      }
    }, duration);
  }

  announce(message) {
    const announcer = document.getElementById("screenReaderAnnouncer");
    if (announcer) {
      announcer.textContent = message;
    }
  }
}
