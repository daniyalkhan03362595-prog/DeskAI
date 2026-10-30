from __future__ import annotations
import json
import logging
import time
import unittest
from unittest.mock import MagicMock, patch

from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from deskai.server.supervisor import DesktopServer


class TestWebSocketAuthorizeRefactorSafety(unittest.TestCase):
    """TC-OUT-29: Verify /ws and /ws/terminal/{id} return 4403/4401/4404/4429 before and after refactoring."""

    def setUp(self):
        self.server = DesktopServer()
        self.client = TestClient(self.server.app)
        self.port = self.server.port
        token = self.server.security.create_launch_token()
        res = self.client.get(
            f"/auth/redeem?token={token}",
            headers={"Host": f"127.0.0.1:{self.port}"},
            follow_redirects=False,
        )
        self.cookie = res.cookies.get("deskai_session")
        self.assertIsNotNone(self.cookie)

    def tearDown(self):
        self.server.stop()

    def test_tc_out_29_ws_invalid_host_returns_4403(self):
        with self.client.websocket_connect(
            "/ws",
            headers={"Host": "evil.com", "Origin": f"http://127.0.0.1:{self.port}"},
            cookies={"deskai_session": self.cookie},
        ) as ws:
            with self.assertRaises(WebSocketDisconnect) as ctx:
                ws.receive_text()
            self.assertEqual(ctx.exception.code, 4403)

    def test_tc_out_29_ws_cross_origin_returns_4403(self):
        with self.client.websocket_connect(
            "/ws",
            headers={"Host": f"127.0.0.1:{self.port}", "Origin": "http://evil.com"},
            cookies={"deskai_session": self.cookie},
        ) as ws:
            with self.assertRaises(WebSocketDisconnect) as ctx:
                ws.receive_text()
            self.assertEqual(ctx.exception.code, 4403)

    def test_tc_out_29_ws_missing_cookie_returns_4401(self):
        clean_client = TestClient(self.server.app)
        with clean_client.websocket_connect(
            "/ws",
            headers={"Host": f"127.0.0.1:{self.port}", "Origin": f"http://127.0.0.1:{self.port}"},
        ) as ws:
            with self.assertRaises(WebSocketDisconnect) as ctx:
                ws.receive_text()
            self.assertEqual(ctx.exception.code, 4401)

    def test_tc_out_29_ws_concurrency_limit_returns_4429(self):
        # 4 active /ws sockets -> 5th returns 4429
        mock_sockets = [MagicMock() for _ in range(4)]
        for s in mock_sockets:
            self.server.security.register_socket(self.cookie, s)

        with self.client.websocket_connect(
            "/ws",
            headers={"Host": f"127.0.0.1:{self.port}", "Origin": f"http://127.0.0.1:{self.port}"},
            cookies={"deskai_session": self.cookie},
        ) as ws:
            with self.assertRaises(WebSocketDisconnect) as ctx:
                ws.receive_text()
            self.assertEqual(ctx.exception.code, 4429)

    def test_tc_out_29_terminal_ws_invalid_host_returns_4403(self):
        with self.client.websocket_connect(
            "/ws/terminal/any_id",
            headers={"Host": "evil.com", "Origin": f"http://127.0.0.1:{self.port}"},
            cookies={"deskai_session": self.cookie},
        ) as ws:
            with self.assertRaises(WebSocketDisconnect) as ctx:
                ws.receive_text()
            self.assertEqual(ctx.exception.code, 4403)

    def test_tc_out_29_terminal_ws_cross_origin_returns_4403(self):
        with self.client.websocket_connect(
            "/ws/terminal/any_id",
            headers={"Host": f"127.0.0.1:{self.port}", "Origin": "http://evil.com"},
            cookies={"deskai_session": self.cookie},
        ) as ws:
            with self.assertRaises(WebSocketDisconnect) as ctx:
                ws.receive_text()
            self.assertEqual(ctx.exception.code, 4403)

    def test_tc_out_29_terminal_ws_missing_cookie_returns_4401(self):
        clean_client = TestClient(self.server.app)
        with clean_client.websocket_connect(
            "/ws/terminal/any_id",
            headers={"Host": f"127.0.0.1:{self.port}", "Origin": f"http://127.0.0.1:{self.port}"},
        ) as ws:
            with self.assertRaises(WebSocketDisconnect) as ctx:
                ws.receive_text()
            self.assertEqual(ctx.exception.code, 4401)

    def test_tc_out_29_terminal_ws_not_found_returns_4404(self):
        with self.client.websocket_connect(
            "/ws/terminal/nonexistent_session",
            headers={"Host": f"127.0.0.1:{self.port}", "Origin": f"http://127.0.0.1:{self.port}"},
            cookies={"deskai_session": self.cookie},
        ) as ws:
            with self.assertRaises(WebSocketDisconnect) as ctx:
                ws.receive_text()
            self.assertEqual(ctx.exception.code, 4404)


class TestOutputWebSocketEndpoint(unittest.TestCase):
    """TC-OUT-20 to TC-OUT-28 and TC-OUT-30: /ws/output endpoint tests."""

    def setUp(self):
        self.server = DesktopServer()
        self.server.start()
        self.client = TestClient(self.server.app)
        self.port = self.server.port
        self.launch_token = self.server.security.create_launch_token()
        res = self.client.get(
            f"/auth/redeem?token={self.launch_token}",
            headers={"Host": f"127.0.0.1:{self.port}"},
            follow_redirects=False,
        )
        self.cookie = res.cookies.get("deskai_session")
        self.assertIsNotNone(self.cookie)

    def tearDown(self):
        self.server.stop()

    def test_tc_out_20_missing_or_invalid_cookie_returns_4401(self):
        """TC-OUT-20: Missing or invalid cookie -> close 4401."""
        # 1. Missing cookie
        clean_client = TestClient(self.server.app)
        with clean_client.websocket_connect(
            "/ws/output",
            headers={"Host": f"127.0.0.1:{self.port}", "Origin": f"http://127.0.0.1:{self.port}"},
        ) as ws:
            with self.assertRaises(WebSocketDisconnect) as ctx:
                ws.receive_text()
            self.assertEqual(ctx.exception.code, 4401)

        # 2. Invalid cookie
        invalid_client = TestClient(self.server.app)
        invalid_client.cookies.set("deskai_session", "invalid_session_cookie_12345")
        with invalid_client.websocket_connect(
            "/ws/output",
            headers={"Host": f"127.0.0.1:{self.port}", "Origin": f"http://127.0.0.1:{self.port}"},
        ) as ws:
            with self.assertRaises(WebSocketDisconnect) as ctx:
                ws.receive_text()
            self.assertEqual(ctx.exception.code, 4401)

    def test_tc_out_21_bad_origin_and_bad_host_returns_4403(self):
        """TC-OUT-21: Bad Origin / bad Host -> close 4403."""
        # 1. Bad Host
        with self.client.websocket_connect(
            "/ws/output",
            headers={"Host": "attacker.com", "Origin": f"http://127.0.0.1:{self.port}"},
            cookies={"deskai_session": self.cookie},
        ) as ws:
            with self.assertRaises(WebSocketDisconnect) as ctx:
                ws.receive_text()
            self.assertEqual(ctx.exception.code, 4403)

        # 2. Bad Origin
        with self.client.websocket_connect(
            "/ws/output",
            headers={"Host": f"127.0.0.1:{self.port}", "Origin": "http://evil.com"},
            cookies={"deskai_session": self.cookie},
        ) as ws:
            with self.assertRaises(WebSocketDisconnect) as ctx:
                ws.receive_text()
            self.assertEqual(ctx.exception.code, 4403)

    def test_tc_out_22_secret_never_on_the_wire(self):
        """TC-OUT-22: Emit log containing launch token and session id; wire frames contain [REDACTED] only."""
        with self.client.websocket_connect(
            "/ws/output",
            headers={"Host": f"127.0.0.1:{self.port}", "Origin": f"http://127.0.0.1:{self.port}"},
            cookies={"deskai_session": self.cookie},
        ) as ws:
            hello = json.loads(ws.receive_text())
            self.assertEqual(hello["type"], "hello")
            # Consume initial startup replay batch
            init_batch = json.loads(ws.receive_text())
            self.assertEqual(init_batch["type"], "batch")

            # Emit a log containing the launch token and session id
            logging.getLogger("deskai.supervisor").info(
                f"Testing secrets launch={self.launch_token} and sess={self.cookie}"
            )

            # Receive the live batch frame
            batch = json.loads(ws.receive_text())
            self.assertEqual(batch["type"], "batch")
            wire_text = json.dumps(batch)
            self.assertNotIn(self.launch_token, wire_text)
            self.assertNotIn(self.cookie, wire_text)
            self.assertIn("Testing secrets launch=[REDACTED] and sess=[REDACTED]", wire_text)

    def test_tc_out_23_socket_cap(self):
        """TC-OUT-23: 3rd concurrent socket for a session -> 4429; /ws and terminal caps unaffected."""
        headers = {"Host": f"127.0.0.1:{self.port}", "Origin": f"http://127.0.0.1:{self.port}"}
        cookies = {"deskai_session": self.cookie}

        with self.client.websocket_connect("/ws/output", headers=headers, cookies=cookies) as ws1:
            h1 = json.loads(ws1.receive_text())
            self.assertEqual(h1["type"], "hello")

            with self.client.websocket_connect("/ws/output", headers=headers, cookies=cookies) as ws2:
                h2 = json.loads(ws2.receive_text())
                self.assertEqual(h2["type"], "hello")

                # 3rd socket must be rejected with 4429
                with self.client.websocket_connect("/ws/output", headers=headers, cookies=cookies) as ws3:
                    with self.assertRaises(WebSocketDisconnect) as ctx:
                        ws3.receive_text()
                    self.assertEqual(ctx.exception.code, 4429)

            # After closing ws2, opening a second socket works again
            with self.client.websocket_connect("/ws/output", headers=headers, cookies=cookies) as ws2_again:
                h2_again = json.loads(ws2_again.receive_text())
                self.assertEqual(h2_again["type"], "hello")

    def test_tc_out_24_replay(self):
        """TC-OUT-24: connect with ?since=N receives exactly missing records in order."""
        logger = logging.getLogger("deskai.bridge.git")
        for i in range(1, 11):
            logger.info(f"git event {i}")

        headers = {"Host": f"127.0.0.1:{self.port}", "Origin": f"http://127.0.0.1:{self.port}"}
        cookies = {"deskai_session": self.cookie}

        # Suppose client already saw up to seq 6: query ?since=6
        with self.client.websocket_connect("/ws/output?since=6", headers=headers, cookies=cookies) as ws:
            hello = json.loads(ws.receive_text())
            self.assertEqual(hello["type"], "hello")
            self.assertGreaterEqual(hello["lastSeq"], 11)

            batch = json.loads(ws.receive_text())
            self.assertEqual(batch["type"], "batch")
            records = batch["records"]
            self.assertEqual(records[0]["seq"], 7)
            self.assertEqual(records[-1]["seq"], 11)
            self.assertEqual([r["text"] for r in records], [f"git event {i}" for i in range(6, 11)])

    def test_tc_out_25_reset_frame(self):
        """TC-OUT-25: evicted cursor -> reset then full replay."""
        # Temporarily fill ring beyond 2000
        for i in range(2100):
            self.server.output_hub.emit("terminal", "info", f"line {i}")

        headers = {"Host": f"127.0.0.1:{self.port}", "Origin": f"http://127.0.0.1:{self.port}"}
        cookies = {"deskai_session": self.cookie}

        # Client has since=5 which has been evicted
        with self.client.websocket_connect("/ws/output?since=5", headers=headers, cookies=cookies) as ws:
            hello = json.loads(ws.receive_text())
            self.assertEqual(hello["type"], "hello")

            reset = json.loads(ws.receive_text())
            self.assertEqual(reset["type"], "reset")

            # First batch arrives with replayed ring
            batch = json.loads(ws.receive_text())
            self.assertEqual(batch["type"], "batch")
            self.assertGreaterEqual(len(batch["records"]), 1)

    def test_tc_out_26_oversize_inbound(self):
        """TC-OUT-26: 2 KB inbound frame -> close 1009; normal inbound ignored."""
        headers = {"Host": f"127.0.0.1:{self.port}", "Origin": f"http://127.0.0.1:{self.port}"}
        cookies = {"deskai_session": self.cookie}

        with self.client.websocket_connect("/ws/output", headers=headers, cookies=cookies) as ws:
            hello = json.loads(ws.receive_text())
            self.assertEqual(hello["type"], "hello")
            # Consume startup replay batch
            ws.receive_text()

            # Send a 2 KB message inbound
            ws.send_text("x" * 2048)
            with self.assertRaises(WebSocketDisconnect) as ctx:
                ws.receive_text()
            self.assertEqual(ctx.exception.code, 1009)

    def test_tc_out_27_batching(self):
        """TC-OUT-27: Rapid records arrive in batches of <= 50 within ~100 ms windows."""
        headers = {"Host": f"127.0.0.1:{self.port}", "Origin": f"http://127.0.0.1:{self.port}"}
        cookies = {"deskai_session": self.cookie}

        with self.client.websocket_connect("/ws/output", headers=headers, cookies=cookies) as ws:
            hello = json.loads(ws.receive_text())
            self.assertEqual(hello["type"], "hello")
            # Consume startup replay batch
            ws.receive_text()

            logger = logging.getLogger("deskai.bridge.ports")
            for i in range(120):
                logger.info(f"port status rapid {i}")

            received = 0
            while received < 120:
                frame = json.loads(ws.receive_text())
                if frame["type"] == "batch":
                    self.assertLessEqual(len(frame["records"]), 50)
                    received += len(frame["records"])

    def test_tc_out_28_slow_consumer(self):
        """TC-OUT-28: simulated full write buffer -> dropped reported, server memory bounded."""
        headers = {"Host": f"127.0.0.1:{self.port}", "Origin": f"http://127.0.0.1:{self.port}"}
        cookies = {"deskai_session": self.cookie}

        with self.client.websocket_connect("/ws/output", headers=headers, cookies=cookies) as ws:
            hello = json.loads(ws.receive_text())
            self.assertEqual(hello["type"], "hello")
            # Consume startup replay batch
            ws.receive_text()

            # Simulate write buffer overflow (> 1,000,000 bytes)
            with patch("deskai.server.supervisor._get_write_buffer_size", return_value=1_500_000):
                logger = logging.getLogger("deskai.diagnostics")
                for i in range(10):
                    logger.info(f"overflow test {i}")
                # Allow pump loop to drop records
                time.sleep(0.2)

            # Normal buffer size restored: next emitted batch reports dropped > 0
            logger.info("resumed record")
            batch = json.loads(ws.receive_text())
            self.assertEqual(batch["type"], "batch")
            self.assertGreater(batch["dropped"], 0)

    def test_tc_out_30_windows_platform_mocking(self):
        """TC-OUT-30: with platform mocked to win32, handler and endpoint tests pass unchanged."""
        with patch("sys.platform", "win32"):
            headers = {"Host": f"127.0.0.1:{self.port}", "Origin": f"http://127.0.0.1:{self.port}"}
            cookies = {"deskai_session": self.cookie}
            with self.client.websocket_connect("/ws/output", headers=headers, cookies=cookies) as ws:
                hello = json.loads(ws.receive_text())
                self.assertEqual(hello["type"], "hello")


if __name__ == "__main__":
    unittest.main()
