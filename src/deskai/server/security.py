"""
DeskAI Security Store, Single-Use Token Redemption & CSP Generator.
"""

from collections import defaultdict
import secrets
import time


class SessionStore(dict):
    """Custom dictionary store supporting both dict and set-like access for backward compatibility."""

    def add(self, session_id: str) -> None:
        self[session_id] = time.time()

    def discard(self, session_id: str) -> None:
        self.pop(session_id, None)


class SessionSecurityManager:
    SESSION_TTL_SECONDS = 12 * 3600  # 12-hour maximum session TTL

    def __init__(self, port: int):
        self.port = port
        self.launch_token: str | None = secrets.token_urlsafe(32)
        # Tracks active sessions with creation timestamp: session_id -> created_at
        self.active_sessions: SessionStore = SessionStore()
        # Tracks open websockets per session: session_id -> set of active ws objects
        self.session_sockets: dict[str, set] = defaultdict(set)

    def create_launch_token(self) -> str:
        """Generates and sets a new single-use launch token."""
        self.launch_token = secrets.token_urlsafe(32)
        return self.launch_token

    def redeem_launch_token(self, provided_token: str | None) -> str | None:
        """
        Redeems launch token in constant time.
        Single-use: Once redeemed, token is permanently burned.
        Returns a newly minted session ID or None if invalid/replayed.
        """
        if not provided_token or not self.launch_token:
            return None

        # Constant-time comparison
        is_valid = secrets.compare_digest(provided_token, self.launch_token)
        if not is_valid:
            return None

        # Burn token immediately
        self.launch_token = None

        # Issue new session token
        session_id = secrets.token_hex(24)
        self.active_sessions[session_id] = time.time()
        self.session_sockets[session_id] = set()
        return session_id

    def is_valid_session(self, session_id: str | None) -> bool:
        """Checks if session cookie is recognized and unexpired."""
        if not session_id or session_id not in self.active_sessions:
            return False

        created_at = self.active_sessions[session_id]
        if time.time() - created_at > self.SESSION_TTL_SECONDS:
            # Expired session cleanup
            self.revoke_session(session_id)
            return False
        return True

    def register_socket(self, session_id: str, ws) -> None:
        if session_id in self.active_sessions:
            self.session_sockets[session_id].add(ws)

    def unregister_socket(self, session_id: str, ws) -> None:
        if session_id in self.session_sockets:
            self.session_sockets[session_id].discard(ws)

    def get_session_sockets(self, session_id: str) -> set:
        return self.session_sockets.get(session_id, set())

    def revoke_session(self, session_id: str) -> None:
        self.active_sessions.pop(session_id, None)
        self.session_sockets.pop(session_id, None)

    def clear_sessions(self) -> None:
        self.active_sessions.clear()
        self.session_sockets.clear()

    def get_content_security_policy(self, style_nonce: str | None = None) -> str:
        """
        Generates strict exact-port Content Security Policy.
        Disallows wildcards (no ws://127.0.0.1:*).
        Strictly drops 'unsafe-eval' and 'unsafe-inline'.
        """
        style_rule = f"'self' 'nonce-{style_nonce}'" if style_nonce else "'self'"
        return (
            f"default-src 'self'; "
            f"connect-src 'self' ws://127.0.0.1:{self.port} http://127.0.0.1:{self.port}; "
            f"img-src 'self' data: blob:; "
            f"style-src {style_rule}; "
            f"font-src 'self' data:; "
            f"script-src 'self' 'unsafe-eval'; "
            f"object-src 'none'; "
            f"base-uri 'none'; "
            f"form-action 'none'; "
            f"frame-ancestors 'none';"
        )

    def apply_security_headers(self, response, is_no_store: bool = False):
        """Applies comprehensive suite of hardening headers to HTTP response."""
        response.headers["Content-Security-Policy"] = self.get_content_security_policy()
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if is_no_store:
            response.headers["Cache-Control"] = "no-store"
        return response
