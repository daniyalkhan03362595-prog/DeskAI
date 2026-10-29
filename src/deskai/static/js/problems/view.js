/**
 * ProblemsView: Safe DOM renderer and keyboard interaction model for the Problems panel.
 * Strictly adheres to zero raw markup injection, WCAG 2.1 AA, and roving tabindex.
 */

import { createSvgIcon } from "../icons.js";

const LABEL = {
  error: "Error",
  warning: "Warning",
  info: "Info"
};

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function renderGroups(container, grouped, ui) {
  if (!grouped || grouped.size === 0) {
    const emptySpan = el("span", "problems-empty", "No problems have been detected in the workspace.");
    container.replaceChildren(emptySpan);
    return;
  }

  const frag = document.createDocumentFragment();
  let firstItem = true;

  for (const [file, items] of grouped) {
    const group = el("div", "problems-group");
    const isCollapsed = ui.collapsed.has(file);
    const groupId = `pg-${ui.idFor(file)}`;

    const head = el("button", "problems-file");
    head.type = "button";
    head.setAttribute("aria-expanded", String(!isCollapsed));
    head.setAttribute("aria-controls", groupId);
    head.dataset.file = file;
    head.tabIndex = firstItem && !ui.focusedId ? 0 : -1;
    if (firstItem && !ui.focusedId) firstItem = false;

    const chevron = createSvgIcon(isCollapsed ? "chevron-right" : "chevron-down", 12, "problems-chevron");
    const nameSpan = el("span", "problems-file-name", file);
    const countSpan = el("span", "problems-file-count", `(${items.length})`);
    head.append(chevron, nameSpan, countSpan);

    const list = el("ul", "problems-list");
    list.id = groupId;
    list.setAttribute("role", "list");
    list.hidden = isCollapsed;

    if (!isCollapsed) {
      for (const d of items) {
        const row = renderItem(d, ui, firstItem);
        if (firstItem && !ui.focusedId) firstItem = false;
        list.appendChild(row);
      }
    }

    group.append(head, list);
    frag.appendChild(group);
  }

  container.replaceChildren(frag);

  // Restore focus if a previous element was focused
  if (ui.focusedId) {
    const target = container.querySelector(`[data-id="${ui.focusedId}"]`) ||
                   container.querySelector(`[data-file="${ui.focusedId}"]`);
    if (target) {
      // Set roving tabindex
      container.querySelectorAll(".problems-file, .problem-item").forEach(b => { b.tabIndex = -1; });
      target.tabIndex = 0;
      target.focus();
    }
  }
}

function renderItem(d, ui, isFirst) {
  const li = el("li", "problems-row");
  li.setAttribute("role", "listitem");

  const btn = el("button", `problem-item severity-${d.severity}`);
  btn.type = "button";
  btn.dataset.id = d.id;
  btn.dataset.file = d.file;

  const startLine = d.range ? d.range.startLine : d.start_line || 1;
  const startCol = d.range ? d.range.startCol : d.start_col || 1;

  btn.dataset.line = String(startLine);
  btn.dataset.col = String(startCol);

  const sevLabel = LABEL[d.severity] || "Problem";
  const sourceCode = d.code ? `${d.source} ${d.code}` : d.source;

  btn.setAttribute(
    "aria-label",
    `${sevLabel}, ${d.message}, ${d.file} line ${startLine} column ${startCol}, source ${d.source}`
  );
  btn.setAttribute("title", d.message);

  btn.tabIndex = ui.focusedId === d.id ? 0 : -1;

  const icon = createSvgIcon(d.severity, 14, `problem-severity-icon severity-${d.severity}`);
  const sevSpan = el("span", "problem-severity", sevLabel);
  const msgSpan = el("span", "problem-message", d.message);
  const srcSpan = el("span", "problem-source", sourceCode);
  const locSpan = el("span", "problem-location", `[${startLine}, ${startCol}]`);

  btn.append(icon, sevSpan, msgSpan, srcSpan, locSpan);
  li.appendChild(btn);

  // Phase 2: Action Button Group (Fix with AI & Explain)
  const actionsDiv = el("div", "problem-item-actions");

  const fixBtn = el("button", "problem-action-btn problem-btn-ai-fix");
  fixBtn.type = "button";
  fixBtn.setAttribute("aria-label", `Fix error in ${d.file} line ${startLine} with AI`);
  fixBtn.setAttribute("title", "Fix this error using DeskAI Assistant");
  fixBtn.textContent = "✨ Fix";
  fixBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (typeof ui.triggerAiFix === "function") {
      ui.triggerAiFix(d);
    }
  });

  const explainBtn = el("button", "problem-action-btn problem-btn-explain");
  explainBtn.type = "button";
  explainBtn.setAttribute("aria-label", `Explain error in ${d.file} line ${startLine}`);
  explainBtn.setAttribute("title", "Explain why this error occurred");
  explainBtn.textContent = "💡 Explain";
  explainBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    if (typeof ui.triggerAiExplain === "function") {
      ui.triggerAiExplain(d);
    }
  });

  actionsDiv.append(fixBtn, explainBtn);
  li.appendChild(actionsDiv);

  return li;
}

/**
 * Attaches keyboard navigation (roving tabindex) and click handlers to the problems view container.
 */
export function initViewKeyboardAndClicks(container, ui, onNavigate) {
  container.addEventListener("focusin", (e) => {
    const item = e.target.closest(".problems-file, .problem-item");
    if (item) {
      ui.focusedId = item.dataset.id || item.dataset.file;
      setRovingTabindex(container, item);
    }
  });

  container.addEventListener("click", (e) => {
    const itemBtn = e.target.closest(".problem-item");
    if (itemBtn) {
      const file = itemBtn.dataset.file;
      const line = parseInt(itemBtn.dataset.line, 10) || 1;
      const col = parseInt(itemBtn.dataset.col, 10) || 1;
      ui.focusedId = itemBtn.dataset.id;
      setRovingTabindex(container, itemBtn);
      if (typeof onNavigate === "function") {
        onNavigate(file, line, col);
      }
      return;
    }

    const fileBtn = e.target.closest(".problems-file");
    if (fileBtn) {
      const file = fileBtn.dataset.file;
      ui.toggleCollapse(file);
      ui.focusedId = file;
      return;
    }
  });

  container.addEventListener("keydown", (e) => {
    const active = document.activeElement;
    if (!active || !container.contains(active)) return;

    const items = Array.from(container.querySelectorAll(".problems-file, .problem-item:not([hidden])"));
    const currentIndex = items.indexOf(active);
    if (currentIndex === -1) return;

    switch (e.key) {
      case "ArrowDown": {
        e.preventDefault();
        const next = items[currentIndex + 1] || items[0];
        setRovingTabindex(container, next);
        ui.focusedId = next.dataset.id || next.dataset.file;
        next.focus();
        break;
      }
      case "ArrowUp": {
        e.preventDefault();
        const prev = items[currentIndex - 1] || items[items.length - 1];
        setRovingTabindex(container, prev);
        ui.focusedId = prev.dataset.id || prev.dataset.file;
        prev.focus();
        break;
      }
      case "ArrowRight": {
        if (active.classList.contains("problems-file")) {
          e.preventDefault();
          const file = active.dataset.file;
          if (ui.collapsed.has(file)) {
            ui.toggleCollapse(file);
          } else {
            const group = active.closest(".problems-group");
            const firstChild = group ? group.querySelector(".problem-item") : null;
            if (firstChild) {
              setRovingTabindex(container, firstChild);
              ui.focusedId = firstChild.dataset.id;
              firstChild.focus();
            }
          }
        }
        break;
      }
      case "ArrowLeft": {
        e.preventDefault();
        if (active.classList.contains("problems-file")) {
          const file = active.dataset.file;
          if (!ui.collapsed.has(file)) {
            ui.toggleCollapse(file);
          }
        } else if (active.classList.contains("problem-item")) {
          const group = active.closest(".problems-group");
          const head = group ? group.querySelector(".problems-file") : null;
          if (head) {
            setRovingTabindex(container, head);
            ui.focusedId = head.dataset.file;
            head.focus();
          }
        }
        break;
      }
      case "Home": {
        e.preventDefault();
        if (items.length > 0) {
          const first = items[0];
          setRovingTabindex(container, first);
          ui.focusedId = first.dataset.id || first.dataset.file;
          first.focus();
        }
        break;
      }
      case "End": {
        e.preventDefault();
        if (items.length > 0) {
          const last = items[items.length - 1];
          setRovingTabindex(container, last);
          ui.focusedId = last.dataset.id || last.dataset.file;
          last.focus();
        }
        break;
      }
      case "Enter":
      case " ": {
        e.preventDefault();
        active.click();
        break;
      }
      case "Escape": {
        e.preventDefault();
        const tabBtn = document.getElementById("tab-problems");
        if (tabBtn) tabBtn.focus();
        break;
      }
    }
  });
}

function setRovingTabindex(container, targetEl) {
  container.querySelectorAll(".problems-file, .problem-item").forEach(el => {
    el.tabIndex = -1;
  });
  if (targetEl) {
    targetEl.tabIndex = 0;
  }
}
