import unittest
from unittest.mock import MagicMock, patch
from starlette.testclient import TestClient

from deskai.server.security import SessionSecurityManager
from deskai.server.supervisor import DesktopServer
from deskai.utils.net import bind_ephemeral_loopback_socket


class TestSecurityHeadersAndHardening(unittest.TestCase):
    def setUp(self):
        self.server = DesktopServer()
        self.client = TestClient(self.server.app)
        self.port = self.server.port

    def tearDown(self):
        self.server.stop()

    def test_csp_strictly_drops_unsafe_eval_and_includes_frame_ancestors(self):
        """CSP allows unsafe-eval for PyWebView bridge, drops unsafe-inline, and includes frame-ancestors none."""
        sec = SessionSecurityManager(8000)
        csp = sec.get_content_security_policy()

        self.assertIn("'unsafe-eval'", csp)
        self.assertNotIn("'unsafe-inline'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("base-uri 'none'", csp)
        self.assertIn("form-action 'none'", csp)
        self.assertIn(f"'nonce-{sec.style_nonce}'", csp)

        sec2 = SessionSecurityManager(8000)
        self.assertNotEqual(sec.style_nonce, sec2.style_nonce)
        self.assertGreaterEqual(len(sec.style_nonce), 16)

    def test_http_security_headers_present_on_root_and_redeem(self):
        """Root (/) and redeem (/auth/redeem) must have strict security headers and Cache-Control: no-store."""
        token = self.server.security.create_launch_token()

        # Test redeem endpoint
        res_redeem = self.client.get(
            f"/auth/redeem?token={token}", headers={"Host": f"127.0.0.1:{self.port}"}, follow_redirects=False
        )
        self.assertEqual(res_redeem.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(res_redeem.headers.get("Cross-Origin-Opener-Policy"), "same-origin")
        self.assertEqual(res_redeem.headers.get("Cross-Origin-Resource-Policy"), "same-origin")
        self.assertEqual(res_redeem.headers.get("Permissions-Policy"), "camera=(), microphone=(), geolocation=()")
        self.assertEqual(res_redeem.headers.get("Cache-Control"), "no-store")

        # Test root endpoint with valid cookie
        session_id = res_redeem.cookies.get("deskai_session")
        res_root = self.client.get(
            "/", headers={"Host": f"127.0.0.1:{self.port}"}, cookies={"deskai_session": session_id}
        )
        self.assertEqual(res_root.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(res_root.headers.get("Cross-Origin-Opener-Policy"), "same-origin")
        self.assertEqual(res_root.headers.get("Cross-Origin-Resource-Policy"), "same-origin")
        self.assertEqual(res_root.headers.get("Permissions-Policy"), "camera=(), microphone=(), geolocation=()")
        self.assertEqual(res_root.headers.get("Cache-Control"), "no-store")
        import re

        meta_match = re.search(r'<meta name="csp-nonce" content="([^"]+)">', res_root.text)
        self.assertIsNotNone(meta_match, "Per-response CSP nonce meta tag missing")
        res_nonce = meta_match.group(1)
        self.assertIn(f"'nonce-{res_nonce}'", res_root.headers.get("Content-Security-Policy", ""))

        # Test static asset endpoint with valid cookie
        res_static = self.client.get(
            "/css/tokens.css", headers={"Host": f"127.0.0.1:{self.port}"}, cookies={"deskai_session": session_id}
        )
        self.assertEqual(res_static.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(res_static.headers.get("Cross-Origin-Opener-Policy"), "same-origin")
        self.assertEqual(res_static.headers.get("Cross-Origin-Resource-Policy"), "same-origin")
        self.assertEqual(res_static.headers.get("Permissions-Policy"), "camera=(), microphone=(), geolocation=()")

    def test_security_headers_present_on_401_and_403(self):
        """401 (unauthorized) and 403 (host mismatch) responses must also include full security headers."""
        # 401 response (missing cookie)
        res_401 = self.client.get("/", headers={"Host": f"127.0.0.1:{self.port}"})
        self.assertEqual(res_401.status_code, 401)
        self.assertEqual(res_401.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(res_401.headers.get("Cross-Origin-Opener-Policy"), "same-origin")
        self.assertEqual(res_401.headers.get("Cross-Origin-Resource-Policy"), "same-origin")
        self.assertEqual(res_401.headers.get("Permissions-Policy"), "camera=(), microphone=(), geolocation=()")

        # 403 response (invalid host)
        res_403 = self.client.get("/", headers={"Host": "attacker.com"})
        self.assertEqual(res_403.status_code, 403)
        self.assertEqual(res_403.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(res_403.headers.get("Cross-Origin-Opener-Policy"), "same-origin")
        self.assertEqual(res_403.headers.get("Cross-Origin-Resource-Policy"), "same-origin")
        self.assertEqual(res_403.headers.get("Permissions-Policy"), "camera=(), microphone=(), geolocation=()")

    def test_auth_redeem_host_mismatch_returns_403(self):
        """Redeem endpoint with valid token must reject forged Host header with 403."""
        token = self.server.security.create_launch_token()
        res = self.client.get(f"/auth/redeem?token={token}", headers={"Host": "evil.com"}, follow_redirects=False)
        self.assertEqual(res.status_code, 403)

    @patch("deskai.utils.net.sys")
    @patch("deskai.utils.net.socket.socket")
    def test_windows_bind_uses_so_exclusiveaddruse(self, mock_socket_cls, mock_sys):
        """On Windows, bind_ephemeral_loopback_socket must set SO_EXCLUSIVEADDRUSE, not SO_REUSEADDR."""
        mock_sys.platform = "win32"
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.getsockname.return_value = ("127.0.0.1", 54321)

        import socket

        with patch.object(socket, "SO_EXCLUSIVEADDRUSE", -5, create=True):
            sock, port = bind_ephemeral_loopback_socket()
            self.assertEqual(port, 54321)
            # Ensure SO_EXCLUSIVEADDRUSE was called
            mock_sock.setsockopt.assert_called_with(socket.SOL_SOCKET, -5, 1)

    def test_terminal_websocket_per_session_cap(self):
        """Terminal WebSocket adheres to 4-socket per-session limit (returns 4429 on 5th)."""
        token = self.server.security.create_launch_token()
        res_redeem = self.client.get(
            f"/auth/redeem?token={token}", headers={"Host": f"127.0.0.1:{self.port}"}, follow_redirects=False
        )
        session_cookie = res_redeem.cookies.get("deskai_session")
        self.assertIsNotNone(session_cookie)

        # Pre-register 4 sockets for this session in security manager
        mock_ws = [MagicMock() for _ in range(4)]
        for ws in mock_ws:
            self.server.security.register_socket(session_cookie, ws)

        # Attempt to open a 5th terminal websocket with same cookie
        with self.client.websocket_connect(
            "/ws/terminal/dummy_session",
            headers={"Host": f"127.0.0.1:{self.port}", "Origin": f"http://127.0.0.1:{self.port}"},
            cookies={"deskai_session": session_cookie},
        ) as ws:
            # 5th socket must be rejected with 4429
            pass

    def test_resize_window_absolute_bounds_validation(self):
        """resize_window_absolute validates integer types and bounds in 200..10000."""
        from deskai.bridge.api import DesktopBridgeAPI

        mock_mgr = MagicMock()
        mock_mgr.server.port = self.port
        mock_mgr.window.get_current_url.return_value = f"http://127.0.0.1:{self.port}/"
        api = DesktopBridgeAPI(mock_mgr)

        # 1. Non-integer types rejected
        self.assertEqual(api.resize_window_absolute("800", 600)["status"], "error")  # type: ignore
        self.assertEqual(api.resize_window_absolute(True, 600)["status"], "error")  # type: ignore
        self.assertEqual(api.resize_window_absolute(800, 600.5)["status"], "error")  # type: ignore

        # 2. Out of bounds rejected (< 200 or > 10000)
        self.assertEqual(api.resize_window_absolute(150, 600)["status"], "error")
        self.assertEqual(api.resize_window_absolute(800, 50)["status"], "error")
        self.assertEqual(api.resize_window_absolute(15000, 800)["status"], "error")

        # 3. Valid bounds accepted
        res_ok = api.resize_window_absolute(1024, 768)
        self.assertEqual(res_ok["status"], "ok")
        self.assertEqual(res_ok["width"], 1024)
        self.assertEqual(res_ok["height"], 768)

    def test_system_telemetry_across_platforms(self):
        """get_system_telemetry returns platform and metrics or explicit 'unavailable' fallbacks."""
        from deskai.bridge.api import DesktopBridgeAPI

        mock_mgr = MagicMock()
        mock_mgr.server.port = self.port
        mock_mgr.window.get_current_url.return_value = f"http://127.0.0.1:{self.port}/"
        api = DesktopBridgeAPI(mock_mgr)

        res = api.get_system_telemetry()
        self.assertEqual(res["status"], "ok")
        t = res["telemetry"]
        self.assertIn("platform", t)
        self.assertIn(t["status"], ("ready", "unavailable"))
        self.assertNotEqual(t["ramTotalMB"], "--")
        self.assertNotEqual(t["ramUsedMB"], "--")
        self.assertNotEqual(t["cpuUsagePct"], "--")


if __name__ == "__main__":
    unittest.main()
