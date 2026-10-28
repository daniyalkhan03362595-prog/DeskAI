/**
 * File Explorer Context Menu Module.
 */
import { store } from "../state.js";

export class ContextMenuManager {
  constructor(viewport, contextMenu, callbacks) {
    this.viewport = viewport;
    this.contextMenu = contextMenu;
    this.callbacks = callbacks;
    this.contextTarget = null;

    this.initEvents();
  }

  initEvents() {
    if (!this.viewport || !this.contextMenu) return;

    this.viewport.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      const itemEl = e.target.closest(".tree-item");
      if (itemEl) {
        this.callbacks.selectNode(itemEl);
        this.show(e.clientX, e.clientY, this.callbacks.getSelectedNode());
      } else {
        const rootPath = store && store.state && store.state.workspace ? store.state.workspace.rootPath : "";
        this.show(e.clientX, e.clientY, {
          path: rootPath,
          isDir: true,
          name: "workspace"
        });
      }
    });

    this.contextMenu.addEventListener("click", async (e) => {
      const item = e.target.closest(".menu-item");
      if (!item) return;
      const action = item.getAttribute("data-action");
      if (action) {
        await this.handleAction(action);
      }
    });

    this.contextMenu.addEventListener("keydown", async (e) => {
      const items = Array.from(this.contextMenu.querySelectorAll(".menu-item"));
      if (items.length === 0) return;
      const currentIndex = items.indexOf(document.activeElement);

      if (e.key === "ArrowDown") {
        e.preventDefault();
        const next = (currentIndex + 1) % items.length;
        items[next].focus();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        const prev = (currentIndex - 1 + items.length) % items.length;
        items[prev].focus();
      } else if (e.key === "Escape") {
        e.preventDefault();
        this.hide();
        const selected = this.callbacks.getSelectedNode();
        if (selected) {
          const node = this.viewport.querySelector(`[data-path="${selected.path}"]`);
          if (node) node.focus();
        }
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (currentIndex !== -1) {
          const action = items[currentIndex].getAttribute("data-action");
          if (action) await this.handleAction(action);
        }
      }
    });

    document.addEventListener("pointerdown", (e) => {
      if (this.contextMenu && !this.contextMenu.hidden && !this.contextMenu.contains(e.target)) {
        this.hide();
      }
    });
  }

  show(x, y, targetNode) {
    if (!this.contextMenu) return;
    this.contextTarget = targetNode;

    this.contextMenu.style.display = "block";
    this.contextMenu.removeAttribute("hidden");

    const menuW = this.contextMenu.offsetWidth || 180;
    const menuH = this.contextMenu.offsetHeight || 200;
    const maxX = window.innerWidth - menuW - 8;
    const maxY = window.innerHeight - menuH - 8;

    const clampedX = Math.max(8, Math.min(x, maxX));
    const clampedY = Math.max(8, Math.min(y, maxY));

    this.contextMenu.style.left = `${clampedX}px`;
    this.contextMenu.style.top = `${clampedY}px`;

    const firstItem = this.contextMenu.querySelector(".menu-item");
    if (firstItem) firstItem.focus();
  }

  hide() {
    if (!this.contextMenu) return;
    this.contextMenu.style.display = "none";
    this.contextMenu.setAttribute("hidden", "");
    this.contextTarget = null;
  }

  async handleAction(action) {
    const target = this.contextTarget || this.callbacks.getSelectedNode();
    this.hide();
    if (!target) return;
    await this.callbacks.executeContextAction(action, target);
  }
}
