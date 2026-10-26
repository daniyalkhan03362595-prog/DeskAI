"""
DesktopServer Implementation:
Pre-bound loopback socket, root static asset mounting, single-use token redemption,
and hardened WebSocket gateway.
"""
import json
import os
import threading
from pathlib import Path
import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles

from deskai.server.security import SessionSecurityManager
from deskai.utils.net import bind_ephemeral_loopback_socket, is_valid_loopback_host


class DesktopServer:
    def __init__(self, static_dir: str | Path | None = None):
        if static_dir is None:
            self.static_dir = Path(__file__).resolve().parent.parent / "static"
        else:
            self.static_dir = Path(static_dir)

        # 1. Ephemeral Port Allocation with Pre-Bound Socket
        self.listen_socket, self.port = bind_ephemeral_loopback_socket()
        self.security = SessionSecurityManager(self.port)
        self.launch_token = self.security.launch_token

        # 2. FastAPI Application (Disabled OpenAPI schema leakage)
        self.app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
        self.uvicorn_server: uvicorn.Server | None = None
        self.server_thread: threading.Thread | None = None

        self._configure_routes_and_guards()

    def _configure_routes_and_guards(self):
        # 1. Single-Use Token Redemption Route
        @self.app.get("/auth/redeem")
        async def redeem_token(request: Request, token: str = ""):
            # Host Verification
            host = request.headers.get("host")
            if not is_valid_loopback_host(host, self.port):
                return Response(status_code=403, content="Invalid Host")

            session_id = self.security.redeem_launch_token(token)
            if not session_id:
                return Response(status_code=403, content="Invalid or Expired Launch Token")

            # Redirect to clean root URL with HttpOnly SameSite=Strict cookie
            response = RedirectResponse(url="/", status_code=303)
            response.set_cookie(
                key="deskai_session",
                value=session_id,
                httponly=True,
                samesite="strict",
                path="/"
            )
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Content-Security-Policy"] = self.security.get_content_security_policy()
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response

        # 2. HTTP Middleware (Host, Cookie & CSP Guards)
        @self.app.middleware("http")
        async def security_middleware(request: Request, call_next):
            path = request.url.path

            # Allowed unauthenticated endpoint
            if path == "/auth/redeem":
                return await call_next(request)

            # Host Header Check
            host = request.headers.get("host")
            if not is_valid_loopback_host(host, self.port):
                return Response(status_code=403, content="Forbidden: Host mismatch")

            # Session Cookie Check
            session_cookie = request.cookies.get("deskai_session")
            if not self.security.is_valid_session(session_cookie):
                return Response(status_code=401, content="Unauthorized: Valid session required")

            response = await call_next(request)

            # Strict Security Headers
            response.headers["Content-Security-Policy"] = self.security.get_content_security_policy()
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response

        # 3. Hardened WebSocket Endpoint (Accepted first, then authorized with 4403/4401)
        @self.app.websocket("/ws")
        async def websocket_endpoint(ws: WebSocket):
            await ws.accept()

            # A. Verify Host Header
            host = ws.headers.get("host", "")
            if not is_valid_loopback_host(host, self.port):
                await ws.close(code=4403, reason="Invalid Host")
                return

            # B. Verify Origin Header (Strict Match - Null Not Allowed)
            origin = ws.headers.get("origin")
            if origin != f"http://127.0.0.1:{self.port}":
                await ws.close(code=4403, reason="Cross-Origin WebSocket Denied")
                return

            # C. Verify Session Cookie
            cookie = ws.cookies.get("deskai_session")
            if not self.security.is_valid_session(cookie):
                await ws.close(code=4401, reason="Unauthorized Session")
                return

            # Frame Handling Loop with Malformed Frame & Size Guard
            try:
                while True:
                    raw_text = await ws.receive_text()

                    # 64 KB Message Cap
                    if len(raw_text) > 65536:
                        await ws.send_json({"type": "error", "code": "ERR_PAYLOAD_TOO_LARGE"})
                        continue

                    try:
                        data = json.loads(raw_text)
                    except json.JSONDecodeError:
                        await ws.send_json({"type": "error", "code": "ERR_MALFORMED_JSON"})
                        continue

                    if not isinstance(data, dict):
                        await ws.send_json({"type": "error", "code": "ERR_INVALID_FRAME"})
                        continue

                    msg_type = data.get("type")
                    if not isinstance(msg_type, str):
                        await ws.send_json({"type": "error", "code": "ERR_INVALID_FRAME"})
                        continue

                    if msg_type == "client.resync":
                        await ws.send_json({"type": "server.snapshot", "seq": 1, "payload": {}})
                    elif msg_type == "uec.transition":
                        # Return ACK
                        await ws.send_json({"type": "uec.ack", "payload": data.get("payload", {})})
                    elif msg_type == "uec.approve":
                        await ws.send_json({"type": "uec.ack", "payload": {"state": "SUCCESS", "approved": True}})
                    elif msg_type == "uec.reject":
                        await ws.send_json({"type": "uec.ack", "payload": {"state": "ROLLBACK", "rejected": True}})
            except WebSocketDisconnect:
                pass

        # 4. Root Static File Mounting (Directly at / so relative css/..., js/... all resolve)
        if self.static_dir.exists():
            self.app.mount("/", StaticFiles(directory=str(self.static_dir), html=True), name="static")

    def start(self):
        """Starts server in a background daemon thread with the pre-bound socket."""
        config = uvicorn.Config(
            app=self.app,
            log_config=None,
            access_log=False
        )
        self.uvicorn_server = uvicorn.Server(config)
        self.server_thread = threading.Thread(
            target=self.uvicorn_server.run,
            kwargs={"sockets": [self.listen_socket]},
            daemon=True
        )
        self.server_thread.start()

    def stop(self):
        """Clean teardown of uvicorn and socket."""
        if self.uvicorn_server:
            self.uvicorn_server.should_exit = True
        try:
            self.listen_socket.close()
        except Exception:
            pass
