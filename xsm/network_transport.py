"""Optional JSONL client for xsm-net. Importing this module starts nothing.

Only the native engine authenticates peers: ``origin`` is always taken from
its event, never from a request or response body. Errors contain fixed codes;
engine stderr, payloads, tickets and key material are deliberately not retained.
"""
from __future__ import annotations

import base64
import copy
import json
import math
import os
from pathlib import Path
import queue
import re
import signal
import stat
import subprocess
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeout


MAX_IPC_LINE = 12 * 1024 * 1024  # Includes the terminating newline; matches Rust.
MAX_FRAME = 8 * 1024 * 1024
DEFAULT_TIMEOUT = 30.0
_MAX_PENDING = 64
_MAX_HISTORY = 4096
_KEY = re.compile(r"[0-9a-f]{64}\Z")
_SIGNATURE = re.compile(r"[0-9a-f]{128}\Z")
_ENGINE_CODES = frozenset((
    "invalid_command", "invalid_json", "invalid_base64", "invalid_peer",
    "invalid_frame", "frame_too_large", "ipc_too_large", "ipc_read", "ipc_write", "ipc_write_timeout",
    "connect_failed", "stream_failed", "timeout", "busy", "unknown_request",
    "state_io", "state_locked", "state_permissions", "invalid_secret",
    "bind_failed", "invalid_relay", "invalid_address", "invalid_port",
))


class SidecarError(RuntimeError):
    """A stable code, with no native stderr or untrusted diagnostic text."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


TransportError = SidecarError


def find_binary(binary=None):
    """Resolve an explicit override or a repository build, without installing."""
    override = binary if binary is not None else os.environ.get("XSM_NET_BINARY")
    if override is not None:
        candidates = [Path(override)]
    else:
        from . import paths
        root = Path(__file__).resolve().parent.parent / "native" / "xsm-net" / "target"
        candidates = [Path(paths.path("network", "bin", "xsm-net"))]
        candidates.extend(root / mode / "xsm-net" for mode in ("release", "debug"))
    try:
        for candidate in candidates:
            if candidate.is_file():
                if os.access(candidate, os.X_OK):
                    return str(candidate.absolute())
                if override is not None:
                    raise SidecarError("binary_not_executable")
    except OSError:
        raise SidecarError("binary_unavailable") from None
    raise SidecarError("binary_missing")


def _timeout(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SidecarError("invalid_timeout")
    try:
        valid = math.isfinite(value) and value > 0
    except OverflowError:
        valid = False
    if not valid:
        raise SidecarError("invalid_timeout")
    return float(value)


def _encode(value, limit=MAX_IPC_LINE):
    try:
        data = json.dumps(value, ensure_ascii=False, allow_nan=False,
                          separators=(",", ":")).encode("utf-8") + b"\n"
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise SidecarError("invalid_json") from None
    if len(data) > limit:
        raise SidecarError("ipc_too_large" if limit == MAX_IPC_LINE else "frame_too_large")
    return data


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError()


def _private_directory(path):
    # Create only missing directories, without changing any existing ancestor.
    missing = []
    current = path
    while not current.exists() and not current.is_symlink():
        missing.append(current)
        current = current.parent
    for directory in reversed(missing):
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            pass
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700
            or info.st_uid != os.geteuid()):
        raise SidecarError("state_permissions")


class Sidecar:
    def __init__(self, state_dir, port=0, relay=None, direct_addresses=(), binary=None):
        if type(port) is not int or not 0 <= port <= 65535:
            raise SidecarError("invalid_port")
        if relay is not None and not isinstance(relay, str):
            raise SidecarError("invalid_relay")
        if isinstance(direct_addresses, (str, bytes)):
            raise SidecarError("invalid_address")
        self.state_dir = Path(state_dir).absolute()
        self.port, self.relay = port, relay
        self.direct_addresses = tuple(direct_addresses)
        if any(not isinstance(address, str) for address in self.direct_addresses):
            raise SidecarError("invalid_address")
        self.binary = binary
        self._lock = threading.RLock()
        self._start_lock = threading.Lock()
        self._cleanup_lock = threading.Lock()
        self._cleanup_done = threading.Event()
        self._stopping = threading.Event()
        self._ready = Future()
        self._ready_info = None
        self._last_transport = None
        self._process = None
        self._reader = self._writer = self._watcher = self._executor = None
        self._handler = None
        self._pending = {}
        self._retired = OrderedDict()
        self._inbound = OrderedDict()
        self._handler_slots = threading.BoundedSemaphore(32)
        self._writes = queue.Queue(maxsize=_MAX_PENDING)
        self._counter = 0
        self._failure = None
        self._closing = False

    @property
    def endpoint_id(self):
        with self._lock:
            return self._ready_info["endpoint_id"] if self._ready_info else None

    @property
    def running(self):
        with self._lock:
            return bool(self._process and self._process.poll() is None and not self._failure and not self._closing)

    @property
    def process_id(self):
        with self._lock:
            return self._process.pid if self._process is not None else None

    @property
    def address(self):
        with self._lock:
            return copy.deepcopy(self._ready_info["address"]) if self._ready_info else None

    @property
    def last_transport(self):
        """Latest native route diagnostics; never includes the RPC body."""
        with self._lock:
            return copy.deepcopy(self._last_transport)

    def start(self, timeout=DEFAULT_TIMEOUT):
        timeout = _timeout(timeout)
        with self._start_lock:
            with self._lock:
                if self._failure:
                    raise SidecarError(self._failure)
                if self._ready_info:
                    return copy.deepcopy(self._ready_info)
                binary = find_binary(self.binary)
                try:
                    _private_directory(self.state_dir)
                except OSError:
                    raise SidecarError("state_io") from None
                args = [binary, "serve", "--state-dir", str(self.state_dir),
                        "--port", str(self.port)]
                if self.relay is not None:
                    args.extend(("--relay", self.relay))
                for address in self.direct_addresses:
                    args.extend(("--direct-address", address))
                try:
                    self._process = subprocess.Popen(
                        args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
                except (OSError, ValueError):
                    raise SidecarError("spawn_failed") from None
                self._executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="xsm-net-handler")
                self._writer = threading.Thread(target=self._write_loop, name="xsm-net-stdin", daemon=True)
                self._reader = threading.Thread(target=self._read_loop, name="xsm-net-stdout", daemon=True)
                self._watcher = threading.Thread(target=self._watch_process, name="xsm-net-wait", daemon=True)
                self._writer.start()
                self._reader.start()
                self._watcher.start()
            try:
                self._ready.result(timeout=timeout)
                with self._lock:
                    if self._failure:
                        raise SidecarError(self._failure)
                    return copy.deepcopy(self._ready_info)
            except FutureTimeout:
                self._fail("start_timeout")
                raise SidecarError("start_timeout") from None
            finally:
                if self._stopping.is_set():
                    self._dispose()

    def set_request_handler(self, callback):
        if callback is not None and not callable(callback):
            raise SidecarError("invalid_handler")
        with self._lock:
            self._handler = callback

    def call(self, op, timeout=DEFAULT_TIMEOUT, **kwargs):
        timeout = _timeout(timeout)
        deadline = time.monotonic() + timeout
        if op not in ("request", "sign", "verify", "address") or "id" in kwargs:
            raise SidecarError("invalid_command")
        if op == "request":
            if "body" not in kwargs or "peer" not in kwargs:
                raise SidecarError("invalid_command")
            # The wire frame bound excludes its length header and JSONL newline.
            _encode(kwargs["body"], MAX_FRAME + 1)
            kwargs["timeout_ms"] = max(1, math.ceil(min(timeout, 120) * 1000))
        with self._lock:
            if self._failure:
                raise SidecarError(self._failure)
            if self._ready_info is None:
                raise SidecarError("not_started")
            if len(self._pending) >= _MAX_PENDING:
                raise SidecarError("busy")
            self._counter += 1
            identifier = "py-%d" % self._counter
            data = _encode(dict(kwargs, id=identifier, op=op))
            future = Future()
            self._pending[identifier] = (future, op)
            try:
                self._enqueue(data)
            except SidecarError:
                self._pending.pop(identifier, None)
                raise
        try:
            return future.result(timeout=max(0, deadline - time.monotonic()))
        except FutureTimeout:
            with self._lock:
                if self._pending.pop(identifier, None) is not None:
                    self._remember(self._retired, identifier, True)
            raise SidecarError("timeout") from None

    def request(self, peer, body, timeout=DEFAULT_TIMEOUT):
        event = self.call("request", peer=peer, body=body, timeout=timeout)
        return {"origin": event["origin"], "body": event["body"]}

    def sign(self, data: bytes, timeout=DEFAULT_TIMEOUT):
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise SidecarError("invalid_data")
        encoded = base64.b64encode(data).decode("ascii")
        return self.call("sign", data=encoded, timeout=timeout)["signature"]

    def verify(self, public_key, data: bytes, signature, timeout=DEFAULT_TIMEOUT):
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise SidecarError("invalid_data")
        encoded = base64.b64encode(data).decode("ascii")
        return self.call("verify", endpoint_id=public_key, data=encoded,
                         signature=signature, timeout=timeout)["valid"]

    def _enqueue(self, data):
        if self._stopping.is_set():
            raise SidecarError(self._failure or "closed")
        try:
            self._writes.put_nowait(data)
        except queue.Full:
            raise SidecarError("busy") from None

    def _write_loop(self):
        try:
            while not self._stopping.is_set():
                try:
                    data = self._writes.get(timeout=0.1)
                except queue.Empty:
                    continue
                self._process.stdin.write(data)
                self._process.stdin.flush()
        except (OSError, ValueError):
            self._fail("process_exited")
        finally:
            if self._stopping.is_set():
                self._dispose()

    def _watch_process(self):
        self._process.wait()
        self._fail("process_exited")
        self._dispose()

    def _read_loop(self):
        try:
            while not self._stopping.is_set():
                line = self._process.stdout.readline(MAX_IPC_LINE + 1)
                if not line:
                    raise SidecarError("process_exited")
                if len(line) > MAX_IPC_LINE:
                    raise SidecarError("ipc_too_large")
                if not line.endswith(b"\n"):
                    raise SidecarError("invalid_stdout")
                try:
                    event = json.loads(line.decode("utf-8"), object_pairs_hook=_pairs,
                                       parse_constant=_invalid_constant)
                except (ValueError, UnicodeError, RecursionError):
                    raise SidecarError("invalid_stdout") from None
                self._dispatch(event)
        except SidecarError as exc:
            self._fail(exc.code)
        except (OSError, ValueError, TypeError, KeyError, RuntimeError):
            self._fail("invalid_stdout")
        finally:
            self._dispose()

    def _dispatch(self, event):
        if not isinstance(event, dict):
            raise SidecarError("invalid_stdout")
        kind = event.get("event")
        with self._lock:
            if self._stopping.is_set():
                return
            if kind == "ready":
                if self._ready_info is not None:
                    raise SidecarError("duplicate_id")
                if (not self._key(event.get("endpoint_id"))
                        or not isinstance(event.get("address"), dict)
                        or type(event.get("requested_port")) is not int
                        or event["requested_port"] != self.port
                        or not isinstance(event.get("bound_addresses"), list)
                        or not all(isinstance(a, str) for a in event["bound_addresses"])
                        or type(event.get("port_fallback")) is not bool):
                    raise SidecarError("invalid_stdout")
                self._ready_info = event
                self._ready.set_result(event)
                return
            if self._ready_info is None:
                raise SidecarError("invalid_stdout")
            if kind == "path":
                identifier = event.get("request_id")
                if (not self._identifier(identifier) or identifier not in self._inbound
                        or event.get("origin") != self._inbound[identifier]
                        or event.get("direction") != "incoming"):
                    raise SidecarError("invalid_stdout")
                self._record_transport(event)
                return
            if kind == "request":
                identifier = event.get("request_id")
                if not self._identifier(identifier) or not self._key(event.get("origin")) or "body" not in event:
                    raise SidecarError("invalid_stdout")
                if identifier in self._inbound:
                    raise SidecarError("duplicate_id")
                self._remember(self._inbound, identifier, event["origin"])
                self._record_transport(event)
                _encode(event["body"], MAX_FRAME + 1)
                if not self._handler_slots.acquire(blocking=False):
                    self._respond(identifier, {"error": {"code": "busy"}})
                    return
                self._executor.submit(self._handle, identifier, event["origin"], event["body"], self._handler)
                return
            if kind not in ("result", "response", "error"):
                raise SidecarError("invalid_stdout")
            identifier = event.get("id")
            if not self._identifier(identifier):
                raise SidecarError("invalid_stdout")
            pending = self._pending.get(identifier)
            if pending is None:
                if kind == "error" and identifier in self._inbound:
                    # The native inbound deadline may expire while a Python
                    # handler runs. Its late respond must not stop other RPCs.
                    return
                if self._retired.get(identifier) is True:
                    self._remember(self._retired, identifier, False)
                    return  # A timed-out call may still finish in the engine.
                raise SidecarError("duplicate_id" if identifier in self._retired else "unknown_id")
            future, op = pending
            if kind == "error":
                code = event.get("code")
                code = code if isinstance(code, str) and code in _ENGINE_CODES else "engine_error"
                error = SidecarError(code)
            else:
                error = None
                if op == "request":
                    valid = kind == "response" and self._key(event.get("origin")) and "body" in event
                    if valid:
                        _encode(event["body"], MAX_FRAME + 1)
                elif op == "sign":
                    valid = kind == "result" and isinstance(event.get("signature"), str) and bool(_SIGNATURE.fullmatch(event["signature"]))
                elif op == "verify":
                    valid = kind == "result" and type(event.get("valid")) is bool
                else:
                    valid = kind == "result" and isinstance(event.get("address"), dict)
                if not valid:
                    raise SidecarError("invalid_stdout")
                if op == "request":
                    self._record_transport(event)
                if op == "address":
                    self._ready_info["address"] = event["address"]
            self._pending.pop(identifier)
            self._remember(self._retired, identifier, False)
            if error:
                future.set_exception(error)
            else:
                future.set_result(event)

    def _record_transport(self, event):
        native = event.get("transport")
        if isinstance(native, dict):
            self._last_transport = {key: copy.deepcopy(native[key]) for key in (
                "path", "selected", "selection_reason", "fallback_reason",
                "remote_address", "relay_url", "paths") if key in native}

    @staticmethod
    def _key(value):
        return isinstance(value, str) and bool(_KEY.fullmatch(value))

    @staticmethod
    def _identifier(value):
        return isinstance(value, str) and 0 < len(value) <= 128

    @staticmethod
    def _remember(history, identifier, value):
        history[identifier] = value
        history.move_to_end(identifier)
        if len(history) > _MAX_HISTORY:
            history.popitem(last=False)

    def _respond(self, identifier, body):
        _encode(body, MAX_FRAME + 1)
        self._enqueue(_encode({"op": "respond", "id": identifier, "body": body}))

    def _handle(self, identifier, origin, body, callback):
        try:
            try:
                result = callback(origin, body) if callback is not None else {"error": {"code": "handler_unavailable"}}
                _encode(result, MAX_FRAME + 1)
            except Exception:
                result = {"error": {"code": "handler_failed"}}
            try:
                self._respond(identifier, result)
            except SidecarError:
                if not self._stopping.is_set():
                    self._fail("ipc_write")
                    self._dispose()
        finally:
            self._handler_slots.release()

    def _fail(self, code):
        with self._lock:
            if self._failure is None:
                self._failure = "closed" if self._closing else code
            self._stopping.set()
            if not self._ready.done():
                self._ready.set_exception(SidecarError(self._failure))
            for future, _ in self._pending.values():
                future.set_exception(SidecarError(self._failure))
            self._pending.clear()

    def close(self):
        with self._lock:
            self._closing = True
            if not self._stopping.is_set() and self._process is not None:
                try:
                    self._writes.put_nowait(b'{"op":"shutdown"}\n')
                except queue.Full:
                    pass
                # Let the writer transmit shutdown before setting its stop event.
                process = self._process
            else:
                process = None
        if process is not None:
            try:
                process.wait(timeout=0.4)
            except subprocess.TimeoutExpired:
                pass
        self._fail("closed")
        self._dispose()
        if threading.current_thread() not in (self._reader, self._writer):
            self._cleanup_done.wait(timeout=3)

    def _dispose(self):
        if self._cleanup_done.is_set():
            return
        if not self._cleanup_lock.acquire(blocking=False):
            return
        try:
            if self._cleanup_done.is_set():
                return
            process = self._process
            if process is not None:
                # A private process group also owns any engine descendants.
                for sig in (signal.SIGTERM, signal.SIGKILL):
                    try:
                        os.killpg(process.pid, sig)
                    except ProcessLookupError:
                        pass
                    except PermissionError:
                        # Some macOS hosts deny signalling an already-gone
                        # process group. Fall back to our owned child only.
                        if process.poll() is None:
                            try:
                                process.send_signal(sig)
                            except ProcessLookupError:
                                pass
                    try:
                        process.wait(timeout=0.4)
                    except subprocess.TimeoutExpired:
                        pass
                for worker in (self._reader, self._writer, self._watcher):
                    if worker is not None and worker is not threading.current_thread():
                        worker.join(timeout=0.5)
                for pipe in (process.stdin, process.stdout):
                    try:
                        pipe.close()
                    except (OSError, ValueError):
                        pass
            if self._executor is not None:
                self._executor.shutdown(wait=False, cancel_futures=True)
            while True:
                try:
                    self._writes.get_nowait()
                except queue.Empty:
                    break
        finally:
            self._cleanup_done.set()
            self._cleanup_lock.release()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.close()
