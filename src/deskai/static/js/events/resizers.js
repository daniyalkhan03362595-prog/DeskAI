/**
 * Panel and Window Resizing Drag Modules.
 * Built with Pointer Events, RAF throttling, cached geometry, and zero layout thrashing.
 */
import { NativeBridge } from "../bridge.js";
import { createSvgIcon } from "../icons.js";

let terminalFitTimer = null;

function scheduleTerminalFit(delay = 80) {
  if (terminalFitTimer) clearTimeout(terminalFitTimer);
  terminalFitTimer = setTimeout(() => {
    terminalFitTimer = null;
    if (window.DeskAITerminal && typeof window.DeskAITerminal.fit === "function") {
      window.DeskAITerminal.fit();
    }
  }, delay);
}

function flushTerminalFit() {
  if (terminalFitTimer) {
    clearTimeout(terminalFitTimer);
    terminalFitTimer = null;
  }
  if (window.DeskAITerminal && typeof window.DeskAITerminal.fit === "function") {
    window.DeskAITerminal.fit();
  }
}

export function initPanelResizers() {
  const resizerLeft = document.getElementById("resizerLeft");
  const resizerRight = document.getElementById("resizerRight");
  const root = document.documentElement;

  // --------------------------------------------------------------------------
  // Left Explorer Sidebar Resizer (#resizerLeft)
  // --------------------------------------------------------------------------
  if (resizerLeft) {
    let currentLeftW = 280;
    try {
      const stored = localStorage.getItem("deskai_sidebar_left_w");
      if (stored) {
        const parsed = parseFloat(stored);
        if (!isNaN(parsed) && parsed >= 180 && parsed <= 450) {
          currentLeftW = parsed;
          root.style.setProperty("--sidebar-left-w", `${parsed}px`);
        }
      }
    } catch (e) {
      console.warn("Failed to load sidebar left width", e);
    }

    resizerLeft.setAttribute("aria-valuemin", "180");
    resizerLeft.setAttribute("aria-valuemax", "450");
    resizerLeft.setAttribute("aria-valuenow", String(Math.round(currentLeftW)));
    resizerLeft.tabIndex = 0;

    let isResizingLeft = false;
    let cachedRootW = 0;
    let cachedMaxW = 450;
    let latestClientX = 0;
    let rafLeftId = null;

    resizerLeft.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      try {
        resizerLeft.setPointerCapture(e.pointerId);
      } catch (err) {
        // Ignored
      }
      isResizingLeft = true;
      resizerLeft.classList.add("is-resizing", "resizing");
      root.classList.add("is-resizing-col");

      cachedRootW = window.innerWidth;
      const rightW = parseFloat(getComputedStyle(root).getPropertyValue("--sidebar-right-w")) || 360;
      cachedMaxW = Math.min(450, Math.max(180, cachedRootW - rightW - 480 - 2));
      latestClientX = e.clientX;
    });

    resizerLeft.addEventListener("pointermove", (e) => {
      if (!isResizingLeft) return;
      e.preventDefault();
      latestClientX = e.clientX;

      if (!rafLeftId) {
        rafLeftId = requestAnimationFrame(() => {
          rafLeftId = null;
          const newW = Math.max(180, Math.min(cachedMaxW, latestClientX));
          root.style.setProperty("--sidebar-left-w", `${newW}px`);
          resizerLeft.setAttribute("aria-valuenow", String(Math.round(newW)));
          currentLeftW = newW;
        });
      }
    });

    const endLeftResize = (e) => {
      if (!isResizingLeft) return;
      isResizingLeft = false;
      if (rafLeftId) {
        cancelAnimationFrame(rafLeftId);
        rafLeftId = null;
      }
      try {
        if (resizerLeft.hasPointerCapture && resizerLeft.hasPointerCapture(e.pointerId)) {
          resizerLeft.releasePointerCapture(e.pointerId);
        }
      } catch (err) {
        // Ignored
      }
      resizerLeft.classList.remove("is-resizing", "resizing");
      root.classList.remove("is-resizing-col");

      try {
        localStorage.setItem("deskai_sidebar_left_w", String(Math.round(currentLeftW)));
      } catch (err) {
        console.warn("Failed to persist sidebar left width", err);
      }
    };

    resizerLeft.addEventListener("pointerup", endLeftResize);
    resizerLeft.addEventListener("pointercancel", endLeftResize);

    // Double-click toggles explorer collapse state
    resizerLeft.addEventListener("dblclick", (e) => {
      e.preventDefault();
      const toggleBtn = document.getElementById("btnToggleSidebar") || document.getElementById("btnExpandSidebar");
      if (toggleBtn) {
        toggleBtn.click();
      }
    });

    // Keyboard accessibility for resizerLeft
    resizerLeft.addEventListener("keydown", (e) => {
      const step = 16;
      const rootW = window.innerWidth;
      const rightW = parseFloat(getComputedStyle(root).getPropertyValue("--sidebar-right-w")) || 360;
      const maxW = Math.min(450, Math.max(180, rootW - rightW - 480 - 2));

      if (e.key === "ArrowLeft") {
        e.preventDefault();
        const newW = Math.max(180, currentLeftW - step);
        root.style.setProperty("--sidebar-left-w", `${newW}px`);
        resizerLeft.setAttribute("aria-valuenow", String(Math.round(newW)));
        currentLeftW = newW;
        try { localStorage.setItem("deskai_sidebar_left_w", String(Math.round(newW))); } catch (err) {}
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        const newW = Math.min(maxW, currentLeftW + step);
        root.style.setProperty("--sidebar-left-w", `${newW}px`);
        resizerLeft.setAttribute("aria-valuenow", String(Math.round(newW)));
        currentLeftW = newW;
        try { localStorage.setItem("deskai_sidebar_left_w", String(Math.round(newW))); } catch (err) {}
      } else if (e.key === "Home") {
        e.preventDefault();
        root.style.setProperty("--sidebar-left-w", "180px");
        resizerLeft.setAttribute("aria-valuenow", "180");
        currentLeftW = 180;
        try { localStorage.setItem("deskai_sidebar_left_w", "180"); } catch (err) {}
      } else if (e.key === "End") {
        e.preventDefault();
        root.style.setProperty("--sidebar-left-w", `${maxW}px`);
        resizerLeft.setAttribute("aria-valuenow", String(Math.round(maxW)));
        currentLeftW = maxW;
        try { localStorage.setItem("deskai_sidebar_left_w", String(Math.round(maxW))); } catch (err) {}
      } else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        const toggleBtn = document.getElementById("btnToggleSidebar") || document.getElementById("btnExpandSidebar");
        if (toggleBtn) toggleBtn.click();
      }
    });
  }

  // --------------------------------------------------------------------------
  // Right Chat Sidebar Resizer (#resizerRight)
  // --------------------------------------------------------------------------
  if (resizerRight) {
    let currentRightW = 360;
    try {
      const stored = localStorage.getItem("deskai_sidebar_right_w");
      if (stored) {
        const parsed = parseFloat(stored);
        if (!isNaN(parsed) && parsed >= 200 && parsed <= 500) {
          currentRightW = parsed;
          root.style.setProperty("--sidebar-right-w", `${parsed}px`);
        }
      }
    } catch (e) {
      console.warn("Failed to load sidebar right width", e);
    }

    resizerRight.setAttribute("aria-valuemin", "200");
    resizerRight.setAttribute("aria-valuemax", "500");
    resizerRight.setAttribute("aria-valuenow", String(Math.round(currentRightW)));
    resizerRight.tabIndex = 0;

    let isResizingRight = false;
    let cachedRootW = 0;
    let cachedMaxW = 500;
    let latestClientX = 0;
    let rafRightId = null;

    resizerRight.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      try {
        resizerRight.setPointerCapture(e.pointerId);
      } catch (err) {
        // Ignored
      }
      isResizingRight = true;
      resizerRight.classList.add("is-resizing", "resizing");
      root.classList.add("is-resizing-col");

      cachedRootW = window.innerWidth;
      const leftW = parseFloat(getComputedStyle(root).getPropertyValue("--sidebar-left-w")) || 280;
      cachedMaxW = Math.min(500, Math.max(200, cachedRootW - leftW - 480 - 2));
      latestClientX = e.clientX;
    });

    resizerRight.addEventListener("pointermove", (e) => {
      if (!isResizingRight) return;
      e.preventDefault();
      latestClientX = e.clientX;

      if (!rafRightId) {
        rafRightId = requestAnimationFrame(() => {
          rafRightId = null;
          const newW = Math.max(200, Math.min(cachedMaxW, cachedRootW - latestClientX));
          root.style.setProperty("--sidebar-right-w", `${newW}px`);
          resizerRight.setAttribute("aria-valuenow", String(Math.round(newW)));
          currentRightW = newW;
        });
      }
    });

    const endRightResize = (e) => {
      if (!isResizingRight) return;
      isResizingRight = false;
      if (rafRightId) {
        cancelAnimationFrame(rafRightId);
        rafRightId = null;
      }
      try {
        if (resizerRight.hasPointerCapture && resizerRight.hasPointerCapture(e.pointerId)) {
          resizerRight.releasePointerCapture(e.pointerId);
        }
      } catch (err) {
        // Ignored
      }
      resizerRight.classList.remove("is-resizing", "resizing");
      root.classList.remove("is-resizing-col");

      try {
        localStorage.setItem("deskai_sidebar_right_w", String(Math.round(currentRightW)));
      } catch (err) {
        console.warn("Failed to persist sidebar right width", err);
      }
    };

    resizerRight.addEventListener("pointerup", endRightResize);
    resizerRight.addEventListener("pointercancel", endRightResize);

    // Double-click resets right sidebar to default width (360px)
    resizerRight.addEventListener("dblclick", (e) => {
      e.preventDefault();
      const defaultW = 360;
      root.style.setProperty("--sidebar-right-w", `${defaultW}px`);
      resizerRight.setAttribute("aria-valuenow", String(defaultW));
      currentRightW = defaultW;
      try { localStorage.setItem("deskai_sidebar_right_w", String(defaultW)); } catch (err) {}
    });

    // Keyboard accessibility for resizerRight
    resizerRight.addEventListener("keydown", (e) => {
      const step = 16;
      const rootW = window.innerWidth;
      const leftW = parseFloat(getComputedStyle(root).getPropertyValue("--sidebar-left-w")) || 280;
      const maxW = Math.min(500, Math.max(200, rootW - leftW - 480 - 2));

      if (e.key === "ArrowLeft") {
        e.preventDefault();
        const newW = Math.min(maxW, currentRightW + step);
        root.style.setProperty("--sidebar-right-w", `${newW}px`);
        resizerRight.setAttribute("aria-valuenow", String(Math.round(newW)));
        currentRightW = newW;
        try { localStorage.setItem("deskai_sidebar_right_w", String(Math.round(newW))); } catch (err) {}
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        const newW = Math.max(200, currentRightW - step);
        root.style.setProperty("--sidebar-right-w", `${newW}px`);
        resizerRight.setAttribute("aria-valuenow", String(Math.round(newW)));
        currentRightW = newW;
        try { localStorage.setItem("deskai_sidebar_right_w", String(Math.round(newW))); } catch (err) {}
      } else if (e.key === "Home") {
        e.preventDefault();
        root.style.setProperty("--sidebar-right-w", "200px");
        resizerRight.setAttribute("aria-valuenow", "200");
        currentRightW = 200;
        try { localStorage.setItem("deskai_sidebar_right_w", "200"); } catch (err) {}
      } else if (e.key === "End") {
        e.preventDefault();
        root.style.setProperty("--sidebar-right-w", `${maxW}px`);
        resizerRight.setAttribute("aria-valuenow", String(Math.round(maxW)));
        currentRightW = maxW;
        try { localStorage.setItem("deskai_sidebar_right_w", String(Math.round(maxW))); } catch (err) {}
      }
    });
  }

  // --------------------------------------------------------------------------
  // Bottom Drawer Resizer (#resizerBottom)
  // --------------------------------------------------------------------------
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
    resizerBottom.tabIndex = 0;

    let isResizing = false;
    let startY = 0;
    let startHeight = 0;
    let cachedMaxH = 800;
    let latestBottomClientY = 0;
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
      root.classList.add("is-resizing-row");
      startY = e.clientY;
      startHeight = parseFloat(getComputedStyle(root).getPropertyValue("--bottom-drawer-h")) || lastExpandedHeight || 220;
      cachedMaxH = getMaxH();
      latestBottomClientY = e.clientY;
    });

    resizerBottom.addEventListener("pointermove", (e) => {
      if (!isResizing) return;
      e.preventDefault();
      latestBottomClientY = e.clientY;

      if (!rafId) {
        rafId = requestAnimationFrame(() => {
          rafId = null;
          const rawH = startHeight + (startY - latestBottomClientY);

          if (rawH < 50) {
            clearDrawerMaximized();
            bottomDrawer.classList.add("collapsed");
            if (drawerToggleBtn) drawerToggleBtn.setAttribute("aria-expanded", "false");
            root.style.setProperty("--bottom-drawer-h", "48px");
            resizerBottom.setAttribute("aria-valuenow", "48");
            if (window.DeskAIPorts) window.DeskAIPorts.stopPolling();
          } else {
            const clampedH = Math.max(48, Math.min(cachedMaxH, rawH));
            if (bottomDrawer.classList.contains("collapsed")) {
              bottomDrawer.classList.remove("collapsed");
              if (drawerToggleBtn) drawerToggleBtn.setAttribute("aria-expanded", "true");
              const activeTab = document.querySelector(".drawer-tab.active");
              if (activeTab && activeTab.getAttribute("data-target") === "ports" && window.DeskAIPorts) {
                window.DeskAIPorts.refresh();
                window.DeskAIPorts.startPolling();
              }
            }
            const roundedH = Math.round(clampedH);
            root.style.setProperty("--bottom-drawer-h", `${roundedH}px`);
            resizerBottom.setAttribute("aria-valuenow", String(roundedH));
            lastExpandedHeight = roundedH;
            scheduleTerminalFit(80);
          }
        });
      }
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
      root.classList.remove("is-resizing-row");
      flushTerminalFit();
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
