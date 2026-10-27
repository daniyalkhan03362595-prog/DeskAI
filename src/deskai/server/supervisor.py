"""
DesktopServer Implementation:
Pre-bound loopback socket, root static asset mounting, single-use token redemption,
and hardened WebSocket gateway.
"""

import asyncio
import json
import threading
import time
from pathlib import Path
import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from deskai.server.security import SessionSecurityManager
from deskai.server.terminal import TerminalManager
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
        self.terminal_manager = TerminalManager()

        # Load shared UEC transition matrix
        transitions_file = self.static_dir / "transitions.json"
        if transitions_file.exists():
            with open(transitions_file, "r", encoding="utf-8") as f:
                self.transitions_table = json.load(f)
        else:
            self.transitions_table = {}

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
                resp = Response(status_code=403, content="Invalid Host")
                return self.security.apply_security_headers(resp, is_no_store=True)

            session_id = self.security.redeem_launch_token(token)
            if not session_id:
                resp = Response(status_code=403, content="Invalid or Expired Launch Token")
                return self.security.apply_security_headers(resp, is_no_store=True)

            # Redirect to clean root URL with HttpOnly SameSite=Strict cookie
            response = RedirectResponse(url="/", status_code=303)
            response.set_cookie(key="deskai_session", value=session_id, httponly=True, samesite="strict", path="/")
            return self.security.apply_security_headers(response, is_no_store=True)

        # 2. Root Index Route (Injects dynamic per-launch CSP style nonce)
        @self.app.get("/")
        async def serve_index(request: Request):
            index_path = self.static_dir / "index.html"
            if not index_path.exists():
                return Response(status_code=404, content="Not Found")
            html = index_path.read_text(encoding="utf-8")
            nonce = self.security.style_nonce
            if '<meta name="csp-nonce"' in html:
                import re

                html = re.sub(
                    r'<meta\s+name=["\']csp-nonce["\']\s+content=["\'][^"\']*["\']>',
                    f'<meta name="csp-nonce" content="{nonce}">',
                    html,
                )
            elif "<head>" in html:
                html = html.replace("<head>", f'<head>\n  <meta name="csp-nonce" content="{nonce}">', 1)
            resp = Response(content=html, media_type="text/html")
            return self.security.apply_security_headers(resp, is_no_store=True)

        @self.app.get("/index.html")
        async def serve_index_html(request: Request):
            return await serve_index(request)

        # 3. HTTP Middleware (Host, Cookie & CSP Guards)
        @self.app.middleware("http")
        async def security_middleware(request: Request, call_next):
            path = request.url.path

            # Allowed unauthenticated endpoint
            if path == "/auth/redeem":
                return await call_next(request)

            # Host Header Check
            host = request.headers.get("host")
            if not is_valid_loopback_host(host, self.port):
                resp = Response(status_code=403, content="Forbidden: Host mismatch")
                return self.security.apply_security_headers(resp)

            # Session Cookie Check
            session_cookie = request.cookies.get("deskai_session")
            if not self.security.is_valid_session(session_cookie):
                resp = Response(status_code=401, content="Unauthorized: Valid session required")
                return self.security.apply_security_headers(resp)

            response = await call_next(request)

            # Strict Security Headers & Cache-Control: no-store for root
            is_no_store = path in ("/", "/auth/redeem")
            return self.security.apply_security_headers(response, is_no_store=is_no_store)

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

            # D. Concurrency Limit: Max 4 Sockets Per Session
            if len(self.security.get_session_sockets(cookie)) >= 4:
                await ws.close(code=4429, reason="Too Many Sockets for Session")
                return

            self.security.register_socket(cookie, ws)

            # Frame Handling Loop with Monotonically Increasing Connection Sequence & UEC State Machine
            conn_seq = 1
            uec_state = "IDLE"
            processed_requests = set()

            async def send_frame(frame_type: str, payload: dict = None, **extra):
                nonlocal conn_seq
                frame = {"type": frame_type, "seq": conn_seq, "payload": payload if payload is not None else {}}
                frame.update(extra)
                conn_seq += 1
                await ws.send_json(frame)

            try:
                # Token Bucket Rate Limiter: 30 msgs/sec capacity and fill rate
                tokens = 30.0
                last_token_time = time.monotonic()

                while True:
                    message = await ws.receive()
                    if message["type"] == "websocket.disconnect":
                        break

                    if message["type"] == "websocket.receive":
                        # Binary frame handling: close with 1003
                        if message.get("bytes") is not None:
                            await ws.close(code=1003, reason="Binary frames unsupported")
                            return

                        raw_text = message.get("text")
                        if raw_text is None:
                            continue

                        # Rate limit check per message
                        now = time.monotonic()
                        elapsed = now - last_token_time
                        last_token_time = now
                        tokens = min(30.0, tokens + elapsed * 30.0)
                        if tokens < 1.0:
                            await ws.close(code=4429, reason="Rate limit exceeded")
                            return
                        tokens -= 1.0

                        # Wire size measurement in UTF-8 bytes (must not exceed 64 KB)
                        raw_bytes = raw_text.encode("utf-8")
                        if len(raw_bytes) > 65536:
                            await send_frame("error", code="ERR_PAYLOAD_TOO_LARGE")
                            continue

                        try:
                            data = json.loads(raw_text)
                        except json.JSONDecodeError:
                            await send_frame("error", code="ERR_MALFORMED_JSON")
                            continue

                        if not isinstance(data, dict):
                            await send_frame("error", code="ERR_INVALID_FRAME")
                            continue

                        msg_type = data.get("type")
                        if not isinstance(msg_type, str):
                            await send_frame("error", code="ERR_INVALID_FRAME")
                            continue

                        if msg_type == "client.resync":
                            await send_frame("server.snapshot", payload={"uec_state": uec_state})
                        elif msg_type == "uec.transition":
                            payload = data.get("payload") or {}
                            target_state = payload.get("to")
                            allowed = self.transitions_table.get(uec_state, [])
                            if target_state in allowed:
                                uec_state = target_state
                                await send_frame("uec.ack", payload={"state": uec_state})
                            else:
                                await send_frame(
                                    "error",
                                    code="ERR_INVALID_TRANSITION",
                                    message=f"Transition from {uec_state} to {target_state} not allowed",
                                )
                        elif msg_type == "uec.approve":
                            req_id = data.get("request_id") or data.get("idempotency_key")
                            if req_id and req_id in processed_requests:
                                await send_frame(
                                    "uec.ack", payload={"state": uec_state, "approved": True, "idempotent": True}
                                )
                                continue

                            if uec_state == "PLANNING":
                                next_state = "EXECUTING"
                            elif uec_state == "REVIEW_DIFF":
                                next_state = "SUCCESS"
                            else:
                                await send_frame(
                                    "error",
                                    code="ERR_INVALID_TRANSITION",
                                    message=f"Cannot approve in state {uec_state}",
                                )
                                continue

                            allowed = self.transitions_table.get(uec_state, [])
                            if next_state in allowed:
                                uec_state = next_state
                                if req_id:
                                    processed_requests.add(req_id)
                                await send_frame("uec.ack", payload={"state": uec_state, "approved": True})
                            else:
                                await send_frame(
                                    "error",
                                    code="ERR_INVALID_TRANSITION",
                                    message=f"Transition from {uec_state} to {next_state} not allowed",
                                )
                        elif msg_type == "uec.reject":
                            req_id = data.get("request_id") or data.get("idempotency_key")
                            if req_id and req_id in processed_requests:
                                await send_frame(
                                    "uec.ack", payload={"state": uec_state, "rejected": True, "idempotent": True}
                                )
                                continue

                            if uec_state == "REVIEW_DIFF":
                                next_state = "ROLLBACK"
                            elif uec_state in ("PLANNING", "EXECUTING"):
                                next_state = "CANCELLED"
                            else:
                                await send_frame(
                                    "error",
                                    code="ERR_INVALID_TRANSITION",
                                    message=f"Cannot reject in state {uec_state}",
                                )
                                continue

                            allowed = self.transitions_table.get(uec_state, [])
                            if next_state in allowed:
                                uec_state = next_state
                                if req_id:
                                    processed_requests.add(req_id)
                                await send_frame("uec.ack", payload={"state": uec_state, "rejected": True})
                            else:
                                await send_frame(
                                    "error",
                                    code="ERR_INVALID_TRANSITION",
                                    message=f"Transition from {uec_state} to {next_state} not allowed",
                                )
            except (WebSocketDisconnect, ConnectionResetError, RuntimeError):
                pass
            finally:
                self.security.unregister_socket(cookie, ws)

        # 4. Dedicated Terminal WebSocket Transport (/ws/terminal/{session_id})
        def _get_write_buffer_size(ws: WebSocket) -> int:
            for attr in ("_transport", "transport"):
                t = getattr(ws, attr, None)
                if t and hasattr(t, "get_write_buffer_size"):
                    try:
                        return t.get_write_buffer_size()
                    except Exception:
                        pass
            raw = getattr(ws, "_websocket", None)
            if raw:
                t = getattr(raw, "transport", None)
                if t and hasattr(t, "get_write_buffer_size"):
                    try:
                        return t.get_write_buffer_size()
                    except Exception:
                        pass
            return 0

        @self.app.websocket("/ws/terminal/{session_id}")
        async def terminal_websocket_endpoint(ws: WebSocket, session_id: str):
            await ws.accept()

            # A. Verify Host Header
            host = ws.headers.get("host", "")
            if not is_valid_loopback_host(host, self.port):
                await ws.close(code=4403, reason="Invalid Host")
                return

            # B. Verify Origin Header (Strict Match)
            origin = ws.headers.get("origin")
            if origin != f"http://127.0.0.1:{self.port}":
                await ws.close(code=4403, reason="Cross-Origin WebSocket Denied")
                return

            # C. Verify Session Cookie
            cookie = ws.cookies.get("deskai_session")
            if not self.security.is_valid_session(cookie):
                await ws.close(code=4401, reason="Unauthorized Session")
                return

            # D. Lookup Terminal Session
            session = self.terminal_manager.get_session(session_id)
            if not session:
                await ws.close(code=4404, reason="Terminal Session Not Found")
                return

            # E. Enforce One WebSocket Attachment per Terminal Session
            if getattr(session, "has_active_websocket", False):
                await ws.close(code=4429, reason="Terminal Session Already Attached")
                return
            session.has_active_websocket = True

            try:
                # F. Concurrent Output and Input Pumps with Atomic Replay Snapshot & Flow Control
                async def output_pump():
                    try:
                        async for chunk in session.read_chunks(with_snapshot=True):
                            while _get_write_buffer_size(ws) > 1_000_000:
                                await asyncio.sleep(0.02)
                            await ws.send_bytes(chunk)
                    except Exception:
                        pass
                    finally:
                        try:
                            code = session.exit_code if session.exit_code is not None else 0
                            await ws.send_text(json.dumps({"type": "exit", "code": code}))
                            await ws.close(code=1000)
                        except Exception:
                            pass

                async def input_pump():
                    input_tokens = 256 * 1024.0
                    last_input_time = time.monotonic()
                    try:
                        while True:
                            msg = await ws.receive()
                            if msg["type"] == "websocket.disconnect":
                                break

                            if msg["type"] == "websocket.receive":
                                raw_bytes = msg.get("bytes")
                                raw_text = msg.get("text")

                                payload_size = (
                                    len(raw_bytes)
                                    if raw_bytes is not None
                                    else (len(raw_text.encode("utf-8")) if raw_text is not None else 0)
                                )

                                if payload_size > 65536:
                                    await ws.send_text(json.dumps({"type": "error", "code": "ERR_PAYLOAD_TOO_LARGE"}))
                                    continue

                                # 256 KB/s paste flood rate limiter
                                now = time.monotonic()
                                elapsed = now - last_input_time
                                last_input_time = now
                                input_tokens = min(256 * 1024.0, input_tokens + elapsed * (256 * 1024.0))
                                if input_tokens < payload_size:
                                    await ws.close(code=4429, reason="Input Rate Limit Exceeded")
                                    return
                                input_tokens -= payload_size

                                if raw_bytes is not None:
                                    session.write(raw_bytes)
                                    continue

                                if raw_text is not None:
                                    try:
                                        ctrl = json.loads(raw_text)
                                    except json.JSONDecodeError:
                                        await ws.send_text(json.dumps({"type": "error", "code": "ERR_MALFORMED_JSON"}))
                                        continue

                                    if not isinstance(ctrl, dict):
                                        await ws.send_text(
                                            json.dumps({"type": "error", "code": "ERR_INVALID_CONTROL_FRAME"})
                                        )
                                        continue

                                    ctype = ctrl.get("type")
                                    if ctype == "resize":
                                        cols = ctrl.get("cols")
                                        rows = ctrl.get("rows")
                                        if type(cols) is not int or type(rows) is not int:
                                            await ws.send_text(
                                                json.dumps({"type": "error", "code": "ERR_INVALID_CONTROL_FRAME"})
                                            )
                                            continue
                                        if not (10 <= cols <= 500) or not (2 <= rows <= 200):
                                            await ws.send_text(
                                                json.dumps({"type": "error", "code": "ERR_INVALID_CONTROL_FRAME"})
                                            )
                                            continue
                                        session.resize(cols, rows)
                                    elif ctype == "close":
                                        await asyncio.to_thread(session.close)
                                        break
                                    else:
                                        await ws.send_text(
                                            json.dumps({"type": "error", "code": "ERR_INVALID_CONTROL_FRAME"})
                                        )
                    except Exception:
                        pass

                out_task = asyncio.create_task(output_pump())
                in_task = asyncio.create_task(input_pump())
                done, pending = await asyncio.wait([out_task, in_task], return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
            except (WebSocketDisconnect, ConnectionResetError, RuntimeError):
                pass
            finally:
                session.has_active_websocket = False

        # 4. Root Static File Mounting (Directly at / so relative css/..., js/... all resolve)
        if self.static_dir.exists():
            self.app.mount("/", StaticFiles(directory=str(self.static_dir), html=True), name="static")

    def start(self):
        """Starts server in a background daemon thread with the pre-bound socket."""
        config = uvicorn.Config(
            app=self.app,
            log_config=None,
            access_log=False,
            ws_max_size=65536,
            ws_ping_interval=20,
            ws_ping_timeout=20,
        )
        self.uvicorn_server = uvicorn.Server(config)
        self.server_thread = threading.Thread(
            target=self.uvicorn_server.run, kwargs={"sockets": [self.listen_socket]}, daemon=True
        )
        self.server_thread.start()

    def stop(self):
        """Clean teardown of uvicorn, thread join, socket closure and session clearance."""
        if hasattr(self, "terminal_manager") and self.terminal_manager:
            try:
                self.terminal_manager.close_all()
            except Exception:
                pass
        if self.uvicorn_server:
            self.uvicorn_server.should_exit = True
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=5.0)
        if self.listen_socket:
            try:
                self.listen_socket.close()
            except Exception:
                pass
            self.listen_socket = None
        self.security.clear_sessions()
