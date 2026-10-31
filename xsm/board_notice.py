"""Telling a member its team's board changed (ADR-0026 decision 6, D23).

A team DM wakes its members at once; a board change does not. The next prompt
of each member gets one line per team whose board has nodes or decisions the
member has not read: which items changed and how many decisions, never the
text. Reading the board (`xsm board show|log|decisions`, xsm_board) is what
moves the member's read position; writing an item or recording a decision
counts as reading what one wrote.

A line is shown once per change: a member that does not read the board is not
told again every turn, only when something new arrives, and then the line
counts everything still unread. A member can turn the lines off per team
(`xsm board mute <team>`).

The position is kept per session, like a team DM's mute: a new session of the
same member starts unread and is told once what the board holds.

What the hook pays each turn: the team files, one directory listing of each
member team's nodes and decisions, and a parse of only the unread nodes, at
most PARSE_LIMIT of them.
"""
from __future__ import annotations

import os
import re

from . import paths, teams

PARSE_LIMIT = 200       # unread nodes parsed per team per turn
TEAM_LIMIT = 5          # teams with a line per turn
ITEM_NAMES = 3          # items named in a line
LINE_LIMIT = 240        # characters in one line


def _key(record: dict) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", "%s-%s" % (record.get("runtime"), record.get("session_id")))


def _state_file(team: str, record: dict) -> str:
    return os.path.join(teams.folder(team), "seen", _key(record) + ".json")


def _load(team: str, record: dict) -> dict:
    state = paths.read_json(_state_file(team, record)) or {}
    return {k: set(state.get(k) or []) for k in ("read", "notified", "decisions_read", "decisions_notified")} \
        | {"muted": bool(state.get("muted"))}


def _save(team: str, record: dict, state: dict) -> None:
    paths.write_json(_state_file(team, record),
                     {k: sorted(v) if isinstance(v, set) else v for k, v in state.items()})


def _node_ids(team: str) -> list:
    from . import board, doc
    try:
        return [n[:-3] for n in os.listdir(doc.nodes_dir(board.path(team))) if n.endswith(".md")]
    except OSError:
        return []


def _decision_ids(team: str) -> list:
    from . import board
    try:
        return [n[:-5] for n in os.listdir(board.decisions_dir(team)) if n.endswith(".json")]
    except OSError:
        return []


def read_ids(record: dict, team: str) -> set:
    """The nodes of a board this session has read or written."""
    return _load(team, record)["read"]


def mark_read(record: dict, team: str, nodes=None, decisions=None) -> None:
    """Move the read position: all of the board (nodes and decisions None),
    or only the ids given (what this member wrote itself)."""
    if not record or not record.get("session_id"):
        return
    state = _load(team, record)
    state["read"] |= set(_node_ids(team) if nodes is None and decisions is None else nodes or [])
    state["decisions_read"] |= set(_decision_ids(team) if nodes is None and decisions is None
                                   else decisions or [])
    _save(team, record, state)


def mute(record: dict, team: str, on: bool = True) -> None:
    state = _load(team, record)
    state["muted"] = on
    _save(team, record, state)


def muted(record: dict, team: str) -> bool:
    return _load(team, record)["muted"]


def _line(team: str, items: list, unparsed: int, decisions: int) -> str:
    parts = []
    if items or unparsed:
        names = ", ".join(items[:ITEM_NAMES])
        more = len(items) - ITEM_NAMES
        count = max(len(items), 1)
        what = "%d%s item%s changed" % (count, "+" if unparsed else "",
                                        "" if count == 1 and not unparsed else "s")
        parts.append(what + (" (%s%s)" % (names, ", +%d more" % more if more > 0 else "") if names else ""))
    if decisions:
        parts.append("%d decision%s recorded" % (decisions, "" if decisions == 1 else "s"))
    line = "board %s: %s. Read it with `xsm board show %s` (xsm_board)." % (team, "; ".join(parts), team)
    return line if len(line) <= LINE_LIMIT else line[:LINE_LIMIT - 1] + "…"


def notice(record: dict | None) -> str | None:
    """The lines for this session's next prompt, or None. Marks what it told."""
    if not record or not record.get("session_id"):
        return None
    from . import board, doc
    lines, extra = [], 0
    for team in teams.teams_of(record):
        name = team["name"]
        state = _load(name, record)
        if state["muted"]:
            continue
        unread = [i for i in _node_ids(name) if i not in state["read"]]
        unread_decisions = [i for i in _decision_ids(name) if i not in state["decisions_read"]]
        new = [i for i in unread if i not in state["notified"]] + \
            [i for i in unread_decisions if i not in state["decisions_notified"]]
        if not new:
            continue
        if len(lines) >= TEAM_LIMIT:
            extra += 1
            continue
        seen_at, unparsed = {}, 0
        folder = doc.nodes_dir(board.path(name))
        for i, ident in enumerate(sorted(unread)):
            if i >= PARSE_LIMIT:
                unparsed += 1
                continue
            try:
                with open(os.path.join(folder, ident + ".md"), encoding="utf-8") as fh:
                    node = doc._parse(fh.read())
            except (OSError, doc.DocError):
                continue
            if node.get("item"):
                key = (node.get("t", ""), node["item"])
                seen_at[node["item"]] = min(seen_at.get(node["item"], key), key)
        items = [item for _, item in sorted(seen_at.values())]     # the board's own order
        if not items and not unparsed and not unread_decisions:
            # Only nodes that are no item (not a board write): nothing to say.
            state["notified"] |= set(unread)
            _save(name, record, state)
            continue
        lines.append(_line(name, items, unparsed, len(unread_decisions)))
        state["notified"] |= set(unread)
        state["decisions_notified"] |= set(unread_decisions)
        _save(name, record, state)
    if not lines:
        return None
    if extra:
        lines.append("and %d more team board%s changed (`xsm team list`)." % (extra, "" if extra == 1 else "s"))
    return "[xsm] " + "\n[xsm] ".join(lines)
