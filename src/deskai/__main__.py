"""
DeskAI Application Main Entrypoint.
Usage:
    python -m deskai
"""
import sys
from deskai.bridge.window import WindowManager


def main():
    debug = "--debug" in sys.argv
    manager = WindowManager()
    manager.run(debug=debug)


if __name__ == "__main__":
    main()
