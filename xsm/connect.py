"""One yes connects two folders and sends the message that was refused for the
lack of it.

A send to a session outside this one's scope was refused with advice: the agent
asked its user, ran `xsm link`, and sent again, three steps, and a forgotten one
meant a message that never went (2026-10-01). User decision: "응 한 번에 연결하고
재전송까지 되게 해": one yes from the person connects and delivers.

The refused message is kept (outbox.py) and the connection it needs is asked
for through the ordinary consent machinery (consent.take_or_request), keyed
exactly as the command that makes the connection keys it (`xsm link`, `join`,
`reach`), so the person's reply is the verdict of the same ask. The agent asks,
runs the same send again (it shows the reply, and does nothing else), and once
more on a yes: that run connects, as the command would, and then sends.

Fail open: where the reply cannot be kept (a worker, no registered session, a
state folder that cannot be written) or the message cannot be, the send is
refused as it was, with the advice, and nothing is promised. A message is never
dropped silently: it is either sent, or held and named, or refused in words.
"""
from __future__ import annotations

import os
from collections import namedtuple

import hashlib

from . import config, consent, envelope, outbox, paths, policy

# go: connected, so send now (`notes` say what was done); else `text` is the
# refusal, for a message held as `id`.
Step = namedtuple("Step", "go text id notes", defaults=((),))


def _tilde(path: str) -> str:
    home = os.path.expanduser("~")
    return path.replace(home, "~", 1) if path.startswith(home) else path


def _broad(root: str) -> bool:
    """The home directory, a folder above it, or `/`: a link there would open
    every session the person has."""
    home = os.path.realpath(os.path.expanduser("~"))
    return home == root or home.startswith(root.rstrip("/") + "/")


def _plan_digest(plan: dict) -> str:
    """A stable digest of what the person is being asked to allow: the verb, the
    target and the two folders. Together with the target handle it selects the
    immutable consent ask. A changed plan or peer selects a distinct ask, so it
    cannot consume an earlier answer (P02 item 1 and 4)."""
    body = "\x1f".join(str(plan.get(k) or "") for k in
                        ("verb", "target", "here", "cwd")).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def _target_handle(target: dict) -> dict:
    """The exact session the plan is about, as the ask must carry it: a short ref
    alone is not enough to re-check the target before applying (P02 item 1)."""
    return {"ref": target.get("ref"), "runtime": target.get("runtime"),
            "session_id": target.get("session_id"), "home": target.get("home"),
            "alias": target.get("alias"), "pid": target.get("pid"),
            "lstart": target.get("lstart")}


def plan_for(sender: dict, target: dict) -> dict | None:
    """The one connection that would let `sender` talk with `target`, as the
    consent ask is keyed: {verb, target, here, cwd, what}, or None when none can
    be asked for.

    A link between the two project folders is the usual one, what every refusal
    names first. When a folder is so broad that a link would open all of a
    person's sessions, one session's reach is asked for instead. When the target's
    folder is in exactly one named project that the sender's is not, joining it
    is the connection the project already means."""
    if not (sender.get("ref") and sender.get("cwd") and target.get("cwd")):
        return None
    here, there = config.project_root(sender["cwd"]), config.project_root(target["cwd"])
    try:
        config.check_link(here, there)          # both are folders, and not the same
    except ValueError:
        return None
    who = "%s@%s" % (target.get("name"), target.get("alias"))
    plan = {"here": here, "cwd": sender["cwd"], "handle": _target_handle(target)}
    if _broad(here) or _broad(there):
        out = dict(plan, verb="reach", target=there, here=None, what=(
            "letting this session reach the sessions in %s, only for as long as it runs, "
            "so your message to %s can go" % (_tilde(there), who)))
    else:
        new = sorted(config.joined_projects(target) - config.joined_projects(sender))
        if len(new) == 1:
            out = dict(plan, verb="join", target=new[0], here=None, what=(
                "adding %s to project %s, the project of %s (every folder in it can talk, both "
                "ways), so your message to %s can go"
                % (_tilde(here), new[0], _tilde(there), who)))
        else:
            out = dict(plan, verb="link", target=there, what=(
                "connecting %s with %s (a link: the sessions of both folders can talk, both ways, "
                "until `xsm unlink`) so your message to %s can go"
                % (_tilde(here), _tilde(there), who)))
    out["digest"] = _plan_digest(out)
    return out


def run(plan: dict, me: dict, verdict: str) -> str:
    """Make the connection the person agreed to, as `xsm link|join|reach` does;
    the line they print. ValueError when it cannot be made."""
    by = consent.by(verdict)
    if plan["verb"] == "link":
        entry, added = config.add_link(plan["here"], plan["target"], by)
        there = entry["b"] if os.path.realpath(entry["a"]) == plan["here"] else entry["a"]
        return "%s: the sessions in %s and in %s can talk, both ways, until `xsm unlink %s`" % (
            "linked" if added else "already linked", _tilde(plan["here"]), _tilde(there),
            _tilde(there))
    if plan["verb"] == "join":
        _, added = config.join(plan["target"], plan["cwd"])
        return "%s project %s: %s" % ("joined" if added else "already in", plan["target"],
                                      _tilde(config.project_root(plan["cwd"])))
    entry, added = config.add_reach(me["ref"], plan["target"], by, session=me)
    return "%s: %s@%s [%s] can talk with the sessions in %s while it runs" % (
        "allowed" if added else "already allowed", me.get("name"), me.get("alias"), me["ref"],
        _tilde(entry["root"]))


def _typed(plan: dict, me: dict) -> Step | None:
    """A person typed this `xsm send` themselves (a terminal, not an agent's shell):
    that is their own yes, so make the connection the one-yes flow would have asked
    for and send,
    saying what was connected (user decision, 2026-10-01: the one send still
    refused was a person's own). None when it cannot be made, and the send is
    refused with the advice. Policy human_send_connects=false turns it off."""
    verdict = "typed `xsm send` themselves"
    try:
        line = run(plan, me, verdict)
    except ValueError:
        return None
    paths.append_jsonl("decisions.jsonl", {
        "event": "consent", "verb": plan["verb"], "target": plan["target"], "verdict": verdict,
        "by": me.get("name")})
    return Step(True, "", envelope.new_id(), (
        "you typed this send yourself, so xsm is %s" % plan["what"], line))


def offer(sender: dict, target: dict, spec: str, msg: dict, why: str) -> Step | None:
    """The step for a send refused as out of scope (`why` is the reason), or None
    to refuse as before. Every run of the same send lands here: the first holds
    the message and asks, the next shows the person's reply, and the one after a
    yes connects."""
    from . import workers
    human = workers.human_terminal()
    if human and not policy.get("human_send_connects"):
        return None                             # the person running this decides on the spot
    plan = plan_for(sender, target)
    if not plan:
        return None
    if human:
        return _typed(plan, sender)
    already_held = outbox.find(sender, spec, msg)
    held = outbox.put(sender, spec, msg)
    if held is None:
        return None
    msg_id = held["id"]
    applied = []
    try:
        reply, go, kept = consent.take_or_request(
            sender, plan["verb"], plan["target"], plan["here"],
            binding={"digest": plan["digest"], "handle": plan["handle"]},
            apply=lambda verdict: applied.append(run(plan, sender, verdict)))
    except ValueError as exc:
        return Step(False, "your user said yes, but the connection could not be made: %s. "
                           "Your message is held as %s; retry the same send to resume the "
                           "same approved plan." % (exc, msg_id), msg_id)
    if reply is None and not kept:
        if already_held is None:
            outbox.drop(msg_id)
        return None
    if go:
        notes = [consent.approved(plan["verb"], plan["target"], reply, kept, sender.get("name"))]
        return Step(True, "", msg_id, tuple(notes + applied))
    unsent = "Your message is NOT sent: it is held as %s." % msg_id
    if reply is None:
        return Step(False, (
            "out of scope: %s. %s It needs your user's yes to %s. First ask them, %s, whether to "
            "go ahead, and wait for their answer. After they answer, run this same command "
            "again: xsm keeps their latest answer in this session as the verdict, and this run "
            "shows you that reply without acting on it. If it is a yes, run it once more: xsm "
            "connects and sends the message, so there is nothing more to ask. If it is a no or "
            "a question, leave it and answer them: the message stays unsent (kept for a day; "
            "`xsm send --held %s` sends it if they change their mind)." % (
                why.partition("; to connect")[0], unsent, plan["what"],
                consent.how(sender.get("runtime")), msg_id)), msg_id)
    return Step(False, consent.shown_refusal(reply, plan["what"], None) + " " + unsent +
                (" " + kept if isinstance(kept, str) else ""), msg_id)


def _select_network(sender: dict, target: dict) -> dict:
    from . import collaboration, network, network_identity, resolve
    try:
        address = network_identity.target(target)
    except ValueError as exc:
        return {"status": "refused", "reason": str(exc), "handshake": "not-started"}

    def fresh():
        found = resolve.resolve(address, caller=sender)
        if not found.ok:
            raise ValueError(found.reason)
        state = found.record.get("state")
        if isinstance(state, dict):
            state = state.get("value")
        if state in ("ended", "stale") or found.record.get("ended_at"):
            raise ValueError("the selected remote conversation is no longer available")
        if found.record.get("generation") != target.get("generation"):
            raise ValueError("the selected remote conversation generation changed; select it again")
        return found

    def synchronize():
        try:
            reply = network.call({"op": "selection", "caller": sender, "target": address})
        except network.NetworkError as exc:
            raise ValueError(str(exc)) from None
        if reply.get("status") != "selected":
            raise ValueError(reply.get("reason") or "remote selection was not recorded")
        current = fresh()
        if not current.scope:
            raise ValueError("remote selection has no current communication scope")
        return current.scope

    try:
        found = fresh()
        target = found.record
        if found.scope:
            return {"status": "permitted", "scope": found.scope,
                    "target": address, "handshake": "not-started"}
        record = collaboration.scope_for(sender, target)
        if record is not None:
            # Resume a consented selection whose broker response was lost.
            scope = synchronize()
            return {"status": "permitted", "scope": scope,
                    "target": address, "handshake": "not-started"}
        proposal = collaboration.propose(sender, target)
        name = target.get("name") or address

        def apply_selection(verdict):
            current = fresh().record
            collaboration.create(sender, current, verdict)

        verdict, go, kept = consent.take_or_request(
            sender, "collaborate", name,
            binding={"pair": proposal["endpoints"], "generation": target["generation"]},
            apply=apply_selection)
        if not go:
            reason = (consent.shown_refusal(verdict, "collaborating with %s" % name, kept)
                      if verdict is not None else
                      "needs your user's selection of %s; ask who to collaborate with, "
                      "then run the same connect again" % name)
            return {"status": "selection-required", "reason": reason,
                    "target": address, "handshake": "not-started"}
        return {"status": "permitted", "scope": synchronize(),
                "target": address, "handshake": "not-started"}
    except ValueError as exc:
        return {"status": "refused", "reason": str(exc), "handshake": "not-started"}


def select(sender: dict, target: dict, call=None) -> dict:
    """Apply the user's selection to exactly two native conversations.

    This is permission to attempt the handshake, never evidence that the peer
    has answered. The ordinary folder commands retain their separate scope.
    """
    from . import collaboration, context, registry
    why = context.require_sure(call, "connect the selected session") if call else None
    if why:
        return {"status": "refused", "reason": why}
    if "home_id" in target or target.get("remote"):
        return _select_network(sender, target)
    current = [r for r in registry.records() if
               r.get("runtime") == target.get("runtime") and
               r.get("home") == target.get("home") and
               r.get("session_id") == target.get("session_id")]
    if len(current) != 1 or current[0].get("state") in ("ended", "stale"):
        return {"status": "refused", "reason": "the selected conversation is no longer available"}
    target = current[0]
    existing = config.scope_for(sender, target)[0]
    if existing:
        return {"status": "permitted", "scope": existing, "handshake": "not-started"}
    proposal = collaboration.propose(sender, target)
    name = target.get("name") or target.get("ref")
    applied = []

    def apply_selection(verdict):
        now = [r for r in registry.records() if
               r.get("runtime") == target.get("runtime") and
               r.get("home") == target.get("home") and
               r.get("session_id") == target.get("session_id")]
        if len(now) != 1 or now[0].get("state") in ("ended", "stale"):
            raise ValueError("the selected conversation ended before applying")
        applied.append(collaboration.create(sender, now[0], verdict))

    try:
        verdict, go, kept = consent.take_or_request(
            sender, "collaborate", name, binding={"pair": proposal["endpoints"]},
            apply=apply_selection)
    except ValueError as exc:
        return {"status": "refused", "reason": str(exc), "handshake": "not-started"}
    if not go:
        reason = (consent.shown_refusal(verdict, "collaborating with %s" % name, kept)
                  if verdict is not None else
                  "needs your user's selection of %s; ask who to collaborate with, "
                  "then run the same connect again" % name)
        return {"status": "selection-required", "reason": reason,
                "target": target.get("ref"), "handshake": "not-started"}
    record = applied[0]
    return {"status": "permitted", "scope": "collaboration:" + record["id"],
            "target": target.get("ref"), "handshake": "not-started"}


def publication(me: dict, visible=True, call=None) -> dict:
    """Publish this conversation only, without granting communication scope."""
    from . import context, directory
    why = context.require_sure(call, "publish this conversation") if call else None
    if why:
        return {"status": "refused", "reason": why}
    if not visible:
        directory.publish(me, visible=False, user_source="explicit unpublish request")
        return {"status": "hidden", "visible": False}
    if directory.is_published(me):
        return {"status": "published", "visible": True}
    applied = []
    try:
        verdict, go, kept = consent.take_or_request(
            me, "publish", me.get("name") or me["ref"],
            binding={"conversation": {k: me.get(k) for k in ("runtime", "home", "session_id")}},
            apply=lambda words: applied.append(directory.publish(me, user_source=words)))
    except ValueError as exc:
        return {"status": "refused", "reason": str(exc)}
    if not go:
        return {"status": "selection-required", "visible": False,
                "reason": consent.shown_refusal(verdict, "publishing this session for discovery", kept)
                if verdict else "needs your user's instruction to make this session discoverable"}
    return {"status": "published", "visible": True}
