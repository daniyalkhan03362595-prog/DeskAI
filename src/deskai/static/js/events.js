import { NativeBridge } from "./bridge.js";
import { store } from "./state.js";
import { toggleTheme } from "./theme.js";

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
      case "toggle-theme":
        toggleTheme();
        break;
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
          const descEl = document.getElementById("confirmModalDesc");
          const titleEl = document.getElementById("confirmModalTitle");
          const hasRunningTerminal = !!(window.DeskAITerminal && window.DeskAITerminal.sessionId);
          const isDirty = !!(window.store && window.store.state && window.store.state.dirtyTabs && window.store.state.dirtyTabs.size > 0);

          if (descEl && titleEl) {
            titleEl.textContent = "Confirm Exit";
            if (isDirty && hasRunningTerminal) {
              descEl.textContent =
                "You have unsaved changes in your open editor tabs and an active terminal running. Are you sure you want to exit?";
            } else if (hasRunningTerminal) {
              descEl.textContent =
                "You have an active terminal session running. Are you sure you want to terminate it and exit?";
            } else {
              descEl.textContent =
                "You have unsaved changes in your open editor tabs. Are you sure you want to discard them and exit?";
            }
          }

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
        if (window.DeskAITerminal) {
          window.DeskAITerminal.destroy();
        }
        await NativeBridge.setDirtyStatus(false);
        await NativeBridge.windowControl("close");
        break;
      }

      case "tab-close":
        if (window.EditorManager) {
          await window.EditorManager.closeTab(param);
        }
        break;
      case "select-tab":
        window.EditorManager.selectTab(param);
        break;

      case "open-folder-dialog": {
        const dir = await NativeBridge.selectFolder();
        if (dir && dir.path) {
          store.state.workspace.rootPath = dir.path;
          const pill = document.getElementById("headerWorkspacePill");
          if (pill) pill.textContent = `DeskAI / ${dir.name}`;
          if (window.DeskAIWelcome) {
            window.DeskAIWelcome.saveRecentProject(dir.path, dir.name);
            window.DeskAIWelcome.sync();
          }
          if (window.ExplorerManager) {
            await window.ExplorerManager.refresh();
          }
        }
        break;
      }

      case "open-file-dialog": {
        const fileRes = await NativeBridge.selectFile();
        if (fileRes && fileRes.path) {
          if (fileRes.workspace_root) {
            await NativeBridge.setWorkspaceRoot(fileRes.workspace_root);
            store.state.workspace.rootPath = fileRes.workspace_root;
            const dirName = fileRes.workspace_root.split("/").pop().split("\\").pop();
            const pill = document.getElementById("headerWorkspacePill");
            if (pill) pill.textContent = `DeskAI / ${dirName}`;
            if (window.ExplorerManager) {
              await window.ExplorerManager.refresh();
            }
          }
          if (window.EditorManager) {
            await window.EditorManager.openFile(fileRes.path);
          }
        }
        break;
      }

      case "open-recent-project": {
        if (param) {
          await NativeBridge.setWorkspaceRoot(param);
          store.state.workspace.rootPath = param;
          const name = param.split("/").pop().split("\\").pop() || param;
          const pill = document.getElementById("headerWorkspacePill");
          if (pill) pill.textContent = `DeskAI / ${name}`;
          if (window.DeskAIWelcome) {
            window.DeskAIWelcome.saveRecentProject(param, name);
            window.DeskAIWelcome.sync();
          }
          if (window.ExplorerManager) {
            await window.ExplorerManager.refresh();
          }
        }
        break;
      }

      case "remove-recent-project": {
        e.stopPropagation();
        if (param && window.DeskAIWelcome) {
          window.DeskAIWelcome.removeRecentProject(param);
        }
        break;
      }

      case "new-file": {
        if (window.ExplorerManager && typeof window.ExplorerManager.promptNewFile === "function") {
          await window.ExplorerManager.promptNewFile();
        } else {
          const fileName = prompt("Enter new file name:") || "untitled.txt";
          if (fileName && window.EditorManager) {
            window.EditorManager.createBuffer(fileName);
          }
        }
        break;
      }
      case "new-folder": {
        if (window.ExplorerManager && typeof window.ExplorerManager.promptNewFolder === "function") {
          await window.ExplorerManager.promptNewFolder();
        } else {
          prompt("Enter folder name:");
        }
        break;
      }
      case "refresh-tree": {
        if (window.ExplorerManager && typeof window.ExplorerManager.refresh === "function") {
          await window.ExplorerManager.refresh();
        }
        break;
      }
      case "collapse-all-folders": {
        if (window.ExplorerManager && typeof window.ExplorerManager.collapseAll === "function") {
          window.ExplorerManager.collapseAll();
        }
        break;
      }

      case "kill-terminal":
        if (window.DeskAITerminal) {
          window.DeskAITerminal.kill();
        }
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

        if (target === "terminal" && window.DeskAITerminal) {
          window.DeskAITerminal.onTabShown();
        } else if (target === "ports" && window.DeskAIPorts) {
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
          window.DeskAIPorts.openPort(port, host, trigger);
        }
        break;
      case "copy-port":
        if (window.DeskAIPorts) {
          window.DeskAIPorts.copyPort(trigger.getAttribute("data-url"), trigger);
        }
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

    // Suppress global app hotkeys when terminal host or xterm textarea is focused
    const terminalHost = document.getElementById("terminalHost");
    if (
      terminalHost &&
      (terminalHost.contains(document.activeElement) ||
        (document.activeElement && (document.activeElement.closest("#terminalHost") || document.activeElement.closest(".xterm"))))
    ) {
      if (isCmd && (key === "s" || key === "w" || e.key === "Enter")) {
        return;
      }
    }

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
    } else if (isCmd && key === "o") {
      e.preventDefault();
      const btn = document.querySelector('[data-action="open-folder-dialog"]');
      if (btn) btn.click();
    } else if (isCmd && key === "n") {
      e.preventDefault();
      const btn = document.querySelector('[data-action="new-file"]');
      if (btn) btn.click();
    } else if (isCmd && key === "l") {
      e.preventDefault();
      const promptInput = document.getElementById("promptTextarea");
      if (promptInput) promptInput.focus();
    } else if (isCmd && (key === "`" || e.code === "Backquote")) {
      e.preventDefault();
      const drawerToggleBtn = document.getElementById("drawerToggleBtn");
      if (drawerToggleBtn) drawerToggleBtn.click();
    }
  });

  // Drawer Tabs ArrowLeft / ArrowRight roving focus
  const drawerTabsContainer = document.querySelector(".drawer-tabs");
  if (drawerTabsContainer) {
    drawerTabsContainer.addEventListener("keydown", (e) => {
      if (e.key === "Tab" && !e.shiftKey) {
        const activeTab = drawerTabsContainer.querySelector(".drawer-tab.active");
        if (activeTab && activeTab.getAttribute("data-target") === "terminal") {
          e.preventDefault();
          if (window.DeskAITerminal && window.DeskAITerminal.term) {
            window.DeskAITerminal.term.focus();
          }
        }
      } else if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        const tabs = Array.from(drawerTabsContainer.querySelectorAll('.drawer-tab[role="tab"]'));
        const currentIndex = tabs.indexOf(document.activeElement);
        if (currentIndex !== -1) {
          e.preventDefault();
          const nextIndex =
            e.key === "ArrowRight"
              ? (currentIndex + 1) % tabs.length
              : (currentIndex - 1 + tabs.length) % tabs.length;
          tabs[nextIndex].focus();
          tabs[nextIndex].click();
        }
      }
    });
  }

  // 5. Dual Resizers Handle Pointer Drag
  initResizers();

  // 6. Header Drag (Wayland / GTK / Windows native move drag) & Double Click Maximize
  const appHeader = document.getElementById("appHeader");
  if (appHeader) {
    let lastHeaderMouseDown = 0;
    appHeader.addEventListener("mousedown", (e) => {
      if (e.button === 0 && !e.target.closest("button, input, textarea, .workspace-pill, [data-action]")) {
        const now = e.timeStamp || Date.now();
        if ((lastHeaderMouseDown > 0 && now - lastHeaderMouseDown < 350) || e.detail > 1) {
          lastHeaderMouseDown = now;
          return;
        }
        lastHeaderMouseDown = now;
        NativeBridge.windowControl("drag_start", null, now);
      }
    });

    appHeader.addEventListener("dblclick", (e) => {
      if (!e.target.closest("button, input, textarea, .workspace-pill, [data-action]")) {
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
  const drawerToggleBtn = document.getElementById("drawerToggleBtn");

  if (resizerBottom && bottomDrawer) {
    let lastExpandedHeight = 220;
    try {
      const stored = localStorage.getItem("deskai_bottom_drawer_h");
      if (stored) {
        const parsed = parseFloat(stored);
        if (!isNaN(parsed) && parsed >= 48) {
          lastExpandedHeight = parsed;
          root.style.setProperty("--bottom-drawer-h", `${parsed}px`);
        }
      }
    } catch (e) {
      console.warn("Failed to load bottom drawer height", e);
    }

    const getMaxH = () => Math.round(window.innerHeight * 0.8);

    resizerBottom.setAttribute("aria-valuemin", "48");
    resizerBottom.setAttribute("aria-valuemax", String(getMaxH()));
    const initialH = parseFloat(getComputedStyle(root).getPropertyValue("--bottom-drawer-h")) || lastExpandedHeight;
    resizerBottom.setAttribute("aria-valuenow", String(Math.round(initialH)));

    let isResizing = false;
    let startY = 0;
    let startHeight = 0;
    let rafId = null;

    resizerBottom.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      try {
        resizerBottom.setPointerCapture(e.pointerId);
      } catch (err) {
        // Ignored if capture unsupported
      }
      isResizing = true;
      resizerBottom.classList.add("is-resizing", "resizing");
      startY = e.clientY;
      startHeight = parseFloat(getComputedStyle(root).getPropertyValue("--bottom-drawer-h")) || lastExpandedHeight || 220;
    });

    resizerBottom.addEventListener("pointermove", (e) => {
      if (!isResizing) return;
      e.preventDefault();

      if (rafId) cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        const rawH = startHeight + (startY - e.clientY);
        const maxH = getMaxH();

        if (rawH < 50) {
          // Snap to collapsed floor
          bottomDrawer.classList.add("collapsed");
          if (drawerToggleBtn) drawerToggleBtn.setAttribute("aria-expanded", "false");
          root.style.setProperty("--bottom-drawer-h", "48px");
          resizerBottom.setAttribute("aria-valuenow", "48");
          if (window.DeskAIPorts) window.DeskAIPorts.stopPolling();
        } else {
          const clampedH = Math.max(48, Math.min(maxH, rawH));
          if (bottomDrawer.classList.contains("collapsed")) {
            bottomDrawer.classList.remove("collapsed");
            if (drawerToggleBtn) drawerToggleBtn.setAttribute("aria-expanded", "true");
            const activeTab = document.querySelector(".drawer-tab.active");
            if (activeTab && activeTab.getAttribute("data-target") === "ports" && window.DeskAIPorts) {
              window.DeskAIPorts.refresh();
              window.DeskAIPorts.startPolling();
            }
          }
          root.style.setProperty("--bottom-drawer-h", `${clampedH}px`);
          resizerBottom.setAttribute("aria-valuenow", String(Math.round(clampedH)));
          lastExpandedHeight = clampedH;
          if (window.DeskAITerminal) window.DeskAITerminal.fit();
        }
      });
    });

    const endResize = (e) => {
      if (!isResizing) return;
      isResizing = false;
      if (rafId) {
        cancelAnimationFrame(rafId);
        rafId = null;
      }
      try {
        if (resizerBottom.hasPointerCapture && resizerBottom.hasPointerCapture(e.pointerId)) {
          resizerBottom.releasePointerCapture(e.pointerId);
        }
      } catch (err) {
        // Ignored
      }
      resizerBottom.classList.remove("is-resizing", "resizing");
      if (window.DeskAITerminal) window.DeskAITerminal.fit();
      if (!bottomDrawer.classList.contains("collapsed")) {
        try {
          localStorage.setItem("deskai_bottom_drawer_h", String(lastExpandedHeight));
        } catch (e) {
          console.warn("Failed to persist bottom drawer height", e);
        }
      }
    };

    resizerBottom.addEventListener("pointerup", endResize);
    resizerBottom.addEventListener("pointercancel", endResize);

    const toggleCollapse = () => {
      const isCollapsed = bottomDrawer.classList.contains("collapsed");
      if (isCollapsed) {
        bottomDrawer.classList.remove("collapsed");
        if (drawerToggleBtn) drawerToggleBtn.setAttribute("aria-expanded", "true");
        const targetH = lastExpandedHeight || 220;
        root.style.setProperty("--bottom-drawer-h", `${targetH}px`);
        resizerBottom.setAttribute("aria-valuenow", String(Math.round(targetH)));
        const activeTab = document.querySelector(".drawer-tab.active");
        if (activeTab && activeTab.getAttribute("data-target") === "terminal" && window.DeskAITerminal) {
          window.DeskAITerminal.fit();
        } else if (activeTab && activeTab.getAttribute("data-target") === "ports" && window.DeskAIPorts) {
          window.DeskAIPorts.refresh();
          window.DeskAIPorts.startPolling();
        }
      } else {
        bottomDrawer.classList.add("collapsed");
        if (drawerToggleBtn) drawerToggleBtn.setAttribute("aria-expanded", "false");
        if (window.DeskAIPorts) window.DeskAIPorts.stopPolling();
      }
    };

    // Double-click to toggle collapse / restore last expanded height
    resizerBottom.addEventListener("dblclick", (e) => {
      e.preventDefault();
      toggleCollapse();
    });

    // Keyboard navigation on resizer (ArrowUp, ArrowDown, Home, End, Enter, Space)
    resizerBottom.addEventListener("keydown", (e) => {
      const step = 16;
      const currentH = parseFloat(getComputedStyle(root).getPropertyValue("--bottom-drawer-h")) || 220;
      const maxH = getMaxH();

      if (e.key === "ArrowUp") {
        e.preventDefault();
        if (bottomDrawer.classList.contains("collapsed")) {
          bottomDrawer.classList.remove("collapsed");
          if (drawerToggleBtn) drawerToggleBtn.setAttribute("aria-expanded", "true");
          const targetH = Math.max(64, lastExpandedHeight || 220);
          root.style.setProperty("--bottom-drawer-h", `${targetH}px`);
          resizerBottom.setAttribute("aria-valuenow", String(Math.round(targetH)));
          lastExpandedHeight = targetH;
        } else {
          const newH = Math.min(maxH, currentH + step);
          root.style.setProperty("--bottom-drawer-h", `${newH}px`);
          resizerBottom.setAttribute("aria-valuenow", String(Math.round(newH)));
          lastExpandedHeight = newH;
        }
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        const newH = currentH - step;
        if (newH < 50) {
          bottomDrawer.classList.add("collapsed");
          if (drawerToggleBtn) drawerToggleBtn.setAttribute("aria-expanded", "false");
          root.style.setProperty("--bottom-drawer-h", "48px");
          resizerBottom.setAttribute("aria-valuenow", "48");
          if (window.DeskAIPorts) window.DeskAIPorts.stopPolling();
        } else {
          root.style.setProperty("--bottom-drawer-h", `${newH}px`);
          resizerBottom.setAttribute("aria-valuenow", String(Math.round(newH)));
          lastExpandedHeight = newH;
        }
      } else if (e.key === "Home") {
        e.preventDefault();
        bottomDrawer.classList.add("collapsed");
        if (drawerToggleBtn) drawerToggleBtn.setAttribute("aria-expanded", "false");
        root.style.setProperty("--bottom-drawer-h", "48px");
        resizerBottom.setAttribute("aria-valuenow", "48");
        if (window.DeskAIPorts) window.DeskAIPorts.stopPolling();
      } else if (e.key === "End") {
        e.preventDefault();
        bottomDrawer.classList.remove("collapsed");
        if (drawerToggleBtn) drawerToggleBtn.setAttribute("aria-expanded", "true");
        root.style.setProperty("--bottom-drawer-h", `${maxH}px`);
        resizerBottom.setAttribute("aria-valuenow", String(maxH));
        lastExpandedHeight = maxH;
      } else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        toggleCollapse();
      }
    });
  }

  window.addEventListener("resize", () => {
    if (window.DeskAITerminal) {
      window.DeskAITerminal.fit();
    }
  });

  // Middle-click (auxclick, button: 1) on editor tabs closes them
  document.addEventListener("auxclick", (e) => {
    if (e.button === 1) {
      const tabEl = e.target.closest(".editor-tab");
      if (tabEl) {
        e.preventDefault();
        const tabId = tabEl.getAttribute("data-tab-id");
        if (tabId && window.EditorManager) {
          window.EditorManager.closeTab(tabId);
        }
      }
    }
  });

  // Horizontal wheel scroll translation on editor tab strip
  const editorTabStrip = document.getElementById("editorTabStrip");
  if (editorTabStrip) {
    editorTabStrip.addEventListener(
      "wheel",
      (e) => {
        if (e.deltaY !== 0) {
          e.preventDefault();
          editorTabStrip.scrollLeft += e.deltaY;
        }
      },
      { passive: false }
    );
  }
}
