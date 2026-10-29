"""Who sent what, and whether it actually arrived.

The send call cannot answer the second question. agent-comms reports "Sent"
for a message its recipient never sees, and nothing in the sender's own
result distinguishes the two (S9 E6-3). So the sender writes `queued`, the
receiving hook writes a receipt, and only a receipt turns a message into
`delivered`.

P01 splits the one word "sent" into the steps it is made of, because they are
not the same fact: the queue command ran, the wake was attempted, the receiver's
hook took it, a paired machine stored it. A successful socket write is not a
receiver; a queue write is not a turn. Each step is recorded on its own axis
under `evidence`, and `runtime_reached` is only true once the receiver's own
side says so (A18-01).

Each entry also carries the *digest* of the request -- the canonical form's
SHA-256 -- so a resend is judged on the whole message and not on the first 200
characters (A18-03). The `preview` stays, for display only.
"""
from __future__ import annotations

import os
import time
import fcntl

from . import envelope, paths


def _certainty_of(basis: str) -> str:
    """The certainty a basis carries, without importing context (context imports
    nothing from ledger, but keeping the mapping here avoids a cycle through
    envelope -> context -> ledger)."""
    from . import context
    return context.certainty_of(basis)


def _entry_path(msg_id: str) -> str:
    return paths.path(paths.LEDGER, "%s.json" % msg_id)


def _receipt_path(msg_id: str) -> str:
    return paths.path(paths.LEDGER, "%s.recv.json" % msg_id)


def queued(msg_id: str, sender: dict, target: dict, scope: str, kind: str, body: str,
           forecast: str | None = None, *, reply_to: str | None = None,
           outcome: str | None = None, priority: str | None = None, attachments=None,
           identity: dict | None = None, basis: str | None = None,
           certainty: str | None = None) -> dict:
    """`forecast` is what Claude's own gate was expected to do (send.native_forecast);
    "hold" is kept so a message that never arrives reads as waiting for a person.

    Everything whose change makes this a different message goes into the digest:
    the whole body, kind, reply_to, outcome, both handles, the scope and the
    attachment manifest. `preview` is written too, but only so a listing has
    something to show -- the resend check reads `digest`, never the preview
    (P01 items 3 and 5).
    """
    before = paths.read_json(_entry_path(msg_id), {}) or {}
    ident = identity or envelope.request_identity(
        msg_id, sender, target, body, kind=kind, reply_to=reply_to, outcome=outcome,
        scope=scope, priority=priority, attachments=attachments)
    entry = {"id": msg_id, "status": "queued", "t": time.time(), "kind": kind, "scope": scope,
             "from": {k: sender.get(k) for k in ("name", "alias", "ref", "runtime")},
             "to": {k: target.get(k) for k in ("name", "alias", "ref", "runtime")},
             "preview": envelope.preview(body)}
    # Additive fields (P01 item 5): a version stamp, the canonical digest, and
    # the reply/outcome contract. An old reader ignores them; a new reader of an
    # old record sees no `digest` and reads it as legacy/unverified.
    entry["req_version"] = envelope.CANON_VERSION
    entry["digest"] = envelope.request_digest(ident)
    if basis:
        # How the sender was identified for this send (P01 item 2). Kept beside
        # the message so a weak identity is visible after the fact, not only in
        # the result the caller happened to read.
        entry["from_basis"] = basis
        entry["from_certainty"] = certainty or _certainty_of(basis)
    if reply_to:
        entry["reply_to"] = reply_to
    if outcome:
        entry["outcome_req"] = outcome
    if priority and priority != "next":
        entry["priority"] = priority
    if attachments:
        entry["attachments"] = ident.get("attachments")
    if forecast == "hold":
        entry["forecast"] = forecast
    if before:
        # A resend under the same id (xsm send --resend, 2026-09-29): `t` stays
        # the first send's so the row keeps its place; the stale error and
        # settle_after go, because they described the attempt being replaced.
        entry["t"] = before.get("t", entry["t"])
        entry["resent_t"] = time.time()
        entry["resends"] = int(before.get("resends") or 0) + 1
        # The evidence axes describe the id, not the attempt, and `step()` merges
        # rather than overwrites for exactly that reason. Rebuilding the entry
        # here would drop them -- and with them the record that the receiver's
        # own hook once took this message (A18-01).
        if before.get("evidence"):
            entry["evidence"] = before["evidence"]
            entry["runtime_reached"] = before.get("runtime_reached") is True
        if before.get("upgraded_from_legacy") or not before.get("digest"):
            # This row predates the digest. The one written now describes what
            # the caller sent *this* time; the original body was never kept, so
            # nothing can vouch that they are the same (P01 item 5). Say so
            # rather than letting the new digest read as a verification of the
            # old row. A later resend keeps the mark, so a digest written by the
            # first resend does not turn the row verified.
            entry["upgraded_from_legacy"] = True
    paths.write_json(_entry_path(msg_id), entry)
    return entry


def failed(msg_id: str, reason: str, status: str = "error") -> None:
    """The send never left: no receipt will come, so the entry itself says so.
    (Measured 2026-09-22: five sends blocked by a sandbox sat as `queued`.)
    `status` is "refused" when a remote peer answered that it would not take it."""
    entry = paths.read_json(_entry_path(msg_id), {}) or {}
    entry.update({"status": status, "error": reason, "failed_t": time.time()})
    paths.write_json(_entry_path(msg_id), entry)


# -- delivery evidence: one axis per step, never collapsed (A18-01) -----------
#
# The old result had one word for the whole trip: `queued`, `delivered`, `error`.
# "queued" was written whether the socket write landed or the queue command ran,
# and the sender read the same word either way. A send is now made of named
# steps, each recorded when it actually happened:
#
#   accepted     the send passed every local check and an id was assigned
#   queued       the runtime's own queue/socket step was attempted
#   wake         the Codex daemon was asked to start the queued item
#   remote_sent  a paired machine's xsm was handed the request
#   remote_stored a paired machine's xsm put the frame into its own channel
#   hook_taken   the receiver's own hook took it (it wrote a receipt)
#
# `runtime_reached` is True only when the receiver's own side said so: its
# receipt on this machine (`hook_taken`). A queue success, a socket write, the
# sender's own acceptance, or a paired machine's `remote_stored` is never that
# (A18-01): `remote_stored` says the far xsm accepted the frame, which is
# exactly as much as a local socket write says, and no more (G01 review).
STEPS = ("accepted", "file-storage", "queued", "wake", "remote_sent", "remote_stored", "hook_taken")


def step(msg_id: str, name: str, ok: bool = True, detail: str | None = None) -> dict:
    """Record one delivery step for this message. Merged, not overwritten, so
    the axes are kept apart even though they live in one file."""
    if name not in STEPS:
        raise ValueError("unknown evidence step: %s" % name)
    entry = paths.read_json(_entry_path(msg_id), {}) or {}
    ev = dict(entry.get("evidence") or {})
    record = {"ok": bool(ok), "t": time.time()}
    if detail:
        record["detail"] = detail
    # The first time a step happened and the latest: a later failure must not
    # erase the fact that the queue did accept it once.
    if name in ev:
        record["early"] = ev[name]
    ev[name] = record
    entry["evidence"] = ev
    entry["runtime_reached"] = ev.get("hook_taken", {}).get("ok") is True
    paths.write_json(_entry_path(msg_id), entry)
    return entry


def handoff_step(msg_id, name, receiver):
    """Persist lifecycle evidence separately from legacy queue/receipt rewrites.

    name=None reserves the full endpoint without claiming a stored event.
    Canonical handoff state remains authoritative across crashes between its
    commit and this annotation. A transport receipt is never an ack.
    """
    from . import handoff
    handoff._id(msg_id)
    if name not in (None, "stored", "claimed", "handoff", "ack"):
        raise ValueError("unknown handoff evidence step")
    filename = paths.path(paths.LEDGER, msg_id + ".handoff.json")
    os.makedirs(os.path.dirname(filename), mode=0o700, exist_ok=True)
    fd = os.open(filename + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        record = paths.read_json(filename, {}) or {}
        endpoint = handoff._identity(receiver)
        if record.get("receiver") and record["receiver"] != endpoint:
            raise ValueError("handoff evidence belongs to another endpoint")
        record.update(id=msg_id, receiver=endpoint)
        if name is not None:
            record.setdefault("steps", {})[name] = {"ok": True, "t": time.time()}
        paths.write_json(filename, record)
    finally:
        os.close(fd)


def evidence_of(msg_id: str) -> dict:
    result = _transport_evidence_of(msg_id)
    record = paths.read_json(paths.path(paths.LEDGER, msg_id + ".handoff.json"))
    result["acknowledged"] = False
    if not isinstance(record, dict) or not record.get("receiver"):
        return result
    from . import handoff
    try:
        current = handoff.status(record["receiver"], msg_id)
    except (OSError, ValueError):
        return result
    if current["status"] == "not-found":
        return result
    steps = dict(record.get("steps") or {})
    steps["stored"] = {"ok": True, "t": current["stored_at"]}
    claim = current.get("claim") or current.get("previous_claim")
    if claim:
        steps["claimed"] = {"ok": True, "t": claim["started_at"]}
    if "handoff-recorded_at" in current:
        steps["handoff"] = {"ok": True, "t": current["handoff-recorded_at"]}
    # Only committed canonical ack counts, even if an annotation was stale.
    steps.pop("ack", None)
    result["acknowledged"] = current["status"] == "acknowledged"
    if result["acknowledged"]:
        steps["ack"] = {"ok": True, "t": current["acknowledged_at"]}
    result["steps"].update(steps)
    result["handoff_status"] = current["status"]
    return result


def _transport_evidence_of(msg_id: str) -> dict:
    """The evidence for a message, with a `legacy` flag when it was written by a
    version that had none. A caller must not read a legacy entry as a runtime
    success: it can only say the message was queued once (P01 item 5)."""
    entry = paths.read_json(_entry_path(msg_id), {}) or {}
    rec = receipt_of(msg_id) or {}
    if not entry and not rec:
        return {"steps": {}, "runtime_reached": False, "digest": None,
                "req_version": None, "legacy": True, "verified": False,
                "upgraded_from_legacy": False}
    ev = entry.get("evidence")
    if isinstance(ev, dict):
        steps = dict(ev)
        # The receiver's receipt is the runtime reaching it; it is written on the
        # receiver's side and read here, not assumed from the sender's queue.
        if rec.get("decision") and not steps.get("hook_taken"):
            steps["hook_taken"] = {"ok": rec.get("decision") == "delivered", "t": rec.get("t"),
                                   "detail": rec.get("decision")}
        reached = steps.get("hook_taken", {}).get("ok") is True
        return {"steps": steps, "runtime_reached": reached,
                "digest": entry.get("digest"), "req_version": entry.get("req_version"),
                "legacy": False,
                # A digest written by the resend of a row that had none describes
                # what was sent *this* time; the original body was never kept, so
                # nothing can vouch that the two are the same (P01 item 5). The
                # row keeps its evidence and stays unverified (G01 review).
                "verified": bool(entry.get("digest")) and not entry.get("upgraded_from_legacy"),
                "upgraded_from_legacy": bool(entry.get("upgraded_from_legacy"))}
    # No `evidence` key at all: written before P01. Anything it says about
    # arrival is unverified, and no full digest can be recovered from a preview.
    taken = entry.get("status") == "delivered" or rec.get("decision") == "delivered"
    return {"steps": {"accepted": {"ok": True, "legacy": True},
                       "queued": {"ok": entry.get("status") != "error", "legacy": True},
                       "hook_taken": {"ok": bool(taken), "legacy": True}},
            "runtime_reached": bool(taken),
            "digest": None, "req_version": None, "legacy": True, "verified": False,
            "upgraded_from_legacy": False}


def unknown(msg_id: str, reason: str, settle_after: float | None = None) -> None:
    """A remote send whose answer was lost: it may have arrived. Neither
    `queued` (on its way) nor `error` (never left) is true, and a sender that
    reads `error` sends again under a new id (issue #4, 2026-09-29)."""
    entry = paths.read_json(_entry_path(msg_id), {}) or {}
    entry.update({"status": "unknown", "error": reason, "unknown_t": time.time()})
    if settle_after:
        # Before this, "no record over there" may only mean "not yet" (remote.reconcile).
        entry["settle_after"] = settle_after
    paths.write_json(_entry_path(msg_id), entry)


def reached(msg_id: str) -> None:
    """The peer says an `unknown` message is queued there: it is on its way."""
    entry = paths.read_json(_entry_path(msg_id), {}) or {}
    if entry.get("status") == "unknown":
        entry["status"] = "queued"
        entry.pop("error", None)
        paths.write_json(_entry_path(msg_id), entry)


def receipt(msg_id: str, decision: str, receiver: dict | None, reason: str = "",
            outcome: str | None = None, from_ref: str | None = None,
            body_sha: str | None = None, req_digest: str | None = None,
            req_version: int | None = None) -> None:
    """Written by the receiving hook. `decision` is delivered | held | blocked.
    `from_ref` and `body_sha` say whose message and which text was delivered, so a
    second run of the hook is only passed for the very same one (receive._repeat).
    `req_digest` is the fuller canonical fingerprint -- id, kind, reply_to,
    outcome, scope and both identities, not only the body -- so a header that
    reuses a delivered id with any of those changed is not a repeat (A18-03).
    An older hook wrote no `req_digest`: that receipt is read as legacy, and the
    weaker `body_sha` stands alone rather than a digest being rebuilt."""
    rec = {"id": msg_id, "decision": decision, "reason": reason, "t": time.time(),
           "receiver": {k: (receiver or {}).get(k) for k in ("name", "alias", "ref", "runtime")}}
    if outcome:
        rec["outcome"] = outcome
    if body_sha:
        rec.update({"from_ref": from_ref, "body_sha": body_sha})
    if req_digest:
        rec.update({"req_digest": req_digest, "req_version": req_version or envelope.CANON_VERSION})
    paths.write_json(_receipt_path(msg_id), rec)


def close(task_id: str, outcome: str, by: dict | None = None) -> None:
    """How the task sent as `task_id` ended, written on the task's own entry.

    The reply that carries the outcome is a message of its own and its receipt
    goes with it; a `--once` worker is stopped and forgotten moments later, so
    the entry the sender already holds the id of is the only lasting place for
    this. Left on a separate key because `status()` overwrites `status` with
    the receipt's decision."""
    entry = paths.read_json(_entry_path(task_id), {}) or {}
    if not entry:
        return                      # nothing sent under that id here; nothing to close
    entry["outcome"] = outcome
    entry["closed_t"] = time.time()
    if by:
        entry["closed_by"] = {k: by.get(k) for k in ("name", "alias", "ref", "runtime")}
    paths.write_json(_entry_path(task_id), entry)


def received(msg_id: str) -> bool:
    """Whether some path already handed this message over (or refused it)."""
    return os.path.exists(_receipt_path(msg_id))


def receipt_of(msg_id: str) -> dict | None:
    """The receiver's own record of what it did with this message, if any."""
    rec = paths.read_json(_receipt_path(msg_id))
    return rec if isinstance(rec, dict) else None


def sent_by(msg_id: str | None, ref: str | None) -> bool:
    """Whether this machine's own `xsm send` queued this id from this session.
    Only the sending side writes the entry, after it checked scope, so it proves
    where a header came from when the sender itself has since exited."""
    if not (msg_id and ref):
        return False
    entry = paths.read_json(_entry_path(msg_id))
    return isinstance(entry, dict) and (entry.get("from") or {}).get("ref") == ref


def status(msg_id: str) -> dict:
    entry = paths.read_json(_entry_path(msg_id), {}) or {}
    rec = paths.read_json(_receipt_path(msg_id))
    if rec:
        entry["status"] = rec.get("decision")
        entry["receipt"] = rec
        if rec.get("outcome") and not entry.get("outcome"):
            # A reply's own outcome belongs on the reply; a task's comes from
            # close(). Neither overwrites the other.
            entry["outcome"] = rec["outcome"]
    if entry:
        # The delivery evidence beside the legacy `status`: `delivered` says a
        # receipt exists, `delivery` says which of the trips actually happened.
        # A legacy row (written before P01) reads as `legacy` and unverified.
        #
        # `delivery` is the wrapper `evidence_of` returns; `evidence` stays the
        # file's own step map (`{step: {ok, t}}`), so the two shapes of one name
        # do not collide for a reader that opens the entry file directly
        # (G01 review). `runtime_reached` is repeated at the top for callers
        # that already read it there.
        entry["delivery"] = evidence_of(msg_id)
        entry["runtime_reached"] = entry["delivery"]["runtime_reached"]
    return entry


def wait_for(msg_id: str, seconds: float, interval: float = 0.4) -> dict:
    deadline = time.time() + seconds
    while True:
        state = status(msg_id)
        if state.get("status") != "queued":
            return state
        if time.time() >= deadline:
            return state
        time.sleep(interval)


def recent(limit: int = 20) -> list:
    entries = []
    try:
        names = os.listdir(paths.path(paths.LEDGER))
    except OSError:
        return []
    for name in names:
        if name.endswith((".recv.json", ".handoff.json")) or not name.endswith(".json"):
            continue
        entries.append(status(name[:-len(".json")]))
    return sorted(entries, key=lambda e: e.get("t", 0), reverse=True)[:limit]
