/**
 * DeskAI Output WebSocket Client
 * Connects to /ws/output?since=N, validates frames, manages cursor, and reconnects with jittered backoff.
 */

const CHANNELS = new Set(["system", "task", "git", "ports", "terminal", "diagnostics"]);
const LEVELS = new Set(["debug", "info", "warn", "error"]);

export class OutputClient {
  constructor({ onRecords, onReset, onState, onDropped }) {
    this.onRecords = onRecords;
    this.onReset = onReset;
    this.onState = onState;
    this.onDropped = onDropped;
    this.lastSeq = 0;
    this.attempts = 0;
    this.socket = null;
    this.timer = 0;
    this.closedByUser = false;
    this.state = "idle";
  }

  connect() {
    this.closedByUser = false;
    this._state("connecting");
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    this.socket = new WebSocket(`${protocol}//${location.host}/ws/output?since=${this.lastSeq}`);

    this.socket.onopen = () => {
      this.attempts = 0;
      this._state("streaming");
    };

    this.socket.onmessage = (ev) => this._onMessage(ev.data);

    this.socket.onclose = (ev) => {
      if (this.closedByUser) return;
      if ([4401, 4403, 4429].includes(ev.code)) {
        this._state("unavailable");
        return;
      }
      this._state("reconnecting");
      const delay = Math.min(1000 * Math.pow(1.5, ++this.attempts), 15000) * (0.75 + Math.random() * 0.5);
      this.timer = setTimeout(() => this.connect(), delay);
    };
  }

  retry() {
    clearTimeout(this.timer);
    this.attempts = 0;
    this.connect();
  }

  close() {
    this.closedByUser = true;
    clearTimeout(this.timer);
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
  }

  _onMessage(raw) {
    let msg;
    try {
      msg = JSON.parse(raw);
    } catch {
      return;
    }
    if (!msg || typeof msg.type !== "string") return;

    if (msg.type === "reset") {
      const restarted = Number.isFinite(msg.lastSeq) && msg.lastSeq < this.lastSeq;
      const missed = restarted ? 0 : Math.max(0, (msg.firstSeq || 1) - 1 - this.lastSeq);
      if (restarted) this.lastSeq = 0;
      if (this.onReset) this.onReset({ restarted, missed });
    } else if (msg.type === "batch" && Array.isArray(msg.records)) {
      const fresh = [];
      for (const r of msg.records.slice(0, 500)) {
        if (!r || !Number.isInteger(r.seq) || r.seq <= this.lastSeq) continue;
        if (!CHANNELS.has(r.channel) || !LEVELS.has(r.level) || typeof r.text !== "string") continue;
        fresh.push({
          seq: r.seq,
          ts: Number(r.ts) || Date.now(),
          channel: r.channel,
          level: r.level,
          text: r.text.slice(0, 4096),
        });
        this.lastSeq = r.seq;
      }
      if (fresh.length && this.onRecords) this.onRecords(fresh);
      if (msg.dropped > 0 && this.onDropped) this.onDropped(msg.dropped);
    }
  }

  _state(s) {
    this.state = s;
    if (this.onState) this.onState(s);
  }
}
