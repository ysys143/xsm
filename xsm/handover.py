"""Handing a session's xsm place over to another session (ADR-0025 decision 20, D27).

Not the claim/ACK handoff of received messages (handoff.py): this is the user
telling a session "hand over to OO". What moves, at once:

- team places: membership and the lead's seat, in every team the session is in;
- the board items it owns: `owner/<its name>` (and `owner/<its name>/...`)
  become `owner/<the successor's name>`, and a `handover/<its name>` item says
  what happened, so the whole team sees it on the board, not in a DM;
- unread DMs: each one not yet acknowledged, verbatim, in the handover letter;
  the original is closed as moved, never deleted;
- pending asks: the questions it asked that have no final answer now belong to
  the successor, so late answers are recorded for it;
- the context summary the handing session wrote, in the same letter.

The letter reaches the successor at its next prompt (notice(), through the
prompt hook like a board line), and `xsm handover show` shows it again.

After that the old conversation's address leads to the successor: a DM sent
to it here, a message from another machine for it, and an answer to a question
it was asked all go to the successor (follow()). The old session keeps running
as an ordinary session with no team place; what it sends is its own.

A restart under the same name is not a handover: name members (D26) are taken
over by the new conversation of that name with no record here.
"""
from __future__ import annotations

import hashlib
import json
import os
import time

from . import paths

DIRECTORY = "handovers"
CHAIN = 8                 # successors followed at most (A -> B -> C ...)


class HandoverError(ValueError):
    pass


def _identity(record: dict) -> dict:
    from . import handoff
    return handoff._identity(record)


def _file(identity: dict) -> str:
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return paths.path(DIRECTORY, digest + ".json")


def load(record: dict) -> dict | None:
    try:
        return paths.read_json(_file(_identity(record)))
    except (ValueError, TypeError):
        return None


def _handle(record: dict) -> dict:
    return {k: record.get(k) for k in ("runtime", "home", "session_id", "name", "alias", "ref")}


def label(handle: dict) -> str:
    return "%s@%s [%s]" % (handle.get("name") or "(unnamed)", handle.get("alias"), handle.get("ref"))


# --- where an old address leads ---------------------------------------------------------

def successor_identity(identity: dict) -> dict | None:
    """The identity the chain of handovers from `identity` ends at, or None."""
    seen, current, last = set(), identity, None
    for _ in range(CHAIN):
        key = json.dumps(current, sort_keys=True)
        if key in seen:
            break
        seen.add(key)
        rec = paths.read_json(_file(current))
        if not rec:
            break
        current = last = rec["to_identity"]
    return last


def follow(target: dict | None) -> tuple:
    """(record, note): the successor's record when `target` was handed over,
    else (target, None)."""
    if not target or target.get("remote"):
        return target, None
    try:
        nxt = successor_identity(_identity(target))
    except (ValueError, TypeError):
        return target, None
    if not nxt:
        return target, None
    from . import registry
    rec = registry.by_session(nxt["runtime"], nxt["session_id"])
    if not rec:
        return target, None
    return rec, "%s handed its place over to %s, so this goes there" % (
        label(_handle(target)), label(_handle(rec)))


def follow_offline(candidates: list) -> dict | None:
    """For a name that only stopped sessions match: the one successor they
    were handed over to, if exactly one."""
    found = {}
    for rec in candidates or []:
        nxt, note = follow(rec)
        if note:
            found[(nxt.get("runtime"), nxt.get("session_id"))] = nxt
    return next(iter(found.values())) if len(found) == 1 else None


def succeeds(newer: dict, older: dict) -> bool:
    """Whether `newer` is `older` or holds its place by handover."""
    try:
        a, b = _identity(newer), _identity(older)
    except (ValueError, TypeError):
        return False
    return a == b or successor_identity(b) == a


def _records() -> list:
    try:
        names = sorted(os.listdir(paths.path(DIRECTORY)))
    except OSError:
        return []
    return [r for r in (paths.read_json(paths.path(DIRECTORY, n)) for n in names if n.endswith(".json")) if r]


def _names(identity: dict, endpoint: dict) -> bool:
    """Whether a local identity is the conversation a P2P endpoint names."""
    return identity.get("runtime") == endpoint.get("runtime") \
        and identity.get("session_id") == endpoint.get("session_id") \
        and hashlib.sha256(str(identity.get("home")).encode()).hexdigest() == endpoint.get("home_id")


def for_handle(handle: dict) -> dict | None:
    """The local successor record for a P2P endpoint of a handed-over session
    (network_messages): the handle names runtime, home_id and session_id."""
    for rec in _records():
        old = rec.get("from_identity") or {}
        if _names(old, handle):
            nxt, note = follow(old)
            return nxt if note else None
    return None


# --- other machines ------------------------------------------------------------------------
#
# A question asked from another machine is bound there to the endpoint it was
# sent to: that machine accepts an answer only from that endpoint. So the
# machine that made a handover tells the machines it talks to (testimony, as
# a team record is: ADR-0021), and they accept the successor's answer. A
# machine testifies only about its own sessions: the old and the new endpoint
# are both on the machine that sends it.

REMOTE = "remote-handovers"
ENDPOINT = ("machine", "runtime", "home_id", "session_id")


def _key(endpoint: dict) -> dict:
    return {k: endpoint.get(k) for k in ENDPOINT}


def _remote_file(endpoint: dict) -> str:
    digest = hashlib.sha256(json.dumps(_key(endpoint), sort_keys=True).encode()).hexdigest()
    return paths.path(REMOTE, digest + ".json")


def local_endpoint(identity: dict, machine: str) -> dict:
    """This machine's P2P endpoint (without its generation) of a local identity."""
    ident = _identity(identity)
    return {"machine": machine, "runtime": ident["runtime"], "session_id": ident["session_id"],
            "home_id": hashlib.sha256(ident["home"].encode()).hexdigest()}


def receive_testimony(origin: str, old: dict, new: dict) -> dict:
    """Keep another machine's statement that its session `old` handed over to
    its session `new`. Refused unless both are the sending machine's."""
    from .network_identity import endpoint
    old, new = endpoint(old), endpoint(new)
    if not (origin == old["machine"] == new["machine"]) or old == new:
        raise ValueError("a machine speaks only for its own sessions")
    path = _remote_file(old)
    current = paths.read_json(path)
    if current:
        return {"status": "kept" if _key(current.get("new") or {}) == new else "conflict"}
    paths.write_json(path, {"t": time.time(), "origin": origin, "old": old, "new": new})
    return {"status": "stored"}


def endpoint_succeeds(newer: dict, older: dict) -> bool:
    """Whether P2P endpoint `newer` is `older` or holds its place by handover:
    by this machine's own handovers, or by the testimony of the machine both
    are on."""
    newer, older = _key(newer), _key(older)
    if newer == older:
        return True
    if newer["machine"] != older["machine"]:
        return False
    current = older
    for _ in range(CHAIN):
        rec = paths.read_json(_remote_file(current))
        if not rec:
            break
        current = _key(rec.get("new") or {})
        if current == newer:
            return True
    for rec in _records():
        if _names(rec.get("from_identity") or {}, older):
            nxt = successor_identity(rec["from_identity"])
            return bool(nxt) and _names(nxt, newer)
    return False


def _publish(record: dict, teams_moved: list) -> list:
    """Tell the machines this session talks to (its teams' remote members, and
    the network service adds those that sent it messages) about the handover."""
    from . import network
    machines = sorted({m["machine"] for t in teams_moved for m in t["record"].get("members", [])
                       if m.get("machine")})
    if not network.available():
        return ["the handover was not sent to the team's other machines: the network service "
                "is not running"] if machines else []
    try:
        result = network.call({"op": "handover-publish", "old": record["from_identity"],
                               "new": record["to_identity"], "machines": machines}, timeout=30)
    except network.NetworkError as exc:
        return ["the handover was not sent to other machines (%s); answers from them to questions "
                "the old session was asked are not taken as answers until it is" % exc]
    return ["the handover was not recorded on machine %s: %s" % (f["machine"][:8], f["code"])
            for f in result.get("failed", [])]


# --- the handover itself ------------------------------------------------------------------

def _check(me: dict, target: dict) -> None:
    if not me or not me.get("session_id") or not me.get("registered"):
        raise HandoverError("this session is not registered, so it has no xsm place to hand over")
    if not target or target.get("remote"):
        raise HandoverError("the successor must be a session on this machine")
    if not target.get("registered"):
        raise HandoverError("%s has no hook record yet" % label(_handle(target)))
    if target.get("state") != "live":
        raise HandoverError("%s is not running" % label(_handle(target)))
    if _identity(target) == _identity(me):
        raise HandoverError("a session cannot hand over to itself")
    if load(target):
        raise HandoverError("%s has itself handed over to another session" % label(_handle(target)))
    if load(me):
        raise HandoverError("this session has already handed over")


def _word(record: dict) -> str:
    """A session's name as a board item name may hold it."""
    import re
    word = re.sub(r"[^A-Za-z0-9\u3131-\uD79D ._:-]", "-",
                  record.get("name") or record.get("ref") or "session").strip()
    return word[:40] or "session"


def _owned(item: str, name: str | None) -> str | None:
    """The rest of an `owner/<name>[/...]` item, '' for the item itself, or None."""
    if not name:
        return None
    base = "owner/" + name
    if item == base:
        return ""
    if item.startswith(base + "/"):
        return item[len(base):]
    return None


def _boards(me: dict, target: dict, team: dict) -> list:
    """Move the items this session owns on `team`'s board and say so there.
    Returns the items moved. Runs while `me` is still a member."""
    from . import board
    old, new = _word(me), _word(target)
    moved = []
    for item, heads in board.current(team["name"]).items():
        rest = _owned(item, old)
        if rest is None or len(heads) != 1:
            continue                     # an item with two versions at once is settled first
        new_item = "owner/" + new + rest
        board.set_item(me, team["name"], new_item, heads[0]["body"].rstrip()
                       + "\n\n(taken over from %s)" % old)
        board.set_item(me, team["name"], item, "handed over to %s (now %s)" % (new, new_item))
        moved.append(item)
    board.set_item(me, team["name"], "handover/" + old,
                   "%s handed its place in this team over to %s on %s. %s%s DMs to %s now reach %s."
                   % (old, new, time.strftime("%Y-%m-%d %H:%M"),
                      "Items moved: %s. " % ", ".join(moved) if moved else "",
                      "The lead's seat moved too. " if team.get("lead") and _lead(team, me) else "",
                      old, new))
    return moved


def _lead(team: dict, me: dict) -> bool:
    from . import teams
    return teams.is_lead(team, me)


def _teams(me: dict, target: dict, approval: str) -> list:
    from . import teams
    out = []
    member = teams.member_of(target)
    for team in teams.teams_of(me):
        with teams._locked(team["name"]) as path:
            current = paths.read_json(path)
            was_lead = teams.is_lead(current, me)
            current["members"] = [m for m in current["members"] if not teams.matches(m, me)]
            if not any(teams._same(m, member) for m in current["members"]):
                current["members"].append(member)
            if was_lead:
                current["lead"] = member
            teams._log(current, "handover", me, member, approval)
            paths.write_json(path, current)
        out.append({"team": current["name"], "lead": was_lead, "record": current})
    return out


def _questions(me: dict, target: dict) -> list:
    """Give the successor the questions this session asked and that have no
    final answer yet. Returns their ids."""
    from . import questions
    moved = []
    try:
        names = sorted(os.listdir(paths.path(questions.DIRECTORY)))
    except OSError:
        return moved
    mine = questions._native(me)
    for name in names:
        if not name.endswith(".json"):
            continue
        request_id = name[:-5]
        try:
            with questions._locked(request_id) as filename:
                record = paths.read_json(filename)
                if not record or questions._native(record["sender"]) != mine:
                    continue
                if any(r.get("outcome") for r in record.get("replies", [])):
                    continue                 # answered for good: it stays the asker's
                record["handed_over_from"] = record["sender"]
                record["sender"] = questions._handle(target)
                paths.write_json(filename, record)
                moved.append(request_id)
        except (ValueError, KeyError, TypeError):
            continue
    return moved


def _groups(me: dict, target: dict) -> list:
    from . import question_groups, questions
    moved = []
    try:
        names = sorted(os.listdir(paths.path(question_groups.DIRECTORY)))
    except OSError:
        return moved
    mine = questions._native(me)
    for name in names:
        path = paths.path(question_groups.DIRECTORY, name)
        record = paths.read_json(path) if name.endswith(".json") else None
        if record and record.get("sender") == mine:
            record["handed_over_from"] = record["sender"]
            record["sender"] = questions._native(target)
            paths.write_json(path, record)
            moved.append(record.get("id"))
    return moved


def _unread(me: dict, target: dict) -> list:
    """The DMs this session has not acknowledged, closed here as moved."""
    from . import handoff, inbox
    moved = {r["id"]: r for r in handoff.move_out(me, target)}
    for item in inbox.peek(me["session_id"]):          # copies kept before the canonical store
        if item.get("id") and item["id"] not in moved:
            moved[item["id"]] = {"id": item["id"], "message": {"content": item["content"]},
                                 "stored_at": item.get("t", 0)}
        inbox.drop(me["session_id"], item.get("id"))
    return sorted(moved.values(), key=lambda r: (r.get("stored_at", 0), r["id"]))


def _letter(me: dict, target: dict, summary: str, teams_moved: list, items: dict,
            asks: list, groups: list, unread: list) -> str:
    old = label(_handle(me))
    lines = ["[xsm handover] %s handed its xsm place over to you, at its user's request." % old,
             "", "What is yours now:"]
    for t in teams_moved:
        lines.append("- team %s%s%s" % (t["team"], " as its lead" if t["lead"] else "",
                     "; board items " + ", ".join(items.get(t["team"]) or []) if items.get(t["team"]) else ""))
    if not teams_moved:
        lines.append("- no team places (it was in no team)")
    lines.append("- %d pending question%s it asked (late answers come to you; `xsm question-status <id>`): %s"
                 % (len(asks), "" if len(asks) == 1 else "s", ", ".join(asks) or "none"))
    if groups:
        lines.append("- question groups: " + ", ".join(g for g in groups if g))
    lines.append("- DMs sent to %s from now on reach you" % old)
    lines += ["", "Its context summary:", "", summary.strip() or "(none written)"]
    lines += ["", "%d unread DM%s it had, verbatim (answer each sender at the address it shows):"
              % (len(unread), "" if len(unread) == 1 else "s")]
    for r in unread:
        m = r.get("message") or {}
        lines += ["", "--- DM %s ---" % r["id"], (m.get("content") or m.get("body") or "").rstrip()]
    lines += ["", "Continue its work from here: read the team boards (`xsm board show <team>`), "
              "tell the team you took over, and if you hold a lead's seat, keep directing "
              "the team; members report to you now."]
    return "\n".join(lines)


def hand_over(me: dict, target: dict, summary: str, approval: str) -> dict:
    """Move this session's xsm place to `target` (the caller has the user's yes)."""
    from . import team_sync, teams
    _check(me, target)
    items = {}
    for team in teams.teams_of(me):
        items[team["name"]] = _boards(me, target, team)
    teams_moved = _teams(me, target, approval)
    asks = _questions(me, target)
    groups = _groups(me, target)
    unread = _unread(me, target)
    record = {"t": time.time(), "from": _handle(me), "from_identity": _identity(me),
              "to": _handle(target), "to_identity": _identity(target), "approval": approval,
              "teams": [{"team": t["team"], "lead": t["lead"]} for t in teams_moved],
              "items": items, "questions": asks, "groups": groups,
              "messages": [r["id"] for r in unread]}
    record["letter"] = _letter(me, target, summary, teams_moved, items, asks, groups, unread)
    record["shown"] = False
    paths.write_json(_file(record["from_identity"]), record)
    notes = []
    for t in teams_moved:
        notes += team_sync.publish(t["record"])
    notes += _publish(record, teams_moved)
    record["notes"] = notes
    return record


# --- the successor reads it ----------------------------------------------------------------

def received(me: dict) -> list:
    """The handovers made to this session, oldest first."""
    try:
        mine = _identity(me)
        names = os.listdir(paths.path(DIRECTORY))
    except (OSError, ValueError, TypeError):
        return []
    out = [paths.read_json(paths.path(DIRECTORY, n)) for n in names if n.endswith(".json")]
    return sorted((r for r in out if r and r.get("to_identity") == mine), key=lambda r: r["t"])


def notice(me: dict | None) -> str | None:
    """The handover letter, once, at the successor's next prompt. It is not a
    DM: after the teams moved the two sessions may share no scope, and the
    letter is this machine's own record of what the user asked for."""
    if not me:
        return None
    out = []
    for rec in received(me):
        if rec.get("shown"):
            continue
        out.append(rec["letter"])
        rec["shown"] = time.time()
        paths.write_json(_file(rec["from_identity"]), rec)
    return "\n\n".join(out) or None


def summary_line(rec: dict) -> str:
    teams_part = ", ".join("%s%s" % (t["team"], " (lead)" if t["lead"] else "") for t in rec["teams"]) or "no teams"
    items = sum(len(v) for v in rec["items"].values())
    return ("handed over to %s: %s; %d board item%s, %d unread DM%s, %d pending question%s. "
            "It reads the letter at its next prompt; DMs to this session now reach it."
            % (label(rec["to"]), teams_part, items, "" if items == 1 else "s",
               len(rec["messages"]), "" if len(rec["messages"]) == 1 else "s",
               len(rec["questions"]), "" if len(rec["questions"]) == 1 else "s"))

