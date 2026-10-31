"""Durable P2P body gateway, not caller authentication or native transport.

The coordinator MUST supply permission and set gateway.network_id from its
verified active membership. No role/approval/signature in peer data grants rights.
prepare returns a JSON wire packet; receive persists a pending mcp-inbox original.
status requires the original sender's exact public endpoint as caller_public.
ingress_record is PRIVATE gate evidence, never a remote RPC response.

Wire packet v1 uses id/network_id/sender/receiver/body/kind/reply_to/outcome/
priority/wake/scope/attachments/file_packet/fingerprint/reply_binding. Public
handles include generation, but request_fingerprint excludes it and display.
Reply binding is {id: original request ID, fingerprint: original network digest}.
Delivery status is queued/held/etc until the canonical handoff is acknowledged.
final_reply contains at most one exact reverse-bound packet; replies contains
metadata only. A prepared final reply does not prove remote receipt or reading.
ingress_record verifies immutable canonical source/body/file-context binding;
the current gate still evaluates current caller/session/traffic policy itself.
Durable packets retain only file manifests/references, never file_packet.data.
prepare and status reply packets obtain live bytes only from the quota/TTL file
store; an expired/unavailable copy cannot be resurrected from gateway records.
compact_legacy_payload(direction, id) is explicit single-record cache cleanup.

Broker API:
  Gateway(root, node_id, permission)  # callback is mandatory, returns bool
  gateway.network_id = verified_active_network_id
  gateway.prepare(sender_local, target_public, body, *, request_id, kind='note',
      reply_to=None, outcome=None, priority='next', wake=True, attachments=(),
      file_packet=None, prepared_intent=False) -> wire packet
  gateway.receive(tls_origin, packet) -> delivery evidence
  gateway.status(tls_origin, request_id, caller_public=None) -> owned evidence
  gateway.ingress_record(message_id) -> private verified binding or None
  request_fingerprint(packet) / source_fingerprint(packet) -> network SHA-256

prepared_intent=True is an OUTBOUND FIRST-PREPARE exception only: a preexisting
queued ledger row must have the exact canonical native-local sender -> opaque
receiver digest, canonical version, body/kind/reply/outcome/priority/refs, and
scope='network:'+network_id. The ledger's target ref must be absent or exactly
network_identity.target(receiver). Ref aliases/names/URLs do not qualify. The
Gateway reads but never rewrites that row. This local intent digest differs
from the wire fingerprint, whose sender AND receiver are opaque. The flag is
not a wire field and grants no receiver permission. Broker send_remote must
explicitly opt in for questions.ask's prequeued intent.

Duplicate rules: same ID must retain exact original bytes/body, opaque endpoints,
semantic fingerprint, wake policy, files and reply binding. A completed ingress
recovers canonical status without storing again, claiming, ACKing or regenerating
copies. An interrupted commit can attach its missing mcp-inbox route under the
canonical handoff lock; current delivery_state/claim/ACK remain unchanged.
Foreign global handoff/outbox/ledger reservations conflict. Existing OWN canonical
ingress may recognize a matching version/digest ledger row or full receive digest;
legacy held receipts also require the exact full native handoff reservation.
Ledger delivered/queued text alone is never read/ACK evidence. Only canonical
handoff ACK counts. Prepared final replies do not establish remote consumption.
"""
from contextlib import contextmanager
import base64
import copy
import fcntl
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time

from . import directory, envelope, files, handoff, network_directory, network_identity, paths, probe

MAX_PACKET = 8 * 1024 * 1024
MAX_RECORD = MAX_PACKET + 1024 * 1024
_ID = re.compile(r"[A-Za-z0-9_-]{1,160}\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_NETWORK = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")
_PUBLIC = {"machine", "runtime", "home_id", "session_id", "generation"}
_FIELDS = {"version", "id", "network_id", "sender", "receiver", "body", "kind", "reply_to",
           "outcome", "priority", "wake", "scope", "attachments", "file_packet", "fingerprint", "reply_binding"}


class GatewayError(ValueError):
    """Stable, payload-free code; original peer data never enters the error."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _key(value):
    return isinstance(value, str) and _HEX.fullmatch(value) is not None


def _api(function):
    @wraps(function)
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except GatewayError:
            raise
        except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            raise GatewayError("gateway-operation-unconfirmed") from None
    return call


def _id(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise GatewayError("invalid-message-id")
    return value


def _json(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise GatewayError("invalid-packet") from None


def _public(value):
    if not isinstance(value, dict) or set(value) != _PUBLIC or not _key(value.get("generation")):
        raise GatewayError("invalid-public-endpoint")
    try:
        return dict(network_identity.endpoint(value), generation=value["generation"])
    except ValueError:
        raise GatewayError("invalid-public-endpoint") from None


def request_fingerprint(packet):
    """Semantic network digest: public native pairs, excluding generations/display."""
    try:
        identity = envelope.request_identity(packet["id"], network_identity.endpoint(packet["sender"]),
            network_identity.endpoint(packet["receiver"]), packet["body"], kind=packet["kind"],
            reply_to=packet["reply_to"], outcome=packet["outcome"], scope=packet["scope"],
            priority=packet["priority"], attachments=packet["attachments"])
        return envelope.request_digest(identity)
    except (KeyError, TypeError, ValueError):
        raise GatewayError("invalid-packet") from None


source_fingerprint = request_fingerprint


def _body_hash(packet):
    return hashlib.sha256(packet["body"].encode("utf-8")).hexdigest()


def _semantic_packet(packet):
    """Keep immutable attachment identity, never a second unmetered blob cache."""
    value = copy.deepcopy(packet)
    if value["file_packet"] is not None:
        value["file_packet"] = {"manifest": copy.deepcopy(value["file_packet"]["manifest"])}
    return value


def _version_metadata(value):
    # files.prepare_* defines this as a text version label, not a descriptor
    # containing server paths or claimed authority.
    return value is None or (isinstance(value, str) and directory._PATH.search(value) is None
                             and not any(ord(c) < 32 for c in value))


def _owner(local):
    return handoff._identity(local)


def _answered_by(asked, answering):
    """The endpoint a request went to, or the one it was handed over to (handover.py)."""
    if asked == answering:
        return True
    from . import handover
    try:
        return handover.endpoint_succeeds(answering, asked)
    except (ValueError, TypeError):
        return False


def _handed_to(original, local):
    """A reply to a question the original asker handed over (handover.py)."""
    from . import handover
    try:
        return handover.succeeds(local, original)
    except (ValueError, TypeError):
        return False


def _private(info, directory=False):
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode) or info.st_uid != os.getuid() \
            or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600) \
            or not directory and info.st_nlink != 1:
        raise GatewayError("non-private-gateway-state")


def _directory(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    _private(path.lstat(), directory=True)


def _pairs(items):
    out = {}
    for key, value in items:
        if key in out:
            raise GatewayError("invalid-gateway-state")
        out[key] = value
    return out


def _read(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return None
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        _private(before)
        if before.st_size > MAX_RECORD:
            raise GatewayError("invalid-gateway-state")
        raw = stream.read(MAX_RECORD + 1)
        after = os.fstat(stream.fileno())
        signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if len(raw) > MAX_RECORD or signature(before) != signature(after) \
                or signature(after) != signature(os.stat(path, follow_symlinks=False)):
            raise GatewayError("invalid-gateway-state")
    try:
        value = json.loads(raw, object_pairs_hook=_pairs)
    except (ValueError, UnicodeError, RecursionError):
        raise GatewayError("invalid-gateway-state") from None
    if not isinstance(value, dict):
        raise GatewayError("invalid-gateway-state")
    return value


def _write(path, value):
    raw = _json(value)
    if len(raw) > MAX_RECORD:
        raise GatewayError("gateway-state-too-large")
    fd, temporary = tempfile.mkstemp(prefix=".gateway-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Gateway:
    @_api
    def __init__(self, root, node_id, permission):
        if not _key(node_id) or not callable(permission):
            raise GatewayError("local-permission-callback-required")
        self.root, self.node_id, self.permission = Path(root), node_id, permission
        self.network_id = None
        _directory(self.root)
        for name in ("outbound", "inbound"):
            _directory(self.root / name)

    def _network(self):
        if not isinstance(self.network_id, str) or not _NETWORK.fullmatch(self.network_id):
            raise GatewayError("verified-network-required")
        return self.network_id

    @contextmanager
    def _locked(self):
        _private(self.root.lstat(), directory=True)
        fd = os.open(self.root / ".lock", os.O_CREAT | os.O_RDWR | os.O_NONBLOCK
                     | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            _private(os.fstat(fd))
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        except (OSError, TypeError, KeyError, RecursionError):
            raise GatewayError("gateway-storage-unavailable") from None
        finally:
            os.close(fd)

    def _path(self, direction, message_id):
        _private(self.root.lstat(), directory=True)
        _private((self.root / direction).lstat(), directory=True)
        return self.root / direction / (_id(message_id) + ".json")

    def _load(self, direction, message_id):
        record = _read(self._path(direction, message_id))
        if record is None:
            return None
        packet = self._packet(record.get("packet"), retained=True)
        if record.get("version") != 1 or record.get("direction") != direction \
                or type(record.get("version")) is not int or record.get("phase") not in ("reserved", "stored") \
                or record.get("id") != message_id or record.get("fingerprint") != packet["fingerprint"] \
                or record.get("body_sha256") != _body_hash(packet) \
                or record.get("packet_sha256") != hashlib.sha256(_json(packet)).hexdigest() \
                or record.get("origin") != packet["sender"]["machine"] \
                or not isinstance(record.get("local"), dict) or record.get("admitted") is not True:
            raise GatewayError("invalid-gateway-state")
        expected = packet["sender"] if direction == "outbound" else packet["receiver"]
        kept = _owner(record["local"])
        actual = {"machine": self.node_id, "runtime": kept["runtime"], "session_id": kept["session_id"],
                  "home_id": hashlib.sha256(os.fsencode(os.path.realpath(record["local"]["home"]))).hexdigest()}
        named = network_identity.endpoint(expected)
        # What arrives for a handed-over session is kept for its successor
        # (handover.py); anything else is one conversation on both sides.
        if expected["machine"] != self.node_id or not (
                named == actual or direction == "inbound" and _answered_by(named, actual)):
            raise GatewayError("invalid-gateway-state")
        replies = record.get("reply_ids")
        if not isinstance(replies, list) or len(replies) > 4096 \
                or any(not isinstance(r, str) or not _ID.fullmatch(r) for r in replies) \
                or len(set(replies)) != len(replies):
            raise GatewayError("invalid-gateway-state")
        receipt = record.get("files")
        if receipt is not None and (packet["file_packet"] is None or not isinstance(receipt, dict)
                or receipt.get("status") != "files-stored" or receipt.get("request_id") != packet["id"]
                or not isinstance(receipt.get("storage_id"), str)
                or not re.fullmatch(r"[0-9a-f]{32}", receipt["storage_id"])
                or receipt.get("manifest") != packet["file_packet"]["manifest"]):
            raise GatewayError("invalid-gateway-state")
        # Old full-packet records remain readable without rewriting an operator's
        # files during an audit read. Never expose their cached data as a source.
        record["packet"] = _semantic_packet(packet)
        record["packet_sha256"] = hashlib.sha256(_json(record["packet"])).hexdigest()
        return record

    def _packet(self, value, retained=False):
        if not isinstance(value, dict) or set(value) != _FIELDS or type(value["version"]) is not int \
                or value["version"] != 1 or len(_json(value)) > MAX_PACKET:
            raise GatewayError("invalid-packet")
        _id(value["id"])
        _public(value["sender"])
        _public(value["receiver"])
        if value["network_id"] != self._network() or value["scope"] != "network:" + self._network() \
                or not isinstance(value["body"], str) or len(value["body"].encode("utf-8")) > files.REQUEST_BYTES \
                or value["kind"] not in envelope.KINDS or value["outcome"] not in (None,) + envelope.OUTCOMES \
                or value["priority"] not in ("next", "now") or type(value["wake"]) is not bool \
                or not value["wake"] and value["priority"] != "next":
            raise GatewayError("invalid-packet")
        if value["reply_to"] is not None:
            _id(value["reply_to"])
        if value["kind"] == "reply":
            binding = value["reply_binding"]
            if value["reply_to"] is None or not isinstance(binding, dict) \
                    or set(binding) != {"id", "fingerprint"} or binding["id"] != value["reply_to"] \
                    or not _key(binding["fingerprint"]):
                raise GatewayError("invalid-reply-binding")
        elif value["reply_binding"] is not None or value["outcome"] is not None:
            raise GatewayError("invalid-packet")
        try:
            refs = envelope.attachment_refs(value["attachments"])
        except ValueError:
            raise GatewayError("invalid-attachment-reference") from None
        if refs != value["attachments"] or len(refs) > 1 \
                or bool(refs) != (value["file_packet"] is not None):
            raise GatewayError("invalid-attachment-reference")
        if not _key(value["fingerprint"]) or request_fingerprint(value) != value["fingerprint"]:
            raise GatewayError("fingerprint-mismatch")
        if retained:
            self._files(value, retained=True)
        return copy.deepcopy(value)

    def _local(self, supplied):
        public = network_directory.public_endpoint(supplied, self.node_id)
        local = network_directory.resolve_local(public, self.node_id) if public else None
        if local is None or _owner(local) != _owner(supplied):
            raise GatewayError("local-native-binding-unverified")
        return local, public

    def _record(self, direction, packet, local):
        packet = _semantic_packet(packet)
        fields = ("runtime", "home", "session_id", "ref", "cwd", "uid", "registered", "certainty", "basis",
                  "identity_certainty", "identity_basis", "permission_mode") + network_directory._GENERATION_FIELDS
        actual = {k: copy.deepcopy(local[k]) for k in fields if k in local}
        actual["home"] = _owner(local)["home"]
        return {"version": 1, "direction": direction, "id": packet["id"], "packet": packet,
                "fingerprint": packet["fingerprint"], "body_sha256": _body_hash(packet),
                "packet_sha256": hashlib.sha256(_json(packet)).hexdigest(),
                "local": actual, "origin": packet["sender"]["machine"], "admitted": True,
                "phase": "reserved", "stored_at": time.time(), "reply_ids": []}

    @staticmethod
    def _same(record, packet, local):
        old = record["packet"]
        if record["fingerprint"] != packet["fingerprint"] or record["body_sha256"] != _body_hash(packet) \
                or _owner(record["local"]) != _owner(local) or old["wake"] != packet["wake"] \
                or old["file_packet"] != _semantic_packet(packet)["file_packet"] or old["reply_binding"] != packet["reply_binding"]:
            raise GatewayError("message-id-conflict")

    def origins_for(self, identity):
        """The machines that sent this local conversation a message: those that
        may hold a question for it (handover.py)."""
        out = set()
        for name in os.listdir(self.root / "inbound") if (self.root / "inbound").is_dir() else []:
            if not name.endswith(".json"):
                continue
            try:
                record = self._load("inbound", name[:-5])
                if record and _owner(record["local"]) == handoff._identity(identity):
                    out.add(record["origin"])
            except (GatewayError, OSError, ValueError, KeyError, TypeError):
                continue
        return out

    def _reverse(self, original, packet):
        return bool(original and original["fingerprint"] == packet["reply_binding"]["fingerprint"]
                    and original["id"] == packet["reply_to"]
                    and network_identity.endpoint(original["packet"]["sender"]) == network_identity.endpoint(packet["receiver"])
                    and _answered_by(network_identity.endpoint(original["packet"]["receiver"]),
                                     network_identity.endpoint(packet["sender"])))

    def _index_reply(self, direction, original, message_id):
        if message_id not in original["reply_ids"]:
            if len(original["reply_ids"]) >= 4096:
                raise GatewayError("reply-history-too-large")
            original["reply_ids"].append(message_id)
            _write(self._path(direction, original["id"]), original)

    @_api
    def prepare(self, sender_local, target_public, body, *, request_id, kind="note", reply_to=None,
                outcome=None, priority="next", wake=True, attachments=(), file_packet=None, prepared_intent=False):
        self._network()
        _id(request_id)
        if type(prepared_intent) is not bool:
            raise GatewayError("invalid-prepared-intent")
        local, sender = self._local(sender_local)
        receiver = _public(target_public)
        try:
            refs = envelope.attachment_refs(attachments)
        except ValueError:
            raise GatewayError("invalid-attachment-reference") from None
        packet = {"version": 1, "id": request_id, "network_id": self.network_id, "sender": sender,
                  "receiver": receiver, "body": body, "kind": kind, "reply_to": reply_to, "outcome": outcome,
                  "priority": priority, "wake": wake, "scope": "network:" + self.network_id,
                  "attachments": refs, "file_packet": file_packet, "reply_binding": None}
        with self._locked():
            original = None
            if kind == "reply":
                original = self._load("inbound", _id(reply_to))
                if not original or self._ingress(original) is None \
                        or not (_owner(original["local"]) == _owner(local)
                                or _handed_to(original["local"], local)):
                    raise GatewayError("reply-original-unverified")
                packet["reply_binding"] = {"id": reply_to, "fingerprint": original["fingerprint"]}
                if not self._reverse(original, packet):
                    raise GatewayError("reply-endpoint-mismatch")
            packet["fingerprint"] = request_fingerprint(packet)
            packet = self._packet(packet)
            self._files(packet)
            before = self._load("outbound", request_id)
            if before:
                if before.get("archived_at") is not None:
                    raise GatewayError("request-archived")
                self._same(before, packet, local)
            else:
                if self._load("inbound", request_id):
                    raise GatewayError("message-id-conflict")
                intent_digest = None
                if prepared_intent:
                    # questions.ask has already queued a native-local -> opaque
                    # remote identity. This is deliberately a different digest
                    # from the network's two-opaque-endpoint fingerprint.
                    queued = _read(Path(paths.path(paths.LEDGER, request_id + ".json")))
                    intent_target = network_identity.endpoint(receiver)
                    # The resolver supplies an exact net: ref; bare opaque
                    # callers have no ref. Accept only those two encodings of
                    # this exact endpoint, never a display name, URL or alias.
                    queued_target = queued.get("to") if isinstance(queued, dict) else None
                    if queued_target is not None and not isinstance(queued_target, dict):
                        raise GatewayError("prepared-intent-unverified")
                    target_ref = (queued_target or {}).get("ref")
                    if target_ref not in (None, network_identity.target(receiver)):
                        raise GatewayError("prepared-intent-unverified")
                    if target_ref is not None:
                        intent_target["ref"] = target_ref
                    intent_digest = envelope.request_digest(envelope.request_identity(request_id, local,
                        intent_target, body, kind=kind, reply_to=reply_to, outcome=outcome,
                        scope=packet["scope"], priority=priority, attachments=refs))
                    if not self._intent_matches(queued, request_id, intent_digest):
                        raise GatewayError("prepared-intent-unverified")
                self._global(request_id, outbound_intent_digest=intent_digest)
            if original:
                self._index_reply("inbound", original, request_id)
            if before is None:
                _write(self._path("outbound", request_id), self._record("outbound", packet, local))
            return packet

    def _message(self, packet, local, receipt=None):
        sender = network_identity.endpoint(packet["sender"])
        message = {"id": packet["id"], "sender": sender, "target": _owner(local), "body": packet["body"],
                   "kind": packet["kind"], "reply_to": packet["reply_to"], "outcome": packet["outcome"],
                   "scope": packet["scope"], "priority": packet["priority"], "wake": packet["wake"],
                   "attachments": packet["attachments"], "delivery_state": "pending"}
        message["content"] = envelope.build(packet["body"], msg_id=packet["id"], sender=sender,
            scope=packet["scope"], kind=packet["kind"], reply_to=packet["reply_to"], outcome=packet["outcome"],
            origin="p2p:" + sender["machine"], attachments=packet["attachments"])
        if receipt:
            value = receipt["manifest"]
            message["file_storage"] = receipt["storage_id"]
            message["receivedfile_context"] = {"storage_id": receipt["storage_id"], "manifest_id": value["id"],
                "version": value["version"], "sha256": value["sha256"],
                "files": [{k: f[k] for k in ("id", "name", "size", "sha256")} for f in value["files"]]}
        return message

    def _handoff_digest(self, packet, local):
        message = self._message(packet, local)
        return envelope.request_digest(envelope.request_identity(packet["id"], message["sender"], _owner(local),
            packet["body"], kind=packet["kind"], reply_to=packet["reply_to"], outcome=packet["outcome"],
            scope=packet["scope"], priority=packet["priority"], attachments=packet["attachments"]))

    @staticmethod
    def _intent_matches(row, message_id, digest):
        return bool(isinstance(row, dict) and row.get("id") == message_id and row.get("status") == "queued"
                    and type(row.get("req_version")) is int and row["req_version"] == envelope.CANON_VERSION
                    and row.get("digest") == digest)

    def _global(self, message_id, record=None, *, outbound_intent_digest=None):
        # Existing core namespaces are read only. No ledger mutation is performed.
        for suffix in (".json", ".recv.json", ".handoff.json"):
            existing = _read(Path(paths.path(paths.LEDGER, message_id + suffix)))
            if existing is not None:
                receiver = existing.get("receiver")
                own_receipt = False
                prepared_entry = bool(record is None and suffix == ".json" and outbound_intent_digest is not None
                    and self._intent_matches(existing, message_id, outbound_intent_digest))
                own_entry = bool(record is not None and suffix == ".json" and self._ingress(record) is not None
                    and existing.get("id") == message_id and existing.get("req_version") == envelope.CANON_VERSION
                    and existing.get("digest") in (record["fingerprint"], self._handoff_digest(record["packet"], record["local"])))
                if record is not None and suffix == ".recv.json" and self._ingress(record) is not None:
                    parsed = envelope.parse(self._message(record["packet"], record["local"])["content"])
                    exact_receiver = (isinstance(receiver, dict)
                        and receiver.get("runtime") == record["local"]["runtime"]
                        and receiver.get("ref") == record["local"].get("ref"))
                    full_digest = (existing.get("req_version") == envelope.CANON_VERSION
                        and existing.get("req_digest") == envelope.received_digest(parsed.header, parsed.body, parsed.attrs)
                        and existing.get("body_sha") == _body_hash(record["packet"])[:16]
                        and existing.get("from_ref") == parsed.header.get("ref"))
                    # Held receipts predate digest fields. Only the existing
                    # exact canonical original + global native reservation can
                    # make one ours; its decision never establishes consumption.
                    reservation = _read(Path(paths.path(paths.LEDGER, message_id + ".handoff.json")))
                    legacy_held = (existing.get("decision") in ("held", "blocked")
                        and not existing.get("req_digest") and isinstance(reservation, dict)
                        and reservation.get("receiver") == _owner(record["local"]))
                    own_receipt = existing.get("id") == message_id and exact_receiver and (full_digest or legacy_held)
                if not prepared_entry and not own_entry and not own_receipt and (record is None or suffix != ".handoff.json" or receiver != _owner(record["local"])):
                    raise GatewayError("message-id-conflict")
        if _read(Path(paths.path("outbox", message_id + ".json"))) is not None:
            raise GatewayError("message-id-conflict")
        folder = Path(paths.path(handoff.DIRECTORY))
        if folder.exists():
            info = folder.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
                raise GatewayError("canonical-state-unverified")
            for child in folder.iterdir():
                if child.is_symlink():
                    raise GatewayError("canonical-state-unverified")
                if not child.is_dir():
                    continue
                existing = _read(child / (message_id + ".json"))
                if existing is not None and (record is None or existing.get("receiver") != _owner(record["local"])
                        or existing.get("digest") != self._handoff_digest(record["packet"], record["local"])):
                    raise GatewayError("message-id-conflict")

    def _route(self, local, message_id):
        # handoff.delivery also writes delivery_state; its pre-lock snapshot
        # could resurrect a concurrently held/refused message. Change only the
        # route while holding the canonical handoff lock and retain its state.
        with handoff._locked(local) as folder:
            current = handoff._read(folder, message_id, local)
            if current is None:
                raise GatewayError("handoff-storage-unconfirmed")
            if current["state"] != "acknowledged" and current.get("delivery_route") != "mcp-inbox":
                current["delivery_route"] = "mcp-inbox"
                handoff._write(os.path.join(folder, message_id + ".json"), current)

    def _files(self, packet, retained=False):
        if packet["file_packet"] is None:
            return
        try:
            if retained:
                part = packet["file_packet"]
                if not isinstance(part, dict) or set(part) not in ({"manifest"}, {"manifest", "data"}):
                    raise GatewayError("file-binding-invalid")
                manifest = part["manifest"]
                files._check_manifest(manifest, packet["id"], packet["body"])
            else:
                manifest, _ = files._packet(packet["file_packet"], packet["id"], packet["body"], files.product_limits())
                if time.time() >= manifest["expires_at"]:
                    raise GatewayError("file-payload-expired")
            sender = packet["sender"]
            if manifest["owner"] != {k: sender[k] for k in ("runtime", "home_id", "session_id")}:
                raise GatewayError("file-owner-mismatch")
            files._expect_reference(manifest, packet["attachments"][0], packet["id"])
            # Version descriptors are opaque caller metadata, never paths or
            # permission evidence. Reject such descriptors rather than rewriting
            # the manifest and breaking the immutable attachment reference.
            for entry in manifest["files"]:
                descriptor = entry.get("source_version")
                if not _version_metadata(descriptor):
                    raise GatewayError("file-binding-invalid")
        except (ValueError, KeyError, TypeError):
            raise GatewayError("file-binding-invalid") from None

    def _wire_packet(self, record):
        """Rehydrate only from existing quota/TTL-managed copies, never sources."""
        packet = copy.deepcopy(record["packet"])
        if packet["file_packet"] is None:
            return packet
        try:
            manifest = packet["file_packet"]["manifest"]
            if record["direction"] == "outbound":
                full = files.export_frozen(record["local"], manifest["id"],
                                           request_id=packet["id"], body=packet["body"])
            else:
                receipt = record.get("files")
                if not receipt:
                    raise GatewayError("file-payload-unavailable")
                with files._store() as root:
                    stored, blobs = files._load(root, "incoming", receipt["storage_id"], files._owner(record["local"]))
                    if time.time() >= min(stored["expires_at"], manifest["expires_at"]):
                        raise GatewayError("file-payload-unavailable")
                    full = {"manifest": stored["manifest"], "data": {
                        key: base64.b64encode(raw).decode("ascii") for key, raw in blobs.items()}}
            if full["manifest"] != manifest:
                raise GatewayError("file-payload-unavailable")
            packet["file_packet"] = full
            self._files(packet)
            return packet
        except (ValueError, OSError, KeyError, TypeError):
            raise GatewayError("file-payload-unavailable") from None

    @_api
    def compact_legacy_payload(self, direction, message_id):
        """Explicit single-record cleanup; no scanning, source reads or TTL renewal.

        Validate an old record and its legacy bytes before stripping the cache.
        Audit reads do not mutate records. Callers choose their own managed store;
        this API never opens unrelated evaluation originals or copies their data.
        """
        if direction not in ("inbound", "outbound"):
            raise GatewayError("invalid-direction")
        with self._locked():
            path = self._path(direction, message_id)
            raw = _read(path)
            if raw is None:
                return {"status": "not-found"}
            record = self._load(direction, message_id)
            part = raw["packet"]["file_packet"]
            if part is None or "data" not in part:
                return {"status": "unchanged", "id": message_id}
            # Validate bytes without treating an expired audit record as active.
            files._packet(part, message_id, raw["packet"]["body"], files.product_limits())
            _write(path, record)
            return {"status": "compacted", "id": message_id}

    def _permission(self, origin, packet, local):
        try:
            return self.permission(origin, copy.deepcopy(packet["sender"]), copy.deepcopy(local),
                                   copy.deepcopy(packet)) is True
        except Exception:
            raise GatewayError("local-permission-unavailable") from None

    @staticmethod
    def _authority_snapshot(local):
        # Metadata rendering can change without changing rights. All other
        # registry/enrichment fields, including cwd/mode/UID/liveness, must stay
        # unchanged while the local permission callback is running.
        display = {"name", "alias", "updated", "name_source", "name_freshness", "doing", "summary", "branch"}
        snapshot = {k: v for k, v in local.items() if k not in display}
        with probe.quick():
            cwd = probe.bounded(directory._canonical, local.get("cwd"), folder=local.get("cwd"))
        if cwd is None:
            raise GatewayError("local-target-unverified")
        snapshot["cwd"] = cwd
        snapshot["home"] = _owner(local)["home"]
        return hashlib.sha256(_json(snapshot)).hexdigest()

    def _receiving(self, handle):
        """The exact local record for a handle, or the session the one it names
        handed its place over to (handover.py): never a name fallback."""
        from . import handover
        local = network_directory.resolve_local(handle, self.node_id)
        if local is not None:
            nxt, note = handover.follow(local)
            return nxt if note else local
        return handover.for_handle(handle)

    def _checked_target(self, origin, packet):
        local = self._receiving(packet["receiver"])
        if local is None:
            raise GatewayError("local-target-unverified")
        before = self._authority_snapshot(local)
        allowed = self._permission(origin, packet, local)
        current = self._receiving(packet["receiver"])
        if current is None or self._authority_snapshot(current) != before:
            raise GatewayError("local-target-changed-during-permission")
        return current, allowed

    @_api
    def receive(self, origin, packet):
        packet = self._packet(packet)
        if not _key(origin) or packet["sender"]["machine"] != origin or packet["receiver"]["machine"] != self.node_id:
            raise GatewayError("tls-origin-or-receiver-mismatch")
        # Even an ACKed duplicate must present authentic, complete wire bytes.
        self._files(packet)
        with self._locked():
            local, allowed = self._checked_target(origin, packet)
            original = self._load("outbound", packet["reply_to"]) if packet["kind"] == "reply" else None
            reverse = packet["kind"] == "reply" and self._reverse(original, packet) \
                and (_owner(original["local"]) == _owner(local)
                     or _handed_to(original["local"], local))
            if not allowed and not reverse:
                raise GatewayError("local-permission-denied")
            if packet["kind"] == "reply" and not reverse:
                raise GatewayError("reply-original-unverified")
            record = self._load("inbound", packet["id"])
            if record:
                self._same(record, packet, local)
            elif self._load("outbound", packet["id"]):
                raise GatewayError("message-id-conflict")
            self._global(packet["id"], record)
            committed = self._ingress(record) if record else None
            if committed is not None:
                if packet["file_packet"] is not None:
                    try:
                        files.received_manifest(local, record["files"]["storage_id"],
                            request_id=packet["id"], body=packet["body"],
                            expected_reference=packet["attachments"][0])
                    except (ValueError, OSError, KeyError, TypeError):
                        raise GatewayError("file-payload-unavailable") from None
                if committed.get("delivery_route") != "mcp-inbox" and committed["status"] != "acknowledged":
                    self._route(local, packet["id"])
                if record["phase"] != "stored":
                    record["phase"] = "stored"
                    _write(self._path("inbound", packet["id"]), record)
                return self._delivery(record)
            if original:
                self._index_reply("outbound", original, packet["id"])
            if record is None:
                record = self._record("inbound", packet, local)
                _write(self._path("inbound", packet["id"]), record)
            receipt = record.get("files")
            if packet["file_packet"] is not None and receipt is None:
                try:
                    receipt = files.receive(local, packet["file_packet"], request_id=packet["id"], body=packet["body"],
                        expected_reference=packet["attachments"][0], limits=files.product_limits())
                except (ValueError, OSError):
                    raise GatewayError("file-storage-unconfirmed") from None
                record["files"] = receipt
                _write(self._path("inbound", packet["id"]), record)
            local, current_permission = self._checked_target(origin, packet)
            if not current_permission and not reverse:
                raise GatewayError("local-permission-denied")
            message = self._message(packet, local, receipt)
            try:
                handoff.store(_owner(local), message)
                self._route(local, packet["id"])
            except (ValueError, OSError):
                raise GatewayError("handoff-storage-unconfirmed") from None
            record["phase"] = "stored"
            _write(self._path("inbound", packet["id"]), record)
            return self._delivery(record)

    def _ingress(self, record):
        current = handoff.status(record["local"], record["id"])
        message = current.get("message")
        if current.get("digest") != self._handoff_digest(record["packet"], record["local"]) \
                or message != self._message(record["packet"], record["local"], record.get("files")):
            return None
        return current

    @_api
    def ingress_record(self, msg_id):
        """Private verified binding for the current gate; no queue/claim/ACK mutation."""
        _private(self.root.lstat(), directory=True)
        record = self._load("inbound", _id(msg_id))
        if not record or self._ingress(record) is None:
            return None
        return copy.deepcopy(dict(record, verified=True, target_local=record["local"],
                                  sender=network_identity.endpoint(record["packet"]["sender"])))

    def _delivery(self, record):
        current = self._ingress(record)
        if current is None:
            return {"id": record["id"], "status": "unknown", "stored": False, "acknowledged": False}
        acknowledged = current["status"] == "acknowledged"
        delivery = current.get("delivery_state")
        status = "acknowledged" if acknowledged else delivery if delivery in ("held", "refused", "offline", "error", "unknown") else "queued"
        return {"id": record["id"], "status": status, "stored": True,
                "handoff_status": current["status"], "delivery_state": delivery,
                "route": current.get("delivery_route"), "acknowledged": acknowledged,
                "fingerprint": record["fingerprint"]}

    @_api
    def status(self, origin, request_id, caller_public=None):
        _id(request_id)
        if not _key(origin) or caller_public is None:
            return {"status": "not-found"}
        try:
            caller = network_identity.endpoint(caller_public)
        except ValueError:
            return {"status": "not-found"}
        record = self._load("inbound", request_id) or self._load("outbound", request_id)
        if not record or origin != record["origin"] or caller != network_identity.endpoint(record["packet"]["sender"]):
            return {"status": "not-found"}
        result = self._delivery(record) if record["direction"] == "inbound" else {
            "id": request_id, "status": "prepared", "acknowledged": False, "fingerprint": record["fingerprint"]}
        result["replies"] = []
        result["final_reply"] = None
        direction = "outbound" if record["direction"] == "inbound" else "inbound"
        for reply_id in record.get("reply_ids", []):
            reply = self._load(direction, _id(reply_id))
            if not reply or reply["packet"]["kind"] != "reply" or not self._reverse(record, reply["packet"]):
                continue
            if direction == "inbound" and self._ingress(reply) is None:
                continue
            evidence = {"id": reply["id"], "fingerprint": reply["fingerprint"],
                        "status": "prepared" if direction == "outbound" else "stored",
                        "reply_to": reply["packet"]["reply_to"], "outcome": reply["packet"]["outcome"]}
            result["replies"].append(evidence)
            if record["packet"]["kind"] != "task" or reply["packet"]["outcome"] in envelope.OUTCOMES:
                final = dict(evidence)
                try:
                    final["packet"] = self._wire_packet(reply)
                except GatewayError as exc:
                    if str(exc) != "file-payload-unavailable":
                        raise
                    # Receipt/ACK and reply identity are independent of current
                    # byte availability. Never substitute a body-only dispatch.
                    final.update(payload_available=False, payload_error="file-payload-unavailable")
                result["final_reply"] = final
        if len(_json(result)) > MAX_PACKET:
            raise GatewayError("status-evidence-too-large")
        return result
