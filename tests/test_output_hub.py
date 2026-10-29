from __future__ import annotations
import asyncio
import logging
import threading
import time
import unittest
from unittest.mock import patch

from deskai.server.output_hub import (
    COALESCE_WINDOW_S,
    MAX_TEXT_CHARS,
    MAX_TEXT_LINES,
    OutputHub,
    OutputLogHandler,
    _Subscriber,
    channel_for_logger,
    clean_text,
    install_output_logging,
    uninstall_output_logging,
)


class TestOutputHubSanitiserAndRedaction(unittest.TestCase):
    """TC-OUT-08 to TC-OUT-11: Sanitisation, truncation, and redaction."""

    def test_tc_out_08_sanitiser_ansi_osc_and_control_chars_stripped(self):
        """TC-OUT-08: ANSI/OSC and control chars stripped; \n and \t kept."""
        raw = "\x1b[31mRed text\x1b[0m\twith tab\n\x1b]8;;http://evil.com\x07hyperlink\x1b]8;;\x07\x00\x08clean\r\n"
        cleaned = clean_text(raw, secrets=set())
        self.assertNotIn("\x1b", cleaned)
        self.assertNotIn("\x00", cleaned)
        self.assertNotIn("\x08", cleaned)
        self.assertNotIn("\r", cleaned)
        self.assertIn("Red text\twith tab\nhyperlinkclean", cleaned)

    def test_tc_out_09_truncation(self):
        """TC-OUT-09: 10,000-char and 100-line messages capped with '... [truncated]'."""
        # 10,000 chars on one line
        long_line = "a" * 10000
        cleaned_chars = clean_text(long_line, secrets=set())
        self.assertLessEqual(len(cleaned_chars), MAX_TEXT_CHARS + len(" ... [truncated]"))
        self.assertTrue(cleaned_chars.endswith(" ... [truncated]"))

        # 100 lines
        lines = [f"line {i}" for i in range(100)]
        many_lines = "\n".join(lines)
        cleaned_lines = clean_text(many_lines, secrets=set())
        split_lines = cleaned_lines.split("\n")
        self.assertLessEqual(len(split_lines), MAX_TEXT_LINES + 1)
        self.assertIn("... [truncated]", split_lines[-1])

    def test_tc_out_10_redaction_patterns(self):
        """TC-OUT-10: Authorization, token=, sk-..., ghp_..., JWT, /auth/redeem?token=... all redacted."""
        secrets = set()
        cases = [
            ("Authorization: Bearer my-secret-token-12345", "Authorization: [REDACTED]"),
            ("cookie: session=abcd1234efgh5678", "cookie: [REDACTED]"),
            ("GET /auth/redeem?token=launch_tok_12345678 HTTP/1.1", "GET /auth/redeem?token=[REDACTED] HTTP/1.1"),
            (
                "Connecting with token=supersecretkey and key=anotherkey123",
                "Connecting with token=[REDACTED] and key=[REDACTED]",
            ),
            ("API error with sk-1234567890abcdef12345678 in request", "API error with [REDACTED] in request"),
            ("Cloning using ghp_123456789012345678901234567890", "Cloning using [REDACTED]"),
            (
                "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHpunv_cYXvdPBwW_dYwcbqgpeYo",
                "Bearer [REDACTED]",
            ),
        ]
        for raw, expected in cases:
            cleaned = clean_text(raw, secrets)
            self.assertEqual(cleaned, expected, f"Failed redacting: {raw}")

    def test_tc_out_11_registered_secrets(self):
        """TC-OUT-11: Registered secrets (launch token and session id) replaced even inside other text."""
        launch_tok = "tok_launch_xyz987654321"
        session_id = "sess_abcdef123456789"
        secrets = {launch_tok, session_id}

        text = f"User connected with launch token {launch_tok} and session {session_id} successfully."
        cleaned = clean_text(text, secrets)
        self.assertNotIn(launch_tok, cleaned)
        self.assertNotIn(session_id, cleaned)
        self.assertEqual(cleaned, "User connected with launch token [REDACTED] and session [REDACTED] successfully.")

        # Ignore short secrets (< MIN_SECRET_LEN)
        short_secrets = {"abc"}
        text2 = "abc is short"
        self.assertEqual(clean_text(text2, short_secrets), "abc is short")


class TestOutputHubCore(unittest.TestCase):
    """TC-OUT-12 to TC-OUT-16: Ring, cursor, reset, coalescing, concurrency, backpressure."""

    def test_tc_out_12_ring_and_cursor(self):
        """TC-OUT-12: seq strictly monotonic from 1; ring keeps last 2000; snapshot_and_subscribe(since)."""
        hub = OutputHub(ring_size=2000)
        for i in range(2500):
            hub.emit("system", "info", f"msg {i}")

        loop = asyncio.new_event_loop()
        try:
            sub = _Subscriber(loop)
            # Total seq emitted: 2500. Ring holds last 2000 (seq 501 to 2500).
            recs, reset, first, last = hub.snapshot_and_subscribe(sub, since=2400)
            self.assertFalse(reset)
            self.assertEqual(first, 501)
            self.assertEqual(last, 2500)
            self.assertEqual(len(recs), 100)
            self.assertEqual(recs[0].seq, 2401)
            self.assertEqual(recs[-1].seq, 2500)
            hub.unsubscribe(sub)
        finally:
            loop.close()

    def test_tc_out_13_reset_semantics(self):
        """TC-OUT-13: evicted cursor and since > last both return reset=True."""
        hub = OutputHub(ring_size=100)
        for i in range(150):
            hub.emit("system", "info", f"msg {i}")

        loop = asyncio.new_event_loop()
        try:
            sub = _Subscriber(loop)
            # Evicted cursor: client has since=10, but ring starts at seq 51
            recs, reset, first, last = hub.snapshot_and_subscribe(sub, since=10)
            self.assertTrue(reset)
            self.assertEqual(len(recs), 100)
            self.assertEqual(recs[0].seq, 51)
            hub.unsubscribe(sub)

            # Cursor ahead of server (server restart): client has since=500, but last is 150
            sub2 = _Subscriber(loop)
            recs2, reset2, first2, last2 = hub.snapshot_and_subscribe(sub2, since=500)
            self.assertTrue(reset2)
            self.assertEqual(len(recs2), 100)
            hub.unsubscribe(sub2)
        finally:
            loop.close()

    def test_tc_out_14_coalescing_and_flush(self):
        """TC-OUT-14: identical emits produce 1 record + summary; flush_pending emits trailing summary."""
        hub = OutputHub(ring_size=2000)
        curr_time = 100.0

        with patch("deskai.server.output_hub.time.monotonic", side_effect=lambda: curr_time):
            # 1,000 identical emits within coalesce window
            for _ in range(1000):
                hub.emit("system", "warn", "Something repeated")

            loop = asyncio.new_event_loop()
            try:
                sub = _Subscriber(loop)
                recs, reset, first, last = hub.snapshot_and_subscribe(sub, since=0)
                # Should have 1 record so far (first emit), with 999 suppressed
                self.assertEqual(len(recs), 1)
                self.assertEqual(recs[0].text, "Something repeated")

                # Advance time past COALESCE_WINDOW_S and flush
                curr_time += COALESCE_WINDOW_S + 0.1
                hub.flush_pending()

                # Process pending threadsafe callbacks in the loop
                async def drain():
                    pass

                loop.run_until_complete(drain())

                self.assertFalse(sub.queue.empty())
                summary = sub.queue.get_nowait()
                self.assertEqual(summary.text, "Previous message repeated 999 more times")
                self.assertEqual(summary.level, "warn")
                self.assertEqual(summary.channel, "system")
                hub.unsubscribe(sub)
            finally:
                loop.close()

    def test_tc_out_15_thread_safety(self):
        """TC-OUT-15: 8 threads x 5,000 emits: no exception, unique ordered seq, no lost records within ring."""
        ring_size = 40000
        hub = OutputHub(ring_size=ring_size)
        num_threads = 8
        emits_per_thread = 5000
        total_emits = num_threads * emits_per_thread

        def worker(thread_idx: int):
            for i in range(emits_per_thread):
                hub.emit("task", "info", f"worker {thread_idx} msg {i}")

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        loop = asyncio.new_event_loop()
        try:
            sub = _Subscriber(loop)
            recs, reset, first, last = hub.snapshot_and_subscribe(sub, since=0)
            self.assertEqual(len(recs), total_emits)
            self.assertEqual(last, total_emits)
            # Verify strict sequence monotonicity
            seqs = [r.seq for r in recs]
            self.assertEqual(seqs, list(range(1, total_emits + 1)))
            hub.unsubscribe(sub)
        finally:
            loop.close()

    def test_tc_out_16_subscriber_backpressure(self):
        """TC-OUT-16: subscriber queue max reached -> drop-oldest, dropped counted, emit never blocks."""
        hub = OutputHub()
        loop = asyncio.new_event_loop()
        try:
            sub = _Subscriber(loop)
            # Replace queue with small capacity
            sub.queue = asyncio.Queue(maxsize=10)
            hub.snapshot_and_subscribe(sub, since=0)

            # Emit 30 records
            start = time.monotonic()
            for i in range(30):
                hub.emit("ports", "info", f"p {i}")
            duration = time.monotonic() - start
            # Producer must never block
            self.assertLess(duration, 0.5)

            # Drain callbacks scheduled on loop
            async def drain():
                pass

            loop.run_until_complete(drain())

            # Queue has 10 items, 20 dropped
            self.assertEqual(sub.queue.qsize(), 10)
            self.assertEqual(sub.dropped, 20)

            # Most recent items kept (20 to 29)
            items = []
            while not sub.queue.empty():
                items.append(sub.queue.get_nowait())
            self.assertEqual(items[0].text, "p 20")
            self.assertEqual(items[-1].text, "p 29")
            hub.unsubscribe(sub)
        finally:
            loop.close()


class TestOutputLogHandlerAndLifecycle(unittest.TestCase):
    """TC-OUT-17 to TC-OUT-19: Logger mapping, re-entrancy, install/uninstall lifecycle."""

    def test_tc_out_17_handler_mapping(self):
        """TC-OUT-17: logger names map to channels; levelno maps to levels; exc_info traceback included."""
        self.assertEqual(channel_for_logger("deskai.bridge.git"), "git")
        self.assertEqual(channel_for_logger("deskai.bridge.git.status"), "git")
        self.assertEqual(channel_for_logger("deskai.bridge.ports"), "ports")
        self.assertEqual(channel_for_logger("deskai.bridge.terminal"), "terminal")
        self.assertEqual(channel_for_logger("deskai.server.terminal"), "terminal")
        self.assertEqual(channel_for_logger("deskai.diagnostics"), "diagnostics")
        self.assertEqual(channel_for_logger("deskai.server.uec"), "task")
        self.assertEqual(channel_for_logger("deskai.supervisor"), "system")
        self.assertEqual(channel_for_logger("unknown.logger"), "system")

        hub = OutputHub()
        handler = install_output_logging(hub)
        try:
            git_logger = logging.getLogger("deskai.bridge.git")
            term_logger = logging.getLogger("deskai.server.terminal")
            sys_logger = logging.getLogger("deskai.supervisor")

            git_logger.debug("git debug line")
            git_logger.info("git info line")
            term_logger.warning("term warning line")
            try:
                raise ValueError("test exception for traceback")
            except ValueError:
                sys_logger.exception("system failure occurred")

            loop = asyncio.new_event_loop()
            try:
                sub = _Subscriber(loop)
                recs, _, _, _ = hub.snapshot_and_subscribe(sub, since=0)
                hub.unsubscribe(sub)

                self.assertEqual(len(recs), 4)
                # rec 0: git debug
                self.assertEqual(recs[0].channel, "git")
                self.assertEqual(recs[0].level, "debug")
                self.assertEqual(recs[0].text, "git debug line")

                # rec 1: git info
                self.assertEqual(recs[1].channel, "git")
                self.assertEqual(recs[1].level, "info")

                # rec 2: term warning -> warn
                self.assertEqual(recs[2].channel, "terminal")
                self.assertEqual(recs[2].level, "warn")
                self.assertEqual(recs[2].text, "term warning line")

                # rec 3: system error with exc_info
                self.assertEqual(recs[3].channel, "system")
                self.assertEqual(recs[3].level, "error")
                self.assertIn("system failure occurred", recs[3].text)
                self.assertIn("Traceback (most recent call last):", recs[3].text)
                self.assertIn("ValueError: test exception for traceback", recs[3].text)
            finally:
                loop.close()
        finally:
            uninstall_output_logging(handler)

    def test_tc_out_18_reentrancy_guard(self):
        """TC-OUT-18: a record emitted while the handler is busy is dropped, no recursion."""
        hub = OutputHub()
        handler = OutputLogHandler(hub)

        # 1. Output hub's own logger records are ignored
        rec_hub = logging.LogRecord(
            name="deskai.server.output_hub",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="internal message",
            args=(),
            exc_info=None,
        )
        handler.emit(rec_hub)

        # 2. Re-entrancy flag busy
        OutputLogHandler._local.busy = True
        try:
            rec_normal = logging.LogRecord(
                name="deskai.bridge.git",
                level=logging.INFO,
                pathname=__file__,
                lineno=1,
                msg="git busy message",
                args=(),
                exc_info=None,
            )
            handler.emit(rec_normal)
        finally:
            OutputLogHandler._local.busy = False

        loop = asyncio.new_event_loop()
        try:
            sub = _Subscriber(loop)
            recs, _, _, _ = hub.snapshot_and_subscribe(sub, since=0)
            self.assertEqual(len(recs), 0)
            hub.unsubscribe(sub)
        finally:
            loop.close()

    def test_tc_out_19_install_uninstall(self):
        """TC-OUT-19: handler removed on stop(); no duplicate handlers after restart."""
        root = logging.getLogger("deskai")
        initial_handlers_count = len(root.handlers)

        hub1 = OutputHub()
        h1 = install_output_logging(hub1)
        self.assertIn(h1, root.handlers)
        self.assertEqual(len(root.handlers), initial_handlers_count + 1)
        self.assertEqual(root.level, logging.DEBUG)

        uninstall_output_logging(h1)
        self.assertNotIn(h1, root.handlers)
        self.assertEqual(len(root.handlers), initial_handlers_count)

        # Re-install
        hub2 = OutputHub()
        h2 = install_output_logging(hub2)
        self.assertIn(h2, root.handlers)
        self.assertEqual(len(root.handlers), initial_handlers_count + 1)
        uninstall_output_logging(h2)
        self.assertNotIn(h2, root.handlers)


if __name__ == "__main__":
    unittest.main()
