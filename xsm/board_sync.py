"""A team board across machines (ADR-0026 decision 2, ADR-0025 D22).

Board nodes are immutable files named by the hash of what they say, so two
machines merge them by copying the ones they lack: nothing to lock, no write to
overwrite. The machine that adds a node sends it to the machines of the team's
remote members. A machine takes a node only from a member machine of the same
team (same team id), only when the id matches the node's content, and never
replaces a node it has; then it renders its board.

`publish` pushes the given nodes; `sync` pushes all of them, for a machine that
was offline. There is no pull: a machine catches up when another sends.
"""
from __future__ import annotations

import os

from . import doc, teams


def _remote(team: dict) -> bool:
    return any(m.get("machine") for m in team.get("members", []))


def publish(team: dict, nodes: list) -> list:
    """Send nodes to the team's other machines. Returns notes to show."""
    from . import network
    if not nodes or not _remote(team):
        return []
    payload = [{"id": n["id"], "text": doc._serialize(n)} for n in nodes]
    try:
        result = network.call({"op": "board-publish", "team": team["name"], "team_id": team["id"],
                               "machines": sorted({m["machine"] for m in team["members"] if m.get("machine")}),
                               "nodes": payload}, timeout=30)
    except network.NetworkError as exc:
        return ["the board change was not sent to the team's other machines (%s); "
                "`xsm board sync %s` sends every node again" % (exc, team["name"])]
    return ["board %s not updated on machine %s: %s" % (team["name"], f["machine"][:8], f["code"])
            for f in result.get("failed", [])]


def sync(team: dict) -> list:
    from . import board
    return publish(team, doc.read(board.path(team["name"])))


def receive(origin: str, team_name: str, team_id: str, nodes: list) -> dict:
    """Take board nodes another machine sent. Returns {"taken", "kept", "refused"}."""
    from . import board
    team = teams.load(teams.check_name(team_name))
    if not team or team.get("id") != team_id:
        raise ValueError("no such team here")
    if not any(m.get("machine") == origin for m in team.get("members", [])) \
            and team.get("origin") != origin:
        raise ValueError("the sending machine has no member in this team")
    if not isinstance(nodes, list):
        raise ValueError("invalid nodes")
    target = board.path(team["name"])
    os.makedirs(doc.nodes_dir(target), exist_ok=True)
    taken = kept = refused = 0
    for item in nodes:
        try:
            node = doc._parse(item["text"])
            if node.get("id") != item["id"] or doc.node_digest(node) != node["id"]:
                refused += 1
                continue
            fd = os.open(os.path.join(doc.nodes_dir(target), node["id"] + ".md"),
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            kept += 1
            continue
        except (KeyError, TypeError, doc.DocError):
            refused += 1
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(item["text"])
        taken += 1
    if taken:
        board.render(team["name"])
    return {"taken": taken, "kept": kept, "refused": refused}
