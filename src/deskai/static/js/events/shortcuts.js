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
}
