import asyncio
import json
import time
import unittest
import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from deskai.server.supervisor import DesktopServer


class TestTask5WebSocketAbuseLimits(unittest.TestCase):
    def setUp(self):
        self.server = DesktopServer()
        self.server.start()

        with httpx.Client(follow_redirects=False) as http:
            res = http.get(
                f"http://127.0.0.1:{self.server.port}/auth/redeem?token={self.server.launch_token}",
                headers={"Host": f"127.0.0.1:{self.server.port}"},
            )
            cookie_val = res.cookies.get("deskai_session")

        self.cookie = f"deskai_session={cookie_val}"
        self.raw_session_id = cookie_val
        self.ws_headers = {
            "Host": f"127.0.0.1:{self.server.port}",
            "Origin": f"http://127.0.0.1:{self.server.port}",
            "Cookie": self.cookie,
        }

    def tearDown(self):
        self.server.stop()

    def test_binary_frame_rejected_with_1003_and_server_stays_alive(self):
        """Binary frame must be rejected with 1003, not crash the server handler."""

        async def run():
            ws_url = f"ws://127.0.0.1:{self.server.port}/ws"
            async with websockets.connect(ws_url, additional_headers=self.ws_headers) as ws:
                # Send raw bytes frame
                await ws.send(b"\x00\x01\x02\x03\xff\xfe")
                try:
                    await asyncio.wait_for(ws.recv(), timeout=2.0)
                    self.fail("Binary frame should trigger connection close 1003")
                except ConnectionClosed as e:
                    close_code = getattr(e, "code", getattr(getattr(e, "rcvd", None), "code", None))
                    self.assertEqual(close_code, 1003)

            # Server thread must remain healthy and alive after handling binary frame
            self.assertTrue(self.server.server_thread.is_alive(), "Server thread crashed after binary frame")

            # Subsequent connection must succeed cleanly
            async with websockets.connect(ws_url, additional_headers=self.ws_headers) as ws2:
                await ws2.send(json.dumps({"type": "client.resync"}))
                msg = await ws2.recv()
                self.assertIn("server.snapshot", msg)

        asyncio.run(run())

    def test_multibyte_utf8_wire_size_enforced(self):
        """30,000 non-ASCII chars (~90 KB UTF-8) must be rejected even if char len < 65536."""

        async def run():
            ws_url = f"ws://127.0.0.1:{self.server.port}/ws"
            async with websockets.connect(ws_url, additional_headers=self.ws_headers) as ws:
                # '€' is 3 bytes in UTF-8. 30,000 chars = 90,000 bytes (> 64 KB cap)
                payload = json.dumps({"type": "test", "data": "€" * 30000}, ensure_ascii=False)
                self.assertLess(len(payload), 65536, "Payload char length must be under 65536")
                self.assertGreater(len(payload.encode("utf-8")), 65536, "Wire bytes must be > 64 KB")

                try:
                    await ws.send(payload)
                    reply = await ws.recv()
                    data = json.loads(reply)
                    self.assertEqual(data.get("type"), "error")
                    self.assertEqual(data.get("code"), "ERR_PAYLOAD_TOO_LARGE")
                except ConnectionClosed as e:
                    # uvicorn ws_max_size rejects oversized frame at wire protocol level with 1009
                    close_code = getattr(e, "code", getattr(getattr(e, "rcvd", None), "code", None))
                    self.assertEqual(close_code, 1009)

        asyncio.run(run())

    def test_max_concurrent_sockets_per_session(self):
        """At most 4 concurrent sockets per session; 5th must be closed with 4429."""

        async def run():
            ws_url = f"ws://127.0.0.1:{self.server.port}/ws"
            sockets = []
            try:
                for i in range(4):
                    s = await websockets.connect(ws_url, additional_headers=self.ws_headers)
                    sockets.append(s)

                # 5th connection must be rejected with 4429
                try:
                    s5 = await websockets.connect(ws_url, additional_headers=self.ws_headers)
                    try:
                        await asyncio.wait_for(s5.recv(), timeout=2.0)
                        self.fail("5th socket should have been closed with 4429")
                    except ConnectionClosed as e:
                        close_code = getattr(e, "code", getattr(getattr(e, "rcvd", None), "code", None))
                        self.assertEqual(close_code, 4429)
                except ConnectionClosed as e:
                    close_code = getattr(e, "code", getattr(getattr(e, "rcvd", None), "code", None))
                    self.assertEqual(close_code, 4429)
            finally:
                for s in sockets:
                    await s.close()

        asyncio.run(run())

    def test_token_bucket_rate_limiting_abuse(self):
        """Rapid message flooding beyond 30 msgs/sec triggers close 4429."""

        async def run():
            ws_url = f"ws://127.0.0.1:{self.server.port}/ws"
            async with websockets.connect(ws_url, additional_headers=self.ws_headers) as ws:
                closed = False
                try:
                    for _ in range(50):
                        await ws.send(json.dumps({"type": "test"}))
                    # Drain responses until closed
                    for _ in range(50):
                        await ws.recv()
                except ConnectionClosed as e:
                    closed = True
                    close_code = getattr(e, "code", getattr(getattr(e, "rcvd", None), "code", None))
                    self.assertEqual(close_code, 4429)
                self.assertTrue(closed, "Expected rate limit abuse to close socket with 4429")

        asyncio.run(run())

    def test_session_ttl_and_clean_teardown(self):
        """Session expires after TTL (12h) and stop() joins thread and clears sessions."""
        # 1. Active session is valid initially
        self.assertTrue(self.server.security.is_valid_session(self.raw_session_id))

        # 2. Backdate creation by 13 hours
        self.server.security.active_sessions[self.raw_session_id] = time.time() - (13 * 3600)
        self.assertFalse(self.server.security.is_valid_session(self.raw_session_id))

        # 3. Stop server cleanly
        self.server.stop()
        self.assertFalse(self.server.server_thread.is_alive(), "Server thread did not terminate")
        self.assertIsNone(self.server.listen_socket, "Listen socket was not reset to None")
        self.assertEqual(len(self.server.security.active_sessions), 0, "Sessions were not cleared on stop")


if __name__ == "__main__":
    unittest.main()
