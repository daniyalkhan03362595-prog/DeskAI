/**
 * Global Keyboard Shortcuts & Roving Tabindex Navigation Module.
 */

export function initKeyboardShortcuts(store) {
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
      if (!(isCmd && (key === "`" || e.code === "Backquote"))) {
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
    } else if (isCmd && e.shiftKey && (key === "`" || e.code === "Backquote")) {
      e.preventDefault();
      const newTermBtn = document.getElementById("btnNewTerminal");
      if (newTermBtn) newTermBtn.click();
    } else if (isCmd && (key === "`" || e.code === "Backquote")) {
      e.preventDefault();
      const drawerToggleBtn = document.getElementById("drawerToggleBtn");
      if (drawerToggleBtn) drawerToggleBtn.click();
    }
  });

  // Drawer Tabs roving tabindex navigation
  const drawerTabsContainer = document.querySelector(".drawer-tabs");
  if (drawerTabsContainer) {
    drawerTabsContainer.addEventListener("keydown", (e) => {
      const tabs = Array.from(drawerTabsContainer.querySelectorAll('.drawer-tab[role="tab"]'));
      const currentIndex = tabs.indexOf(document.activeElement);
      if (currentIndex === -1) return;

      if (e.key === "ArrowRight" || e.key === "ArrowDown") {
        e.preventDefault();
        const nextIndex = (currentIndex + 1) % tabs.length;
        tabs[nextIndex].focus();
        tabs[nextIndex].click();
      } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
        e.preventDefault();
        const prevIndex = (currentIndex - 1 + tabs.length) % tabs.length;
        tabs[prevIndex].focus();
        tabs[prevIndex].click();
      } else if (e.key === "Home") {
        e.preventDefault();
        tabs[0].focus();
        tabs[0].click();
      } else if (e.key === "End") {
        e.preventDefault();
        tabs[tabs.length - 1].focus();
        tabs[tabs.length - 1].click();
      }
    });
  }

  // Drawer Actions toolbar roving tabindex navigation
  const drawerActions = document.getElementById("drawerActions");
  if (drawerActions) {
    function updateActionsFocus(targetBtn, buttons) {
      buttons.forEach((btn) => {
        btn.setAttribute("tabindex", btn === targetBtn ? "0" : "-1");
      });
      targetBtn.focus();
    }

    drawerActions.addEventListener("keydown", (e) => {
      const visibleButtons = Array.from(drawerActions.querySelectorAll("button:not(.is-hidden):not([disabled])"));
      if (visibleButtons.length === 0) return;

      const activeEl = document.activeElement;
      const currentIndex = visibleButtons.indexOf(activeEl);
      if (currentIndex === -1) return;

      if (e.key === "ArrowRight" || e.key === "ArrowDown") {
        e.preventDefault();
        const nextIndex = (currentIndex + 1) % visibleButtons.length;
        updateActionsFocus(visibleButtons[nextIndex], visibleButtons);
      } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
        e.preventDefault();
        const prevIndex = (currentIndex - 1 + visibleButtons.length) % visibleButtons.length;
        updateActionsFocus(visibleButtons[prevIndex], visibleButtons);
      } else if (e.key === "Home") {
        e.preventDefault();
        updateActionsFocus(visibleButtons[0], visibleButtons);
      } else if (e.key === "End") {
        e.preventDefault();
        updateActionsFocus(visibleButtons[visibleButtons.length - 1], visibleButtons);
      }
    });
  }
}

export function syncDrawerActionsTabindex() {
  const container = document.getElementById("drawerActions");
  if (!container) return;
  const visibleButtons = Array.from(container.querySelectorAll("button:not(.is-hidden)"));
  if (visibleButtons.length === 0) return;
  const hasFocusable = visibleButtons.some((b) => b.getAttribute("tabindex") === "0");
  if (!hasFocusable) {
    visibleButtons.forEach((b) => b.setAttribute("tabindex", "-1"));
    const firstEnabled = visibleButtons.find((b) => !b.disabled) || visibleButtons[0];
    if (firstEnabled) firstEnabled.setAttribute("tabindex", "0");
  }
}
