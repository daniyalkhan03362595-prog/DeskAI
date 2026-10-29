from __future__ import annotations
import logging
import shutil
import subprocess
import sys
from deskai.bridge.base import BaseBridgeModule

logger = logging.getLogger(__name__)


class ClipboardBridge(BaseBridgeModule):
    """Bridge module providing cross-platform OS clipboard read/write capabilities."""

    def clipboard_write(self, text: str = "") -> dict:
        """Writes text string to the system clipboard."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin"}
        if text is None:
            text = ""

        try:
            if sys.platform == "win32":
                return self._win32_write(text)
            else:
                return self._linux_write(text)
        except Exception as e:
            logger.exception("clipboard_write failed")
            return {"status": "error", "message": str(e)}

    def clipboard_read(self) -> dict:
        """Reads text string from the system clipboard."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin", "text": ""}

        try:
            if sys.platform == "win32":
                return self._win32_read()
            else:
                return self._linux_read()
        except Exception as e:
            logger.exception("clipboard_read failed")
            return {"status": "error", "message": str(e), "text": ""}

    def _win32_write(self, text: str) -> dict:
        import ctypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002

        if not user32.OpenClipboard(0):
            return {"status": "error", "message": "Failed to open clipboard"}
        try:
            user32.EmptyClipboard()
            encoded = text.encode("utf-16-le") + b"\x00\x00"
            h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
            if h_mem:
                p_mem = kernel32.GlobalLock(h_mem)
                if p_mem:
                    ctypes.memmove(p_mem, encoded, len(encoded))
                    kernel32.GlobalUnlock(h_mem)
                    user32.SetClipboardData(CF_UNICODETEXT, h_mem)
            return {"status": "ok"}
        finally:
            user32.CloseClipboard()

    def _win32_read(self) -> dict:
        import ctypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        CF_UNICODETEXT = 13

        if not user32.OpenClipboard(0):
            return {"status": "error", "message": "Failed to open clipboard", "text": ""}
        try:
            h_mem = user32.GetClipboardData(CF_UNICODETEXT)
            if not h_mem:
                return {"status": "ok", "text": ""}
            p_mem = kernel32.GlobalLock(h_mem)
            if not p_mem:
                return {"status": "ok", "text": ""}
            try:
                text = ctypes.wstring_at(p_mem)
                return {"status": "ok", "text": text}
            finally:
                kernel32.GlobalUnlock(h_mem)
        finally:
            user32.CloseClipboard()

    def _linux_write(self, text: str) -> dict:
        # 1. Try GTK clipboard (standard in PyWebView WebKitGTK on Linux)
        try:
            import gi

            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk, Gdk

            cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            cb.set_text(text, -1)
            cb.store()
            return {"status": "ok"}
        except Exception:
            pass

        # 2. Try CLI clipboard utilities (wl-copy, xclip, xsel)
        if shutil.which("wl-copy"):
            try:
                subprocess.run(["wl-copy"], input=text.encode("utf-8"), check=True, timeout=2.0)
                return {"status": "ok"}
            except Exception:
                pass

        if shutil.which("xclip"):
            try:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=text.encode("utf-8"),
                    check=True,
                    timeout=2.0,
                )
                return {"status": "ok"}
            except Exception:
                pass

        if shutil.which("xsel"):
            try:
                subprocess.run(["xsel", "--clipboard", "--input"], input=text.encode("utf-8"), check=True, timeout=2.0)
                return {"status": "ok"}
            except Exception:
                pass

        return {"status": "error", "message": "No Linux clipboard backend available"}

    def _linux_read(self) -> dict:
        # 1. Try GTK clipboard
        try:
            import gi

            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk, Gdk

            cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            val = cb.wait_for_text()
            return {"status": "ok", "text": val or ""}
        except Exception:
            pass

        # 2. Try CLI clipboard utilities (wl-paste, xclip, xsel)
        if shutil.which("wl-paste"):
            try:
                out = subprocess.check_output(["wl-paste", "--no-newline"], timeout=2.0)
                return {"status": "ok", "text": out.decode("utf-8", "replace")}
            except Exception:
                pass

        if shutil.which("xclip"):
            try:
                out = subprocess.check_output(["xclip", "-selection", "clipboard", "-out"], timeout=2.0)
                return {"status": "ok", "text": out.decode("utf-8", "replace")}
            except Exception:
                pass

        if shutil.which("xsel"):
            try:
                out = subprocess.check_output(["xsel", "--clipboard", "--output"], timeout=2.0)
                return {"status": "ok", "text": out.decode("utf-8", "replace")}
            except Exception:
                pass

        return {"status": "ok", "text": ""}
