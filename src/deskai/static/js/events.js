/**
 * Global Event Dispatcher & Action Router Module.
 */
import { NativeBridge } from "./bridge.js";
import { store } from "./state.js";
import { toggleTheme } from "./theme.js";
import { createSvgIcon } from "./icons.js";
import { initKeyboardShortcuts } from "./events/shortcuts.js";
import { initPanelResizers, initHeaderAndWindowResizers } from "./events/resizers.js";

export function initGlobalEvents() {
  // 1. Drag & Drop Navigation Lock
  window.addEventListener("dragover", (e) => e.preventDefault(), false);
  window.addEventListener("drop", (e) => e.preventDefault(), false);

  // 2. Universal Link Click Interceptor
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

  // 3. Action Router
  document.addEventListener("click", async (e) => {
    const trigger = e.target.closest("[data-action]");
    if (!trigger) return;

    if (trigger.closest(".bubble-body, .tab-label, .markdown-surface")) {
      return;
    }
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

      case "toggle-sidebar": {
        const appBody = document.getElementById("appBody");
        const sidebar = document.getElementById("sidebarLeft");
        const resizer = document.getElementById("resizerLeft");
        const toggleBtn = document.getElementById("btnToggleSidebar");
        if (appBody && sidebar) {
          const isCollapsed = appBody.classList.toggle("sidebar-left-collapsed");
          sidebar.classList.toggle("collapsed", isCollapsed);
          if (resizer) resizer.classList.toggle("collapsed", isCollapsed);
          if (toggleBtn) {
            toggleBtn.classList.toggle("active", !isCollapsed);
            toggleBtn.setAttribute("aria-checked", String(!isCollapsed));
            toggleBtn.setAttribute("title", isCollapsed ? "Expand Explorer Sidebar" : "Collapse Explorer Sidebar");
          }
        }
        break;
      }

      case "kill-terminal":
        if (window.DeskAITerminal) {
          window.DeskAITerminal.kill();
        }
        break;

      case "new-terminal":
        if (window.DeskAITerminal) {
          window.DeskAITerminal.newSession();
        }
        break;

      case "maximize-drawer": {
        const stage = document.getElementById("editorStage");
        const drawer = document.getElementById("bottomDrawer");
        const btn = document.getElementById("btnMaximizeDrawer");
        if (stage && drawer) {
          if (drawer.classList.contains("collapsed")) {
            drawer.classList.remove("collapsed");
            const toggleBtn = document.getElementById("drawerToggleBtn");
            if (toggleBtn) toggleBtn.setAttribute("aria-expanded", "true");
          }

          const isMaximized = stage.classList.toggle("drawer-maximized");
          if (btn) {
            btn.setAttribute("aria-expanded", String(isMaximized));
            btn.setAttribute("title", isMaximized ? "Restore Terminal Panel Size" : "Maximize Terminal Panel");
            btn.setAttribute("aria-label", isMaximized ? "Restore Terminal Panel Size" : "Maximize Terminal Panel");
            btn.replaceChildren(createSvgIcon(isMaximized ? "restore" : "maximize", 14));
          }

          if (window.DeskAITerminal) {
            window.DeskAITerminal.fit();
          }
        }
        break;
      }

      case "toggle-drawer": {
        const drawer = document.getElementById("bottomDrawer");
        const stage = document.getElementById("editorStage");
        if (drawer) {
          const isCollapsed = drawer.classList.toggle("collapsed");
          trigger.setAttribute("aria-expanded", String(!isCollapsed));
          if (isCollapsed) {
            if (stage && stage.classList.contains("drawer-maximized")) {
              stage.classList.remove("drawer-maximized");
              const maxBtn = document.getElementById("btnMaximizeDrawer");
              if (maxBtn) {
                maxBtn.setAttribute("aria-expanded", "false");
                maxBtn.setAttribute("title", "Maximize Terminal Panel");
                maxBtn.setAttribute("aria-label", "Maximize Terminal Panel");
                maxBtn.replaceChildren(createSvgIcon("maximize", 14));
              }
            }
            if (window.DeskAIPorts) window.DeskAIPorts.stopPolling();
          } else {
            const activeTab = document.querySelector(".drawer-tab.active");
            if (activeTab && activeTab.getAttribute("data-target") === "ports" && window.DeskAIPorts) {
              window.DeskAIPorts.refresh();
              window.DeskAIPorts.startPolling();
            } else if (activeTab && activeTab.getAttribute("data-target") === "terminal" && window.DeskAITerminal) {
              window.DeskAITerminal.fit();
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
          t.setAttribute("tabindex", "-1");
        });
        trigger.classList.add("active");
        trigger.setAttribute("aria-selected", "true");
        trigger.setAttribute("tabindex", "0");

        document.querySelectorAll(".drawer-panel").forEach(panel => {
          if (panel.id === `${target}Panel`) {
            panel.classList.add("active");
            panel.removeAttribute("hidden");
          } else {
            panel.classList.remove("active");
            panel.setAttribute("hidden", "");
          }
        });

        // Toggle terminal action buttons visibility in drawer header
        const btnNewTerm = document.getElementById("btnNewTerminal");
        const btnKillTerm = document.getElementById("btnKillTerminalHeader");
        const isTerminalTab = target === "terminal";
        if (btnNewTerm) btnNewTerm.classList.toggle("is-hidden", !isTerminalTab);
        if (btnKillTerm) btnKillTerm.classList.toggle("is-hidden", !isTerminalTab);

        if (target === "terminal" && window.DeskAITerminal) {
          window.DeskAITerminal.onTabShown();
        } else if (target === "ports" && window.DeskAIPorts) {
          window.DeskAIPorts.refresh();
          window.DeskAIPorts.startPolling();
        } else if (target === "problems" && window.DeskAIProblems) {
          window.DeskAIProblems.onShow();
        } else if (window.DeskAIPorts) {
          window.DeskAIPorts.stopPolling();
        }
        break;
      }

      case "problems-filter": {
        const sev = trigger.getAttribute("data-severity");
        if (window.DeskAIProblems && sev) {
          window.DeskAIProblems.toggleFilter(sev);
        }
        break;
      }
      case "problems-collapse": {
        if (window.DeskAIProblems) {
          window.DeskAIProblems.toggleCollapseAll();
        }
        break;
      }
      case "problems-run": {
        if (window.DeskAIProblems) {
          window.DeskAIProblems.runWorkspace();
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

  // 4. Keyboard Shortcuts
  initKeyboardShortcuts(store);

  // 5. Panel & Window Resizers
  initPanelResizers();
  initHeaderAndWindowResizers();
}
