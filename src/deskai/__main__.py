"""
DeskAI Application Main Entrypoint.
Usage:
    python -m deskai [workspace_dir] [--debug]
"""

import os
import sys
from deskai.bridge.window import WindowManager


def main():
    debug = "--debug" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--debug"]
    initial_workspace = None
    if args:
        candidate = os.path.abspath(args[0])
        if os.path.isdir(candidate):
            initial_workspace = candidate

    manager = WindowManager(initial_workspace=initial_workspace)
    manager.run(debug=debug)


if __name__ == "__main__":
    main()
