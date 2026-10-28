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
        const inlineBtn = e.target.closest(".tree-inline-btn");
        if (inlineBtn) {
          e.stopPropagation();
          e.preventDefault();
          const action = inlineBtn.getAttribute("data-action");
          const targetPath = inlineBtn.getAttribute("data-path");
          const itemEl = inlineBtn.closest(".tree-item");

          if (action === "folder-new-file") {
            await this.toggleFolder(targetPath, true);
            await this.promptNewFile(targetPath);
          } else if (action === "folder-new-folder") {
            await this.toggleFolder(targetPath, true);
            await this.promptNewFolder(targetPath);
          } else if (action === "item-rename") {
            if (itemEl) this.startInlineRename(itemEl);
          } else if (action === "item-delete") {
            if (itemEl) {
              const isDir = itemEl.getAttribute("data-is-dir") === "true";
              const label = itemEl.querySelector(".tree-label");
              const name = label ? label.textContent : "";
              this.startInlineDelete(itemEl, { path: targetPath, isDir, name });
            }
          }
          return;
        }

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
      target ||
      this.contextTarget ||
      (this.contextMenuManager ? this.contextMenuManager.contextTarget : null) ||
      this.selectedNode;
    if (!targetNode) return;
    target = targetNode;

    switch (action) {
      case "ctx-new-file": {
        const targetDir =
          target && target.isDir
            ? target.path
            : target && target.path && target.path.includes("/")
            ? target.path.substring(0, target.path.lastIndexOf("/"))
            : null;
        await this.promptNewFile(targetDir);
        break;
      }

      case "ctx-new-folder": {
        const targetDir =
          target && target.isDir
            ? target.path
            : target && target.path && target.path.includes("/")
            ? target.path.substring(0, target.path.lastIndexOf("/"))
            : null;
        await this.promptNewFolder(targetDir);
        break;
      }

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
    if (!target || !target.path) return;
    const nodeEl = this.viewport ? this.viewport.querySelector(`[data-path="${target.path}"]`) : null;
    if (nodeEl) {
      this.startInlineDelete(nodeEl, target);
      return;
    }

    const isDir = target.isDir;
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
      const errMsg = `Delete failed: ${res ? res.message : "Unknown error"}`;
      this.showToast(errMsg, "error");
      this.announce(errMsg);
    }
  }

  startInlineDelete(nodeEl, target) {
    if (!nodeEl || nodeEl.classList.contains("is-deleting") || nodeEl.classList.contains("is-renaming")) return;

    // Clean up any other active inline deletions in the tree
    const existingDeleting = this.viewport.querySelectorAll(".tree-item.is-deleting");
    existingDeleting.forEach((el) => {
      if (typeof el._cancelDelete === "function") el._cancelDelete();
    });

    const labelEl = nodeEl.querySelector(".tree-label");
    if (!labelEl) return;

    const normalActions = nodeEl.querySelector(".tree-inline-actions");
    if (normalActions) normalActions.style.display = "none";
    labelEl.style.display = "none";
    nodeEl.classList.add("is-deleting");

    const isDir = target ? target.isDir : nodeEl.getAttribute("data-is-dir") === "true";
    const targetPath = target ? target.path : nodeEl.getAttribute("data-path");
    const itemName = target ? target.name : (labelEl.textContent || "this item");

    const confirmContainer = document.createElement("div");
    confirmContainer.className = "tree-delete-confirm-wrapper";
    confirmContainer.style.display = "flex";
    confirmContainer.style.alignItems = "center";
    confirmContainer.style.flex = "1";
    confirmContainer.style.minWidth = "0";

    const confirmText = document.createElement("span");
    confirmText.className = "tree-delete-confirm-text";
    confirmText.textContent = `Delete '${itemName}'?`;
    confirmContainer.appendChild(confirmText);

    const deleteActions = document.createElement("div");
    deleteActions.className = "tree-create-actions tree-delete-actions";

    const confirmBtn = document.createElement("button");
    confirmBtn.type = "button";
    confirmBtn.className = "tree-create-btn tree-delete-confirm tree-create-confirm";
    confirmBtn.setAttribute("data-action", "confirm-delete");
    confirmBtn.setAttribute("title", "Delete (Enter)");
    confirmBtn.setAttribute("aria-label", `Confirm delete ${itemName}`);
    confirmBtn.appendChild(createSvgIcon("check", 13, "deskai-svg-icon"));
    deleteActions.appendChild(confirmBtn);

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "tree-create-btn tree-delete-cancel tree-create-cancel";
    cancelBtn.setAttribute("data-action", "cancel-delete");
    cancelBtn.setAttribute("title", "Cancel (Esc)");
    cancelBtn.setAttribute("aria-label", "Cancel delete");
    cancelBtn.appendChild(createSvgIcon("close", 13, "deskai-svg-icon"));
    deleteActions.appendChild(cancelBtn);

    confirmContainer.appendChild(deleteActions);
    nodeEl.appendChild(confirmContainer);

    let committed = false;
    let cancelled = false;

    const cancel = () => {
      if (committed || cancelled) return;
      cancelled = true;
      if (confirmContainer.parentElement) {
        confirmContainer.parentElement.removeChild(confirmContainer);
      }
      labelEl.style.display = "";
      if (normalActions) normalActions.style.display = "";
      nodeEl.classList.remove("is-deleting");
      delete nodeEl._cancelDelete;
      delete nodeEl._commitDelete;
      nodeEl.focus();
    };

    const commit = async () => {
      if (committed || cancelled) return;
      committed = true;
      delete nodeEl._cancelDelete;
      delete nodeEl._commitDelete;

      const res = await NativeBridge.deletePath(targetPath);
      if (res && res.status === "ok") {
        if (!isDir && window.EditorManager && window.EditorManager.buffers) {
          for (const [id, buf] of window.EditorManager.buffers.entries()) {
            if (buf.path === targetPath) {
              await window.EditorManager.closeTab(id, true);
            }
          }
        }
        await this.refresh();
      } else {
        const errorMsg = res && res.message ? res.message : `Failed to delete ${itemName}`;
        this.showToast(errorMsg, "error");
        this.announce(errorMsg);
        cancel();
      }
    };

    nodeEl._cancelDelete = cancel;
    nodeEl._commitDelete = commit;

    confirmBtn.addEventListener("mousedown", (e) => e.preventDefault());
    cancelBtn.addEventListener("mousedown", (e) => e.preventDefault());

    confirmBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      await commit();
    });

    cancelBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      cancel();
    });

    const keyHandler = async (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        e.stopPropagation();
        nodeEl.removeEventListener("keydown", keyHandler);
        await commit();
      } else if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        nodeEl.removeEventListener("keydown", keyHandler);
        cancel();
      }
    };
    nodeEl.addEventListener("keydown", keyHandler);

    confirmBtn.focus();
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
    if (!nodeEl || nodeEl.classList.contains("is-renaming") || nodeEl.classList.contains("is-deleting")) return;

    const labelEl = nodeEl.querySelector(".tree-label");
    if (!labelEl) return;

    const normalActions = nodeEl.querySelector(".tree-inline-actions");
    if (normalActions) normalActions.style.display = "none";

    const oldName = labelEl.textContent;
    const oldPath = nodeEl.getAttribute("data-path");
    const isDir = nodeEl.getAttribute("data-is-dir") === "true";

    nodeEl.classList.add("is-renaming");
    labelEl.style.display = "none";

    const renameContainer = document.createElement("div");
    renameContainer.className = "tree-rename-wrapper";
    renameContainer.style.display = "flex";
    renameContainer.style.alignItems = "center";
    renameContainer.style.flex = "1";
    renameContainer.style.minWidth = "0";

    const inputEl = document.createElement("input");
    inputEl.type = "text";
    inputEl.className = "tree-rename-input";
    inputEl.value = oldName;
    inputEl.setAttribute("aria-label", `Rename ${oldName}`);
    renameContainer.appendChild(inputEl);

    const renameActions = document.createElement("div");
    renameActions.className = "tree-create-actions tree-rename-actions";

    const confirmBtn = document.createElement("button");
    confirmBtn.type = "button";
    confirmBtn.className = "tree-create-btn tree-create-confirm";
    confirmBtn.setAttribute("data-action", "confirm-rename");
    confirmBtn.setAttribute("title", "Confirm (Enter)");
    confirmBtn.setAttribute("aria-label", "Confirm Rename");
    confirmBtn.appendChild(createSvgIcon("check", 13, "deskai-svg-icon"));
    renameActions.appendChild(confirmBtn);

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "tree-create-btn tree-create-cancel";
    cancelBtn.setAttribute("data-action", "cancel-rename");
    cancelBtn.setAttribute("title", "Cancel (Esc)");
    cancelBtn.setAttribute("aria-label", "Cancel Rename");
    cancelBtn.appendChild(createSvgIcon("close", 13, "deskai-svg-icon"));
    renameActions.appendChild(cancelBtn);

    renameContainer.appendChild(renameActions);
    nodeEl.appendChild(renameContainer);

    let committed = false;
    let cancelled = false;

    const cancel = () => {
      if (committed || cancelled) return;
      cancelled = true;
      if (renameContainer.parentElement) {
        renameContainer.parentElement.removeChild(renameContainer);
      }
      labelEl.style.display = "";
      if (normalActions) normalActions.style.display = "";
      nodeEl.classList.remove("is-renaming");
      nodeEl.focus();
    };

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

    confirmBtn.addEventListener("mousedown", (e) => e.preventDefault());
    cancelBtn.addEventListener("mousedown", (e) => e.preventDefault());

    confirmBtn.addEventListener("click", async (e) => {
      e.stopPropagation();
      await commit();
    });

    cancelBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      cancel();
    });

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
      setTimeout(async () => {
        if (!committed && !cancelled) {
          await commit();
        }
      }, 150);
    });

    inputEl.focus();
    const dotIndex = oldName.lastIndexOf(".");
    if (dotIndex > 0 && !isDir) {
      inputEl.setSelectionRange(0, dotIndex);
    } else {
      inputEl.select();
    }
  }

  async promptNewFile(targetDirParam = null) {
    return this.startInlineCreate({ type: "file", targetDirParam });
  }

  async promptNewFolder(targetDirParam = null) {
    return this.startInlineCreate({ type: "folder", targetDirParam });
  }

  async startInlineCreate({ type = "file", targetDirParam = null } = {}) {
    if (!this.viewport) return;

    let targetDir = targetDirParam || "";
    const rootPath = store && store.state && store.state.workspace ? store.state.workspace.rootPath : "";

    if (!targetDir) {
      if (this.selectedNode && this.selectedNode.isDir) {
        targetDir = this.selectedNode.path;
      } else if (this.selectedNode && this.selectedNode.path) {
        const lastSlash = this.selectedNode.path.lastIndexOf("/");
        targetDir = lastSlash !== -1 ? this.selectedNode.path.substring(0, lastSlash) : rootPath;
      } else if (rootPath) {
        targetDir = rootPath;
      }
    }

    // Clean up any existing inline creation row
    const existing = this.viewport.querySelector(".tree-inline-create");
    if (existing) {
      existing.remove();
    }

    let level = 1;
    let targetContainer = this.viewport;
    let insertBeforeEl = this.viewport.firstChild;

    if (targetDir && targetDir !== rootPath) {
      await this.toggleFolder(targetDir, true);
      const folderEl = this.viewport.querySelector(`.tree-item[data-path="${targetDir}"]`);
      if (folderEl) {
        const parentLevel = parseInt(folderEl.getAttribute("aria-level") || "1", 10);
        level = parentLevel + 1;

        const next = folderEl.nextElementSibling;
        if (next && next.classList.contains("tree-group")) {
          targetContainer = next;
          insertBeforeEl = next.firstChild;
        } else {
          targetContainer = folderEl.parentElement || this.viewport;
          insertBeforeEl = folderEl.nextSibling;
        }
      }
    }

    const emptyMsg = this.viewport.querySelector(".tree-empty-message");
    if (emptyMsg) {
      emptyMsg.style.display = "none";
    }

    const rowEl = document.createElement("div");
    rowEl.className = "tree-item tree-inline-create is-creating";
    rowEl.setAttribute("role", "treeitem");
    rowEl.setAttribute("aria-level", String(level));
    rowEl.setAttribute("tabindex", "0");

    if (level > 1) {
      const indentSpan = document.createElement("span");
      indentSpan.className = "tree-indent";
      indentSpan.style.width = `${(level - 1) * 14}px`;
      indentSpan.setAttribute("aria-hidden", "true");
      rowEl.appendChild(indentSpan);
    }

    if (type === "folder") {
      const arrowSpan = document.createElement("span");
      arrowSpan.className = "tree-arrow";
      arrowSpan.setAttribute("aria-hidden", "true");
      arrowSpan.textContent = "▼";
      rowEl.appendChild(arrowSpan);
    }

    const iconSpan = document.createElement("span");
    iconSpan.className = "tree-icon";
    iconSpan.setAttribute("aria-hidden", "true");
    const iconName = type === "folder" ? "folder" : "file";
    iconSpan.appendChild(createSvgIcon(iconName, 14, "deskai-svg-icon tree-svg-icon"));
    rowEl.appendChild(iconSpan);

    const inputWrapper = document.createElement("div");
    inputWrapper.className = "tree-create-input-wrapper";

    const inputEl = document.createElement("input");
    inputEl.type = "text";
    inputEl.className = "tree-create-input";
    inputEl.placeholder = type === "folder" ? "Folder name..." : "File name...";
    inputEl.setAttribute("aria-label", type === "folder" ? "New folder name" : "New file name");
    inputEl.setAttribute("spellcheck", "false");
    inputEl.setAttribute("autocomplete", "off");
    inputWrapper.appendChild(inputEl);
    rowEl.appendChild(inputWrapper);

    const actionsSpan = document.createElement("div");
    actionsSpan.className = "tree-create-actions";

    const confirmBtn = document.createElement("button");
    confirmBtn.type = "button";
    confirmBtn.className = "tree-create-btn tree-create-confirm";
    confirmBtn.setAttribute("data-action", "confirm-inline-create");
    confirmBtn.setAttribute("title", "Confirm (Enter)");
    confirmBtn.setAttribute("aria-label", "Confirm");
    confirmBtn.appendChild(createSvgIcon("check", 13, "deskai-svg-icon"));
    actionsSpan.appendChild(confirmBtn);

    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "tree-create-btn tree-create-cancel";
    cancelBtn.setAttribute("data-action", "cancel-inline-create");
    cancelBtn.setAttribute("title", "Cancel (Esc)");
    cancelBtn.setAttribute("aria-label", "Cancel");
    cancelBtn.appendChild(createSvgIcon("close", 13, "deskai-svg-icon"));
    actionsSpan.appendChild(cancelBtn);

    rowEl.appendChild(actionsSpan);

    if (insertBeforeEl) {
      targetContainer.insertBefore(rowEl, insertBeforeEl);
    } else {
      targetContainer.appendChild(rowEl);
    }

    let isCommitted = false;
    let isCancelled = false;

    const cancel = () => {
      if (isCommitted || isCancelled) return;
      isCancelled = true;
      rowEl.remove();
      if (emptyMsg && (!this.entries || this.entries.length === 0)) {
        emptyMsg.style.display = "";
      }
    };

    const commit = async () => {
      if (isCommitted || isCancelled) return;
      const rawName = inputEl.value.trim();
      if (!rawName) {
        cancel();
        return;
      }
      isCommitted = true;
      rowEl.remove();

      const root = store && store.state && store.state.workspace ? store.state.workspace.rootPath : "";
      const parentDir = targetDir || root || "";
      const cleanParent = parentDir.replace(/\/+$/, "");
      const fullPath = cleanParent ? `${cleanParent}/${rawName}` : rawName;

      if (type === "folder") {
        const res = await NativeBridge.createDir(fullPath);
        if (res && res.status === "ok") {
          if (cleanParent && this.dirChildren.has(cleanParent)) {
            this.dirChildren.delete(cleanParent);
          }
          await this.refresh();
        }
      } else {
        const res = await NativeBridge.writeFile(fullPath, "");
        if (res && res.status === "ok") {
          if (cleanParent && this.dirChildren.has(cleanParent)) {
            this.dirChildren.delete(cleanParent);
          }
          await this.refresh();
          if (window.EditorManager && typeof window.EditorManager.openFile === "function") {
            await window.EditorManager.openFile(fullPath);
          }
        }
      }
    };

    confirmBtn.addEventListener("mousedown", (e) => e.preventDefault());
    cancelBtn.addEventListener("mousedown", (e) => e.preventDefault());

    confirmBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      commit();
    });

    cancelBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      cancel();
    });

    inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        e.stopPropagation();
        commit();
      } else if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        cancel();
      }
    });

    inputEl.addEventListener("blur", () => {
      setTimeout(() => {
        if (!isCommitted && !isCancelled && !inputEl.value.trim()) {
          cancel();
        }
      }, 150);
    });

    setTimeout(() => {
      inputEl.focus();
    }, 10);
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
