"""Experimental host protocol. A stdio connection belongs to a trusted local host.

Not a network listener or an authentication boundary against the local uid.
Session handles are connection-local; model-facing tools never receive them.
"""
from __future__ import annotations

import hashlib
import hmac
import fcntl
import json
import os
import queue
import re
import sys
import threading
import time
import uuid

from . import context, handoff, identity, paths, registry
from .operation_schema import TOOLS, ToolError, operation_returns_json, OperationDisplay
from .operations import OperationService

VERSION = "1"
POLL_INTERVAL = 0.2
MAX_LINE = 1024 * 1024
RUNTIME = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")


REQUEST_FIELDS = {
    "initialize": {"protocolVersion"},
    "operations/list": set(),
    "session.open": {"runtime", "profile", "conversation", "cwd", "capabilities"},
    "session.update": {"session", "state", "name"},
    "session.close": {"session"},
    "events.subscribe": {"session"},
    "operation.call": {"session", "operation", "arguments"},
    "inbox.release": {"session", "tokens"},
    "delivery.report": {"session", "id", "state", "token"},
    "decision.response": {"session", "questionId", "challenge", "displayed", "action", "answer", "source_id"},
    "decision.abandon": {"session", "questionId", "challenge"},
}


def request_fields(method, params):
    allowed = REQUEST_FIELDS.get(method)
    if allowed is not None and set(params) - allowed:
        raise ProtocolError(-32602, "unknown parameters for " + method)


class ProtocolError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


class QuestionPending(Exception):
    def __init__(self, decision_id, question_id):
        self.decision_id = decision_id
        self.question_id = question_id
        super().__init__(decision_id)


def validate(value, schema, path="arguments"):
    """Validate the subset used by the existing public tool schemas."""
    kind = schema.get("type")
    types = {"object": dict, "array": list, "string": str, "boolean": bool,
             "number": (int, float), "integer": int}
    if kind in types and (not isinstance(value, types[kind]) or
            (kind in ("number", "integer") and isinstance(value, bool))):
        raise ProtocolError(-32602, path + " must be " + kind)
    if kind == "number" and isinstance(value, float):
        import math
        if not math.isfinite(value):
            raise ProtocolError(-32602, path + " must be finite")
    if kind in ("number", "integer"):
        if "minimum" in schema and value < schema["minimum"]:
            raise ProtocolError(-32602, path + " is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ProtocolError(-32602, path + " exceeds maximum")
    if isinstance(value, str) and "pattern" in schema:
        import re
        if re.search(schema["pattern"], value) is None:
            raise ProtocolError(-32602, path + " has an invalid format")
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
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ProtocolError(-32602, path + " has too many items")
        for item in value:
            validate(item, schema.get("items", {}), path + "[]")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


class BoundHost(OperationService):
    def __init__(self, record, connection, token, capabilities):
        self.initialize_service()
        self._closed = False
        self.record = record
        self.connection, self.token = connection, token
        self.client_name = "xsm-protocol-host"
        if "user-decisions" in capabilities:
            self.client_caps = {"elicitation": {}}

    def session(self):
        self.ctx = context.of_record(self.record, context.BASIS_HOOK,
                                    evidence=("protocol host opened this conversation",))
        return self.record

    def ask_client(self, method, params):
        from . import decisions
        if method != "elicitation/create" or "elicitation" not in self.client_caps:
            raise ProtocolError(-32004, "host has no user-interface capability; no approval recorded")
        call = self.decision_calls.get(self.active_request)
        if not call:
            raise ProtocolError(-32004, "question has no scoped decision invocation")
        if not isinstance(params.get("message"), str) or not params["message"].strip():
            raise ProtocolError(-32602, "a nonempty user question is required")
        choices = params.get("requestedSchema", {}).get("properties", {}).get("answer", {}).get("enum")
        record = decisions.begin(call["key"], call["me"], call["scope"], call["generation"],
            params.get("message", ""), waiter=self.active_request, choices=choices)
        record = decisions.recover_display(record["id"])
        if not self._decision_current(call):
            raise ProtocolError(-32003, "decision caller or scope changed")
        if record.get("answer"):
            if record["status"] not in ("answered", "denied", "dismissed", "unshown-or-declined"):
                raise ProtocolError(-32003, "decision is not applicable: " + record["status"])
            if record["status"] == "answered":
                decisions.start_application(record["id"], call["generation"], call["scope"],
                                            reader=self.reader_identity)
            return record["answer"]["reply"]
        if record["status"] != "pending":
            raise ProtocolError(-32003, "decision is " + record["status"])
        if record["id"] not in self.connection.ui_requests:
            if not decisions.display(record["id"], self.active_request, params["message"],
                    "host-user", reader=self.reader_identity):
                raise ProtocolError(-32003, "question already belongs to another display owner")
            self.connection.ui_requests[record["id"]] = {
                "host": self, "call": call, "notified": False,
                "event": {"session": self.token, "decisionId": record["id"],
                    "questionId": uuid.uuid4().hex, "challenge": uuid.uuid4().hex,
                    "question": params["message"], "requestedSchema": params["requestedSchema"],
                    "expiresAt": record["expires_at"]}}
        raise QuestionPending(record["id"], self.connection.ui_requests[record["id"]]["event"]["questionId"])


class Connection:
    def __init__(self):
        self.initialized = False
        self.sessions = {}
        self.subscriptions = set()
        self.notified = {}
        self.locks = {}
        self.ui_requests = {}
        self.ui_answers = {}

    def bound(self, params):
        token = params.get("session")
        if not isinstance(token, str) or token not in self.sessions:
            raise ProtocolError(-32001, "unknown or closed connection-local session")
        return token, self.sessions[token]

    def dispatch(self, method, params):
        if method == "initialize":
            if self.initialized:
                raise ProtocolError(-32600, "connection already initialized")
            request_fields(method, params)
            if params.get("protocolVersion") != VERSION:
                raise ProtocolError(-32002, "unsupported protocol version")
            self.initialized = True
            return {"protocolVersion": VERSION, "experimental": True,
                    "capabilities": ["messaging", "inbox", "events", "user-decisions"],
                    "limits": {"claimLeaseSeconds": handoff.CLAIM_LEASE},
                    "operations": [t["name"] for t in TOOLS]}
        if not self.initialized:
            raise ProtocolError(-32002, "initialize first")
        request_fields(method, params)
        if method == "operations/list":
            return {"operations": TOOLS}
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
        if method == "inbox.release":
            from . import receive
            tokens = params.get("tokens")
            if not isinstance(tokens, list) or not tokens or not all(isinstance(t, str) for t in tokens):
                raise ProtocolError(-32602, "tokens must be a nonempty array of claim tokens")
            result = receive.release_inbox(host.record, tokens)
            self.notified.pop(token, None)
            return result
        if method == "delivery.report":
            mid, state = params.get("id"), params.get("state")
            if state not in ("queued", "admitted", "refused", "unknown"):
                raise ProtocolError(-32602, "state is queued, admitted, refused or unknown; use xsm_ack for consumption")
            original = handoff.status(host.record, mid)
            if original["status"] == "not-found":
                raise ProtocolError(-32602, "message does not belong to this receiver")
            from . import ledger
            if state == "admitted":
                from . import receive
                owner, generation = receive.consumer_for(host.record)
                current = original.get("claim") or {}
                supplied = params.get("token")
                if (not isinstance(supplied, str) or current.get("owner") != owner or
                        current.get("generation") != generation or
                        not hmac.compare_digest((current.get("token") or "").encode(), supplied.encode())):
                    raise ProtocolError(-32003, "native admission requires this host's exact claim token")
                receive.protocol_receipt(host.record, original, "protocol host observed native context admission")
            if state in ("queued", "admitted"):
                ledger.step(mid, "queued", True, "protocol host reports native input queue acceptance")
            paths.append_jsonl("protocol-delivery.jsonl", {
                "id": mid, "receiver": host.record["ref"], "state": state})
            return {"recorded": state, "acknowledged": False}
        if method == "decision.response":
            return self.decision_response(token, host, params)
        if method == "decision.abandon":
            return self.abandon_question(token, host, params)
        if method != "operation.call":
            raise ProtocolError(-32601, "unknown method")
        name, args = params.get("operation"), params.get("arguments", {})
        tool = next((t for t in TOOLS if t["name"] == name), None)
        if tool is None:
            raise ProtocolError(-32601, "unknown operation")
        validate(args, tool["inputSchema"])
        args = dict(args)
        if args.get("answer_request"):
            raise ProtocolError(-32004, "native transcript answer recovery requires a verified native binding")
        # These waits require the MCP transport's re-entrant request pump.
        if args.get("wait") or args.get("wait_secs"):
            raise ProtocolError(-32004, "blocking waits not implemented; subscribe and query status")
        if "wait" in tool["inputSchema"].get("properties", {}):
            args["wait"] = 0
        host.ctx = None
        host.active_request = uuid.uuid4().hex
        try:
            result = host.call(name, args)
            if not isinstance(result, str):
                raise ProtocolError(-32603, "internal server error")
            if not operation_returns_json(name, args):
                metadata = result.metadata if isinstance(result, OperationDisplay) else {}
                return dict(metadata, text=str(result))
            try:
                value = json.loads(result)
            except (TypeError, ValueError, RecursionError):
                raise ProtocolError(-32603, "internal server error") from None
            if not isinstance(value, dict):
                raise ProtocolError(-32603, "internal server error")
            if name == "xsm_inbox":
                from . import receive
                value["items"] = [receive.inbox_item_metadata(host.record, claim['id'])
                                  for claim in value.get('claims', [])]
            return value
        except QuestionPending as pending:
            return {"status": "waiting-for-user", "decision_id": pending.decision_id,
                    "question_id": pending.question_id}
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
        if not isinstance(caps, list) or not all(c in ("messaging", "inbox", "events", "user-decisions") for c in caps):
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
                  "protocol_version": VERSION, "protocol_generation": uuid.uuid4().hex,
                  "registered": True, "activity": "idle"}
        record["protocol_root"] = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
        record["protocol_python"] = sys.executable
        record["protocol_python_version"] = sys.version.split()[0]
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
            self.sessions[token] = BoundHost(record, self, token, caps)
            self.locks[token] = fd
        except BaseException:
            os.close(fd)
            raise
        return {"session": token, "generation": record["protocol_generation"],
                "ref": record["ref"], "capabilities": caps}

    @staticmethod
    def save(record):
        paths.write_json(registry._record_path(record["runtime"], record["session_id"]), record)

    def close_session(self, token):
        host = self.sessions.pop(token)
        self.subscriptions.discard(token)
        self.notified.pop(token, None)
        from . import decisions
        try:
            for key, item in list(self.ui_requests.items()):
                if item["host"] is host:
                    if decisions.read(key):
                        decisions.abandon_display(key, host.instance_id)
                    del self.ui_requests[key]
            registry.mark_ended(host.record["runtime"], host.record["session_id"], "protocol-close",
                                home=host.record["home"])
        finally:
            os.close(self.locks.pop(token))

    def close(self):
        for token in list(self.sessions):
            self.close_session(token)

    def events(self):
        from . import receive
        for item in self.ui_requests.values():
            if not item["notified"]:
                item["notified"] = True
                yield {"jsonrpc": "2.0", "method": "decision/request", "params": item["event"]}
        for token in sorted(self.subscriptions):
            rec = self.sessions[token].record
            ids = handoff.pending_ids(rec, owner_alive=receive._consumer_alive)
            # A passive FYI never emits an unsolicited notification.
            ids = [mid for mid in ids if receive.message_wake_policy(handoff.status(rec, mid)["message"]) is True]
            current = tuple(sorted(ids))
            if current and self.notified.get(token) != current:
                yield {"jsonrpc": "2.0", "method": "events/available",
                       "params": {"session": token, "ids": list(current)}}
            self.notified[token] = current

    def decision_response(self, token, host, params):
        from . import consent, decisions
        if "elicitation" not in host.client_caps:
            raise ProtocolError(-32004, "host has no user-interface capability; no approval recorded")
        if set(params) != {"session", "questionId", "challenge", "displayed", "action", "answer", "source_id"}:
            raise ProtocolError(-32602, "exact host question response fields required")
        for key in ("questionId", "challenge", "displayed", "action", "source_id"):
            if not isinstance(params[key], str) or not params[key] or len(params[key]) > MAX_LINE:
                raise ProtocolError(-32602, "invalid host response " + key)
        fingerprint = decisions.digest(params)
        prior = self.ui_answers.get(params["questionId"])
        if prior:
            if prior["session"] != token or prior["fingerprint"] != fingerprint:
                raise ProtocolError(-32003, "question response already consumed")
            return {"status": decisions.public_status(host.record, prior["decision"])["status"],
                    "decision_id": prior["decision"]}
        selected = next(((key, item) for key, item in self.ui_requests.items()
                         if item["event"]["questionId"] == params["questionId"]), None)
        if not selected:
            raise ProtocolError(-32003, "question does not belong to a pending host display")
        key, item = selected
        event = item["event"]
        if (item["host"] is not host or event["session"] != token or
                not hmac.compare_digest(event["challenge"].encode(), params["challenge"].encode()) or
                params["displayed"] != event["question"]):
            raise ProtocolError(-32003, "question, display, or host identity mismatch")
        record = decisions.read(key)
        if (record["status"] != "pending" or time.time() < record["created_at"] or
                time.time() > record["expires_at"] or not host._decision_current(item["call"])):
            raise ProtocolError(-32003, "question is closed, expired or superseded")
        action, answer = params["action"], params["answer"]
        if (
            action not in ("accept", "decline", "cancel")
            or (answer is not None and not isinstance(answer, str))
            or (
                action == "accept"
                and (
                    not isinstance(answer, str)
                    or not answer.strip()
                    or (record.get("choices") and answer.strip() not in record["choices"])
                )
            )
        ):
            raise ProtocolError(-32602, "invalid displayed answer")
        marker = consent.claim_answer(host.record, "host:" + params["source_id"], None, "decision:" + key)
        if not marker:
            raise ProtocolError(-32003, "host answer already belongs to another question")
        # Retain the existing answer-consumption marker lifecycle without
        # relabeling this host callback as verified native transcript evidence.
        with decisions.locked(key) as filename:
            current = paths.read_json(filename)
            current["native_marker"] = marker
            paths.write_json(filename, current)
        reply = {"result": {"action": action, "content": {"answer": answer},
                            "_meta": {"approvals_reviewer": "user"}}}
        record = decisions.response(key, reply, "host-user", source_id=params["source_id"],
                                    displayed=params["displayed"])
        self.ui_answers[params["questionId"]] = {"session": token, "fingerprint": fingerprint, "decision": key}
        del self.ui_requests[key]
        return {"status": record["status"], "decision_id": key}

    def abandon_question(self, token, host, params):
        from . import decisions
        if "elicitation" not in host.client_caps:
            raise ProtocolError(-32004, "host has no user-interface capability")
        if set(params) != {"session", "questionId", "challenge"}:
            raise ProtocolError(-32602, "exact question route required")
        for key in ("questionId", "challenge"):
            if not isinstance(params[key], str) or not params[key]:
                raise ProtocolError(-32602, "invalid question route")
        selected = next(((key, item) for key, item in self.ui_requests.items()
                         if item["event"]["questionId"] == params["questionId"]), None)
        if not selected:
            raise ProtocolError(-32003, "question has no pending display")
        key, item = selected
        if (item["host"] is not host or item["event"]["session"] != token or
                not hmac.compare_digest(item["event"]["challenge"].encode(), params["challenge"].encode())):
            raise ProtocolError(-32003, "question host identity mismatch")
        record = decisions.abandon_display(key, host.instance_id)
        del self.ui_requests[key]
        return {"status": record["status"], "decision_id": key}


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
                try:
                    emit({"jsonrpc": "2.0", "id": mid, "result": result})
                except (ValueError, TypeError, RecursionError):
                    # Invalid backend output is not an invalid client request.
                    raise ProtocolError(-32603, "internal server error") from None
            except ProtocolError as exc:
                emit({"jsonrpc": "2.0", "id": mid, "error": {"code": exc.code, "message": exc.message}})
            except (ValueError, TypeError, ToolError) as exc:
                error = {"code": -32602, "message": str(exc)}
                if isinstance(exc, ToolError) and exc.data is not None:
                    error['data'] = exc.data
                emit({"jsonrpc": "2.0", "id": mid, "error": error})
            except Exception as exc:
                # A request can fail after a durable effect. Do not retry, ACK,
                # or expose backend details; the caller must reconcile state.
                emit({"jsonrpc": "2.0", "id": mid,
                      "error": {"code": -32603, "message": "internal server error"}})
                try:
                    sys.stderr.write("xsm protocol: internal request error (" + type(exc).__name__ + ")\n")
                except Exception:
                    pass
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
    from . import protocol_contract
    describe = actions.add_parser("describe", help="export this installation's experimental protocol contract as JSON")
    describe.set_defaults(func=protocol_contract.command)
    from . import host_install
    for action in ("install", "uninstall", "inspect"):
        parser = actions.add_parser(action, help=action + " a native host binding")
        parser.add_argument("runtime", choices=sorted(host_install.BINDINGS))
        parser.add_argument("--home", required=True, help="explicit native profile directory")
        if action != "inspect":
            parser.add_argument("--dry-run", action="store_true")
        parser.set_defaults(func=host_install.command)
