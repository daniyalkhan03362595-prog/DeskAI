#!/usr/bin/env python3
"""
DeskAI WCAG 2.1 Contrast Ratio Verification Tool
Validates foreground/background token pairs across dark and light themes against:
- WCAG 2.1 Level AA for normal text: >= 4.5:1
- WCAG 2.1 Level AA for UI components and focus indicators: >= 3.0:1
"""

import re
import sys
from pathlib import Path


def relative_luminance(hex_color: str) -> float:
    """Compute WCAG 2.1 relative luminance from 6-digit hex."""
    hex_color = hex_color.strip().lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join([c * 2 for c in hex_color])
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0

    def adjust(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r_lin = adjust(r)
    g_lin = adjust(g)
    b_lin = adjust(b)
    return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin


def contrast_ratio(c1_hex: str, c2_hex: str) -> float:
    """Compute WCAG 2.1 contrast ratio between two hex colors."""
    l1 = relative_luminance(c1_hex)
    l2 = relative_luminance(c2_hex)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def extract_css_variables(css_text: str, selector: str) -> dict[str, str]:
    """Extract CSS variables defined within a given block."""
    tokens = {}
    pattern = rf"{selector}\s*\{{([^}}]+)\}}"
    match = re.search(pattern, css_text)
    if not match:
        return tokens

    block = match.group(1)
    for line in block.splitlines():
        line = line.strip()
        if line.startswith("--") and ":" in line:
            parts = line.split(":", 1)
            var_name = parts[0].strip().lstrip("-")
            val = parts[1].split(";")[0].strip()
            # Capture hex colors
            hex_match = re.search(r"#[0-9a-fA-F]{3,8}\b", val)
            if hex_match:
                tokens[var_name] = hex_match.group(0)
    return tokens


def parse_tokens(css_path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Parse dark (default :root) and light theme tokens from tokens.css."""
    content = css_path.read_text(encoding="utf-8")

    # Dark theme: :root { ... } before media query
    dark_tokens = extract_css_variables(content, r":root")

    # Light theme: :root\[data-theme="light"\] { ... }
    light_tokens = extract_css_variables(content, r':root\[data-theme="light"\]')
    if not light_tokens:
        # Fallback to prefers-color-scheme: light inner selector
        light_tokens = extract_css_variables(content, r':root:not\(\[data-theme="dark"\]\)')

    return dark_tokens, light_tokens


# Actual foreground/background pairs used across DeskAI interface
PAIRS_TO_CHECK = [
    # (Foreground Token, Background Token, Min Ratio, Category, Description)
    ("text-primary", "bg-app", 4.5, "Text", "Primary body text on main app canvas"),
    ("text-secondary", "bg-app", 4.5, "Text", "Secondary text labels on main app canvas"),
    ("text-muted", "bg-app", 4.5, "Text", "Muted text/hints on main app canvas"),
    ("text-primary", "bg-surface", 4.5, "Text", "Primary editor text on surface"),
    ("text-secondary", "bg-surface", 4.5, "Text", "Secondary labels on workbench surface"),
    ("text-muted", "bg-surface", 4.5, "Text", "Gutter & muted text on workbench surface"),
    ("text-primary", "bg-card", 4.5, "Text", "Primary card/dock text"),
    ("text-secondary", "bg-card", 4.5, "Text", "Secondary card/dock text"),
    ("text-muted", "bg-card", 4.5, "Text", "Muted dock hints"),
    ("text-primary", "bg-header", 4.5, "Text", "Titlebar primary title text"),
    ("text-secondary", "bg-header", 4.5, "Text", "Titlebar secondary text"),
    ("text-muted", "bg-header", 4.5, "Text", "Titlebar window controls"),
    ("text-primary", "bg-sidebar", 4.5, "Text", "Explorer tree filename text"),
    ("text-secondary", "bg-sidebar", 4.5, "Text", "Explorer tree folder text"),
    ("text-muted", "bg-sidebar", 4.5, "Text", "Explorer tree status indicators"),
    ("text-btn-primary", "color-primary", 4.5, "Text", "Primary action button text"),
    ("color-success", "bg-surface", 4.5, "Text", "Diff added line indicator"),
    ("color-danger", "bg-surface", 4.5, "Text", "Diff deleted line indicator"),
    ("color-danger", "bg-card", 4.5, "Text", "Problem error label"),
    ("color-warning", "bg-card", 4.5, "Text", "Problem warning label"),
    ("color-info", "bg-card", 4.5, "Text", "Problem info label"),
    ("color-danger", "bg-header", 4.5, "Text", "Output error text on toolbar header"),
    ("color-warning", "bg-header", 4.5, "Text", "Output warning text on toolbar header"),
    ("color-danger", "bg-app", 4.5, "Text", "Output error text on app background"),
    ("color-warning", "bg-app", 4.5, "Text", "Output warning text on app background"),
    ("color-danger", "bg-card", 3.0, "UI", "Problem error icon"),
    ("color-warning", "bg-card", 3.0, "UI", "Problem warning icon"),
    ("color-info", "bg-card", 3.0, "UI", "Problem info icon"),
    ("border-focus", "bg-app", 3.0, "UI", "Active focus ring on app canvas"),
    ("border-focus", "bg-surface", 3.0, "UI", "Active focus ring on surface"),
    ("border-input", "bg-surface", 3.0, "UI", "Form input border on surface"),
    ("border-input", "bg-card", 3.0, "UI", "Form input border on dock card"),
    ("terminal-fg", "terminal-bg", 4.5, "Text", "Terminal default text on terminal canvas"),
    ("ansi-bright-white", "terminal-bg", 4.5, "Text", "Terminal ANSI Bright White"),
    ("ansi-green", "terminal-bg", 4.5, "Text", "Terminal ANSI Green"),
    ("ansi-blue", "terminal-bg", 4.5, "Text", "Terminal ANSI Blue"),
    ("ansi-red", "terminal-bg", 4.5, "Text", "Terminal ANSI Red"),
    ("ansi-yellow", "terminal-bg", 4.5, "Text", "Terminal ANSI Yellow"),
    ("ansi-cyan", "terminal-bg", 4.5, "Text", "Terminal ANSI Cyan"),
    ("ansi-magenta", "terminal-bg", 4.5, "Text", "Terminal ANSI Magenta"),
    ("ansi-white", "terminal-bg", 4.5, "Text", "Terminal ANSI White"),
    ("ansi-black", "terminal-bg", 4.5, "Text", "Terminal ANSI Black"),
]


def evaluate_theme(theme_name: str, tokens: dict[str, str]) -> tuple[bool, list[dict]]:
    """Evaluate contrast ratios for a specific theme."""
    results = []
    all_passed = True

    for fg_token, bg_token, req, category, desc in PAIRS_TO_CHECK:
        fg_hex = tokens.get(fg_token)
        bg_hex = tokens.get(bg_token)

        if not fg_hex or not bg_hex:
            all_passed = False
            results.append(
                {
                    "theme": theme_name,
                    "category": category,
                    "fg_token": fg_token,
                    "bg_token": bg_token,
                    "fg_hex": fg_hex or "MISSING",
                    "bg_hex": bg_hex or "MISSING",
                    "ratio": 0.0,
                    "required": req,
                    "status": "FAIL (Missing Token)",
                    "desc": desc,
                }
            )
            continue

        ratio = contrast_ratio(fg_hex, bg_hex)
        passed = ratio >= req
        if not passed:
            all_passed = False

        results.append(
            {
                "theme": theme_name,
                "category": category,
                "fg_token": fg_token,
                "bg_token": bg_token,
                "fg_hex": fg_hex,
                "bg_hex": bg_hex,
                "ratio": ratio,
                "required": req,
                "status": "PASS" if passed else "FAIL",
                "desc": desc,
            }
        )

    return all_passed, results


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    tokens_file = repo_root / "src" / "deskai" / "static" / "css" / "tokens.css"

    if not tokens_file.exists():
        print(f"Error: tokens.css not found at {tokens_file}", file=sys.stderr)
        return 1

    dark_tokens, light_tokens = parse_tokens(tokens_file)

    overall_pass = True
    print("\n" + "=" * 92)
    print("                     DESKAI WCAG 2.1 CONTRAST VERIFICATION REPORT")
    print("=" * 92)

    for theme_name, tokens in [("Dark Theme", dark_tokens), ("Light Theme", light_tokens)]:
        passed, results = evaluate_theme(theme_name, tokens)
        if not passed:
            overall_pass = False

        print(f"\n--- {theme_name.upper()} ---")
        header_fmt = "{:<6} | {:<4} | {:<18} | {:<16} | {:<7} | {:<7} | {:<7} | {:<8}"
        print(header_fmt.format("Status", "Cat", "Foreground", "Background", "FG Hex", "BG Hex", "Ratio", "Required"))
        print("-" * 92)
        for r in results:
            row_fmt = "{:<6} | {:<4} | {:<18} | {:<16} | {:<7} | {:<7} | {:5.2f}:1 | >={:.1f}:1"
            print(
                row_fmt.format(
                    r["status"],
                    r["category"],
                    r["fg_token"],
                    r["bg_token"],
                    r["fg_hex"],
                    r["bg_hex"],
                    r["ratio"],
                    r["required"],
                )
            )

    print("\n" + "=" * 92)
    if overall_pass:
        print("RESULT: ALL THEME TOKEN PAIRS MEET OR EXCEED WCAG 2.1 AA REQUIREMENTS.")
        print("=" * 92 + "\n")
        return 0
    else:
        print("RESULT: ONE OR MORE THEME TOKEN PAIRS FAILED WCAG 2.1 AA REQUIREMENTS.", file=sys.stderr)
        print("=" * 92 + "\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
