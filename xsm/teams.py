"""Teams: the sessions working together (ADR-0025 decisions 9-20).

A team is a list of members with an optional lead. It is not a place messages
pile up: a DM to the team goes to each member (multisend), and the team's board
lives in the same folder (ADR-0026). A session may be in several teams.

- A member is held by name (D26): a session of this machine is (runtime, home,
  name), so the same name opened again takes its place back. A session of
  another machine is (machine, runtime, home_id, session_id): the P2P frame
  carries no name, so a remote member is bound to its conversation and moves
  only by a handoff.
- Being in a team lets members DM each other (D19). That is a permission of its
  own, read here and in config.scope_for; it is never expanded into pair
  permissions, and it opens nothing to anyone outside the team.
- Who changes it (D20, D5): a lead adds and removes sessions of its own project;
  a session outside that scope joins only on the user's approval, and naming or
  changing the lead is always the user's. A member may leave by itself. The
  approval itself is collected by the caller (cli/mcp) and recorded here.
"""
from __future__ import annotations

import os
import re
import time
import uuid
from contextlib import contextmanager

from . import paths

DIRECTORY = "teams"
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")
ADDRESS_PREFIXES = ("team:", "#")


class TeamError(ValueError):
    pass


# --- storage --------------------------------------------------------------------

def check_name(name: str) -> str:
    name = (name or "").strip()
    if not NAME_RE.match(name):
        raise TeamError("a team name is letters, digits, '.', '_' and '-' (up to 63), "
                        "starting with a letter or digit")
    return name


def folder(name: str) -> str:
    return paths.path(DIRECTORY, check_name(name))


def _file(name: str) -> str:
    return os.path.join(folder(name), "team.json")


@contextmanager
def _locked(name: str):
    import fcntl
    os.makedirs(folder(name), mode=0o700, exist_ok=True)
    fd = os.open(os.path.join(folder(name), ".lock"), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield _file(name)
    finally:
        os.close(fd)


def load(name: str) -> dict | None:
    try:
        rec = paths.read_json(_file(name))
    except TeamError:
        return None
    return rec if isinstance(rec, dict) and rec.get("name") == name else None


def names() -> list:
    try:
        entries = sorted(os.listdir(paths.path(DIRECTORY)))
    except OSError:
        return []
    return [n for n in entries if NAME_RE.match(n) and load(n)]


def all_teams() -> list:
    return [t for t in (load(n) for n in names()) if t]


# --- members --------------------------------------------------------------------

def member_of(record: dict, by_conversation: bool = False) -> dict:
    """The member key of a registry record (local) or a P2P endpoint (remote).
    A local session is held by name (D26); one without a name, or a member
    made from a selected conversation (by_conversation), by its session id."""
    if record.get("machine") and record.get("home_id") and not record.get("home"):
        return {"machine": record["machine"], "runtime": record.get("runtime"),
                "home_id": record["home_id"], "session_id": record.get("session_id"),
                "name": record.get("name")}
    if not (record.get("runtime") and record.get("home")):
        raise TeamError("not a registered session")
    home = os.path.realpath(os.path.expanduser(record["home"]))
    if record.get("name") and not by_conversation:
        return {"runtime": record["runtime"], "home": home, "name": record["name"]}
    if not record.get("session_id"):
        raise TeamError("not a registered session")
    return {"runtime": record["runtime"], "home": home, "session_id": record["session_id"],
            "name": record.get("name")}


def _same(member: dict, other: dict) -> bool:
    if member.get("machine") or other.get("machine"):
        return all(member.get(k) == other.get(k) for k in ("machine", "runtime", "home_id", "session_id"))
    if member.get("runtime") != other.get("runtime") or member.get("home") != other.get("home"):
        return False
    if member.get("session_id") or other.get("session_id"):
        return member.get("session_id") == other.get("session_id")
    return member.get("name") == other.get("name")


def matches(member: dict, record: dict) -> bool:
    """Whether a session (registry record or P2P endpoint) is this member: by
    name for a name member, by session id for a conversation member."""
    try:
        if member.get("session_id") and not member.get("machine"):
            return _same(member, member_of(record, by_conversation=True))
        return _same(member, member_of(record))
    except (TeamError, TypeError):
        return False


def label(member: dict) -> str:
    if member.get("session_id") and not member.get("machine") and not member.get("name"):
        return "%s:%s" % (member.get("runtime"), member["session_id"][:12])
    if member.get("machine"):
        return "%s on %s [%s]" % (member.get("name") or member.get("session_id"),
                                   member["machine"][:8], member.get("runtime"))
    alias = os.path.basename(member.get("home", "").rstrip("/")).lstrip(".") or "?"
    return "%s@%s" % (member.get("name"), alias)


def is_member(team: dict, record: dict) -> bool:
    return any(matches(m, record) for m in team.get("members", []))


def is_lead(team: dict, record: dict) -> bool:
    return bool(team.get("lead")) and matches(team["lead"], record)


def live_session(member: dict) -> dict | None:
    """The live local session a member names now: the newest live record with
    that runtime, home and name (D26: the same name opened again)."""
    if member.get("machine"):
        return None
    from . import registry
    rows = [r for r in registry.records() if r.get("state") == "live" and matches(member, r)]
    return max(rows, key=lambda r: r.get("updated", 0)) if rows else None


def address(member: dict) -> str | None:
    """A send target for a member right now, or None when it is not running."""
    if member.get("machine"):
        from .network_identity import target
        try:
            return target({k: member[k] for k in ("machine", "runtime", "home_id", "session_id")})
        except (KeyError, ValueError, TypeError):
            return None
    rec = live_session(member)
    return "%s:%s" % (rec["runtime"], rec["session_id"]) if rec else None


# --- permission (D19) -------------------------------------------------------------

def scope_for(a: dict, b: dict) -> str | None:
    """The first team that has both sessions, or None. Never a pair permission."""
    for team in all_teams():
        if is_member(team, a) and is_member(team, b):
            return team["name"]
    return None


def teams_of(record: dict) -> list:
    return [t for t in all_teams() if is_member(t, record)]


# --- changes -----------------------------------------------------------------------

def _log(team: dict, action: str, by: dict, subject: dict | None, approval: str | None) -> None:
    team.setdefault("log", []).append({
        "t": time.time(), "action": action, "by": label(member_of(by)) if by else None,
        "subject": label(subject) if subject else None, "approval": approval})
    team["generation"] = int(team.get("generation", 0)) + 1
    team["updated_at"] = time.time()


def create(me: dict, name: str) -> dict:
    name = check_name(name)
    creator = member_of(me)
    with _locked(name) as path:
        if paths.read_json(path):
            raise TeamError("team %s already exists on this machine" % name)
        team = {"name": name, "id": uuid.uuid4().hex, "created_at": time.time(),
                "created_by": creator, "lead": None, "members": [creator], "generation": 0}
        _log(team, "create", me, creator, None)
        paths.write_json(path, team)
    return team


def require(name: str) -> dict:
    team = load(check_name(name))
    if not team:
        raise TeamError("no team %s on this machine" % name)
    return team


def add_rule(me: dict, team: dict, target: dict) -> str:
    """What adding `target` needs: "lead" (the lead of the same project may),
    or "user" (the user's approval). Refuses a non-member."""
    if not is_member(team, me):
        raise TeamError("only a member of %s can add to it" % team["name"])
    if is_member(team, target):
        raise TeamError("%s is already in %s" % (label(member_of(target)), team["name"]))
    if target.get("remote") or target.get("machine") and not target.get("home"):
        return "user"
    from . import config
    scope, _ = config.scope_for(me, target, team_aware=False)
    return "lead" if scope and is_lead(team, me) else "user"


def add(me: dict, name: str, target: dict, approval: str) -> dict:
    """Apply an add the caller has cleared with add_rule (`approval` is "lead",
    or the user's verdict text)."""
    member = member_of(target)
    with _locked(check_name(name)) as path:
        team = paths.read_json(path)
        if not team:
            raise TeamError("no team %s on this machine" % name)
        if not is_member(team, me):
            raise TeamError("only a member of %s can add to it" % name)
        if any(_same(m, member) for m in team["members"]):
            return team
        team["members"].append(member)
        _log(team, "add", me, member, approval)
        paths.write_json(path, team)
    return team


def remove(me: dict, name: str, member_spec: dict, approval: str | None) -> dict:
    """Remove a member: the member itself, the lead, or on the user's approval.
    A pair made by connect also loses the selection it was made from."""
    with _locked(check_name(name)) as path:
        team = paths.read_json(path)
        if not team:
            raise TeamError("no team %s on this machine" % name)
        kept = [m for m in team["members"] if not _same(m, member_spec)]
        if len(kept) == len(team["members"]):
            raise TeamError("%s is not in %s" % (label(member_spec), name))
        itself = matches(member_spec, me)
        if not (itself or is_lead(team, me) or approval):
            raise TeamError("removing another member is the lead's or your user's decision")
        team["members"] = kept
        if team.get("lead") and _same(team["lead"], member_spec):
            team["lead"] = None
        _log(team, "leave" if itself else "remove", me, member_spec, approval)
        paths.write_json(path, team)
    if team.get("pair"):
        from . import collaboration
        collaboration.drop_id(team["pair"]["collaboration"])
    return team


# --- connect: a pair is a team of two (ADR-0025 decision 13) --------------------------

def pair_name(collaboration_id: str) -> str:
    return "pair-" + collaboration_id[:10]


def make_pair(sender: dict, target: dict, collaboration: dict) -> dict:
    """The two-member team a connect makes. Members are the two selected
    conversations themselves (connect selects a conversation, not a name).
    Idempotent: an existing pair team for the same selection is returned."""
    name = pair_name(collaboration["id"])
    members = [member_of(sender, by_conversation=True), member_of(target, by_conversation=True)]
    with _locked(name) as path:
        team = paths.read_json(path)
        if team and (team.get("pair") or {}).get("collaboration") == collaboration["id"] \
                and len(team.get("members", [])) == 2:
            return team
        team = {"name": name, "id": uuid.uuid4().hex, "created_at": time.time(),
                "created_by": members[0], "lead": None, "members": members, "generation": 0,
                "pair": {"collaboration": collaboration["id"]}}
        _log(team, "connect", sender, members[1], collaboration.get("verdict"))
        paths.write_json(path, team)
    return team


def adopt_pairs() -> int:
    """Show the selections made before 0.5.1 as pair teams. Their permission
    already holds through the selection itself; this only lists them."""
    from . import collaboration
    made = 0
    try:
        files = os.listdir(paths.path(collaboration.DIRECTORY))
    except OSError:
        return 0
    for fname in files:
        if not fname.endswith(".json"):
            continue
        record = paths.read_json(paths.path(collaboration.DIRECTORY, fname))
        if not isinstance(record, dict) or record.get("active") is not True or load(pair_name(record.get("id", ""))):
            continue
        ends = record.get("endpoints") or []
        if len(ends) != 2:
            continue
        try:
            make_pair(ends[0], ends[1], record)
            made += 1
        except (TeamError, KeyError, TypeError, ValueError):
            continue
    return made


def set_lead(me: dict, name: str, member_spec: dict | None, approval: str) -> dict:
    """Name (or clear, with None) the lead. Always the user's decision (D5)."""
    if not approval:
        raise TeamError("naming the lead is your user's decision")
    with _locked(check_name(name)) as path:
        team = paths.read_json(path)
        if not team:
            raise TeamError("no team %s on this machine" % name)
        if member_spec is not None and not any(_same(m, member_spec) for m in team["members"]):
            raise TeamError("%s is not in %s" % (label(member_spec), name))
        team["lead"] = member_spec
        _log(team, "lead" if member_spec else "no-lead", me, member_spec, approval)
        paths.write_json(path, team)
    return team


def find_member(team: dict, word: str) -> dict:
    """A member by what a person or agent calls it: its name, name@alias, its
    label, or a live session's ref."""
    word = (word or "").strip()
    hits = []
    for m in team.get("members", []):
        rec = live_session(m)
        names = {m.get("name"), label(m), m.get("session_id"),
                 rec.get("ref") if rec else None, ("ref:" + rec["ref"]) if rec and rec.get("ref") else None}
        if word in names:
            hits.append(m)
    if len(hits) != 1:
        raise TeamError("%s in %s: %s" % (word, team["name"],
                                          "no such member" if not hits else "more than one member matches"))
    return hits[0]


# --- addresses and notifications -----------------------------------------------------

def is_address(spec: str) -> bool:
    return isinstance(spec, str) and spec.strip().startswith(ADDRESS_PREFIXES)


def team_name(spec: str) -> str:
    spec = spec.strip()
    return check_name(spec[5:] if spec.startswith("team:") else spec[1:])


def expand(specs: list, sender: dict) -> tuple:
    """Replace each team address by its members' current addresses. Returns
    (specs, notes): notes name the members that are not running, and a team
    the sender is not in is refused (D19: being in a team is the permission)."""
    out, notes = [], []
    for spec in specs:
        if not is_address(spec):
            out.append(spec)
            continue
        team = require(team_name(spec))
        if not is_member(team, sender):
            raise TeamError("you are not in team %s" % team["name"])
        for m in team["members"]:
            if matches(m, sender):
                continue
            target = address(m)
            if target:
                out.append(target)
            else:
                notes.append("%s in %s is not running; it was not sent" % (label(m), team["name"]))
    return out, notes


def _mute_file(name: str, record: dict) -> str:
    key = "%s-%s" % (record.get("runtime"), record.get("session_id"))
    return os.path.join(folder(name), "muted", re.sub(r"[^A-Za-z0-9_.-]", "_", key))


def mute(name: str, record: dict, on: bool = True) -> None:
    require(name)
    path = _mute_file(name, record)
    if on:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(str(time.time()))
    else:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def muted(name: str, record: dict) -> bool:
    try:
        return os.path.exists(_mute_file(name, record))
    except TeamError:
        return False
