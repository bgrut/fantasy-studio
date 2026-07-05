"""
Blender Bridge — socket client (Python side, runs in orchestrator process).

Talks to the Fantasy Studio Bridge addon running inside Blender. Same
length-prefixed JSON protocol as bridge_server.py (in the addon).

Connection model:
    - Lazy: connect() opens TCP, holds one connection
    - call(op, params, timeout) sends, waits, returns
    - Auto-reconnect on broken pipe (one retry)
    - Thread-safe via lock — multiple callers serialize on the socket

This module has NO bpy imports — it runs in the regular Python process,
not inside Blender.
"""

import socket
import struct
import json
import uuid
import threading
import time
from typing import Any, Optional

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9876
DEFAULT_TIMEOUT = 60.0
FRAME_HEADER = struct.Struct(">I")


class BridgeError(Exception):
    """Raised when an op fails — wraps the addon's structured error."""

    def __init__(self, op: str, error: str, code: Optional[str] = None, trace: Optional[str] = None):
        super().__init__(f"[{op}] {error}")
        self.op = op
        self.error_msg = error
        self.code = code
        self.trace = trace


class BridgeConnectionError(BridgeError):
    """Raised when we can't reach Blender at all."""

    def __init__(self, msg: str):
        super().__init__("connect", msg)


# ───────────────────────────────────────────────────────────────────────
# Module-level singleton connection (most code uses this)
# ───────────────────────────────────────────────────────────────────────

_sock: Optional[socket.socket] = None
_lock = threading.Lock()
_host = DEFAULT_HOST
_port = DEFAULT_PORT


def configure(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """Set the host/port for future connect() calls."""
    global _host, _port
    _host = host
    _port = port


def _connect_locked(host: Optional[str] = None, port: Optional[int] = None,
                    timeout: float = 5.0) -> None:
    """Connect WITHOUT taking _lock — caller must already hold it.

    Split out because call() reconnects while holding _lock; the old code
    called connect() there, re-acquiring the same non-reentrant lock =
    SELF-DEADLOCK (the 2026-07-05 story-render hang: a render outlived the
    socket timeout, the reconnect path froze the thread forever)."""
    global _sock
    if _sock is not None:
        return
    h = host or _host
    p = port or _port
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((h, p))
        s.settimeout(None)  # blocking after connect
        _sock = s
    except (ConnectionRefusedError, socket.timeout, OSError) as e:
        raise BridgeConnectionError(
            f"can't reach Blender addon at {h}:{p} — {e}. "
            f"Is Blender running with the fantasy_studio_bridge addon enabled?"
        )


def connect(host: Optional[str] = None, port: Optional[int] = None, timeout: float = 5.0) -> None:
    """Open the socket connection to the Blender addon. Raises BridgeConnectionError on failure."""
    with _lock:
        _connect_locked(host, port, timeout)


def disconnect() -> None:
    global _sock
    with _lock:
        if _sock is not None:
            try:
                _sock.close()
            except Exception:
                pass
            _sock = None


def is_connected() -> bool:
    return _sock is not None


# ───────────────────────────────────────────────────────────────────────
# Frame I/O
# ───────────────────────────────────────────────────────────────────────

def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("socket closed mid-frame")
        buf += chunk
    return buf


def _send_frame(sock: socket.socket, obj: dict) -> None:
    payload = json.dumps(obj).encode("utf-8")
    sock.sendall(FRAME_HEADER.pack(len(payload)) + payload)


def _recv_frame(sock: socket.socket) -> dict:
    header = _recv_exact(sock, FRAME_HEADER.size)
    (length,) = FRAME_HEADER.unpack(header)
    payload = _recv_exact(sock, length)
    return json.loads(payload.decode("utf-8"))


# ───────────────────────────────────────────────────────────────────────
# Main entry: call(op, params)
# ───────────────────────────────────────────────────────────────────────

def call(op: str, params: Optional[dict] = None, timeout: float = DEFAULT_TIMEOUT, auto_reconnect: bool = True) -> Any:
    """Send an op to Blender, return result. Raises BridgeError on op failure."""
    if not is_connected():
        connect()

    req = {"id": str(uuid.uuid4()), "op": op, "params": params or {}}

    with _lock:
        try:
            assert _sock is not None
            _sock.settimeout(timeout)
            _send_frame(_sock, req)
            resp = _recv_frame(_sock)
        except (ConnectionError, BrokenPipeError, ConnectionResetError, socket.timeout) as e:
            # Connection died. Try once to reconnect + retry.
            _force_reset()
            if not auto_reconnect:
                raise BridgeConnectionError(f"socket error on op={op}: {e}")
            try:
                _connect_locked()          # we already hold _lock — see above
                assert _sock is not None
                _sock.settimeout(timeout)
                _send_frame(_sock, req)
                resp = _recv_frame(_sock)
            except Exception as e2:
                raise BridgeConnectionError(f"reconnect failed for op={op}: {e2}")

    if resp.get("id") != req["id"]:
        raise BridgeError(op, f"response id mismatch: got {resp.get('id')}, expected {req['id']}")

    if not resp.get("ok"):
        raise BridgeError(
            op,
            resp.get("error", "unknown error"),
            code=resp.get("code"),
            trace=resp.get("trace"),
        )
    return resp.get("result")


def ping(timeout: float = 2.0) -> bool:
    """Cheap liveness check — returns True if Blender's addon answers."""
    try:
        result = call("ping", timeout=timeout, auto_reconnect=False)
        return bool(result and result.get("pong"))
    except BridgeError:
        return False


def _force_reset() -> None:
    """Internal: drop socket without taking lock (caller already holds it)."""
    global _sock
    if _sock is not None:
        try:
            _sock.close()
        except Exception:
            pass
        _sock = None


# ───────────────────────────────────────────────────────────────────────
# Convenience: wait for Blender to come up (useful right after launching it)
# ───────────────────────────────────────────────────────────────────────

def wait_until_ready(timeout: float = 30.0, poll_interval: float = 0.5) -> bool:
    """Block until the bridge responds to ping, or timeout. Returns True on success."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            connect(timeout=1.0)
            if ping(timeout=1.0):
                return True
        except BridgeConnectionError:
            pass
        disconnect()
        time.sleep(poll_interval)
    return False
