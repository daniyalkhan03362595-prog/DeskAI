"""
Runtime Integration & End-to-End Server Verification Suite for DeskAI Layer 1
Directly probes the live DesktopServer instance over loopback HTTP & WebSocket.
"""
import asyncio
import json
import time
import unittest
import urllib.request
import urllib.error
from urllib.parse import urlparse
import websockets
from websockets.exceptions import ConnectionClosed

from deskai.server.supervisor import DesktopServer


class TestDeskAIRuntimeServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = DesktopServer()
        cls.server.start()
        # Give server a brief moment to start thread
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_single_use_token_redemption_and_cookie_issuance(self):
        """Tests that redeeming launch token sets session cookie, redirects 303, and burns token."""
        port = self.server.port
        token = self.server.launch_token
        self.assertIsNotNone(token)

        redeem_url = f"http://127.0.0.1:{port}/auth/redeem?token={token}"

        # 1. First redemption attempt
        req = urllib.request.Request(redeem_url, headers={"Host": f"127.0.0.1:{port}"})
        class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        opener = urllib.request.build_opener(NoRedirectHandler)
        try:
            resp = opener.open(req)
            status = resp.status
            set_cookie = resp.headers.get("Set-Cookie", "")
        except urllib.error.HTTPError as e:
            status = e.code
            set_cookie = e.headers.get("Set-Cookie", "")

        self.assertEqual(status, 303)
        self.assertIn("deskai_session=", set_cookie)
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=strict", set_cookie)

        # Extract session cookie
        cookie_val = set_cookie.split("deskai_session=")[1].split(";")[0]

        # 2. Second redemption attempt with the same burned token must return 403 Forbidden
        req2 = urllib.request.Request(redeem_url, headers={"Host": f"127.0.0.1:{port}"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            opener.open(req2)
        self.assertEqual(ctx.exception.code, 403)

        # 3. Request without cookie returns 401 Unauthorized
        root_req = urllib.request.Request(f"http://127.0.0.1:{port}/", headers={"Host": f"127.0.0.1:{port}"})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            opener.open(root_req)
        self.assertEqual(ctx.exception.code, 401)

        # 4. Request with valid session cookie returns 200 OK HTML
        auth_root_req = urllib.request.Request(
            f"http://127.0.0.1:{port}/",
            headers={
                "Host": f"127.0.0.1:{port}",
                "Cookie": f"deskai_session={cookie_val}"
            }
        )
        auth_resp = urllib.request.urlopen(auth_root_req)
        self.assertEqual(auth_resp.status, 200)
        body = auth_resp.read().decode("utf-8")
        self.assertIn("<!DOCTYPE html>", body)
        self.assertIn("DeskAI Studio", body)

        # 5. Root static assets (css/tokens.css, js/app.js, vendor/purify.min.js) all return 200 OK
        for asset_path in ["/css/tokens.css", "/css/layout.css", "/js/app.js", "/vendor/purify.min.js"]:
            asset_req = urllib.request.Request(
                f"http://127.0.0.1:{port}{asset_path}",
                headers={
                    "Host": f"127.0.0.1:{port}",
                    "Cookie": f"deskai_session={cookie_val}"
                }
            )
            asset_resp = urllib.request.urlopen(asset_req)
            self.assertEqual(asset_resp.status, 200, f"Asset {asset_path} failed to return 200")

    def test_live_websocket_security_and_frame_handling(self):
        """Tests live WebSocket handshake, codes 4401/4403, and JSON frame exchange."""
        port = self.server.port
        test_session = "valid_test_session_id_456"
        self.server.security.active_sessions.add(test_session)
        ws_url = f"ws://127.0.0.1:{port}/ws"

        async def run_ws_tests():
            # A. Evil Origin rejected with 4403
            try:
                async with websockets.connect(
                    ws_url,
                    additional_headers={
                        "Host": f"127.0.0.1:{port}",
                        "Origin": "http://evil-site.com",
                        "Cookie": f"deskai_session={test_session}"
                    }
                ) as ws:
                    await ws.recv()
            except ConnectionClosed as e:
                self.assertEqual(e.rcvd.code, 4403)

            # B. Null Origin rejected with 4403
            try:
                async with websockets.connect(
                    ws_url,
                    additional_headers={
                        "Host": f"127.0.0.1:{port}",
                        "Origin": "null",
                        "Cookie": f"deskai_session={test_session}"
                    }
                ) as ws:
                    await ws.recv()
            except ConnectionClosed as e:
                self.assertEqual(e.rcvd.code, 4403)

            # C. Missing Cookie rejected with 4401
            try:
                async with websockets.connect(
                    ws_url,
                    additional_headers={
                        "Host": f"127.0.0.1:{port}",
                        "Origin": f"http://127.0.0.1:{port}"
                    }
                ) as ws:
                    await ws.recv()
            except ConnectionClosed as e:
                self.assertEqual(e.rcvd.code, 4401)

            # D. Legitimate connection: All headers matched -> Success!
            async with websockets.connect(
                ws_url,
                additional_headers={
                    "Host": f"127.0.0.1:{port}",
                    "Origin": f"http://127.0.0.1:{port}",
                    "Cookie": f"deskai_session={test_session}"
                }
            ) as ws:
                # Send resync frame
                await ws.send(json.dumps({"type": "client.resync", "seq": 1}))
                reply = await ws.recv()
                data = json.loads(reply)
                self.assertEqual(data.get("type"), "server.snapshot")

        asyncio.run(run_ws_tests())


if __name__ == "__main__":
    unittest.main()
