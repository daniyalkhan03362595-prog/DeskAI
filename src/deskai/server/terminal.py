"""
Terminal Session & PTY Management for DeskAI.
Provides process isolation, environment allowlisting, ring replay buffering,
and clean lifecycle termination across POSIX (ptyprocess) and Windows (pywinpty).
"""

import asyncio
from collections.abc import AsyncIterator
import os
import secrets
import shutil
import signal
import sys
import threading
import time

from deskai.utils.path import is_disallowed_workspace_root, is_safe_workspace_path

try:
    import ptyprocess
except ImportError:
    ptyprocess = None

try:
    import winpty
except ImportError:
    winpty = None


def resolve_shell() -> str:
    """Resolves shell path from an immutable system allowlist."""
    if sys.platform == "win32":
        try:
            pwsh = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
        except Exception:
            pwsh = None
        if pwsh:
            return pwsh
        try:
            cmd = shutil.which("cmd.exe") or os.environ.get("ComSpec")
        except Exception:
            cmd = os.environ.get("ComSpec")
        if cmd:
            return cmd
        return "cmd.exe"

    shell_env = os.environ.get("SHELL")
    valid_shells: list[str] = []
    if os.path.exists("/etc/shells"):
        try:
            with open("/etc/shells", "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s and not s.startswith("#"):
                        valid_shells.append(s)
        except Exception:
            pass

    if shell_env and os.path.isabs(shell_env) and shell_env in valid_shells:
        if os.path.isfile(shell_env) and os.access(shell_env, os.X_OK):
            return shell_env

    if os.path.isfile("/bin/bash") and os.access("/bin/bash", os.X_OK):
        return "/bin/bash"
    if os.path.isfile("/usr/bin/bash") and os.access("/usr/bin/bash", os.X_OK):
        return "/usr/bin/bash"
    return "/bin/sh"


def build_terminal_env() -> dict[str, str]:
    """
    Constructs an explicit child environment allowlist.
    Prevents leaking internal tokens, server secrets, and DESKAI_* variables.
    """
    allowlisted_exact = {
        "HOME",
        "USER",
        "LOGNAME",
        "LANG",
        "LANGUAGE",
        "SHELL",
        "DISPLAY",
        "WAYLAND_DISPLAY",
        "XDG_RUNTIME_DIR",
        "SSH_AUTH_SOCK",
        "TMPDIR",
        "TERMINFO",
        "SystemRoot",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "TEMP",
        "TMP",
        "ComSpec",
        "PATHEXT",
    }
    env: dict[str, str] = {}
    for k, v in os.environ.items():
        if k in allowlisted_exact or k.startswith("LC_") or k.startswith("XDG_"):
            env[k] = v
        elif k == "PATH":
            env["PATH"] = v

    if "HOME" not in env and sys.platform != "win32":
        env["HOME"] = os.path.expanduser("~")
    if "USER" not in env and sys.platform != "win32":
        env["USER"] = os.environ.get("USER", os.environ.get("LOGNAME", "user"))
    if "PATH" not in env:
        env["PATH"] = os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")

    env["TERM"] = "xterm-256color"
    env["COLORTERM"] = "truecolor"

    # Explicitly ensure NO DESKAI_* secrets or launch tokens reach child
    for k in list(env.keys()):
        if k.startswith("DESKAI_") or "TOKEN" in k.upper():
            del env[k]

    return env


class ReplayBuffer:
    """Bounded ring replay buffer (default 256 KB) for client resync."""

    def __init__(self, max_bytes: int = 256 * 1024):
        self.max_bytes = max_bytes
        self._buffer = bytearray()
        self._lock = threading.Lock()

    def append(self, data: bytes):
        if not data:
            return
        with self._lock:
            if len(data) >= self.max_bytes:
                self._buffer = bytearray(data[-self.max_bytes :])
                return
            self._buffer.extend(data)
            overflow = len(self._buffer) - self.max_bytes
            if overflow > 0:
                del self._buffer[:overflow]

    def get_snapshot(self) -> bytes:
        with self._lock:
            return bytes(self._buffer)

    def __len__(self) -> int:
        with self._lock:
            return len(self._buffer)


class TerminalSession:
    """
    Unified wrapper around POSIX ptyprocess and Windows ConPTY/pywinpty.
    Provides write(bytes), resize(cols, rows), read_chunks(), close(), alive, exit_code.
    """

    def __init__(
        self,
        session_id: str,
        cwd: str,
        cols: int = 80,
        rows: int = 24,
        replay_buffer_size: int = 256 * 1024,
    ):
        self.session_id = session_id
        self.cwd = cwd
        self.cols = max(10, min(500, int(cols)))
        self.rows = max(2, min(200, int(rows)))
        self.replay_buffer = ReplayBuffer(max_bytes=replay_buffer_size)
        self._process = None
        self._closed = False
        self._exit_code: int | None = None
        self._subscribers: list[asyncio.Queue[bytes]] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._reader_thread: threading.Thread | None = None
        self._lock = threading.Lock()

        self._spawn()

    def _spawn(self):
        shell = resolve_shell()
        env = build_terminal_env()
        if sys.platform == "win32":
            winpty_mod = sys.modules.get("winpty") or winpty
            if winpty_mod is None:
                try:
                    import winpty as winpty_mod
                except ImportError:
                    winpty_mod = None
            if winpty_mod is None:
                raise RuntimeError("winpty is required on Windows")
            self._process = winpty_mod.PtyProcess.spawn(
                [shell],
                cwd=self.cwd,
                env=env,
                dimensions=(self.rows, self.cols),
            )
        else:
            if ptyprocess is None:
                raise RuntimeError("ptyprocess is required on POSIX")
            argv = [shell]
            if os.path.basename(shell) in ("bash", "sh", "zsh"):
                argv.append("-i")
            self._process = ptyprocess.PtyProcess.spawn(
                argv,
                cwd=self.cwd,
                env=env,
                dimensions=(self.rows, self.cols),
            )

        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name=f"TerminalReader-{self.session_id[:8]}",
            daemon=True,
        )
        self._reader_thread.start()

    def _reader_loop(self):
        try:
            while not self._closed and self._is_alive():
                if sys.platform == "win32":
                    data = self._process.read(4096)
                    if isinstance(data, str):
                        data = data.encode("utf-8", errors="replace")
                else:
                    data = os.read(self._process.fd, 4096)
                if not data:
                    break
                with self._lock:
                    self.replay_buffer.append(data)
                self._dispatch_to_subscribers(data)
        except (OSError, EOFError):
            pass
        finally:
            self._on_process_ended()

    def _is_alive(self) -> bool:
        if self._process is None:
            return False
        try:
            return bool(self._process.isalive())
        except Exception:
            return False

    def _dispatch_to_subscribers(self, data: bytes, is_eof: bool = False):
        """
        Dispatches chunks (or EOF sentinel b'') to active subscribers with backpressure.
        Blocks the reader thread with a short polling loop until all attached subscriber
        queues accept the chunk, causing the PTY buffer to fill and child process to block.
        When NO subscriber is attached, output goes only to ReplayBuffer and the reader does not block.
        The EOF sentinel is never dropped.
        """
        if not self._loop or self._loop.is_closed():
            return

        with self._lock:
            pending_queues = set(self._subscribers)

        if not pending_queues:
            return

        while pending_queues and not self._closed:
            done_event = threading.Event()
            still_pending = set()

            def try_enqueue():
                with self._lock:
                    active = set(self._subscribers)
                for q in pending_queues:
                    if q not in active:
                        continue
                    try:
                        q.put_nowait(data)
                    except asyncio.QueueFull:
                        still_pending.add(q)
                done_event.set()

            try:
                self._loop.call_soon_threadsafe(try_enqueue)
            except RuntimeError:
                break

            done_event.wait(timeout=0.005)
            if not done_event.is_set():
                time.sleep(0.001)
                continue

            pending_queues = still_pending
            if pending_queues:
                time.sleep(0.001)

    def _on_process_ended(self):
        if self._process:
            try:
                for _ in range(20):
                    if not self._is_alive():
                        break
                    time.sleep(0.05)
                if hasattr(self._process, "exitstatus") and self._process.exitstatus is not None:
                    self._exit_code = self._process.exitstatus
            except Exception:
                pass
        self._dispatch_to_subscribers(b"", is_eof=True)

    @property
    def alive(self) -> bool:
        if self._closed:
            return False
        return self._is_alive()

    @property
    def exit_code(self) -> int | None:
        if self._exit_code is not None:
            return self._exit_code
        if self._process:
            try:
                self._is_alive()
                if hasattr(self._process, "exitstatus") and self._process.exitstatus is not None:
                    self._exit_code = self._process.exitstatus
                    return self._exit_code
            except Exception:
                pass
        return None

    def write(self, data: bytes):
        """Writes raw bytes or keystrokes to PTY stdin."""
        if self._closed or not self.alive:
            return
        if sys.platform == "win32":
            text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
            self._process.write(text)
        else:
            self._process.write(data)

    def resize(self, cols: int, rows: int):
        """Resizes the terminal window; kernel delivers SIGWINCH to process group."""
        if self._closed or not self.alive:
            return
        cols = max(10, min(500, int(cols)))
        rows = max(2, min(200, int(rows)))
        self.cols = cols
        self.rows = rows
        if self._process:
            self._process.setwinsize(rows, cols)

    async def read_chunks(self, with_snapshot: bool = False) -> AsyncIterator[bytes]:
        """
        Asynchronously yields chunks of binary terminal output as they arrive.
        If with_snapshot is True, takes the replay snapshot and registers the subscriber queue
        atomically under self._lock so no bytes are lost or duplicated between snapshot and live output.
        """
        self._loop = asyncio.get_running_loop()
        queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=64)
        snapshot = b""
        with self._lock:
            if with_snapshot:
                snapshot = self.replay_buffer.get_snapshot()
            self._subscribers.append(queue)

        if snapshot:
            yield snapshot

        try:
            while True:
                chunk = await queue.get()
                if chunk == b"":
                    break
                yield chunk
        finally:
            with self._lock:
                if queue in self._subscribers:
                    self._subscribers.remove(queue)

    def close(self):
        """Sends SIGHUP, escalates to SIGKILL after 3s, then reaps process."""
        if self._closed:
            return
        self._closed = True
        if self._process:
            if sys.platform == "win32":
                try:
                    self._process.close()
                except Exception:
                    pass
            else:
                pid = getattr(self._process, "pid", None)
                if pid and self._is_alive():
                    try:
                        os.killpg(pid, signal.SIGHUP)
                    except OSError:
                        pass
                    start = time.time()
                    while time.time() - start < 3.0:
                        if not self._is_alive():
                            break
                        time.sleep(0.05)
                    if self._is_alive():
                        try:
                            os.killpg(pid, signal.SIGKILL)
                        except OSError:
                            pass
                try:
                    self._process.close(force=True)
                except Exception:
                    pass
        self._on_process_ended()


class TerminalManager:
    """Manages active terminal sessions, spawn gating, and clean teardown."""

    MAX_SESSIONS = 4

    def __init__(self):
        self._sessions: dict[str, TerminalSession] = {}
        self._lock = threading.Lock()

    @property
    def has_running_terminal(self) -> bool:
        with self._lock:
            return any(s.alive for s in self._sessions.values())

    def get_session(self, session_id: str) -> TerminalSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def create_session(
        self,
        workspace_root: str,
        cols: int = 80,
        rows: int = 24,
        client_cwd: str | None = None,
    ) -> TerminalSession:
        """
        Spawns a new TerminalSession subject to spawn gates.
        client_cwd must NOT be provided; cwd is strictly workspace_root server-side.
        """
        if client_cwd is not None:
            raise ValueError("Client-supplied cwd is strictly forbidden")

        if not workspace_root:
            raise ValueError("Workspace root not set")

        if is_disallowed_workspace_root(workspace_root):
            raise ValueError(f"Disallowed workspace root: {workspace_root}")

        if not is_safe_workspace_path(workspace_root, workspace_root):
            raise ValueError(f"Unsafe workspace path: {workspace_root}")

        with self._lock:
            # Clean up reaped/dead sessions
            dead_ids = [sid for sid, s in self._sessions.items() if not s.alive]
            for sid in dead_ids:
                try:
                    self._sessions[sid].close()
                except Exception:
                    pass
                del self._sessions[sid]

            active_count = len([s for s in self._sessions.values() if s.alive])
            if active_count >= self.MAX_SESSIONS:
                raise RuntimeError(f"Concurrent session limit reached (max {self.MAX_SESSIONS})")

            session_id = secrets.token_urlsafe(32)
            session = TerminalSession(
                session_id=session_id,
                cwd=workspace_root,
                cols=cols,
                rows=rows,
            )
            self._sessions[session_id] = session
            return session

    def close_session(self, session_id: str) -> bool:
        with self._lock:
            session = self._sessions.pop(session_id, None)
        if session:
            session.close()
            return True
        return False

    def close_all(self):
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            try:
                session.close()
            except Exception:
                pass
