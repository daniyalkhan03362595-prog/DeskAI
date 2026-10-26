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
        token = self.server.security.create_launch_token()
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
            f"http://127.0.0.1:{port}/", headers={"Host": f"127.0.0.1:{port}", "Cookie": f"deskai_session={cookie_val}"}
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
                headers={"Host": f"127.0.0.1:{port}", "Cookie": f"deskai_session={cookie_val}"},
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
                        "Cookie": f"deskai_session={test_session}",
                    },
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
                        "Cookie": f"deskai_session={test_session}",
                    },
                ) as ws:
                    await ws.recv()
            except ConnectionClosed as e:
                self.assertEqual(e.rcvd.code, 4403)

            # C. Missing Cookie rejected with 4401
            try:
                async with websockets.connect(
                    ws_url, additional_headers={"Host": f"127.0.0.1:{port}", "Origin": f"http://127.0.0.1:{port}"}
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
                    "Cookie": f"deskai_session={test_session}",
                },
            ) as ws:
                # Send resync frame
                await ws.send(json.dumps({"type": "client.resync", "seq": 1}))
                reply = await ws.recv()
                data = json.loads(reply)
                self.assertEqual(data.get("type"), "server.snapshot")

                # E. Malformed JSON frame handling
                await ws.send("not-valid-json{{{")
                err_reply = await ws.recv()
                err_data = json.loads(err_reply)
                self.assertEqual(err_data.get("code"), "ERR_MALFORMED_JSON")

                # F. Non-dict frame (JSON array) handling
                await ws.send(json.dumps(["item1", "item2"]))
                err_arr = await ws.recv()
                err_arr_data = json.loads(err_arr)
                self.assertEqual(err_arr_data.get("code"), "ERR_INVALID_FRAME")

                # G. Non-string type handling
                await ws.send(json.dumps({"type": 12345}))
                err_type = await ws.recv()
                err_type_data = json.loads(err_type)
                self.assertEqual(err_type_data.get("code"), "ERR_INVALID_FRAME")

                # H. Oversized payload handling (> 64KB: rejected by uvicorn ws_max_size with 1009)
                oversized_payload = json.dumps({"type": "test", "data": "X" * 70000})
                try:
                    await ws.send(oversized_payload)
                    err_size = await ws.recv()
                    err_size_data = json.loads(err_size)
                    self.assertEqual(err_size_data.get("code"), "ERR_PAYLOAD_TOO_LARGE")
                except ConnectionClosed as e:
                    close_code = getattr(e, "code", getattr(getattr(e, "rcvd", None), "code", None))
                    self.assertEqual(close_code, 1009)

            # I. UEC approve & reject ACK handling (guarded by state machine on fresh connection)
            async with websockets.connect(
                ws_url,
                additional_headers={
                    "Host": f"127.0.0.1:{self.server.port}",
                    "Origin": f"http://127.0.0.1:{self.server.port}",
                    "Cookie": f"deskai_session={test_session}",
                },
            ) as uec_ws:
                await uec_ws.send(json.dumps({"type": "uec.transition", "payload": {"from": "IDLE", "to": "PLANNING"}}))
                await uec_ws.recv()
                await uec_ws.send(
                    json.dumps({"type": "uec.transition", "payload": {"from": "PLANNING", "to": "EXECUTING"}})
                )
                await uec_ws.recv()
                await uec_ws.send(
                    json.dumps({"type": "uec.transition", "payload": {"from": "EXECUTING", "to": "REVIEW_DIFF"}})
                )
                await uec_ws.recv()

                await uec_ws.send(json.dumps({"type": "uec.approve", "payload": {}}))
                ack_approve = await uec_ws.recv()
                self.assertEqual(json.loads(ack_approve).get("payload", {}).get("state"), "SUCCESS")

                # Reset to IDLE -> step to REVIEW_DIFF -> test reject
                await uec_ws.send(json.dumps({"type": "uec.transition", "payload": {"from": "SUCCESS", "to": "IDLE"}}))
                await uec_ws.recv()
                await uec_ws.send(json.dumps({"type": "uec.transition", "payload": {"from": "IDLE", "to": "PLANNING"}}))
                await uec_ws.recv()
                await uec_ws.send(
                    json.dumps({"type": "uec.transition", "payload": {"from": "PLANNING", "to": "EXECUTING"}})
                )
                await uec_ws.recv()
                await uec_ws.send(
                    json.dumps({"type": "uec.transition", "payload": {"from": "EXECUTING", "to": "REVIEW_DIFF"}})
                )
                await uec_ws.recv()

                await uec_ws.send(json.dumps({"type": "uec.reject", "payload": {}}))
                ack_reject = await uec_ws.recv()
                self.assertEqual(json.loads(ack_reject).get("payload", {}).get("state"), "ROLLBACK")

        asyncio.run(run_ws_tests())

    def test_starlette_testclient_all_static_assets_and_no_docs_leak(self):
        """Uses Starlette/FastAPI TestClient to assert all assets resolve 200 OK and docs are 404."""
        from fastapi.testclient import TestClient

        client = TestClient(self.server.app)
        host_hdr = {"Host": f"127.0.0.1:{self.server.port}"}

        # 1. Unauthenticated requests to /docs and /openapi.json are rejected with 401
        self.assertEqual(client.get("/docs", headers=host_hdr).status_code, 401)
        self.assertEqual(client.get("/openapi.json", headers=host_hdr).status_code, 401)

        # 1b. Evil Host header rejected with 403 Forbidden
        evil_host_hdr = {"Host": "evil-attacker.com"}
        self.assertEqual(client.get("/css/tokens.css", headers=evil_host_hdr).status_code, 403)

        # 2. Authenticated session setup
        session_id = "testclient_session_789"
        self.server.security.active_sessions.add(session_id)
        client.cookies.set("deskai_session", session_id)

        # 3. Authenticated requests to disabled docs endpoints return 404 (No schema leakage)
        self.assertEqual(client.get("/docs", headers=host_hdr).status_code, 404)
        self.assertEqual(client.get("/openapi.json", headers=host_hdr).status_code, 404)
        self.assertEqual(client.get("/redoc", headers=host_hdr).status_code, 404)

        # 4. Assert all 16 static assets resolve 200 OK
        assets = [
            "/css/tokens.css",
            "/css/layout.css",
            "/css/components.css",
            "/css/diff.css",
            "/css/animations.css",
            "/vendor/purify.min.js",
            "/vendor/marked.min.js",
            "/vendor/codemirror.bundle.js",
            "/js/app.js",
            "/js/bridge.js",
            "/js/editor.js",
            "/js/events.js",
            "/js/state.js",
            "/js/stream.js",
            "/js/uec.js",
            "/js/ws.js",
        ]
        for asset in assets:
            res = client.get(asset, headers=host_hdr)
            self.assertEqual(res.status_code, 200, f"Asset {asset} failed with {res.status_code}")

    def test_playwright_real_browser_smoke_test(self):
        """
        Launches real headless Chromium via Playwright, navigates to the redeemed URL,
        asserts zero console errors, app.js executed, CSS applied, and WebSocket connected.
        """
        from playwright.sync_api import sync_playwright

        port = self.server.port
        token = self.server.security.create_launch_token()
        redeem_url = f"http://127.0.0.1:{port}/auth/redeem?token={token}"

        console_errors = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda exc: console_errors.append(str(exc)))

            # Navigate to launch token redemption URL
            page.goto(redeem_url, wait_until="networkidle")

            # 1. Assert URL was cleanly redirected to root /
            self.assertEqual(page.url.rstrip("/"), f"http://127.0.0.1:{port}")

            # 2. Assert Title & UI elements are present in DOM
            self.assertEqual(page.title(), "DeskAI Studio")
            self.assertTrue(page.locator("#appRoot").is_visible())
            self.assertTrue(page.locator("#editorStage").is_visible())
            self.assertEqual(page.locator("#windowResizeHandles .resize-handle").count(), 8)

            # 3. Assert CSS applied
            bg_color = page.evaluate("getComputedStyle(document.body).backgroundColor")
            self.assertTrue(bg_color is not None and len(bg_color) > 0)

            # 4. Wait for WebSocket connection to establish (readyState 1 = OPEN)
            page.wait_for_function(
                "() => window.wsClient && window.wsClient.socket && window.wsClient.socket.readyState === 1",
                timeout=5000,
            )
            ws_state = page.evaluate("() => window.wsClient.socket.readyState")
            self.assertEqual(ws_state, 1)

            # 5. Assert zero console errors
            critical_errors = [e for e in console_errors if "favicon.ico" not in e]
            self.assertEqual(critical_errors, [], f"Console errors detected: {critical_errors}")

            browser.close()

    def test_bridge_resize_window_edge_validation(self):
        """Tests that DesktopBridgeAPI edge mapping handles valid/invalid values safely."""
        from deskai.bridge.window import WindowManager

        wm = WindowManager()
        # Non-initialized native window or invalid edge returns False safely
        self.assertFalse(wm.api.resize_window("invalid_edge_direction"))
        self.assertFalse(wm.api.resize_window("top"))


if __name__ == "__main__":
    unittest.main()
