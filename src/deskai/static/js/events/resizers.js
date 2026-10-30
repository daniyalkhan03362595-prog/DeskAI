/**
 * Panel and Window Resizing Drag Modules.
 */
import { NativeBridge } from "../bridge.js";
import { createSvgIcon } from "../icons.js";

export function initPanelResizers() {
  const resizerLeft = document.getElementById("resizerLeft");
  const resizerRight = document.getElementById("resizerRight");
  const root = document.documentElement;

  if (resizerLeft) {
    resizerLeft.addEventListener("mousedown", (e) => {
      e.preventDefault();
      resizerLeft.classList.add("resizing");
      const onMouseMove = (ev) => {
        const rootW = window.innerWidth;
        const rightW = parseInt(getComputedStyle(root).getPropertyValue("--sidebar-right-w") || "210", 10);
        const maxW = Math.min(450, Math.max(180, rootW - rightW - 480 - 2));
        const newW = Math.max(180, Math.min(maxW, ev.clientX));
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
        const rootW = window.innerWidth;
        const leftW = parseInt(getComputedStyle(root).getPropertyValue("--sidebar-left-w") || "200", 10);
        const maxW = Math.min(500, Math.max(200, rootW - leftW - 480 - 2));
        const newW = Math.max(200, Math.min(maxW, rootW - ev.clientX));
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

  const clearDrawerMaximized = () => {
    const stage = document.getElementById("editorStage");
    if (stage && stage.classList.contains("drawer-maximized")) {
      stage.classList.remove("drawer-maximized");
      const maxBtn = document.getElementById("btnMaximizeDrawer");
      if (maxBtn) {
        const activeTab = document.querySelector(".drawer-tab.active");
        const target = activeTab ? activeTab.getAttribute("data-target") : "terminal";
        const tabLabel = target ? (target.charAt(0).toUpperCase() + target.slice(1)) : "Panel";
        maxBtn.setAttribute("aria-expanded", "false");
        maxBtn.setAttribute("title", `Maximize ${tabLabel} Panel`);
        maxBtn.setAttribute("aria-label", `Maximize ${tabLabel} Panel`);
        maxBtn.replaceChildren(createSvgIcon("maximize", 14));
      }
    }
  };

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
        // Ignored
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
          clearDrawerMaximized();
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
        clearDrawerMaximized();
        bottomDrawer.classList.add("collapsed");
        if (drawerToggleBtn) drawerToggleBtn.setAttribute("aria-expanded", "false");
        if (window.DeskAIPorts) window.DeskAIPorts.stopPolling();
      }
    };

    resizerBottom.addEventListener("dblclick", (e) => {
      e.preventDefault();
      toggleCollapse();
    });

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
          clearDrawerMaximized();
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
        clearDrawerMaximized();
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

export function initHeaderAndWindowResizers() {
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

  const resizeHandles = document.getElementById("windowResizeHandles");
  if (resizeHandles) {
    resizeHandles.addEventListener("mousedown", (e) => {
      const handle = e.target.closest(".resize-handle");
      if (handle && e.button === 0) {
        e.preventDefault();
        e.stopPropagation();
        const edge = handle.dataset.edge;
        if (!edge) return;

        NativeBridge.windowControl("resize_start", edge, e.timeStamp || Date.now());

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
