"""Local discovery evidence, separate from communication permissions (ADR-0024).

Public API:
* publish(me, visible=True, user_source=...): exact-conversation publication;
  the coordinator supplies the user's publication instruction, never a peer ACK.
* is_published(record): no name/ref/generation inheritance across conversations.
* exclusion_status(path, exclusions=None): excluded / included / unknown.
  A confirmed match takes precedence over other malformed/unreadable roots.
* excluded(path, exclusions=None): privacy wrapper (unknown is hidden).
  config.json ``directory_excluded_paths`` is
  a list of absolute (or ~/...) directory roots, not globs. Canonical descendants,
  including nonexistent ones, are excluded. Invalid/unreadable policy is unknown;
  discovery fails closed, while registry callers preserve basic communication.
  Registry/attachment callers can pass the same explicit list to this function.
* discover(caller, records=None, machine=None, work=None, branch=None): returns
  {candidates, status, reason, unanswered}. Only allowed same-uid local homes are
  read. Remote machine requests return unknown until P12 verifies remote origins.
  Candidates have an opaque exact id/handle, never a home/cwd/transcript path.
* resolve_candidate(caller, key): internal current full record for an exact
  candidate id/address, rechecking visibility and native identity. This private
  result is for the connection coordinator, never a public directory response.

Scope/machine/exclusion/repository/branch filters precede task enrichment;
work filtering necessarily reads the native title/plan, then liveness is read
only for matches. All I/O uses the enclosing shared probe.quick budget. A failed
source is unknown metadata, not a new messaging restriction. No source is consent.

Native adapters intentionally recognize structured fields, not conversation prose:
Codex registry current name, session_meta.git.branch, update_plan, task_started /
task_complete; Claude registry sessions/<pid>.json name and transcript TodoWrite.
Claude transcript_path must be supplied by its hook/registry integration; no
project/transcript glob or guessed path is used. Native transcript records remain
version-dependent and unknown schemas remain unknown. References for transcript
provenance and TodoWrite's input schema:
https://code.claude.com/docs/en/hooks#common-input-fields
https://platform.claude.com/docs/en/agent-sdk/typescript#todowrite
The hooks documentation warns that asynchronous transcripts can lag live turns.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import socket
import stat
import time
from datetime import datetime

from . import config, identity, paths, probe, registry

PUBLICATIONS = "directory-publications"
EXCLUSIONS_KEY = "directory_excluded_paths"
TAIL_BYTES = 256 * 1024
HEAD_BYTES = 256 * 1024
JSON_BYTES = 64 * 1024
STALE_SECONDS = 300  # Display freshness only; never expires publication/permission.
TEXT_CHARS = 240
_PATH = re.compile(r"(?<![\w])(?:~?/|[A-Za-z]:\\)[^\s<>\"']+")


def _canonical(value):
    if not isinstance(value, str) or not value or "\x00" in value:
        return None
    expanded = os.path.expanduser(value)
    if not os.path.isabs(expanded):
        return None
    return os.path.realpath(expanded)


def _real(value):
    if not isinstance(value, str):
        return None
    return probe.remember(("directory-real", value),
                          lambda: probe.bounded(_canonical, value, folder=value))


def _inside(child, root):
    return bool(child and root and os.path.commonpath((child, root)) == root)


def _read_settings():
    """Missing config means defaults; an existing unreadable policy is unknown.

    Keep config.load's communication-availability fallback separate. Read the
    actual file once, bounded and consistently, without a check/open race.
    """
    try:
        stored = _small_json(paths.path(config.CONFIG))
    except FileNotFoundError:
        return dict(config.DEFAULT_CONFIG)
    if stored is None:
        return None
    result = dict(config.DEFAULT_CONFIG)
    result.update(stored[0])
    return result


def _settings():
    return probe.remember(("directory-config",), lambda: probe.bounded(_read_settings))


def exclusion_status(path, exclusions=None):
    """Shared three-way metadata policy, never an implicit communication ban.

    Invalid roots or failed probes yield unknown unless another root definitely
    matches. A valid empty list is included without probes. No cwd fallback or
    glob expansion. Canonical roots include symlinks and missing descendants.
    """
    with probe.quick():
        if exclusions is None:
            cfg = _settings()
            if not isinstance(cfg, dict):
                return "unknown"
            exclusions = cfg.get(EXCLUSIONS_KEY, [])
        if not isinstance(exclusions, (list, tuple)):
            return "unknown"
        if not exclusions:
            return "included"
        value = _real(path)
        if not value:
            return "unknown"
        uncertain = False
        for root in exclusions:
            if not isinstance(root, str) or any(mark in root for mark in ("*", "?", "[")):
                uncertain = True
                continue
            canonical = _real(root)
            if canonical is None:
                uncertain = True
            elif _inside(value, canonical):
                return "excluded"
        return "unknown" if uncertain else "included"


def excluded(path, exclusions=None):
    """Privacy-only predicate. Registry registration must use exclusion_status."""
    return exclusion_status(path, exclusions) != "included"


def _endpoint(record):
    if not isinstance(record, dict) or record.get("runtime") not in ("codex", "claude"):
        return None
    if record.get("certainty") == "provisional" or record.get("basis") in ("cwd", "neighbor", "none"):
        return None
    sid = record.get("session_id")
    home = _real(record.get("home"))
    if not isinstance(sid, str) or not sid.strip() or len(sid) > 256 \
            or any(c in sid for c in ("/", "\\", "\x00", "\n", "\r")) or not home:
        return None
    return {"runtime": record["runtime"], "home": home, "session_id": sid}


def _key(endpoint):
    return hashlib.sha256(json.dumps(endpoint, sort_keys=True).encode()).hexdigest()


def _local_machine(value):
    return value is None or value in ("local", socket.gethostname())


def _owned_home(home):
    info = os.stat(home)
    return stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()


def _allowed(record, endpoint):
    if endpoint is None or record.get("registered") is False \
            or record.get("remote") or not _local_machine(record.get("machine")) \
            or not _local_machine(record.get("origin")) \
            or record.get("uid", os.getuid()) != os.getuid():
        return False
    homes = probe.remember(("directory-homes",), lambda: probe.bounded(config.homes))
    if not isinstance(homes, list) or not any(
            isinstance(h, dict) and h.get("runtime") == endpoint["runtime"]
            and h.get("enabled", True) is not False and _real(h.get("path")) == endpoint["home"]
            for h in homes):
        return False
    return probe.remember(("directory-owner", endpoint["home"]), lambda: probe.bounded(
        _owned_home, endpoint["home"], folder=endpoint["home"], default=False))


def _signature(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _small_json(path):
    # Nonblocking open avoids hanging on a FIFO substituted for a native file.
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() \
                or before.st_size > JSON_BYTES:
            return None
        data = stream.read(JSON_BYTES + 1)
        after = os.fstat(stream.fileno())
        try:
            current = os.stat(path)
        except FileNotFoundError:
            return None  # Disappeared during the read, not an initially missing policy.
        if _signature(before) != _signature(after) or _signature(after) != _signature(current):
            return None
    value = json.loads(data)
    return (value, before.st_mtime) if isinstance(value, dict) else None


def _publication(endpoint):
    result = probe.bounded(_small_json, paths.path(PUBLICATIONS, _key(endpoint) + ".json"))
    value = result[0] if result else None
    return value if isinstance(value, dict) and value.get("endpoint") == endpoint \
        and value.get("uid") == os.getuid() and value.get("visible") is True \
        and isinstance(value.get("user_source"), str) and value["user_source"].strip() else None


def publish(me, visible=True, user_source=None):
    """Persist only visibility (0600), never a scope/link/permission.

    Same conversation resumes retain this setting; renames/ref collisions and
    pid changes do not affect its key. New conversations must be published anew.
    Invalid/nonlocal identities or missing explicit user provenance raise ValueError.
    OSError is left to the coordinator to report a refused persistence operation.
    """
    with probe.quick():
        endpoint = _endpoint(me)
        if not _allowed(me, endpoint) or not isinstance(visible, bool):
            raise ValueError("publication requires an allowed exact local conversation")
        if not isinstance(user_source, str) or not user_source.strip():
            raise ValueError("publication requires the user's explicit instruction source")
        if len(user_source) > 4096 or (visible and excluded(me.get("cwd"))):
            raise ValueError("publication source is too large or the directory is excluded")
        result = {"endpoint": endpoint, "uid": os.getuid(), "visible": visible,
                  "user_source": user_source, "updated_at": time.time()}
        if visible:
            config.require_valid_policy()
        paths.write_json(paths.path(PUBLICATIONS, _key(endpoint) + ".json"), result, mode=0o600)
        return result


def is_published(record):
    with probe.quick():
        endpoint = _endpoint(record)
        return bool(_allowed(record, endpoint) and not excluded(record.get("cwd"))
                    and _publication(endpoint))


def _timestamp(value):
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            result = float(value)
        elif isinstance(value, str):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                return None
            result = dt.timestamp()
        else:
            return None
        return result if math.isfinite(result) else None
    except (ValueError, OverflowError, OSError):
        return None


def _text(value):
    if not isinstance(value, str):
        return None
    value = _PATH.sub("[path]", value)
    value = " ".join(value.split())
    return value[:TEXT_CHARS] or None


def _observation(value=None, source=None, timestamp=None):
    now = time.time()
    stamp = _timestamp(timestamp)
    known = value is not None
    return {"value": value, "status": "known" if known else "unknown",
            "source": source, "timestamp": timestamp if stamp is not None else None,
            "observed_at": now, "freshness": ("stale" if now - stamp > STALE_SECONDS else "fresh")
            if known and stamp is not None and stamp <= now + 5 else "unknown"}


def _snapshot(path, endpoint):
    """Bounded consistent head/tail; mismatch/partial JSON/replacement is unknown."""
    path = _canonical(path)
    if not _inside(path, endpoint["home"]):
        return None
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid():
            return None
        head = None
        lower = 0
        if endpoint["runtime"] == "codex":
            line = stream.readline(HEAD_BYTES + 1)
            if len(line) > HEAD_BYTES or not line.endswith(b"\n"):
                return None
            head = json.loads(line)
            if not isinstance(head, dict) or head.get("type") != "session_meta" \
                    or not isinstance(head.get("payload"), dict) \
                    or head["payload"].get("id") != endpoint["session_id"]:
                return None
            lower = stream.tell()
        start = max(lower, before.st_size - TAIL_BYTES)
        stream.seek(max(0, start - 1))
        boundary = start == 0 or stream.read(1) == b"\n"
        stream.seek(start)
        tail = stream.read(min(TAIL_BYTES, before.st_size - start))
        after = os.fstat(stream.fileno())
        if _signature(before) != _signature(after) or _signature(after) != _signature(os.stat(path)):
            return None
    if not boundary:
        tail = tail.partition(b"\n")[2]
    if tail and not tail.endswith(b"\n"):
        return None
    rows = []
    for line in tail.splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            return None
        if endpoint["runtime"] == "claude":
            if row.get("sessionId") not in (None, endpoint["session_id"]):
                return None
        elif row.get("type") == "session_meta" and (
                not isinstance(row.get("payload"), dict)
                or row["payload"].get("id") != endpoint["session_id"]):
            return None
        rows.append(row)
    return head, rows


def _plan(items, key):
    if not isinstance(items, list) or len(items) > 100:
        return None
    if any(not isinstance(item, dict) or not _text(item.get(key))
           or item.get("status") not in ("pending", "in_progress", "completed") for item in items):
        return None
    return [{"step": _text(item[key]), "status": item["status"]} for item in items]


def _native(record, endpoint):
    sid, runtime, home = endpoint["session_id"], endpoint["runtime"], endpoint["home"]
    path = registry.codex_rollout(home, sid) if runtime == "codex" else record.get("transcript_path")
    if not path:
        return {}
    snapshot = _snapshot(path, endpoint)
    if snapshot is None:
        return {}
    head, rows = snapshot
    out = {}
    if head:
        git = head["payload"].get("git")
        if isinstance(git, dict):
            out["branch"] = _observation(_text(git.get("branch")), "codex:session_meta:git.branch",
                                         head.get("timestamp"))
    for row in rows:
        stamp = row.get("timestamp")
        items, source = None, None
        if runtime == "codex":
            payload = row.get("payload")
            if not isinstance(payload, dict):
                continue
            kind = payload.get("type")
            if row.get("type") == "event_msg" and kind in (
                    "task_started", "task_complete", "task_completed", "turn_aborted"):
                out["activity"] = _observation("busy" if kind == "task_started" else "idle",
                                               "codex:event_msg:" + kind, stamp)
            if row.get("type") == "response_item" and kind == "function_call" \
                    and payload.get("name") in ("update_plan", "functions.update_plan"):
                source = "codex:rollout:update_plan"
                try:
                    arguments = json.loads(payload.get("arguments", ""))
                    items = _plan(arguments.get("plan"), "step") if isinstance(arguments, dict) else None
                except (ValueError, TypeError):
                    pass
        elif row.get("sessionId") == sid and row.get("type") == "assistant":
            msg = row.get("message")
            blocks = msg.get("content") if isinstance(msg, dict) else None
            if not isinstance(blocks, list):
                continue
            for block in blocks:
                if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "TodoWrite":
                    source = "claude:transcript:TodoWrite"
                    data = block.get("input")
                    items = _plan(data.get("todos"), "content") if isinstance(data, dict) else None
        if source:
            out["todo"] = _observation(items[:8] if items is not None else None, source, stamp)
            out["todo"]["truncated"] = items is not None and len(items) > 8
            active = [item["step"] for item in items or [] if item["status"] == "in_progress"]
            pending = [item["step"] for item in items or [] if item["status"] == "pending"]
            out["summary"] = _observation((active or pending or [None])[0], source, stamp)
    return out


def _claude_session(record, endpoint, refresh=False):
    pid = record.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    path = os.path.join(endpoint["home"], "sessions", "%s.json" % pid)
    if not _inside(_canonical(path), endpoint["home"]):
        return None
    return _small_json(path) if refresh else probe.remember(
        ("directory-native-session", path), lambda: _small_json(path))


def _title(record, endpoint):
    if endpoint["runtime"] == "codex":
        name = registry._codex_thread_name(endpoint["home"], endpoint["session_id"])
        return _observation(_text(name), "codex:registry:current_name", time.time())
    result = _claude_session(record, endpoint)
    if not result or result[0].get("sessionId") != endpoint["session_id"]:
        return _observation()
    return _observation(_text(result[0].get("name")), "claude:registry:current_name", result[1])


def _liveness(record, endpoint):
    if endpoint["runtime"] == "claude":
        try:
            current = _claude_session(record, endpoint)
        except (OSError, ValueError):
            current = None
        if current and current[0].get("sessionId"):
            if current[0]["sessionId"] != endpoint["session_id"]:
                return "ended", "native_session_replaced"
            native_socket = current[0].get("messagingSocketPath")
            if isinstance(native_socket, str):
                record = dict(record, socket=native_socket)
    return identity.state_reason(record)


def _native_identity(record, endpoint):
    """False on explicit replacement, None on unavailable native metadata.

    A missing title/transcript is not permission denial. Registry exact identity
    is still usable; a contradictory native conversation is never usable.
    """
    if endpoint["runtime"] == "claude":
        result = _claude_session(record, endpoint, refresh=True)
        sid = result[0].get("sessionId") if result else None
        return sid == endpoint["session_id"] if isinstance(sid, str) else None
    path = registry.codex_rollout(endpoint["home"], endpoint["session_id"])
    path = _canonical(path)
    if not _inside(path, endpoint["home"]):
        return None
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid():
            return None
        line = stream.readline(HEAD_BYTES + 1)
        after = os.fstat(stream.fileno())
        if len(line) > HEAD_BYTES or not line.endswith(b"\n") \
                or _signature(before) != _signature(after) or _signature(after) != _signature(os.stat(path)):
            return None
    data = json.loads(line)
    if not isinstance(data, dict) or data.get("type") != "session_meta" \
            or not isinstance(data.get("payload"), dict):
        return None
    sid = data["payload"].get("id")
    return sid == endpoint["session_id"] if isinstance(sid, str) else None


def _repo(cwd):
    return probe.remember(("directory-repo", cwd), lambda: probe.bounded(
        config.git_repo, cwd, folder=cwd, default=(None, None)))


def _discover_local(caller, records=None, machine=None, work=None, branch=None):
    """Return a sanitized candidate union. Does not adopt, connect, or send.

    records defaults to raw local registry pointers, not registry.records(), so
    private sessions never get native enrichment. A coordinator may supply its
    existing records snapshot. Full SHA-256 id + opaque home_id disambiguate short
    refs and duplicate names; coordinator selection revalidates the exact endpoint.
    Unknown remote machine filters return no names/counts. Work is a case-insensitive
    substring of a native title/task or stored hook name; branch is exact.
    A hook-name fallback retains record.updated as its timestamp and explicitly
    unknown freshness: registry activity is not proof of a current native title.
    """
    result = {"candidates": [], "status": "ok", "reason": None, "unanswered": {}}
    if any(value is not None and (not isinstance(value, str) or not value.strip())
           for value in (machine, work, branch)):
        result.update(status="unknown", reason="invalid_filter")
        return result
    if not _local_machine(machine):
        result.update(status="unknown", reason="remote_discovery_unverified")
        return result
    with probe.quick():
        cfg = _settings()
        own = _endpoint(caller)
        if not isinstance(cfg, dict) or not isinstance(cfg.get("deny", []), list) \
                or not _allowed(caller, own) or excluded(caller.get("cwd")):
            result.update(status="unknown", reason="caller_or_policy_unverified")
            return result
        own_repo = _repo(_real(caller.get("cwd")))[1]
        rows = records if records is not None else probe.bounded(registry.raw_records)
        if not isinstance(rows, (list, tuple)):
            result.update(status="unknown", reason="registry_unavailable")
            return result
        seen = set()
        rows = sorted((r for r in rows if isinstance(r, dict)),
                      key=lambda r: _timestamp(r.get("updated")) or 0, reverse=True)
        for record in rows:
            if record.get("remote") or not _local_machine(record.get("machine")) \
                    or not _local_machine(record.get("origin")):
                continue
            endpoint = _endpoint(record)
            if not _allowed(record, endpoint) or excluded(record.get("cwd")) \
                    or record.get("ref") in cfg.get("deny", []):
                continue
            key = _key(endpoint)
            if key in seen:
                continue
            seen.add(key)
            cwd = _real(record.get("cwd"))
            top, common = _repo(cwd)
            basis = []
            if _publication(endpoint):
                basis.append("published")
            if own_repo and common and own_repo == common:
                basis.append("same_repo")
            if not basis:
                continue
            branch_name = probe.git(cwd, "symbolic-ref", "--quiet", "--short", "HEAD")
            branch_obs = _observation(_text(branch_name), "git:symbolic-ref", time.time())
            if branch is not None and branch_obs["value"] is not None and branch_obs["value"] != branch:
                continue
            native = probe.bounded(_native, record, endpoint, folder=endpoint["home"], default={})
            if branch_obs["value"] is None:
                branch_obs = native.get("branch", _observation())
            if branch is not None and branch_obs["value"] != branch:
                if branch_obs["value"] is None:
                    result.update(status="unknown", reason="native_filter_unknown")
                continue
            title = probe.bounded(_title, record, endpoint, folder=endpoint["home"])
            title = title if isinstance(title, dict) else _observation()
            if title["value"] is None and _text(record.get("name")):
                title = _observation(_text(record["name"]), "registry:hook.name", record.get("updated"))
                title["freshness"] = "unknown"
            summary = native.get("summary", _observation())
            if work is not None and (not isinstance(work, str) or not any(
                    work.casefold() in value.casefold() for value in (title["value"], summary["value"])
                    if isinstance(value, str))):
                if title["value"] is None and summary["value"] is None:
                    result.update(status="unknown", reason="native_filter_unknown")
                continue
            state = probe.bounded(_liveness, record, endpoint, default=("unknown", "probe_unavailable"))
            state_value, why = state
            receive = None
            if state_value in ("ended", "stale"):
                receive = "unavailable"
            elif state_value == "live" and why not in ("socket_blocked", "live_unverified"):
                if endpoint["runtime"] == "codex" or why == "live" or record.get("socket"):
                    receive = "available"
            result["candidates"].append({
                "id": key, "target": "candidate:" + key, "is_self": endpoint == own,
                "handle": {"runtime": endpoint["runtime"], "session_id": endpoint["session_id"],
                                       "home_id": hashlib.sha256(endpoint["home"].encode()).hexdigest(),
                                       "machine": "local"},
                "ref": _text(record.get("ref")), "machine": "local", "runtime": endpoint["runtime"],
                "name": title["value"] or _text(record.get("name")), "title": title,
                "name_source": title["source"] if title["value"] is not None else "registry:cached_name",
                "name_freshness": title["freshness"] if title["value"] is not None else "unknown",
                "discovery_basis": basis,
                "repository": _text(config.repo_name(common)) if common else None,
                "branch": branch_obs, "summary": summary, "todo": native.get("todo", _observation()),
                "activity": native.get("activity", _observation()),
                "state": _observation(state_value if state_value != "unknown" else None,
                                      "registry:liveness:" + why, time.time()),
                "receive": _observation(receive, "registry:receive_capability", time.time()),
            })
        result["unanswered"] = probe.unanswered()
        if result["unanswered"]:
            result.update(status="unknown", reason="probe_incomplete")
    return result


def discover(caller, records=None, machine=None, work=None, branch=None):
    """Local candidates plus authenticated, separately filtered P2P peers.

    An explicit records snapshot is a local projection, including projections
    produced for a remote caller. It must never recurse into network discovery.
    A stopped/unconfigured network neither starts a process nor blocks locals.
    """
    result = _discover_local(caller, records=records, machine=machine, work=work, branch=branch)
    if records is not None:
        return result
    from . import network
    if not network.available():
        return result
    if _discover_local(caller, records=[])["reason"] is not None:
        return result
    try:
        remote = network.call({"op": "discover", "caller": caller, "machine": machine,
                               "work": work, "branch": branch}, timeout=3)
    except (network.NetworkError, OSError, ValueError):
        result["unanswered"]["network"] = "unavailable"
        if not _local_machine(machine):
            result.update(status="unknown", reason="remote_discovery_unavailable")
        return result
    result["candidates"].extend(remote.get("candidates", []))
    result["unanswered"].update(remote.get("unanswered", {}))
    if result["reason"] == "remote_discovery_unverified":
        result.update(status=remote.get("status", "unknown"), reason=remote.get("reason"))
    elif remote.get("status") != "ok":
        result.update(status="unknown", reason="remote_discovery_incomplete")
    return result


def resolve_candidate(caller, key):
    """Revalidate candidate:<full id> (or full id) into a private full record.

    Never resolve names or abbreviated refs here. Publication permits discovery,
    not communication: the coordinator still checks scope/consent and the current
    endpoint before delivery. A same-conversation resume can resolve anew, but a
    registry/native identity change during this lookup returns None for retry.
    Source enrichment failure alone does not prohibit basic messaging; the native
    endpoint must remain unchanged and any explicit replacement is rejected.
    """
    if not isinstance(key, str):
        return None
    if key.startswith("candidate:"):
        key = key[len("candidate:"):]
    if not re.fullmatch(r"[0-9a-f]{64}", key):
        return None
    with probe.quick():
        rows = probe.bounded(registry.raw_records)
        if not isinstance(rows, list):
            return None
        hits = [row for row in rows if (endpoint := _endpoint(row)) is not None and _key(endpoint) == key]
        if not hits:
            from . import network, resolve
            if not network.available():
                return None
            candidates = [row for row in discover(caller)["candidates"]
                          if row.get("id") == key and isinstance(row.get("target"), str)
                          and row["target"].startswith("net:")]
            if len(candidates) != 1:
                return None
            candidate = candidates[0]
            found = resolve.resolve(candidate["target"], caller=caller)
            if not found.ok or found.record.get("handle") != candidate.get("handle"):
                return None
            return dict(found.record, scope=found.scope, scope_basis=found.scope_basis)
        if len(hits) != 1 or not discover(caller, records=hits)["candidates"]:
            return None
        raw = hits[0]
        endpoint = _endpoint(raw)
        current = probe.bounded(registry._enrich, raw, folder=endpoint["home"])
        if not isinstance(current, dict) or _endpoint(current) != endpoint \
                or current.get("native_session_id", endpoint["session_id"]) not in (None, endpoint["session_id"]) \
                or current.get("end_reason") in ("superseded", "thread_replaced", "thread_unloaded"):
            return None
        native_match = probe.bounded(_native_identity, current, endpoint, folder=endpoint["home"])
        if native_match is False:
            return None
        # The raw record may have been replaced by a resume or a new thread
        # while native enrichment was running. Never deliver the old snapshot.
        latest = probe.bounded(registry.raw_records)
        if not isinstance(latest, list):
            return None
        fresh = [row for row in latest if _endpoint(row) == endpoint]
        generation_fields = ("pid", "lstart", "mcp_pid", "mcp_lstart", "cwd", "ended_at", "end_reason")
        if len(fresh) != 1 or any(raw.get(field) != fresh[0].get(field) for field in generation_fields):
            return None
        # Bypass the configuration memo for this final policy observation.
        cfg = probe.bounded(_read_settings)
        homes = probe.bounded(config.homes)
        if not isinstance(cfg, dict) or not isinstance(homes, list) \
                or not any(isinstance(h, dict) and h.get("runtime") == endpoint["runtime"]
                           and h.get("enabled", True) is not False and _real(h.get("path")) == endpoint["home"]
                           for h in homes) \
                or excluded(fresh[0].get("cwd"), cfg.get(EXCLUSIONS_KEY, [])) \
                or excluded(caller.get("cwd"), cfg.get(EXCLUSIONS_KEY, [])) \
                or not isinstance(cfg.get("deny", []), list) or raw.get("ref") in cfg.get("deny", []):
            return None
        if not discover(caller, records=fresh)["candidates"]:
            return None
        return current
