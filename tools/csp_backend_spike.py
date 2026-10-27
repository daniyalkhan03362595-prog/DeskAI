"""
Reproducible Per-Backend Spike: CSP 'unsafe-eval' Dependency in PyWebView.

Verifies whether the current PyWebView platform backend requires 'unsafe-eval'
in Content-Security-Policy to execute window.evaluate_js().

Usage:
    python tools/csp_backend_spike.py
"""

import sys
import threading
import time
import webview


def run_spike() -> dict:
    platform = sys.platform
    gui_backend = "gtk" if platform.startswith("linux") else None

    results = {
        "platform": platform,
        "gui_backend": gui_backend or "default",
        "tested_backend": None,
        "without_unsafe_eval": None,
        "with_unsafe_eval": None,
    }

    print(f"[CSP Spike] Platform: {platform}, Backend: {gui_backend or 'default'}")

    # 1. Test Without 'unsafe-eval'
    html_without = """
    <!DOCTYPE html>
    <html>
    <head>
      <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self';">
    </head>
    <body><h3>Testing without unsafe-eval</h3></body>
    </html>
    """

    err_without = None

    def bg_without(w):
        nonlocal err_without
        time.sleep(0.8)
        try:
            val = w.evaluate_js("2 + 2")
            results["without_unsafe_eval"] = {"success": True, "value": val}
        except Exception as e:
            err_without = e
            results["without_unsafe_eval"] = {
                "success": False,
                "error_type": type(e).__name__,
                "error_details": str(e),
            }
        finally:
            w.destroy()

    win1 = webview.create_window("CSP Spike (No unsafe-eval)", html=html_without)
    t1 = threading.Thread(target=bg_without, args=(win1,), daemon=True)
    t1.start()
    try:
        webview.start(gui=gui_backend)
        results["tested_backend"] = f"{platform} ({gui_backend or 'default'})"
    except Exception as e:
        print(f"[CSP Spike] Error starting webview: {e}")
        results["tested_backend"] = f"Failed to start: {e}"
        return results

    # 2. Test With 'unsafe-eval'
    html_with = """
    <!DOCTYPE html>
    <html>
    <head>
      <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-eval';">
    </head>
    <body><h3>Testing with unsafe-eval</h3></body>
    </html>
    """

    def bg_with(w):
        time.sleep(0.8)
        try:
            val = w.evaluate_js("2 + 2")
            results["with_unsafe_eval"] = {"success": True, "value": val}
        except Exception as e:
            results["with_unsafe_eval"] = {
                "success": False,
                "error_type": type(e).__name__,
                "error_details": str(e),
            }
        finally:
            w.destroy()

    win2 = webview.create_window("CSP Spike (With unsafe-eval)", html=html_with)
    t2 = threading.Thread(target=bg_with, args=(win2,), daemon=True)
    t2.start()
    try:
        webview.start(gui=gui_backend)
    except Exception as e:
        print(f"[CSP Spike] Error starting webview: {e}")

    return results


def main():
    res = run_spike()
    print("\n================== CSP SPIKE RESULTS ==================")
    print(f"Platform: {res['platform']}")
    print(f"Tested Backend: {res['tested_backend']}")
    print(f"Without 'unsafe-eval': {res['without_unsafe_eval']}")
    print(f"With 'unsafe-eval':    {res['with_unsafe_eval']}")
    print("=======================================================\n")

    untested = []
    if sys.platform != "win32":
        untested.append("Windows (Edge WebView2 / WinForms)")
    if sys.platform != "darwin":
        untested.append("macOS (WebKit / Cocoa)")

    if untested:
        print(f"[Note] The following backends were NOT tested in this environment: {', '.join(untested)}")


if __name__ == "__main__":
    main()
