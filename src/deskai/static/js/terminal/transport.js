/**
 * Dedicated WebSocket Transport for Interactive Terminal.
 * Handles /ws/terminal/{sessionId} connection, flow control, binary chunks, and reconnection.
 */

function jsonSafeParse(str) {
  try {
    return JSON.parse(str);
  } catch (e) {
    return null;
  }
}

export class TerminalTransport {
  constructor(callbacks) {
    this.callbacks = callbacks;
    this.ws = null;
    this.reconnectAttempts = 0;
    this.lastCloseCode = 1006;
    this.encoder = new TextEncoder();
  }

  connect(sessionId) {
    if (this.ws) {
      try {
        this.ws.close();
      } catch (err) {
        // Ignored
      }
      this.ws = null;
    }

    const host = window.location.host;
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocol}//${host}/ws/terminal/${sessionId}`;

    this.ws = new WebSocket(url);
    this.ws.binaryType = "arraybuffer";

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      if (this.callbacks.onOpen) this.callbacks.onOpen();
    };

    this.ws.onmessage = (event) => {
      if (typeof event.data === "string") {
        try {
          const frame = jsonSafeParse(event.data);
          if (frame && frame.type === "exit") {
            if (this.callbacks.onExit) this.callbacks.onExit(frame.code ?? 0);
          } else if (frame && frame.type === "error") {
            console.warn("[TerminalTransport] Error frame:", frame);
          }
        } catch (err) {
          // Ignored
        }
      } else if (event.data instanceof ArrayBuffer) {
        if (this.callbacks.onData) {
          this.callbacks.onData(new Uint8Array(event.data));
        }
      }
    };

    this.ws.onclose = (event) => {
      const code = event ? event.code : 1006;
      this.lastCloseCode = code;

      if (this.callbacks.isExited && this.callbacks.isExited()) {
        return;
      }

      if (code === 4429 && this.reconnectAttempts < 3) {
        this.reconnectAttempts++;
        setTimeout(() => {
          if (!this.callbacks.isExited || !this.callbacks.isExited()) {
            this.connect(sessionId);
          }
        }, 300);
        return;
      }

      if (this.callbacks.onClose) {
        this.callbacks.onClose(code);
      }
    };

    this.ws.onerror = (err) => {
      console.warn("[TerminalTransport] WebSocket error:", err);
    };
  }

  sendData(data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(typeof data === "string" ? this.encoder.encode(data) : data);
      return true;
    }
    return false;
  }

  sendResize(cols, rows) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "resize", cols, rows }));
    }
  }

  close() {
    if (this.ws) {
      try {
        this.ws.close();
      } catch (e) {
        // Ignored
      }
      this.ws = null;
    }
  }
}
