"""One question to several recipients (ADR-0025 decision 6).

Each recipient gets an ordinary question of its own (`questions.ask`) under the
id `<group>-<n>`, so its correlated reply, late and partial answers, outcome and
acknowledgement work exactly as for a single question. The group record ties
the recipients together for the asker; `question-status <group>` reads them all.

A wait ends when every recipient has answered or ended, or at the deadline, and
returns whatever has arrived by then.
"""
from __future__ import annotations

import os
import re
import time

from . import envelope, multisend, paths, questions

DIRECTORY = "question-groups"


class GroupError(ValueError):
    pass


def _path(group_id: str) -> str:
    if not isinstance(group_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,120}", group_id):
        raise GroupError("invalid group id")
    return paths.path(DIRECTORY, group_id + ".json")


def load(group_id: str) -> dict | None:
    try:
        return paths.read_json(_path(group_id))
    except GroupError:
        return None


def is_group(request_id) -> bool:
    return isinstance(request_id, str) and load(request_id) is not None


def ask_many(sender: dict, specs: list, body: str, *, wait: float = 0, priority: str = "next",
             wake: str = "auto", pump=None, cancelled=None, poll=None) -> dict:
    specs = [s.strip() for s in specs if isinstance(s, str) and s.strip()]
    if not specs:
        raise GroupError("no recipients")
    if len(specs) > multisend.LIMIT:
        raise GroupError("at most %d recipients in one question" % multisend.LIMIT)
    if not isinstance(body, str) or not body.strip():
        raise GroupError("question body required")
    try:
        specs, notes, _ = multisend.expand_teams(specs, sender)
    except multisend.MultiError as exc:
        raise GroupError(str(exc))
    plan = multisend.plan_recipients(specs, sender)
    group_id = envelope.new_id()
    going = [e for e in plan if e["skip"] is None]
    record = {"id": group_id, "sender": questions._native(sender), "created_at": time.time(),
              "recipients": [], "notes": notes}
    for n, entry in enumerate(plan):
        if entry["skip"] is not None:
            record["recipients"].append({"spec": entry["spec"], "label": entry["label"], "id": None,
                                         "skipped": entry["skip"].reason})
            continue
        others = [e["label"] for e in going if e is not entry]
        text = multisend.also_note(others) + "\n" + body if others else body
        child = "%s-%d" % (group_id, n)
        result = questions.ask(sender, entry["spec"], text, wait=0, request_id=child,
                               priority=priority, wake=wake)
        record["recipients"].append({"spec": entry["spec"], "label": entry["label"], "id": child,
                                     "first_status": result.get("status")})
    os.makedirs(paths.path(DIRECTORY), mode=0o700, exist_ok=True)
    paths.write_json(_path(group_id), record)
    return wait_for(sender, group_id, wait=wait, pump=pump, cancelled=cancelled, poll=poll)


def status(sender: dict, group_id: str) -> dict:
    record = load(group_id)
    if not record:
        return {"status": "not-found", "id": group_id, "group": True, "recipients": [], "replies": []}
    if questions._native(sender) != record.get("sender"):
        return {"status": "refused", "id": group_id, "group": True, "recipients": [], "replies": [],
                "reason": "request belongs to another conversation"}
    rows, replies = [], []
    for saved in record["recipients"]:
        if not saved.get("id"):
            rows.append({"recipient": saved["label"], "spec": saved["spec"], "status": "skipped",
                         "reason": saved.get("skipped")})
            continue
        child = questions.status(sender, saved["id"])
        rows.append(dict(child, recipient=saved["label"], spec=saved["spec"]))
        for reply in child.get("replies") or []:
            replies.append(dict(reply, request_id=saved["id"], recipient=saved["label"]))
    asked = [r for r in rows if r["status"] != "skipped"]
    answered = [r for r in asked if r.get("replies")]
    ended = [r for r in asked if r.get("final") or r["status"] in
             ("refused", "selection-required", "held", "blocked", "error", "not-found")]
    open_ = [r for r in asked if r not in ended and not r.get("replies")]
    if not asked:
        overall = "refused"
    elif asked and all(r.get("final") for r in asked):
        overall = "final"
    elif answered:
        overall = "reply_received" if open_ else "replied"
    elif all(r in ended for r in asked):
        overall = "refused"
    else:
        overall = "pending"
    return {"status": overall, "id": group_id, "group": True, "notes": record.get("notes") or [],
            "answered": len(answered), "asked": len(asked), "skipped": len(rows) - len(asked),
            "waiting_on": [r["recipient"] for r in open_],
            "recipients": rows, "replies": replies,
            "recover_at": {"cli": ["xsm", "question-status", group_id],
                           "mcp": {"tool": "xsm_question_status", "arguments": {"id": group_id}}}}


def wait_for(sender: dict, group_id: str, wait: float = 0, pump=None, cancelled=None,
             poll=None) -> dict:
    """Until every recipient has answered or ended, the deadline, or a cancel.
    `poll(child_id)` reads one recipient's reply copies (receive.poll_replies)."""
    deadline = time.monotonic() + questions._duration(wait)
    last_poll = float("-inf")
    while True:
        if poll is not None and time.monotonic() - last_poll >= 0.2:
            last_poll = time.monotonic()
            for child in child_ids(group_id):
                poll(child)
        result = status(sender, group_id)
        if not result["waiting_on"] or result["status"] in ("not-found", "refused"):
            result["wait_end_reason"] = "all-answered-or-ended"
            return result
        if cancelled is not None and cancelled():
            result["wait_end_reason"] = "cancelled"
            return result
        if time.monotonic() >= deadline:
            result["wait_end_reason"] = "timeout"
            return result
        if pump is not None:
            pump()
        time.sleep(min(0.05, max(0, deadline - time.monotonic())))


def child_ids(group_id: str) -> list:
    record = load(group_id) or {}
    return [r["id"] for r in record.get("recipients", []) if r.get("id")]


def with_claims(me: dict, result: dict) -> dict:
    """Claim tokens for exactly the answers being returned, recipient by
    recipient: the same handoff as one question's (receive.claim_question_replies)."""
    from . import receive
    claims = []
    for row in result.get("recipients") or []:
        if row.get("replies"):
            row["claims"] = receive.claim_question_replies(me, row).get("claims", [])
            claims.extend(row["claims"])
    return dict(result, claims=claims)
