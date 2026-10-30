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
    """item -> its nodes, in the order the items first appeared."""
    out = {}
    for n in nodes:
        if n.get("item"):
            out.setdefault(n["item"], []).append(n)
    return out


def heads(item_nodes: list) -> list:
    """The nodes of one item that no later node of the same item builds on:
    one when the item is settled, several when members wrote at once."""
    built_on = {p for n in item_nodes for p in n["parents"]}
    return [n for n in item_nodes if n["id"] not in built_on]


def current(team: str) -> dict:
    """item -> its head nodes now."""
    return {item: heads(ns) for item, ns in items(doc.read(path(team))).items()}


# --- render and direct edits ------------------------------------------------------------

def _footer(n: dict) -> str:
    extra = []
    if n.get("decision"):
        extra.append("decision %s" % n["decision"])
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
            out += [hs[0]["body"].rstrip(), "", _footer(hs[0])]
            continue
        out += ["_%d %s_" % (len(hs), CONFLICT)]
        for i, n in enumerate(hs, 1):
            out += ["", "### version %d" % i, "", n["body"].rstrip(), "", _footer(n)]
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
    from . import board_sync
    node["sync_notes"] = board_sync.publish(team, [node])
    return node


def show(me: dict, team_name: str) -> str:
    team = _require_member(me, team_name)
    return render(team["name"])


def log(me: dict, team_name: str, item: str | None = None) -> list:
    team = _require_member(me, team_name)
    nodes = doc.read(path(team["name"]))
    return [n for n in nodes if item is None or n.get("item") == item]


def changed_since(team: str, since_ids: set) -> dict:
    """item -> number of nodes not in since_ids (what a member has not seen)."""
    out = {}
    for n in doc.read(path(team)):
        if n.get("item") and n["id"] not in since_ids:
            out[n["item"]] = out.get(n["item"], 0) + 1
    return out
