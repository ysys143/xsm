"""Caller-owned attachment preparation shared by CLI and MCP.

The CLI reads paths with its own OS authority. MCP supplies only already-read
inline content. Frozen copies are reused by exact request id across approval
waits; changed originals never replace them silently. This module does not
grant a scope, deliver a body, or infer an unknown peer's file capability.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os

from . import context, envelope, files, handoff, paths, probe, registry, resolve


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def prepare(caller, target, body, request_id, items=None, *, source="inline",
            manifest_id=None, previous=None, fallback=None, call=None):
    """Return final body, immutable refs and a validated packet; never send.

    No items/manifest means the ordinary messaging path. ``fallback=inline``
    is explicit, changes the final body before its request digest is made, and
    sends no pretend file packet to a peer that cannot receive files.
    """
    if not items and not manifest_id:
        return {"body": body, "attachments": [], "file_packet": None,
                "file_limits": None, "manifest_id": None, "mode": "none"}
    why = context.require_sure(call, "prepare attachments") if call else None
    if why:
        raise files.FileError("caller-unverified", why, request_id)
    identity = handoff._identity(caller)
    handoff._id(request_id)
    if source not in ("inline", "cli"):
        raise files.FileError("invalid-source", "use caller-inline or CLI paths", request_id)
    if items and manifest_id:
        raise files.FileError("ambiguous-input", "reuse a manifest or supply new items, not both", request_id)
    if fallback not in (None, "inline"):
        raise files.FileError("invalid-fallback", "only explicit inline fallback is supported", request_id)
    limits = files.product_limits()
    key = _digest([identity, request_id])
    folder = paths.path("material-intents")
    os.makedirs(folder, mode=0o700, exist_ok=True)
    fd = os.open(os.path.join(folder, key + ".lock"), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        filename = os.path.join(folder, key + ".json")
        try:
            with open(filename, encoding="utf-8") as stream:
                memo = json.load(stream)
        except FileNotFoundError:
            memo = None
        except (OSError, ValueError) as exc:
            raise files.FileError("intent-unavailable", "attachment intent cannot be read", request_id) from exc
        input_digest = _digest({"body": body, "items": items, "source": source,
                                "previous": previous})
        if memo:
            if not isinstance(memo, dict) or memo.get("owner") != identity or memo.get("body_digest") != _digest(body):
                raise files.FileError("intent-conflict", "request id belongs to other attachment input", request_id)
            if manifest_id:
                if memo.get("manifest_id") != manifest_id:
                    raise files.FileError("intent-conflict", "request id has a different frozen manifest", request_id)
            elif memo.get("input_digest") != input_digest:
                raise files.FileError("intent-conflict", "request id has different attachment input", request_id)
            manifest_id = memo["manifest_id"]
        elif manifest_id is None:
            build = files.prepare_cli if source == "cli" else files.prepare_inline
            manifest = build(caller, request_id, body, items, limits=limits, previous=previous)
            manifest_id = manifest["id"]
            paths.write_json(filename, {"owner": identity, "request_id": request_id,
                             "body_digest": _digest(body), "input_digest": input_digest,
                             "manifest_id": manifest_id})
        if source == "inline":
            # The caller already read these exact private-copy bytes. Exporting
            # that version needs no new source-path read or source permission.
            packet=files.export_frozen(caller,manifest_id,request_id,body)
        else:
            packet = files.export_packet(caller, manifest_id, request_id=request_id, body=body)
    except files.FileError as exc:
        exc.manifest_id = manifest_id
        raise
    finally:
        os.close(fd)
    with probe.quick():
        found = (resolve.resolve(target, caller=caller)
                 if target.strip().startswith(("candidate:", "net:")) else resolve.resolve(target))
    if not found.ok:
        exc=files.FileError("target-unavailable", found.reason, request_id)
        exc.manifest_id=manifest_id
        raise exc
    if found.record.get("remote"):
        from . import network
        try:
            answer = network.call({"op": "capabilities", "caller": caller,
                                   "target": found.record["target"]})
            capability = answer.get("capabilities") if isinstance(answer, dict) else None
        except network.NetworkError as exc:
            capability = {"status": "unknown", "reason": str(exc)}
        if not isinstance(capability, dict):
            capability = {"status": "unknown", "reason": "no remote reader observation"}
        elif capability.get("status") != "observed":
            capability = dict(capability, status="unknown")
    else:
        capability = registry.file_capability(found.record)
    try:
        negotiated = files.negotiate(packet, request_id=request_id, body=body,
                                    capability=capability, limits=limits, fallback=fallback)
    except files.FileError as exc:
        exc.manifest_id=manifest_id
        raise
    mode = negotiated["mode"]
    return {"body": negotiated["body"], "attachments": [negotiated["reference"]] if mode == "files" else [],
            "file_packet": negotiated["packet"], "file_limits": limits,
            "manifest_id": manifest_id, "mode": mode}


def public(prepared):
    return {"manifest_id": prepared["manifest_id"], "mode": prepared["mode"],
            "references": prepared["attachments"]}


def failure(exc):
    return {"status":"attachment-error","code":exc.code,"reason":str(exc),
            "request_id":exc.request_id,"manifest_id":getattr(exc,"manifest_id",None),
            "body_sent":False,"recovery":"keep the same request ID/body and frozen manifest; a changed snapshot requires a new request"}
