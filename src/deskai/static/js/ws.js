import { store } from "./state.js";

export class WebSocketClient {
  constructor(endpointUrl) {
    this.url = endpointUrl;   // Cookies carry session auth automatically
    this.socket = null;
    this.reconnectAttempts = 0;
    this.maxReconnectDelay = 10000;
    this.consecutive1006 = 0;
    this.handlers = new Map();
    this.outboundQueue = [];
    this.isFatalClosed = false;
  }

  on(actionType, handler) {
    if (!this.handlers.has(actionType)) {
      this.handlers.set(actionType, []);
    }
    this.handlers.get(actionType).push(handler);
  }

  _routeMessage(msg) {
    if (!msg || !msg.type) return;
    const handlers = this.handlers.get(msg.type);
    if (handlers) {
      for (const h of handlers) {
        try {
          h(msg.payload || msg);
        } catch (err) {
          console.error(`[WS] Handler error on ${msg.type}:`, err);
        }
      }
    }
  }

  connect() {
    if (this.isFatalClosed) return;

    this.socket = new WebSocket(this.url);

    this.socket.onopen = () => {
      console.log("[WS] Connected to Desktop Gateway.");
      this.reconnectAttempts = 0;
      this.consecutive1006 = 0;
      store.state.connection.isSocketConnected = true;
      this._flushSafeQueue();
      this._requestSnapshotResync();
    };

    this.socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.seq !== undefined) {
          const expected = store.state.connection.lastSeq + 1;
          if (store.state.connection.lastSeq > 0 && msg.seq !== expected) {
            console.warn(`[WS] Gap detected: got ${msg.seq}, expected ${expected}. Resyncing.`);
            store.state.connection.lastSeq = msg.seq;
            this._requestSnapshotResync();
            return;
          }
          store.state.connection.lastSeq = msg.seq;
        }
        this._routeMessage(msg);
      } catch (e) {
        console.error("[WS] Parse error:", e);
      }
    };

    this.socket.onclose = (event) => {
      store.state.connection.isSocketConnected = false;
      
      // Code 4401/4403/1008: Explicit Security Rejection -> Fatal halt
      if (event.code === 4401 || event.code === 4403 || event.code === 1008) {
        this.isFatalClosed = true;
        console.error(`[WS] Fatal: Authentication rejected by server (Code ${event.code}).`);
        alert("DeskAI security validation failed. Please restart application.");
        return;
      }

      // Code 1006: Handshake rejected or aborted
      if (event.code === 1006) {
        this.consecutive1006++;
        if (this.consecutive1006 >= 3) {
          this.isFatalClosed = true;
          console.error("[WS] Fatal: Repeated handshake failures (Code 1006). Halting.");
          return;
        }
      }

      this._scheduleReconnect();
    };
  }

  // Returns boolean status so caller knows if message was sent
  send(type, payload = {}, options = { replayable: false }) {
    const frame = {
      type,
      idempotency_key: crypto.randomUUID(),
      payload,
      timestamp: Date.now()
    };

    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(frame));
      return true;
    } else if (options.replayable) {
      this.outboundQueue.push(frame);
      return false;
    } else {
      console.warn(`[WS] Non-replayable action '${type}' dropped during disconnect.`);
      return false;
    }
  }

  _flushSafeQueue() {
    while (this.outboundQueue.length > 0 && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(this.outboundQueue.shift()));
    }
  }

  _requestSnapshotResync() {
    this.send("client.resync", { lastSeq: store.state.connection.lastSeq });
  }

  _scheduleReconnect() {
    this.reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), this.maxReconnectDelay);
    setTimeout(() => this.connect(), delay);
  }
}
