"""Durable human decision lifecycle; peer claims are never human answers.

Transport adapters supply observed display/response data. A display request is
not proof that the person saw it. Application is tied to the original scope and
generation. Uncertain side effects remain unknown until a caller reads them back.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import time

from . import paths

DIRECTORY = "human-decisions"
TERMINAL = ("denied", "cancelled", "expired", "superseded", "applied")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def owner(me):
    return {"runtime": me.get("runtime"),
            "home": os.path.realpath(me["home"]) if me.get("home") else None,
            "conversation": me.get("session_id") or me.get("conversation") or me.get("ref")}


def invocation(me, tool, arguments, generation, resource=None):
    args = {k: v for k, v in arguments.items()
            if k not in ("answer_request", "original_question", "notify")}
    value = {"owner": owner(me), "tool": tool, "scope": args,
             "generation": generation, "cwd": os.path.realpath(me["cwd"]) if me.get("cwd") else None}
    if resource is not None:
        value["resource"] = resource
    return digest(value)


def filename(key):
    if not isinstance(key, str) or len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
        raise ValueError("invalid decision id")
    return paths.path(DIRECTORY, key + ".json")


@contextmanager
def locked(key):
    name = filename(key)
    os.makedirs(os.path.dirname(name), mode=0o700, exist_ok=True)
    fd = os.open(name + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield name
    finally:
        os.close(fd)


def read(key):
    return paths.read_json(filename(key))


def begin(key, me, scope, generation, question, ttl=1800, waiter=None, now=None, choices=None):
    now = time.time() if now is None else now
    with locked(key) as path:
        record = paths.read_json(path)
        if record:
            if (record["owner"] != owner(me) or record["scope_digest"] != digest(scope)
                    or record["generation"] != generation or record["question"] != question):
                raise ValueError("decision identity, scope or question changed")
            if record['status'] in ('pending','answered') and now>record['expires_at']:
                record['status']='expired'
        else:
            record = {"id": key, "owner": owner(me), "scope": scope,
                      "scope_digest": digest(scope), "generation": generation,
                      "question": question, "question_digest": digest(question),
                      "created_at": now, "expires_at": now + ttl,
                      "status": "pending", "display": {"status": "not-requested"},
                      "waiters": {}, "answer": None, "application": None,
                      "choices": choices,
                      "native_question": "[xsm-decision:%s] %s" % (key[:16], question)}
        if waiter is not None:
            record["waiters"][str(waiter)] = "waiting"
        paths.write_json(path, record)
        return record


def display(key, waiter, shown_text, channel, complete=True, reader=None):
    with locked(key) as path:
        record = paths.read_json(path)
        if record["status"] in TERMINAL or record["display"]["status"] != "not-requested":
            return False
        record["display"] = {"status": "requested", "owner": str(waiter),
                             "text": shown_text, "digest": digest(shown_text),
                             "complete": bool(complete), "channel": channel,
                             "requested_at": time.time(), "human_saw": None}
        if reader:
            record["display"]["reader"] = reader
        paths.write_json(path, record)
        return True


def abandon_display(key, instance):
    """Client EOF loses the display owner, never the original question/answer."""
    with locked(key) as path:
        record = paths.read_json(path)
        shown = record["display"]
        if (record["status"] == "pending" and not record.get("answer") and
                (shown.get("reader") or {}).get("instance") == instance):
            record.setdefault("display_history", []).append(dict(shown, ended="client-disconnected"))
            record["display"] = {"status": "not-requested"}
            paths.write_json(path, record)
        return record


def recover_display(key):
    """Only proven dead/replaced readers permit automatic pending-form recovery."""
    from . import context, identity
    record = read(key)
    reader = (record.get("display") or {}).get("reader") if record else None
    if reader and record["status"] == "pending" and not record.get("answer"):
        pid = reader.get("pid")
        start = identity.lstart(pid) if pid and identity.pid_alive(pid) else None
        if not pid or not identity.pid_alive(pid) or (start and context.generation(pid, start) != reader.get("generation")):
            return abandon_display(key, reader["instance"])
    return record


def response(key, reply, source, source_id=None, displayed=None, now=None):
    """Only internal transport adapters call this; never expose it as a grant RPC."""
    now = time.time() if now is None else now
    with locked(key) as path:
        record = paths.read_json(path)
        if record["status"] in ("applied", "cancelled", "superseded"):
            return record
        result = reply.get("result") if isinstance(reply, dict) else None
        action = result.get("action") if isinstance(result, dict) else None
        content = result.get("content") if isinstance(result, dict) else None
        answer = content.get("answer") if isinstance(content, dict) else None
        reviewer = (result.get("_meta") or {}).get("approvals_reviewer") if isinstance(result, dict) and isinstance(result.get("_meta") or {}, dict) else "unknown"
        if source not in ("mcp-elicitation", "native-user", "human-terminal") or reviewer not in (None, "user"):
            state = "unknown"
        elif now < record["created_at"]:
            state = "unknown"  # clock rollback is not an extended approval
        elif now > record["expires_at"]:
            state = "expired"
        elif action == "decline":
            # Codex may decline without showing the form; source cannot prove no.
            state = "unshown-or-declined"
        elif action == "cancel":
            state = "dismissed"
        elif action == "accept" and isinstance(answer, str) and answer.strip():
            choices = record.get("choices")
            if choices and answer.strip() not in choices:
                state = "unknown"
            else:
                negative = answer.strip() in ("deny", "not now", "no")
                state = "denied" if negative and record["scope"].get("tool") != "xsm_decide" else "answered"
        else:
            state = "unknown"
        record.update(status=state, answer={"reply": reply, "source": source,
                      "source_id": source_id, "recorded_at": now})
        if displayed is not None:
            record["display"]["reported_text"] = displayed
            record["display"]["reported_digest"] = digest(displayed)
            expected = record.get("native_question", record["question"]) if source == "native-user" else record["question"]
            record["display"]["complete"] = (record["display"].get("complete", False)
                and displayed == expected
                and (source == "native-user" or displayed == record["display"].get("text")))
        paths.write_json(path, record)
        return record


def cancel_waiter(key, waiter):
    with locked(key) as path:
        record = paths.read_json(path)
        record["waiters"][str(waiter)] = "cancelled"
        paths.write_json(path, record)
        return record


def revoke(key):
    with locked(key) as path:
        record = paths.read_json(path)
        record["status"] = "cancelled"
        record["revoked_at"] = time.time()
        paths.write_json(path, record)
        return record


def claim_native(me, source_id, key):
    from . import consent
    record = read(key)
    question = record.get("native_question", record["question"])
    marker = consent.claim_answer(me, source_id, consent.digest(question), "decision:" + key)
    if not marker:
        raise ValueError("this native user answer already belongs to another operation")
    with locked(key) as path:
        record = paths.read_json(path);record["native_marker"] = marker
        paths.write_json(path, record)


def start_application(key, generation, scope, receipt=None, reader=None):
    """Persist acceptance before effects. A lost completion requires readback, not replay."""
    now = time.time()
    with locked(key) as path:
        record = paths.read_json(path)
        if record["generation"] != generation or record["scope_digest"] != digest(scope):
            raise ValueError("decision caller or scope changed")
        if (record["status"] in TERMINAL or (record.get("application") or {}).get("phase") == "started"
                or now < record["created_at"] or now > record["expires_at"]):
            raise ValueError("decision closed or outcome unknown; inspect status and domain state before retrying")
        if not receipt and (record["status"] != "answered" or not record["display"].get("complete")):
            raise ValueError("no complete user answer to apply")
        if receipt:
            record["permission_receipt"] = receipt
        record.update(status="unknown", application={"phase": "started", "started_at": now,
                      "reader": reader, "source": (receipt or {}).get("source") or
                      (record.get("answer") or {}).get("source")})
        paths.write_json(path, record)
        return record


def applied(key, result, generation, scope, now=None):
    """Commit an observed domain result. This never substitutes for executing it."""
    now = time.time() if now is None else now
    with locked(key) as path:
        record = paths.read_json(path)
        if record["status"] == "applied":
            return record
        if (record["generation"] != generation or record["scope_digest"] != digest(scope)):
            record["status"] = "superseded"
        elif (record.get("application") or {}).get("phase") == "started":
            if not record.get("permission_receipt") and not record["display"].get("complete"):
                raise ValueError("no complete user answer to commit")
            application = dict(record["application"], phase="completed", result=result, observed_at=now)
            if now < application["started_at"]:
                application["clock_rollback_after_start"] = True
            record.update(status="applied", application=application)
        elif now<record['created_at']:
            record['status']='unknown'
        elif now > record["expires_at"]:
            record["status"] = "expired"
        elif record["status"] != "answered" or not record["display"].get("complete"):
            raise ValueError("no complete, current human decision to apply")
        else:
            record.update(status="applied", application={"result": result, "observed_at": now})
        paths.write_json(path, record)
        if record["status"] == "applied" and record.get("native_marker"):
            from . import consent
            marker = record["native_marker"]
            with consent._locked(marker):
                used = paths.read_json(marker, {})
                used["consumed"] = True
                paths.write_json(marker, used)
        return record


def deny(key):
    with locked(key) as path:
        record = paths.read_json(path)
        if record["status"] in ("answered", "unshown-or-declined"):
            record["status"] = "denied"
            paths.write_json(path, record)
        return record


def supersede(key):
    with locked(key) as path:
        record = paths.read_json(path)
        record["status"] = "superseded"
        paths.write_json(path, record)
        return record


def _visible_status(record):
    if record['status'] in ('pending','answered'):
        now=time.time()
        if now<record['created_at']:return 'unknown'
        if now>record['expires_at']:return 'expired'
    return record['status']


def public_status(me, key=None, cancel=False):
    if key is None:
        if cancel:
            raise ValueError("decision id required for cancellation")
        try:
            names = os.listdir(paths.path(DIRECTORY))
        except OSError:
            names = []
        result = []
        for name in names:
            if not name.endswith(".json"):
                continue
            try:
                record = read(name[:-5])
                if record and record["owner"] == owner(me):
                    result.append({"id": record["id"], "status": _visible_status(record),
                                   "question": record["question"], "created_at": record["created_at"]})
            except (ValueError, KeyError, TypeError):
                continue
        return {"status": "decisions", "decisions": result}
    record = read(key)
    if not record or record["owner"] != owner(me):
        return {"id": key, "status": "not-found"}
    if cancel:
        if (record.get("application") or {}).get("phase") == "started":
            return {"id": key, "status": "application-started", "reason": "withdrawal cannot stop an operation already started; inspect domain state before retrying or revoking"}
        if record["status"] == "applied":
            return {"id": key, "status": "already-applied",
                    "reason": "cancel cannot undo an applied effect; use its domain revocation"}
        record = revoke(key)
        from . import consent
        consent.cancel_bound_requests(me, key)
    result = {k: record[k] for k in ("id", "status", "question", "question_digest", "display",
                                   "answer", "application", "expires_at", "choices")}
    result["scope"] = record["scope"]
    result["native_question"] = record.get("native_question", record["question"])
    if record.get("permission_receipt"):
        result["permission_receipt"] = record["permission_receipt"]
    result['status']=_visible_status(record)
    result["attention"] = paths.read_json(paths.path("attention", key + ".json"))
    return result
