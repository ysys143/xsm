"""Owner-only recovery of outbound originals, independent of the running network.

Archiving hides a local pending item and prevents another dispatch of its ID.
It does not cancel remote execution or discard evidence or late replies.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import time

from . import envelope, handoff, network, network_identity, network_messages


def _original(caller, request_id):
    request_id = handoff._id(request_id)
    root = network.root() / "messages"
    identity = network._read_private(network.root() / "identity.json")
    raw = network_messages._read(root / "outbound" / (request_id + ".json"))
    if raw is None or handoff._identity(raw.get("local")) != handoff._identity(caller):
        raise ValueError("request not found for this conversation")
    gateway = network_messages.Gateway(root, identity["endpoint_id"], lambda *args: False)
    gateway.network_id = raw.get("packet", {}).get("network_id")
    record = gateway._load("outbound", request_id)
    if record is None or handoff._identity(record["local"]) != handoff._identity(caller):
        raise ValueError("request not found for this conversation")
    return gateway, record


def requests(caller, include_archived=False):
    handoff._identity(caller)
    folder = network.root() / "messages" / "outbound"
    if not folder.exists():
        return []
    rows = []
    for path in folder.glob("*.json"):
        try:
            _, record = _original(caller, path.stem)
            if record.get("archived_at") is not None and not include_archived:
                continue
            packet = record["packet"]
            rows.append({"id": record["id"], "network_id": packet["network_id"],
                         "target": network_identity.target(packet["receiver"]),
                         "kind": packet["kind"], "preview": envelope.preview(packet["body"]),
                         "stored_at": record["stored_at"], "archived_at": record.get("archived_at"),
                         "recovery_only": True})
        except (OSError, ValueError, TypeError, KeyError):
            continue
    return sorted(rows, key=lambda row: (row["stored_at"], row["id"]), reverse=True)


def export(caller, request_id, output):
    _, record = _original(caller, request_id)
    value = {"version": 1, "kind": "xsm-outbound-original", "untrusted_data": True,
             "packet": copy.deepcopy(record["packet"]), "archived_at": record.get("archived_at"),
             "attachment_payloads": "external-quota-ttl-store" if record["packet"]["attachments"] else "none"}
    body = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2).encode()
    destination = Path(output).expanduser().absolute()
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    return {"status": "exported", "id": record["id"], "path": str(destination),
            "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}


def archive(caller, request_id):
    gateway, _ = _original(caller, request_id)
    with gateway._locked():
        record = gateway._load("outbound", request_id)
        if record is None or handoff._identity(record["local"]) != handoff._identity(caller):
            raise ValueError("request not found for this conversation")
        record.setdefault("archived_at", time.time())
        network_messages._write(gateway._path("outbound", request_id), record)
    return {"status": "archived", "id": request_id, "original_retained": True,
            "remote_execution_cancelled": False}
