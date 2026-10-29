/**
 * In-Editor Diagnostics Controller for CodeMirror 6.
 * Renders gutter dots, in-editor wavy squiggles, and floating hover cards.
 */

export class EditorDiagnosticsController {
  constructor() {
    this.tooltipEl = null;
    this.hideTimer = null;
    this.currentDiagnostic = null;
    this.boundContainers = new WeakSet();
    this._initTooltip();
    this._initGlobalListeners();
  }

  _initTooltip() {
    if (typeof document === "undefined") return;
    let el = document.getElementById("problemEditorTooltip");
    if (!el) {
      el = document.createElement("div");
      el.id = "problemEditorTooltip";
      el.className = "problem-editor-tooltip";
      el.setAttribute("role", "tooltip");
      el.setAttribute("aria-hidden", "true");
      el.style.display = "none";
      el.addEventListener("mouseenter", () => this.cancelHide());
      el.addEventListener("mouseleave", () => this.scheduleHide());
      document.body.appendChild(el);
    }
    this.tooltipEl = el;
  }

  _initGlobalListeners() {
    if (typeof window === "undefined") return;
    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        this.hideTooltip();
      }
    });
  }

  cancelHide() {
    if (this.hideTimer) {
      clearTimeout(this.hideTimer);
      this.hideTimer = null;
    }
  }

  scheduleHide(delay = 180) {
    this.cancelHide();
    this.hideTimer = setTimeout(() => {
      this.hideTooltip();
    }, delay);
  }

  showTooltip(targetEl, diag) {
    if (!this.tooltipEl || !targetEl || !diag) return;
    this.cancelHide();
    this.currentDiagnostic = diag;

    this.tooltipEl.replaceChildren();

    const header = document.createElement("div");
    header.className = "problem-tooltip-header";

    const badge = document.createElement("span");
    const sev = (diag.severity || "error").toLowerCase();
    badge.className = `problem-badge badge-${sev}`;
    badge.textContent = sev.charAt(0).toUpperCase() + sev.slice(1);
    header.appendChild(badge);

    if (diag.code) {
      const codeSpan = document.createElement("span");
      codeSpan.className = "problem-tooltip-code";
      codeSpan.textContent = `[${diag.code}]`;
      header.appendChild(codeSpan);
    }

    const lineNum = diag.range ? diag.range.startLine : diag.start_line || diag.line || 1;
    const colNum = diag.range ? diag.range.startCol : diag.start_col || diag.col || 1;

    const locSpan = document.createElement("span");
    locSpan.className = "problem-tooltip-loc";
    locSpan.textContent = `Ln ${lineNum}, Col ${colNum}`;
    header.appendChild(locSpan);

    this.tooltipEl.appendChild(header);

    const msgEl = document.createElement("div");
    msgEl.className = "problem-tooltip-message";
    msgEl.textContent = diag.message || "Unknown error";
    this.tooltipEl.appendChild(msgEl);

    if (diag.ai_fixable !== false) {
      const actionsEl = document.createElement("div");
      actionsEl.className = "problem-tooltip-actions";

      const fixBtn = document.createElement("button");
      fixBtn.className = "problem-action-btn problem-btn-ai-fix";
      fixBtn.type = "button";
      fixBtn.textContent = "✨ Fix with AI";
      fixBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        this.hideTooltip();
        if (window.DeskAIProblems && typeof window.DeskAIProblems.triggerAiFix === "function") {
          window.DeskAIProblems.triggerAiFix(diag);
        }
      });
      actionsEl.appendChild(fixBtn);

      const explainBtn = document.createElement("button");
      explainBtn.className = "problem-action-btn problem-btn-explain";
      explainBtn.type = "button";
      explainBtn.textContent = "💡 Explain";
      explainBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        this.hideTooltip();
        if (window.DeskAIProblems && typeof window.DeskAIProblems.triggerAiExplain === "function") {
          window.DeskAIProblems.triggerAiExplain(diag);
        }
      });
      actionsEl.appendChild(explainBtn);

      this.tooltipEl.appendChild(actionsEl);
    }

    this.tooltipEl.style.display = "block";
    this.tooltipEl.setAttribute("aria-hidden", "false");

    const rect = targetEl.getBoundingClientRect();
    const tooltipRect = this.tooltipEl.getBoundingClientRect();
    let top = rect.top - tooltipRect.height - 8;
    if (top < 10) {
      top = rect.bottom + 8;
    }
    const left = Math.max(10, Math.min(rect.left, window.innerWidth - tooltipRect.width - 10));

    this.tooltipEl.style.top = `${Math.round(top)}px`;
    this.tooltipEl.style.left = `${Math.round(left)}px`;
  }

  hideTooltip() {
    if (!this.tooltipEl) return;
    this.tooltipEl.style.display = "none";
    this.tooltipEl.setAttribute("aria-hidden", "true");
    this.currentDiagnostic = null;
  }

  _getLineElement(view, lineNum) {
    try {
      if (!view || !view.state || !view.state.doc) return null;
      if (lineNum < 1 || lineNum > view.state.doc.lines) return null;
      const pos = view.state.doc.line(lineNum).from;
      const domAt = view.domAtPos(pos);
      if (!domAt || !domAt.node) return null;
      let curr = domAt.node.nodeType === 1 ? domAt.node : domAt.node.parentElement;
      while (curr && curr !== view.dom) {
        if (curr.classList && curr.classList.contains("cm-line")) {
          return curr;
        }
        curr = curr.parentElement;
      }
    } catch {
      // Line might not be in DOM yet
    }
    return null;
  }

  clearDecorations(container) {
    if (!container) return;
    const lines = container.querySelectorAll(
      ".cm-line-diagnostic-error, .cm-line-diagnostic-warning, .cm-line-diagnostic-info"
    );
    for (const l of lines) {
      l.classList.remove("cm-line-diagnostic-error", "cm-line-diagnostic-warning", "cm-line-diagnostic-info");
      l.removeAttribute("data-diagnostic-line");
      delete l._diagnosticData;
    }
    const gutters = container.querySelectorAll(".cm-gutter-diagnostic");
    for (const g of gutters) {
      g.classList.remove(
        "cm-gutter-diagnostic",
        "cm-gutter-diagnostic-error",
        "cm-gutter-diagnostic-warning",
        "cm-gutter-diagnostic-info"
      );
      delete g._diagnosticData;
    }
  }

  update(buffer = null) {
    if (!buffer && window.EditorManager) {
      const activeId = window.EditorManager.activeTabId;
      if (activeId && window.EditorManager.buffers) {
        buffer = window.EditorManager.buffers.get(activeId);
      }
    }
    if (!buffer || !buffer.container || !buffer.view) return;

    this.clearDecorations(buffer.container);

    if (!window.DeskAIProblems || !window.DeskAIProblems.store) return;
    const store = window.DeskAIProblems.store;

    const filePath = buffer.path || "";
    if (!filePath) return;

    const allDiags = store.all();
    const matchedDiags = allDiags.filter((d) => {
      const dFile = (d.file || "").replace(/\\/g, "/");
      const bFile = filePath.replace(/\\/g, "/");
      return bFile.endsWith(dFile) || dFile.endsWith(bFile);
    });

    if (matchedDiags.length === 0) return;

    if (!this.boundContainers.has(buffer.container)) {
      this.boundContainers.add(buffer.container);
      buffer.container.addEventListener("mouseover", (e) => {
        const lineEl = e.target.closest(
          ".cm-line-diagnostic-error, .cm-line-diagnostic-warning, .cm-line-diagnostic-info"
        );
        const gutterEl = e.target.closest(".cm-gutter-diagnostic");
        const target = lineEl || gutterEl;
        if (target && target._diagnosticData) {
          this.showTooltip(target, target._diagnosticData);
        }
      });
      buffer.container.addEventListener("mouseout", (e) => {
        const lineEl = e.target.closest(
          ".cm-line-diagnostic-error, .cm-line-diagnostic-warning, .cm-line-diagnostic-info"
        );
        const gutterEl = e.target.closest(".cm-gutter-diagnostic");
        if (lineEl || gutterEl) {
          this.scheduleHide();
        }
      });
    }

    const gutterEls = buffer.container.querySelectorAll(".cm-gutter.cm-lineNumbers .cm-gutterElement");
    const docLines = buffer.view && buffer.view.state && buffer.view.state.doc ? buffer.view.state.doc.lines : 1;

    for (const diag of matchedDiags) {
      const rawLine = diag.range ? diag.range.startLine : diag.start_line || diag.line || 1;
      const lineNum = Math.min(Math.max(Number(rawLine) || 1, 1), docLines);
      const sev = (diag.severity || "error").toLowerCase();

      // Gutter decoration
      for (const g of gutterEls) {
        if (g.textContent.trim() === String(lineNum)) {
          g.classList.add("cm-gutter-diagnostic", `cm-gutter-diagnostic-${sev}`);
          g._diagnosticData = diag;
          break;
        }
      }

      // Line squiggle decoration
      const lineEl = this._getLineElement(buffer.view, lineNum);
      if (lineEl) {
        lineEl.classList.add(`cm-line-diagnostic-${sev}`);
        lineEl.setAttribute("data-diagnostic-line", String(lineNum));
        lineEl._diagnosticData = diag;
      }
    }
  }
}

export const editorDiagnostics = new EditorDiagnosticsController();
if (typeof window !== "undefined") {
  window.DeskAIEditorDiagnostics = editorDiagnostics;
}
