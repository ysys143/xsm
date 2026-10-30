"""Opt-in P2P service. Local messaging and legacy SSH never start this service.

The Unix control interface is private to the OS user. Remote requests carry an
origin supplied by the TLS transport, never by a message's JSON body. Invitations
are delivered through private files/stdin, not command arguments or diagnostics.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import time

from . import paths

MAX_FRAME = 8 * 1024 * 1024
PUBLIC_CODES = frozenset((
    "non-private-state-directory", "non-private-state-file", "invalid-state-file", "frame-too-large",
    "duplicate-json-key", "invalid-json", "object-required", "service-disconnected",
    "service-unavailable-or-response-unknown", "service-start-failed", "service-start-unknown",
    "invalid-endpoint-address", "invalid-active-network", "join-did-not-admit-this-device",
    "already-in-a-network", "invalid-invitation", "origin-mismatch", "join-refused-or-state-mismatch",
    "join-state-mismatch", "no-active-network", "unknown-operation", "peer-refused",
    "engine-build-source-or-toolchain-unavailable", "engine-build-failed", "invalid-port",
    "invalid-relay", "invalid-invitation-lifetime", "operation-failed", "request-failed",
    "join-response-unknown", "join-unreachable", "caller-unverified",
    "target-unavailable", "selection-required", "selection-unverified", "message-id-conflict",
    "admission-unavailable", "request-archived"))


class NetworkError(Exception):
    """Stable public error; secret payloads are never part of the message."""


class AdmissionUnavailable(NetworkError):
    """A temporary inability to evaluate policy, never a recorded refusal."""


def root():
    return Path(paths.path("network"))


def socket_path():
    key = hashlib.sha256(os.path.realpath(paths.HOME).encode()).hexdigest()[:24]
    return Path(tempfile.gettempdir()) / ("xsm-net-%d" % os.getuid()) / (key + ".sock")


def _private_directory(path):
    missing, current = [], path
    while not current.exists() and not current.is_symlink():
        missing.append(current)
        current = current.parent
    for item in reversed(missing):
        try:
            item.mkdir(mode=0o700)
        except FileExistsError:
            pass
    if path.is_symlink() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise NetworkError("non-private-state-directory")


def _read_private(path):
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > MAX_FRAME:
                raise NetworkError("non-private-state-file")
            return _decode(stream.read(MAX_FRAME + 1))
    except (ValueError, UnicodeError):
        raise NetworkError("invalid-state-file") from None


def _decode(raw):
    if len(raw) > MAX_FRAME:
        raise NetworkError("frame-too-large")
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise NetworkError("duplicate-json-key")
            result[k] = v
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError):
        raise NetworkError("invalid-json") from None
    if not isinstance(value, dict):
        raise NetworkError("object-required")
    return value


def _wire(value):
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    if len(raw) > MAX_FRAME:
        raise NetworkError("frame-too-large")
    return raw + b"\n"


def call(request, timeout=15):
    """One local RPC. A timeout is unknown, never automatic mutation replay."""
    try:
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(timeout)
            client.connect(str(socket_path()))
            client.sendall(_wire(request))
            with client.makefile("rb") as stream:
                raw = stream.readline(MAX_FRAME + 2)
            if not raw:
                raise NetworkError("service-disconnected")
            result = _decode(raw)
            if not result.get("ok"):
                code = result.get("code")
                raise NetworkError(code if isinstance(code, str) and code in PUBLIC_CODES else "request-failed")
            return result["result"]
    except (OSError, TimeoutError):
        raise NetworkError("service-unavailable-or-response-unknown") from None


def available():
    return socket_path().exists()


def note_native_reader(record):
    """Called only by this version's executed native hook, never MCP setup."""
    from .network_directory import public_endpoint
    try:
        handle = public_endpoint(record, "0" * 64)
        if handle is None:
            return False
        folder = root() / "native-readers"
        _private_directory(folder)
        key = hashlib.sha256(_wire(handle)).hexdigest()
        paths.write_json(str(folder / (key + ".json")), {"version": 1, "endpoint": handle})
        return True
    except (OSError, ValueError, TypeError, NetworkError):
        return False


def native_reader_ready(record):
    from .network_directory import public_endpoint
    try:
        handle = public_endpoint(record, "0" * 64)
        if handle is None:
            return False
        key = hashlib.sha256(_wire(handle)).hexdigest()
        return _read_private(root() / "native-readers" / (key + ".json")) == {
            "version": 1, "endpoint": handle}
    except (OSError, ValueError, TypeError, NetworkError):
        return False


def message_gateway(permission=None):
    from .network_messages import Gateway
    identity = _read_private(root() / "identity.json")
    active = _read_private(root() / "active.json")
    gateway = Gateway(root() / "messages", identity["endpoint_id"], permission or (lambda *args: False))
    gateway.network_id = active["network_id"]
    return gateway


def inbound_record(parsed, receiver=None):
    """Private admission evidence, not a peer-supplied origin/approval tag."""
    from . import envelope, handoff
    try:
        record = message_gateway().ingress_record(parsed.header.get("id"))
        if not record or parsed.header.get("origin") != "p2p:" + record["origin"]:
            return None
        packet = record["packet"]
        canonical = envelope.parse(message_gateway()._message(
            packet, record["target_local"], record.get("files"))["content"])
        if parsed.header != canonical.header:
            return None
        if receiver is not None and handoff._identity(receiver) != handoff._identity(record["target_local"]):
            return None
        if parsed.header.get("scope") != packet["scope"] or parsed.body != packet["body"] \
                or parsed.header.get("kind", "note") != packet["kind"] \
                or parsed.header.get("reply-to") != packet["reply_to"] \
                or parsed.header.get("outcome") != packet["outcome"] \
                or envelope.attachment_refs(parsed.attachments) != packet["attachments"]:
            return None
        if receiver is not None:
            try:
                fresh = call({"op": "admission", "caller": receiver,
                              "id": packet["id"]}, timeout=2)
            except NetworkError as exc:
                if str(exc) in ("no-active-network", "caller-unverified"):
                    return None
                raise AdmissionUnavailable("P2P admission temporarily unavailable") from None
            if fresh.get("allowed") is not True:
                return None
        return record
    except AdmissionUnavailable:
        raise
    except (OSError, ValueError, KeyError, TypeError, NetworkError):
        return None


def reconcile(msg_id, caller=None, wait=0):
    """Retrieve exact remote evidence without resending or creating a service."""
    from . import ledger, registry
    entry = ledger.status(msg_id)
    if not str(entry.get("scope") or "").startswith("network:"):
        return entry
    caller = caller or registry.me()
    target = (entry.get("to") or {}).get("ref")
    if not caller or not isinstance(target, str) or not target.startswith("net:"):
        return dict(entry, network_status="unknown", reason="caller-or-target-unverified")
    seconds = float(wait)
    if seconds < 0 or not math.isfinite(seconds):
        raise ValueError("network wait must be finite and nonnegative")
    deadline = time.monotonic() + seconds
    while True:
        try:
            delivery = call({"op": "message-status", "caller": caller,
                             "target": target, "id": msg_id}, timeout=min(5, max(1, seconds)))
        except NetworkError:
            return dict(ledger.status(msg_id), network_status="unknown")
        if delivery.get("stored"):
            ledger.reached(msg_id)
            ledger.step(msg_id, "remote_stored")
        if delivery.get("acknowledged"):
            # The receiver's canonical consumer ACK, not its socket/queue write.
            ledger.step(msg_id, "hook_taken", True, "authenticated remote canonical consumer ACK")
            ledger.receipt(msg_id, "delivered", {"ref": target}, "remote canonical consumer acknowledged")
        entry = ledger.status(msg_id)
        entry["network_delivery"] = delivery
        if delivery.get("acknowledged") or delivery.get("status") in ("held", "refused", "not-found") \
                or time.monotonic() >= deadline:
            return entry
        time.sleep(min(.2, max(0, deadline - time.monotonic())))


def start(timeout=15):
    """Start only our service; concurrent starts serialize in serve()."""
    try:
        return call({"op": "status"}, timeout=1)
    except NetworkError:
        pass
    folder = root()
    _private_directory(folder)
    err = os.open(folder / "service-errors.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    env = dict(os.environ, XSM_HOME=paths.HOME,
               PYTHONPATH=str(Path(__file__).resolve().parents[1]), PYTHONDONTWRITEBYTECODE="1")
    try:
        child = subprocess.Popen([sys.executable, "-B", "-m", "xsm.network", "serve"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=err, env=env, start_new_session=True)
    finally:
        os.close(err)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return call({"op": "status"}, timeout=.5)
        except NetworkError:
            if child.poll() is not None and child.returncode != 0:
                raise NetworkError("service-start-failed") from None
            if child.poll() == 0 and not socket_path().exists():
                # A former service can be releasing its lock after engine EOF.
                # Restarting a service is not replaying a business operation.
                err = os.open(folder / "service-errors.log", os.O_WRONLY | os.O_APPEND)
                try:
                    child = subprocess.Popen([sys.executable, "-B", "-m", "xsm.network", "serve"],
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=err,
                        env=env, start_new_session=True)
                finally:
                    os.close(err)
            time.sleep(.05)
    raise NetworkError("service-start-unknown")


def _address_id(address):
    if not isinstance(address, dict):
        raise NetworkError("invalid-endpoint-address")
    value = address.get("id") or address.get("endpoint_id")
    if not isinstance(value, str) or not value:
        raise NetworkError("invalid-endpoint-address")
    return value


class Daemon:
    def __init__(self, sidecar):
        self.transport = sidecar
        self.ready = None
        self._lock = threading.RLock()
        self._operator_lock = threading.RLock()
        self._peers = {}
        self._stop = threading.Event()
        self.server = None

    def store(self, directory=None):
        from .network_membership import MembershipStore
        if directory is None:
            try:
                active = _read_private(root() / "active.json")
            except FileNotFoundError:
                return None
            net = active.get("network_id")
            if not isinstance(net, str) or not net:
                raise NetworkError("invalid-active-network")
            directory = root() / "networks" / hashlib.sha256(net.encode()).hexdigest()
        return MembershipStore(directory, self.transport.endpoint_id,
                               self.transport.sign, self.transport.verify)

    def _install(self, state, initialize=None, expected_network=None):
        # The old active pointer survives every validation/write failure.
        staging = root() / "staging" / secrets.token_hex(16)
        _private_directory(staging)
        candidate = self.store(staging)
        if initialize is not None:
            candidate.initialize(*initialize)
        else:
            candidate.adopt(state)
        if expected_network is not None and candidate.network_id != expected_network:
            raise NetworkError("join-state-mismatch")
        if not candidate.is_active(self.transport.endpoint_id):
            raise NetworkError("join-did-not-admit-this-device")
        net = candidate.network_id
        dest = root() / "networks" / hashlib.sha256(net.encode()).hexdigest()
        _private_directory(dest.parent)
        if dest.exists():
            retained = self.store(dest)
            retained.merge(candidate.snapshot())
            if not retained.is_active(self.transport.endpoint_id):
                raise NetworkError("join-did-not-admit-this-device")
        else:
            os.rename(staging, dest)
        paths.write_json(str(root() / "active.json"), {"network_id": net})
        self._load_peers()
        return self.store()

    def _load_peers(self):
        current = self.store()
        self._peers = {}
        if current:
            saved = paths.read_json(str(root() / ("peers-" + hashlib.sha256(current.network_id.encode()).hexdigest() + ".json")), {})
            members = {m["endpoint_id"] for m in current.members()}
            if isinstance(saved, dict):
                self._peers = {k: v for k, v in saved.items() if k in members and isinstance(v, dict) and _address_id(v) == k}

    def status(self):
        self.refresh_address()
        store = self.store()
        return {"status": "running", "endpoint_id": self.transport.endpoint_id,
                "address": self.transport.address,
                "active": bool(store and store.is_active(self.transport.endpoint_id)),
                "network": store.public_state() if store else None,
                "transport": self.ready, "last_transport": self.transport.last_transport,
                "service_pid": os.getpid(), "engine_pid": self.transport.process_id,
                "known_peers": sorted(self._peers)}

    def refresh_address(self):
        # Iroh learns its relay/interface addresses after the initial ready
        # frame. Refresh the SDK cache through the real IPC result, rather than
        # publishing the startup-only address forever.
        try:
            self.transport.call("address", timeout=2)
        except Exception:
            return False
        return True

    def repositories(self):
        from .network_directory import RepositoryMap
        return RepositoryMap(root() / "repositories")

    def caller(self, record):
        from .network_directory import public_endpoint, resolve_local
        handle = public_endpoint(record, self.transport.endpoint_id)
        current = resolve_local(handle, self.transport.endpoint_id) if handle else None
        if current is None:
            raise NetworkError("caller-unverified")
        return current

    def peer_address(self, key):
        return self._peers.get(key) or {"id": key, "addrs": []}

    def _contacts(self):
        with self._lock:
            store = self.store()
            if not store or not store.is_active(self.transport.endpoint_id):
                return {}
            return {k: v for k, v in self._peers.items() if store.is_active(k)}

    def _learn_contacts(self, origin, packet):
        with self._lock:
            self._learn_contacts_locked(origin, packet)

    def _learn_contacts_locked(self, origin, packet):
        store = self.store()
        if not store or not store.is_active(origin) or not store.is_active(self.transport.endpoint_id):
            return
        candidates = dict(packet.get("contacts") or {})
        if len(candidates) > 128:
            raise NetworkError("invalid-endpoint-address")
        address = packet.get("address")
        if isinstance(address, dict) and _address_id(address) == origin:
            candidates[origin] = address
        changed = False
        for key, address in candidates.items():
            if key != self.transport.endpoint_id and store.is_active(key) \
                    and isinstance(address, dict) and _address_id(address) == key:
                # Contacts suggest a route, never an identity or permission.
                # QUIC still pins this member's authenticated endpoint key.
                if self._peers.get(key) != address:
                    self._peers[key] = address
                    changed = True
        if changed:
            self._save_peers()

    def gateway(self, permission=None):
        from .network_messages import Gateway
        store = self.store()
        if not store or not store.is_active(self.transport.endpoint_id):
            raise NetworkError("no-active-network")
        value = Gateway(root() / "messages", self.transport.endpoint_id,
                        permission or (lambda *args: False))
        value.network_id = store.network_id
        return value

    @staticmethod
    def _grant_payload(value):
        return b"xsm:selected-conversations:v1\x00" + json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False).encode("ascii")

    def _grant_file(self, sender, receiver):
        from .network_identity import endpoint
        pair = sorted((endpoint(sender), endpoint(receiver)),
                      key=lambda v: json.dumps(v, sort_keys=True))
        key = hashlib.sha256(self._grant_payload({"network": self.store().network_id,
                                                "pair": pair})).hexdigest()
        return root() / "selections" / (key + ".json")

    def _check_grant(self, grant, sender, receiver):
        from .network_identity import endpoint
        if not isinstance(grant, dict) or set(grant) != {"statement", "signature"}:
            return False
        value = grant["statement"]
        if not isinstance(value, dict) or set(value) != {
                "version", "network_id", "issuer", "sender", "receiver", "selection_id", "evidence_sha256"}:
            return False
        try:
            issuer = value["issuer"]
            a, b = endpoint(value["sender"]), endpoint(value["receiver"])
            pair = (endpoint(sender), endpoint(receiver))
            if value["version"] != 1 or value["network_id"] != self.store().network_id \
                    or issuer != a["machine"] or not self.store().is_active(issuer) \
                    or pair not in ((a, b), (b, a)) \
                    or not all(isinstance(value[k], str) and len(value[k]) == 64
                               and all(c in "0123456789abcdef" for c in value[k])
                               for k in ("selection_id", "evidence_sha256")):
                return False
            return self.transport.verify(issuer, self._grant_payload(value), grant["signature"])
        except (ValueError, TypeError, KeyError):
            return False

    def _grant(self, local, remote):
        # This attests an existing local human decision, never a peer ACK.
        from . import collaboration
        from .network_directory import public_endpoint
        from .network_identity import endpoint
        actual = self.caller(local)
        own = public_endpoint(actual, self.transport.endpoint_id)
        record = collaboration.scope_for(actual, remote)
        if record:
            value = {"version": 1, "network_id": self.store().network_id,
                     "issuer": self.transport.endpoint_id, "sender": endpoint(own),
                     "receiver": endpoint(remote), "selection_id": record["id"],
                     "evidence_sha256": hashlib.sha256(self._grant_payload(record)).hexdigest()}
            return {"statement": value, "signature": self.transport.sign(self._grant_payload(value))}
        try:
            saved = _read_private(self._grant_file(own, remote))
        except FileNotFoundError:
            return None
        return saved if self._check_grant(saved, own, remote) else None

    def _permission(self, origin, sender, local, repository_id=None, grant=None):
        from . import collaboration
        from .network_directory import public_endpoint
        own = public_endpoint(local, self.transport.endpoint_id)
        if sender.get("machine") != origin or own is None:
            return False
        if self.repositories().allows(origin, repository_id, local.get("cwd")):
            return True
        from . import teams
        if teams.scope_for(local, sender):
            # Both are members of one team this machine holds (ADR-0025, D19).
            return True
        try:
            saved = grant or _read_private(self._grant_file(sender, own))
        except FileNotFoundError:
            return False
        if not self._check_grant(saved, sender, own):
            return False
        # When this machine issued the selection, revocation is authoritative
        # here. The other direction is a signed member attestation of selection.
        if saved["statement"]["issuer"] == self.transport.endpoint_id:
            return collaboration.scope_for(local, sender) is not None
        try:
            retained = _read_private(self._grant_file(sender, own))
        except FileNotFoundError:
            return False
        return retained == saved

    def resolve_remote(self, caller, target):
        from .network_directory import public_endpoint
        from .network_identity import parse_target
        caller = self.caller(caller)
        address = parse_target(target)
        if address is None or address["machine"] == self.transport.endpoint_id:
            raise NetworkError("target-unavailable")
        grant = self._grant(caller, address)
        result = self.rpc(self.peer_address(address["machine"]), {"op": "resolve",
            "caller": public_endpoint(caller, self.transport.endpoint_id), "target": address,
            "repository_id": self.repositories().for_local(caller["cwd"], address["machine"]),
            "authorization": grant})
        return {"target": result["target"], "scope": result.get("scope"),
                "scope_basis": result.get("scope_basis")}

    def publish_team(self, team):
        """Send a team record to the machines of its remote members (ADR-0025).
        The record is what this machine holds; members are sent as endpoints."""
        from . import team_sync
        record = team_sync.to_endpoints(team, self.transport.endpoint_id)
        machines = sorted({m["machine"] for m in record["members"]
                           if m and m.get("machine") and m["machine"] != self.transport.endpoint_id})
        published, failed = [], []
        for machine in machines:
            try:
                answer = self.rpc(self.peer_address(machine), {"op": "team", "team": record})
                status = (answer.get("result") or {}).get("status")
                (published if status in ("updated", "stale") else failed).append(
                    {"machine": machine, "status": status} if status in ("updated", "stale")
                    else {"machine": machine, "code": status or "refused"})
            except NetworkError as exc:
                failed.append({"machine": machine, "code": str(exc)})
        return {"published": published, "failed": failed}

    def publish_board(self, request):
        """Send board nodes to the machines of the team's remote members (ADR-0026)."""
        published, failed = [], []
        for machine in sorted(set(request.get("machines") or [])):
            if machine == self.transport.endpoint_id:
                continue
            try:
                answer = self.rpc(self.peer_address(machine), {"op": "board-nodes",
                    "team": request["team"], "team_id": request["team_id"], "nodes": request["nodes"],
                    "decisions": request.get("decisions") or []})
                published.append({"machine": machine, **(answer.get("result") or {})})
            except NetworkError as exc:
                failed.append({"machine": machine, "code": str(exc)})
        return {"published": published, "failed": failed}

    def select_remote(self, caller, target):
        from .network_directory import public_endpoint
        caller = self.caller(caller)
        current = self.resolve_remote(caller, target)["target"]
        grant = self._grant(caller, current)
        if grant is None or grant["statement"]["issuer"] != self.transport.endpoint_id:
            raise NetworkError("selection-unverified")
        self.rpc(self.peer_address(current["machine"]), {"op": "selection",
            "caller": public_endpoint(caller, self.transport.endpoint_id), "target": current,
            "authorization": grant})
        return {"status": "selected", "target": current}

    def send_remote(self, request):
        from . import envelope, ledger, send
        from .network_messages import GatewayError
        caller = self.caller(request["caller"])
        resolved = self.resolve_remote(caller, request["target"])
        target = resolved["target"]
        if send.priority_refusal(target, request.get("priority", "next")):
            raise NetworkError("target-unavailable")
        grant = self._grant(caller, target)
        gateway = self.gateway()
        msg_id = request.get("id") or envelope.new_id()
        try:
            packet = gateway.prepare(caller, {k: target[k] for k in (
                "machine", "runtime", "home_id", "session_id", "generation")}, request["body"],
                request_id=msg_id, kind=request.get("kind", "note"), reply_to=request.get("reply_to"),
                outcome=request.get("outcome"), priority=request.get("priority", "next"),
                wake=request.get("wake", True), attachments=request.get("attachments") or (),
                file_packet=request.get("file_packet"), prepared_intent=bool(ledger.status(msg_id)))
        except GatewayError as exc:
            if exc.code == "request-archived":
                raise NetworkError("request-archived") from None
            if exc.code in ("message-id-conflict", "prepared-intent-unverified"):
                raise NetworkError("message-id-conflict") from None
            raise
        if not resolved.get("scope") and packet["kind"] != "reply":
            raise NetworkError("selection-required")
        ledger.queued(msg_id, caller, target, packet["scope"], packet["kind"], packet["body"],
            reply_to=packet["reply_to"], outcome=packet["outcome"], priority=packet["priority"],
            attachments=packet["attachments"])
        try:
            result = self.rpc(self.peer_address(target["machine"]), {"op": "deliver", "packet": packet,
                "repository_id": self.repositories().for_local(caller["cwd"], target["machine"]),
                "authorization": grant})
        except Exception:
            ledger.unknown(msg_id, "network-response-unknown; retrieve status using the same ID")
            return {"id": msg_id, "status": "unknown", "target": target,
                    "reason": "network-response-unknown; retrieve status using the same ID"}
        delivery = result["delivery"]
        ledger.step(msg_id, "remote_stored", delivery.get("stored") is True)
        if delivery.get("acknowledged"):
            ledger.step(msg_id, "hook_taken", True, "authenticated remote canonical consumer ACK")
            ledger.receipt(msg_id, "delivered", {"ref": target["ref"]}, "remote canonical consumer acknowledged")
        return {"id": msg_id, "status": "delivered" if delivery.get("acknowledged") else
                "sent-unconfirmed" if delivery.get("stored") else delivery.get("status", "unknown"),
                "target": target, "reason": "stored remotely; native consumption is reported separately",
                "delivery": delivery}

    def admission(self, request):
        from . import handoff, probe
        with probe.observe_unavailable() as observed:
            try:
                caller = self.caller(request["caller"])
                # A positively verified caller may lack unrelated display
                # metadata. That cannot turn a later known scope denial into
                # an outage. Failures that prevent caller verification still
                # reach the exception mapping below.
                observed["unavailable"] = False
                record = self.gateway().ingress_record(request["id"])
                if not record or handoff._identity(caller) != handoff._identity(record["target_local"]):
                    allowed = False
                else:
                    policy = _read_private(root() / "ingress-policy" / (record["id"] + ".json"))
                    packet, store = record["packet"], self.store()
                    allowed = policy.get("fingerprint") == record["fingerprint"] \
                        and store.is_active(record["origin"]) and store.is_active(self.transport.endpoint_id) \
                        and (packet["kind"] == "reply" or self._permission(record["origin"], packet["sender"],
                            caller, policy.get("repository_id"), policy.get("authorization")))
            except NetworkError:
                if observed["unavailable"]:
                    raise NetworkError("admission-unavailable") from None
                raise
            if not allowed and observed["unavailable"]:
                raise NetworkError("admission-unavailable")
            return {"allowed": bool(allowed)}

    def wake_native(self, packet):
        from . import adapters, handoff
        from .network_directory import resolve_local
        local = resolve_local(packet["receiver"], self.transport.endpoint_id)
        if not local or not packet["wake"] or not native_reader_ready(local):
            return
        current = handoff.status(local, packet["id"])
        if current["status"] == "acknowledged" or current.get("delivery_route") != "mcp-inbox":
            return
        # The canonical claim/ACK remains the duplicate boundary for both the
        # native queue and MCP. A queue write is not native consumption.
        try:
            handoff.delivery(local, packet["id"], "pending", route="native")
            content = current["message"]["content"]
            if local["runtime"] == "claude":
                if not local.get("socket"):
                    raise ValueError("no-native-socket")
                adapters.to_claude(local["socket"], content, packet["id"], priority=packet["priority"])
            else:
                adapters.to_codex(local["home"], local["session_id"], content)
        except (adapters.DeliveryError, OSError, ValueError):
            handoff.delivery(local, packet["id"], "pending", route="mcp-inbox")

    def wake_safely(self, packet):
        try:
            self.wake_native(packet)
        except Exception:
            # The durable canonical original remains. Background failures must
            # not print native/peer payloads through Python thread tracebacks.
            return

    def discovery(self, caller, machine=None, work=None, branch=None):
        from .network_directory import public_endpoint
        caller = self.caller(caller)
        store = self.store()
        if not store or not store.is_active(self.transport.endpoint_id):
            return {"candidates": [], "status": "unknown", "reason": "no-active-network"}
        candidates, unanswered = [], {}
        for member in store.members():
            key = member["endpoint_id"]
            if key == self.transport.endpoint_id or member["status"] != "active":
                continue
            if machine and machine.casefold() not in (key.casefold(), member["machine_name"].casefold()) \
                    and machine.casefold() not in member["machine_name"].casefold():
                continue
            try:
                answer = self.rpc(self.peer_address(key), {"op": "directory",
                    "caller": public_endpoint(caller, self.transport.endpoint_id),
                    "repository_id": self.repositories().for_local(caller["cwd"], key),
                    "work": work, "branch": branch})
                for row in answer["candidates"]:
                    row["machine_name"] = member["machine_name"]
                    row["origin_assurance"] = "authenticated-member"
                    candidates.append(row)
            except Exception:
                unanswered[key] = "peer-unavailable-or-policy-unknown"
        return {"candidates": candidates, "status": "unknown" if unanswered else "ok",
                "reason": "peer-unavailable" if unanswered else None, "unanswered": unanswered}

    def _join(self, ticket, machine_name):
        issuer = ticket.get("issuer")
        _address_id(issuer)
        contacts = [issuer]
        if ticket.get("reusable") is True:
            contacts += ticket.get("peers", [])
        seen = set()
        invite_hash = hashlib.sha256(ticket["secret"].encode()).hexdigest()
        for peer in contacts:
            expected = _address_id(peer)
            if expected in seen:
                continue
            seen.add(expected)
            try:
                response = self.transport.request(peer, {
                    "op": "join", "network_id": ticket["network_id"], "secret": ticket["secret"],
                    "machine_name": machine_name, "address": self.transport.address}, timeout=30)
            except Exception as exc:
                if getattr(exc, "code", None) == "connect_failed":
                    # The application stream was never opened. Only this
                    # definite-unreached case may try another online member.
                    continue
                try:
                    response = self.transport.request(peer, {"op": "join-status",
                        "network_id": ticket["network_id"], "invite_hash": invite_hash}, timeout=10)
                except Exception:
                    raise NetworkError("join-response-unknown") from None
                if not response.get("body", {}).get("ok"):
                    raise NetworkError("join-response-unknown") from None
            if response["origin"] != expected:
                raise NetworkError("origin-mismatch")
            result = response["body"]
            if not result.get("ok") or result.get("network_id") != ticket["network_id"]:
                raise NetworkError("join-refused-or-state-mismatch")
            with self._lock:
                self._install(result["state"], expected_network=ticket["network_id"])
                self._peers[expected] = peer
                self._learn_contacts(expected, result)
                self._save_peers()
            return self.status()
        raise NetworkError("join-unreachable")

    def local(self, request):
        # Serialize local mutations without holding the incoming-network lock
        # across RPCs. Two machines may discover/join each other concurrently.
        if request.get("op") in ("init", "join", "invite", "remove", "leave", "revoke-invite", "map-repository"):
            with self._operator_lock:
                return self._local(request)
        return self._local(request)

    def _local(self, request):
        op = request.get("op")
        if op == "status":
            return self.status()
        if op == "stop":
            self._stop.set()
            if self.server:
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            return {"status": "stopping"}
        if op == "join":
            ticket = request.get("ticket")
            if not isinstance(ticket, dict) or ticket.get("version") != 1:
                raise NetworkError("invalid-invitation")
            return self._join(ticket, request.get("machine_name") or socket.gethostname())
        if op == "discover":
            return self.discovery(request["caller"], request.get("machine"), request.get("work"), request.get("branch"))
        if op == "resolve":
            return self.resolve_remote(request["caller"], request["target"])
        if op == "selection":
            return self.select_remote(request["caller"], request["target"])
        if op == "team-publish":
            return self.publish_team(request["team"])
        if op == "board-publish":
            return self.publish_board(request)
        if op == "send":
            return self.send_remote(request)
        if op == "admission":
            return self.admission(request)
        if op == "capabilities":
            from .network_directory import public_endpoint
            caller = self.caller(request["caller"])
            target = self.resolve_remote(caller, request["target"])["target"]
            answer = self.rpc(self.peer_address(target["machine"]), {"op": "capabilities",
                "caller": public_endpoint(caller, self.transport.endpoint_id), "target": target,
                "repository_id": self.repositories().for_local(caller["cwd"], target["machine"]),
                "authorization": self._grant(caller, target)})
            return {"capabilities": answer["capabilities"]}
        if op == "message-status":
            from .network_directory import public_endpoint
            from .network_identity import parse_target
            caller = self.caller(request["caller"])
            target = parse_target(request["target"])
            if target is None:
                raise NetworkError("target-unavailable")
            return self.rpc(self.peer_address(target["machine"]), {"op": "message-status",
                "caller": public_endpoint(caller, self.transport.endpoint_id), "id": request["id"]})["delivery"]
        with self._lock:
            store = self.store()
            if op == "init":
                if store:
                    raise NetworkError("already-in-a-network")
                self._install(None, (request["name"], request.get("machine_name") or socket.gethostname()))
                return self.status()
            if not store:
                raise NetworkError("no-active-network")
            if op == "map-repository":
                value = self.repositories().bind(request["path"], request["repository_id"], request["peer_keys"])
                return {"status": "mapped", "repository_id": request["repository_id"]}
            if op == "members":
                return {"network_id": store.network_id, "members": store.members()}
            if op == "invite":
                self.refresh_address()
                item = store.issue_invite(reusable=request.get("reusable", True),
                                          lifetime_seconds=request.get("lifetime_seconds"))
                ticket = {"version": 1, "network_id": store.network_id,
                          "issuer": self.transport.address, "secret": item["secret"],
                          "peers": [v for k, v in self._peers.items() if store.is_active(k)],
                          "reusable": request.get("reusable", True)}
                folder = root() / "invites"
                _private_directory(folder)
                target = folder / (secrets.token_hex(16) + ".json")
                paths.write_json(str(target), ticket)
                return {"network_id": store.network_id, "ticket_file": str(target),
                        "reusable": ticket["reusable"]}
            if op == "remove":
                store.remove(request["endpoint_id"])
                return {"status": "removed", "endpoint_id": request["endpoint_id"]}
            if op == "revoke-invite":
                store.revoke_invite(request["invite_hash"])
                return {"status": "revoked"}
            if op == "leave":
                store.leave()
                return {"status": "left"}
        if op == "ping":
            peer = request["peer"]
            if isinstance(peer, str):
                peer = self.peer_address(peer)
            return self.rpc(peer, {"op": "ping"})
        raise NetworkError("unknown-operation")

    def _save_peers(self):
        store = self.store()
        if store:
            paths.write_json(str(root() / ("peers-" + hashlib.sha256(store.network_id.encode()).hexdigest() + ".json")), self._peers)

    def rpc(self, peer, request):
        store = self.store()
        if not store:
            raise NetworkError("no-active-network")
        if request.get("op") != "sync" and (not store.is_active(self.transport.endpoint_id)
                                             or not store.is_active(_address_id(peer))):
            raise NetworkError("peer-refused")
        if request.get("op") == "sync" and not any(m["endpoint_id"] == _address_id(peer) for m in store.members()):
            raise NetworkError("peer-refused")
        packet = dict(request, network_id=store.network_id, address=self.transport.address)
        if request.get("op") in ("sync", "ping"):
            packet["state"] = store.snapshot()
            packet["contacts"] = self._contacts()
        response = self.transport.request(peer, packet, timeout=30)
        if response["origin"] != _address_id(peer):
            raise NetworkError("origin-mismatch")
        body = response["body"]
        if not body.get("ok"):
            if body.get("policy"):
                # Only signed, pinned-root membership data is accepted here.
                # This is never a peer's plaintext claim of a permission.
                store.merge(body["policy"])
            raise NetworkError("peer-refused")
        if body.get("state"):
            store.merge(body["state"])
        self._learn_contacts(response["origin"], body)
        return body

    def incoming(self, origin, request):
        try:
            with self._lock:
                store = self.store()
                if not store or not isinstance(request, dict) or request.get("network_id") != store.network_id:
                    return {"ok": False, "code": "network-unavailable"}
                op = request.get("op")
                if op == "join":
                    store.redeem(request.get("secret", ""), origin, request.get("machine_name", ""))
                else:
                    # A signed admission from another member can arrive before
                    # gossip. Merge validates the pinned root and every record.
                    was_active = store.is_active(origin)
                    if request.get("state"):
                        store.merge(request["state"])
                    self._learn_contacts(origin, request)
                    if op == "sync":
                        # Signed roster replication can deliver removal of its
                        # own sender. It never delivers work or private sessions.
                        if was_active or store.is_active(origin):
                            result = {"ok": True, "network_id": store.network_id,
                                      "status": "policy-updated"}
                            if store.is_active(origin) and store.is_active(self.transport.endpoint_id):
                                result.update(contacts=self._contacts(), address=self.transport.address)
                            return result
                    if not store.is_active(origin) or not store.is_active(self.transport.endpoint_id):
                        result = {"ok": False, "code": "not-an-active-member"}
                        if any(m["endpoint_id"] == origin for m in store.members()):
                            # The signed roster has no bearer secrets. A known
                            # removed device can learn its removal, not sessions.
                            result["policy"] = store.snapshot()
                        return result
                self._learn_contacts(origin, request)
                if op == "join-status":
                    if not any(r.get("op") == "admit" and r.get("endpoint_id") == origin
                               and r.get("invite_hash") == request.get("invite_hash")
                               for r in store.snapshot()["records"]):
                        return {"ok": False, "code": "join-not-confirmed"}
                if op == "directory":
                    from .network_directory import local_candidates
                    from .network_identity import endpoint
                    caller = endpoint(request.get("caller"))
                    if caller["machine"] != origin:
                        return {"ok": False, "code": "origin-mismatch"}
                    return {"ok": True, "candidates": local_candidates(origin, request.get("repository_id"),
                        self.repositories(), self.transport.endpoint_id,
                        work=request.get("work"), branch=request.get("branch"))}
                if op in ("resolve", "selection", "capabilities"):
                    return self._incoming_target(origin, request)
                if op == "board-nodes":
                    from . import board_sync
                    try:
                        return {"ok": True, "result": board_sync.receive(
                            origin, request.get("team"), request.get("team_id"), request.get("nodes"),
                            request.get("decisions"))}
                    except ValueError:
                        return {"ok": False, "code": "invalid-board"}
                if op == "team":
                    from . import team_sync
                    try:
                        return {"ok": True, "result": team_sync.receive(
                            origin, request.get("team"), self.transport.endpoint_id)}
                    except ValueError:
                        return {"ok": False, "code": "invalid-team"}
                if op == "deliver":
                    packet = request["packet"]
                    if packet.get("attachments"):
                        from . import registry
                        from .network_directory import resolve_local
                        target = resolve_local(packet.get("receiver"), self.transport.endpoint_id)
                        capability = registry.file_capability(target)
                        if capability.get("status") != "observed" or capability.get("version") != 1:
                            return {"ok": False, "code": "unsupported-files-capability"}
                    permission = lambda peer, sender, local, packet: self._permission(
                        peer, sender, local, request.get("repository_id"), request.get("authorization"))
                    delivery = self.gateway(permission).receive(origin, request["packet"])
                    folder = root() / "ingress-policy"
                    _private_directory(folder)
                    packet = request["packet"]
                    paths.write_json(str(folder / (packet["id"] + ".json")), {
                        "fingerprint": packet["fingerprint"], "repository_id": request.get("repository_id"),
                        "authorization": request.get("authorization")})
                    if delivery.get("stored") and not delivery.get("acknowledged"):
                        threading.Thread(target=self.wake_safely, args=(request["packet"],), daemon=True).start()
                    return {"ok": True, "delivery": delivery}
                if op == "message-status":
                    return {"ok": True, "delivery": self.gateway().status(
                        origin, request["id"], request.get("caller"))}
                if op in ("join", "join-status", "sync", "ping"):
                    return {"ok": True, "network_id": store.network_id,
                            "endpoint_id": self.transport.endpoint_id, "state": store.snapshot(),
                            "contacts": self._contacts(), "address": self.transport.address}
                return {"ok": False, "code": "unknown-operation"}
        except Exception:
            # Do not reflect peer-controlled errors, invite secrets or state.
            return {"ok": False, "code": "invalid-or-unauthorized-request"}

    def _incoming_target(self, origin, request):
        from . import directory, registry
        from .network_directory import local_candidates, public_endpoint, resolve_local
        from .network_identity import endpoint, target as format_target
        sender, wanted = endpoint(request.get("caller")), endpoint(request.get("target"))
        if sender["machine"] != origin or wanted["machine"] != self.transport.endpoint_id:
            return {"ok": False, "code": "origin-mismatch"}
        # A stable conversation key resolves only to its actual current native
        # generation. Neither a display name nor a new CID is substituted.
        handles = [public_endpoint(r, self.transport.endpoint_id) for r in registry.raw_records()]
        handles = [h for h in handles if h is not None and endpoint(h) == wanted]
        if len(handles) != 1:
            return {"ok": False, "code": "target-unavailable"}
        handle = handles[0]
        local = resolve_local(handle, self.transport.endpoint_id)
        if local is None:
            return {"ok": False, "code": "target-unavailable"}
        rows = local_candidates(origin, request.get("repository_id"), self.repositories(), self.transport.endpoint_id)
        candidate = next((r for r in rows if r["handle"] == handle), None)
        grant = request.get("authorization")
        permitted = self._permission(origin, sender, local, request.get("repository_id"), grant)
        if request["op"] == "selection":
            if candidate is None or not self._check_grant(grant, sender, handle) \
                    or grant["statement"]["issuer"] != origin:
                return {"ok": False, "code": "selection-unverified"}
            folder = root() / "selections"
            _private_directory(folder)
            paths.write_json(str(self._grant_file(sender, handle)), grant)
            return {"ok": True, "status": "selected"}
        if candidate is None and not permitted:
            return {"ok": False, "code": "target-unavailable"}
        if request["op"] == "capabilities":
            if not permitted:
                return {"ok": False, "code": "selection-required"}
            observed = registry.file_capability(local)
            # Process IDs are local evidence, never network discovery metadata.
            return {"ok": True, "capabilities": {k: observed[k] for k in
                    ("status", "version", "source", "observed_at", "reason") if k in observed}}
        result = dict(candidate or {}, **handle, handle=handle, remote=True,
                      registered=True, ref=format_target(handle), target=format_target(handle))
        same = self.repositories().allows(origin, request.get("repository_id"), local.get("cwd"))
        return {"ok": True, "target": result,
                "scope": "network:" + self.store().network_id if permitted else None,
                "scope_basis": "same-repository" if same else "selected" if permitted else None}

    def synchronize(self):
        while not self._stop.wait(2):
            self.refresh_address()
            for key, peer in list(self._peers.items()):
                try:
                    self.rpc(peer, {"op": "sync"})
                except Exception:
                    continue

    def watch_engine(self):
        while not self._stop.wait(.2):
            if not self.transport.running:
                self._stop.set()
                if self.server:
                    self.server.shutdown()
                return


def serve():
    from .network_transport import Sidecar
    folder = root()
    _private_directory(folder)
    lock = os.open(folder / "service.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(lock)
        return 0
    location = socket_path()
    _private_directory(location.parent)
    sidecar = None
    try:
        try:
            settings = _read_private(folder / "settings.json")
        except FileNotFoundError:
            settings = {}
        sidecar = Sidecar(folder / "transport", port=settings.get("port", 0),
                          relay=settings.get("relay"), direct_addresses=settings.get("direct_addresses", ()))
        daemon = Daemon(sidecar)
        daemon.ready = sidecar.start()
        paths.write_json(str(folder / "identity.json"), {"endpoint_id": sidecar.endpoint_id})
        sidecar.set_request_handler(daemon.incoming)
        daemon._load_peers()

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.request.settimeout(60)
                try:
                    request = _decode(self.rfile.readline(MAX_FRAME + 2))
                    result = {"ok": True, "result": daemon.local(request)}
                except NetworkError as exc:
                    result = {"ok": False, "code": str(exc)}
                except Exception:
                    result = {"ok": False, "code": "operation-failed"}
                try:
                    self.wfile.write(_wire(result))
                except OSError:
                    pass

        class Server(socketserver.ThreadingUnixStreamServer):
            daemon_threads = True

        # The service lock proves the previous listener has no live owner.
        if location.exists():
            location.unlink()
        daemon.server = Server(str(location), Handler)
        os.chmod(location, 0o600)
        threading.Thread(target=daemon.synchronize, daemon=True).start()
        threading.Thread(target=daemon.watch_engine, daemon=True).start()
        daemon.server.serve_forever(poll_interval=.1)
        daemon._stop.set()
        daemon.server.server_close()
        return 0
    finally:
        if sidecar:
            sidecar.close()
        if location.exists():
            location.unlink()
        os.close(lock)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="xsm-network")
    parser.add_argument("command", choices=["serve"])
    args = parser.parse_args(argv)
    try:
        return serve()
    except Exception:
        print("xsm network: service-start-failed", file=sys.stderr)
        return 4


def configure_parser(subparsers):
    net = subparsers.add_parser("network", help="manage opt-in P2P networking and device membership")
    net.set_defaults(func=command)
    actions = net.add_subparsers(dest="network_action", required=True)
    for name in ("start", "stop", "status", "members", "address", "build"):
        actions.add_parser(name).set_defaults(func=command)
    recover = actions.add_parser("requests", help="list this conversation's saved outgoing originals without starting networking")
    recover.add_argument("--archived", action="store_true")
    recover.set_defaults(func=command)
    export = actions.add_parser("export", help="export one caller-owned original to a new private file")
    export.add_argument("request_id")
    export.add_argument("--output", required=True)
    export.set_defaults(func=command)
    archive = actions.add_parser("archive", help="hide a pending original without deleting it or cancelling remote work")
    archive.add_argument("request_id")
    archive.set_defaults(func=command)
    init = actions.add_parser("init")
    init.add_argument("name")
    init.add_argument("--machine-name")
    init.set_defaults(func=command)
    invite = actions.add_parser("invite", help="write an invitation to a private file; never print its secret")
    invite.add_argument("--once", action="store_true")
    invite.add_argument("--expires", type=int, help="lifetime in seconds; one-time default is 86400, reusable default is unlimited")
    invite.set_defaults(func=command)
    join = actions.add_parser("join")
    source = join.add_mutually_exclusive_group(required=True)
    source.add_argument("--ticket-file")
    source.add_argument("--ticket-stdin", action="store_true")
    join.add_argument("--machine-name")
    join.set_defaults(func=command)
    remove = actions.add_parser("remove")
    remove.add_argument("endpoint_id")
    remove.set_defaults(func=command)
    revoke = actions.add_parser("revoke-invite")
    revoke.add_argument("invite_hash")
    revoke.set_defaults(func=command)
    actions.add_parser("leave").set_defaults(func=command)
    cfg = actions.add_parser("configure")
    cfg.add_argument("--port", type=int)
    cfg.add_argument("--relay", help="public, off, or a custom HTTPS relay URL")
    cfg.add_argument("--direct-address", action="append")
    cfg.set_defaults(func=command)
    discover = actions.add_parser("sessions", help="find permitted remote native conversations")
    for key in ("machine", "work", "branch"):
        discover.add_argument("--" + key)
    discover.set_defaults(func=command)
    mapping = actions.add_parser("map-repository", help="record an explicit cross-machine repository mapping")
    mapping.add_argument("path")
    mapping.add_argument("--repository-id", default=None)
    mapping.add_argument("--peer", required=True, action="append")
    mapping.set_defaults(func=command)


def build_engine():
    """Build the locked source explicitly; never install global configuration."""
    import shutil
    source = Path(__file__).resolve().parents[1] / "native" / "xsm-net"
    if not (source / "Cargo.lock").exists() or not shutil.which("cargo"):
        raise NetworkError("engine-build-source-or-toolchain-unavailable")
    result = subprocess.run(["cargo", "build", "--release", "--locked"], cwd=source,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise NetworkError("engine-build-failed")
    binary = source / "target" / "release" / "xsm-net"
    folder = root() / "bin"
    _private_directory(folder)
    dest = folder / "xsm-net"
    fd, staged = tempfile.mkstemp(dir=folder, prefix=".engine-")
    try:
        with os.fdopen(fd, "wb") as out, binary.open("rb") as incoming:
            shutil.copyfileobj(incoming, out)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(staged, 0o700)
        os.replace(staged, dest)
    finally:
        if os.path.exists(staged):
            os.unlink(staged)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    paths.write_json(str(folder / "supply.json"), {"sha256": digest, "source": "local-locked-build",
                                                 "signature": "not-verified"})
    return {"status": "installed", "path": str(dest), "sha256": digest,
            "source": "local-locked-build", "signature": "not-verified"}


def command(args):
    action = args.network_action
    try:
        if action in ("requests", "export", "archive"):
            from . import context, network_recovery, registry
            caller, caller_context = registry.me_context()
            if not caller or context.require_sure(caller_context, "recover the saved outgoing original"):
                raise NetworkError("caller-unverified")
            if action == "requests":
                result = {"requests": network_recovery.requests(caller, args.archived)}
            elif action == "export":
                result = network_recovery.export(caller, args.request_id, args.output)
            else:
                result = network_recovery.archive(caller, args.request_id)
        elif action == "build":
            result = build_engine()
        elif action == "start":
            result = start()
        elif action == "configure":
            try:
                settings = _read_private(root() / "settings.json")
            except FileNotFoundError:
                settings = {}
            if args.port is not None:
                if not 0 <= args.port <= 65535:
                    raise NetworkError("invalid-port")
                settings["port"] = args.port
            if args.relay is not None:
                if args.relay not in ("public", "off"):
                    from urllib.parse import urlsplit
                    url = urlsplit(args.relay)
                    local = url.hostname in ("localhost", "127.0.0.1", "::1")
                    if (url.scheme != "https" and not (local and url.scheme == "http")) or not url.hostname \
                            or url.username is not None or url.password is not None or url.query or url.fragment:
                        raise NetworkError("invalid-relay")
                settings["relay"] = None if args.relay == "public" else args.relay
            if args.direct_address is not None:
                settings["direct_addresses"] = args.direct_address
            _private_directory(root())
            paths.write_json(str(root() / "settings.json"), settings)
            result = {"status": "saved", "effective": "on-next-start", "settings": settings}
        elif action == "status" and not available():
            result = {"status": "stopped", "active": False}
        else:
            if action in ("init", "join"):
                start()
            req = {"op": "status" if action == "address" else action}
            if action == "init":
                req.update(name=args.name, machine_name=args.machine_name)
            elif action == "invite":
                if args.expires is not None and args.expires <= 0:
                    raise NetworkError("invalid-invitation-lifetime")
                req.update(reusable=not args.once,
                           lifetime_seconds=args.expires if args.expires is not None else
                           86400 if args.once else None)
            elif action == "join":
                ticket = _decode(sys.stdin.buffer.read(MAX_FRAME + 1)) if args.ticket_stdin else _read_private(args.ticket_file)
                req.update(ticket=ticket, machine_name=args.machine_name)
            elif action == "remove":
                req["endpoint_id"] = args.endpoint_id
            elif action == "revoke-invite":
                req["invite_hash"] = args.invite_hash
            elif action == "map-repository":
                req.update(path=os.path.realpath(os.path.expanduser(args.path)),
                           repository_id=args.repository_id or secrets.token_hex(16), peer_keys=args.peer)
            elif action == "sessions":
                from . import registry
                req.update(op="discover", caller=registry.me(), machine=args.machine,
                           work=args.work, branch=args.branch)
            result = call(req, timeout=60)
            if action == "address":
                result = {"endpoint_id": result["endpoint_id"], "address": result["address"]}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (NetworkError, OSError, ValueError) as exc:
        # Never put input tickets or peer-controlled errors in CLI telemetry.
        code = str(exc) if isinstance(exc, NetworkError) and str(exc) in PUBLIC_CODES else "operation-failed"
        print(json.dumps({"status": "error", "code": code,
                          "recover_at": {"cli": ["xsm", "network", "status"]}}))
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
