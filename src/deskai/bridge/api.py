"""
DesktopBridgeAPI Implementation:
Exposed to JavaScript via window.pywebview.api.
Handles native dialogs, external URL dispatch, window controls, and path sandboxing.
"""

import ipaddress
import os
import socket
import sys
from urllib.parse import urlsplit
import webbrowser
from typing import TYPE_CHECKING
import webview

from deskai.utils.path import is_safe_workspace_path, canonicalize_path, is_disallowed_workspace_root

if TYPE_CHECKING:
    from deskai.bridge.window import WindowManager


_LOOPBACK_HOSTS = {"127.0.0.1", "[::1]"}


def _is_safe_external_url(url: str) -> bool:
    """
    Validates external URL string strictly.
    Rejects control characters, length > 2048, missing hostname, userinfo spoofing, and dangerous schemes.
    """
    if not isinstance(url, str) or len(url) > 2048:
        return False
    url = url.strip()
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in url):
        return False
    try:
        p = urlsplit(url)
    except ValueError:
        return False
    scheme = p.scheme.lower()
    if scheme in ("http", "https"):
        return bool(p.hostname) and not p.username
    if scheme == "mailto":
        return bool(p.path)
    return False


def _reachable_host(ip: str):
    """
    Translates an IP string to (host, exposure) for loopback reachability.
    Unwraps IPv4-mapped IPv6, returning ('127.0.0.1' or '[::1]', 'loopback' | 'all-interfaces')
    for local or unspecified binds, or None if external/LAN-only.
    """
    try:
        clean_ip = ip.split("%", 1)[0]
        addr = ipaddress.ip_address(clean_ip)
    except ValueError:
        return None
    if addr.version == 6 and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    host = "127.0.0.1" if addr.version == 4 else "[::1]"
    if addr.is_loopback:
        return host, "loopback"
    if addr.is_unspecified:
        return host, "all-interfaces"
    return None


# Support both pywebview 6.x (webview.FileDialog) and 5.x (webview.FOLDER_DIALOG)
def _get_dialog_type(name: str, fallback_attr: str, default_code: int):
    file_dialog = getattr(webview, "FileDialog", None)
    if file_dialog and hasattr(file_dialog, name):
        return getattr(file_dialog, name)
    return getattr(webview, fallback_attr, default_code)


DIALOG_FOLDER = _get_dialog_type("FOLDER", "FOLDER_DIALOG", 20)
DIALOG_OPEN = _get_dialog_type("OPEN", "OPEN_DIALOG", 10)
DIALOG_SAVE = _get_dialog_type("SAVE", "SAVE_DIALOG", 30)

# Windows Hit-Test Codes & Semantic Resize Direction Mapping
RESIZE_DIRECTIONS = {
    "n": 12,
    "s": 15,
    "w": 10,
    "e": 11,
    "nw": 13,
    "ne": 14,
    "sw": 16,
    "se": 17,
    "top": 12,
    "bottom": 15,
    "left": 10,
    "right": 11,
    "top-left": 13,
    "top-right": 14,
    "bottom-left": 16,
    "bottom-right": 17,
    "move": 2,
}


def _windows_native_drag(window: webview.Window, ht_code: int) -> bool:
    """Dispatches native Windows WM_NCLBUTTONDOWN message via ctypes."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = getattr(window, "native", None)
        if not isinstance(hwnd, int):
            raw_title = getattr(window, "title", None)
            title = raw_title if isinstance(raw_title, str) and raw_title else "DeskAI"
            hwnd = user32.FindWindowW(None, title)
        if isinstance(hwnd, int) and hwnd > 0:
            WM_NCLBUTTONDOWN = 0x00A1
            user32.ReleaseCapture()
            user32.SendMessageW(hwnd, WM_NCLBUTTONDOWN, ht_code, 0)
            return True
    except Exception as e:
        print(f"[DeskAI] Windows native drag error: {e}")
    return False


class DesktopBridgeAPI:
    def __init__(self, manager: "WindowManager"):
        self._manager = manager
        self.workspace_root: str | None = None
        self._terminal_confirmed_in_session: bool = False

    @property
    def _window(self) -> webview.Window:
        return self._manager.window

    def _is_origin_allowed(self) -> bool:
        """Ensures caller originates strictly from the local application origin."""
        if not self._window:
            return False
        port = getattr(getattr(self._manager, "server", None), "port", None)
        if port is None:
            return False
        get_url = getattr(self._window, "get_current_url", None)
        if not get_url:
            return False
        current_url = get_url() or ""
        expected_origin = f"http://127.0.0.1:{port}"
        if current_url.startswith(expected_origin):
            suffix = current_url[len(expected_origin) :]
            if not suffix or suffix.startswith(("/", "?", "#")):
                return True
        return False

    def select_folder(self) -> dict:
        """Opens native OS folder selection dialog."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin", "path": None}
        selected = self._window.create_file_dialog(DIALOG_FOLDER)
        if selected and len(selected) > 0:
            folder_path = canonicalize_path(selected[0])
            if is_disallowed_workspace_root(folder_path):
                return {"status": "error", "message": "Disallowed system directory", "path": None}
            self.workspace_root = folder_path
            return {"status": "ok", "path": folder_path, "name": os.path.basename(folder_path)}
        return {"status": "cancelled", "path": None}

    def select_file(self) -> dict:
        """Opens native OS file selection dialog."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin", "path": None}
        selected = self._window.create_file_dialog(DIALOG_OPEN)
        if selected and len(selected) > 0:
            file_path = canonicalize_path(selected[0])
            if not self.workspace_root:
                parent_dir = os.path.dirname(file_path)
                if not is_disallowed_workspace_root(parent_dir):
                    self.workspace_root = parent_dir
            return {
                "status": "ok",
                "path": file_path,
                "name": os.path.basename(file_path),
                "workspace_root": self.workspace_root,
            }
        return {"status": "cancelled", "path": None}

    def save_file_dialog(self, default_name: str = "untitled.txt") -> dict:
        """Opens native OS file save dialog."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin", "path": None}
        selected = self._window.create_file_dialog(DIALOG_SAVE, save_filename=default_name)
        if selected:
            return {"status": "ok", "path": canonicalize_path(selected)}
        return {"status": "cancelled", "path": None}

    def open_external_url(self, url: str) -> bool:
        """
        Dispatches web URLs to the user's default OS browser.
        Blocks javascript:, file:, or malformed/hostile URLs.
        """
        if not self._is_origin_allowed():
            return False
        if not _is_safe_external_url(url):
            return False
        return bool(webbrowser.open(url.strip()))

    def open_port(self, port: int, host: str = "127.0.0.1") -> bool:
        """
        Opens a validated loopback port in the default browser.
        Origin guarded; only accepts real integer port numbers and loopback hosts.
        Refuses the internal supervisor port (which requires internal launch cookie).
        """
        if not self._is_origin_allowed():
            return False
        if isinstance(port, bool) or not isinstance(port, int) or not (1 <= port <= 65535):
            return False
        if host not in _LOOPBACK_HOSTS:
            return False
        supervisor_port = getattr(getattr(self._manager, "server", None), "port", None)
        if supervisor_port and port == supervisor_port:
            return False
        return bool(webbrowser.open(f"http://{host}:{port}"))

    def probe_port(self, port: int, host: str = "127.0.0.1") -> bool:
        """
        Probes whether a loopback port is actively listening with ~150ms timeout.
        """
        if not self._is_origin_allowed():
            return False
        if isinstance(port, bool) or not isinstance(port, int) or not (1 <= port <= 65535):
            return False
        if host not in _LOOPBACK_HOSTS:
            return False
        target_host = "::1" if host == "[::1]" else host
        family = socket.AF_INET6 if ":" in target_host else socket.AF_INET
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.15)
                res = sock.connect_ex((target_host, port))
                return res == 0
        except Exception:
            return False

    def drag_window(self, timestamp: float | None = None) -> bool:
        """Initiates native window move drag across Windows and Linux (Wayland/X11)."""
        if not self._is_origin_allowed():
            return False

        if sys.platform == "win32":
            return _windows_native_drag(self._window, 2)

        native = getattr(self._window, "native", None)
        if native and hasattr(native, "begin_move_drag"):
            try:
                from gi.repository import GLib, Gdk

                def _do_drag():
                    try:
                        display = Gdk.Display.get_default()
                        if display:
                            seat = display.get_default_seat()
                            if seat:
                                pointer = seat.get_pointer()
                                if pointer:
                                    _, x, y = pointer.get_position()
                                    native.begin_move_drag(1, int(x), int(y), Gdk.CURRENT_TIME)
                    except Exception as e:
                        print(f"[DeskAI] Native drag error: {e}")

                GLib.idle_add(_do_drag)
                return True
            except Exception as e:
                print(f"[DeskAI] Bridge drag error: {e}")
                return False
        return False

    def resize_window(self, edge: str, timestamp: float | None = None) -> bool:
        """Initiates native window resize drag across Windows and Linux (Wayland/X11)."""
        if not self._is_origin_allowed():
            return False

        if edge not in RESIZE_DIRECTIONS:
            raise ValueError(f"Invalid resize direction: {edge}")

        if sys.platform == "win32":
            ht_code = RESIZE_DIRECTIONS[edge]
            return _windows_native_drag(self._window, ht_code)

        native = getattr(self._window, "native", None)
        if native and hasattr(native, "begin_resize_drag"):
            try:
                from gi.repository import GLib, Gdk

                if hasattr(native, "is_maximized") and native.is_maximized():
                    return False

                edge_map = {
                    "top": Gdk.WindowEdge.NORTH,
                    "n": Gdk.WindowEdge.NORTH,
                    "bottom": Gdk.WindowEdge.SOUTH,
                    "s": Gdk.WindowEdge.SOUTH,
                    "left": Gdk.WindowEdge.WEST,
                    "w": Gdk.WindowEdge.WEST,
                    "right": Gdk.WindowEdge.EAST,
                    "e": Gdk.WindowEdge.EAST,
                    "top-left": Gdk.WindowEdge.NORTH_WEST,
                    "nw": Gdk.WindowEdge.NORTH_WEST,
                    "top-right": Gdk.WindowEdge.NORTH_EAST,
                    "ne": Gdk.WindowEdge.NORTH_EAST,
                    "bottom-left": Gdk.WindowEdge.SOUTH_WEST,
                    "sw": Gdk.WindowEdge.SOUTH_WEST,
                    "bottom-right": Gdk.WindowEdge.SOUTH_EAST,
                    "se": Gdk.WindowEdge.SOUTH_EAST,
                }
                edge_enum = edge_map.get(edge)
                if edge_enum is None:
                    return False

                def _do_resize():
                    try:
                        display = Gdk.Display.get_default()
                        if display:
                            seat = display.get_default_seat()
                            if seat:
                                pointer = seat.get_pointer()
                                if pointer:
                                    _, x, y = pointer.get_position()
                                    native.begin_resize_drag(edge_enum, 1, int(x), int(y), Gdk.CURRENT_TIME)
                    except Exception as e:
                        print(f"[DeskAI] Native resize error: {e}")

                GLib.idle_add(_do_resize)
                return True
            except Exception as e:
                print(f"[DeskAI] Bridge resize error: {e}")
                return False
        return False

    def resize_window_absolute(self, width: int, height: int) -> bool:
        """Directly resizes native window frame to specified dimensions."""
        if not self._is_origin_allowed():
            return False
        w = max(900, int(width))
        h = max(600, int(height))
        try:
            self._window.resize(w, h)
            return True
        except Exception as e:
            print(f"[DeskAI] Window resize error: {e}")
            return False

    def window_control(self, action: str, direction: str | None = None, timestamp: float | None = None) -> bool:
        """Handles native window frame buttons and frameless drag/resize actions."""
        if not self._is_origin_allowed():
            return False

        valid_actions = {
            "minimize",
            "maximize",
            "close",
            "close_request",
            "drag_start",
            "resize_start",
            "resize_absolute",
        }
        if action not in valid_actions:
            raise ValueError(f"Unknown window control action: {action}")

        if action == "minimize":
            self._window.minimize()
            return True
        elif action == "maximize":
            # Toggle maximize/restore
            native = getattr(self._window, "native", None)
            if native and hasattr(native, "is_maximized"):
                try:
                    from gi.repository import GLib

                    if native.is_maximized():
                        GLib.idle_add(native.unmaximize)
                    else:
                        GLib.idle_add(native.maximize)
                    return True
                except Exception:
                    pass
            self._window.toggle_fullscreen()
            return True
        elif action == "close":
            if self._manager.lifecycle.confirm_exit():
                self._manager.lifecycle._exit_confirmed = True
                self._window.destroy()
                return True
            return False
        elif action == "close_request":
            if not self._manager.lifecycle.has_dirty_tabs and not self._manager.lifecycle.has_running_terminal:
                self._manager.lifecycle._exit_confirmed = True
                self._window.destroy()
                return True
            return False
        elif action == "drag_start":
            return self.drag_window(timestamp=timestamp)
        elif action == "resize_start":
            if not direction or direction not in RESIZE_DIRECTIONS:
                raise ValueError(f"Invalid resize direction: {direction}")
            return self.resize_window(direction, timestamp=timestamp)
        return False

    def set_dirty_status(self, is_dirty: bool):
        """Pushed by frontend whenever active editor buffers change."""
        if not self._is_origin_allowed():
            return
        self._manager.lifecycle.has_dirty_tabs = bool(is_dirty)

    def read_file(self, target_path: str) -> dict:
        """Reads sandboxed file within workspace root. Max 10MB."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin", "content": None}
        if not self._is_safe_path(target_path):
            return {"status": "error", "message": "Access denied: Path outside workspace", "content": None}

        canonical = canonicalize_path(target_path)
        if not os.path.isfile(canonical):
            return {"status": "error", "message": "File not found", "content": None}

        if os.path.getsize(canonical) > 10 * 1024 * 1024:
            return {"status": "error", "message": "File exceeds maximum 10MB size limit", "content": None}

        try:
            with open(canonical, "r", encoding="utf-8") as f:
                content = f.read()
            return {"status": "ok", "content": content, "path": canonical}
        except UnicodeDecodeError:
            return {"status": "error", "message": "File is not valid UTF-8 text", "content": None}
        except Exception as e:
            return {"status": "error", "message": str(e), "content": None}

    def write_file(self, target_path: str, content: str) -> dict:
        """Atomically writes file within workspace root."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin"}
        if not self._is_safe_path(target_path):
            return {"status": "error", "message": "Access denied: Path outside workspace"}

        canonical = canonicalize_path(target_path)
        parent_dir = os.path.dirname(canonical)
        os.makedirs(parent_dir, exist_ok=True)

        import tempfile

        try:
            with tempfile.NamedTemporaryFile("w", dir=parent_dir, encoding="utf-8", delete=False) as tf:
                tf.write(content)
                tf.flush()
                os.fsync(tf.fileno())
                temp_name = tf.name
            os.replace(temp_name, canonical)
            return {"status": "ok", "path": canonical}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def list_dir(self, target_path: str | None = None) -> dict:
        """Lists directory entries safely inside workspace root."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin", "entries": []}

        path_to_list = target_path if target_path else self.workspace_root
        if not path_to_list or not self._is_safe_path(path_to_list):
            return {"status": "error", "message": "Access denied: Path outside workspace", "entries": []}

        canonical = canonicalize_path(path_to_list)
        if not os.path.isdir(canonical):
            return {"status": "error", "message": "Directory not found", "entries": []}

        try:
            entries = []
            with os.scandir(canonical) as it:
                for entry in it:
                    if entry.name.startswith("."):
                        continue
                    entries.append(
                        {
                            "name": entry.name,
                            "is_dir": entry.is_dir(),
                            "path": canonicalize_path(entry.path),
                        }
                    )
            entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
            return {"status": "ok", "entries": entries, "path": canonical}
        except Exception as e:
            return {"status": "error", "message": str(e), "entries": []}

    def get_system_telemetry(self) -> dict:
        """Returns real host system telemetry or fallback values."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin", "telemetry": None}

        telemetry = {
            "gpuName": "--",
            "vramUsedMB": "--",
            "vramTotalMB": "--",
            "cpuUsagePct": "--",
            "ramUsedMB": "--",
            "status": "ready",
        }

        try:
            import platform

            telemetry["platform"] = platform.system()

            # Attempt real memory telemetry
            if os.name != "nt" and os.path.exists("/proc/meminfo"):
                mem = {}
                with open("/proc/meminfo", "r") as f:
                    for line in f:
                        parts = line.split(":")
                        if len(parts) == 2:
                            mem[parts[0].strip()] = parts[1].strip()
                if "MemTotal" in mem and "MemAvailable" in mem:
                    total_kb = int(mem["MemTotal"].split()[0])
                    avail_kb = int(mem["MemAvailable"].split()[0])
                    used_mb = (total_kb - avail_kb) // 1024
                    telemetry["ramUsedMB"] = used_mb
                    telemetry["ramTotalMB"] = total_kb // 1024
        except Exception:
            pass

        return {"status": "ok", "telemetry": telemetry}

    def get_listening_ports(self) -> dict:
        """
        Enumerates active local listening ports on loopback and host interfaces.
        Always includes the DeskAI supervisor port.
        """
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin", "ports": []}

        warnings = []
        rows = {}

        try:
            import psutil
        except ImportError:
            psutil = None
            warnings.append("psutil_missing")

        if psutil:
            try:
                conns = psutil.net_connections(kind="inet")
            except (psutil.AccessDenied, PermissionError):
                conns = []
                warnings.append("socket_table_denied")
            except Exception:
                conns = []

            names: dict[int, str] = {}
            listen_status = getattr(psutil, "CONN_LISTEN", "LISTEN")
            for c in conns:
                status = getattr(c, "status", None)
                if status != listen_status and status != "LISTEN":
                    continue
                laddr = getattr(c, "laddr", None)
                if not laddr or not hasattr(laddr, "port") or laddr.port < 1024:
                    continue
                target = _reachable_host(getattr(laddr, "ip", ""))
                if target is None:
                    continue
                host, exposure = target
                port = laddr.port
                pid = getattr(c, "pid", None)
                if pid is not None and pid not in names:
                    try:
                        proc = psutil.Process(pid)
                        names[pid] = proc.name()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        names[pid] = f"PID {pid}"
                    except Exception:
                        names[pid] = f"PID {pid}"

                proc_name = names.get(pid, "Restricted") if pid is not None else "Restricted"
                rows[(port, host)] = {
                    "port": port,
                    "host": host,
                    "address": f"http://{host}:{port}",
                    "protocol": "TCP",
                    "process": proc_name,
                    "pid": pid,
                    "status": "Listening",
                    "origin": "Local",
                    "exposure": exposure,
                    "openable": True,
                }

        supervisor_port = getattr(getattr(self._manager, "server", None), "port", None)
        if supervisor_port:
            rows[(supervisor_port, "127.0.0.1")] = {
                "port": supervisor_port,
                "host": "127.0.0.1",
                "address": f"http://127.0.0.1:{supervisor_port}",
                "protocol": "HTTP",
                "process": "DeskAI Supervisor",
                "pid": None,
                "status": "Listening",
                "origin": "System",
                "exposure": "loopback",
                "openable": False,
            }

        ports = sorted(rows.values(), key=lambda r: (r["port"], r["host"]))
        return {"status": "ok", "ports": ports, "warnings": warnings}

    def _is_safe_path(self, target_path: str) -> bool:
        """Internal sandbox helper."""
        return is_safe_workspace_path(target_path, self.workspace_root)

    def terminal_open(self, cols: int, rows: int) -> dict:
        """Opens a new interactive host shell in the active workspace."""
        if not self._is_origin_allowed():
            return {"status": "error", "message": "Unauthorized origin"}

        if type(cols) is not int or type(rows) is not int:
            return {"status": "error", "message": "cols and rows must be integers"}

        if not (10 <= cols <= 500) or not (2 <= rows <= 200):
            return {"status": "error", "message": "cols must be in 10..500 and rows in 2..200"}

        if not self.workspace_root:
            return {"status": "error", "message": "Workspace root not set"}

        if is_disallowed_workspace_root(self.workspace_root):
            return {"status": "error", "message": "Disallowed workspace root"}

        if not is_safe_workspace_path(self.workspace_root, self.workspace_root):
            return {"status": "error", "message": "Unsafe workspace path"}

        if not self._terminal_confirmed_in_session:
            ws_name = os.path.basename(self.workspace_root) or self.workspace_root
            confirmed = False
            if self._window and hasattr(self._window, "create_confirmation_dialog"):
                confirmed = bool(
                    self._window.create_confirmation_dialog(
                        "Terminal Authorization",
                        f"Open a host shell in {ws_name}?",
                    )
                )
            if not confirmed:
                return {"status": "error", "message": "User declined terminal authorization"}
            self._terminal_confirmed_in_session = True

        server = getattr(self._manager, "server", None)
        tm = getattr(server, "terminal_manager", None)
        if not tm:
            return {"status": "error", "message": "Terminal manager unavailable"}

        try:
            session = tm.create_session(self.workspace_root, cols=cols, rows=rows)
            return {"status": "ok", "session_id": session.session_id}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def terminal_close(self, session_id: str) -> bool:
        """Closes an active terminal session."""
        if not self._is_origin_allowed():
            return False
        if not isinstance(session_id, str):
            return False
        server = getattr(self._manager, "server", None)
        tm = getattr(server, "terminal_manager", None)
        if not tm:
            return False
        return tm.close_session(session_id)
