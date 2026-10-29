"""IC06 preparation only: no transport, membership policy, or permission grant.

Origin is supplied OUTSIDE packet decoding by an authenticated adapter and still
requires its verifier. A machine/home hash/publication/body tag is never a file
permission, human approval or signature. Unknown policies remain unknown.
local_digest is an opaque unchanged LOCAL audit digest, independently verified
when a private mapping is available; home_id is never substituted for a path.
Network semantics have a separate domain and canonical body SHA supplied/checked
through the existing envelope canonicalizer. Generation and raw bytes are only
freshness/frame evidence, not semantic identity. This module has no file I/O.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re


SCHEMA = "xsm.network-prep/v1"
STATES = ("declared", "observed", "unsupported", "unknown", "degraded")


class ContractError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise ContractError(message)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _hex(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _json(value):
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                          separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ContractError("not bounded-compatible Unicode JSON") from exc


def _sha(data):
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Endpoint:
    machine: str
    runtime: str
    home_id: str
    conversation: str
    generation: str
    native_ref: str | None = None

    def __post_init__(self):
        _require(all(_text(getattr(self, k)) for k in ("machine", "runtime", "conversation", "generation")),
                 "complete machine/native conversation/generation required")
        _require(_hex(self.home_id), "home_id must be SHA-256, never a path")
        _require(self.native_ref is None or _text(self.native_ref), "invalid native ref")

    def identity(self):
        return {k: v for k, v in asdict(self).items() if k != "generation"}


@dataclass(frozen=True)
class Origin:
    """Adapter observation, not a serializable packet claim or a signature."""
    machine: str
    evidence_id: str

    def __post_init__(self):
        _require(_text(self.machine) and _text(self.evidence_id), "origin observation incomplete")


def _refs(values):
    _require(isinstance(values, (list, tuple)), "refs must be an ordered sequence")
    result = []
    for value in values:
        _require(isinstance(value, (list, tuple)) and len(value) == 4, "canonical four-field ref required")
        path, digest, version, size = value
        _require(isinstance(path, str) and re.fullmatch(r"manifest:[0-9a-f]{32}", path), "opaque manifest ref required")
        _require(_hex(digest) and type(version) is int and version > 0
                 and type(size) is int and size >= 0, "invalid ref digest/version/size")
        result.append((path, digest, version, size))
    _require(len({r[0] for r in result}) == len(result), "duplicate manifest ref")
    return tuple(result)


@dataclass(frozen=True)
class Request:
    id: str
    sender: Endpoint
    receiver: Endpoint
    body: str
    local_digest: str
    canonical_body_sha256: str
    refs: tuple = ()
    kind: str = "task"
    reply_to: str | None = None
    outcome: str | None = None
    scope: str | None = None
    priority: str | None = None

    def __post_init__(self):
        _require(_text(self.id) and isinstance(self.sender, Endpoint) and isinstance(self.receiver, Endpoint), "request identity incomplete")
        _require(isinstance(self.body, str) and _hex(self.local_digest) and _hex(self.canonical_body_sha256),
                 "body, local audit digest and envelope-canonical body SHA required")
        _require(self.kind in ("note", "task", "reply") and self.outcome in (None, "succeeded", "failed"), "invalid kind/outcome")
        _require(all(v is None or _text(v) for v in (self.reply_to, self.scope, self.priority)), "invalid optional fields")
        _require(self.kind == "reply" or self.reply_to is None, "only replies carry reply_to")
        _require(self.kind != "reply" or _text(self.reply_to), "reply requires original request id")
        object.__setattr__(self, "refs", _refs(self.refs))
        _json(self.body)  # Reject unpaired surrogates before hashing.

    @property
    def body_sha256(self):
        return _sha(self.body.encode("utf-8"))

    def wire(self):
        return dict(asdict(self), body_sha256=self.body_sha256, schema=SCHEMA, type="send")

    @property
    def fingerprint(self):
        semantic = {"domain": "xsm.network-semantic/v1", "id": self.id,
                    "sender": self.sender.identity(), "receiver": self.receiver.identity(),
                    "canonical_body_sha256": self.canonical_body_sha256, "refs": self.refs,
                    "kind": self.kind, "reply_to": self.reply_to, "outcome": self.outcome,
                    "scope": self.scope, "priority": self.priority}
        return _sha(_json(semantic))

    @property
    def frame_sha256(self):
        return _sha(_json(self.wire()))


def from_local(identity, local_digest, sender, receiver, raw_body):
    """Consume actual envelope.request_identity output; never normalize a path.

    Private canonical home strings are hashed then discarded. No file is read
    and no legacy digest is reconstructed with home_id pretending to be a path.
    """
    for label, endpoint in (("from", sender), ("to", receiver)):
        handle = identity.get(label) or {}
        _require(_text(handle.get("home")), "private verified handle mapping unavailable")
        _require(_sha(handle["home"].encode("utf-8")) == endpoint.home_id
                 and handle.get("runtime") == endpoint.runtime
                 and handle.get("conversation") == endpoint.conversation
                 and (endpoint.native_ref is None or handle.get("ref") == endpoint.native_ref),
                 "local/opaque endpoint mapping mismatch")
    return Request(identity["id"], sender, receiver, raw_body, local_digest,
                   _sha(identity["body"].encode("utf-8")), tuple(identity["attachments"]),
                   identity["kind"], identity["reply_to"], identity["outcome"], identity["scope"], identity["priority"])


@dataclass(frozen=True)
class Capability:
    endpoint: Endpoint
    name: str
    version: int | None
    status: str
    observed_at: float | None = None

    def __post_init__(self):
        _require(isinstance(self.endpoint, Endpoint) and _text(self.name) and self.status in STATES, "invalid capability")
        _require(self.version is None or type(self.version) is int and self.version > 0, "invalid capability version")
        _require(self.observed_at is None or type(self.observed_at) in (int, float)
                 and math.isfinite(self.observed_at), "invalid observation timestamp")

    def wire(self):
        return dict(asdict(self), schema=SCHEMA, type="capabilities")


def encode(value):
    _require(isinstance(value, (Request, Capability)), "only explicit DTOs are encoded")
    return _json(value.wire())


def _unique(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def decode(data, *, max_bytes):
    _require(type(max_bytes) is int and max_bytes > 0 and isinstance(data, bytes), "explicit byte parser bound required")
    _require(len(data) <= max_bytes, "packet exceeds parser bound")
    try:
        value = json.loads(data, object_pairs_hook=_unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ContractError("nonfinite JSON")))
        _require(isinstance(value, dict) and value.pop("schema") == SCHEMA, "unsupported schema")
        kind = value.pop("type")
        if kind == "send":
            expected = set(Request.__dataclass_fields__) | {"body_sha256"}
            _require(set(value) == expected, "unexpected or missing request fields")
            raw_sha = value.pop("body_sha256")
            value["sender"], value["receiver"] = Endpoint(**value["sender"]), Endpoint(**value["receiver"])
            result = Request(**value)
            _require(raw_sha == result.body_sha256, "raw body digest mismatch")
            return result
        _require(kind == "capabilities" and set(value) == set(Capability.__dataclass_fields__), "unsupported DTO")
        value["endpoint"] = Endpoint(**value["endpoint"])
        return Capability(**value)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        raise ContractError("invalid network DTO: " + str(exc)) from exc


def _verify(callback, *args):
    if callback is None:
        return "unknown"
    try:
        answer = callback(*args)
    except Exception:
        return "unknown"
    return "verified" if answer is True else "rejected" if answer is False else "unknown"


def assess(request, origin, *, origin_verifier=None, semantic_verifier=None,
           membership_verifier=None, person_verifier=None, repository_verifier=None,
           collaboration_verifier=None, backend_verifier=None, owner_verifier=None,
           local_digest_verifier=None, generation_verifier=None, disclosure_verifier=None, published=False):
    """Evidence only. Publication, matching Git URLs/names and body tags grant nothing.

    repository_verifier must consult an explicit verified cross-machine mapping,
    not folder basename/Git URL equality. No default membership/person/backend policy.
    """
    _require(isinstance(request, Request) and isinstance(origin, Origin), "separate request/transport observation required")
    auth = _verify(origin_verifier, origin)
    if auth == "verified":
        _require(origin.machine == request.sender.machine, "authenticated machine differs from packet sender")
    checks = {"origin": auth, "semantic": _verify(semantic_verifier, request),
              "local_digest": _verify(local_digest_verifier, request),
              "generation": _verify(generation_verifier, request, origin),
              "membership": _verify(membership_verifier, request, origin),
              "same_person": _verify(person_verifier, request, origin),
              "same_owner": _verify(owner_verifier, request, origin),
              "same_repository": _verify(repository_verifier, request, origin),
              "collaboration": _verify(collaboration_verifier, request, origin),
              "backend_selection": _verify(backend_verifier, request, origin),
              "disclosure": _verify(disclosure_verifier, request, origin)}
    return {"checks": checks, "authenticated_machine": origin.machine if auth == "verified" else None,
            "published": published is True, "visibility": "public" if auth == checks["disclosure"] == "verified" else "private",
            "human_approval": "unknown", "file_read_permission": "unknown"}


def capabilities(claim, endpoint, origin, *, origin_verifier=None, capability_verifier=None):
    _require(isinstance(claim, Capability) and isinstance(endpoint, Endpoint)
             and claim.endpoint.identity() == endpoint.identity(), "capability semantic endpoint changed")
    _require(isinstance(origin, Origin) and origin.machine == endpoint.machine, "capability origin mismatch")
    auth, verified = _verify(origin_verifier, origin), _verify(capability_verifier, claim, origin)
    if claim.endpoint.generation != endpoint.generation:
        verified = "unknown"  # Resume retains identity, never inherits an old observation.
    return {"status": claim.status if auth == verified == "verified" else "unknown", "version": claim.version,
            "verification": verified, "file_read_permission": "unknown", "human_approval": "unknown"}


class Boundary:
    """Small in-memory conformance recorder, NOT a transport or authorization engine."""
    def __init__(self):
        self.requests, self.latest, self.fingerprints, self.evidence = {}, {}, {}, {}

    def _bind(self, request):
        previous = self.fingerprints.get(request.id)
        _require(previous is None or previous == request.fingerprint, "same id has different endpoint/body/refs")
        self.fingerprints[request.id] = request.fingerprint

    def register_send(self, request, origin, **verifiers):
        report = assess(request, origin, **verifiers)
        _require(report["checks"]["origin"] == report["checks"]["semantic"] == "verified", "unverified origin or local semantic binding")
        self._bind(request)
        original = self.requests.setdefault(request.id, request)
        self.latest[request.id] = request
        changed = (original.sender.generation, original.receiver.generation) != (request.sender.generation, request.receiver.generation)
        self.evidence.setdefault(request.id, {"backend_accepted": False, "backend_queued": False,
                                             "backend_delivered": False, "replies": [], "freshness": "unknown"})
        if changed:
            self.evidence[request.id]["freshness"] = report["checks"]["generation"]
        return dict(report, id=request.id, fingerprint=request.fingerprint,
                    generation_changed=changed, approval_recheck="unknown" if changed else "not-evaluated",
                    transport_attempted=False)

    def observe(self, request_id, fingerprint, stage, origin, *, origin_verifier=None,
                endpoint=None, reply=None, semantic_verifier=None, generation_verifier=None):
        _require(request_id in self.requests, "unknown request id")
        original = self.requests[request_id]
        _require(fingerprint == original.fingerprint, "evidence belongs to another request")
        _require(isinstance(origin, Origin) and _verify(origin_verifier, origin) == "verified", "unverified observation")
        _require(stage in ("accepted", "queued", "delivered", "actual_reply"), "invalid evidence stage")
        state = self.evidence[request_id]
        if stage == "actual_reply":
            _require(isinstance(reply, Request) and reply.kind == "reply" and reply.id != original.id,
                     "a backend status or body claim is not an actual reply")
            _require(reply.reply_to == original.id and reply.sender.identity() == original.receiver.identity()
                     and reply.receiver.identity() == original.sender.identity(), "reply_to or exact native pair changed")
            _require(origin.machine == reply.sender.machine and _verify(semantic_verifier, reply) == "verified", "reply origin/semantic binding unverified")
            state["freshness"] = _verify(generation_verifier, reply, origin)
            if state["freshness"] != "verified":
                return self.status(request_id)  # Original ID retained, no unverified actual-reply claim.
            self._bind(reply)
            if reply.id not in state["replies"]:
                state["replies"].append(reply.id)
        else:
            if stage == "delivered":
                _require(isinstance(endpoint, Endpoint) and endpoint.identity() == original.receiver.identity()
                         and origin.machine == endpoint.machine, "backend delivery endpoint mismatch")
            state["backend_" + stage] = True
        return self.status(request_id)

    def status(self, request_id):
        _require(request_id in self.evidence, "unknown request id")
        value = self.evidence[request_id]
        return dict(value, replies=list(value["replies"]), actual_reply=bool(value["replies"]),
                    human_approval="unknown", file_read_permission="unknown")
