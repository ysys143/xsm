"""Handing a session's xsm place over to another session (ADR-0025 decision 20, D27).

Not the claim/ACK handoff of received messages (handoff.py): this is the user
telling a session "hand over to OO". What moves, at once:

- team places: membership and the lead's seat, in every team the session is in;
- the board items it owns: `owner/<its name>` (and `owner/<its name>/...`)
  become `owner/<the successor's name>`, and a `handover/<its name>` item says
  what happened, so the whole team sees it on the board, not in a DM;
- unread and held DMs: each original not yet acknowledged is copied to the
  successor (handoff.hand_to) and stays at the old session marked `moved_to`; the
  successor receives it through its own gate and inbox as any message. Held
  entries follow (held.rebind). The letter says how many and which, never what;
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
import uuid
from contextlib import contextmanager

from . import paths

DIRECTORY = "handovers"
CHAIN = 8                 # successors followed at most (A -> B -> C ...)
LOCK_SECONDS = 30         # how long a handover waits for another one on this machine
STEPS = ("boards", "teams", "questions", "groups", "originals", "held")    # in the order they run


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


def is_done(record: dict | None) -> bool:
    """A record without `state` was written by 0.6.1, which wrote it last: done."""
    return bool(record) and record.get("state", "done") == "done"


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
        from . import migration
        moved = migration.retirement(current)
        if moved and moved['status'] == 'committed':
            current = last = _identity(moved['target'])
            continue
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
    from . import migration
    if migration.retirement(target):
        return migration.redirect(target)
    try:
        nxt = successor_identity(_identity(target))
    except (ValueError, TypeError):
        return target, None
    if not nxt:
        return target, None
    from . import registry
    rec = registry.by_session(nxt["runtime"], nxt["session_id"], home=nxt["home"])
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


def proves_copy(record: dict, receiver: dict) -> bool:
    """Whether a stored original that came to `receiver` by handover (and, before
    or after it, by profile migration) is its own: every hop leaves the endpoint
    the previous one reached, and a handover hop is stood for by
    handovers/<source>.json (`moving` or `done`, to the same endpoint). The
    request identity stays the original's (migration.proves_copy does the same
    for migrations alone and is not changed)."""
    from . import envelope, migration
    chain = record.get("handover_history") or []
    if not chain:
        return False
    canonical = record["identity"]["to"]
    previous = {"runtime": canonical["runtime"], "home": canonical["home"],
                "session_id": canonical["conversation"]}

    def migrated(hop: dict) -> bool:
        transfer = migration.read(hop["id"])
        return bool(transfer and transfer["status"] in ("fenced", "moving", "committed")
                    and migration.endpoint(transfer["source"]) == hop["source"]
                    and migration.endpoint(transfer["target"]) == hop["target"])

    def handed(hop: dict) -> bool:
        rec = paths.read_json(_file(hop["source"]))
        return bool(rec and rec.get("state", "done") in ("moving", "done")
                    and rec.get("from_identity") == hop["source"] and rec.get("to_identity") == hop["target"]
                    and rec.get("id", hop["id"]) == hop["id"])

    try:
        steps = []
        for hop in chain:
            steps += [(migrated, m) for m in hop.get("migrations") or []] + [(handed, hop)]
        steps += [(migrated, m) for m in record.get("migration_history") or []]
        for check, hop in steps:
            if previous != hop["source"] or not check(hop):
                return False
            previous = hop["target"]
        return previous == _identity(receiver) and envelope.request_digest(record["identity"]) == record["digest"]
    except (KeyError, TypeError, ValueError):
        return False


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
    from . import migration
    for filename in migration._json_files(migration.DIRECTORY):
        transfer = paths.read_json(filename)
        if transfer and _names(_identity(transfer['source']), handle) and migration.retirement(transfer['source']):
            return migration.redirect(transfer['source'])[0]
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
    from . import migration
    for filename in migration._json_files(migration.DIRECTORY):
        transfer = paths.read_json(filename)
        if transfer and _names(_identity(transfer['source']), older):
            nxt = successor_identity(_identity(transfer['source']))
            if nxt and _names(nxt, newer):
                return True
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
#
# Order (PROTOCOL 5.15): one handover at a time on this machine (a blocking
# file lock), `_check`, then `_begin` writes handovers/<A>.json with
# state="moving": from then on the old address leads to the successor. Each
# step runs once (`_step` marks it done in that record), so a handover that
# died half way is finished by running it again to the same target. `_finish`
# writes the letter and sets state="done"; only then do the readers of letters
# and receipts see it.

@contextmanager
def _handover_lock(timeout: float = LOCK_SECONDS):
    """The machine-wide handover lock. It waits; the caller judges again
    (`_check`) once it holds it, so two requests give the same result in
    either order."""
    import fcntl
    os.makedirs(paths.path(DIRECTORY), mode=0o700, exist_ok=True)
    fd = os.open(paths.path(DIRECTORY, ".lock"), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise HandoverError("another handover is running on this machine and did not finish in %d "
                                        "seconds; try again" % int(timeout))
                time.sleep(0.05)
        yield
    finally:
        os.close(fd)


def _check(me: dict, target: dict, resume: bool = False) -> None:
    """Refuse what cannot be done. `resume`: an unfinished (moving) handover of
    `me` to this same `target` is not a refusal, it is finished."""
    from . import migration
    migration.assert_active(me)
    migration.assert_active(target)
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
    mine = load(me)
    if mine:
        if resume and mine.get("state") == "moving" and mine.get("to_identity") == _identity(target):
            return
        raise HandoverError(
            "%s already handed its place over to %s; to move on, hand %s over from there: run "
            "`xsm handover <session>` in %s"
            % (label(_handle(me)), label(mine["to"]), label(mine["to"]), label(mine["to"])))
    theirs = load(target)
    if theirs:
        if successor_identity(_identity(target)) == _identity(me):
            raise HandoverError(
                "%s already handed its place over to %s, so handing %s over to it would make a loop; "
                "run `xsm handover <session>` with a session that has not handed over"
                % (label(_handle(target)), label(theirs["to"]), label(_handle(me))))
        raise HandoverError(
            "%s has itself handed over to %s; hand over to %s instead: run `xsm handover %s`"
            % (label(_handle(target)), label(theirs["to"]), label(theirs["to"]),
               theirs["to"].get("ref") or "<session>"))


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


def _closed(new: str, new_item: str) -> str:
    return "handed over to %s (now %s)" % (new, new_item)


CLOSE_ROUNDS = 5     # how many times a late write to owner/<old> is carried before the item is reported


def _boards(me: dict, target: dict, places: list) -> dict:
    """Move the items this session owns on the boards of `places` and say so
    there. A team it has left since is skipped and named, and so is an item
    that has two versions at once (settled first by its members). Runs while
    `me` is still a member; an item already closed by an earlier run counts as
    moved and is not copied again."""
    from . import board, teams
    out = {"items": {}, "skipped": [], "skipped_items": {}}
    for name in places:
        team = teams.load(name)
        if not team or not teams.is_member(team, me):
            out["skipped"].append(name)
            continue
        moved = out["items"].setdefault(name, [])
        left = []
        try:
            _board_team(me, target, team, moved, left)
        except board.BoardError:
            out["skipped"].append(name)          # it left while its board was moving
        if left:
            out["skipped_items"][name] = left
    return out


def _carried(team: str, new_item: str, body: str) -> bool:
    """Whether `owner/<new>` already holds a node carrying this text (a run
    that died after copying it): carrying it again would duplicate it."""
    from . import board, doc
    prefix = body.rstrip() + "\n\n("
    return any(n["body"].startswith(prefix)
               for n in board.items(doc.read(board.path(team))).get(new_item, []))


def _carry(me: dict, team: str, new_item: str, body: str, marker: str) -> None:
    from . import board
    if not _carried(team, new_item, body):
        board.set_item(me, team, new_item, body.rstrip() + "\n\n(%s)" % marker)


def _close(me: dict, team: dict, item: str, new_item: str, old: str, closing: str) -> bool:
    """Close `item` with the forwarding note, then read it again: a head that
    is not the note was written meanwhile (a member's write lands between the
    copy and the closing write, or between the reading and the listing). Carry
    it to `new_item` and close again over every head, until one head is left.
    Returns whether the item ends with the note alone."""
    from . import board, teams
    name = team["name"]
    for _ in range(CLOSE_ROUNDS):
        board.show(me, name)                     # the closing write builds on every head read now
        heads = board.current(name).get(item, [])
        extra = [h for h in heads if h["body"].strip() != closing]
        for h in extra:
            _carry(me, name, new_item, h["body"],
                   "written to %s during the handover" % item)
        if len(heads) == 1 and not extra:
            return True
        if not teams.is_member(teams.load(name) or {}, me):
            raise board.BoardError("%s left team %s" % (old, name))
        board.set_item(me, name, item, closing)
    board.show(me, name)
    return len(board.current(name).get(item, [])) == 1


def _board_team(me: dict, target: dict, team: dict, moved: list, left: list | None = None) -> None:
    from . import board, teams
    left = [] if left is None else left
    name = team["name"]
    old, new = _word(me), _word(target)
    board.show(me, name)         # what it moves, it has read
    state = board.current(name)
    mine, held = [], []
    for item, heads in state.items():
        if _owned(item, old) is None:
            continue
        closing = _closed(new, "owner/" + new + _owned(item, old))
        if len(heads) == 1 or any(h["body"].strip() == closing for h in heads):
            mine.append((item, heads))           # one version, or a closing note a dead run left beside a late write
        else:
            held.append(item)                    # two versions at once: settled first, by their writers
    left.extend(held)
    note = ("%s handed its place in this team over to %s on %s. %s%s%sDMs to %s now reach %s."
            % (old, new, time.strftime("%Y-%m-%d %H:%M"),
               "Items moved: %s. " % ", ".join(item for item, _ in mine) if mine else "",
               "The lead's seat moved too. " if team.get("lead") and _lead(team, me) else "",
               "Not moved, two versions at once (settle them, then hand them over by hand): %s. "
               % ", ".join(held) if held else "",
               old, new))
    # The announcement comes first: if the session leaves the team now, nothing
    # of its items has moved yet and nothing is left half done on the board.
    said = state.get("handover/" + old) or []
    if not any(h["body"].startswith("%s handed its place in this team over to %s on " % (old, new))
               for h in said):
        board.set_item(me, name, "handover/" + old, note)
    for item, heads in mine:
        new_item = "owner/" + new + _owned(item, old)
        closing = _closed(new, new_item)
        if len(heads) == 1 and heads[0]["body"].strip() == closing:
            moved.append(item)                   # a run that died after closing it
            continue
        if not teams.is_member(teams.load(name) or {}, me):
            raise board.BoardError("%s left team %s" % (old, name))
        for h in heads:
            if h["body"].strip() != closing:
                _carry(me, name, new_item, h["body"], "taken over from %s" % old)
        if _close(me, team, item, new_item, old, closing):
            moved.append(item)
        else:
            left.append(item)                    # still written to faster than it can be closed
    unsaid = [i for i in left if i not in held]
    if unsaid:
        board.set_item(me, name, "handover/" + old,
                       "%s: not moved, still being written to during the handover: %s."
                       % (old, ", ".join(unsaid)))


def _lead(team: dict, me: dict) -> bool:
    from . import teams
    return teams.is_lead(team, me)


def _places(me: dict) -> list:
    """The names of the teams `me` is in, listed until two lists agree: a team
    it joins while the list is being made is not missed."""
    from . import teams
    last = None
    for _ in range(3):
        now = sorted(t["name"] for t in teams.teams_of(me))
        if now == last:
            break
        last = now
    return now


def _teams(me: dict, target: dict, places: list, approval: str) -> dict:
    """Replace `me` by `target` in each of `places`, looking again at the
    membership under that team's lock: a team `me` has left since is skipped
    and named. A team it joined after the list is moved too."""
    from . import teams
    member = teams.member_of(target)
    out = {"moved": [], "left": []}

    def move(name: str) -> dict | None:
        with teams._locked(name) as path:
            current = paths.read_json(path)
            if not current or not teams.is_member(current, me):
                return None
            was_lead = teams.is_lead(current, me)
            current["members"] = [m for m in current["members"] if not teams.matches(m, me)]
            if not any(teams._same(m, member) for m in current["members"]):
                current["members"].append(member)
            if was_lead:
                current["lead"] = member
            teams._log(current, "handover", me, member, approval)
            paths.write_json(path, current)
        return {"team": name, "lead": was_lead}

    for name in places:
        moved = move(name)
        if moved:
            out["moved"].append(moved)
        else:
            out["left"].append(name)
    for team in teams.teams_of(me):
        if team["name"] not in places:
            moved = move(team["name"])
            if moved:
                out["moved"].append(dict(moved, late=True))
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


def _originals(me: dict, target: dict, handover_id: str) -> dict:
    """The DMs this session has not acknowledged, copied to the successor with
    their state (held ones included); a conflicting one stays here and is listed.
    The old inbox copies of what moved are dropped: the successor has the original."""
    from . import handoff, inbox
    out = handoff.hand_to(me, target, handover_id)
    for mid in out["moved"]:
        inbox.drop(me["session_id"], mid)
    return out


def _held(me: dict, target: dict, handover_id: str) -> dict:
    """The held entries of this session now belong to the successor: `xsm held
    deliver` works for it and for nobody else (the person's yes still decides)."""
    from . import held
    names = held.rebind(me, target, {"handover": handover_id})
    ids = []
    for name in names:
        entry = paths.read_json(paths.path(paths.HELD, name)) or {}
        ids.append(entry.get("id") or name[:-5])
    return {"names": [n[:-5] for n in names], "ids": ids}


def _letter(me: dict, target: dict, summary: str, teams_moved: list, items: dict,
            asks: list, groups: list, originals: dict, skipped: list | None = None,
            held: dict | None = None, skipped_items: dict | None = None) -> str:
    old = label(_handle(me))
    lines = ["[xsm handover] %s handed its xsm place over to you, at its user's request." % old,
             "", "What is yours now:"]
    for t in teams_moved:
        lines.append("- team %s%s%s" % (t["team"], " as its lead" if t["lead"] else "",
                     "; board items " + ", ".join(items.get(t["team"]) or []) if items.get(t["team"]) else ""))
    if not teams_moved:
        lines.append("- no team places (it was in no team)")
    if skipped:
        lines.append("- not moved, it had left these teams meanwhile: " + ", ".join(skipped))
    for team_name, names in sorted((skipped_items or {}).items()):
        lines.append("- board items not moved in team %s (two versions at once, or still written to): %s; "
                     "see the item `handover/%s` on that board"
                     % (team_name, ", ".join(names), _word(me)))
    lines.append("- %d pending question%s it asked (late answers come to you; `xsm question-status <id>`): %s"
                 % (len(asks), "" if len(asks) == 1 else "s", ", ".join(asks) or "none"))
    if groups:
        lines.append("- question groups: " + ", ".join(g for g in groups if g))
    lines.append("- DMs sent to %s from now on reach you" % old)
    lines += ["", "Its context summary:", "", summary.strip() or "(none written)"]
    held = held or {"names": [], "ids": []}
    moved, kept = originals.get("moved") or [], originals.get("kept") or []
    unread = [m for m in moved if m not in held["ids"]]
    lines += ["", "Its DMs (their text is not in this letter; they reach you as any message does):",
              "- %d unread DM%s moved to you, in your inbox: %s"
              % (len(unread), "" if len(unread) == 1 else "s", ", ".join(unread) or "none")]
    if held["names"]:
        lines.append("- %d held DM%s moved to you and still held, because its gate kept %s for its user's yes "
                     "(`xsm held deliver <id>`, with your user's yes): %s"
                     % (len(held["names"]), "" if len(held["names"]) == 1 else "s",
                        "it" if len(held["names"]) == 1 else "them", ", ".join(held["names"])))
    if kept:
        lines.append("- %d DM%s stayed with %s (could not be moved): %s"
                     % (len(kept), "" if len(kept) == 1 else "s", old,
                        "; ".join("%s (%s)" % (k["id"], k["why"]) for k in kept)))
    lines += ["", "Continue its work from here: read the team boards (`xsm board show <team>`), "
              "tell the team you took over, and if you hold a lead's seat, keep directing "
              "the team; members report to you now."]
    return "\n".join(lines)


def _save(rec: dict) -> None:
    paths.write_json(_file(rec["from_identity"]), rec)


def _begin(me: dict, target: dict, summary: str, approval: str) -> dict:
    """Write the handover down before anything moves. From here the old address
    leads to `target` (follow), and the steps below can be run again."""
    rec = {"id": uuid.uuid4().hex, "state": "moving", "t": time.time(),
           "from": _handle(me), "from_identity": _identity(me),
           "to": _handle(target), "to_identity": _identity(target),
           "approval": approval, "summary": summary, "places": _places(me),
           "steps": {}, "shown": False}
    _save(rec)
    return rec


def _step(rec: dict, name: str, fn):
    """Run one step once: its result is stored in the record as its marker, so
    a handover run again to the same target skips what is done."""
    if name in rec["steps"]:
        return rec["steps"][name]
    rec["steps"][name] = fn()
    _save(rec)
    return rec["steps"][name]


def _finish(rec: dict, me: dict, target: dict) -> dict:
    steps = rec["steps"]
    rec["teams"] = steps["teams"]["moved"]
    rec["items"] = {t: list(v) for t, v in steps["boards"]["items"].items()}
    rec["questions"], rec["groups"] = steps["questions"], steps["groups"]
    rec["messages"] = list(steps["originals"]["moved"])
    rec["held_messages"] = list(steps["held"]["ids"])
    rec["kept_messages"] = list(steps["originals"]["kept"])
    rec["skipped"] = {"teams": sorted(set(steps["boards"]["skipped"]) | set(steps["teams"]["left"])),
                      "items": {t: list(v) for t, v in (steps["boards"].get("skipped_items") or {}).items()}}
    rec["letter"] = _letter(me, target, rec.get("summary") or "", rec["teams"], rec["items"],
                            rec["questions"], rec["groups"], steps["originals"], rec["skipped"]["teams"],
                            steps["held"], rec["skipped"]["items"])
    rec["state"] = "done"
    rec["finished_at"] = time.time()
    _save(rec)
    return rec


def _run(rec: dict, me: dict, target: dict) -> dict:
    """The steps, each once. An exception (or a death) in a step leaves the
    record `moving`; running it again to the same target goes on from there."""
    _step(rec, "boards", lambda: _boards(me, target, rec["places"]))
    _step(rec, "teams", lambda: _teams(me, target, rec["places"], rec["approval"]))
    _step(rec, "questions", lambda: _questions(me, target))
    _step(rec, "groups", lambda: _groups(me, target))
    _step(rec, "originals", lambda: _originals(me, target, rec["id"]))
    _step(rec, "held", lambda: _held(me, target, rec["id"]))
    return _finish(rec, me, target)


def _record_of(identity: dict) -> dict | None:
    from . import registry
    return registry.by_session(identity["runtime"], identity["session_id"], home=identity["home"])


def _announce(rec: dict) -> list:
    """Tell the other machines (outside the lock: it is network)."""
    from . import team_sync, teams
    notes, moved = [], []
    for t in rec["teams"]:
        team = teams.load(t["team"])
        if team:
            moved.append({"record": team})
            notes += team_sync.publish(team)
    return notes + _publish(rec, moved)


def unfinished() -> list:
    """The handovers that began and did not finish: what a crash leaves."""
    return [r for r in _records() if r.get("state") == "moving"]


def hand_over(me: dict, target: dict, summary: str, approval: str) -> dict:
    """Move this session's xsm place to `target` (the caller has the user's yes).
    One at a time on this machine; a `moving` record of this session to the same
    target is finished, not started again."""
    finished, refusal = [], None
    try:
        with _handover_lock():
            pending = load(me)
            if pending and pending.get("state") == "moving" and pending.get("to_identity") != _identity(target):
                # An earlier handover to another session did not finish: finish it
                # first, then judge this request (it is a second handover).
                earlier = _record_of(pending["to_identity"])
                if earlier is None:
                    raise HandoverError(
                        "an earlier handover of %s to %s did not finish and that session is not found; "
                        "start it again, or hand over to it once it is running"
                        % (label(_handle(me)), label(pending["to"])))
                _check(me, earlier, resume=True)
                finished.append(_run(pending, me, earlier))
            _check(me, target, resume=True)
            pending = load(me)
            rec = pending if pending else _begin(me, target, summary, approval)
            finished.append(_run(rec, me, target))
    except HandoverError as exc:
        refusal = exc
    notes = []
    for rec in finished:
        notes += _announce(rec)
    if refusal:
        raise refusal
    finished[-1]["notes"] = notes
    return finished[-1]


# --- the successor reads it ----------------------------------------------------------------

def received(me: dict) -> list:
    """The handovers made to this session that are done, oldest first."""
    try:
        mine = _identity(me)
        names = os.listdir(paths.path(DIRECTORY))
    except (OSError, ValueError, TypeError):
        return []
    out = [paths.read_json(paths.path(DIRECTORY, n)) for n in names if n.endswith(".json")]
    return sorted((r for r in out if is_done(r) and r.get("to_identity") == mine), key=lambda r: r["t"])


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
    left = (rec.get("skipped") or {}).get("teams") or []
    held = (rec.get("skipped") or {}).get("items") or {}
    return ("handed over to %s: %s; %d board item%s, %d unread DM%s, %d pending question%s. "
            "It reads the letter at its next prompt; DMs to this session now reach it.%s"
            % (label(rec["to"]), teams_part, items, "" if items == 1 else "s",
               len(rec["messages"]), "" if len(rec["messages"]) == 1 else "s",
               len(rec["questions"]), "" if len(rec["questions"]) == 1 else "s",
               (" Not moved, it had left %s meanwhile." % ", ".join(left) if left else "")
               + (" Board items not moved: %s." % "; ".join("%s: %s" % (t, ", ".join(v))
                                                           for t, v in sorted(held.items())) if held else "")))

