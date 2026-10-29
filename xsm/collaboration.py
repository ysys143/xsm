"""Selected native-conversation permissions (ADR-0024).

This is a permission store, not discovery, consent collection, or a completed
handshake. Callers authenticate the current endpoints, obtain a real affirmative
user verdict through consent, and verify liveness/generation on resume. Neither
peer ACKs nor discovery metadata are evidence of user consent here.
"""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import time

from . import paths

DIRECTORY = "collaborations"


def _identity(record: Mapping) -> dict:
    if not isinstance(record, Mapping):
        raise ValueError("a native conversation record is required")
    if "home_id" in record or record.get("remote"):
        from .network_identity import endpoint
        return endpoint(dict(record))
    result = {}
    for field in ("runtime", "home", "session_id"):
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("native conversation requires %s" % field)
        result[field] = value
    result["home"] = os.path.realpath(os.path.expanduser(result["home"]))
    return result


def _pair(sender: Mapping, target: Mapping) -> tuple[list[dict], str]:
    endpoints = sorted((_identity(sender), _identity(target)),
                       key=lambda item: json.dumps(item, sort_keys=True))
    if endpoints[0] == endpoints[1]:
        raise ValueError("collaboration requires two distinct conversations")
    encoded = json.dumps(endpoints, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return endpoints, hashlib.sha256(encoded).hexdigest()


def propose(sender: Mapping, target: Mapping) -> dict:
    """Return a detached exact-pair proposal; do not persist or grant anything."""
    endpoints, key = _pair(sender, target)
    return {"id": key, "kind": "collaboration", "endpoints": endpoints}


@contextmanager
def _locked(key: str):
    # Keep the lock inode even after drop so concurrent waiters serialize with
    # later creates. Each pair has its own file, avoiding whole-store lost writes.
    folder = paths.path(DIRECTORY)
    os.makedirs(folder, mode=0o700, exist_ok=True)
    fd = os.open(os.path.join(folder, key + ".lock"), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _stored(proposal: dict) -> dict | None:
    record = paths.read_json(paths.path(DIRECTORY, proposal["id"] + ".json"))
    if not isinstance(record, dict):
        return None
    if (record.get("id") != proposal["id"] or record.get("kind") != "collaboration"
            or record.get("endpoints") != proposal["endpoints"]
            or record.get("active") is not True
            or not isinstance(record.get("verdict"), str)
            or not record["verdict"].strip()):
        return None
    return record


def create(sender: Mapping, target: Mapping, verdict: str) -> dict:
    """Persist a bidirectional permission after the caller obtained consent.

    Preserve the original verdict verbatim. This function does not interpret
    natural language or establish its source: that is the consent coordinator's
    responsibility. An active pair is idempotent and retains its first evidence.
    A dropped pair needs a fresh create with consent to become active again.
    """
    if not isinstance(verdict, str) or not verdict.strip():
        raise ValueError("a user verdict obtained through consent is required")
    proposal = propose(sender, target)
    with _locked(proposal["id"]):
        existing = _stored(proposal)
        if existing is not None:
            return existing
        from . import config
        config.require_valid_policy()
        record = dict(proposal, active=True, verdict=verdict, created_at=time.time())
        paths.write_json(paths.path(DIRECTORY, proposal["id"] + ".json"), record)
        return record


def scope_for(sender: Mapping, target: Mapping) -> dict | None:
    """Return exact-pair permission evidence, or None; never infer folder scope.

    Invalid/incomplete current identities fail closed. This result does not
    override machine authentication, block policies, or endpoint termination.
    """
    try:
        proposal = propose(sender, target)
    except ValueError:
        return None
    return _stored(proposal)


def drop(sender: Mapping, target: Mapping) -> bool:
    """Revoke both directions atomically. Return whether an active pair changed.

    Retain the verdict and identities as revoked evidence; unrelated pairs and
    discovery publication are untouched. Lifecycle callers use this on session
    termination or permission withdrawal, but not temporary offline/resume.
    """
    proposal = propose(sender, target)
    with _locked(proposal["id"]):
        record = _stored(proposal)
        if record is None:
            return False
        record.update(active=False, revoked_at=time.time())
        paths.write_json(paths.path(DIRECTORY, proposal["id"] + ".json"), record)
        return True
