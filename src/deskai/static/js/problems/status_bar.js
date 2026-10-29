/**
 * StatusBarProblemsWidget: Persistent status bar widget for workspace problems.
 * Displays live error and warning counts and switches to the problems panel on click.
 */

export class StatusBarProblemsWidget {
  constructor(store) {
    this.store = store;
    this.buttonEl = document.getElementById("statusBarProblems");
    this.errEl = document.getElementById("statusBarErrCount");
    this.warnEl = document.getElementById("statusBarWarnCount");

    this._initEvents();
    if (this.store && typeof this.store.subscribe === "function") {
      this.store.subscribe(() => this.sync());
    }
    this.sync();
  }

  _initEvents() {
    if (!this.buttonEl) return;
    this.buttonEl.addEventListener("click", () => {
      this.toggleProblemsPanel();
    });
  }

  sync() {
    if (!this.buttonEl || !this.store) return;
    const { errors, warnings } = this.store.counts();

    if (this.errEl) {
      this.errEl.textContent = `✖ ${errors}`;
    }
    if (this.warnEl) {
      this.warnEl.textContent = `▲ ${warnings}`;
    }

    this.buttonEl.setAttribute("data-has-errors", String(errors > 0));
    this.buttonEl.setAttribute("data-has-warnings", String(warnings > 0));

    const title = `Workspace Problems: ${errors} errors, ${warnings} warnings`;
    this.buttonEl.setAttribute("title", title);
    this.buttonEl.setAttribute("aria-label", title);
  }

  toggleProblemsPanel() {
    const drawer = document.getElementById("bottomDrawer");
    const tabProblems = document.getElementById("tab-problems");
    const toggleBtn = document.getElementById("drawerToggleBtn");

    const isMinimized = drawer && (drawer.classList.contains("minimized") || drawer.style.display === "none");
    if (isMinimized && toggleBtn) {
      toggleBtn.click();
    }

    if (tabProblems) {
      tabProblems.click();
      tabProblems.focus();
    }
  }
}
