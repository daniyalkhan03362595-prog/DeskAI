"""
Network Ports & URL Bridge Module.
Handles loopback port probing, listening port enumeration, and safe external URL dispatch.
"""

import ipaddress
import logging
import socket
from urllib.parse import urlsplit
import webbrowser

from deskai.bridge.base import BaseBridgeModule

logger = logging.getLogger(__name__)

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
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    host = "127.0.0.1" if addr.version == 4 else "[::1]"
    if addr.is_loopback:
        return host, "loopback"
    if addr.is_unspecified:
        return host, "all-interfaces"
    return None


class PortsBridge(BaseBridgeModule):
    """Bridge methods for local network port diagnostics and URL launching."""

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
        logger.info("Opening local service in browser: http://%s:%s", host, port)
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
        logger.debug("Ports scanned: %d active listener(s) found", len(ports))
        return {"status": "ok", "ports": ports, "warnings": warnings}
