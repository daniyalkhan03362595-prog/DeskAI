import re
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
            r, g, b = [int(hex_str[i:i+2], 16) / 255.0 for i in (0, 2, 4)]
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


if __name__ == "__main__":
    unittest.main()
