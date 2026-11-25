"""The connections a handover copies to the successor (state-model spec D1, F4).

A session that is handed over keeps its old conversation partners only as far as
the successor shares a scope with them: a team moves with the seat
(handover._teams), but a reach, the folder the old session sat in, a folder
linked to it, and a worker or parent relation do not. A late answer from such a
partner to a question the old session asked was then refused at send, because
nothing connected it to the successor.

`plan` lists, before anything moves, what the successor would get; the person
sees the list in the approval and `apply` makes exactly that list, each copy on
its own: one that fails (a folder that is gone) is skipped and listed, and the
handover goes on. The successor gets what the old session had and no more: a
reach to a folder the old session reached or sat in or had linked, a pair team
with a worker or the parent of the old session. The old session's own
connections stay as they are, and a worker's parent is not changed.

Result rows are {kind, what, ok, why?}; kinds: reach, folder, link, worker, parent.
"""
from __future__ import annotations

import json
import os

from . import paths

KINDS = ("reach", "folder", "link", "worker", "parent")


def _identity(record: dict) -> dict:
    from . import handoff
    return handoff._identity(record)


def _has_scope(target: dict, folder: str) -> bool:
    """Whether `target` already talks with the sessions of `folder`: a default
    project, a link or a reach of its own. A named stand-in for a session in
    the folder carries only its place."""
    from . import config
    try:
        return bool(config.scope_for(target, {"cwd": folder}, team_aware=False)[0])
    except (ValueError, OSError):
        return False


def _running(ref: str | None) -> dict | None:
    """The one running local session with this ref, or None (none, or two)."""
    if not ref:
        return None
    from . import registry
    found = [r for r in registry.records() if r.get("ref") == ref
             and r.get("state") in ("live", "unknown") and not r.get("ended_at")]
    return found[0] if len(found) == 1 else None


def _peer(record: dict) -> dict:
    return {k: record.get(k) for k in ("runtime", "home", "session_id", "ref", "name", "alias")}


def _relations(me: dict) -> list:
    """The sessions `me` started as workers, and the one that started it."""
    from . import delegation, registry, workers
    found = {}

    def note(kind: str, record: dict | None) -> None:
        if record and record.get("session_id"):
            found.setdefault((record.get("runtime"), record.get("home"), record["session_id"]), (kind, record))

    for w in workers.all_workers():
        if w.get("parent_ref") == me.get("ref") and w.get("ref"):
            note("worker", _running(w["ref"]))
        if w.get("ref") == me.get("ref") and w.get("parent_ref"):
            note("parent", _running(w["parent_ref"]))
    owner = delegation.parent(me)
    if owner and owner.get("state") not in ("ended", "stale", "needs-relink"):
        note("parent", owner)
    try:
        names = os.listdir(paths.path("worker-links"))
    except OSError:
        names = []
    mine = delegation.key(me)
    for name in sorted(names):
        value = paths.read_json(paths.path("worker-links", name)) if name.endswith(".json") else None
        try:
            if value and delegation.key(value["parent"]) == mine:
                child = value["child"]
                note("worker", registry.by_session(child["runtime"], child["session_id"], home=child["home"]))
        except (KeyError, TypeError):
            continue
    return [(kind, rec) for kind, rec in found.values()
            if rec.get("state") not in ("ended", "stale") and not rec.get("ended_at")]


def plan(me: dict, target: dict) -> dict:
    """What `target` would be given. Pure: nothing is written."""
    from . import config
    links, seen = [], set()

    def add(kind: str, what: str, **more) -> None:
        if (kind, what) not in seen:
            seen.add((kind, what))
            links.append(dict({"kind": kind, "what": what}, **more))

    for r in config.reaches():
        if config.reach_holds(r, me) and r.get("root") and not _has_scope(target, r["root"]):
            add("reach", r["root"])
    if me.get("cwd"):
        root = config.project_root(me["cwd"])
        if not _has_scope(target, root):
            add("folder", root)
        for mine, other in config.links_covering(root):
            if not _has_scope(target, other):
                add("link", other, via=mine)
    me_id, target_id = _identity(me), _identity(target)
    for kind, rec in _relations(me):
        if _identity(rec) in (me_id, target_id) or config.scope_for(target, rec)[0]:
            continue
        add(kind, rec.get("ref") or rec["session_id"], peer=_peer(rec))
    return {"from": me_id, "target": target_id, "links": links}


def describe(plan: dict | None) -> list:
    """One line per copy, for the approval and the letter."""
    out = []
    for item in (plan or {}).get("links") or []:
        what, kind = item["what"], item["kind"]
        name = (item.get("peer") or {}).get("name")
        if kind == "reach":
            out.append("a reach to %s, as the old session has" % what)
        elif kind == "folder":
            out.append("a reach to %s, the folder the old session works in" % what)
        elif kind == "link":
            out.append("a reach to %s, a folder linked to the old session's" % what)
        elif kind == "worker":
            out.append("a pair team with %s [%s], a worker the old session started (it stays its parent)"
                       % (name or "worker", what))
        else:
            out.append("a pair team with %s [%s], the session that started the old session"
                       % (name or "parent", what))
    return out


def _copy(target: dict, item: dict, approval: str, note: str) -> dict:
    from . import collaboration, config, registry, teams
    kind, what = item["kind"], item["what"]
    if kind in ("reach", "folder", "link"):
        _entry, added = config.add_reach(target["ref"], what, note, session=target)
        return {"added": added}
    peer = item.get("peer") or {}
    now = registry.by_session(peer.get("runtime"), peer.get("session_id"), home=peer.get("home"))
    if not now or now.get("state") in ("ended", "stale") or now.get("ended_at"):
        raise ValueError("%s is not running" % (peer.get("name") or what))
    if config.scope_for(target, now)[0]:
        return {"added": False}
    pair = teams.make_pair(target, now, collaboration.create(target, now, approval))
    return {"added": True, "team": pair["name"]}


def apply(target: dict, plan: dict | None, approval: str, old: str = "the old session") -> list:
    """Make the planned copies. Each copy stands alone: a failure is a row with
    ok false and its reason, never an exception."""
    from . import registry
    target = registry.by_session(target["runtime"], target["session_id"], home=target["home"]) or target
    rows = []
    for item in (plan or {}).get("links") or []:
        row = {"kind": item["kind"], "what": item["what"], "ok": True}
        if item.get("peer", {}).get("name"):
            row["name"] = item["peer"]["name"]
        try:
            done = _copy(target, item, approval, "handover from %s" % old)
            if not done["added"]:
                row["why"] = "already connected"
            if done.get("team"):
                row["team"] = done["team"]
        except Exception as exc:          # one copy failing must not stop the handover (spec 0, 6)
            row.update(ok=False, why=str(exc) or exc.__class__.__name__)
        rows.append(row)
    return rows


def lines(rows: list) -> list:
    """The rows as letter lines."""
    out = []
    for row in rows or []:
        tail = "" if row.get("ok") and not row.get("why") else " (%s)" % row.get("why")
        out.append("%s %s %s%s" % ("copied:" if row.get("ok") else "not copied:", row["kind"], row["what"], tail))
    return out


def dumps(rows: list) -> str:
    return json.dumps(rows, default=str, sort_keys=True)
