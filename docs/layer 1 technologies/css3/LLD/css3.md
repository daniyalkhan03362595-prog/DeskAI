# Layer 1 Technology LLD: CSS3 Design System, Variables & Hardware Acceleration

Yeh document **DeskAI** ke **Layer 1 (Presentation & Styling)** mein use hone wali **CSS3** ki mukammal **Low-Level Design (LLD)** specifications, design tokens, layout geometry, component styling, hardware-accelerated animations aur CSS containment rules ko **Roman Urdu** mein tafseel se bayan karta hai.

---

## 1. Executive Summary & Design Constraints

DeskAI ka visual architecture bina kisi utility framework (Tailwind/Bootstrap) ya preprocessor (Sass/Less) ke **Modern Pure CSS3** standards par tayar kiya gaya hai.

### Low-Level Technical Constraints:
1. **Zero Runtime Overhead:** Runtime par CSS-in-JS compilation ya stylesheet recalculations ka bojh 0% hona chahiye.
2. **Strict Layout Isolation (`contain`):** AI text tokens ke rapid streaming ke dauran poori window ka reflow/repaint block hona chahiye.
3. **GPU Hardware Compositing:** Smooth 60 FPS visual feedback ke liye animations aur dynamic transforms direct GPU layer par render honge.
4. **Sub-millisecond Theming:** Tamam colors, spacings aur dimensions CSS Custom Properties (`var(--...)`) ke zariye centrally control honge.

---

## 2. Directory & Stylesheet Architecture

Frontend styling 5 modular files mein munazzam hai:

```text
src/deskai/static/css/
├── tokens.css                # Design tokens: colors, typography, spacing, shadows, z-index
├── layout.css                # Grid layout, 3-column split-pane, resizers, custom scrollbars
├── components.css            # Header, file tree, hardware dock, chat, UEC
├── diff.css                  # Side-by-side & unified syntax diff lines & gutters
└── animations.css            # GPU-composited @keyframes (pulse, shimmer, morphing)
```

---

## 3. Design Tokens & Theme Specification (`tokens.css`)

Poori application `:root` variables ke zariye dynamically adapt hoti hai:

```css
:root {
  /* ==========================================================================
     1. 2026 Obsidian Matte + Warm Amber Palette
     ========================================================================== */
  --bg-app: #121315;            /* Deep Obsidian Matte Master Canvas */
  --bg-header: #17181b;         /* Elevated Window Titlebar & Controls */
  --bg-sidebar: #151619;        /* Explorer & Activity Navigation */
  --bg-surface: #1a1b1f;        /* Editor Workbench & Terminal Drawer */
  --bg-card: #202126;           /* Cards & Input Dock Containers */
  --bg-hover: rgba(255, 255, 255, 0.05);
  --bg-active: rgba(255, 255, 255, 0.08);

  /* Hairline Borders & Dividers */
  --border-subtle: #26272c;
  --border-regular: #31333a;
  --border-focus: #d99b26;

  /* Accent & Functional Colors */
  --color-primary: #d99b26;     /* Primary Warm Amber Accent */
  --color-primary-hover: #b8821d;
  --color-amber: #f59e0b;       /* DeskAI ⚡ Lightning Brand */
  --color-success: #22c55e;     /* GPU active & diff additions */
  --color-warning: #f59e0b;     /* In-progress & review diffs */
  --color-danger: #ff6b6b;      /* Contrast 5.8:1 on card */

  /* Text Colors */
  --text-primary: #ededed;
  --text-secondary: #9ca0a6;
  --text-muted: #8a8e97;        /* Contrast 5.7:1 (Exceeds WCAG AA >= 4.5:1) */
  --text-inverse: #121315;
  --text-btn-primary: #121315;  /* Contrast 7.7:1 on Amber button (Exceeds WCAG AAA) */

  /* ==========================================================================
     2. Typography Scales
     ========================================================================== */
  --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Ubuntu, sans-serif;
  --font-mono: "JetBrains Mono", "Fira Code", "Cascadia Code", monospace;

  --text-xs: 11px;
  --text-sm: 12.5px;
  --text-base: 14px;
  --text-lg: 16px;
  --text-xl: 20px;

  /* ==========================================================================
     3. Spacing Scales
     ========================================================================== */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;

  /* ==========================================================================
     4. Dynamic Layout Geometry
     ========================================================================== */
  --header-height: 38px;
  --sidebar-left-w: 280px;      /* Live adjusted by pointer drag */
  --sidebar-right-w: 360px;     /* Live adjusted by pointer drag */
  --bottom-drawer-h: 220px;

  /* ==========================================================================
     5. Layer Elevation (Z-Index)
     ========================================================================== */
  --z-content: 1;
  --z-resizer: 20;
  --z-sticky-footer: 50;
  --z-header: 100;
  --z-modal: 500;
  --z-toast: 1000;

  /* Shadows */
  --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.4);
  --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.5);
  --shadow-glow-teal: 0 0 12px rgba(26, 188, 156, 0.35);
  --shadow-glow-blue: 0 0 12px rgba(52, 152, 219, 0.35);
}
```

---

## 4. Master Layout Grid & Split-Pane Geometry (`layout.css`)

Application ka root container CSS Grid par mabni hai jo window ko 100% viewport par lock rakhta hai:

```css
/* Master App Container */
html, body {
  margin: 0;
  padding: 0;
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  background-color: var(--bg-app);
  color: var(--text-primary);
  font-family: var(--font-sans);
  -webkit-font-smoothing: antialiased;
}

.app-root {
  display: grid;
  grid-template-rows: var(--header-height) 1fr;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

/* 3-Column IDE Body */
.app-body {
  display: grid;
  grid-template-columns: var(--sidebar-left-w) 4px 1fr 4px var(--sidebar-right-w);
  width: 100%;
  height: 100%;
  overflow: hidden;
  position: relative;
}

/* Split-Pane Resizer Handles */
.resizer-col {
  width: 4px;
  height: 100%;
  background-color: var(--border-subtle);
  cursor: col-resize;
  position: relative;
  z-index: var(--z-resizer);
  transition: background-color 0.15s ease;
  user-select: none;
}

.resizer-col:hover,
.resizer-col.resizing {
  background-color: var(--color-primary);
  box-shadow: 0 0 8px var(--color-primary);
}

/* Custom Minimalist WebKit Scrollbars */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: var(--border-regular);
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--text-muted);
}
```

---

## 5. Layout Containment & Rendering Optimization

Jab local Qwen 7B model chat window mein tezi se text chunks stream karta hai, to browser ke poore DOM tree ko repaint hone se bachane ke liye **CSS Containment** use hoti hai:

```css
/* Chat Thread Containment */
.sidebar-right {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.chat-thread {
  flex: 1;
  min-height: 0;                /* Allows flex container to shrink properly */
  contain: layout paint;        /* Isolate layout without rigid size constraints */
  overflow-y: auto;
  overflow-x: hidden;
  will-change: scroll-position;
}

/* Editor Surface Containment (Note: CodeMirror configured with tooltips({parent: document.body})) */
.editor-stage {
  contain: layout paint;
  overflow: hidden;
  position: relative;
}

/* Hardware Compositing Promotion */
.uec-card,
.palette-dialog,
.telemetry-row {
  transform: translateZ(0);     /* Promotes to dedicated GPU layer */
  backface-visibility: hidden;
}
```

---

## 6. Components Styling Specification (`components.css`)

### 6.1 Hardware Telemetry Dock
Sidebar ke bottom par fixed panel:
```css
.hardware-dock {
  position: sticky;
  bottom: 0;
  background-color: var(--bg-header);
  border-top: 1px solid var(--border-subtle);
  padding: var(--space-3);
  z-index: var(--z-sticky-footer);
  font-size: var(--text-xs);
}

.telemetry-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-2);
}

.vram-meter-track {
  width: 100%;
  height: 5px;
  background-color: var(--border-subtle);
  border-radius: 3px;
  overflow: hidden;
  margin: var(--space-1) 0 var(--space-2) 0;
}

.vram-meter-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--color-teal), var(--color-primary));
  border-radius: 3px;
  transition: width 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}
```

### 6.2 Unified Execution Card (UEC) Morphing Container
```css
.uec-card {
  background-color: var(--bg-card);
  border: 1px solid var(--border-regular);
  border-radius: 8px;
  padding: var(--space-3);
  margin: var(--space-3);
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
  box-shadow: var(--shadow-md);
}

.uec-card[data-state="PLANNING"] {
  border-color: var(--color-teal);
  box-shadow: var(--shadow-glow-teal);
}

.uec-card[data-state="EXECUTING"] {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-glow-blue);
}

.uec-card[data-state="REVIEW_DIFF"] {
  border-color: var(--color-warning);
}
```

---

## 7. Diff Syntax & Line Gutters (`diff.css`)

Code differences ko side-by-side aur unified views mein render karne ke liye precise styling:

```css
.diff-table {
  width: 100%;
  border-collapse: collapse;
  font-family: var(--font-mono);
  font-size: var(--text-sm);
}

.diff-line {
  line-height: 20px;
}

.diff-line.addition {
  background-color: rgba(46, 204, 113, 0.12);
}

.diff-line.deletion {
  background-color: rgba(231, 76, 60, 0.12);
}

.diff-gutter-num {
  width: 45px;
  text-align: right;
  padding-right: var(--space-2);
  color: var(--text-muted);
  user-select: none;
  border-right: 1px solid var(--border-subtle);
}

.diff-content {
  padding-left: var(--space-2);
  white-space: pre;
}

.diff-sign-add { color: var(--color-success); font-weight: bold; }
.diff-sign-del { color: var(--color-danger); font-weight: bold; }
```

---

## 8. GPU-Accelerated Keyframes & Motion (`animations.css`)

```css
/* GPU Active Status Pulsing Glow */
@keyframes pulse-glow {
  0% {
    box-shadow: 0 0 0 0 rgba(46, 204, 113, 0.7);
  }
  70% {
    box-shadow: 0 0 0 6px rgba(46, 204, 113, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(46, 204, 113, 0);
  }
}

.status-dot-active {
  width: 8px;
  height: 8px;
  background-color: var(--color-success);
  border-radius: 50%;
  display: inline-block;
  animation: pulse-glow 2s infinite ease-out;
  transform: translateZ(0);
}

/* Streaming Skeleton Shimmer */
@keyframes shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}

.skeleton-loading {
  background: linear-gradient(90deg, var(--bg-surface) 25%, var(--bg-card) 50%, var(--bg-surface) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}
```

---

## 9. Accessibility & WCAG AA Contrast Standards

1. **High Contrast Typography (2026 Obsidian Matte Palette):**
   - `--text-primary` (`#ededed`) on `--bg-app` (`#121315`) yields a contrast ratio of **15.9:1**, far exceeding the WCAG AAA requirement (7:1).
   - `--text-secondary` (`#9ca0a6`) yields **7.1:1** (WCAG AAA).
   - `--text-muted` (`#8a8e97`) yields **5.7:1**, exceeding WCAG AA for small 11px/12px text (requires >= 4.5:1).
   - `--text-btn-primary` (`#121315`) on `--color-primary` (`#d99b26`) yields **7.7:1** (WCAG AAA).
2. **Keyboard Focus Outlines:**
   ```css
   :focus-visible {
     outline: 2px solid var(--border-focus);
     outline-offset: 2px;
   }
   ```
3. **Motion Sensitivity:**
   ```css
   @media (prefers-reduced-motion: reduce) {
     *, *::before, *::after {
       animation-duration: 0.01ms !important;
       transition-duration: 0.01ms !important;
     }
   }
   ```
4. **Screen Reader Utility (`.sr-only`):**
   Visually hides text while preserving it for assistive technologies (screen readers):
   ```css
   .sr-only {
     position: absolute;
     width: 1px;
     height: 1px;
     padding: 0;
     margin: -1px;
     overflow: hidden;
     clip: rect(0, 0, 0, 0);
     white-space: nowrap;
     border: 0;
   }
   ```
