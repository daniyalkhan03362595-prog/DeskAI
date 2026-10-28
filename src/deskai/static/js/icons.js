/**
 * Inline SVG Icon System for DeskAI Studio.
 * Generates vector icons using createElementNS with currentColor and tokens.
 * Zero external libraries, zero network requests, zero innerHTML.
 */

const SVG_NS = "http://www.w3.org/2000/svg";

/**
 * Registry of SVG icon paths and primitives (24x24 viewBox).
 */
const ICON_DEFS = {
  "file": [
    { tag: "path", attrs: { d: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" } },
    { tag: "polyline", attrs: { points: "14 2 14 8 20 8" } },
  ],
  "file-plus": [
    { tag: "path", attrs: { d: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" } },
    { tag: "polyline", attrs: { points: "14 2 14 8 20 8" } },
    { tag: "line", attrs: { x1: "12", y1: "18", x2: "12", y2: "12" } },
    { tag: "line", attrs: { x1: "9", y1: "15", x2: "15", y2: "15" } },
  ],
  "folder": [
    { tag: "path", attrs: { d: "M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" } },
  ],
  "folder-plus": [
    { tag: "path", attrs: { d: "M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" } },
    { tag: "line", attrs: { x1: "12", y1: "11", x2: "12", y2: "17" } },
    { tag: "line", attrs: { x1: "9", y1: "14", x2: "15", y2: "14" } },
  ],
  "refresh": [
    { tag: "polyline", attrs: { points: "23 4 23 10 17 10" } },
    { tag: "polyline", attrs: { points: "1 20 1 14 7 14" } },
    { tag: "path", attrs: { d: "M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" } },
  ],
  "collapse": [
    { tag: "rect", attrs: { x: "3", y: "3", width: "18", height: "18", rx: "2", ry: "2" } },
    { tag: "line", attrs: { x1: "8", y1: "12", x2: "16", y2: "12" } },
  ],
  "close": [
    { tag: "line", attrs: { x1: "18", y1: "6", x2: "6", y2: "18" } },
    { tag: "line", attrs: { x1: "6", y1: "6", x2: "18", y2: "18" } },
  ],
  "check": [
    { tag: "polyline", attrs: { points: "20 6 9 17 4 12" } },
  ],
  "chevron-right": [
    { tag: "polyline", attrs: { points: "9 18 15 12 9 6" } },
  ],
  "chevron-down": [
    { tag: "polyline", attrs: { points: "6 9 12 15 18 9" } },
  ],
  "lightning": [
    { tag: "polygon", attrs: { points: "13 2 3 14 12 14 11 22 21 10 12 10 13 2" } },
  ],
  "theme": [
    { tag: "circle", attrs: { cx: "12", cy: "12", r: "5" } },
    { tag: "line", attrs: { x1: "12", y1: "1", x2: "12", y2: "3" } },
    { tag: "line", attrs: { x1: "12", y1: "21", x2: "12", y2: "23" } },
    { tag: "line", attrs: { x1: "4.22", y1: "4.22", x2: "5.64", y2: "5.64" } },
    { tag: "line", attrs: { x1: "18.36", y1: "18.36", x2: "19.78", y2: "19.78" } },
    { tag: "line", attrs: { x1: "1", y1: "12", x2: "3", y2: "12" } },
    { tag: "line", attrs: { x1: "21", y1: "12", x2: "23", y2: "12" } },
    { tag: "line", attrs: { x1: "4.22", y1: "19.78", x2: "5.64", y2: "18.36" } },
    { tag: "line", attrs: { x1: "18.36", y1: "5.64", x2: "19.78", y2: "4.22" } },
  ],
  "gear": [
    { tag: "circle", attrs: { cx: "12", cy: "12", r: "3" } },
    {
      tag: "path",
      attrs: {
        d: "M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z",
      },
    },
  ],
  "send": [
    { tag: "line", attrs: { x1: "22", y1: "2", x2: "11", y2: "13" } },
    { tag: "polygon", attrs: { points: "22 2 15 22 11 13 2 9 22 2" } },
  ],
  "sparkle": [
    { tag: "path", attrs: { d: "m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z" } },
  ],
  "edit": [
    { tag: "path", attrs: { d: "M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" } },
    { tag: "path", attrs: { d: "M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" } },
  ],
  "trash": [
    { tag: "polyline", attrs: { points: "3 6 5 6 21 6" } },
    { tag: "path", attrs: { d: "M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" } },
  ],
  "copy": [
    { tag: "rect", attrs: { x: "9", y: "9", width: "13", height: "13", rx: "2", ry: "2" } },
    { tag: "path", attrs: { d: "M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" } },
  ],
  "link": [
    { tag: "path", attrs: { d: "M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" } },
    { tag: "path", attrs: { d: "M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" } },
  ],
  "terminal": [
    { tag: "polyline", attrs: { points: "4 17 10 11 4 5" } },
    { tag: "line", attrs: { x1: "12", y1: "19", x2: "20", y2: "19" } },
  ],
  "status-dot": [
    { tag: "circle", attrs: { cx: "12", cy: "12", r: "6", fill: "currentColor" } },
  ],
};

/**
 * Creates an inline SVG icon element without innerHTML.
 * @param {string} name - Icon name from ICON_DEFS
 * @param {number} [size=14] - Width and height in px
 * @param {string} [className="deskai-svg-icon"] - CSS class
 * @returns {SVGSVGElement}
 */
export function createSvgIcon(name, size = 14, className = "deskai-svg-icon") {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("xmlns", SVG_NS);
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", String(size));
  svg.setAttribute("height", String(size));
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("class", className);

  const defs = ICON_DEFS[name] || ICON_DEFS["file"];
  for (const def of defs) {
    const el = document.createElementNS(SVG_NS, def.tag);
    if (def.attrs) {
      for (const [key, val] of Object.entries(def.attrs)) {
        el.setAttribute(key, val);
      }
    }
    svg.appendChild(el);
  }

  return svg;
}
