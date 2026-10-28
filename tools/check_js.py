#!/usr/bin/env python3
"""
DeskAI JavaScript Syntax & Static Analysis Verification.
Ensures all frontend ES modules are syntactically valid and pass Node.js module parsing.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_JS_DIR = REPO_ROOT / "src" / "deskai" / "static" / "js"


def main() -> int:
    js_files = [f for f in STATIC_JS_DIR.rglob("*.js") if "vendor" not in f.parts]
    if not js_files:
        print("Error: No JavaScript files found to check.", file=sys.stderr)
        return 1

    errors = 0
    for js_file in sorted(js_files):
        rel_path = js_file.relative_to(REPO_ROOT)
        with open(js_file, "rb") as fh:
            res = subprocess.run(
                ["node", "--input-type=module", "--check"],
                stdin=fh,
                capture_output=True,
                text=True,
            )
            if res.returncode != 0:
                print(f"FAILED: {rel_path}\n{res.stderr}", file=sys.stderr)
                errors += 1
            else:
                # OK
                pass

    if errors > 0:
        print(f"\nJavaScript syntax check failed: {errors} file(s) with errors.", file=sys.stderr)
        return 1

    print(f"Verified {len(js_files)} frontend JavaScript files (all passed syntax check).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
