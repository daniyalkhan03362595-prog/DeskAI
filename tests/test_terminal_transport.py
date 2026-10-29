"""
Behavioral & Security Tests for Dedicated Terminal WebSocket Transport (Phase 2).
Validates /ws/terminal/{session_id} for:
- Origin enforcement (rejects off-origin with 4403)
- Session cookie enforcement (rejects unauthenticated with 4401)
- Unknown session ID (rejects with 4404)
- Malformed control frames and oversized frame rejection
- Multi-MB output throughput without triggering 4429 message rate limit
- Reconnect replaying the server-side replay buffer
- Process exit delivering JSON exit frame {"type":"exit","code":N}
"""

import asyncio
import json
import os
import sys
import tempfile
import time
import unittest

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from deskai.server.supervisor import DesktopServer


class TestTerminalTransport(unittest.TestCase):
    def setUp(self):
        self.server = DesktopServer()
        self.server.start()

        # Create a safe temporary workspace directory
        self.temp_workspace = tempfile.mkdtemp(prefix="deskai_term_test_")

        # Authenticate session
        with httpx.Client(follow_redirects=False) as http:
            res = http.get(
                f"http://127.0.0.1:{self.server.port}/auth/redeem?token={self.server.launch_token}",
                headers={"Host": f"127.0.0.1:{self.server.port}"},
            )
            cookie_val = res.cookies.get("deskai_session")

        self.cookie = f"deskai_session={cookie_val}"
        self.ws_headers = {
            "Host": f"127.0.0.1:{self.server.port}",
            "Origin": f"http://127.0.0.1:{self.server.port}",
            "Cookie": self.cookie,
        }

    def tearDown(self):
        self.server.stop()
        if os.path.exists(self.temp_workspace):
            try:
                os.rmdir(self.temp_workspace)
            except OSError:
                pass

    def test_wrong_origin_rejected_with_4403(self):
        """Cross-origin WebSocket connection is rejected with 4403."""

        async def run():
            session = self.server.terminal_manager.create_session(self.temp_workspace)
            ws_url = f"ws://127.0.0.1:{self.server.port}/ws/terminal/{session.session_id}"

            bad_headers = dict(self.ws_headers)
            bad_headers["Origin"] = "http://attacker.com"

            try:
                async with websockets.connect(ws_url, additional_headers=bad_headers) as ws:
                    await ws.recv()
                    self.fail("Should have closed with 4403")
            except ConnectionClosed as e:
                code = getattr(e, "code", getattr(getattr(e, "rcvd", None), "code", None))
                self.assertEqual(code, 4403)

        asyncio.run(run())

    def test_missing_cookie_rejected_with_4401(self):
        """Unauthenticated WebSocket connection is rejected with 4401."""

        async def run():
            session = self.server.terminal_manager.create_session(self.temp_workspace)
            ws_url = f"ws://127.0.0.1:{self.server.port}/ws/terminal/{session.session_id}"

            no_cookie_headers = {
                "Host": f"127.0.0.1:{self.server.port}",
                "Origin": f"http://127.0.0.1:{self.server.port}",
            }

            try:
                async with websockets.connect(ws_url, additional_headers=no_cookie_headers) as ws:
                    await ws.recv()
                    self.fail("Should have closed with 4401")
            except ConnectionClosed as e:
                code = getattr(e, "code", getattr(getattr(e, "rcvd", None), "code", None))
                self.assertEqual(code, 4401)

        asyncio.run(run())

    def test_unknown_session_id_rejected_with_4404(self):
        """Connecting to non-existent session ID is rejected with 4404."""

        async def run():
            ws_url = f"ws://127.0.0.1:{self.server.port}/ws/terminal/non_existent_session_id"
            try:
                async with websockets.connect(ws_url, additional_headers=self.ws_headers) as ws:
                    await ws.recv()
                    self.fail("Should have closed with 4404")
            except ConnectionClosed as e:
                code = getattr(e, "code", getattr(getattr(e, "rcvd", None), "code", None))
                self.assertEqual(code, 4404)

        asyncio.run(run())

    def test_malformed_control_frames_rejected_with_error(self):
        """Malformed JSON or invalid control payloads receive error frames without crashing."""

        async def run():
            session = self.server.terminal_manager.create_session(self.temp_workspace)
            ws_url = f"ws://127.0.0.1:{self.server.port}/ws/terminal/{session.session_id}"

            async with websockets.connect(ws_url, additional_headers=self.ws_headers) as ws:
                # 1. Non-JSON string
                await ws.send("NOT_JSON")
                resp1 = await ws.recv()
                data1 = json.loads(resp1) if isinstance(resp1, str) else {}
                self.assertEqual(data1.get("type"), "error")
                self.assertEqual(data1.get("code"), "ERR_MALFORMED_JSON")

                # 2. Invalid control type
                await ws.send(json.dumps({"type": "unknown_action"}))
                resp2 = await ws.recv()
                data2 = json.loads(resp2) if isinstance(resp2, str) else {}
                self.assertEqual(data2.get("type"), "error")
                self.assertEqual(data2.get("code"), "ERR_INVALID_CONTROL_FRAME")

                # 3. Invalid resize types (bool or out-of-range)
                await ws.send(json.dumps({"type": "resize", "cols": True, "rows": 24}))
                resp3 = await ws.recv()
                data3 = json.loads(resp3) if isinstance(resp3, str) else {}
                self.assertEqual(data3.get("type"), "error")
                self.assertEqual(data3.get("code"), "ERR_INVALID_CONTROL_FRAME")

        asyncio.run(run())

    @unittest.skipIf(sys.platform == "win32", "POSIX PTY throughput test")
    def test_multi_mb_output_does_not_trigger_4429(self):
        """High throughput PTY output (multi-MB) streams smoothly without triggering 4429 rate limit."""

        async def run():
            session = self.server.terminal_manager.create_session(self.temp_workspace)
            ws_url = f"ws://127.0.0.1:{self.server.port}/ws/terminal/{session.session_id}"

            async with websockets.connect(ws_url, additional_headers=self.ws_headers) as ws:
                # Stream ~1MB of text via python in PTY
                py_cmd = (
                    b"python3 -c \"import sys; [sys.stdout.write('A'*1000 + '\\n') "
                    b'for _ in range(1000)]; sys.stdout.flush()"\n'
                )
                session.write(py_cmd)

                received_bytes = 0
                start_time = time.monotonic()
                while received_bytes < 500_000 and (time.monotonic() - start_time) < 5.0:
                    try:
                        chunk = await asyncio.wait_for(ws.recv(), timeout=2.0)
                        if isinstance(chunk, bytes):
                            received_bytes += len(chunk)
                    except TimeoutError:
                        break

                self.assertGreaterEqual(
                    received_bytes,
                    100_000,
                    f"Expected to receive significant output, got {received_bytes} bytes",
                )

        asyncio.run(run())

    @unittest.skipIf(sys.platform == "win32", "POSIX PTY buffer reconnect test")
    def test_reconnect_replays_buffer(self):
        """Reconnecting to an existing session immediately replays recent history from replay buffer."""

        async def run():
            session = self.server.terminal_manager.create_session(self.temp_workspace)
            ws_url = f"ws://127.0.0.1:{self.server.port}/ws/terminal/{session.session_id}"

            # 1. Connect first time and print a unique marker
            async with websockets.connect(ws_url, additional_headers=self.ws_headers) as ws1:
                session.write(b"echo UNIQUE_REPLAY_MARKER_9988\n")
                found = False
                for _ in range(10):
                    chunk = await asyncio.wait_for(ws1.recv(), timeout=2.0)
                    if isinstance(chunk, bytes) and b"UNIQUE_REPLAY_MARKER_9988" in chunk:
                        found = True
                        break
                self.assertTrue(found, "Marker was not received on first connection")

            # 2. Reconnect to same session: first frame received MUST be binary replay containing marker
            async with websockets.connect(ws_url, additional_headers=self.ws_headers) as ws2:
                replay_chunk = await asyncio.wait_for(ws2.recv(), timeout=2.0)
                self.assertIsInstance(replay_chunk, bytes)
                self.assertIn(b"UNIQUE_REPLAY_MARKER_9988", replay_chunk)

        asyncio.run(run())

    @unittest.skipIf(sys.platform == "win32", "POSIX PTY exit frame test")
    def test_exit_frame_delivered_on_process_exit(self):
        """When the terminal shell exits, a JSON exit frame is delivered before connection closes."""

        async def run():
            session = self.server.terminal_manager.create_session(self.temp_workspace)
            ws_url = f"ws://127.0.0.1:{self.server.port}/ws/terminal/{session.session_id}"

            async with websockets.connect(ws_url, additional_headers=self.ws_headers) as ws:
                # Tell shell to exit with code 42
                session.write(b"exit 42\n")

                exit_frame = None
                while True:
                    try:
                        frame = await asyncio.wait_for(ws.recv(), timeout=3.0)
                        if isinstance(frame, str):
                            data = json.loads(frame)
                            if data.get("type") == "exit":
                                exit_frame = data
                                break
                    except (ConnectionClosed, TimeoutError):
                        break

                self.assertIsNotNone(exit_frame, "Exit frame was not delivered")
                self.assertEqual(exit_frame.get("code"), 42)

        asyncio.run(run())

    @unittest.skipIf(sys.platform == "win32", "POSIX SIGHUP trap test")
    def test_other_websocket_stays_responsive_during_stubborn_terminal_close(self):
        """Closing a SIGHUP-ignoring shell offloaded to a thread does not block other websocket traffic."""

        async def run():
            sess1 = self.server.terminal_manager.create_session(self.temp_workspace)
            sess2 = self.server.terminal_manager.create_session(self.temp_workspace)

            ws_url1 = f"ws://127.0.0.1:{self.server.port}/ws/terminal/{sess1.session_id}"
            ws_url2 = f"ws://127.0.0.1:{self.server.port}/ws/terminal/{sess2.session_id}"

            async with (
                websockets.connect(ws_url1, additional_headers=self.ws_headers) as ws1,
                websockets.connect(ws_url2, additional_headers=self.ws_headers) as ws2,
            ):
                sess1.write(b"trap '' HUP; sleep 10\n")
                await asyncio.sleep(0.1)

                close_task = asyncio.create_task(ws1.send(json.dumps({"type": "close"})))
                await asyncio.sleep(0.1)

                t_ping_start = time.time()
                await ws2.send(json.dumps({"type": "resize", "cols": 120, "rows": 40}))
                sess2.write(b"echo RESPONSIVE_OK\n")

                received_ok = False
                for _ in range(10):
                    try:
                        frame = await asyncio.wait_for(ws2.recv(), timeout=0.8)
                        if isinstance(frame, bytes) and b"RESPONSIVE_OK" in frame:
                            received_ok = True
                            break
                    except (TimeoutError, ConnectionClosed):
                        break

                t_ping_duration = time.time() - t_ping_start
                self.assertTrue(received_ok, "ws2 failed to respond while sess1 was closing")
                self.assertLess(
                    t_ping_duration,
                    1.5,
                    f"ws2 response took {t_ping_duration:.2f}s, indicating event loop was blocked",
                )

                await close_task
                sess2.close()

        asyncio.run(run())

    @unittest.skipIf(sys.platform == "win32", "POSIX contiguous stream test")
    def test_reattach_during_continuous_write_yields_contiguous_byte_stream(self):
        """Atomically taking replay snapshot and subscribing prevents lost or duplicated bytes on reattach."""
        import re

        async def run():
            session = self.server.terminal_manager.create_session(self.temp_workspace)
            session.write(b"stty -echo\n")
            await asyncio.sleep(0.1)

            ws_url = f"ws://127.0.0.1:{self.server.port}/ws/terminal/{session.session_id}"

            writer_cmd = (
                b'python3 -c "'
                b"import time; "
                b"[print(f'BLK_{i:06d}', flush=True) or time.sleep(0.005) for i in range(1, 601)]; "
                b"print('REATTACH_FINISHED', flush=True)"
                b'"\n'
            )
            session.write(writer_cmd)

            ws1_bytes = bytearray()
            async with websockets.connect(ws_url, additional_headers=self.ws_headers) as ws1:
                for _ in range(5):
                    frame = await asyncio.wait_for(ws1.recv(), timeout=2.0)
                    if isinstance(frame, bytes):
                        ws1_bytes.extend(frame)

            await asyncio.sleep(0.05)

            ws2_bytes = bytearray()
            async with websockets.connect(ws_url, additional_headers=self.ws_headers) as ws2:
                while True:
                    try:
                        frame = await asyncio.wait_for(ws2.recv(), timeout=4.0)
                        if isinstance(frame, bytes):
                            ws2_bytes.extend(frame)
                            if b"REATTACH_FINISHED" in frame:
                                break
                        elif isinstance(frame, str):
                            data = json.loads(frame)
                            if data.get("type") == "exit":
                                break
                    except (TimeoutError, ConnectionClosed):
                        break

            matches = re.findall(rb"BLK_(\d{6})", ws2_bytes)
            nums = [int(m) for m in matches]
            self.assertGreater(len(nums), 5, "Expected at least 5 block tokens in reattached stream")

            expected_range = list(range(nums[0], nums[-1] + 1))
            self.assertEqual(
                nums,
                expected_range,
                f"Stream was not contiguous: {nums[:10]}...{nums[-10:]}",
            )
            session.close()

        asyncio.run(run())

    @unittest.skipIf(sys.platform == "win32", "POSIX pty test")
    def test_six_concurrent_terminal_websockets_all_connect_and_stream(self):
        """All 6 concurrent terminal sessions plus 1 notification socket connect and stream without 4429."""

        async def run():
            notif_url = f"ws://127.0.0.1:{self.server.port}/ws"
            notif_ws = await websockets.connect(notif_url, additional_headers=self.ws_headers)

            term_sockets = []
            sessions = []
            try:
                for i in range(6):
                    session = self.server.terminal_manager.create_session(self.temp_workspace)
                    sessions.append(session)
                    term_url = f"ws://127.0.0.1:{self.server.port}/ws/terminal/{session.session_id}"
                    ws = await websockets.connect(term_url, additional_headers=self.ws_headers)
                    term_sockets.append(ws)

                for i, ws in enumerate(term_sockets):
                    token = f"TERM_OK_{i}".encode("utf-8")
                    sessions[i].write(b"echo " + token + b"\n")
                    received = bytearray()
                    start_time = time.monotonic()
                    while time.monotonic() - start_time < 3.0:
                        frame = await asyncio.wait_for(ws.recv(), timeout=2.0)
                        if isinstance(frame, bytes):
                            received.extend(frame)
                            if token in received:
                                break
                    self.assertIn(token, received, f"Terminal session {i + 1} did not receive expected output")
            finally:
                for ws in term_sockets:
                    await ws.close()
                await notif_ws.close()
                for s in sessions:
                    s.close()

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
