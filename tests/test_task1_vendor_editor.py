import hashlib
import json
from pathlib import Path
import unittest
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = REPO_ROOT / "src" / "deskai" / "static" / "vendor"
MANIFEST_PATH = VENDOR_DIR / "MANIFEST.json"


class TestTask1VendorAndEditor(unittest.TestCase):
    def test_manifest_exists_and_hashes_match(self):
        """Verifies MANIFEST.json exists and all SHA-256 hashes match files on disk."""
        self.assertTrue(MANIFEST_PATH.exists(), f"MANIFEST.json not found at {MANIFEST_PATH}")
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        required_keys = ["purify.min.js", "marked.min.js", "codemirror.bundle.js"]
        for key in required_keys:
            self.assertIn(key, manifest, f"Missing {key} in MANIFEST.json")
            entry = manifest[key]
            self.assertIn("version", entry)
            self.assertIn("sha256", entry)
            self.assertIn("url", entry)

            file_path = VENDOR_DIR / key
            self.assertTrue(file_path.exists(), f"Vendor file {key} does not exist")
            content = file_path.read_bytes()
            computed_hash = hashlib.sha256(content).hexdigest()
            self.assertEqual(
                computed_hash,
                entry["sha256"],
                f"Hash mismatch for {key}: expected {entry['sha256']}, got {computed_hash}",
            )

    def test_vendor_libraries_and_editor_in_browser(self):
        """Playwright test checking real DOMPurify, marked, and CodeMirror 6 EditorView."""
        self.assertTrue(MANIFEST_PATH.exists(), "MANIFEST.json must exist")
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        purify_path = str(VENDOR_DIR / "purify.min.js")
        marked_path = str(VENDOR_DIR / "marked.min.js")
        cm_path = str(VENDOR_DIR / "codemirror.bundle.js")

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto("about:blank")

            page.add_script_tag(path=purify_path)
            page.add_script_tag(path=marked_path)
            page.add_script_tag(path=cm_path)

            # 1. Verify DOMPurify
            dompurify_version = page.evaluate("window.DOMPurify ? window.DOMPurify.version : null")
            self.assertEqual(dompurify_version, manifest["purify.min.js"]["version"])
            has_add_hook = page.evaluate("typeof window.DOMPurify.addHook === 'function'")
            self.assertTrue(has_add_hook, "DOMPurify.addHook must be a function")

            # 2. Verify marked
            has_marked_use = page.evaluate("typeof window.marked.use === 'function'")
            has_marked_lexer = page.evaluate("typeof window.marked.Lexer === 'function'")
            self.assertTrue(has_marked_use, "marked.use must be a function")
            self.assertTrue(has_marked_lexer, "marked.Lexer must be a function")

            # 3. Verify CodeMirror 6 exports
            has_editor_view = page.evaluate("typeof window.CodeMirror.EditorView === 'function'")
            has_editor_state = page.evaluate("typeof window.CodeMirror.EditorState === 'function'")
            self.assertTrue(has_editor_view, "CodeMirror.EditorView must exist")
            self.assertTrue(has_editor_state, "CodeMirror.EditorState must exist")

            # 4. Instantiate CodeMirror 6 EditorView with Python syntax highlighting
            eval_res = page.evaluate("""() => {
              const host = document.createElement('div');
              host.id = 'editorHost';
              document.body.appendChild(host);

              const { EditorView, EditorState, createBasicExtensions } = window.CodeMirror;
              const state = EditorState.create({
                doc: 'def hello_world():\\n    return 42',
                extensions: createBasicExtensions({ language: 'python' })
              });
              const view = new EditorView({ state, parent: host });
              const cmEditor = host.querySelector('.cm-editor');
              const lineNumbers = host.querySelector('.cm-lineNumbers');
              const tokenSpans = Array.from(host.querySelectorAll('.cm-line span')).map(el => el.textContent);
              return {
                mounted: !!cmEditor,
                hasGutters: !!lineNumbers,
                numTokens: tokenSpans.length,
                tokens: tokenSpans
              };
            }""")
            self.assertTrue(eval_res["mounted"], "CodeMirror EditorView was not mounted")
            self.assertTrue(eval_res["hasGutters"], "Line numbers gutter was not rendered")
            self.assertGreater(eval_res["numTokens"], 0, "No syntax highlighted tokens found")
            self.assertIn("def", eval_res["tokens"], "Expected 'def' keyword token")
            self.assertIn("return", eval_res["tokens"], "Expected 'return' keyword token")

            browser.close()


if __name__ == "__main__":
    unittest.main()
