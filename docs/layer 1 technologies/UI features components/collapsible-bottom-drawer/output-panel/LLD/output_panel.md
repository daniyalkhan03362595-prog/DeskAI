# Low-Level Design (LLD): Output Panel (System & Channel Logs)

**Document ID:** `ORX-LLD-OUTPUT-PANEL-V2`  
**Version:** `2.1` (supersedes `ORX-LLD-OUTPUT-PANEL-V1` and V2.0 draft; incorporates clickable file:line navigation, log file export, and per-channel unread badges)  
**Parent Document:** `ORX-HLD-OUTPUT-PANEL-V2`  
**Target Codebase:** `DeskAI` (verified against `main` @ `5cc5434`)  
**Status:** Implemented  
**Date:** October 30, 2026  

---

## 1. File Map

| File | Action | Purpose |
| :--- | :--- | :--- |
| `src/deskai/server/output_hub.py` | NEW | `LogRecord`, sanitiser and redaction, `OutputHub`, `OutputLogHandler`, `install_output_logging()` |
| `src/deskai/server/supervisor.py` | MODIFY | Own an `OutputHub`; `_authorize_ws()` helper; `/ws/output` endpoint; install/uninstall handler in `start()`/`stop()`; structured `task` channel transitions |
| `src/deskai/static/js/output/client.js` | NEW | `OutputClient` (socket, cursor, reconnect, frame validation) |
| `src/deskai/static/js/output/index.js` | NEW | `OutputManager` (toolbar, filters, prefs, announcer, tab indicator, `saveLog()`, `navigateToFile()`, per-channel unread badges) |
| `src/deskai/static/js/terminal.js` | MODIFY | `LogView` record mode, `formatLogText()` parsing `file:line[:col]` links into interactive accessible `.log-link` DOM elements |
| `src/deskai/static/js/icons.js` | MODIFY | Vector `download` icon definition in `ICON_DEFS` |
| `src/deskai/static/js/app.js` | MODIFY | Create `OutputManager`, expose `window.DeskAIOutput` |
| `src/deskai/static/js/events.js` | MODIFY | `output-*` `data-action` cases (`output-save`, `output-nav`, `output-copy`, etc.); keyboard Enter/Space activation |
| `src/deskai/static/index.html` | MODIFY | Output panel markup (section 4.1), tab indicator, `output-save` button |
| `src/deskai/static/css/components.css`, `tokens.css` | MODIFY | Log styles, `.log-link` interaction styles, `#outputChannelSelect.has-unread` styling |
| `tools/check_contrast.py` | MODIFY | Log level colour pairs |
| `tests/test_output_*.py` | NEW | See section 10 (TC-OUT-01..51) |

---

## 2. Backend: `server/output_hub.py`

### 2.1 Constants and model

```python
from __future__ import annotations
import asyncio, logging, re, threading, time
from collections import deque
from dataclasses import dataclass

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
    ts: int            # epoch milliseconds
    channel: str
    level: str
    text: str

    def to_dict(self) -> dict:
        return {"seq": self.seq, "ts": self.ts, "channel": self.channel, "level": self.level, "text": self.text}
```

### 2.2 Sanitise and redact (runs before anything is stored)

```python
_CONTROL_RE = re.compile(r"\x1b(?:\][^\x07\x1b]*(?:\x07|\x1b\\)|\[[0-?]*[ -/]*[@-~]|[@-Z\\-_])|[\x00-\x08\x0b\x0c\x0d\x0e-\x1f\x7f]")
_REDACTIONS = [
    (re.compile(r"(?i)\b(authorization|cookie|set-cookie)\s*[:=]\s*[^\r\n]+"), r"\1: [REDACTED]"),
    (re.compile(r"(?i)(/auth/redeem\?token=)[^\s&\"']+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\b(token|secret|password|passwd|api[_-]?key|access[_-]?key|deskai_session)\s*[=:]\s*[^\s&\"']+"), r"\1=[REDACTED]"),
    (re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,})\b"), "[REDACTED]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), "[REDACTED]"),
]

def clean_text(value, secrets: set[str]) -> str:
    text = _CONTROL_RE.sub("", str(value))                  # strips ANSI/OSC and control chars, keeps \n and \t
    for secret in secrets:                                  # exact runtime secrets first (launch token, session ids)
        if len(secret) >= MIN_SECRET_LEN:
            text = text.replace(secret, "[REDACTED]")
    for pattern, repl in _REDACTIONS:
        text = pattern.sub(repl, text)
    lines = text.split("\n")
    if len(lines) > MAX_TEXT_LINES:
        lines = lines[:MAX_TEXT_LINES] + ["... [truncated]"]
    text = "\n".join(lines).rstrip()
    return text[:MAX_TEXT_CHARS] + (" ... [truncated]" if len(text) > MAX_TEXT_CHARS else "")
```

Note the regex `\r` is removed by `_CONTROL_RE` (CRLF becomes LF-only through `\n`); a lone `\r` never reaches the page.

### 2.3 `OutputHub`

```python
class _Subscriber:
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.queue: asyncio.Queue[LogRecord] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_MAX)
        self.dropped = 0

    def offer(self, rec: LogRecord) -> None:               # always executed on the subscriber's loop thread
        try:
            self.queue.put_nowait(rec)
        except asyncio.QueueFull:                          # drop-oldest, count it
            try: self.queue.get_nowait()
            except asyncio.QueueEmpty: pass
            self.dropped += 1
            try: self.queue.put_nowait(rec)
            except asyncio.QueueFull: self.dropped += 1


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
            with self._lock: self._secrets.add(value)

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
                if last and (last.channel, last.level, last.text) == (channel, level, clean) \
                        and now - self._last_mono < COALESCE_WINDOW_S:
                    self._suppressed += 1
                    self._last_mono = now
                    return
                summary = self._summary_locked()
                if summary: out.append(summary)
                rec = self._append_locked(channel, level, clean)
                self._last, self._last_mono = rec, now
                out.append(rec)
                subs = list(self._subs)
            self._publish(subs, out)
        except Exception:
            pass

    def flush_pending(self) -> None:
        """Called by each stream pump tick so a trailing repeat count is not lost when logging goes quiet."""
        with self._lock:
            if self._suppressed and time.monotonic() - self._last_mono >= COALESCE_WINDOW_S:
                summary = self._summary_locked(); subs = list(self._subs)
            else:
                return
        if summary: self._publish(subs, [summary])

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
        with self._lock: self._subs.discard(sub)

    # helpers
    def _append_locked(self, channel, level, text) -> LogRecord:
        self._seq += 1
        rec = LogRecord(self._seq, int(time.time() * 1000), channel, level, text)
        self._ring.append(rec)
        return rec

    def _summary_locked(self) -> LogRecord | None:
        if not self._suppressed or not self._last: return None
        n, self._suppressed = self._suppressed, 0
        return self._append_locked(self._last.channel, self._last.level,
                                   f"Previous message repeated {n} more time{'s' if n != 1 else ''}")

    @staticmethod
    def _publish(subs, records) -> None:
        for sub in subs:
            for rec in records:
                try: sub.loop.call_soon_threadsafe(sub.offer, rec)
                except RuntimeError: pass                    # loop already closed
```

`reset` semantics: `since > last` means the client holds a cursor from a previous server run; `since + 1 < first` means records were evicted from the ring. In both cases the full ring is replayed and the client is told via a `reset` frame.

### 2.4 `OutputLogHandler`

```python
_CHANNEL_PREFIXES = (
    ("deskai.bridge.git", "git"), ("deskai.bridge.ports", "ports"),
    ("deskai.bridge.terminal", "terminal"), ("deskai.server.terminal", "terminal"),
    ("deskai.diagnostics", "diagnostics"), ("deskai.bridge.diagnostics", "diagnostics"),
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
        self.setFormatter(logging.Formatter("%(message)s"))   # exc_info appended by Formatter.format()

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(self._local, "busy", False) or record.name.startswith("deskai.server.output_hub"):
            return                                             # re-entrancy guard: the hub must never log about itself
        self._local.busy = True
        try:
            level = ("error" if record.levelno >= logging.ERROR else "warn" if record.levelno >= logging.WARNING
                     else "info" if record.levelno >= logging.INFO else "debug")
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
        root.setLevel(logging.DEBUG)                           # the UI filters by level; the logger must not pre-filter
    return handler

def uninstall_output_logging(handler: OutputLogHandler) -> None:
    logging.getLogger("deskai").removeHandler(handler)
```

`propagate` is left unchanged so existing console/stderr behaviour is unchanged.

---

## 3. Backend: `server/supervisor.py`

### 3.1 Authorisation helper (refactor, behaviour unchanged)

The Host / Origin / cookie checks are currently copied into `/ws` and `/ws/terminal/{id}`. Extract:

```python
async def _authorize_ws(self, ws: WebSocket) -> str | None:
    """Accepts, then applies Host -> Origin -> cookie checks. Returns the session cookie or None (socket already closed)."""
    await ws.accept()                                          # accept first so 44xx close codes reach the client
    if not is_valid_loopback_host(ws.headers.get("host", ""), self.port):
        await ws.close(code=4403, reason="Invalid Host"); return None
    if ws.headers.get("origin") != f"http://127.0.0.1:{self.port}":
        await ws.close(code=4403, reason="Cross-Origin WebSocket Denied"); return None
    cookie = ws.cookies.get("deskai_session")
    if not self.security.is_valid_session(cookie):
        await ws.close(code=4401, reason="Unauthorized Session"); return None
    return cookie
```

Existing endpoints call it; the existing close-code tests must pass unchanged (guard against regressions with a test per endpoint).

### 3.2 Hub lifecycle

* `__init__`: `self.output_hub = OutputHub()`; `self.output_hub.register_secret(self.security.launch_token)`. In `redeem_token` after a session id is minted: `self.output_hub.register_secret(session_id)`.
* `start()`: `self._log_handler = install_output_logging(self.output_hub)`; `logger.info("Supervisor active on loopback port %s. Ready for tasks.", self.port)` (never log the token or the redeem URL).
* `stop()`: `uninstall_output_logging(self._log_handler)` before closing sockets.
* `self._output_sockets: dict[str, int]` (per-session counter, **separate** from `security.session_sockets` so the `/ws` cap of 4 and terminal accounting are unaffected).

### 3.3 `/ws/output` endpoint

```python
@self.app.websocket("/ws/output")
async def output_websocket_endpoint(ws: WebSocket):
    cookie = await self._authorize_ws(ws)
    if cookie is None:
        return
    if self._output_sockets.get(cookie, 0) >= 2:
        await ws.close(code=4429, reason="Too Many Output Sockets"); return
    self._output_sockets[cookie] = self._output_sockets.get(cookie, 0) + 1

    try:
        since = max(0, int(ws.query_params.get("since", "0")))
    except ValueError:
        since = 0
    sub = _Subscriber(asyncio.get_running_loop())
    records, reset, first, last = self.output_hub.snapshot_and_subscribe(sub, since)
    try:
        await ws.send_text(json.dumps({"type": "hello", "firstSeq": first, "lastSeq": last, "ringSize": RING_SIZE}))
        if reset:
            await ws.send_text(json.dumps({"type": "reset", "firstSeq": first, "lastSeq": last}))
        for i in range(0, len(records), 200):                  # replay in chunks
            chunk = records[i:i + 200]
            await ws.send_text(json.dumps({"type": "batch", "records": [r.to_dict() for r in chunk],
                                           "lastSeq": chunk[-1].seq, "dropped": 0}))

        async def pump():
            while True:
                batch = [await sub.queue.get()]
                await asyncio.sleep(0.1)                       # batching window
                while len(batch) < 50 and not sub.queue.empty():
                    batch.append(sub.queue.get_nowait())
                self.output_hub.flush_pending()
                if _get_write_buffer_size(ws) > 1_000_000:     # slow consumer: drop and report
                    sub.dropped += len(batch); continue
                dropped, sub.dropped = sub.dropped, 0
                await ws.send_text(json.dumps({"type": "batch", "records": [r.to_dict() for r in batch],
                                               "lastSeq": batch[-1].seq, "dropped": dropped}))

        async def ticker():                                    # flush trailing repeat summaries while quiet
            while True:
                await asyncio.sleep(1.0); self.output_hub.flush_pending()

        async def receiver():                                  # inbound data is ignored; oversize closes with 1009
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect": return
                if len(msg.get("text") or "") > 1024 or len(msg.get("bytes") or b"") > 1024:
                    await ws.close(code=1009, reason="Message Too Big"); return

        tasks = [asyncio.create_task(c()) for c in (pump, ticker, receiver)]
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in tasks: t.cancel()
    except (WebSocketDisconnect, ConnectionResetError, RuntimeError):
        pass
    finally:
        self.output_hub.unsubscribe(sub)
        self._output_sockets[cookie] = max(0, self._output_sockets.get(cookie, 1) - 1)
```

`_get_write_buffer_size` is the existing helper in `supervisor.py` (reuse, do not duplicate). The CSP `connect-src ws://127.0.0.1:<port>` already permits the endpoint (same origin and port).

---

## 4. Frontend

### 4.1 `index.html` (replaces the V1 stub)

```html
<!-- Output Channel Panel -->
<div class="drawer-panel" id="outputPanel" role="tabpanel" aria-labelledby="tab-output" tabindex="0" hidden>
  <div class="output-toolbar" role="toolbar" aria-label="Output controls">
    <label class="output-field"><span class="output-field-label">Channel</span>
      <select id="outputChannelSelect" class="output-select" data-action="output-channel">
        <option value="all" selected>All</option><option value="system">System</option><option value="task">Task</option>
        <option value="git">Git</option><option value="ports">Ports</option><option value="terminal">Terminal</option>
        <option value="diagnostics">Diagnostics</option>
      </select></label>
    <label class="output-field"><span class="output-field-label">Level</span>
      <select id="outputLevelSelect" class="output-select" data-action="output-level">
        <option value="debug">Debug+</option><option value="info" selected>Info+</option>
        <option value="warn">Warnings+</option><option value="error">Errors</option>
      </select></label>
    <label class="sr-only" for="outputFilterInput">Filter output</label>
    <input type="text" id="outputFilterInput" class="output-filter-input" placeholder="Filter output" autocomplete="off" />
    <button type="button" class="icon-btn" data-action="output-time" aria-pressed="false" aria-label="Show timestamps" title="Show timestamps"></button>
    <button type="button" class="icon-btn" data-action="output-wrap" aria-pressed="true" aria-label="Wrap long lines" title="Wrap long lines"></button>
    <button type="button" class="icon-btn" data-action="output-copy" aria-label="Copy visible output" title="Copy visible output"></button>
    <button type="button" class="icon-btn" data-action="output-save" aria-label="Save output to file" title="Save output to file"></button>
    <button type="button" class="icon-btn" data-action="output-clear" aria-label="Clear output" title="Clear output"></button>
  </div>
  <div class="output-status" id="outputStatus" role="status" hidden></div>
  <div class="terminal-view log-view" id="channelOutput" role="log" aria-label="Output log" aria-live="off">
    <div class="log-banner">[DeskAI System] Supervisor active on loopback. Ready for tasks.</div>
  </div>
  <button type="button" class="output-jump" id="outputJump" data-action="output-jump" hidden>Jump to latest</button>
</div>
```

Rules: toolbar icons use `createSvgIcon()` from `icons.js` (no emoji); the panel keeps `tabindex="0"` (the single keyboard stop, consistent with the other panels and existing tests); the `.drawer-content` element **remains the shared scroll container** (required by `test_log_view_line_cap_and_scroll_preservation`), so the toolbar is `position: sticky; top: 0` and `Jump to latest` is `position: sticky; bottom`.

### 4.2 `output/client.js`

```javascript
const CHANNELS = new Set(["system", "task", "git", "ports", "terminal", "diagnostics"]);
const LEVELS = new Set(["debug", "info", "warn", "error"]);

export class OutputClient {
  constructor({ onRecords, onReset, onState, onDropped }) {
    Object.assign(this, { onRecords, onReset, onState, onDropped });
    this.lastSeq = 0; this.attempts = 0; this.socket = null; this.timer = 0; this.closedByUser = false;
  }
  connect() {
    this.closedByUser = false; this._state("connecting");
    this.socket = new WebSocket(`ws://${location.host}/ws/output?since=${this.lastSeq}`);
    this.socket.onopen = () => { this.attempts = 0; this._state("streaming"); };
    this.socket.onmessage = (ev) => this._onMessage(ev.data);
    this.socket.onclose = (ev) => {
      if (this.closedByUser) return;
      if ([4401, 4403, 4429].includes(ev.code)) { this._state("unavailable"); return; }
      this._state("reconnecting");
      const delay = Math.min(1000 * Math.pow(1.5, ++this.attempts), 15000) * (0.75 + Math.random() * 0.5);   // same shape as ws.js
      this.timer = setTimeout(() => this.connect(), delay);
    };
  }
  retry() { clearTimeout(this.timer); this.attempts = 0; this.connect(); }
  close() { this.closedByUser = true; clearTimeout(this.timer); if (this.socket) this.socket.close(); }

  _onMessage(raw) {
    let msg; try { msg = JSON.parse(raw); } catch { return; }
    if (!msg || typeof msg.type !== "string") return;
    if (msg.type === "reset") {
      const restarted = Number.isFinite(msg.lastSeq) && msg.lastSeq < this.lastSeq;     // new server run
      const missed = restarted ? 0 : Math.max(0, (msg.firstSeq || 1) - 1 - this.lastSeq);
      if (restarted) this.lastSeq = 0;
      this.onReset({ restarted, missed });
    } else if (msg.type === "batch" && Array.isArray(msg.records)) {
      const fresh = [];
      for (const r of msg.records.slice(0, 500)) {
        if (!r || !Number.isInteger(r.seq) || r.seq <= this.lastSeq) continue;           // dedupe by cursor
        if (!CHANNELS.has(r.channel) || !LEVELS.has(r.level) || typeof r.text !== "string") continue;
        fresh.push({ seq: r.seq, ts: Number(r.ts) || Date.now(), channel: r.channel, level: r.level, text: r.text.slice(0, 4096) });
        this.lastSeq = r.seq;
      }
      if (fresh.length) this.onRecords(fresh);
      if (msg.dropped > 0) this.onDropped(msg.dropped);
    }
  }
  _state(s) { this.state = s; this.onState(s); }
}
```

Every field from the socket is validated; nothing is interpreted as markup.

### 4.3 `LogView` record mode (`js/terminal.js`)

Keep the existing class and constants; add:

```javascript
const MAX_RECORDS = 5000;
const LEVEL_RANK = { debug: 0, info: 1, warn: 2, error: 3 };
const LEVEL_TAG = { debug: "DEBUG", info: "INFO", warn: "WARN", error: "ERROR" };

// inside class LogView
this.records = [];                                   // record mode source of truth (max MAX_RECORDS)
this.queueRecords = [];                              // pending filtered records, drained by _flush()
this.filter = { channel: "all", minLevel: "info", text: "" };
this.options = { wrap: true, timestamps: false };

writeRecords(records) {                              // called by OutputManager
  this.records.push(...records);
  if (this.records.length > MAX_RECORDS) this.records.splice(0, this.records.length - MAX_RECORDS);
  this.queueRecords.push(...records.filter((r) => this.matches(r)));
  if (!this.rafId) this.rafId = requestAnimationFrame(() => this._flush());
}
matches(r) {
  const f = this.filter;
  if (f.channel !== "all" && r.channel !== f.channel) return false;
  if (LEVEL_RANK[r.level] < LEVEL_RANK[f.minLevel]) return false;
  return !f.text || (r.text + " " + r.channel).toLowerCase().includes(f.text);
}
renderRecord(r) {
  const row = document.createElement("div");
  row.className = `log-line log-${r.level}`;
  row.dataset.seq = String(r.seq); row.dataset.channel = r.channel; row.dataset.level = r.level;
  const time = document.createElement("span"); time.className = "log-time"; time.textContent = formatTime(r.ts);
  const chan = document.createElement("span"); chan.className = "log-channel"; chan.textContent = r.channel;
  const tag = document.createElement("span"); tag.className = "log-level-tag"; tag.textContent = LEVEL_TAG[r.level];
  const text = document.createElement("span"); text.className = "log-text";
  formatLogText(text, r.text); // splits plain text and clickable .log-link elements without innerHTML
  row.append(time, chan, tag, text);
  return row;
}
renderAll() {                                        // after a filter change: rebuild from this.records, one DOM write
  const frag = document.createDocumentFragment();
  for (const r of this.records) if (this.matches(r)) frag.append(this.renderRecord(r));
  const banner = this.el.querySelector(".log-banner");
  this.el.replaceChildren(...(banner ? [banner] : []), frag);
}
setOptions({ wrap, timestamps }) {                   // toggles classes on the container, no re-render
  this.el.classList.toggle("log-nowrap", !wrap);
  this.el.classList.toggle("log-show-time", !!timestamps);
}
```

Required adjustments to existing methods:
* `_flush()` also drains `this.queueRecords` (appending `renderRecord()` nodes) and trims record-mode rows above `MAX_RECORDS`; the legacy `write()` path (`<span>`, 10,000-line cap, ANSI strip) is untouched so existing tests keep passing.
* `clear()` empties `this.records`, `queueRecords`, removes everything **except** `.log-banner`, and resets the scroll position. `TC-OUT-05` and the legacy tests remain valid.
* `formatTime(ts)` uses `Intl.DateTimeFormat(undefined, {hour12:false, hour:"2-digit", minute:"2-digit", second:"2-digit"})` plus zero-padded milliseconds.
* The scroll container stays `.drawer-content` (existing getter). `pinned` and the 40 px threshold are unchanged. When `pinned` turns false the manager shows `#outputJump`; `Jump to latest` or `End` sets `pinned = true` and scrolls.

### 4.4 `output/index.js` (`OutputManager`)

| Responsibility | Behaviour |
| :--- | :--- |
| Wiring | `client = new OutputClient({...})`, `view = window.DeskAILogView`; `connect()` on app start (the stream runs even while the tab is hidden so nothing is lost) |
| Records | `onRecords(rs)`: `view.writeRecords(rs)`; if Output tab is not active, increment unread counters for warn/error and update the tab indicator; if active, debounced announcer |
| Reset | `onReset({restarted, missed})`: restarted -> `view.clear()` plus status note; else append a local notice record `N earlier lines were discarded` |
| Dropped | `onDropped(n)`: local notice record `N lines were dropped (slow display)` |
| State | updates `#outputStatus` (`Reconnecting…`, `Output stream unavailable` + `Retry` button, hidden when streaming) |
| Filters | `output-channel`, `output-level` change events and input on the filter text (debounce 150 ms, lower-cased) call `view.filter = ...; view.renderAll()` |
| Toggles | `output-time`, `output-wrap` flip `aria-pressed`, call `view.setOptions()` |
| Copy | joins visible rows (`HH:mm:ss.SSS [channel] [LEVEL] text`) and calls `NativeBridge.clipboardWrite(text)` (fallback `navigator.clipboard.writeText`); announces `Copied N lines` |
| Save / Export | `saveLog()` joins visible rows and creates an instant Blob download (`deskai-output-<timestamp>.log`); announces `Saved N lines to <filename>` |
| Code Navigation | `navigateToFile(file, line, col)` resolves path via `store.state.workspace.rootPath` and jumps to `EditorManager.openAt(fullPath, line, col)` |
| Channel Badges | `_updateChannelSelectBadges()` tracks unread record counts per channel in `#outputChannelSelect` (e.g. `Git (2)`) and applies `.has-unread` class |
| Clear | `view.clear()`, announces `Output cleared`; the server ring is untouched (a reload replays it) |
| Local logging API | `window.DeskAIOutput.log(channel, level, text)` pushes a client-only record (negative `seq`, never sent to the server) for frontend events |
| Tab indicator | `#tab-output` gets a `<span class="tab-badge">` with `.has-errors` or `.has-warnings`; `aria-label` becomes `Output, 2 new errors`; cleared in `onShow()` |
| Announcer | single debounced (1000 ms) call to `announce()` (exported from `terminal.js`): `2 new errors, 1 warning in Output` |
| Prefs (P2) | `localStorage` keys `deskai.output.prefs` (`channel`, `level`, `wrap`, `timestamps`), wrapped in try/catch, panel works without it |

### 4.5 `events.js`

In `case "drawer-tab"` add `if (target === "output" && window.DeskAIOutput) window.DeskAIOutput.onShow();`. Add cases `output-time`, `output-wrap`, `output-copy`, `output-save`, `output-clear`, `output-jump`, `output-retry`, `output-nav`. Select and input events are bound directly in `OutputManager` (they are `change`/`input`, not clicks). Keyboard on the panel: `End` -> jump to latest; `Ctrl+A` -> select only the log contents (`Range.selectNodeContents(#channelOutput)`); `Esc` -> focus `#tab-output`; Enter/Space on `.log-link` -> dispatch click for `output-nav`.

---

## 5. CSS (tokens only)

```css
.output-toolbar { position: sticky; top: 0; z-index: 1; display: flex; align-items: center; gap: var(--space-2);
  padding: var(--space-1-5) var(--space-3); background: var(--bg-header); border-bottom: 1px solid var(--border-subtle); }
.output-field { display: inline-flex; align-items: center; gap: var(--space-1-5); font-size: var(--text-xs); color: var(--text-secondary); }
.output-select, .output-filter-input { min-height: 28px; font: inherit; font-size: var(--text-xs); color: var(--text-primary);
  background: var(--bg-surface); border: 1px solid var(--border-input); border-radius: var(--radius-sm); }
#outputChannelSelect.has-unread { border-color: var(--color-info); }
.log-link { color: var(--color-info); text-decoration: underline; text-underline-offset: 2px; cursor: pointer; border-radius: var(--radius-sm); padding: 0 2px; display: inline; }
.log-link:hover { color: var(--color-primary); text-decoration-thickness: 2px; }
.log-link:focus-visible { outline: 2px solid var(--border-focus); outline-offset: 1px; }
.output-select, .output-filter-input { min-height: 28px; font: inherit; font-size: var(--text-xs); color: var(--text-primary);
  background: var(--bg-surface); border: 1px solid var(--border-input); border-radius: var(--radius-sm); }
.output-filter-input { flex: 1; min-width: 80px; }
.output-status { padding: var(--space-1-5) var(--space-3); font-size: var(--text-xs); color: var(--text-secondary); }
.log-view { padding: var(--space-2) var(--space-3); }
.log-banner { color: var(--text-muted); margin-bottom: var(--space-1); }
.log-line { display: grid; grid-template-columns: auto auto auto 1fr; column-gap: var(--space-2); content-visibility: auto;
  contain-intrinsic-size: auto 1.5em; white-space: pre-wrap; overflow-wrap: anywhere; }
.log-time { display: none; color: var(--text-muted); }
.log-show-time .log-time { display: inline; }
.log-channel { color: var(--text-muted); min-width: 7ch; }
.log-level-tag { display: none; font-weight: 600; }                       /* visible text tag for warn/error only */
.log-warn .log-level-tag, .log-error .log-level-tag { display: inline; }
.log-error .log-level-tag, .log-error .log-text { color: var(--color-danger); }
.log-warn .log-level-tag, .log-warn .log-text { color: var(--color-warning); }
.log-info .log-text { color: var(--text-secondary); }
.log-debug .log-text { color: var(--text-muted); }
.log-nowrap .log-line { white-space: pre; overflow-x: auto; }
.output-jump { position: sticky; bottom: var(--space-2); float: right; margin-right: var(--space-3); min-height: 28px; padding: 0 var(--space-3);
  border: 1px solid var(--border-focus); border-radius: var(--radius-sm); background: var(--bg-card); color: var(--text-primary); font: inherit; font-size: var(--text-xs); }
.output-toolbar :focus-visible, .output-jump:focus-visible { outline: 2px solid var(--border-focus); outline-offset: 1px; }
@media (prefers-reduced-motion: reduce) { .log-view { scroll-behavior: auto; } }
```

Because the legacy `write()` path renders `<span class="log-error">` etc. directly, also define the level classes for bare spans (`span.log-error { color: var(--color-danger); }` and so on) so the existing `LogView` API gets styling too.

Add contrast pairs to `tools/check_contrast.py`: `color-danger`, `color-warning`, `text-secondary`, `text-muted` against the panel background (`bg-app` or `bg-header`, whichever the panel uses), 4.5:1, both themes.

Layout stability: the toolbar has a fixed height, the status line is `hidden` when not needed and is placed **below** the toolbar (it pushes only the log, not the toolbar); `Jump to latest` is sticky/floating so showing it moves nothing.

---

## 6. Accessibility Contract (testable)

| Requirement | Implementation | Test |
| :--- | :--- | :--- |
| Tab semantics unchanged | `role="tab"`, `aria-controls="outputPanel"` | TC-OUT-07 |
| Log region | `#channelOutput` `role="log"`, `aria-live="off"`, `aria-label="Output log"` | TC-OUT-36 |
| No per-line announcements | live region is off; only the debounced summary | TC-OUT-37 |
| Level not colour-only | `WARN` / `ERROR` text tag visible | TC-OUT-38 |
| Toolbar labelled | every control has an accessible name; toggles use `aria-pressed` | TC-OUT-39 |
| Keyboard | End, Ctrl+A (log only), Esc | TC-OUT-40 |
| Tab indicator name | `Output, N new errors` | TC-OUT-41 |
| Targets / size | controls >= 28 px, text >= 12 px | size scan |
| Contrast, both themes | pairs in `check_contrast.py` | CI lint job |
| Reduced motion | no smooth scrolling | TC-OUT-42 |

---

## 7. Edge Cases

| Case | Expected behaviour |
| :--- | :--- |
| Log storm (10,000 identical lines/s) | Coalesced to one record plus a summary record; DOM stays bounded |
| Log storm of distinct lines | Ring evicts oldest; subscriber queue drops oldest and reports `dropped` |
| Client reconnects after short drop | `?since=lastSeq` replays only missing records, no duplicates |
| Client reconnects after a long drop | Ring evicted -> `reset` frame -> notice `N earlier lines were discarded` |
| Server restarted while page open | Client `lastSeq` > server `lastSeq` -> `reset` with `restarted` -> view cleared, cursor reset |
| Record text is `<img src=x onerror=alert(1)>` | Rendered as text; no element created |
| Record text contains ANSI / OSC 8 hyperlink | Stripped on the server and in the legacy path |
| Record text contains the launch token or a session id | `[REDACTED]` |
| 1 MB single message | Truncated to 4096 chars / 40 lines with `... [truncated]` |
| Message tries to forge `[ERROR]` | Level/channel come from fields only; text stays text |
| Hidden Output tab | Records stored; rendering deferred, unread counters updated |
| `/ws/output` auth failure (4401/4403) or cap (4429) | `Unavailable` state with `Retry`; local client logs still shown |
| Handler invoked recursively (logging inside the hub) | Re-entrancy guard drops it |
| Loop closed during shutdown | `RuntimeError` swallowed in `_publish` |
| Browser test without a server socket | Client state `unavailable`/`reconnecting`; no uncaught errors |
| Filter hides everything | Show `.output-empty` text `No output matches the current filters` (role status, polite) |

---

## 8. Backward Compatibility

* `#outputPanel`, `#channelOutput`, `.terminal-view`, the banner text and `aria-controls` linkage are unchanged: **TC-OUT-01 to TC-OUT-07** keep passing (TC-OUT-06 still sees `var(--font-mono)` / `var(--text-xs)` on `.terminal-view`).
* `window.DeskAILogView.constructor` and `write()`, `clear()`, `lineCount`, `pinned` behave as before (the existing scroll/cap/ANSI tests are not modified).
* Fix the doc/code drift: legacy raw-write cap stays 10,000 lines; record mode is 5,000 records.

---

## 9. Implementation Order & Definition of Done

1. `output_hub.py` (model, sanitiser, redaction, hub, handler) + unit tests.
2. `_authorize_ws()` refactor with regression tests for the existing endpoints, then `/ws/output` + endpoint tests.
3. `OutputClient` + `LogView` record mode + markup/CSS + `OutputManager` + contrast tool update.
4. Toolbar actions, announcer, tab indicator, keyboard.
5. A11y, resilience (reconnect/reset/storm) and E2E tests against the **real** `DesktopServer`.
6. P2 / P3 items as separate commits.

**Definition of Done:** black (`--line-length 120`) and flake8 clean; `python -m unittest discover -s tests` green on Ubuntu and Windows x 3.11/3.12; no `innerHTML` anywhere in `static/js` (the existing hygiene test passes); no raw colours outside `tokens.css`; `tools/check_contrast.py` passes; screenshots at 900x600 and 1440x900 in dark and light themes; existing TC-OUT and `LogView` tests unchanged and green.

---

## 10. Test Plan & Traceability Matrix

### 10.1 Hub unit tests (`tests/test_output_hub.py`)

| ID | Target | Assertion |
| :--- | :--- | :--- |
| TC-OUT-08 | Sanitiser | ANSI/OSC and control chars stripped; `\n` and `\t` kept |
| TC-OUT-09 | Truncation | 10,000-char and 100-line messages capped with `... [truncated]` |
| TC-OUT-10 | Redaction patterns | `Authorization: Bearer abc`, `token=xyz`, `sk-...`, `ghp_...`, JWT, `/auth/redeem?token=...` all redacted |
| TC-OUT-11 | Registered secrets | launch token and session id values replaced even inside other text |
| TC-OUT-12 | Ring and cursor | seq strictly monotonic from 1; ring keeps the last 2000; `snapshot_and_subscribe(since)` returns exactly seq > since |
| TC-OUT-13 | Reset semantics | evicted cursor and `since > last` both return `reset=True` |
| TC-OUT-14 | Coalescing | 1,000 identical emits -> 1 record + 1 summary (`Previous message repeated 999 more times`); `flush_pending()` emits a trailing summary after the window |
| TC-OUT-15 | Thread safety | 8 threads x 5,000 emits: no exception, unique ordered seq, no lost records within ring size |
| TC-OUT-16 | Subscriber backpressure | queue max reached -> drop-oldest, `dropped` counted, producers never block (emit time bounded) |
| TC-OUT-17 | Handler mapping | logger names map to channels; levelno maps to levels; `exc_info` traceback included |
| TC-OUT-18 | Re-entrancy | a record emitted while the handler is busy is dropped, no recursion |
| TC-OUT-19 | Install/uninstall | handler removed on `stop()`; no duplicate handlers after restart |

### 10.2 Endpoint / security tests (`tests/test_output_ws.py`)

| ID | Target | Assertion |
| :--- | :--- | :--- |
| TC-OUT-20 | Missing / invalid cookie | close 4401 |
| TC-OUT-21 | Bad Origin / bad Host | close 4403 |
| TC-OUT-22 | Secret never on the wire | emit a log containing the launch token and a session id; frames contain `[REDACTED]` only |
| TC-OUT-23 | Socket cap | 3rd concurrent socket for a session -> 4429; `/ws` and terminal caps unaffected |
| TC-OUT-24 | Replay | connect with `since=N` receives exactly missing records, in order |
| TC-OUT-25 | Reset frame | evicted cursor -> `reset` then full replay |
| TC-OUT-26 | Oversize inbound | 2 KB inbound frame -> close 1009; normal inbound ignored |
| TC-OUT-27 | Batching | 200 rapid records arrive in batches of <= 50 within ~100 ms windows |
| TC-OUT-28 | Slow consumer | simulated full write buffer -> `dropped` reported, server memory bounded |
| TC-OUT-29 | Refactor safety | `/ws` and `/ws/terminal/{id}` still return 4403/4401/4404/4429 exactly as before the `_authorize_ws` extraction |
| TC-OUT-30 | Windows | with platform mocked/real, handler and endpoint tests pass unchanged |

### 10.3 Frontend / E2E (Playwright against the **real** `DesktopServer`, not `file://`)

| ID | Target | Assertion |
| :--- | :--- | :--- |
| TC-OUT-31 | Live stream | triggering a backend `logger.warning` appears in the panel within 1 s with `WARN` tag |
| TC-OUT-32 | Filters | channel, level and text filters show/hide the right rows; empty-filter message appears |
| TC-OUT-33 | Follow / Jump | pinned follows; scrolling up stops follow and shows `Jump to latest`; End/click restores |
| TC-OUT-34 | Clear / Copy | clear empties records but keeps the banner; copy writes the visible text (bridge mocked) |
| TC-OUT-35 | Reconnect | closing the socket client-side reconnects with the cursor; no duplicate rows, no gaps |
| TC-OUT-36 | Log region ARIA | `role="log"`, `aria-live="off"`, labelled |
| TC-OUT-37 | Announcer | a burst of errors yields one debounced summary, no per-line announcements |
| TC-OUT-38 | Level not colour-only | warn/error rows contain visible text tags |
| TC-OUT-39 | Toolbar a11y | all controls named, toggles have `aria-pressed`, targets >= 28 px |
| TC-OUT-40 | Keyboard | End, Ctrl+A (selects only log), Esc work |
| TC-OUT-41 | Tab indicator | unread errors update `aria-label` and clear on show |
| TC-OUT-42 | Reduced motion | no smooth scrolling under `prefers-reduced-motion` |
| TC-OUT-43 | DOM safety | `<img src=x onerror=...>` renders as text, no element created |
| TC-OUT-44 | Storm | 20,000 records in 2 s: DOM <= 5,000 rows, main thread stays responsive, no layout shift |
| TC-OUT-45 | Layout | no horizontal overflow at 900x600; toolbar does not shift when status/jump appear |
| TC-OUT-46 | Themes | contrast pairs pass; screenshots rendered in dark and light |
| TC-OUT-47 | Static scan | no `innerHTML` / `outerHTML` / `insertAdjacentHTML` / `document.write` in `static/js/output/*` and `LogView` |
| TC-OUT-48 | Server restart simulation | cursor ahead of server -> view cleared with notice, new records shown |
| TC-OUT-49 | Clickable file:line links | file references in log text render as accessible `.log-link` jumping to `EditorManager.openAt` |
| TC-OUT-50 | Save / Export log | `output-save` button in toolbar exports visible log lines as `.log` file |
| TC-OUT-51 | Channel unread badges | inactive channels track unread counts in `#outputChannelSelect` (e.g. `Git (2)`) and toggle `.has-unread` |

### 10.4 Existing tests retained

TC-OUT-01 to TC-OUT-07 and the `LogView` line-cap, scroll-preservation and ANSI/OSC-stripping tests in `tests/test_bottom_drawer_behavior.py` remain unchanged.
