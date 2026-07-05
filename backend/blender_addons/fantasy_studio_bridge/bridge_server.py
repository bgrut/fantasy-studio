"""
Bridge socket server — runs INSIDE Blender.

Threading model:
    - Listener thread: accepts TCP connections
    - Per-connection thread: reads frames, queues ops for main-thread execution
    - Main thread (Blender): pops ops via bpy.app.timers, dispatches to handlers,
      writes results back to the connection thread

Why main-thread dispatch?
    bpy is NOT thread-safe. All bpy mutations MUST happen on Blender's main
    thread. We use bpy.app.timers.register() to drain the op queue at ~30Hz.
    Socket I/O stays on worker threads (safe), but actual bpy calls hop to
    main via the timer.

Protocol:
    Frame = 4-byte big-endian length + UTF-8 JSON bytes.
    Request: {"id": str, "op": str, "params": dict}
    Response: {"id": str, "ok": bool, "result": Any} or {"id": str, "ok": False, "error": str, "trace": str}
"""

import socket
import threading
import struct
import json
import queue
import traceback
import time
from typing import Optional, Tuple

import bpy

from . import handlers


# ───────────────────────────────────────────────────────────────────────
# Module state
# ───────────────────────────────────────────────────────────────────────

_server_socket: Optional[socket.socket] = None
_listener_thread: Optional[threading.Thread] = None
_stop_flag = threading.Event()
_op_queue: "queue.Queue[Tuple[dict, queue.Queue]]" = queue.Queue()
_timer_registered = False

LOG_PREFIX = "[studio_bridge]"
FRAME_HEADER = struct.Struct(">I")  # 4-byte big-endian length
MAX_FRAME_BYTES = 16 * 1024 * 1024  # 16MB cap to prevent runaway alloc


# ───────────────────────────────────────────────────────────────────────
# Frame I/O
# ───────────────────────────────────────────────────────────────────────

def _recv_exact(sock: socket.socket, n: int) -> Optional[bytes]:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def _recv_frame(sock: socket.socket) -> Optional[dict]:
    header = _recv_exact(sock, FRAME_HEADER.size)
    if header is None:
        return None
    (length,) = FRAME_HEADER.unpack(header)
    if length == 0 or length > MAX_FRAME_BYTES:
        raise ValueError(f"frame length {length} out of bounds")
    payload = _recv_exact(sock, length)
    if payload is None:
        return None
    return json.loads(payload.decode("utf-8"))


def _send_frame(sock: socket.socket, obj: dict) -> None:
    payload = json.dumps(obj, default=_json_default).encode("utf-8")
    sock.sendall(FRAME_HEADER.pack(len(payload)) + payload)


def _json_default(o):
    """Best-effort JSON encoder for bpy primitives that aren't natively serializable."""
    # bpy.types.bpy_prop_array, Vector, Color, etc. all support iteration
    try:
        return list(o)
    except TypeError:
        return repr(o)


# ───────────────────────────────────────────────────────────────────────
# Connection handler (worker thread, NOT main)
# ───────────────────────────────────────────────────────────────────────

def _handle_connection(conn: socket.socket, addr) -> None:
    print(f"{LOG_PREFIX} client connected: {addr}")
    try:
        # Long socket-read timeout. Inner per-op timeout is enforced separately
        # via result_q.get(timeout=...) below. 1800s gives long renders room.
        conn.settimeout(1800.0)
        while not _stop_flag.is_set():
            try:
                req = _recv_frame(conn)
            except socket.timeout:
                continue
            except (ConnectionResetError, BrokenPipeError):
                break

            if req is None:
                break  # peer closed

            req_id = req.get("id", "")
            op = req.get("op", "")
            params = req.get("params", {}) or {}

            # Special: "ping" answered immediately on worker thread (no bpy touch)
            if op == "ping":
                _send_frame(conn, {"id": req_id, "ok": True, "result": {"pong": True, "ts": time.time()}})
                continue

            # All other ops MUST run on main thread → submit + wait for result.
            # Long timeout because render_animation can take 10+ minutes for big scenes.
            result_q: queue.Queue = queue.Queue(maxsize=1)
            _op_queue.put(({"id": req_id, "op": op, "params": params}, result_q))
            try:
                # Timeouts sized for the WORST supported hardware, not the
                # best: a 100-frame scene takes 25-45 min on a CPU-only box,
                # and heavy execute_python compose steps can pass 5 min
                # (2026-07-05 story-film hang). The CLIENT owns the shorter
                # per-op deadline; the server is just a backstop.
                op_timeout = 5400.0 if op in ("render_animation", "render_frame") else 1800.0
                result = result_q.get(timeout=op_timeout)
            except queue.Empty:
                try:
                    _send_frame(conn, {
                        "id": req_id,
                        "ok": False,
                        "error": f"timeout waiting for main-thread dispatch (op '{op}' took >{op_timeout}s)",
                    })
                except OSError:
                    break      # peer already gone — never crash the handler
                continue

            try:
                _send_frame(conn, result)
            except OSError:    # incl. ConnectionAborted — peer timed out first
                break
    finally:
        try:
            conn.close()
        except Exception:
            pass
        print(f"{LOG_PREFIX} client disconnected: {addr}")


def _listener_loop(server_sock: socket.socket) -> None:
    server_sock.settimeout(0.5)
    while not _stop_flag.is_set():
        try:
            conn, addr = server_sock.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        t = threading.Thread(target=_handle_connection, args=(conn, addr), daemon=True, name=f"studio_bridge_conn_{addr[1]}")
        t.start()


# ───────────────────────────────────────────────────────────────────────
# Main-thread drainer — registered as a bpy timer
# ───────────────────────────────────────────────────────────────────────

def _drain_op_queue() -> float:
    """Pop pending ops, dispatch on main thread, write result back to caller queue."""
    drained = 0
    while not _op_queue.empty() and drained < 8:  # cap per tick so we don't stall UI
        try:
            envelope, result_q = _op_queue.get_nowait()
        except queue.Empty:
            break

        req_id = envelope["id"]
        op = envelope["op"]
        params = envelope["params"]

        try:
            result = handlers.dispatch(op, params)
            response = {"id": req_id, "ok": True, "result": result}
        except handlers.UnknownOpError as e:
            response = {"id": req_id, "ok": False, "error": str(e), "code": "unknown_op"}
        except Exception as e:
            response = {
                "id": req_id,
                "ok": False,
                "error": f"{type(e).__name__}: {e}",
                "trace": traceback.format_exc(),
            }

        try:
            result_q.put_nowait(response)
        except queue.Full:
            print(f"{LOG_PREFIX} result queue full for op={op}; dropping")
        drained += 1

    # Re-arm timer
    return 0.033 if _stop_flag.is_set() is False else None


# ───────────────────────────────────────────────────────────────────────
# Public API: start/stop
# ───────────────────────────────────────────────────────────────────────

def start(port: int = 9876, host: str = "127.0.0.1") -> Tuple[bool, str]:
    global _server_socket, _listener_thread, _timer_registered

    if _server_socket is not None:
        return False, "bridge already running"

    _stop_flag.clear()

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.listen(8)
    except OSError as e:
        return False, f"bind failed: {e}"

    _server_socket = s
    _listener_thread = threading.Thread(target=_listener_loop, args=(s,), daemon=True, name="studio_bridge_listener")
    _listener_thread.start()

    if not _timer_registered:
        bpy.app.timers.register(_drain_op_queue, first_interval=0.1)
        _timer_registered = True

    print(f"{LOG_PREFIX} listening on {host}:{port}")
    return True, ""


def stop() -> None:
    global _server_socket, _listener_thread, _timer_registered

    _stop_flag.set()

    if _server_socket is not None:
        try:
            _server_socket.close()
        except Exception:
            pass
        _server_socket = None

    if _listener_thread is not None:
        _listener_thread.join(timeout=2.0)
        _listener_thread = None

    if _timer_registered:
        try:
            bpy.app.timers.unregister(_drain_op_queue)
        except (ValueError, RuntimeError):
            pass
        _timer_registered = False

    # Drain any pending ops so callers don't hang
    while not _op_queue.empty():
        try:
            _, result_q = _op_queue.get_nowait()
            result_q.put_nowait({"ok": False, "error": "bridge stopped"})
        except (queue.Empty, queue.Full):
            break

    print(f"{LOG_PREFIX} stopped")
