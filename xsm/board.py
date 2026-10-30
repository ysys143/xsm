"""A team's board, owned by xsm doc (ADR-0026 decisions 1-5).

The board is what is true for the team now: decisions in force, who owns what,
progress. Members write it as immutable doc nodes, each about one item; the
rendered BOARD.md shows the newest node of every item, and two nodes written on
the same item at once are both shown, not one over the other. The history is the
nodes themselves.

- It lives at the team's common path (~/.xsm/teams/<team>/), so worktrees never
  see different boards (D29).
- Only members read or write it (a team is the permission, ADR-0025).
- A direct edit of BOARD.md is not lost: the next render finds the rendered
  file changed and takes every changed item as a node marked as a file edit,
  before writing the file again. Agents and people both write the board, and
  whichever tool made a change, it survives.
- New nodes go to the machines of the team's remote members (board_sync).
"""
from __future__ import annotations

import hashlib
import json
import os
import re

from . import doc, teams

FILE = "BOARD.md"
HEADER = ("<!-- xsm board for team %s: rendered from its nodes. Change it with `xsm board set "
          "%s <item> --text ...` (or xsm_board); a direct edit here is taken as a node at the "
          "next render. -->")
CONFLICT = "versions at once; agree which stands and set it"
FOOTER_RE = re.compile(r"^_by .* · node ([0-9a-f]{12})(?: · .*)?_$")


class BoardError(ValueError):
    pass


def path(team: str) -> str:
    return os.path.join(teams.folder(team), FILE)


def _stamp_file(team: str) -> str:
    return doc.nodes_dir(path(team)) + "/.rendered"


def _require_member(me: dict, team_name: str) -> dict:
    try:
        team = teams.require(team_name)
    except teams.TeamError as exc:
        raise BoardError(str(exc))
    if not teams.is_member(team, me):
        raise BoardError("only a member of team %s reads or writes its board" % team["name"])
    return team


# --- the items ------------------------------------------------------------------

def items(nodes: list) -> dict:
    """item -> its nodes, items in the order they first appeared (node times
    are to the second, so items begun in the same second go by name)."""
    out = {}
    for n in nodes:
        if n.get("item"):
            out.setdefault(n["item"], []).append(n)
    return dict(sorted(out.items(), key=lambda kv: (kv[1][0].get("t", ""), kv[0])))


def heads(item_nodes: list) -> list:
    """The nodes of one item that no later node of the same item builds on:
    one when the item is settled, several when members wrote at once."""
    built_on = {p for n in item_nodes for p in n["parents"]}
    return [n for n in item_nodes if n["id"] not in built_on]


def current(team: str) -> dict:
    """item -> its head nodes now."""
    return {item: heads(ns) for item, ns in items(doc.read(path(team))).items()}


# --- render and direct edits ------------------------------------------------------------

def _footer(n: dict, team: str | None = None) -> str:
    extra = []
    if n.get("decision"):
        rec = load_decision(team, n["decision"]) if team else None
        if rec:
            where = (" on machine %s" % rec["from_machine"][:8]) if rec.get("from_machine") else ""
            extra.append("decided%s by %s: %s -> %s" % (where, rec.get("decided_by", "the user"),
                                                        rec.get("question"), rec.get("answer")))
        else:
            # A node can name a decision id, but only the record makes it one.
            extra.append("decision %s has no record here: not confirmed" % n["decision"])
    if n.get("author_kind") == "file-edit":
        extra.append("taken from a direct edit")
    return "_by %s · %s · node %s%s_" % (n["author"], n["t"], n["id"],
                                         "".join(" · " + e for e in extra))


def render_text(team: str, state: dict | None = None) -> str:
    state = current(team) if state is None else state
    out = [HEADER % (team, team), "", "# %s board" % team]
    if not state:
        out += ["", "_Nothing on the board yet. Add an item with `xsm board set %s <item> "
                "--text ...`._" % team]
    for item, hs in state.items():
        out += ["", "## %s" % item, ""]
        if len(hs) == 1:
            out += [hs[0]["body"].rstrip(), "", _footer(hs[0], team)]
            continue
        out += ["_%d %s_" % (len(hs), CONFLICT)]
        for i, n in enumerate(hs, 1):
            out += ["", "### version %d" % i, "", n["body"].rstrip(), "", _footer(n, team)]
    return "\n".join(out).rstrip() + "\n"


def _sections(text: str) -> dict:
    """item -> (node id the section was rendered from, body) for each settled
    item of a rendered board, as it reads now (possibly edited)."""
    out, item, lines = {}, None, []

    def close():
        if item is None:
            return
        body = [l for l in lines]
        rendered_from = None
        while body and not body[-1].strip():
            body.pop()
        if body and FOOTER_RE.match(body[-1].strip()):
            rendered_from = FOOTER_RE.match(body[-1].strip()).group(1)
            body.pop()
        if any(l.startswith("### version ") or CONFLICT in l for l in lines):
            return                        # a conflicted item is settled with `set`, not an edit
        out[item] = (rendered_from, "\n".join(body).strip())

    for line in text.splitlines():
        if line.startswith("## "):
            close()
            item, lines = line[3:].strip(), []
        elif item is not None:
            lines.append(line)
    close()
    return out


def take_edits(team: str) -> list:
    """Nodes for the items a direct edit of BOARD.md changed or added since the
    last render. Returns the nodes added."""
    p = path(team)
    try:
        with open(p, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return []
    try:
        with open(_stamp_file(team), encoding="utf-8") as fh:
            stamp = fh.read().strip()
    except OSError:
        stamp = None
    if stamp == hashlib.sha256(text.encode()).hexdigest():
        return []
    state = current(team)
    added = []
    for item, (rendered_from, body) in _sections(text).items():
        if not body or not doc.ITEM_RE.match(item):
            continue
        hs = state.get(item, [])
        if len(hs) == 1 and hs[0]["body"].strip() == body:
            continue
        if len(hs) > 1:
            continue
        parents = [hs[0]["id"]] if len(hs) == 1 else []
        added.append(doc.add(p, {"kind": "file-edit", "name": "a direct edit of BOARD.md"},
                             body, ["update"], parents, item=item))
    return added


def render(team: str) -> str:
    """Take any direct edit as nodes, then write BOARD.md from the nodes."""
    take_edits(team)
    text = render_text(team)
    p = path(team)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, p)
    os.makedirs(doc.nodes_dir(p), exist_ok=True)
    with open(_stamp_file(team), "w", encoding="utf-8") as fh:
        fh.write(hashlib.sha256(text.encode()).hexdigest())
    return text


# --- what members do ------------------------------------------------------------------

def author(me: dict) -> dict:
    """Who wrote a node: the person at this terminal, or the registered session."""
    from . import workers
    if workers.human_terminal():
        return {"kind": "human", "name": os.environ.get("USER") or "person"}
    return {"kind": "agent", "name": me.get("name"), "alias": me.get("alias"), "ref": me.get("ref")}


def set_item(me: dict, team_name: str, item: str, text: str, tag: str | None = None,
             decision: str | None = None) -> dict:
    """Write an item: a new node that builds on the item's current version(s),
    so setting an item also settles a conflict on it."""
    team = _require_member(me, team_name)
    item = (item or "").strip()
    take_edits(team["name"])
    hs = current(team["name"]).get(item, [])
    try:
        node = doc.add(path(team["name"]), author(me), text, [tag] if tag else ["update"],
                       [n["id"] for n in hs], item=item, decision=decision)
    except doc.DocError as exc:
        raise BoardError(str(exc))
    render(team["name"])
    from . import board_notice, board_sync
    board_notice.mark_read(me, team["name"], nodes=[node["id"]])
    node["sync_notes"] = board_sync.publish(team, [node])
    return node


def show(me: dict, team_name: str) -> str:
    from . import board_notice
    team = _require_member(me, team_name)
    text = render(team["name"])
    board_notice.mark_read(me, team["name"])
    return text


def log(me: dict, team_name: str, item: str | None = None) -> list:
    from . import board_notice
    team = _require_member(me, team_name)
    nodes = doc.read(path(team["name"]))
    board_notice.mark_read(me, team["name"])
    return [n for n in nodes if item is None or n.get("item") == item]


def changed_since(team: str, since_ids: set) -> dict:
    """item -> number of nodes not in since_ids (what a member has not seen)."""
    out = {}
    for n in doc.read(path(team)):
        if n.get("item") and n["id"] not in since_ids:
            out[n["item"]] = out.get(n["item"], 0) + 1
    return out


# --- decisions beside the board (ADR-0026 decision 7) ------------------------------------

def decisions_dir(team: str) -> str:
    return os.path.join(teams.folder(team), "decisions")


def decision_id(record: dict) -> str:
    body = {k: record.get(k) for k in ("t", "team", "question", "answer", "options", "decided_by",
                                       "via", "asked_by", "item")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def load_decision(team: str, ident: str) -> dict | None:
    if not isinstance(ident, str) or not re.fullmatch(r"[0-9a-f]{12}", ident):
        return None
    try:
        with open(os.path.join(decisions_dir(team), ident + ".json"), encoding="utf-8") as fh:
            rec = json.load(fh)
    except (OSError, ValueError):
        return None
    return rec if isinstance(rec, dict) and decision_id(rec) == ident else None


def decisions(team: str) -> list:
    try:
        names = sorted(os.listdir(decisions_dir(team)))
    except OSError:
        return []
    out = [load_decision(team, n[:-5]) for n in names if n.endswith(".json")]
    return sorted([r for r in out if r], key=lambda r: r.get("t", 0))


def _write_decision(team: str, record: dict) -> bool:
    """Write a decision record once; never replace one. Returns whether written."""
    os.makedirs(decisions_dir(team), mode=0o700, exist_ok=True)
    try:
        fd = os.open(os.path.join(decisions_dir(team), record["id"] + ".json"),
                     os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=1)
    return True


def record_decision(me: dict, team_name: str, question: str, answer: str, *, via: str,
                    options=None, item: str | None = None, summary: str | None = None) -> dict:
    """Keep the user's answer beside the board and, with an item, set that item
    to it. Only the two places that hold the user's own answer call this: the
    xsm_decide form and a person at this terminal (`xsm board decide`)."""
    import time
    from . import workers
    if me is None:
        if via != "terminal" or not workers.human_terminal():
            raise BoardError("without a session, only the person themselves records a decision")
        try:
            team = teams.require(team_name)
        except teams.TeamError as exc:
            raise BoardError(str(exc))
    else:
        team = _require_member(me, team_name)
    if via not in ("mcp-elicitation", "terminal"):
        raise BoardError("a decision is your user's own answer, from the form or the terminal")
    record = {"t": time.time(), "team": team["name"], "question": question, "answer": answer,
              "options": list(options) if options else None,
              "decided_by": "%s (person via %s)" % (os.environ.get("USER") or "person", via),
              "via": via, "asked_by": (me or {}).get("ref"), "item": item}
    record["id"] = decision_id(record)
    _write_decision(team["name"], record)
    node = None
    if item:
        hs = current(team["name"]).get(item, [])
        text = "%s: %s" % (summary, answer) if summary else "%s -> %s" % (question, answer)
        try:
            node = doc.add(path(team["name"]), {"kind": "human", "name": os.environ.get("USER") or "person",
                                                "via": via}, text, ["update"], [n["id"] for n in hs],
                           item=item, decision=record["id"])
        except doc.DocError as exc:
            raise BoardError(str(exc))
    render(team["name"])
    from . import board_notice, board_sync
    if me is not None:
        board_notice.mark_read(me, team["name"], nodes=[node["id"]] if node else [],
                               decisions=[record["id"]])
    record["sync_notes"] = board_sync.publish(team, [node] if node else [], decisions=[record])
    record["node"] = node["id"] if node else None
    return record
