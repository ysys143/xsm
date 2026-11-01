"""Experimental host protocol. A stdio connection belongs to a trusted local host.

Not a network listener or an authentication boundary against the local uid.
Session handles are connection-local; model-facing tools never receive them.
"""
from __future__ import annotations

import hashlib
import fcntl
import json
import os
import queue
import re
import sys
import threading
import time
import uuid

from . import context, handoff, identity, mcp, paths, registry

VERSION = "1"
POLL_INTERVAL = 0.2
MAX_LINE = 1024 * 1024
RUNTIME = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")


class ProtocolError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def validate(value, schema, path="arguments"):
    """Validate the subset used by the existing public tool schemas."""
    kind = schema.get("type")
    types = {"object": dict, "array": list, "string": str, "boolean": bool,
             "number": (int, float), "integer": int}
    if kind in types and (not isinstance(value, types[kind]) or
            (kind in ("number", "integer") and isinstance(value, bool))):
        raise ProtocolError(-32602, path + " must be " + kind)
    if kind == "number":
        import math
        if not math.isfinite(value):
            raise ProtocolError(-32602, path + " must be finite")
    if "enum" in schema and value not in schema["enum"]:
        raise ProtocolError(-32602, path + " has an unsupported value")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                raise ProtocolError(-32602, path + "." + key + " is required")
        props = schema.get("properties", {})
        for key, item in value.items():
            if key not in props:
                raise ProtocolError(-32602, path + "." + key + " is unknown")
            validate(item, props[key], path + "." + key)
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise ProtocolError(-32602, path + " has too few items")
        for item in value:
            validate(item, schema.get("items", {}), path + "[]")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


class BoundHost(mcp.Server):
    def __init__(self, record):
        super().__init__()
        self.record = record

    def session(self):
        self.ctx = context.of_record(self.record, context.BASIS_HOOK,
                                    evidence=("protocol host opened this conversation",))
        return self.record

    def ask_client(self, method, params):
        # No generic peer or model response may become a person's answer.
        raise ProtocolError(-32004, "host user-interface binding is not implemented; no approval recorded")


class Connection:
    def __init__(self):
        self.initialized = False
        self.sessions = {}
        self.subscriptions = set()
        self.notified = {}
        self.locks = {}

    def bound(self, params):
        token = params.get("session")
        if not isinstance(token, str) or token not in self.sessions:
            raise ProtocolError(-32001, "unknown or closed connection-local session")
        return token, self.sessions[token]

    def dispatch(self, method, params):
        if method == "initialize":
            if self.initialized:
                raise ProtocolError(-32600, "connection already initialized")
            if params.get("protocolVersion") != VERSION:
                raise ProtocolError(-32002, "unsupported protocol version")
            self.initialized = True
            return {"protocolVersion": VERSION, "experimental": True,
                    "capabilities": ["messaging", "inbox", "events"],
                    "operations": [t["name"] for t in mcp.TOOLS]}
        if not self.initialized:
            raise ProtocolError(-32002, "initialize first")
        if method == "operations/list":
            return {"operations": mcp.TOOLS}
        if method == "session.open":
            return self.open(params)
        token, host = self.bound(params)
        if method == "session.close":
            self.close_session(token)
            return {"closed": True}
        if method == "session.update":
            if set(params) - {"session", "state", "name"}:
                raise ProtocolError(-32602, "session identity is immutable")
            state = params.get("state", host.record.get("activity", "idle"))
            if state not in ("idle", "busy"):
                raise ProtocolError(-32602, "state must be idle or busy")
            host.record["activity"] = state
            if "name" in params:
                if not isinstance(params["name"], str):
                    raise ProtocolError(-32602, "name must be text")
                host.record["name"] = params["name"]
            self.save(host.record)
            return {"state": state}
        if method == "events.subscribe":
            self.subscriptions.add(token)
            return {"subscribed": True}
        if method == "delivery.report":
            mid, state = params.get("id"), params.get("state")
            if state not in ("queued", "refused", "unknown"):
                raise ProtocolError(-32602, "state is queued, refused or unknown; use xsm_ack for consumption")
            if handoff.status(host.record, mid)["status"] == "not-found":
                raise ProtocolError(-32602, "message does not belong to this receiver")
            from . import ledger
            if state == "queued":
                ledger.step(mid, "queued", True, "protocol host reports native input queue acceptance")
            paths.append_jsonl("protocol-delivery.jsonl", {
                "id": mid, "receiver": host.record["ref"], "state": state})
            return {"recorded": state, "acknowledged": False}
        if method == "decision.response":
            raise ProtocolError(-32004, "verified host decision binding not implemented; no approval recorded")
        if method != "operation.call":
            raise ProtocolError(-32601, "unknown method")
        name, args = params.get("operation"), params.get("arguments", {})
        tool = next((t for t in mcp.TOOLS if t["name"] == name), None)
        if tool is None:
            raise ProtocolError(-32601, "unknown operation")
        validate(args, tool["inputSchema"])
        args = dict(args)
        # These waits require the MCP transport's re-entrant request pump.
        if args.get("wait") or args.get("wait_secs"):
            raise ProtocolError(-32004, "blocking waits not implemented; subscribe and query status")
        if "wait" in tool["inputSchema"].get("properties", {}):
            args["wait"] = 0
        host.ctx = None
        host.active_request = uuid.uuid4().hex
        try:
            result = host.call(name, args)
            try:
                return json.loads(result)
            except (TypeError, ValueError):
                return {"text": result}
        finally:
            # Never acknowledge on output flush. Original claims remain durable.
            host.handoff_calls.pop(host.active_request, None)
            host.active_request = None

    def open(self, params):
        if set(params) - {"runtime", "profile", "conversation", "cwd", "capabilities"}:
            raise ProtocolError(-32602, "unknown registration field")
        runtime = params.get("runtime")
        if not isinstance(runtime, str) or not RUNTIME.fullmatch(runtime) or runtime in ("claude", "codex"):
            raise ProtocolError(-32602, "runtime must be a new slug; native sessions require their verified bindings")
        for key in ("profile", "conversation", "cwd"):
            value = params.get(key)
            if not isinstance(value, str) or not value or len(value) > 4096:
                raise ProtocolError(-32602, key + " must be nonempty text of at most 4096 characters")
        cwd = params["cwd"]
        if not os.path.isabs(cwd) or not os.path.isdir(cwd):
            raise ProtocolError(-32602, "cwd must be an existing absolute directory")
        caps = params.get("capabilities", [])
        if not isinstance(caps, list) or not all(c in ("messaging", "inbox", "events") for c in caps):
            raise ProtocolError(-32004, "unsupported participant capability")
        profile = hashlib.sha256(params["profile"].encode()).hexdigest()
        sid = hashlib.sha256(json.dumps([profile, params["conversation"]]).encode()).hexdigest()
        home = paths.path("protocol-profiles", runtime, profile)
        previous = paths.read_json(registry._record_path(runtime, sid), {})
        if previous and not previous.get("ended_at") and identity.state_of(previous) == "live":
            raise ProtocolError(-32003, "conversation already has a live owner")
        from . import config
        config.require_valid_policy()
        status = registry._exclusion_status(cwd, config.load().get("directory_excluded_paths", []))
        if status != "included":
            raise ProtocolError(-32003, "directory is excluded or exclusion cannot be determined")
        pid = os.getpid()
        start = identity.lstart(pid)
        if not start:
            raise ProtocolError(-32003, "cannot establish host process generation")
        record = {"runtime": runtime, "home": home, "session_id": sid,
                  "pid": pid, "lstart": start, "cwd": os.path.realpath(cwd),
                  "ref": identity.ref_of(runtime, home, sid), "name": runtime + "-" + sid[:8],
                  "protocol_version": VERSION, "registered": True, "activity": "idle"}
        token = uuid.uuid4().hex
        filename = registry._record_path(runtime, sid)
        os.makedirs(os.path.dirname(filename), mode=0o700, exist_ok=True)
        fd = os.open(filename + ".protocol-lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ProtocolError(-32003, "conversation already has a live owner")
            previous = paths.read_json(filename, {})
            if previous and not previous.get("ended_at") and identity.state_of(previous) == "live":
                raise ProtocolError(-32003, "conversation already has a live owner")
            self.save(record)
            self.sessions[token] = BoundHost(record)
            self.locks[token] = fd
        except BaseException:
            os.close(fd)
            raise
        return {"session": token, "generation": context.generation(pid, start),
                "ref": record["ref"], "capabilities": caps}

    @staticmethod
    def save(record):
        paths.write_json(registry._record_path(record["runtime"], record["session_id"]), record)

    def close_session(self, token):
        host = self.sessions.pop(token)
        self.subscriptions.discard(token)
        self.notified.pop(token, None)
        try:
            registry.mark_ended(host.record["runtime"], host.record["session_id"], "protocol-close",
                                home=host.record["home"])
        finally:
            os.close(self.locks.pop(token))

    def close(self):
        for token in list(self.sessions):
            self.close_session(token)

    def events(self):
        from . import receive
        for token in sorted(self.subscriptions):
            rec = self.sessions[token].record
            ids = handoff.pending_ids(rec, owner_alive=receive._consumer_alive)
            # A passive FYI never emits an unsolicited notification.
            ids = [mid for mid in ids if handoff.status(rec, mid)["message"].get("wake", True)]
            current = tuple(sorted(ids))
            if current and self.notified.get(token) != current:
                yield {"jsonrpc": "2.0", "method": "events/available",
                       "params": {"session": token, "ids": list(current)}}
            self.notified[token] = current


def serve(inp=None, out=None):
    inp, out = inp or sys.stdin, out or sys.stdout
    incoming = queue.Queue(maxsize=64)
    connection = Connection()

    def read():
        try:
            while True:
                line = inp.readline(MAX_LINE + 1)
                if not line:
                    break
                incoming.put(line)
                if len(line) > MAX_LINE:
                    break
        finally:
            incoming.put(None)

    threading.Thread(target=read, daemon=True).start()

    def emit(value):
        out.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
        out.flush()

    try:
        next_poll = time.monotonic()
        while True:
            if time.monotonic() >= next_poll:
                for event in connection.events():
                    emit(event)
                next_poll = time.monotonic() + POLL_INTERVAL
            try:
                line = incoming.get(timeout=max(0, next_poll - time.monotonic()))
            except queue.Empty:
                continue
            if line is None:
                break
            mid, request = None, None
            try:
                if len(line) > MAX_LINE:
                    raise ProtocolError(-32600, "frame exceeds limit")
                try:
                    request = json.loads(line, object_pairs_hook=_object,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                except (ValueError, RecursionError):
                    raise ProtocolError(-32700, "invalid JSON")
                if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
                    raise ProtocolError(-32600, "expected JSON-RPC 2.0 object")
                if set(request) - {"jsonrpc", "id", "method", "params"}:
                    raise ProtocolError(-32600, "unknown request field")
                mid = request.get("id")
                if isinstance(mid, bool) or not isinstance(mid, (str, int, type(None))):
                    mid = None
                    raise ProtocolError(-32600, "invalid request id")
                if "id" not in request:
                    # All state-changing methods require a response correlation.
                    continue
                method, params = request.get("method"), request.get("params", {})
                if not isinstance(method, str) or not isinstance(params, dict):
                    raise ProtocolError(-32600, "method and object params required")
                result = connection.dispatch(method, params)
                emit({"jsonrpc": "2.0", "id": mid, "result": result})
            except ProtocolError as exc:
                emit({"jsonrpc": "2.0", "id": mid, "error": {"code": exc.code, "message": exc.message}})
            except (ValueError, TypeError, KeyError, mcp.ToolError) as exc:
                emit({"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": str(exc)}})
    except (BrokenPipeError, OSError):
        return 1
    finally:
        connection.close()
    return 0


def configure_parser(sub):
    command = sub.add_parser("protocol", help="experimental host protocol")
    actions = command.add_subparsers(dest="protocol_action", required=True)
    server = actions.add_parser("serve", help="serve JSON-RPC over stdio")
    server.add_argument("--stdio", action="store_true", required=True)
    server.set_defaults(func=lambda args: serve())
