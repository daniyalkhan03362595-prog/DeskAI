export class TokenStreamBuffer {
  constructor(targetElement) {
    this.target = targetElement;
    this.chunkQueue = [];
    this.accumulatedText = "";
    this.isScheduled = false;
    this.lastRenderTime = 0;
    this.renderIntervalMs = 100; // 10 Hz throttle
    this.trailingTimer = null;
    this.isUserScrolledUp = false;

    const container = this.target.parentElement;
    if (container) {
      container.addEventListener("scroll", () => {
        const distanceToBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
        this.isUserScrolledUp = distanceToBottom > 40;
      });
    }
  }

  append(chunk) {
    this.chunkQueue.push(chunk);
    this._scheduleFlush();
  }

  _scheduleFlush() {
    if (this.isScheduled) return;
    this.isScheduled = true;

    const now = performance.now();
    const elapsed = now - this.lastRenderTime;

    if (elapsed >= this.renderIntervalMs) {
      requestAnimationFrame(() => this._flush());
    } else {
      clearTimeout(this.trailingTimer);
      this.trailingTimer = setTimeout(() => {
        requestAnimationFrame(() => this._flush());
      }, this.renderIntervalMs - elapsed);
      this.isScheduled = false;
    }
  }

  _flush() {
    if (this.chunkQueue.length > 0) {
      this.accumulatedText += this.chunkQueue.join("");
      this.chunkQueue = [];
    }

    // Sanitize with DOMPurify
    if (window.DOMPurify && window.marked) {
      if (!window.__deskai_purify_hooked && typeof window.DOMPurify.addHook === "function") {
        window.DOMPurify.addHook("afterSanitizeAttributes", (node) => {
          if (node.tagName === "A") {
            node.setAttribute("rel", "noopener noreferrer");
            node.removeAttribute("target");
          }
          node.removeAttribute("class");
        });
        window.__deskai_purify_hooked = true;
      }

      const cleanHtml = window.DOMPurify.sanitize(window.marked.parse(this.accumulatedText), {
        ALLOWED_TAGS: [
          'p', 'br', 'strong', 'em', 'code', 'pre', 'ul', 'ol', 'li', 'span',
          'h1', 'h2', 'h3', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'blockquote', 'a'
        ],
        ALLOWED_ATTR: ['href'],
        ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto):)/i
      });
      this.target.innerHTML = cleanHtml;
    } else {
      // Safe fallback if vendor not loaded
      this.target.textContent = this.accumulatedText;
    }
    this.lastRenderTime = performance.now();
    this.isScheduled = false;

    if (!this.isUserScrolledUp && this.target.parentElement) {
      const container = this.target.parentElement;
      container.scrollTop = container.scrollHeight;
    }
  }

  complete() {
    clearTimeout(this.trailingTimer);
    this._flush();
    const announcer = document.getElementById("screenReaderAnnouncer");
    if (announcer) {
      announcer.textContent = "AI generation complete.";
    }
  }
}
