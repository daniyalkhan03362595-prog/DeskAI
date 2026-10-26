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
    this.resyncInFlight = false;
    this.lastResyncTime = 0;
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

  _showBanner(message, isFatal = false) {
    if (typeof document === "undefined") return;
    let banner = document.getElementById("connectionBanner");
    if (!banner) {
      banner = document.createElement("div");
      banner.id = "connectionBanner";
      banner.className = "connection-banner";
      banner.setAttribute("role", "alert");
      const appRoot = document.getElementById("appRoot") || document.body;
      const appHeader = document.getElementById("appHeader");
      if (appHeader && appHeader.nextSibling) {
        appRoot.insertBefore(banner, appHeader.nextSibling);
      } else if (appRoot) {
        appRoot.prepend(banner);
      }
    }
    if (banner) {
      banner.textContent = message;
      banner.className = isFatal ? "connection-banner fatal" : "connection-banner warning";
      banner.style.display = "block";
    }
  }

  _hideBanner() {
    if (typeof document === "undefined") return;
    const banner = document.getElementById("connectionBanner");
    if (banner) {
      banner.style.display = "none";
    }
  }

  connect() {
    if (this.isFatalClosed) return;

    this.socket = new WebSocket(this.url);

    this.socket.onopen = () => {
      console.log("[WS] Connected to Desktop Gateway.");
      this.reconnectAttempts = 0;
      this.consecutive1006 = 0;
      this.resyncInFlight = false;
      this.lastResyncTime = 0;
      this._hideBanner();

      // Reset sequence tracker on fresh connection before initial snapshot
      if (store && store.state && store.state.connection) {
        store.state.connection.lastSeq = 0;
        store.state.connection.isSocketConnected = true;
      }

      this._flushSafeQueue();
      this._requestSnapshotResync();
    };

    this.socket.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "server.snapshot") {
          // On snapshot, adopt server sequence directly without gap detection
          if (msg.seq !== undefined && store && store.state && store.state.connection) {
            store.state.connection.lastSeq = msg.seq;
          }
          this.resyncInFlight = false;
        } else if (msg.seq !== undefined && store && store.state && store.state.connection) {
          const currentLast = store.state.connection.lastSeq;
          const expected = currentLast + 1;
          if (currentLast > 0 && msg.seq !== expected) {
            console.warn(`[WS] Gap detected: got ${msg.seq}, expected ${expected}. Resyncing.`);
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
      if (store && store.state && store.state.connection) {
        store.state.connection.isSocketConnected = false;
      }
      this.resyncInFlight = false;

      // Code 4401/4403/1008: Explicit Security / Auth Rejection -> Fatal halt
      if (event.code === 4401 || event.code === 4403 || event.code === 1008) {
        this.isFatalClosed = true;
        console.error(`[WS] Fatal: Authentication rejected by server (Code ${event.code}).`);
        this._showBanner("Security validation failed. Please restart DeskAI.", true);
        return;
      }

      // Code 1006 or normal close: Do not treat server restarts as fatal.
      this._showBanner("Disconnected from supervisor. Reconnecting...");
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
    while (this.outboundQueue.length > 0 && this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(this.outboundQueue.shift()));
    }
  }

  _requestSnapshotResync() {
    if (this.resyncInFlight) return;
    const now = Date.now();
    if (now - this.lastResyncTime < 2000) {
      // Rate-limited: at most 1 resync per 2 seconds
      return;
    }
    this.resyncInFlight = true;
    this.lastResyncTime = now;
    const lastSeq = store && store.state && store.state.connection ? store.state.connection.lastSeq : 0;
    this.send("client.resync", { lastSeq });
  }

  _scheduleReconnect() {
    this.reconnectAttempts++;
    // Jittered exponential backoff
    const baseDelay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), this.maxReconnectDelay);
    const jitter = Math.random() * 500;
    const delay = baseDelay + jitter;
    setTimeout(() => this.connect(), delay);
  }
}
