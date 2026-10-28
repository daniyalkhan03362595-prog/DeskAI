/**
 * File Explorer Tree Rendering & Keyboard Navigation Module.
 */
import { createSvgIcon } from "../icons.js";

export function detectFileIcon(filename, isDir) {
  if (isDir) return "folder";
  if (!filename) return "file";
  const lower = filename.toLowerCase();

  // Code & script extensions
  if (
    lower.endsWith(".py") ||
    lower.endsWith(".pyw") ||
    lower.endsWith(".js") ||
    lower.endsWith(".mjs") ||
    lower.endsWith(".cjs") ||
    lower.endsWith(".ts") ||
    lower.endsWith(".tsx") ||
    lower.endsWith(".jsx") ||
    lower.endsWith(".json") ||
    lower.endsWith(".html") ||
    lower.endsWith(".htm") ||
    lower.endsWith(".css") ||
    lower.endsWith(".scss") ||
    lower.endsWith(".sass") ||
    lower.endsWith(".less") ||
    lower.endsWith(".sh") ||
    lower.endsWith(".bash") ||
    lower.endsWith(".zsh") ||
    lower.endsWith(".sql") ||
    lower.endsWith(".toml") ||
    lower.endsWith(".yaml") ||
    lower.endsWith(".yml") ||
    lower.endsWith(".xml") ||
    lower.endsWith(".in") ||
    lower.endsWith(".rs") ||
    lower.endsWith(".go") ||
    lower.endsWith(".c") ||
    lower.endsWith(".cpp") ||
    lower.endsWith(".h") ||
    lower.endsWith(".java") ||
    lower.endsWith(".env") ||
    lower.endsWith(".gitignore") ||
    lower.endsWith(".gitattributes") ||
    lower.endsWith(".editorconfig")
  ) {
    return "file-code";
  }

  // Text, markdown & documentation extensions
  if (
    lower.endsWith(".md") ||
    lower.endsWith(".markdown") ||
    lower.endsWith(".txt") ||
    lower.endsWith(".rst") ||
    lower.endsWith(".log") ||
    lower.endsWith(".csv") ||
    lower.endsWith(".tsv")
  ) {
    return "file-text";
  }

  return "file";
}

export function initToolbarKeyboard(toolbar) {
  if (!toolbar) return;
  const buttons = Array.from(toolbar.querySelectorAll("button.icon-btn"));
  if (buttons.length === 0) return;

  function updateToolbarFocus(targetIndex) {
    buttons.forEach((btn, i) => {
      if (i === targetIndex) {
        btn.setAttribute("tabindex", "0");
        btn.focus();
      } else {
        btn.setAttribute("tabindex", "-1");
      }
    });
  }

  toolbar.addEventListener("keydown", (e) => {
    const activeEl = document.activeElement;
    const currentIndex = buttons.indexOf(activeEl);
    if (currentIndex === -1) return;

    if (e.key === "ArrowRight") {
      e.preventDefault();
      const nextIndex = (currentIndex + 1) % buttons.length;
      updateToolbarFocus(nextIndex);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      const prevIndex = (currentIndex - 1 + buttons.length) % buttons.length;
      updateToolbarFocus(prevIndex);
    } else if (e.key === "Home") {
      e.preventDefault();
      updateToolbarFocus(0);
    } else if (e.key === "End") {
      e.preventDefault();
      updateToolbarFocus(buttons.length - 1);
    }
  });
}

export function initTreeKeyboard(viewport, callbacks) {
  if (!viewport) return;

  viewport.addEventListener("keydown", async (e) => {
    const visibleItems = Array.from(viewport.querySelectorAll(".tree-item"));
    if (visibleItems.length === 0) return;

    let currentIndex = visibleItems.indexOf(document.activeElement);
    if (currentIndex === -1) {
      const activeNode = viewport.querySelector(".tree-item.active");
      currentIndex = activeNode ? visibleItems.indexOf(activeNode) : 0;
    }

    const currentItem = visibleItems[currentIndex];

    switch (e.key) {
      case "ArrowDown": {
        e.preventDefault();
        const nextIndex = Math.min(currentIndex + 1, visibleItems.length - 1);
        callbacks.focusNode(visibleItems[nextIndex]);
        break;
      }
      case "ArrowUp": {
        e.preventDefault();
        const prevIndex = Math.max(currentIndex - 1, 0);
        callbacks.focusNode(visibleItems[prevIndex]);
        break;
      }
      case "ArrowRight": {
        e.preventDefault();
        if (currentItem && currentItem.getAttribute("data-is-dir") === "true") {
          const isExpanded = currentItem.getAttribute("aria-expanded") === "true";
          if (!isExpanded) {
            await callbacks.toggleFolder(currentItem.getAttribute("data-path"), true);
          } else {
            if (currentIndex + 1 < visibleItems.length) {
              callbacks.focusNode(visibleItems[currentIndex + 1]);
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
            await callbacks.toggleFolder(currentItem.getAttribute("data-path"), false);
            return;
          }
        }
        const groupParent = currentItem.closest(".tree-group");
        if (groupParent) {
          const parentItem = groupParent.previousElementSibling;
          if (parentItem && parentItem.classList.contains("tree-item")) {
            callbacks.focusNode(parentItem);
          }
        }
        break;
      }
      case "Home": {
        e.preventDefault();
        callbacks.focusNode(visibleItems[0]);
        break;
      }
      case "End": {
        e.preventDefault();
        callbacks.focusNode(visibleItems[visibleItems.length - 1]);
        break;
      }
      case "Enter": {
        e.preventDefault();
        if (currentItem) {
          await callbacks.activateNode(currentItem);
        }
        break;
      }
      case " ": {
        e.preventDefault();
        if (currentItem) {
          callbacks.selectNode(currentItem);
        }
        break;
      }
      case "F2": {
        e.preventDefault();
        if (currentItem) {
          callbacks.startInlineRename(currentItem);
        }
        break;
      }
      case "F10": {
        if (e.shiftKey && currentItem) {
          e.preventDefault();
          const rect = currentItem.getBoundingClientRect();
          callbacks.showContextMenu(rect.left + 24, rect.bottom, callbacks.getSelectedNode() || {
            path: currentItem.getAttribute("data-path"),
            isDir: currentItem.getAttribute("data-is-dir") === "true",
            name: currentItem.querySelector(".tree-label") ? currentItem.querySelector(".tree-label").textContent : ""
          });
        }
        break;
      }
      case "ContextMenu": {
        if (currentItem) {
          e.preventDefault();
          const rect = currentItem.getBoundingClientRect();
          callbacks.showContextMenu(rect.left + 24, rect.bottom, callbacks.getSelectedNode() || {
            path: currentItem.getAttribute("data-path"),
            isDir: currentItem.getAttribute("data-is-dir") === "true",
            name: currentItem.querySelector(".tree-label") ? currentItem.querySelector(".tree-label").textContent : ""
          });
        }
        break;
      }
    }
  });
}

export function renderTreeNodes(entries, parentEl, level, state) {
  let firstAssigned = false;

  for (const entry of entries) {
    const itemEl = document.createElement("div");
    const isDir = entry.is_dir;
    const isExpanded = isDir && state.expandedDirs.has(entry.path);
    const isSelected = state.selectedNode && state.selectedNode.path === entry.path;

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

    if (!firstAssigned && level === 1 && !state.selectedNode) {
      itemEl.setAttribute("tabindex", "0");
      firstAssigned = true;
    } else if (isSelected) {
      itemEl.setAttribute("tabindex", "0");
    } else {
      itemEl.setAttribute("tabindex", "-1");
    }

    if (level > 1) {
      const indentSpan = document.createElement("span");
      indentSpan.className = "tree-indent";
      indentSpan.style.width = `${(level - 1) * 14}px`;
      indentSpan.setAttribute("aria-hidden", "true");
      itemEl.appendChild(indentSpan);
    }

    if (isDir) {
      const arrowSpan = document.createElement("span");
      arrowSpan.className = "tree-arrow";
      arrowSpan.setAttribute("aria-hidden", "true");
      arrowSpan.textContent = isExpanded ? "▼" : "►";
      itemEl.appendChild(arrowSpan);
    }

    const iconSpan = document.createElement("span");
    iconSpan.className = "tree-icon";
    iconSpan.setAttribute("aria-hidden", "true");
    const iconName = isDir ? (isExpanded ? "folder-open" : "folder") : detectFileIcon(entry.name, false);
    iconSpan.setAttribute("data-icon", iconName);
    iconSpan.appendChild(createSvgIcon(iconName, 14, "deskai-svg-icon tree-svg-icon"));
    itemEl.appendChild(iconSpan);

    const labelSpan = document.createElement("span");
    labelSpan.className = "tree-label";
    labelSpan.textContent = entry.name;
    itemEl.appendChild(labelSpan);

    const actionsSpan = document.createElement("span");
    actionsSpan.className = "tree-inline-actions";

    if (isDir) {
      const newFileBtn = document.createElement("button");
      newFileBtn.type = "button";
      newFileBtn.className = "tree-inline-btn";
      newFileBtn.setAttribute("data-action", "folder-new-file");
      newFileBtn.setAttribute("data-path", entry.path);
      newFileBtn.setAttribute("title", `New File in ${entry.name}...`);
      newFileBtn.setAttribute("aria-label", `New File in ${entry.name}`);
      newFileBtn.appendChild(createSvgIcon("file-plus", 13, "deskai-svg-icon"));
      actionsSpan.appendChild(newFileBtn);

      const newFolderBtn = document.createElement("button");
      newFolderBtn.type = "button";
      newFolderBtn.className = "tree-inline-btn";
      newFolderBtn.setAttribute("data-action", "folder-new-folder");
      newFolderBtn.setAttribute("data-path", entry.path);
      newFolderBtn.setAttribute("title", `New Folder in ${entry.name}...`);
      newFolderBtn.setAttribute("aria-label", `New Folder in ${entry.name}`);
      newFolderBtn.appendChild(createSvgIcon("folder-plus", 13, "deskai-svg-icon"));
      actionsSpan.appendChild(newFolderBtn);
    }

    const renameBtn = document.createElement("button");
    renameBtn.type = "button";
    renameBtn.className = "tree-inline-btn";
    renameBtn.setAttribute("data-action", "item-rename");
    renameBtn.setAttribute("data-path", entry.path);
    renameBtn.setAttribute("title", `Rename ${entry.name}...`);
    renameBtn.setAttribute("aria-label", `Rename ${entry.name}`);
    renameBtn.appendChild(createSvgIcon("edit", 13, "deskai-svg-icon"));
    actionsSpan.appendChild(renameBtn);

    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.className = "tree-inline-btn btn-delete";
    deleteBtn.setAttribute("data-action", "item-delete");
    deleteBtn.setAttribute("data-path", entry.path);
    deleteBtn.setAttribute("title", `Delete ${entry.name}...`);
    deleteBtn.setAttribute("aria-label", `Delete ${entry.name}`);
    deleteBtn.appendChild(createSvgIcon("trash", 13, "deskai-svg-icon"));
    actionsSpan.appendChild(deleteBtn);

    itemEl.appendChild(actionsSpan);

    parentEl.appendChild(itemEl);

    if (isDir && isExpanded) {
      const groupEl = document.createElement("div");
      groupEl.className = "tree-group";
      groupEl.setAttribute("role", "group");

      const children = state.dirChildren.get(entry.path) || [];
      renderTreeNodes(children, groupEl, level + 1, state);
      parentEl.appendChild(groupEl);
    }
  }
}
