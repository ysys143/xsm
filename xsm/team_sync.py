"""Teams across machines (ADR-0025 decision 14, D22).

A team with members on other machines is kept on each of those machines as the
same record. The machine that changes a team sends the whole record, as P2P
endpoints, to every other member machine over the network service; a machine
takes it when the sender is an active member machine of the network and the team
id matches (or is new here). Its own endpoints are turned back into local name
members.

This is the equal-members model of ADR-0021: a member machine's statement is a
member's testimony, not this user's approval, and a hostile member is not
contained.

Concurrent changes (state-model fix F8, decision D3). The higher generation wins.
At the same generation:

- an identical record is an echo: nothing changes, no generation goes up, and the
  acknowledgement it carries is noted;
- a different record goes to the larger machine key of the two authors, on both
  machines. A record this machine changed itself is authored by this machine's own
  key. The losing machine takes the winner's record, puts its own unacknowledged
  changes back on top, raises the generation and sends the result again, so no
  machine's change is lost to the tie.

Every change made here is kept in the team's `pending_ops` ({op: add|remove|lead|
replace, member, at_generation}; a handover is replace) until the other member
machines have acknowledged it. The acknowledgement travels in the record: it carries
`seen`, the highest generation of each machine's record the sender has taken, and the
receiver notes it in `acked_by` (machine -> the highest generation of its own record
that machine has taken). An op the sending machine had not seen is re-applied on top of
a newer record too, not only on a tie. An op that no longer applies (removing a member
who is already gone) is left out but named in the team log, as a conflict. Re-applying
raises the generation only when something changed, and an echo never does, so two
machines settle after a few records. Records written before these fields exist still
load. With three machines or more, an op stays pending until every other machine has
acknowledged it, so a machine that is away keeps it pending (and re-applies it on top of
that machine's next newer record).

A local name member (D26) travels as the endpoint of its session running now.
A member that is not running travels by name only and cannot be matched on the
other machine until it runs and the team is published again; a team send
publishes first when the team has remote members.
"""
from __future__ import annotations

import copy
import hashlib
import time

from . import paths, teams

FIELDS = ("name", "id", "generation", "lead", "members", "created_at", "updated_at", "seen")


def to_endpoints(team: dict, own_machine: str) -> dict:
    """The record as another machine reads it: every member an endpoint."""
    from .network_directory import public_endpoint

    def convert(member):
        if member is None or member.get("machine"):
            return member
        rec = teams.live_session(member)
        ep = public_endpoint(rec, own_machine) if rec else None
        if ep is None:
            return {"machine": own_machine, "runtime": member.get("runtime"), "name": member.get("name"),
                    "home_id": hashlib.sha256(member["home"].encode()).hexdigest(),
                    "session_id": None, "not_running": True}
        return {k: ep[k] for k in ("machine", "runtime", "home_id", "session_id")} | {"name": member.get("name")}

    out = {k: copy.deepcopy(team.get(k)) for k in FIELDS}
    out["members"] = [convert(m) for m in team.get("members", [])]
    out["lead"] = convert(team.get("lead"))
    return out


def publish(team: dict) -> list:
    """Send the team to its remote members' machines. Returns notes for the
    caller to show; a machine that cannot be reached is named, never retried
    silently (the next change or team send publishes again)."""
    from . import network
    if not any(m.get("machine") for m in team.get("members", [])):
        return []
    try:
        result = network.call({"op": "team-publish", "team": team}, timeout=30)
    except network.NetworkError as exc:
        return ["the team record was not sent to its members on other machines (%s); "
                "it is sent again with the next change or team send" % exc]
    return ["team %s not updated on machine %s: %s" % (team["name"], f["machine"][:8], f["code"])
            for f in result.get("failed", [])]


def receive(origin: str, incoming: dict, own_machine: str) -> dict:
    """Take a team record a member machine sent. Returns {"status": ...}; a result with
    `republish` names a team this machine changed while taking the record (it re-applied
    its own changes), which the network service must send again."""
    if not isinstance(incoming, dict):
        raise ValueError("invalid team record")
    name = teams.check_name(incoming.get("name") or "")
    if not isinstance(incoming.get("id"), str) or not isinstance(incoming.get("generation"), int) \
            or not isinstance(incoming.get("members"), list):
        raise ValueError("invalid team record")
    machines = {m.get("machine") for m in incoming["members"] if isinstance(m, dict)}
    if origin not in machines or own_machine not in machines:
        raise ValueError("a team is accepted only from a machine that has a member in it, "
                         "and only by a machine that has one")
    local = [_back_to_local(m, own_machine) for m in incoming["members"]]
    record = {k: copy.deepcopy(incoming.get(k)) for k in FIELDS if k != "seen"}
    record["members"] = [m for m in local if m is not None]
    record["lead"] = _back_to_local(incoming.get("lead"), own_machine) if incoming.get("lead") else None
    record["origin"] = origin
    record["author"] = origin
    sent_seen = incoming.get("seen") if isinstance(incoming.get("seen"), dict) else {}
    their_ack = sent_seen.get(own_machine)
    their_ack = their_ack if isinstance(their_ack, int) and not isinstance(their_ack, bool) else 0
    generation = record["generation"]
    with teams._locked(name) as path:
        current = paths.read_json(path)
        if current and current.get("id") != record["id"]:
            return {"status": "conflict", "reason": "a different team %s exists on this machine" % name}
        if not current:
            record["seen"] = {origin: generation}
            record["acked_by"] = {origin: their_ack}
            record["pending_ops"] = []
            record["log"] = [_received(origin, generation)]
            paths.write_json(path, record)
            return {"status": "updated"}
        mine = int(current.get("generation", 0))
        author = (current["author"] if "author" in current else current.get("origin")) or own_machine
        echo = generation == mine and _same_content(current, record)
        if generation != mine:
            take = generation > mine
        else:
            take = not echo and origin > author            # a tie: the larger machine key wins on both sides
        acked = dict(current.get("acked_by") or {})
        acked[origin] = max(int(acked.get(origin, 0)), their_ack)
        seen = dict(current.get("seen") or {})
        if not take:
            if echo:
                seen[origin] = max(int(seen.get(origin, 0)), generation)
            pending = _unacknowledged(current.get("pending_ops"), acked, current.get("members", []), own_machine)
            if (acked, seen, pending) != (current.get("acked_by") or {}, current.get("seen") or {},
                                          current.get("pending_ops") or []):
                current.update(acked_by=acked, seen=seen, pending_ops=pending)
                paths.write_json(path, current)
            return {"status": "stale"}
        seen[origin] = max(int(seen.get(origin, 0)), generation)
        record["seen"], record["acked_by"] = seen, acked
        record["log"] = list(current.get("log") or []) + [_received(origin, generation)]
        before = len(record["log"])
        record["pending_ops"] = _reapply(record, current.get("pending_ops"), origin, own_machine)
        paths.write_json(path, record)
        _notice_conflicts(name, [e for e in record["log"][before:] if e.get("action") == "conflict"], origin)
        return {"status": "updated"} if record["author"] else {"status": "updated", "republish": name}


def _notice_conflicts(team: str, conflicts: list, origin: str) -> None:
    """A change of this machine that could not be put back on the record taken is kept in the
    team log and, here, on the team's board as the item `team/<name>/conflicts`, which the
    members are told about like any board change (board_notice). A notice only: it never stops
    or refuses the record, and a board that cannot be written is left alone."""
    if not conflicts:
        return
    try:
        from . import board, doc
        item, path = "team/%s/conflicts" % team, board.path(team)
        heads = board.heads(board.items(doc.read(path)).get(item, []))
        lines = [ln for h in heads for ln in h["body"].splitlines() if ln.strip()]
        lines += ["%s: this machine's change (%s) was not applied on top of the record taken from machine %s: %s"
                  % (time.strftime("%Y-%m-%d %H:%M"), c.get("subject") and "%s %s" % (c.get("op"), c["subject"]) or c.get("op"),
                     origin[:8], c.get("reason")) for c in conflicts]
        doc.add(path, {"kind": "file-edit", "name": "xsm team sync"}, "\n".join(lines[-20:]), ["update"],
                [h["id"] for h in heads], item=item)
        board.render(team)
    except Exception:                  # a notice, never a block (spec 0, rule 4)
        pass


def _received(origin: str, generation: int) -> dict:
    return {"action": "received", "from": origin[:8], "generation": generation}


def _same_content(a: dict, b: dict) -> bool:
    """Whether two records (members in this machine's form) say the same: id, name, lead, members."""
    if a.get("id") != b.get("id") or a.get("name") != b.get("name"):
        return False
    la, lb = a.get("lead"), b.get("lead")
    if bool(la) != bool(lb) or (la and not teams._same(la, lb)):
        return False
    ma, mb = a.get("members") or [], b.get("members") or []
    return all(any(teams._same(x, y) for y in mb) for x in ma) \
        and all(any(teams._same(x, y) for y in ma) for x in mb)


def _unacknowledged(ops, acked: dict, members: list, own_machine: str) -> list:
    """The ops some other member machine has not acknowledged yet (`acked`: machine -> the
    highest generation of this machine's record it has taken). A team with no other machine
    keeps none."""
    others = {m["machine"] for m in members if m.get("machine") and m["machine"] != own_machine}
    return [op for op in ops or []
            if any(int(acked.get(machine, 0)) < int(op["at_generation"]) for machine in others)]


def _reapply(record: dict, ops, origin: str, own_machine: str) -> list:
    """Put this machine's changes that `origin` has not seen on top of the record just taken.
    An op that no longer applies is left out of the record but named in the team log (a
    conflict), never dropped silently. When something changed, the generation goes up and
    this machine becomes the author (the record is then newer than the one taken). Returns
    the ops that stay pending."""
    acked = int((record.get("acked_by") or {}).get(origin, 0))
    keep, todo, applied = [], [], []
    for op in ops or []:
        (todo if int(op["at_generation"]) > acked else keep).append(op)
    before = copy.deepcopy(record)
    for op in todo:
        reason = _apply(record, op)
        if reason is None:
            applied.append(op)
        else:
            record["log"].append({"t": time.time(), "action": "conflict", "op": op["op"],
                                  "subject": _op_label(op), "reason": reason,
                                  "generation": record["generation"]})
    if applied and _same_content(before, record):
        applied = []                    # the ops cancelled each other out: the record is what it was
    if applied:
        record["generation"] = int(record["generation"]) + 1
        record["updated_at"] = time.time()
        record["author"] = None
        record["log"].append({"t": time.time(), "action": "reapply", "by": None,
                              "subject": ", ".join(_op_label(op) for op in applied), "approval": None})
        for op in applied:
            op["at_generation"] = record["generation"]
    return _unacknowledged(keep + applied, record["acked_by"], record["members"], own_machine)


def _op_label(op: dict) -> str:
    member = op.get("member")
    text = teams.label(member) if member else "no lead"
    return "%s %s" % (op["op"], "%s -> %s" % (text, teams.label(op["to"])) if op.get("to") else text)


def _index(members: list, spec: dict, also=None):
    for i, m in enumerate(members):
        if teams._same(m, spec) or (also and teams._same(m, also)):
            return i
    return None


def _apply(record: dict, op: dict):
    """Apply one op to the record in place. None when it changed something, else why it did not."""
    members, lead = record["members"], record.get("lead")
    kind, spec = op["op"], op.get("member")
    if kind == "add":
        if _index(members, spec) is not None:
            return "already in the team"
        members.append(copy.deepcopy(spec))
    elif kind == "remove":
        at = _index(members, spec)
        if at is None:
            return "not in the team any more"
        del members[at]
        if lead and teams._same(lead, spec):
            record["lead"] = None
    elif kind == "lead":
        if spec is None:
            if not lead:
                return "there is no lead already"
            record["lead"] = None
        elif _index(members, spec) is None:
            return "not in the team, so it cannot lead"
        elif lead and teams._same(lead, spec):
            return "already the lead"
        else:
            record["lead"] = copy.deepcopy(members[_index(members, spec)])
    elif kind == "replace":
        at = _index(members, spec, op.get("also"))
        if at is None:
            return "the member handing over is not in the team any more"
        old, new = members.pop(at), copy.deepcopy(op["to"])
        if _index(members, new) is None:
            members.append(new)
        if lead and teams._same(lead, old):
            record["lead"] = new
    else:
        return "unknown op"
    return None


def _back_to_local(member, own_machine):
    """This machine's endpoint becomes its local name member when the session
    is registered here; other machines' endpoints stay as they are."""
    if not isinstance(member, dict):
        return None
    if member.get("machine") != own_machine:
        return {k: member.get(k) for k in ("machine", "runtime", "home_id", "session_id", "name")}
    from . import handover, registry
    matches = [r for r in registry.raw_records() if handover._names(r, member)]
    rec = registry._enrich(matches[0]) if len(matches) == 1 else None
    if rec and rec.get("home") and rec.get("name"):
        return teams.member_of(rec)
    return None
