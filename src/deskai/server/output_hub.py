from __future__ import annotations
import asyncio
from collections import deque
from dataclasses import dataclass
import logging
import re
import threading
import time

CHANNELS = ("system", "task", "git", "ports", "terminal", "diagnostics")
LEVELS = ("debug", "info", "warn", "error")
RING_SIZE = 2000
MAX_TEXT_CHARS = 4096
MAX_TEXT_LINES = 40
SUBSCRIBER_QUEUE_MAX = 1000
COALESCE_WINDOW_S = 1.0
MIN_SECRET_LEN = 8


@dataclass(frozen=True)
class LogRecord:
    seq: int
    ts: int  # epoch milliseconds
    channel: str
    level: str
    text: str

    def to_dict(self) -> dict:
        return {"seq": self.seq, "ts": self.ts, "channel": self.channel, "level": self.level, "text": self.text}


_CONTROL_RE = re.compile(
    r"\x1b(?:\][^\x07\x1b]*(?:\x07|\x1b\\)|\[[0-?]*[ -/]*[@-~]|[@-Z\\-_])|[\x00-\x08\x0b\x0c\x0d\x0e-\x1f\x7f]"
)
_REDACTIONS = [
    (re.compile(r"(?i)\b(authorization|cookie|set-cookie)\s*[:=]\s*[^\r\n]+"), r"\1: [REDACTED]"),
    (re.compile(r"(?i)(/auth/redeem\?token=)[^\s&\"']+"), r"\1[REDACTED]"),
    (
        re.compile(
            r"(?i)\b(token|secret|password|passwd|(?:api[_-]?|access[_-]?)?key|deskai_session)\s*[=:]\s*[^\s&\"']+"
        ),
        r"\1=[REDACTED]",
    ),
    (
        re.compile(
            r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,})\b"
        ),
        "[REDACTED]",
    ),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), "[REDACTED]"),
]


def clean_text(value, secrets: set[str]) -> str:
    text = _CONTROL_RE.sub("", str(value))  # strips ANSI/OSC and control chars, keeps \n and \t
    for secret in secrets:  # exact runtime secrets first (launch token, session ids)
        if len(secret) >= MIN_SECRET_LEN:
            text = text.replace(secret, "[REDACTED]")
    for pattern, repl in _REDACTIONS:
        text = pattern.sub(repl, text)
    lines = text.split("\n")
    if len(lines) > MAX_TEXT_LINES:
        lines = lines[:MAX_TEXT_LINES] + ["... [truncated]"]
    text = "\n".join(lines).rstrip()
    return text[:MAX_TEXT_CHARS] + (" ... [truncated]" if len(text) > MAX_TEXT_CHARS else "")


class _Subscriber:
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.queue: asyncio.Queue[LogRecord] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_MAX)
        self.dropped = 0

    def offer(self, rec: LogRecord) -> None:  # always executed on the subscriber's loop thread
        try:
            self.queue.put_nowait(rec)
        except asyncio.QueueFull:  # drop-oldest, count it
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self.dropped += 1
            try:
                self.queue.put_nowait(rec)
            except asyncio.QueueFull:
                self.dropped += 1


class OutputHub:
    def __init__(self, ring_size: int = RING_SIZE):
        self._lock = threading.Lock()
        self._ring: deque[LogRecord] = deque(maxlen=ring_size)
        self._seq = 0
        self._secrets: set[str] = set()
        self._subs: set[_Subscriber] = set()
        self._last: LogRecord | None = None
        self._last_mono = 0.0
        self._suppressed = 0

    def register_secret(self, value: str | None) -> None:
        if value and len(value) >= MIN_SECRET_LEN:
            with self._lock:
                self._secrets.add(value)

    def emit(self, channel: str, level: str, text) -> None:
        """Thread-safe, non-blocking, never raises."""
        try:
            channel = channel if channel in CHANNELS else "system"
            level = level if level in LEVELS else "info"
            with self._lock:
                secrets = set(self._secrets)
            clean = clean_text(text, secrets)
            if not clean:
                return
            now = time.monotonic()
            out: list[LogRecord] = []
            with self._lock:
                last = self._last
                if (
                    last
                    and (last.channel, last.level, last.text) == (channel, level, clean)
                    and now - self._last_mono < COALESCE_WINDOW_S
                ):
                    self._suppressed += 1
                    self._last_mono = now
                    return
                summary = self._summary_locked()
                if summary:
                    out.append(summary)
                rec = self._append_locked(channel, level, clean)
                self._last, self._last_mono = rec, now
                out.append(rec)
                subs = list(self._subs)
            self._publish(subs, out)
        except Exception:
            pass

    def flush_pending(self) -> None:
        """Called by each stream pump tick so a trailing repeat count is not lost when logging goes quiet."""
        summary = None
        subs: list[_Subscriber] = []
        with self._lock:
            if self._suppressed and time.monotonic() - self._last_mono >= COALESCE_WINDOW_S:
                summary = self._summary_locked()
                subs = list(self._subs)
            else:
                return
        if summary:
            self._publish(subs, [summary])

    def snapshot_and_subscribe(self, sub: _Subscriber, since: int):
        """Atomic: records after `since` plus registration, so nothing is missed or duplicated."""
        with self._lock:
            last = self._seq
            first = self._ring[0].seq if self._ring else last + 1
            reset = (since > last) or (since + 1 < first and since != 0 and last > 0)
            records = list(self._ring) if (reset or since == 0) else [r for r in self._ring if r.seq > since]
            self._subs.add(sub)
        return records, reset, first, last

    def unsubscribe(self, sub: _Subscriber) -> None:
        with self._lock:
            self._subs.discard(sub)

    # helpers
    def _append_locked(self, channel: str, level: str, text: str) -> LogRecord:
        self._seq += 1
        rec = LogRecord(self._seq, int(time.time() * 1000), channel, level, text)
        self._ring.append(rec)
        return rec

    def _summary_locked(self) -> LogRecord | None:
        if not self._suppressed or not self._last:
            return None
        n, self._suppressed = self._suppressed, 0
        return self._append_locked(
            self._last.channel,
            self._last.level,
            f"Previous message repeated {n} more time{'s' if n != 1 else ''}",
        )

    @staticmethod
    def _publish(subs: list[_Subscriber], records: list[LogRecord]) -> None:
        for sub in subs:
            for rec in records:
                try:
                    sub.loop.call_soon_threadsafe(sub.offer, rec)
                except RuntimeError:
                    pass  # loop already closed


_CHANNEL_PREFIXES = (
    ("deskai.bridge.git", "git"),
    ("deskai.bridge.ports", "ports"),
    ("deskai.bridge.terminal", "terminal"),
    ("deskai.server.terminal", "terminal"),
    ("deskai.diagnostics", "diagnostics"),
    ("deskai.bridge.diagnostics", "diagnostics"),
    ("deskai.server.uec", "task"),
)


def channel_for_logger(name: str) -> str:
    for prefix, channel in _CHANNEL_PREFIXES:
        if name == prefix or name.startswith(prefix + "."):
            return channel
    return "system"


class OutputLogHandler(logging.Handler):
    _local = threading.local()

    def __init__(self, hub: OutputHub):
        super().__init__(level=logging.DEBUG)
        self.hub = hub
        self.setFormatter(logging.Formatter("%(message)s"))  # exc_info appended by Formatter.format()

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(self._local, "busy", False) or record.name.startswith("deskai.server.output_hub"):
            return  # re-entrancy guard: the hub must never log about itself
        self._local.busy = True
        try:
            level = (
                "error"
                if record.levelno >= logging.ERROR
                else (
                    "warn"
                    if record.levelno >= logging.WARNING
                    else "info" if record.levelno >= logging.INFO else "debug"
                )
            )
            self.hub.emit(channel_for_logger(record.name), level, self.format(record))
        except Exception:
            pass
        finally:
            self._local.busy = False


def install_output_logging(hub: OutputHub) -> OutputLogHandler:
    handler = OutputLogHandler(hub)
    root = logging.getLogger("deskai")
    root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > logging.DEBUG:
        root.setLevel(logging.DEBUG)  # the UI filters by level; the logger must not pre-filter
    return handler


def uninstall_output_logging(handler: OutputLogHandler) -> None:
    logging.getLogger("deskai").removeHandler(handler)
