# Low-Level Design (LLD): App Branding Title

**Document ID:** `ORX-LLD-APP-BRANDING-TITLE-V1`  
**Version:** `1.0` (Window Control Bar Subcomponent Architecture)  
**Parent Document:** `ORX-HLD-APP-BRANDING-TITLE-V1`  
**Target Codebase:** `DeskAI`  
**Target Files:**
* `src/deskai/static/index.html`
* `src/deskai/static/css/components.css`
* `src/deskai/static/css/tokens.css`
* `tests/test_app_branding_title.py`
**Status:** Approved for Implementation  
**Date:** October 28, 2026  

---

## 1. Executive Summary & Objective

The **App Branding Title** (`.app-logo`) provides brand identity in the top header (`#appHeader`) of DeskAI Studio.

This Low-Level Design defines:
1. Exact DOM layout, accessible markup, and aria attributes.
2. Complete CSS token mappings and properties.
3. Frameless window drag pass-through behavior.
4. Test specifications for Playwright test suite (`TC-ABT-01` through `TC-ABT-05`).

---

## 2. DOM Structure & Accessibility Markup

### 2.1 Markup Specification in `src/deskai/static/index.html`

```html
<header class="app-header pywebview-drag-region" id="appHeader" role="banner">
  <div class="header-left">
    <div class="app-logo" id="appLogo" aria-label="DeskAI Studio">
      <span class="app-logo-icon" aria-hidden="true">⚡</span>
      <span class="app-logo-text">DeskAI</span>
    </div>
    <span class="workspace-pill" id="headerWorkspacePill">DeskAI / main</span>
  </div>
  <div class="header-right window-controls" role="group" aria-label="Window Controls">
    <button class="win-btn win-min" data-action="win-minimize" aria-label="Minimize Window">─</button>
    <button class="win-btn win-max" data-action="win-maximize" aria-label="Maximize Window">□</button>
    <button class="win-btn win-close" data-action="win-close" aria-label="Close Window">✕</button>
  </div>
</header>
```

### 2.2 Accessibility Attributes
- **Container (`#appHeader`):** Has `role="banner"` declaring the landmark for assistive technologies.
- **Logo Container (`#appLogo`):** Has `aria-label="DeskAI Studio"` ensuring screen readers announce the full application name clearly.
- **Icon (`.app-logo-icon`):** Has `aria-hidden="true"` so screen readers do not read the lightning symbol literally.
- **Text (`.app-logo-text`):** Visual typography for the brand name.
- **Focusability:** Non-focusable (no `tabindex`), preserving tab-order integrity for actual controls.

---

## 3. CSS Styling & Token Specifications

In `src/deskai/static/css/components.css`:

```css
.app-header {
  height: var(--header-height);
  background-color: var(--bg-header);
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-3);
  z-index: var(--z-header);
  user-select: none;
  -webkit-app-region: drag;
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.app-logo {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-weight: 700;
  font-size: var(--text-base);
  color: var(--color-amber);
  letter-spacing: -0.5px;
  cursor: default;
  user-select: none;
}

.app-logo-icon {
  font-size: var(--text-sm);
  line-height: 1;
}

.app-logo-text {
  font-weight: 700;
  letter-spacing: -0.5px;
}
```

### 3.1 Design Token Reference

| Property | CSS Variable | Value / Description |
|---|---|---|
| Color | `var(--color-amber)` | `#f59e0b` (Primary brand accent) |
| Font Size | `var(--text-base)` | `13px` (High-density desktop IDE base) |
| Font Size Icon | `var(--text-sm)` | `12px` |
| Gap | `var(--space-1)` | `4px` |
| Height | `var(--header-height)` | `38px` |
| Background | `var(--bg-header)` | `#12151c` |

---

## 4. Test Specifications (Playwright)

File: `tests/test_app_branding_title.py`

| Test Case ID | Test Case Name | Description & Verification Steps |
|---|---|---|
| **TC-ABT-01** | `test_abt_01_accessible_markup_and_semantics` | Asserts `#appHeader` has `role="banner"`, `#appLogo` exists with `aria-label="DeskAI Studio"`, and `.app-logo-icon` has `aria-hidden="true"`. |
| **TC-ABT-02** | `test_abt_02_brand_text_and_icon_content` | Asserts text content of `.app-logo-text` is `"DeskAI"` and icon is `"⚡"`. |
| **TC-ABT-03** | `test_abt_03_token_styles_and_colors` | Asserts computed color of `#appLogo` matches `--color-amber` token (RGB `245, 158, 11`), font weight is `700`, and `user-select` is `none`. |
| **TC-ABT-04** | `test_abt_04_drag_region_inheritance` | Asserts `#appHeader` has `-webkit-app-region: drag` and `#appLogo` is not marked as `no-drag` so window dragging passes through. |
| **TC-ABT-05** | `test_abt_05_keyboard_tab_traversal_skips_logo` | Tabs through the page from body; verifies that focus moves directly to interactive elements without stopping on `#appLogo`. |

---

## 5. Implementation Roadmap
1. Refine `src/deskai/static/index.html` to include `#appLogo`, `.app-logo-icon`, and `.app-logo-text` with accessibility attributes.
2. Refine `src/deskai/static/css/components.css` to add `.app-logo-icon` and `.app-logo-text` classes with token variables.
3. Author `tests/test_app_branding_title.py` covering `TC-ABT-01` through `TC-ABT-05`.
4. Run full test suite and verify `black` + `flake8` compliance.
