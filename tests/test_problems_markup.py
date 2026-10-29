from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from deskai.diagnostics.html_syntax import check_html
from deskai.diagnostics.runner import run_checks
from deskai.diagnostics.toml_syntax import check_toml
from deskai.diagnostics.xml_syntax import check_xml


class TestProblemsMarkupCheckers(unittest.TestCase):
    def test_toml_valid(self) -> None:
        source = """
[project]
name = "deskai"
version = "3.0.0"
authors = [{ name = "Daniyal" }]
"""
        diags = check_toml(source, "pyproject.toml")
        self.assertEqual(len(diags), 0)

    def test_toml_syntax_error(self) -> None:
        source = """
[project]
name = "deskai
version = "3.0.0"
"""
        diags = check_toml(source, "pyproject.toml")
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0].source, "toml")
        self.assertEqual(diags[0].severity, "error")
        self.assertEqual(diags[0].code, "TOMLDecodeError")
        self.assertEqual(diags[0].start_line, 3)

    def test_html_valid_with_void_tags(self) -> None:
        source = """<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8">
    <link rel="stylesheet" href="style.css">
  </head>
  <body>
    <h1>DeskAI</h1>
    <img src="logo.png" alt="logo">
    <br>
    <input type="text">
  </body>
</html>"""
        diags = check_html(source, "index.html")
        self.assertEqual(len(diags), 0)

    def test_html_mismatched_tags(self) -> None:
        source = """<div><span>Mismatched</div></span>"""
        diags = check_html(source, "index.html")
        self.assertGreaterEqual(len(diags), 1)
        mismatched = [d for d in diags if d.code == "HTML_MISMATCHED_TAG"]
        self.assertGreaterEqual(len(mismatched), 1)
        self.assertIn("expected </span>", mismatched[0].message)

    def test_html_unclosed_tag(self) -> None:
        source = """<section><p>Unclosed paragraph</section>"""
        diags = check_html(source, "partial.html")
        self.assertGreaterEqual(len(diags), 1)
        self.assertTrue(any("unclosed" in d.message.lower() or "mismatched" in d.message.lower() for d in diags))

    def test_xml_valid(self) -> None:
        source = """<?xml version="1.0" encoding="UTF-8"?>
<note>
  <to>Tove</to>
  <from>Jani</from>
  <heading>Reminder</heading>
  <body>Don't forget me this weekend!</body>
</note>"""
        diags = check_xml(source, "note.xml")
        self.assertEqual(len(diags), 0)

    def test_xml_syntax_error(self) -> None:
        source = """<root><child>Broken</root>"""
        diags = check_xml(source, "data.xml")
        self.assertEqual(len(diags), 1)
        self.assertEqual(diags[0].source, "xml")
        self.assertEqual(diags[0].severity, "error")
        self.assertEqual(diags[0].code, "ParseError")

    def test_runner_on_disk_integration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            # Create a broken TOML file
            toml_file = tmppath / "settings.toml"
            toml_file.write_text("broken = [1, 2,\n", encoding="utf-8")

            res = run_checks(str(toml_file), str(tmppath), "req-1")
            self.assertEqual(res["status"], "ok")
            self.assertEqual(len(res["diagnostics"]), 1)
            self.assertEqual(res["diagnostics"][0]["source"], "toml")

            # Create an invalid SVG file
            svg_file = tmppath / "icon.svg"
            svg_file.write_text("<svg><path></svg>", encoding="utf-8")

            res_svg = run_checks(str(svg_file), str(tmppath), "req-2")
            self.assertEqual(res_svg["status"], "ok")
            self.assertEqual(len(res_svg["diagnostics"]), 1)
            self.assertEqual(res_svg["diagnostics"][0]["source"], "xml")


if __name__ == "__main__":
    unittest.main()
