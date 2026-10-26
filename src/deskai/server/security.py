"""
DeskAI Security Store, Single-Use Token Redemption & CSP Generator.
"""
import secrets


class SessionSecurityManager:
    def __init__(self, port: int):
        self.port = port
        self.launch_token: str | None = secrets.token_urlsafe(32)
        self.active_sessions: set[str] = set()

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
        self.active_sessions.add(session_id)
        return session_id

    def is_valid_session(self, session_id: str | None) -> bool:
        """Checks if session cookie is recognized in active sessions."""
        if not session_id:
            return False
        return session_id in self.active_sessions

    def revoke_session(self, session_id: str):
        self.active_sessions.discard(session_id)

    def get_content_security_policy(self, style_nonce: str | None = None) -> str:
        """
        Generates strict exact-port Content Security Policy.
        Disallows wildcards (no ws://127.0.0.1:*).
        """
        style_rule = f"'self' 'nonce-{style_nonce}'" if style_nonce else "'self' 'unsafe-inline'"
        return (
            f"default-src 'self'; "
            f"connect-src 'self' ws://127.0.0.1:{self.port} http://127.0.0.1:{self.port}; "
            f"img-src 'self' data: blob:; "
            f"style-src {style_rule}; "
            f"font-src 'self' data:; "
            f"script-src 'self' 'unsafe-eval'; "
            f"object-src 'none'; "
            f"base-uri 'none'; "
            f"form-action 'none';"
        )
