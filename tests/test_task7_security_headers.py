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


if __name__ == "__main__":
    unittest.main()
