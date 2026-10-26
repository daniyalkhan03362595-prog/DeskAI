import json
from pathlib import Path
import unittest
from playwright.sync_api import sync_playwright
from starlette.testclient import TestClient

from deskai.server.supervisor import DesktopServer

TRANSITIONS_PATH = Path(__file__).resolve().parent.parent / "src" / "deskai" / "static" / "transitions.json"


class TestTask4ServerUECStateMachine(unittest.TestCase):
    def setUp(self):
        self.server = DesktopServer()
        self.client = TestClient(self.server.app)

        self.headers = {
            "Host": f"127.0.0.1:{self.server.port}",
            "Origin": f"http://127.0.0.1:{self.server.port}",
        }

        # Authenticate session with proper host header
        redeem_res = self.client.get(
            f"/auth/redeem?token={self.server.launch_token}",
            headers=self.headers,
            follow_redirects=False,
        )
        self.session_cookie = redeem_res.cookies.get("deskai_session")
        self.cookies = {"deskai_session": self.session_cookie}

    def test_transitions_file_exists(self):
        """Validates that transitions.json exists and defines valid states."""
        self.assertTrue(TRANSITIONS_PATH.exists(), f"transitions.json not found at {TRANSITIONS_PATH}")
        with open(TRANSITIONS_PATH, "r", encoding="utf-8") as f:
            table = json.load(f)
        self.assertIn("IDLE", table)
        self.assertIn("PLANNING", table)
        self.assertIn("REVIEW_DIFF", table)

    def test_server_rejects_invalid_transitions(self):
        """Server must reject invalid state transitions from IDLE with ERR_INVALID_TRANSITION."""
        with self.client.websocket_connect("/ws", headers=self.headers, cookies=self.cookies) as ws:
            # In IDLE state, uec.approve is INVALID (must be in REVIEW_DIFF or PLANNING)
            ws.send_json({"type": "uec.approve", "request_id": "req-1"})
            reply = ws.receive_json()

            # Must be an error frame, not a success ack
            self.assertEqual(
                reply.get("type"),
                "error",
                f"Expected error frame for invalid transition from IDLE, got: {reply}",
            )
            self.assertEqual(reply.get("code"), "ERR_INVALID_TRANSITION")

            # Direct jump from IDLE to SUCCESS must be rejected
            ws.send_json({"type": "uec.transition", "payload": {"from": "IDLE", "to": "SUCCESS"}})
            reply2 = ws.receive_json()
            self.assertEqual(reply2.get("type"), "error")
            self.assertEqual(reply2.get("code"), "ERR_INVALID_TRANSITION")

    def test_server_valid_transitions_and_idempotency(self):
        """Server processes valid transitions step by step and is idempotent per request_id."""
        with self.client.websocket_connect("/ws", headers=self.headers, cookies=self.cookies) as ws:
            # 1. IDLE -> PLANNING
            ws.send_json({"type": "uec.transition", "payload": {"from": "IDLE", "to": "PLANNING"}})
            r1 = ws.receive_json()
            self.assertEqual(r1.get("type"), "uec.ack")
            self.assertEqual(r1.get("payload", {}).get("state"), "PLANNING")

            # 2. PLANNING -> EXECUTING
            ws.send_json({"type": "uec.transition", "payload": {"from": "PLANNING", "to": "EXECUTING"}})
            r2 = ws.receive_json()
            self.assertEqual(r2.get("type"), "uec.ack")
            self.assertEqual(r2.get("payload", {}).get("state"), "EXECUTING")

            # 3. EXECUTING -> REVIEW_DIFF
            ws.send_json({"type": "uec.transition", "payload": {"from": "EXECUTING", "to": "REVIEW_DIFF"}})
            r3 = ws.receive_json()
            self.assertEqual(r3.get("type"), "uec.ack")
            self.assertEqual(r3.get("payload", {}).get("state"), "REVIEW_DIFF")

            # 4. Approve in REVIEW_DIFF -> SUCCESS
            ws.send_json({"type": "uec.approve", "request_id": "unique-req-99"})
            r4 = ws.receive_json()
            self.assertEqual(r4.get("type"), "uec.ack")
            self.assertEqual(r4.get("payload", {}).get("state"), "SUCCESS")
            self.assertTrue(r4.get("payload", {}).get("approved"))

            # 5. Idempotent re-send of same request_id
            ws.send_json({"type": "uec.approve", "request_id": "unique-req-99"})
            r5 = ws.receive_json()
            self.assertEqual(r5.get("type"), "uec.ack")
            self.assertEqual(r5.get("payload", {}).get("state"), "SUCCESS")
            self.assertTrue(r5.get("payload", {}).get("idempotent"))

    def test_single_uec_frame_sent_per_click(self):
        """Playwright test: clicking Accept Changes in REVIEW_DIFF must send exactly 1 uec.* frame."""
        server = DesktopServer()
        server.start()

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()

            redeem_url = f"http://127.0.0.1:{server.port}/auth/redeem?token={server.launch_token}"
            page.goto(redeem_url)
            page.wait_for_selector("#promptForm")
            page.wait_for_function(
                "() => window.wsClient && window.wsClient.socket && window.wsClient.socket.readyState === 1"
            )

            # Put UEC into REVIEW_DIFF and intercept outgoing frames
            page.evaluate("""() => {
              window.__uecOutgoingFrames = [];
              const originalSend = WebSocket.prototype.send;
              WebSocket.prototype.send = function(data) {
                try {
                  const parsed = JSON.parse(data);
                  if (parsed.type && parsed.type.startsWith('uec.')) {
                    window.__uecOutgoingFrames.push(parsed.type);
                  }
                } catch(e) {}
                return originalSend.apply(this, arguments);
              };

              // Mount and transition to REVIEW_DIFF
              window.store.state.execution.state = "REVIEW_DIFF";
              window.UEC.renderButtons("REVIEW_DIFF");
            }""")

            # Click Accept Changes button
            page.click("button[data-action='uec-approve']")
            page.wait_for_timeout(300)

            frames = page.evaluate("() => window.__uecOutgoingFrames")
            browser.close()
            server.stop()

            self.assertEqual(
                len(frames),
                1,
                f"Expected exactly 1 uec.* frame on Accept Changes, got {len(frames)}: {frames}",
            )


if __name__ == "__main__":
    unittest.main()
