"""Signed, durable device membership (ADR-0021).

Only the supplied callbacks handle cryptography; this module never opens a key.
Signatures cover canonical UTF-8 JSON including the operation, network and causal
parents. Display names have no authority. This is a mutually trusting member
model: an offline fork signed before a removal can still be merged. It does not
promise cryptographic eviction of malicious members or a global consensus clock.

Wire state is {version, network_id, records: [signed record, ...]}. network_id is
"<founder public key>:<SHA-256 of unsigned genesis without network_id>". The
digest binds the founder key, random nonce and all genesis fields; the prefix
keeps that stable root key visible after initialization, adoption and removal.
Every record has domain/op/network_id/issuer/parents/issued_at/signature plus
operation fields.
Record IDs are SHA-256 of the entire canonical signed record. An invite secret
is returned only by issue_invite; neither snapshots nor disk contain it.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import tempfile
import time
from contextlib import contextmanager


DOMAIN = "xsm/membership/1"
MAX_STATE_BYTES = 4 * 1024 * 1024
MAX_RECORDS = 1024
MAX_PARENTS = 128
_COMMON = {"domain", "op", "network_id", "issuer", "parents", "issued_at", "signature"}
_FIELDS = {
    "initialize": {"name", "machine_name", "nonce"},
    "invite": {"invite_hash", "reusable", "expires_at"},
    "admit": {"invite_hash", "endpoint_id", "machine_name"},
    "remove": {"endpoint_id"},
    "revoke": {"invite_hash"},
}


class MembershipError(ValueError):
    """A stable, secret-free error; ``code`` is suitable for a control response."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _json(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError):
        raise MembershipError("invalid_state") from None


def _hash(value):
    return hashlib.sha256(_json(value)).hexdigest()


def _hex(value, size=64):
    return (isinstance(value, str) and len(value) == size
            and all(c in "0123456789abcdef" for c in value))


def _text(value):
    return (isinstance(value, str) and 0 < len(value) <= 256
            and not any(ord(c) < 32 or ord(c) == 127 for c in value))


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def _signature(value):
    # Callback contract is hexadecimal, not a particular signature algorithm.
    return (isinstance(value, str) and 2 <= len(value) <= 1024
            and len(value) % 2 == 0 and _hex(value, len(value)))


def _unsigned(record):
    return {k: v for k, v in record.items() if k != "signature"}


def _network_id(genesis):
    digest = _hash({k: v for k, v in _unsigned(genesis).items() if k != "network_id"})
    return genesis["issuer"] + ":" + digest


def _valid_network_id(value):
    return (isinstance(value, str) and len(value) == 129 and value[64] == ":"
            and _hex(value[:64]) and _hex(value[65:]))


class _Graph:
    """A verified causal history, with remove-wins concurrent membership."""

    def __init__(self, state, verify):
        if (not isinstance(state, dict) or set(state) != {"version", "network_id", "records"}
                or type(state["version"]) is not int or state["version"] != 1
                or not _valid_network_id(state["network_id"]) or not isinstance(state["records"], list)
                or not 1 <= len(state["records"]) <= MAX_RECORDS
                or len(_json(state)) > MAX_STATE_BYTES):
            raise MembershipError("invalid_state")
        # Detach only after checking the serialization bound. Deep-copying an
        # untrusted nested object first can raise RecursionError before validation.
        state = json.loads(_json(state))
        self.network_id = state["network_id"]
        self.records = {}
        self.ancestors = {}
        for record in state["records"]:
            self._shape(record)
            rid = _hash(record)
            if rid in self.records:
                raise MembershipError("duplicate_record")
            self.records[rid] = record
        roots = [rid for rid, r in self.records.items() if r["op"] == "initialize"]
        if len(roots) != 1:
            raise MembershipError("invalid_genesis")
        self.root = roots[0]
        genesis = self.records[self.root]
        if genesis["parents"] or _network_id(genesis) != self.network_id:
            raise MembershipError("invalid_genesis")
        # Verify every byte before allowing any graph-derived authorization.
        for record in self.records.values():
            try:
                valid = verify(record["issuer"], _json(_unsigned(record)), record["signature"])
            except Exception:
                valid = False
            if valid is not True:
                raise MembershipError("invalid_signature")
        pending = set(self.records)
        self.order = []
        while pending:
            ready = sorted(rid for rid in pending
                           if all(p in self.ancestors for p in self.records[rid]["parents"]))
            if not ready:
                raise MembershipError("invalid_parents")
            for rid in ready:
                record = self.records[rid]
                view = set(record["parents"])
                for parent in record["parents"]:
                    view.update(self.ancestors[parent])
                    if record["issued_at"] < self.records[parent]["issued_at"]:
                        raise MembershipError("invalid_time")
                self.ancestors[rid] = view
                if rid != self.root:
                    if self.root not in view or not self.active(record["issuer"], view):
                        raise MembershipError("inactive_issuer")
                    self._operation(record, view)
                self.order.append(rid)
                pending.remove(rid)
        self.all = set(self.records)
        for r in self.records.values():
            if r["op"] == "invite" and not r["reusable"] and len(self.uses(r["invite_hash"])) > 1:
                # Separate forks must not turn a one-time credential into two
                # admissions, even if both records bear genuine issuer signatures.
                raise MembershipError("conflicting_consumption")

    def _shape(self, r):
        if (not isinstance(r, dict) or not isinstance(r.get("op"), str)
                or r["op"] not in _FIELDS or set(r) != _COMMON | _FIELDS[r["op"]]
                or r["domain"] != DOMAIN or r["network_id"] != self.network_id
                or not _hex(r["issuer"]) or not _signature(r["signature"])
                or not _number(r["issued_at"]) or not isinstance(r["parents"], list)
                or len(r["parents"]) > MAX_PARENTS
                or any(not _hex(p) for p in r["parents"])
                or len(set(r["parents"])) != len(r["parents"])):
            raise MembershipError("invalid_record")
        op = r["op"]
        if (op == "initialize" and (not _text(r["name"]) or not _text(r["machine_name"])
                                   or not _hex(r["nonce"]))
                or op in ("admit", "remove") and not _hex(r["endpoint_id"])
                or op == "admit" and not _text(r["machine_name"])
                or "invite_hash" in r and not _hex(r["invite_hash"])):
            raise MembershipError("invalid_record")
        if op == "invite" and (type(r["reusable"]) is not bool
                               or r["expires_at"] is not None and
                               (not _number(r["expires_at"]) or r["expires_at"] <= r["issued_at"])
                               or not r["reusable"] and r["expires_at"] is None):
            raise MembershipError("invalid_invite")

    def admissions(self, endpoint, view):
        return [rid for rid in view if
                (self.records[rid]["op"] == "initialize" and self.records[rid]["issuer"] == endpoint)
                or (self.records[rid]["op"] == "admit" and self.records[rid]["endpoint_id"] == endpoint)]

    def active(self, endpoint, view=None):
        view = self.all if view is None else view
        return any(self.admission_active(rid, view) for rid in self.admissions(endpoint, view))

    def admission_active(self, rid, view=None):
        """Whether this particular admission still survives every known removal."""
        view = self.all if view is None else view
        admission = self.records[rid]
        endpoint = admission["issuer"] if admission["op"] == "initialize" else admission["endpoint_id"]
        removals = {rid for rid in view if self.records[rid]["op"] == "remove"
                    and self.records[rid]["endpoint_id"] == endpoint}
        return removals <= self.ancestors[rid]

    def invite(self, invite_hash, view=None):
        view = self.all if view is None else view
        matches = [self.records[rid] for rid in sorted(view)
                   if self.records[rid]["op"] == "invite"
                   and self.records[rid]["invite_hash"] == invite_hash]
        if len(matches) != 1:
            raise MembershipError("unknown_invite")
        return matches[0]

    def revoked(self, invite_hash, view=None):
        view = self.all if view is None else view
        return any(self.records[rid]["op"] == "revoke"
                   and self.records[rid]["invite_hash"] == invite_hash for rid in view)

    def uses(self, invite_hash, view=None):
        view = self.all if view is None else view
        return [self.records[rid] for rid in sorted(view)
                if self.records[rid]["op"] == "admit"
                and self.records[rid]["invite_hash"] == invite_hash]

    def _operation(self, r, view):
        op = r["op"]
        if op == "invite":
            if any(self.records[rid].get("invite_hash") == r["invite_hash"] for rid in view):
                raise MembershipError("duplicate_invite")
        elif op in ("admit", "revoke"):
            invite = self.invite(r["invite_hash"], view)
            if op == "revoke":
                return  # Every active member has the same revocation authority.
            if self.revoked(r["invite_hash"], view):
                raise MembershipError("revoked_invite")
            if not self.active(invite["issuer"], view):
                raise MembershipError("inactive_invite_issuer")
            if invite["expires_at"] is not None and r["issued_at"] >= invite["expires_at"]:
                raise MembershipError("expired_invite")
            if not invite["reusable"]:
                if r["issuer"] != invite["issuer"]:
                    raise MembershipError("issuer_required")
                if self.uses(r["invite_hash"], view):
                    raise MembershipError("invite_consumed")
            if self.active(r["endpoint_id"], view):
                raise MembershipError("already_member")
        elif op == "remove" and not self.active(r["endpoint_id"], view):
            raise MembershipError("inactive_member")

    def state(self):
        return {"version": 1, "network_id": self.network_id,
                "records": [copy.deepcopy(self.records[rid]) for rid in self.order]}

    def heads(self):
        return sorted(self.all - {p for r in self.records.values() for p in r["parents"]})


class MembershipStore:
    """Private file store; callbacks are sign(bytes)->hex and verify(key,bytes,hex)->bool.

    All readers and mutations take a stable sibling flock and read afresh. Writes
    fsync a private temporary file, replace membership.json, then fsync the
    directory. No in-memory state is changed on failed validation or replacement.
    Errors raise MembershipError (ValueError); filesystem errors propagate.
    """

    def __init__(self, root, node_id, sign, verify, clock=time.time):
        if not _hex(node_id) or not callable(sign) or not callable(verify):
            raise MembershipError("invalid_identity")
        self.root = Path(root)
        self.node_id = node_id
        self.sign = sign
        self.verify = verify
        self.clock = clock
        self.path = self.root / "membership.json"

    @contextmanager
    def _locked(self):
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(str(self.root / "membership.lock"),
                     os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def _read(self):
        try:
            fd = os.open(str(self.path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            return None
        with os.fdopen(fd, "rb") as stream:
            data = stream.read(MAX_STATE_BYTES + 1)
        if len(data) > MAX_STATE_BYTES:
            raise MembershipError("state_too_large")
        try:
            state = json.loads(data)
        except (ValueError, UnicodeError, RecursionError):
            raise MembershipError("invalid_state") from None
        return _Graph(state, self.verify)

    def _write(self, graph):
        data = _json(graph.state())
        fd, staged = tempfile.mkstemp(prefix=".membership-", dir=str(self.root))
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(staged, str(self.path))
            directory = os.open(str(self.root), os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(staged):
                os.unlink(staged)

    def _required(self):
        graph = self._read()
        if graph is None:
            raise MembershipError("not_initialized")
        return graph

    @property
    def network_id(self):
        """Return the root-bound network ID string, or None before joining."""
        with self._locked():
            graph = self._read()
            return graph.network_id if graph else None

    @property
    def founder(self):
        """Return the immutable genesis public key, or None before joining.

        This is a trust anchor, not an administrator role. Removal of this
        device never changes the root identity or other members' authority.
        """
        with self._locked():
            graph = self._read()
            return graph.records[graph.root]["issuer"] if graph else None

    @property
    def founder_public_key(self):
        """Return founder (explicit public-key spelling for control consumers)."""
        return self.founder

    def _now(self):
        now = self.clock()
        if not _number(now):
            raise MembershipError("invalid_time")
        return now

    def _record(self, op, graph=None, issued_at=None, **fields):
        now = self._now() if issued_at is None else issued_at
        if graph and now < max(r["issued_at"] for r in graph.records.values()):
            raise MembershipError("clock_behind")
        r = dict(domain=DOMAIN, op=op, network_id=graph.network_id if graph else "",
                 issuer=self.node_id, parents=graph.heads() if graph else [], issued_at=now, **fields)
        if graph is None:
            r["network_id"] = _network_id(r)
        r["signature"] = self.sign(_json(r))
        return r

    def _append(self, graph, record):
        result = self._stage(graph, record)
        self._write(result)
        return result

    def _stage(self, graph, record):
        """Validate one additional record in memory, without committing it."""
        state = graph.state()
        state["records"].append(record)
        return _Graph(state, self.verify)

    def initialize(self, name, machine_name):
        """Return signed wire state {version, network_id, records}; refuse overwrite."""
        with self._locked():
            if self._read() is not None:
                raise MembershipError("already_initialized")
            record = self._record("initialize", name=name, machine_name=machine_name,
                                  nonce=secrets.token_hex(32))
            graph = _Graph({"version": 1, "network_id": record["network_id"],
                            "records": [record]}, self.verify)
            self._write(graph)
            return graph.state()

    def snapshot(self):
        """Return signed wire state (or {} before joining), for active peers only.

        The caller must authenticate the recipient; this local method has no
        remote caller identity. It never returns invite secrets or private keys.
        """
        with self._locked():
            graph = self._read()
            return graph.state() if graph else {}

    @staticmethod
    def _members(graph):
        endpoints = {r["issuer"] if r["op"] == "initialize" else r["endpoint_id"]
                     for r in graph.records.values() if r["op"] in ("initialize", "admit")}
        result = []
        for endpoint in sorted(endpoints):
            admissions = graph.admissions(endpoint, graph.all)
            latest = max(admissions, key=lambda rid: (len(graph.ancestors[rid]), rid))
            result.append({"endpoint_id": endpoint, "machine_name": graph.records[latest]["machine_name"],
                           "status": "active" if graph.active(endpoint) else "removed"})
        return result

    def public_state(self):
        """Return {} or {version,network_id,name,members,invites}; no bearer secrets.

        members are {endpoint_id,machine_name,status}; invite rows contain only
        invite_hash/issuer/reusable/expires_at/revoked/consumed_by, never a token.
        """
        with self._locked():
            graph = self._read()
            if not graph:
                return {}
            invites = []
            for rid in sorted(graph.all):
                r = graph.records[rid]
                if r["op"] == "invite":
                    invites.append({k: r[k] for k in ("invite_hash", "issuer", "reusable", "expires_at")})
                    invites[-1].update(revoked=graph.revoked(r["invite_hash"]),
                                       consumed_by=sorted({u["endpoint_id"] for u in graph.uses(r["invite_hash"])}))
            return {"version": 1, "network_id": graph.network_id,
                    "name": graph.records[graph.root]["name"],
                    "members": self._members(graph), "invites": invites}

    def members(self):
        """Return [{endpoint_id,machine_name,status}] including removed devices."""
        return self.public_state().get("members", [])

    def is_active(self, endpoint_id):
        """Return bool; only the exact authenticated endpoint key has authority."""
        with self._locked():
            graph = self._read()
            return bool(graph and graph.active(endpoint_id))

    def issue_invite(self, reusable=True, lifetime_seconds=None):
        """Return {secret,invite,network_id}; invite is the signed invite record.

        A one-time invite requires a caller-specified positive lifetime in
        seconds. Reusable invites may have no expiration. Secrets are not saved.
        """
        if (type(reusable) is not bool or lifetime_seconds is not None
                and (not _number(lifetime_seconds) or lifetime_seconds <= 0)
                or not reusable and lifetime_seconds is None):
            raise MembershipError("invalid_lifetime")
        with self._locked():
            graph = self._required()
            if not graph.active(self.node_id):
                raise MembershipError("inactive_issuer")
            secret = secrets.token_urlsafe(32)
            now = self._now()
            r = self._record("invite", graph, invite_hash=hashlib.sha256(secret.encode()).hexdigest(),
                             reusable=reusable, issued_at=now,
                             expires_at=now + lifetime_seconds if lifetime_seconds is not None else None)
            self._append(graph, r)
            return {"secret": secret, "invite": copy.deepcopy(r), "network_id": graph.network_id}

    def redeem(self, secret, endpoint_id, machine_name):
        """Return {network_id,admission,state}, only after durable acceptance.

        The transport must bind endpoint_id to its authenticated peer. Reusable
        links work at any active member; one-time links work only at the issuer
        (otherwise issuer_required). A lost response is recoverable for the same
        active device even after expiry; revoke/removal still refuse the retry.
        Removal/leave revokes known live reusable links in the same commit.
        Rejoining requires a newly issued link or a separate unused one-time
        invite. No network RPC is performed here when the issuer is offline.
        """
        if (not isinstance(secret, str) or not 16 <= len(secret) <= 512
                or not _hex(endpoint_id) or not _text(machine_name)):
            raise MembershipError("invalid_redemption")
        invite_hash = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        with self._locked():
            graph = self._required()
            invite = graph.invite(invite_hash)
            if not graph.active(self.node_id) or not graph.active(invite["issuer"]):
                raise MembershipError("inactive_issuer")
            if graph.revoked(invite_hash):
                raise MembershipError("revoked_invite")
            if not invite["reusable"] and self.node_id != invite["issuer"]:
                raise MembershipError("issuer_required")
            uses = graph.uses(invite_hash)
            previous = [r for r in uses if r["endpoint_id"] == endpoint_id
                        and graph.admission_active(_hash(r))]
            if previous:
                admission = max(previous, key=lambda r: (len(graph.ancestors[_hash(r)]), _hash(r)))
                return {"network_id": graph.network_id, "admission": copy.deepcopy(admission), "state": graph.state()}
            if uses and not invite["reusable"]:
                raise MembershipError("invite_consumed")
            if invite["expires_at"] is not None and self._now() >= invite["expires_at"]:
                raise MembershipError("expired_invite")
            if graph.active(endpoint_id):
                raise MembershipError("already_member")
            admission = self._record("admit", graph, invite_hash=invite_hash,
                                     endpoint_id=endpoint_id, machine_name=machine_name)
            result = self._append(graph, admission)
            return {"network_id": graph.network_id, "admission": copy.deepcopy(admission), "state": result.state()}

    def merge(self, state):
        """Validate same-network wire state; return durable deterministic union.

        An uninitialized store must use adopt. Existing removals/revocations are
        retained when merging an older snapshot. No unsigned native member list
        or name-based authority can be imported.
        """
        with self._locked():
            current = self._required()
            incoming = _Graph(state, self.verify)
            if current.network_id != incoming.network_id:
                raise MembershipError("wrong_network")
            union = dict(current.records)
            union.update(incoming.records)
            graph = _Graph({"version": 1, "network_id": current.network_id,
                            "records": list(union.values())}, self.verify)
            self._write(graph)
            return graph.state()

    def adopt(self, state):
        """Return verified durable wire state, replacing a prior network atomically.

        The new network must already admit this device. Verification, including
        its admission chain, completes before replacement. Same-network adopt
        unions history to prevent rollback. Validation/replace failures leave
        the previous network file unchanged, so it remains usable after restart.
        """
        with self._locked():
            incoming = _Graph(state, self.verify)
            if not incoming.active(self.node_id):
                raise MembershipError("not_admitted")
            current = self._read()
            if current and current.network_id == incoming.network_id:
                union = dict(current.records)
                union.update(incoming.records)
                incoming = _Graph({"version": 1, "network_id": current.network_id,
                                   "records": list(union.values())}, self.verify)
                if not incoming.active(self.node_id):
                    raise MembershipError("not_admitted")
            self._write(incoming)
            return incoming.state()

    def remove(self, endpoint_id):
        """Return signed wire state after atomic removal and reusable-link rotation.

        Any active member may remove a device. Under one lock, stage revocations
        of every known, unrevoked, unexpired reusable invite before the removal
        record, then commit all records once. Staging revocations first also
        permits self-removal: their signer is still active in their causal view.
        A pre-commit signing/validation/write failure preserves the original file.

        New links may be issued by surviving active members. Unknown offline
        forks are outside this guarantee; this is not cryptographic eviction of
        malicious members or retroactive invalidation of accepted admissions.
        """
        if not _hex(endpoint_id):
            raise MembershipError("invalid_identity")
        with self._locked():
            graph = self._required()
            if not graph.active(self.node_id):
                raise MembershipError("inactive_issuer")
            if not graph.active(endpoint_id):
                raise MembershipError("inactive_member")
            now = self._now()
            invites = sorted({r["invite_hash"] for r in graph.records.values()
                              if r["op"] == "invite" and r["reusable"]
                              and not graph.revoked(r["invite_hash"])
                              and (r["expires_at"] is None or now < r["expires_at"])})
            for invite_hash in invites:
                record = self._record("revoke", graph, issued_at=now, invite_hash=invite_hash)
                graph = self._stage(graph, record)
            record = self._record("remove", graph, issued_at=now, endpoint_id=endpoint_id)
            result = self._stage(graph, record)
            self._write(result)
            return result.state()

    def revoke_invite(self, invite_hash):
        """Return signed wire state after revocation by any active member."""
        if not _hex(invite_hash):
            raise MembershipError("invalid_invite")
        with self._locked():
            graph = self._required()
            record = self._record("revoke", graph, invite_hash=invite_hash)
            return self._append(graph, record).state()

    def leave(self):
        """Return wire state after atomic self-removal and reusable-link rotation."""
        return self.remove(self.node_id)
