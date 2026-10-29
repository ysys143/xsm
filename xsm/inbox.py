"""A copy of each message sent to a Codex session, for it to read mid-turn.

Codex takes its queue only between turns. A session that keeps working —
`sleep; ./phase; ./xsm channel` in a loop, which is what a Codex worker told
to check often does — never ends a turn and never receives anything: in S10
collab run 4 all six messages to the Codex worker (three phase announcements,
a peer's reply) sat in its queue for the whole fifteen minutes.

These session-id files are compatibility exports. New sends first persist the
full endpoint-bound original in handoff; old destructive readers cannot remove
it. Pre-P04 originals are archived before an export is removed. Receipts still
suppress native queue duplicates, but neither receipt nor export deletion is a
confirmed-consumption ack. New receive APIs explicitly claim and acknowledge.
"""
from __future__ import annotations

import os
import hashlib
import json
import re
import time

from . import paths

INBOX = "inbox"
MAX_WAIT = 600          # a `--wait` longer than a person's approval window is a daemon
MCP_MAX_WAIT = 60       # the MCP server reads one request at a time; a long block looks dead
KEEPALIVE = 15.0        # a silent process is one an agent kills


def _dir(session_id: str) -> str:
    return paths.path(INBOX, str(session_id))


def keep(session_id: str, msg_id: str, content: str, *, receiver=None) -> None:
    # Compatibility export only. New senders durably store the canonical
    # original first; old consumers may delete this without acknowledging it.
    item = {"id": msg_id, "t": time.time(), "content": content,
            "export": {"owner_type": "legacy-export"}}
    if receiver is not None:
        from . import handoff, context
        item["receiver"] = handoff._identity(receiver)
        item["export"]["generation"] = (context.generation(receiver.get("pid"), receiver.get("lstart"))
                                           if receiver.get("pid") and receiver.get("lstart") else None)
    paths.write_json(os.path.join(_dir(session_id), "%s.json" % msg_id),
                     item)


def preserve(item, session_id):
    """Keep pre-P04 originals before a destructive legacy export read/delete.

    Unknown sender/home records stay evidence, not newly authenticated input.
    Content-addressed paths never overwrite a different original under one ID.
    """
    if not isinstance(item, dict) or not item.get("content"):
        return
    key = hashlib.sha256(json.dumps(item, sort_keys=True).encode("utf-8")).hexdigest()
    endpoint = hashlib.sha256(str(session_id).encode("utf-8")).hexdigest()
    filename = paths.path("legacy-inbox-originals", endpoint, key + ".json")
    if not os.path.exists(filename):
        from . import handoff
        handoff._write(filename, item)


def legacy_items(session_id):
    """Non-consuming import view, including old .taking and preserved originals."""
    result = []
    try:
        names = os.listdir(_dir(session_id))
    except OSError:
        names = []
    for name in names:
        if name.endswith((".json", ".taking")):
            item = paths.read_json(os.path.join(_dir(session_id), name))
            if isinstance(item, dict) and item.get("content"):
                result.append(item)
    seen = {item.get("id") for item in result}
    endpoint = hashlib.sha256(str(session_id).encode("utf-8")).hexdigest()
    archive = paths.path("legacy-inbox-originals", endpoint)
    try:
        archived = sorted(os.listdir(archive))
    except OSError:
        archived = []
    for name in archived:
        item = paths.read_json(os.path.join(archive, name)) if name.endswith(".json") else None
        if isinstance(item, dict) and item.get("content") and item.get("id") not in seen:
            result.append(item)
            seen.add(item.get("id"))
    return result


def note_queued(session_id: str, msg_id: str, codex_home: str, queued_id: str | None) -> None:
    """Record where the queue's own copy of a kept message is, so the reader
    that takes the message first can take that copy back out (issue #7). A
    copy already taken is left alone."""
    if not (session_id and msg_id and queued_id):
        return
    p = os.path.join(_dir(session_id), "%s.json" % msg_id)
    item = paths.read_json(p)
    if isinstance(item, dict):
        item.update({"queued_id": queued_id, "codex_home": codex_home})
        paths.write_json(p, item)


def drop(session_id: str | None, msg_id: str | None) -> None:
    if not (session_id and msg_id):
        return
    try:
        filename = os.path.join(_dir(session_id), "%s.json" % msg_id)
        preserve(paths.read_json(filename), session_id)
        os.unlink(filename)
    except OSError:
        pass


def count(session_id: str | None) -> int:
    """Cheap: one listdir. Runs after every command a Codex session makes."""
    if not session_id:
        return 0
    try:
        return sum(1 for n in os.listdir(_dir(session_id)) if n.endswith(".json"))
    except OSError:
        return 0


def pending_status(receiver, *, owner_alive=None):
    """Read-only, exact-endpoint union of canonical IDs and live exports.

    Unknown count is None, never an invented zero. No registry identity lookup,
    claim, recovery transition or ACK occurs here; known_count is a lower bound.
    """
    from . import handoff
    ids, diagnostics = set(), []
    try:
        endpoint = handoff._identity(receiver)
    except (ValueError, TypeError, AttributeError):
        return {'count': None, 'known_count': 0, 'diagnostics': ['receiver-identity-unavailable']}
    try:
        ids.update(handoff._id(mid) for mid in handoff.pending_ids(receiver, owner_alive=owner_alive))
    except Exception as exc:
        diagnostics.append('canonical-pending-unavailable:' + type(exc).__name__)
    try:
        names = os.listdir(_dir(endpoint['session_id']))
    except FileNotFoundError:
        names = []
    except OSError as exc:
        names = []
        diagnostics.append('legacy-pending-unavailable:' + type(exc).__name__)
    for name in names:
        if not name.endswith('.json'):
            continue
        try:
            item = paths.read_json(os.path.join(_dir(endpoint['session_id']), name))
            if not isinstance(item, dict):
                raise ValueError('unreadable export')
            mid = handoff._id(item.get('id'))
            if item.get('receiver') is not None:
                if handoff._identity(item['receiver']) != endpoint:
                    continue
            elif not (endpoint['runtime'] == 'codex' and item.get('codex_home') and
                      os.path.realpath(os.path.expanduser(item['codex_home'])) == endpoint['home']):
                # An unbound old CID export is not another home's metadata.
                if handoff.status(receiver, mid).get('status') != 'not-found':
                    continue  # Exact canonical IDs already supply eligibility.
                diagnostics.append('legacy-receiver-unbound')
                continue
            canonical = handoff.status(receiver, mid)
            if canonical.get('status') == 'not-found':
                ids.add(mid)
            # Existing originals, including ACK/error/live leases, are governed
            # solely by pending_ids; a stale export cannot resurrect them.
        except (OSError, ValueError, KeyError, TypeError) as exc:
            diagnostics.append('legacy-export-unavailable:' + type(exc).__name__)
    return {'count': None if diagnostics else len(ids), 'known_count': len(ids), 'diagnostics': diagnostics}


def pending_fields(receiver, *, owner_alive=None):
    try:
        status = pending_status(receiver, owner_alive=owner_alive)
    except Exception as exc:
        status = {'count': None, 'known_count': 0, 'diagnostics': ['pending-unavailable:' + type(exc).__name__]}
    result = {'inbox_pending': status['count']}
    if status['diagnostics']:
        result.update(inbox_pending_diagnostics=status['diagnostics'], inbox_pending_known=status['known_count'])
    text = notice(receiver.get('session_id'), pending=status)
    if text:
        result['inbox_notice'] = text
    return result


def wait_for(session_id: str | None, seconds: float, interval: float = 1.0,
             keepalive: float = KEEPALIVE, out=None, counter=None, pump=None, cancelled=None) -> int | None:
    """Block until a message is waiting, and say how many. 0 when time runs out.

    This is not a daemon: it is one command blocking until it returns, and the
    process ends with it. The cap is what says so in code. It exists because
    the alternative is what a Codex worker actually did — `sleep` in a loop,
    which never ends the turn, which is exactly why its six queued messages
    never arrived (S10 collab run 4).

    It counts; it never takes. `take()` claims by rename, so a waiting loop
    that took would swallow the message it was waiting for.
    """
    deadline = time.monotonic() + max(0.0, min(seconds, MAX_WAIT))
    spoke = time.monotonic()
    while True:
        if (pump is not None and not pump()) or (cancelled is not None and cancelled()):
            return 0
        waiting = counter() if counter is not None else count(session_id)
        if waiting is None:
            return None  # Caller reports the count diagnostic; do not wait on a false zero.
        if waiting:
            return waiting
        left = deadline - time.monotonic()
        if left <= 0:
            if out:
                out.write("[xsm] no message in %ds. Call `xsm inbox --wait` again if you are "
                          "still waiting; do not sleep-poll.\n" % seconds)
                out.flush()
            return 0
        if out and keepalive and time.monotonic() - spoke >= keepalive:
            out.write("[xsm] waiting for messages — %ds left; this returns the moment one "
                      "arrives.\n" % int(left))
            out.flush()
            spoke = time.monotonic()
        time.sleep(min(interval, left))


def peek(session_id: str) -> list:
    """Read waiting copies without claiming/deleting them (question waits).

    Correlated replies can be indexed while the runtime is inside a tool.
    Unrelated messages and native queue copies keep their ordinary handover.
    """
    folder = _dir(session_id)
    try:
        names = [n for n in os.listdir(folder) if n.endswith(".json")]
    except OSError:
        return []
    items = [paths.read_json(os.path.join(folder, name)) for name in names]
    return sorted((i for i in items if isinstance(i, dict) and i.get("content")),
                  key=lambda i: i.get("t", 0))


def take(session_id: str, *, receiver=None, exclude=()) -> list:
    """Claim every waiting copy, oldest first. The rename is the claim: two
    readers at once (a shell `xsm inbox` and the MCP tool) get each message
    once between them."""
    d = _dir(session_id)
    try:
        names = [n for n in os.listdir(d) if n.endswith(".json")]
    except OSError:
        return []
    out = []
    for name in names:
        original = os.path.join(d, name)
        item = paths.read_json(original)
        if isinstance(item, dict):
            if item.get("id") in exclude:
                continue
            if receiver is not None and item.get("receiver") is not None:
                from . import handoff
                if handoff._identity(item["receiver"]) != handoff._identity(receiver):
                    continue
            preserve(item, session_id)
        claimed = os.path.join(d, name[:-len(".json")] + ".taking")
        try:
            os.rename(original, claimed)
        except OSError:
            continue
        item = paths.read_json(claimed)
        if isinstance(item, dict) and item.get("receiver") is not None:
            from . import context, handoff, identity, ledger
            endpoint = item["receiver"]
            original = handoff.status(endpoint, item["id"])
            if original["status"] != "not-found":
                # Compatibility callers of the current module also participate
                # in ownership. Truly older binaries remain at-least-once;
                # their export deletion alone still cannot ack the original.
                start = identity.lstart(os.getpid())
                if not start:
                    raise ValueError("cannot establish legacy reader generation; original retained")
                owner = {"type": "legacy-export", "id": "process:%s" % os.getpid()}
                generation = context.generation(os.getpid(), start)
                record = handoff.claim(endpoint, owner, generation, message_id=item["id"])
                if record["status"] == "empty":
                    item = None
                else:
                    token = record["claim"]["token"]
                    ledger.handoff_step(record["id"], "claimed", endpoint)
                    handoff.handoff(endpoint, token, owner, generation)
                    ledger.handoff_step(record["id"], "handoff", endpoint)
                    item["handoff_claim"] = {"id": record["id"], "token": token,
                                              "owner": owner, "generation": generation,
                                              "digest": record["digest"]}
        try:
            os.unlink(claimed)
        except OSError:
            pass
        if item and item.get("content"):
            out.append(item)
    return sorted(out, key=lambda i: i.get("t", 0))


def notice(session_id: str | None, *, receiver=None, owner_alive=None, pending=None) -> str:
    pending = pending if pending is not None else pending_status(receiver, owner_alive=owner_alive) if receiver else None
    n = pending['count'] if pending is not None else count(session_id)
    if n is None:
        return '[xsm] Inbox pending count is unknown; originals remain available. Check inbox before waiting again.'
    if not n:
        return ""
    return ("[xsm] %d message%s from other sessions waiting for you; read with `xsm inbox` "
            "(or the xsm_inbox MCP tool) before waiting again." % (n, "" if n == 1 else "s"))


def _reply_dir(receiver):
    endpoint = {k: receiver.get(k) for k in ("runtime", "home", "session_id")}
    if not all(isinstance(v, str) and v for v in endpoint.values()):
        raise ValueError("exact reply receiver required")
    endpoint["home"] = os.path.realpath(os.path.expanduser(endpoint["home"]))
    key = hashlib.sha256(json.dumps(endpoint, sort_keys=True).encode()).hexdigest()
    return paths.path("question-reply-copies", key)


def keep_reply(receiver, msg_id, request_id, content):
    """Cache a successfully queued question reply across older native hooks.

    The receiver still checks this envelope before indexing. A separate cache
    prevents an older hook from deleting the only full-body copy first.
    """
    if not isinstance(msg_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", msg_id):
        raise ValueError("invalid reply id")
    paths.write_json(os.path.join(_reply_dir(receiver), msg_id + ".json"),
                     {"id": msg_id, "request_id": request_id, "content": content, "t": time.time()})


def reply_copies(receiver, request_id):
    folder = _reply_dir(receiver)
    try:
        names = [n for n in os.listdir(folder) if n.endswith(".json")]
    except OSError:
        return []
    result = []
    for name in names:
        item = paths.read_json(os.path.join(folder, name))
        if isinstance(item, dict) and item.get("request_id") == request_id and item.get("content"):
            result.append(item)
    return sorted(result, key=lambda x: x.get("t", 0))


def drop_reply(receiver, msg_id):
    if not isinstance(msg_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", msg_id):
        return
    try:
        os.unlink(os.path.join(_reply_dir(receiver), msg_id + ".json"))
    except OSError:
        pass
