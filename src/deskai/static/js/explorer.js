import { store } from "./state.js";
import { NativeBridge } from "./bridge.js";

export class ExplorerManager {
  constructor() {
    this.viewport = document.getElementById("fileTreeViewport");
    this.toolbar = document.getElementById("explorerToolbar");
    this.selectedNode = null;
    this.expandedDirs = new Set();
    this.dirChildren = new Map();
    this.entries = [];

    this.initToolbarKeyboard();
    this.initTreeKeyboard();
    this.initClickDelegation();
  }

  detectFileIcon(filename, isDir) {
    if (isDir) return "📁";
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

  initTreeKeyboard() {
    if (!this.viewport) return;

    this.viewport.addEventListener("keydown", async (e) => {
      const visibleItems = Array.from(this.viewport.querySelectorAll(".tree-item"));
      if (visibleItems.length === 0) return;

      let currentIndex = visibleItems.indexOf(document.activeElement);
      if (currentIndex === -1) {
        const activeNode = this.viewport.querySelector(".tree-item.active");
        currentIndex = activeNode ? visibleItems.indexOf(activeNode) : 0;
      }

      const currentItem = visibleItems[currentIndex];

      switch (e.key) {
        case "ArrowDown": {
          e.preventDefault();
          const nextIndex = Math.min(currentIndex + 1, visibleItems.length - 1);
          this.focusNode(visibleItems[nextIndex]);
          break;
        }

        case "ArrowUp": {
          e.preventDefault();
          const prevIndex = Math.max(currentIndex - 1, 0);
          this.focusNode(visibleItems[prevIndex]);
          break;
        }

        case "ArrowRight": {
          e.preventDefault();
          if (currentItem && currentItem.getAttribute("data-is-dir") === "true") {
            const isExpanded = currentItem.getAttribute("aria-expanded") === "true";
            if (!isExpanded) {
              await this.toggleFolder(currentItem.getAttribute("data-path"), true);
            } else {
              if (currentIndex + 1 < visibleItems.length) {
                this.focusNode(visibleItems[currentIndex + 1]);
              }
            }
          }
          break;
        }

        case "ArrowLeft": {
          e.preventDefault();
          if (currentItem && currentItem.getAttribute("data-is-dir") === "true") {
            const isExpanded = currentItem.getAttribute("aria-expanded") === "true";
            if (isExpanded) {
              await this.toggleFolder(currentItem.getAttribute("data-path"), false);
              return;
            }
          }
          const groupParent = currentItem.closest(".tree-group");
          if (groupParent) {
            const parentItem = groupParent.previousElementSibling;
            if (parentItem && parentItem.classList.contains("tree-item")) {
              this.focusNode(parentItem);
            }
          }
          break;
        }

        case "Home": {
          e.preventDefault();
          this.focusNode(visibleItems[0]);
          break;
        }

        case "End": {
          e.preventDefault();
          this.focusNode(visibleItems[visibleItems.length - 1]);
          break;
        }

        case "Enter": {
          e.preventDefault();
          if (currentItem) {
            await this.activateNode(currentItem);
          }
          break;
        }

        case " ": {
          e.preventDefault();
          if (currentItem) {
            this.selectNode(currentItem);
          }
          break;
        }

        case "F2": {
          e.preventDefault();
          if (currentItem) {
            this.startInlineRename(currentItem);
          }
          break;
        }
      }
    });
  }

  initClickDelegation() {
    if (!this.viewport) return;

    this.viewport.addEventListener("click", async (e) => {
      const itemEl = e.target.closest(".tree-item");
      if (!itemEl) return;
      await this.activateNode(itemEl);
    });
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
      emptyIcon.textContent = "📁";
      emptyContainer.appendChild(emptyIcon);

      const emptyText = document.createElement("p");
      emptyText.className = "empty-text";
      emptyText.textContent = "No folder open";
      emptyContainer.appendChild(emptyText);

      const actionBtn = document.createElement("button");
      actionBtn.type = "button";
      actionBtn.className = "empty-action-btn";
      actionBtn.setAttribute("data-action", "open-folder-dialog");
      actionBtn.textContent = "Open Folder";
      emptyContainer.appendChild(actionBtn);

      this.viewport.appendChild(emptyContainer);
      return;
    }

    this.renderNodeList(this.entries, this.viewport, 1);
  }

  renderNodeList(entries, parentEl, level) {
    let firstAssigned = false;

    for (const entry of entries) {
      const itemEl = document.createElement("div");
      const isDir = entry.is_dir;
      const isExpanded = isDir && this.expandedDirs.has(entry.path);
      const isSelected = this.selectedNode && this.selectedNode.path === entry.path;

      itemEl.className = isDir ? "tree-item is-folder" : "tree-item is-file";
      if (isExpanded) itemEl.classList.add("expanded");
      if (isSelected) itemEl.classList.add("active");

      itemEl.setAttribute("role", "treeitem");
      itemEl.setAttribute("data-path", entry.path);
      itemEl.setAttribute("data-is-dir", isDir ? "true" : "false");
      itemEl.setAttribute("aria-level", String(level));
      itemEl.setAttribute("title", entry.path);

      if (isDir) {
        itemEl.setAttribute("aria-expanded", isExpanded ? "true" : "false");
      }

      // Roving tabindex: exactly one visible item has 0, rest -1
      if (!firstAssigned && level === 1 && !this.selectedNode) {
        itemEl.setAttribute("tabindex", "0");
        firstAssigned = true;
      } else if (isSelected) {
        itemEl.setAttribute("tabindex", "0");
      } else {
        itemEl.setAttribute("tabindex", "-1");
      }

      // Indent spacer
      if (level > 1) {
        const indentSpan = document.createElement("span");
        indentSpan.className = "tree-indent";
        indentSpan.style.width = `${(level - 1) * 14}px`;
        indentSpan.setAttribute("aria-hidden", "true");
        itemEl.appendChild(indentSpan);
      }

      // Chevron arrow for directories
      if (isDir) {
        const arrowSpan = document.createElement("span");
        arrowSpan.className = "tree-arrow";
        arrowSpan.setAttribute("aria-hidden", "true");
        arrowSpan.textContent = isExpanded ? "▼" : "►";
        itemEl.appendChild(arrowSpan);
      }

      // Icon badge
      const iconSpan = document.createElement("span");
      iconSpan.className = "tree-icon";
      iconSpan.setAttribute("aria-hidden", "true");
      iconSpan.textContent = isDir ? (isExpanded ? "📂" : "📁") : this.detectFileIcon(entry.name, false);
      itemEl.appendChild(iconSpan);

      // Label text node
      const labelSpan = document.createElement("span");
      labelSpan.className = "tree-label";
      labelSpan.textContent = entry.name;
      itemEl.appendChild(labelSpan);

      parentEl.appendChild(itemEl);

      // Nested child group
      if (isDir && isExpanded) {
        const groupEl = document.createElement("div");
        groupEl.className = "tree-group";
        groupEl.setAttribute("role", "group");

        const children = this.dirChildren.get(entry.path) || [];
        this.renderNodeList(children, groupEl, level + 1);
        parentEl.appendChild(groupEl);
      }
    }
  }
}
