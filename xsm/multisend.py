"""One DM to several recipients (ADR-0025 decisions 2-8).

A message is a DM: the sender names who gets it, and there may be more than one.
Each recipient gets its own delivery under its own message id, so the receipts,
the acknowledgements and a resend stay per recipient; the group id ties them
together for the sender.

- A recipient outside this session's scope is skipped, not offered a connect:
  the others still get the message and the result says who was left out (D14).
- Every recipient is told who else got it. The note leads the body, so it
  reaches a local session, an SSH peer and a P2P peer alike, and an older xsm
  reads it as ordinary text (D15).
- The worst recipient result decides the exit code (D17).
- Traffic is observed per sender and recipient pair, so a group send already
  counts once per pair: nothing here adds to it.
"""
from __future__ import annotations

import os
import time

from . import config, envelope, ledger, paths, probe, registry, resolve, send

GROUPS = "groups"
LIMIT = 16                      # recipients in one send (implementation default, T1)
# Exit-code order of the CLI: the larger is the worse (D17).
SEVERITY = {"delivered": 0, "stored": 0, "refused": 2, "held": 2, "blocked": 2,
            "sent-unconfirmed": 3, "unknown": 3, "error": 4}


class MultiError(ValueError):
    pass


class MultiResult:
    def __init__(self, group_id: str, rows: list):
        self.group_id = group_id
        self.rows = rows              # [{"spec", "label", "result": SendResult}]

    @property
    def worst(self) -> str:
        return max((r["result"].status for r in self.rows),
                   key=lambda s: SEVERITY.get(s, 4), default="refused")

    def lines(self) -> list:
        sent = sum(1 for r in self.rows if r["result"].status in send.LEFT)
        out = ["group %s: %d of %d recipients sent" % (self.group_id, sent, len(self.rows))]
        for row in self.rows:
            res = row["result"]
            line = "  %s: %s: %s" % (row["label"], res.status, res.reason or "")
            if res.msg_id and res.status != "refused":
                line += " (id %s)" % res.msg_id
            out.append(line)
        return out

    def as_dict(self) -> dict:
        return {"group": self.group_id, "status": self.worst,
                "recipients": [dict(spec=r["spec"], label=r["label"], **r["result"].as_dict())
                               for r in self.rows]}


def _label(target: dict | None, spec: str) -> str:
    if target and target.get("name"):
        return "%s@%s [%s]" % (target.get("name"), target.get("alias"), target.get("ref"))
    return spec


def _local(spec: str) -> bool:
    """Specs this machine resolves itself; the rest (an SSH peer, a P2P target)
    are decided by send() on the way out."""
    spec = spec.strip()
    return not (spec.startswith(("net:", "candidate:")) or spec.count("@") >= 2)


def also_note(others: list) -> str:
    return "(also sent to: %s)" % ", ".join(others)


def _group_path(group_id: str) -> str:
    return paths.path(GROUPS, group_id + ".json")


def _save(record: dict) -> None:
    os.makedirs(paths.path(GROUPS), mode=0o700, exist_ok=True)
    paths.write_json(_group_path(record["id"]), record)


def load_group(group_id: str) -> dict | None:
    group_id = (group_id or "").strip()
    if not group_id or "/" in group_id or group_id.startswith("."):
        return None
    try:
        return paths.read_json(_group_path(group_id))
    except (OSError, ValueError):
        return None


def plan_recipients(specs: list, sender: dict) -> list:
    """Resolve every recipient first, so each one can be told who else gets it.
    Returns [{"spec", "label", "target", "skip"}]; skip is a refusal SendResult
    for one that is not sent (unknown, yourself, out of scope)."""
    plan, seen = [], set()
    for spec in specs:
        entry = {"spec": spec, "target": None, "skip": None}
        if _local(spec):
            with probe.quick():
                found = resolve.resolve(spec)
            if not found.ok:
                entry["skip"] = send.SendResult("refused", found.reason, candidates=found.candidates)
            else:
                target = found.record or {}
                entry["target"] = target
                key = (target.get("runtime"), target.get("session_id"), target.get("home"))
                if key in seen:
                    continue                      # the same session named twice
                seen.add(key)
                if target.get("ref") and target.get("ref") == sender.get("ref"):
                    entry["skip"] = send.SendResult("refused", "refusing to send to yourself", target=target)
                elif not target.get("remote"):
                    scope, reason = config.scope_for(sender, target)
                    if not scope:
                        entry["skip"] = send.SendResult(
                            "refused", "out of scope, so not sent (the other recipients were): %s"
                            % reason, target=target)
        elif spec in seen:
            continue
        else:
            seen.add(spec)
        entry["label"] = _label(entry["target"], spec)
        plan.append(entry)

    return plan


def send_many(specs: list, body: str, *, sender: dict | None = None, call=None, kind: str = "note",
              reply_to: str | None = None, priority: str = "next", wait: float = 0.0,
              outcome: str | None = None, wake: bool = True) -> MultiResult:
    specs = [s.strip() for s in specs if s and s.strip()]
    if not specs:
        raise MultiError("no recipients")
    if len(specs) > LIMIT:
        raise MultiError("at most %d recipients in one send" % LIMIT)
    if sender is None:
        registry.forget_identity()
        with probe.quick():
            sender = registry.me()
            call = call or registry.last_identity()
    if not sender:
        raise MultiError("this session is not registered; run `xsm doctor`")

    plan = plan_recipients(specs, sender)
    group_id = envelope.new_id()
    going = [e for e in plan if e["skip"] is None]
    record = {"id": group_id, "t": time.time(), "sender": sender.get("ref"), "kind": kind,
              "reply_to": reply_to, "outcome": outcome, "priority": priority, "recipients": []}
    rows = []
    for entry in plan:
        if entry["skip"] is not None:
            rows.append({"spec": entry["spec"], "label": entry["label"], "result": entry["skip"]})
            record["recipients"].append({"spec": entry["spec"], "label": entry["label"],
                                         "id": None, "status": "refused"})
            continue
        others = [e["label"] for e in going if e is not entry]
        text = also_note(others) + "\n" + body if others else body
        result = send.send(entry["spec"], text, sender=sender, call=call, kind=kind,
                           reply_to=reply_to, priority=priority, wait=0.0, outcome=outcome,
                           wake=wake)
        rows.append({"spec": entry["spec"], "label": entry["label"], "result": result})
        record["recipients"].append({"spec": entry["spec"], "label": entry["label"],
                                     "id": result.msg_id, "status": result.status, "body": text})
    _wait_together(rows, wait)
    for row, saved in zip(rows, record["recipients"]):
        saved["status"] = row["result"].status
    _save(record)
    return MultiResult(group_id, rows)


def _wait_together(rows: list, wait: float) -> None:
    """One wait for the whole group, not one per recipient: poll each local
    receipt until it lands or the shared deadline passes."""
    if wait <= 0:
        return
    deadline = time.time() + wait
    pending = [r for r in rows if r["result"].status == "sent-unconfirmed" and r["result"].msg_id]
    while pending and time.time() < deadline:
        still = []
        for row in pending:
            state = ledger.status(row["result"].msg_id)
            status = state.get("status")
            if status == "delivered":
                row["result"].status, row["result"].reason = "delivered", "receiver recorded it"
            elif status in ("held", "blocked"):
                row["result"].status = status
                row["result"].reason = (state.get("receipt") or {}).get("reason", "")
            else:
                still.append(row)
        pending = still
        if pending:
            time.sleep(0.4)


def resend_group(group_id: str, *, sender: dict | None = None, call=None, wait: float = 0.0) -> MultiResult:
    """Send again, under their own ids, only the recipients whose delivery is
    still open (queued, unknown or error). Recipients that were skipped or got
    it are left alone."""
    record = load_group(group_id)
    if not record:
        raise MultiError("no group %s was sent from this machine" % group_id)
    if sender is None:
        registry.forget_identity()
        with probe.quick():
            sender = registry.me()
            call = call or registry.last_identity()
    if not sender or sender.get("ref") != record.get("sender"):
        raise MultiError("group %s was sent by another session" % group_id)
    rows = []
    for saved in record["recipients"]:
        current = ledger.status(saved["id"]).get("status") if saved.get("id") else None
        if not saved.get("id") or current not in send.RESENDABLE:
            result = send.SendResult(current or saved["status"], "not resent", saved.get("id"))
        else:
            result = send.send(saved["spec"], saved["body"], sender=sender, call=call,
                               kind=record.get("kind") or "note", reply_to=record.get("reply_to"),
                               outcome=record.get("outcome"), priority=record.get("priority") or "next",
                               msg_id=saved["id"], resend=True)
        rows.append({"spec": saved["spec"], "label": saved["label"], "result": result})
    _wait_together(rows, wait)
    for row, saved in zip(rows, record["recipients"]):
        saved["status"] = row["result"].status
    _save(record)
    return MultiResult(group_id, rows)
