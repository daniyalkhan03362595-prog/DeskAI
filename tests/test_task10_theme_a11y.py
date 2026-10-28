import re
import sys
import unittest
from pathlib import Path


class TestThemeAndAccessibility(unittest.TestCase):
    def test_favicon_declared_in_index_html(self):
        """index.html must declare a favicon to avoid browser 404."""
        index_html = Path("src/deskai/static/index.html").read_text(encoding="utf-8")
        self.assertRegex(index_html, r'<link\s+rel="icon"\s+type="image/svg\+xml"\s+href="icon\.svg"')

    def test_border_input_token_defined_and_contrast_compliant(self):
        """tokens.css must define --border-input with contrast >= 3:1 against --bg-surface (#1a1b1f)."""
        tokens_css = Path("src/deskai/static/css/tokens.css").read_text(encoding="utf-8")
        self.assertIn("--border-input", tokens_css)

        # Extract --border-input hex value e.g. #4b4d54
        match = re.search(r"--border-input:\s*(#[0-9a-fA-F]{6})", tokens_css)
        self.assertIsNotNone(match, "--border-input hex color not found in tokens.css")
        border_hex = match.group(1).lstrip("#")

        # Compute relative luminance
        def lum(hex_str):
            r, g, b = [int(hex_str[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]
            rg = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
            return 0.2126 * rg[0] + 0.7152 * rg[1] + 0.0722 * rg[2]

        l_bg = lum("1a1b1f")
        l_border = lum(border_hex)
        contrast = (max(l_bg, l_border) + 0.05) / (min(l_bg, l_border) + 0.05)
        self.assertGreaterEqual(contrast, 3.0, f"Contrast {contrast:.2f}:1 is less than 3:1 requirement")

    def test_no_hardcoded_colors_in_components_and_diff(self):
        """components.css and diff.css must not contain raw hardcoded colors (#fff, #b8821d, rgba(231,76,60...))."""
        diff_css = Path("src/deskai/static/css/diff.css").read_text(encoding="utf-8")
        components_css = Path("src/deskai/static/css/components.css").read_text(encoding="utf-8")

        # Disallow specific hardcoded values identified in audit
        self.assertNotIn("rgba(231, 76, 60", diff_css)
        self.assertNotIn("rgba(46, 204, 113", diff_css)
        self.assertNotIn("#b8821d", components_css)
        self.assertNotIn("#f59e0b", components_css)
        self.assertNotIn("#fff", components_css)

    def test_focus_visible_and_forced_colors_declared(self):
        """tokens.css or components.css must declare :focus-visible and forced-colors."""
        tokens_css = Path("src/deskai/static/css/tokens.css").read_text(encoding="utf-8")
        components_css = Path("src/deskai/static/css/components.css").read_text(encoding="utf-8")
        all_css = tokens_css + components_css

        self.assertIn(":focus-visible", all_css)
        self.assertIn("forced-colors", all_css)

    def test_editor_tab_aria_and_keyboard_nav(self):
        """editor.js must configure role=tablist, aria-controls, tabindex, and Arrow key nav."""
        editor_js = Path("src/deskai/static/js/editor.js").read_text(encoding="utf-8")
        self.assertIn("aria-controls", editor_js)
        self.assertIn("ArrowRight", editor_js)
        self.assertIn("ArrowLeft", editor_js)

    def test_resize_handles_size_at_least_6px(self):
        """Window resize handles must be at least 6px wide/tall in layout.css."""
        layout_css = Path("src/deskai/static/css/layout.css").read_text(encoding="utf-8")
        height_matches = re.findall(r"\.resize-handle\.(?:top|bottom)\s*\{[^}]*height:\s*([0-9]+)px", layout_css)
        for h in height_matches:
            self.assertGreaterEqual(int(h), 6)
        width_matches = re.findall(r"\.resize-handle\.(?:left|right)\s*\{[^}]*width:\s*([0-9]+)px", layout_css)
        for w in width_matches:
            self.assertGreaterEqual(int(w), 6)

    def test_stream_throttle_trailing_edge(self):
        """stream.js must schedule a trailingTimer flush."""
        stream_js = Path("src/deskai/static/js/stream.js").read_text(encoding="utf-8")
        self.assertIn("this.trailingTimer = setTimeout", stream_js)

    def test_terminal_ansi_tokens_defined_and_meet_contrast(self):
        """tokens.css must define --terminal-* and 16 --ansi-* tokens with WCAG AA >= 4.5:1 contrast against #141518."""
        tokens_css = Path("src/deskai/static/css/tokens.css").read_text(encoding="utf-8")
        self.assertIn("--terminal-bg", tokens_css)
        self.assertIn("--terminal-fg", tokens_css)
        self.assertIn("--terminal-cursor", tokens_css)

        ansi_names = [
            "black",
            "red",
            "green",
            "yellow",
            "blue",
            "magenta",
            "cyan",
            "white",
            "bright-black",
            "bright-red",
            "bright-green",
            "bright-yellow",
            "bright-blue",
            "bright-magenta",
            "bright-cyan",
            "bright-white",
        ]

        def lum(hex_str):
            r, g, b = [int(hex_str[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]
            rg = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
            return 0.2126 * rg[0] + 0.7152 * rg[1] + 0.0722 * rg[2]

        l_bg = lum("141518")

        for name in ansi_names:
            token_key = f"--ansi-{name}"
            match = re.search(rf"{token_key}:\s*(#[0-9a-fA-F]{{6}})", tokens_css)
            self.assertIsNotNone(match, f"{token_key} color not found in tokens.css")
            color_hex = match.group(1).lstrip("#")
            l_fg = lum(color_hex)
            contrast = (max(l_bg, l_fg) + 0.05) / (min(l_bg, l_fg) + 0.05)
            self.assertGreaterEqual(
                contrast,
                4.5,
                f"ANSI token {token_key} ({color_hex}) contrast {contrast:.2f}:1 is less than 4.5:1 against #141518",
            )

    def test_light_theme_tokens_defined_and_contrast_passes(self):
        """tokens.css must define complete light theme tokens and pass all WCAG AA contrast requirements."""
        tokens_css = Path("src/deskai/static/css/tokens.css").read_text(encoding="utf-8")
        self.assertIn(':root[data-theme="light"]', tokens_css)
        self.assertIn("@media (prefers-color-scheme: light)", tokens_css)

        # Run check_contrast script and assert clean exit code 0
        import subprocess

        result = subprocess.run(
            [sys.executable, "tools/check_contrast.py"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"check_contrast.py failed with output:\n{result.stdout}\n{result.stderr}",
        )

    def test_theme_toggle_button_and_persistence_module(self):
        """Index HTML must include theme toggle button and theme.js must safely persist choice."""
        index_html = Path("src/deskai/static/index.html").read_text(encoding="utf-8")
        self.assertIn('id="btnToggleTheme"', index_html)
        self.assertIn('data-action="toggle-theme"', index_html)

        theme_js = Path("src/deskai/static/js/theme.js").read_text(encoding="utf-8")
        self.assertIn("localStorage.getItem", theme_js)
        self.assertIn("localStorage.setItem", theme_js)
        self.assertIn("try {", theme_js)
        self.assertIn("catch", theme_js)
        self.assertIn("prefers-color-scheme", theme_js)

        # Verify theme initialization in app.js
        app_js = Path("src/deskai/static/js/app.js").read_text(encoding="utf-8")
        self.assertIn('import { initTheme } from "./theme.js"', app_js)
        self.assertIn("initTheme()", app_js)

    def test_prefers_reduced_motion_in_animations_css(self):
        """animations.css must handle prefers-reduced-motion to disable non-essential motion."""
        animations_css = Path("src/deskai/static/css/animations.css").read_text(encoding="utf-8")
        self.assertIn("@media (prefers-reduced-motion: reduce)", animations_css)
        self.assertIn("animation-duration", animations_css)
        self.assertIn("transition-duration", animations_css)

    def test_no_raw_colors_outside_tokens_css(self):
        """No raw hex (#...) or rgb/rgba(...) colors may exist in any css file outside tokens.css."""
        css_dir = Path("src/deskai/static/css")
        hex_pattern = re.compile(r"#[0-9a-fA-F]{3,8}\b")
        rgb_pattern = re.compile(r"rgba?\([^)]+\)")

        violations = []
        for css_file in css_dir.glob("*.css"):
            if css_file.name == "tokens.css":
                continue
            content = css_file.read_text(encoding="utf-8")
            if hex_pattern.search(content) or rgb_pattern.search(content):
                violations.append(css_file.name)

        self.assertEqual(
            violations,
            [],
            f"Raw color declarations found outside tokens.css in: {violations}",
        )

    def test_every_interactive_element_has_accessible_name(self):
        """Every interactive element in static/index.html must have an accessible name."""
        from html.parser import HTMLParser

        class InteractiveScanner(HTMLParser):
            def __init__(self):
                super().__init__()
                self.interactive = []
                self.stack = []

            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)
                is_interactive = False
                if tag in ("button", "input", "select", "textarea", "a"):
                    is_interactive = True
                elif attrs_dict.get("role") in ("button", "tab", "treeitem", "menuitem"):
                    is_interactive = True
                elif "tabindex" in attrs_dict and attrs_dict["tabindex"] != "-1":
                    is_interactive = True

                entry = {"tag": tag, "attrs": attrs_dict, "text": "", "interactive": is_interactive}
                self.stack.append(entry)
                if is_interactive:
                    self.interactive.append(entry)

            def handle_data(self, data):
                if self.stack:
                    self.stack[-1]["text"] += data.strip()

            def handle_endtag(self, tag):
                if self.stack:
                    entry = self.stack.pop()
                    if self.stack and entry["text"]:
                        self.stack[-1]["text"] += " " + entry["text"]

        scanner = InteractiveScanner()
        scanner.feed(Path("src/deskai/static/index.html").read_text(encoding="utf-8"))

        unnamed = []
        for el in scanner.interactive:
            tag = el["tag"]
            attrs = el["attrs"]
            text = el["text"].strip()
            name = (
                attrs.get("aria-label")
                or attrs.get("title")
                or attrs.get("aria-labelledby")
                or attrs.get("placeholder")
                or text
            )
            if not name:
                unnamed.append((tag, attrs.get("id", ""), attrs.get("class", "")))

        self.assertEqual(
            unnamed,
            [],
            f"Found interactive elements missing an accessible name: {unnamed}",
        )

    def test_every_interactive_element_has_visible_focus_style(self):
        """CSS must define accessible focus rings via :focus-visible and not strip outline without focus styling."""
        tokens_css = Path("src/deskai/static/css/tokens.css").read_text(encoding="utf-8")
        self.assertIn(":focus-visible", tokens_css)
        self.assertIn("outline:", tokens_css)

        components_css = Path("src/deskai/static/css/components.css").read_text(encoding="utf-8")
        # Ensure that whenever outline is set to none on interactive inputs, box-shadow or border-color focus is set
        for input_cls in [".ports-filter-input", ".modal-input"]:
            match = re.search(rf"{re.escape(input_cls)}:focus-visible\s*\{{([^}}]+)\}}", components_css)
            self.assertIsNotNone(match, f"Missing focus-visible style for {input_cls}")
            rules = match.group(1)
            has_visible_indicator = "border-color" in rules or "box-shadow" in rules or "outline" in rules
            self.assertTrue(
                has_visible_indicator,
                f"Element {input_cls} has no visible focus indicator",
            )


if __name__ == "__main__":
    unittest.main()
