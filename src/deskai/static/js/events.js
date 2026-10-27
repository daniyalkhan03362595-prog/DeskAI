import { NativeBridge } from "./bridge.js";
import { store } from "./state.js";

export function initGlobalEvents() {
  // 1. Drag & Drop Navigation Lock
  window.addEventListener("dragover", (e) => e.preventDefault(), false);
  window.addEventListener("drop", (e) => e.preventDefault(), false);

  // 2. Universal Link Click Interceptor (click & auxclick for middle click)
  function handleLinkClick(e) {
    const anchor = e.target.closest("a[href]");
    if (anchor) {
      const url = anchor.getAttribute("href");
      if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("mailto:")) {
        e.preventDefault();
        window.pywebview.api.open_external_url(url);
      }
    }
  }
  document.addEventListener("click", handleLinkClick);
  document.addEventListener("auxclick", (e) => {
    if (e.button === 1) handleLinkClick(e);
  });

  // 3. Complete Action Router (All 16 actions)
  document.addEventListener("click", async (e) => {
    const trigger = e.target.closest("[data-action]");
    if (!trigger) return;

    // Security guard: ignore data-action inside user content surfaces
    if (trigger.closest(".bubble-body, .tab-label, .markdown-surface")) {
      return;
    }

    // Security guard: must be inside #appRoot
    if (!trigger.closest("#appRoot")) {
      return;
    }

    const action = trigger.dataset.action;
    const param = trigger.dataset.param;

    switch (action) {
      case "win-minimize":
        NativeBridge.windowControl("minimize");
        break;
      case "win-maximize":
        NativeBridge.windowControl("maximize");
        break;
      case "win-close": {
        const canClose = await NativeBridge.windowControl("close_request");
        if (!canClose) {
          const confirmModal = document.getElementById("confirmModal");
          if (confirmModal && typeof confirmModal.showModal === "function") {
            confirmModal.showModal();
          } else {
            NativeBridge.windowControl("close");
          }
        }
        break;
      }

      case "cancel-exit": {
        const confirmModal = document.getElementById("confirmModal");
        if (confirmModal && confirmModal.close) {
          confirmModal.close();
        }
        break;
      }

      case "confirm-exit": {
        const confirmModal = document.getElementById("confirmModal");
        if (confirmModal && confirmModal.close) {
          confirmModal.close();
        }
        await NativeBridge.setDirtyStatus(false);
        await NativeBridge.windowControl("close");
        break;
      }

      case "tab-close":
        window.EditorManager.closeTab(param);
        break;
      case "select-tab":
        window.EditorManager.selectTab(param);
        break;

      case "open-folder-dialog":
        const dir = await NativeBridge.selectFolder();
        if (dir && dir.path) {
          store.state.workspace.rootPath = dir.path;
          const pill = document.getElementById("headerWorkspacePill");
          if (pill) pill.textContent = `DeskAI / ${dir.name}`;
        }
        break;
      case "new-file":
        const fileName = prompt("Enter new file name:");
        if (fileName) window.EditorManager.createBuffer(fileName);
        break;
      case "new-folder":
        prompt("Enter folder name:");
        break;
      case "refresh-tree":
        console.log("Refreshing workspace tree...");
        break;

      case "toggle-drawer": {
        const drawer = document.getElementById("bottomDrawer");
        if (drawer) {
          const isCollapsed = drawer.classList.toggle("collapsed");
          trigger.setAttribute("aria-expanded", String(!isCollapsed));
          if (isCollapsed) {
            if (window.DeskAIPorts) window.DeskAIPorts.stopPolling();
          } else {
            const activeTab = document.querySelector(".drawer-tab.active");
            if (activeTab && activeTab.getAttribute("data-target") === "ports" && window.DeskAIPorts) {
              window.DeskAIPorts.refresh();
              window.DeskAIPorts.startPolling();
            }
          }
        }
        break;
      }
      case "drawer-tab": {
        const target = trigger.getAttribute("data-target");
        const drawer = document.getElementById("bottomDrawer");
        if (drawer && drawer.classList.contains("collapsed")) {
          drawer.classList.remove("collapsed");
          const toggleBtn = document.getElementById("drawerToggleBtn");
          if (toggleBtn) toggleBtn.setAttribute("aria-expanded", "true");
        }

        document.querySelectorAll(".drawer-tab").forEach(t => {
          t.classList.remove("active");
          t.setAttribute("aria-selected", "false");
        });
        trigger.classList.add("active");
        trigger.setAttribute("aria-selected", "true");

        document.querySelectorAll(".drawer-panel").forEach(panel => {
          if (panel.id === `${target}Panel`) {
            panel.classList.add("active");
            panel.removeAttribute("hidden");
          } else {
            panel.classList.remove("active");
            panel.setAttribute("hidden", "");
          }
        });

        if (target === "ports" && window.DeskAIPorts) {
          window.DeskAIPorts.refresh();
          window.DeskAIPorts.startPolling();
        } else if (window.DeskAIPorts) {
          window.DeskAIPorts.stopPolling();
        }
        break;
      }

      case "watch-port":
      case "add-port":
        if (window.DeskAIPorts) window.DeskAIPorts.promptAddPort();
        break;
      case "cancel-watch-port": {
        const modal = document.getElementById("watchPortModal");
        if (modal && typeof modal.close === "function") modal.close();
        break;
      }
      case "refresh-ports":
        if (window.DeskAIPorts) window.DeskAIPorts.refresh();
        break;
      case "open-port":
        if (window.DeskAIPorts) {
          const port = trigger.getAttribute("data-port");
          const host = trigger.getAttribute("data-host") || "127.0.0.1";
          window.DeskAIPorts.openPort(port, host);
        }
        break;
      case "copy-port":
        if (window.DeskAIPorts) window.DeskAIPorts.copyPort(trigger.getAttribute("data-url"));
        break;
      case "remove-port":
        if (window.DeskAIPorts) {
          const port = trigger.getAttribute("data-port");
          const host = trigger.getAttribute("data-host") || "127.0.0.1";
          window.DeskAIPorts.removePort(port, host);
        }
        break;

      case "uec-approve":
        window.UEC.approvePlan();
        break;
      case "uec-reject":
        window.UEC.rejectPlan();
        break;
      case "uec-rollback":
        window.UEC.rollback();
        break;
      case "uec-cancel":
        window.UEC.cancel();
        break;
      case "uec-reset":
        window.UEC.reset();
        break;

      default:
        console.warn("Unhandled action:", action);
    }
  });

  // 4. Global Hotkeys (Supporting Ctrl and macOS Meta/Cmd)
  window.addEventListener("keydown", (e) => {
    const isCmd = e.ctrlKey || e.metaKey;
    const key = e.key.toLowerCase();

    if (isCmd && key === "s") {
      e.preventDefault();
      if (window.EditorManager && typeof window.EditorManager.saveActiveBuffer === "function") {
        window.EditorManager.saveActiveBuffer();
      }
    } else if (isCmd && key === "w") {
      e.preventDefault();
      if (window.EditorManager && window.EditorManager.activeTabId) {
        window.EditorManager.closeTab(window.EditorManager.activeTabId);
      }
    } else if (isCmd && e.key === "Enter") {
      e.preventDefault();
      const form = document.getElementById("promptForm");
      if (form) form.requestSubmit();
    }
  });

  // 5. Dual Resizers Handle Pointer Drag
  initResizers();

  // 6. Header Drag (Wayland / GTK / Windows native move drag) & Double Click Maximize
  const appHeader = document.getElementById("appHeader");
  if (appHeader) {
    let lastHeaderMouseDown = 0;
    appHeader.addEventListener("mousedown", (e) => {
      if (e.button === 0 && !e.target.closest("button, input, textarea, .workspace-pill")) {
        const now = e.timeStamp || Date.now();
        if (now - lastHeaderMouseDown < 350 || e.detail > 1) {
          lastHeaderMouseDown = now;
          return;
        }
        lastHeaderMouseDown = now;
        NativeBridge.windowControl("drag_start", null, now);
      }
    });

    appHeader.addEventListener("dblclick", (e) => {
      if (!e.target.closest("button, input, textarea")) {
        NativeBridge.windowControl("maximize");
      }
    });
  }

  // 7. Outer Edge & Corner Window Resizing (Native Wayland / GTK / Windows + Hybrid Fallback)
  const resizeHandles = document.getElementById("windowResizeHandles");
  if (resizeHandles) {
    resizeHandles.addEventListener("mousedown", (e) => {
      const handle = e.target.closest(".resize-handle");
      if (handle && e.button === 0) {
        e.preventDefault();
        e.stopPropagation();
        const edge = handle.dataset.edge;
        if (!edge) return;

        // Try native compositor resize drag first
        NativeBridge.windowControl("resize_start", edge, e.timeStamp || Date.now());

        // Hybrid Fallback: Mouse coordinate drag tracking if compositor doesn't grab
        const startX = e.screenX;
        const startY = e.screenY;
        const startW = window.outerWidth || window.innerWidth;
        const startH = window.outerHeight || window.innerHeight;

        function onMouseMove(moveEvent) {
          const dx = moveEvent.screenX - startX;
          const dy = moveEvent.screenY - startY;
          let newW = startW;
          let newH = startH;

          if (edge.includes("right") || edge === "right" || edge === "e") newW += dx;
          if (edge.includes("left") || edge === "left" || edge === "w") newW -= dx;
          if (edge.includes("bottom") || edge === "bottom" || edge === "s") newH += dy;
          if (edge.includes("top") || edge === "top" || edge === "n") newH -= dy;

          newW = Math.max(900, Math.round(newW));
          newH = Math.max(600, Math.round(newH));

          NativeBridge.resizeWindowAbsolute(newW, newH);
        }

        function onMouseUp() {
          window.removeEventListener("mousemove", onMouseMove);
          window.removeEventListener("mouseup", onMouseUp);
        }

        window.addEventListener("mousemove", onMouseMove);
        window.addEventListener("mouseup", onMouseUp);
      }
    });
  }
}

function initResizers() {
  const resizerLeft = document.getElementById("resizerLeft");
  const resizerRight = document.getElementById("resizerRight");
  const root = document.documentElement;

  if (resizerLeft) {
    resizerLeft.addEventListener("mousedown", (e) => {
      e.preventDefault();
      resizerLeft.classList.add("resizing");
      const onMouseMove = (ev) => {
        const newW = Math.max(180, Math.min(500, ev.clientX - 48));
        root.style.setProperty("--sidebar-left-w", `${newW}px`);
      };
      const onMouseUp = () => {
        resizerLeft.classList.remove("resizing");
        window.removeEventListener("mousemove", onMouseMove);
        window.removeEventListener("mouseup", onMouseUp);
      };
      window.addEventListener("mousemove", onMouseMove);
      window.addEventListener("mouseup", onMouseUp);
    });
  }

  if (resizerRight) {
    resizerRight.addEventListener("mousedown", (e) => {
      e.preventDefault();
      resizerRight.classList.add("resizing");
      const onMouseMove = (ev) => {
        const newW = Math.max(260, Math.min(600, window.innerWidth - ev.clientX));
        root.style.setProperty("--sidebar-right-w", `${newW}px`);
      };
      const onMouseUp = () => {
        resizerRight.classList.remove("resizing");
        window.removeEventListener("mousemove", onMouseMove);
        window.removeEventListener("mouseup", onMouseUp);
      };
      window.addEventListener("mousemove", onMouseMove);
      window.addEventListener("mouseup", onMouseUp);
    });
  }

  const resizerBottom = document.getElementById("resizerBottom");
  const bottomDrawer = document.getElementById("bottomDrawer");
  const editorStage = document.getElementById("editorStage");

  if (resizerBottom && bottomDrawer && editorStage) {
    resizerBottom.addEventListener("mousedown", (e) => {
      e.preventDefault();
      resizerBottom.classList.add("resizing");

      const onMouseMove = (ev) => {
        const stageRect = editorStage.getBoundingClientRect();
        const rawH = stageRect.bottom - ev.clientY;
        const maxH = Math.max(160, editorStage.clientHeight - 80);
        const newH = Math.max(48, Math.min(maxH, rawH));
        root.style.setProperty("--bottom-drawer-h", `${newH}px`);
        resizerBottom.setAttribute("aria-valuenow", String(Math.round(newH)));
        if (bottomDrawer.classList.contains("collapsed") && newH > 40) {
          bottomDrawer.classList.remove("collapsed");
        }
      };

      const onMouseUp = () => {
        resizerBottom.classList.remove("resizing");
        window.removeEventListener("mousemove", onMouseMove);
        window.removeEventListener("mouseup", onMouseUp);
      };

      window.addEventListener("mousemove", onMouseMove);
      window.addEventListener("mouseup", onMouseUp);
    });

    // Keyboard navigation (ArrowUp to enlarge drawer, ArrowDown to shrink)
    resizerBottom.addEventListener("keydown", (e) => {
      const step = e.shiftKey ? 50 : 20;
      const currentH = parseInt(getComputedStyle(root).getPropertyValue("--bottom-drawer-h"), 10) || 220;
      const maxH = Math.max(160, editorStage.clientHeight - 80);

      if (e.key === "ArrowUp") {
        e.preventDefault();
        const newH = Math.min(maxH, currentH + step);
        root.style.setProperty("--bottom-drawer-h", `${newH}px`);
        resizerBottom.setAttribute("aria-valuenow", String(Math.round(newH)));
        bottomDrawer.classList.remove("collapsed");
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        const newH = Math.max(48, currentH - step);
        root.style.setProperty("--bottom-drawer-h", `${newH}px`);
        resizerBottom.setAttribute("aria-valuenow", String(Math.round(newH)));
      }
    });

    // Double-click to toggle collapse or restore default height
    resizerBottom.addEventListener("dblclick", () => {
      if (bottomDrawer.classList.contains("collapsed")) {
        bottomDrawer.classList.remove("collapsed");
        root.style.setProperty("--bottom-drawer-h", "220px");
      } else {
        bottomDrawer.classList.add("collapsed");
      }
    });
  }
}
