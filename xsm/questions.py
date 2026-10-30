"""Durable correlated questions. Receive calls record_reply only after auth.

Waiting never consumes inboxes. Callbacks are zero-argument functions; pump
returns False on client EOF (None/True continue). It is
called outside file locks so the MCP owner can remain its sole input reader.
A claimed send is never automatically retried after a crash (delivery unknown).
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import fcntl
import hashlib
import json
import math
import os
import re
import time

from . import config, envelope, ledger, paths, probe, resolve, send

DIRECTORY = "questions"
# Automatic wake follows transport policy; never is a strictly passive local send.
CAPABILITIES = {"attachments": True, "wake_control": True,
                "priority": send.PRIORITY_CAPABILITIES}


def _filename(request_id):
    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", request_id):
        raise ValueError("invalid request ID")
    return paths.path(DIRECTORY, request_id + ".json")


@contextmanager
def _locked(request_id):
    filename = _filename(request_id)
    os.makedirs(os.path.dirname(filename), mode=0o700, exist_ok=True)
    fd = os.open(filename + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield filename
    finally:
        os.close(fd)


def _native(record):
    if not isinstance(record, dict):
        raise ValueError("native identity required")
    if "home_id" in record or record.get("remote"):
        from .network_identity import endpoint
        return endpoint(record)
    values = {key: record.get(key) for key in ("runtime", "home", "session_id")}
    if any(not isinstance(v, str) or not v.strip() for v in values.values()):
        raise ValueError("runtime, home and session_id required")
    values["home"] = os.path.realpath(os.path.expanduser(values["home"]))
    return values


def _handle(record):
    return dict(_native(record), **{k: record.get(k) for k in ("ref", "name", "alias")})


def _result(request_id, record=None, state=None, reason=None):
    # Public results own their nested data; auth records retain native homes.
    record = copy.deepcopy(record) if record is not None else None
    replies = (record or {}).get("replies", [])
    for reply in replies:
        for endpoint in ("sender", "receiver"):
            handle = reply.get(endpoint)
            if isinstance(handle, dict) and "home" in handle:
                home = handle.pop("home")
                handle["home_id"] = hashlib.sha256(home.encode("utf-8")).hexdigest()
    final_outcome = next((r["outcome"] for r in reversed(replies)
                          if r.get("outcome") in envelope.OUTCOMES), None)
    final = final_outcome is not None
    send_state = ((record or {}).get("send_evidence") or {}).get("status")
    current = ledger.status(request_id) if record else {}
    terminal = ("held", "blocked", "refused", "error")
    current_state = current.get("status")
    pending_state = (current_state if current_state in terminal else
                     send_state if send_state in terminal and current_state != "delivered"
                     else "pending")
    result = {"status": state or ("final" if final else "reply_received" if replies else pending_state),
              "id": request_id, "purpose": (record or {}).get("purpose"),
              "created_at": (record or {}).get('created_at'),
              "replies": replies, "final": final,
              "final_outcome": final_outcome,
              "recover_at": ({"cli": ["xsm", "question-status", request_id],
                             "mcp": {"tool": "xsm_question_status",
                                     "arguments": {"id": request_id}}} if record else None),
              "wait_end_reason": pending_state if not replies and pending_state in terminal else None,
              "capabilities": copy.deepcopy(CAPABILITIES),
              "wake": "never" if (record or {}).get("wake")=="never" else "transport_policy", "send_evidence": (record or {}).get("send_evidence"),
              "delivery_evidence": ledger.evidence_of(request_id) if record else None,
              "handshake": "not-started"}
    if record and record.get("purpose") == "handshake":
        result["handshake"] = (
            "completed" if final_outcome == "succeeded" else
            "declined" if final_outcome == "failed" else
            "reply_received" if replies else "pending")
    if reason:
        result["reason"] = reason
    elif not replies and pending_state in terminal:
        result["reason"] = ((current.get("receipt") or {}).get("reason") or
                            current.get("error") or
                            (record.get("send_evidence") or {}).get("reason") or pending_state)
    return result


def status(sender, request_id):
    """Read only the owner's request, including late and partial replies."""
    try:
        record = paths.read_json(_filename(request_id))
        if not record:
            return _result(request_id, state="not-found")
        if _native(sender) != _native(record["sender"]):
            return _result(request_id, state="refused", reason="request belongs to another conversation")
    except (ValueError, KeyError, TypeError):
        return _result(request_id, state="refused", reason="invalid request or caller identity")
    return _result(request_id, record)


def list_requests(sender):
    """Read-only recovery of IDs owned by this exact native conversation.

    Return metadata only, never reply bodies or other owners' requests. A lost
    auto-ID can be recovered here after cancellation without sending again.
    Invalid records and symlinks are skipped; no locks or state are created.
    """
    try:
        owner = _native(sender)
    except ValueError:
        return []
    rows = []
    try:
        with os.scandir(paths.path(DIRECTORY)) as entries:
            for entry in entries:
                try:
                    if not entry.name.endswith(".json") or not entry.is_file(follow_symlinks=False):
                        continue
                    request_id = entry.name[:-5]
                    record = paths.read_json(_filename(request_id))
                    if not isinstance(record, dict) or record.get("id") != request_id:
                        continue
                    if _native(record["sender"]) != owner:
                        continue
                    _native(record["target"])
                    created = record["created_at"]
                    if (record.get("purpose") not in ("question", "handshake") or
                            not isinstance(record.get("body"), str) or
                            not isinstance(record.get("digest"), str) or
                            not re.fullmatch(r"[0-9a-f]{64}", record["digest"]) or
                            isinstance(created, bool) or not isinstance(created, (int, float)) or
                            not math.isfinite(created) or not isinstance(record.get("replies"), list)):
                        continue
                    public_target = _handle(record["target"])
                    if "home" in public_target:
                        home = public_target.pop("home")
                        public_target["home_id"] = hashlib.sha256(home.encode("utf-8")).hexdigest()
                    rows.append({"id": request_id, "purpose": record["purpose"],
                                 "target": public_target, "preview": envelope.preview(record["body"]),
                                 "digest": record["digest"], "created_at": created,
                                 "status": _result(request_id, record)["status"]})
                except (OSError, ValueError, KeyError, TypeError, AttributeError):
                    continue
    except OSError:
        return []
    return sorted(rows, key=lambda row: (row["created_at"], row["id"]), reverse=True)


def _duration(wait):
    value = float(wait)
    if not math.isfinite(value) or value < 0:
        raise ValueError("wait must be finite and nonnegative")
    return value


def wait_for(sender, request_id, wait=0, pump=None, cancelled=None):
    """Wait for a correlated reply, not delivery; timeout/cancel retains state."""
    deadline = time.monotonic() + _duration(wait)
    while True:
        result = status(sender, request_id)
        if result["status"] != "pending":
            result["wait_end_reason"] = "reply" if result["replies"] else result["status"]
            return result
        if cancelled is not None and cancelled():
            result["wait_end_reason"] = "cancelled"
            return result
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            result["wait_end_reason"] = "timeout"
            return result
        if pump is not None:
            client_live = pump()
            # Re-read after callbacks, including replies arriving at the deadline.
            result = status(sender, request_id)
            if result["status"] != "pending":
                result["wait_end_reason"] = "reply" if result["replies"] else result["status"]
                return result
            if client_live is False:
                result["wait_end_reason"] = "client_closed"
                return result
        time.sleep(min(0.02, max(0, deadline - time.monotonic())))


def ask(sender, target_spec, body, wait=0, request_id=None, priority="next",
        pump=None, cancelled=None, purpose="question", attachments=None,
        file_packet=None, file_limits=None, wake="auto"):
    """Claim one send, then return the same dict contract as status/wait_for.

    Sender/target full handles, body and digest are retained. Reusing an ID
    cannot send twice, even after uncertain delivery. Different content refuses.
    """
    _duration(wait)
    request_id = request_id or envelope.new_id()
    try:
        _filename(request_id)
        _native(sender)
        if not isinstance(body, str) or not body.strip():
            raise ValueError("question body required")
        if purpose not in ("question", "handshake") or priority not in ("next", "now"):
            raise ValueError("unsupported purpose or priority")
        if wake not in ("auto", "never"):
            raise ValueError("unsupported wake mode; use auto or never")
        target_spec = target_spec.strip()
        candidate = target_spec.startswith("candidate:")
        remote = target_spec.startswith("net:")
        with probe.quick():
            found = (resolve.resolve(target_spec, caller=sender) if candidate or remote
                     else resolve.resolve(target_spec))
        if not found.ok:
            return _result(request_id, state="refused", reason=found.reason)
        target = found.record
        remote = remote or target.get("remote") is True
        why_priority = send.priority_refusal(target, priority)
        if why_priority:
            return _result(request_id, state="refused", reason=why_priority)
        identity = {"sender": _native(sender), "target": _native(target),
                    "body": envelope.request_identity(
                        request_id, sender, target, body, kind="task")["body"],
                    "priority": priority, "purpose": purpose}
        if attachments:
            identity["attachments"] = envelope.request_identity(request_id, sender, target, body,
                                                               attachments=attachments)["attachments"]
        if wake != "auto":
            identity["wake"] = wake
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True,
                                           ensure_ascii=False).encode("utf-8")).hexdigest()
        with _locked(request_id) as filename:
            record = paths.read_json(filename)
            if record:
                if record.get("digest") != digest:
                    return _result(request_id, state="refused", reason="request ID content or endpoints differ")
            else:
                if remote:
                    scope, reason = found.scope, "select the exact remote conversation before asking"
                else:
                    scope, reason = config.scope_for(sender, target)
                if not scope:
                    return _result(request_id, state="selection-required", reason=reason)
                if ledger.status(request_id):
                    return _result(request_id, state="refused", reason="ID already used outside questions")
                record = {"id": request_id, "sender": _handle(sender), "target": _handle(target),
                          "body": body, "digest": digest, "purpose": purpose, "priority": priority,
                          "attachments": attachments or [], "wake": wake,
                          "created_at": time.time(), "replies": [], "send_claimed": True,
                          "send_evidence": {"status": "unknown", "reason": "send claimed; not retried"}}
                paths.write_json(filename, record)
                # Register the exact outbound intent before dispatch. The send
                # resend path revalidates this digest and never offers folders.
                ledger.queued(request_id, sender, target, scope, "task", body,
                              priority=priority, attachments=attachments)
                record = None  # this caller alone owns the initial send
        if record is None:
            # Only the claimant dispatches the prepared intent. resend=True is
            # used for its no-widening revalidation, never for a second dispatch.
            try:
                address = target_spec if candidate or remote else "%s:%s" % (
                    target["runtime"], target["session_id"])
                sent = send.send(address, body, sender=sender, kind="task",
                                 priority=priority, msg_id=request_id,
                                 resend=True, wake=wake != "never", attachments=attachments,
                                 file_packet=file_packet, file_limits=file_limits)
                evidence = sent.as_dict()
            except Exception as exc:
                evidence = {"status": "error", "reason": str(exc), "id": request_id}
            with _locked(request_id) as filename:
                record = paths.read_json(filename)
                record["send_evidence"] = evidence
                paths.write_json(filename, record)
        return wait_for(sender, request_id, wait, pump, cancelled)
    except (ValueError, TypeError) as exc:
        return _result(request_id, state="refused", reason=str(exc))


def _answerer(sender, target):
    """The asked session, or the one it handed its place over to (handover.py)."""
    if _native(sender) == _native(target):
        return True
    if "home_id" in target or target.get("remote"):
        return False
    from . import handover
    return handover.succeeds(sender, target)


def expects_reply(receiver, sender, request_id):
    """Whether this exact pair has a stored request; read-only, not receive auth.

    Used to retain transport reply copies only for indexed questions. The
    authenticated receive path must still validate the actual incoming frame
    before calling record_reply. Partial/final answers do not expire the pair.
    """
    try:
        record = paths.read_json(_filename(request_id))
        return bool(record and record.get("id") == request_id
                    and _native(receiver) == _native(record["sender"])
                    and _answerer(sender, record["target"]))
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


def record_reply(receiver, sender, header, body):
    """After receive authentication, store only a reply from the selected peer.

    receiver is the original questioner, sender the authenticated replying peer.
    Header claims never substitute for these native identities. Duplicate IDs
    are idempotent; changed content under a reply ID is rejected.
    """
    if not isinstance(header, dict) or header.get("kind") != "reply":
        return False
    request_id = header.get("reply-to") or header.get("reply_to")
    reply_id = header.get("id")
    try:
        _filename(request_id)
        _filename(reply_id)
        if not isinstance(body, str):
            return False
        outcome = header.get("outcome")
        if outcome is not None and outcome not in envelope.OUTCOMES:
            return False
        with _locked(request_id) as filename:
            record = paths.read_json(filename)
            if not record or _native(receiver) != _native(record["sender"]) or \
                    not _answerer(sender, record["target"]):
                return False
            reply = {"id": reply_id, "body": body, "outcome": outcome,
                     "sender": _handle(sender), "receiver": _handle(receiver)}
            for previous in record["replies"]:
                if previous["id"] == reply_id:
                    return all(previous.get(k) == reply[k] for k in ("body", "outcome"))
            record["replies"].append(dict(reply, received_at=time.time()))
            paths.write_json(filename, record)
            return True
    except (ValueError, KeyError, TypeError):
        return False
