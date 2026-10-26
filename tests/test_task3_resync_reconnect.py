import time
import unittest
from playwright.sync_api import sync_playwright

from deskai.server.supervisor import DesktopServer


class TestTask3ResyncLoopAndReconnect(unittest.TestCase):
    def test_resync_frame_count_on_reconnect(self):
        """Playwright test: forcing socket disconnect must not trigger infinite resync loop (<= 2 in 3s)."""
        server = DesktopServer()
        server.start()

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()

            redeem_url = f"http://127.0.0.1:{server.port}/auth/redeem?token={server.launch_token}"
            page.goto(redeem_url)
            page.wait_for_selector("#promptForm")

            # Wait for initial WS connection and snapshot
            page.wait_for_function(
                "() => window.wsClient && window.wsClient.socket && window.wsClient.socket.readyState === 1"
            )

            # Track sent frames
            page.evaluate("""() => {
              window.__resyncCount = 0;
              const originalSend = WebSocket.prototype.send;
              WebSocket.prototype.send = function(data) {
                try {
                  const parsed = JSON.parse(data);
                  if (parsed.type === 'client.resync') {
                    window.__resyncCount++;
                  }
                } catch(e) {}
                return originalSend.apply(this, arguments);
              };
            }""")

            # Simulate prior received sequence number in store so lastSeq > 0
            page.evaluate("() => { if (window.store) { window.store.state.connection.lastSeq = 5; } }")

            # Force socket close to trigger reconnect flow
            page.evaluate("() => { window.wsClient.socket.close(); }")

            # Wait 3.2 seconds to measure resync frame rate
            time.sleep(3.2)

            resync_count = page.evaluate("() => window.__resyncCount")
            last_seq = page.evaluate("() => window.store ? window.store.state.connection.lastSeq : 0")

            browser.close()
            server.stop()

            # Resync frames must be capped (<= 2 in 3 seconds), and lastSeq must be valid
            self.assertLessEqual(
                resync_count, 2, f"Resync storm occurred: sent {resync_count} frames in 3s (expected <= 2)"
            )
            self.assertGreaterEqual(last_seq, 1, f"lastSeq was not adopted correctly: {last_seq}")

    def test_js_gap_and_snapshot_logic_unit(self):
        """Unit test of WebSocketClient gap detection and snapshot sequence adoption."""
        server = DesktopServer()
        server.start()

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()

            redeem_url = f"http://127.0.0.1:{server.port}/auth/redeem?token={server.launch_token}"
            page.goto(redeem_url)
            page.wait_for_selector("#promptForm")

            results = page.evaluate("""() => {
              const client = window.wsClient;
              let resyncCalls = 0;
              client._requestSnapshotResync = () => { resyncCalls++; };

              // 1. Initial snapshot adoption: seq 1 should NOT trigger resync
              client.socket.onmessage({ data: JSON.stringify({ type: "server.snapshot", seq: 1, payload: {} }) });
              const seqAfterSnapshot = window.store.state.connection.lastSeq;
              const resyncAfterSnapshot = resyncCalls;

              // 2. Normal sequential frame: seq 2
              client.socket.onmessage({ data: JSON.stringify({ type: "agent.plan", seq: 2, payload: {} }) });
              const seqAfterPlan = window.store.state.connection.lastSeq;

              // 3. Gap frame: seq 5 (expected 3) -> should trigger gap resync
              client.socket.onmessage({ data: JSON.stringify({ type: "agent.diff", seq: 5, payload: {} }) });
              const resyncAfterGap = resyncCalls;

              return {
                seqAfterSnapshot,
                resyncAfterSnapshot,
                seqAfterPlan,
                resyncAfterGap
              };
            }""")

            browser.close()
            server.stop()

            self.assertEqual(results["seqAfterSnapshot"], 1, "Snapshot seq was not adopted")
            self.assertEqual(results["resyncAfterSnapshot"], 0, "Snapshot triggered unexpected resync")
            self.assertEqual(results["seqAfterPlan"], 2, "Sequential frame did not update lastSeq")
            self.assertEqual(results["resyncAfterGap"], 1, "Gap did not trigger resync")


if __name__ == "__main__":
    unittest.main()
