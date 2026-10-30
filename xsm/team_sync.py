"""Teams across machines (ADR-0025 decision 14, D22).

A team with members on other machines is kept on each of those machines as the
same record. The machine that changes a team sends the whole record, as P2P
endpoints, to every other member machine over the network service; a machine
takes it when the sender is an active member machine of the network, the team
id matches (or is new here) and the generation is newer (a tie goes to the
larger machine key). Its own endpoints are turned back into local name members.

This is the equal-members model of ADR-0021: a member machine's statement is a
member's testimony, not this user's approval, and a hostile member is not
contained. Concurrent changes on two machines are not merged: the newer
generation wins.

A local name member (D26) travels as the endpoint of its session running now.
A member that is not running travels by name only and cannot be matched on the
other machine until it runs and the team is published again; a team send
publishes first when the team has remote members.
"""
from __future__ import annotations

import copy
import hashlib

from . import paths, teams

FIELDS = ("name", "id", "generation", "lead", "members", "created_at", "updated_at")


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
    """Take a team record a member machine sent. Returns {"status": ...}."""
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
    record = {k: copy.deepcopy(incoming.get(k)) for k in FIELDS}
    record["members"] = [m for m in local if m is not None]
    record["lead"] = _back_to_local(incoming.get("lead"), own_machine) if incoming.get("lead") else None
    record["origin"] = origin
    with teams._locked(name) as path:
        current = paths.read_json(path)
        if current and current.get("id") != record["id"]:
            return {"status": "conflict", "reason": "a different team %s exists on this machine" % name}
        if current:
            newer = (record["generation"], origin) > (int(current.get("generation", 0)), current.get("origin") or "")
            if not newer:
                return {"status": "stale"}
            record["log"] = list(current.get("log") or [])
        record["log"] = list(record.get("log") or []) + [{"action": "received", "from": origin[:8],
                                                         "generation": record["generation"]}]
        paths.write_json(path, record)
    return {"status": "updated"}


def _back_to_local(member, own_machine):
    """This machine's endpoint becomes its local name member when the session
    is registered here; other machines' endpoints stay as they are."""
    if not isinstance(member, dict):
        return None
    if member.get("machine") != own_machine:
        return {k: member.get(k) for k in ("machine", "runtime", "home_id", "session_id", "name")}
    from . import registry
    rec = registry.by_session(member.get("runtime") or "", member.get("session_id") or "") \
        if member.get("session_id") else None
    if rec and rec.get("home") and rec.get("name"):
        return teams.member_of(rec)
    return None
