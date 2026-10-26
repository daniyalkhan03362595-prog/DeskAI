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

      case "toggle-drawer":
        document.getElementById("bottomDrawer").classList.toggle("collapsed");
        break;
      case "drawer-tab":
        document.querySelectorAll(".drawer-tab").forEach(t => t.classList.remove("active"));
        trigger.classList.add("active");
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
}
