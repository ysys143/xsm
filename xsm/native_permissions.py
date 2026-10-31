"""Read a Claude permission invocation's identity, never its user's answer."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import time

MAX_TAIL_BYTES = 2 * 1024 * 1024
MAX_OPEN_CALLS = 128


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def identify(worker, data, runtime):
    """Return immutable native invocation fields, or None when ambiguous.

    Older PermissionRequest payloads omit tool_use_id. Worker-local PreToolUse
    metadata keeps it before the transcript is flushed; older workers fall back
    to a bounded transcript read. Only one exact open invocation is eligible.
    No directory scan, input-only guess, or approval is performed here.
    """
    session = data.get("session_id")
    if runtime != "claude" or not session or session != worker.get("session_id") or not worker.get("home"):
        return None
    tool_id = data.get("tool_use_id")
    if not isinstance(tool_id, str) or not tool_id:
        tool_id, observed = _recorded(worker, data, runtime)
        if observed and not tool_id:
            return None
    if not tool_id:
        for _ in range(2):  # tolerate one concurrent transcript append, never guess an ID
            tool_id = _from_transcript(worker, data)
            if tool_id:
                break
    if not tool_id:
        return None
    return {"runtime": runtime, "home": os.path.realpath(worker["home"]),
            "session_id": session, "worker": worker["name"], "pid": worker.get("pid"),
            "lstart": worker.get("lstart"), "tool_use_id": tool_id}


def _worker_identity(worker, runtime):
    return {"runtime": runtime, "home": os.path.realpath(worker["home"]),
            "session_id": worker.get("session_id"), "worker": worker["name"],
            "pid": worker.get("pid"), "lstart": worker.get("lstart")}


def _state_path(worker):
    from . import paths
    return paths.path("workers", worker["name"], "native-invocations.json")


def observe(worker, data, runtime):
    """Worker-local hooks retain invocation identity before transcript flushing.

    This is tool metadata, never an approval. Completed/failed calls are retired;
    indistinguishable concurrent calls stay ambiguous. No global hooks change.
    """
    if (runtime != "claude" or worker.get("mode") != "background" or not worker.get("home")
            or data.get("session_id") != worker.get("session_id")):
        return
    tool_id, prompt = data.get("tool_use_id"), data.get("prompt_id")
    if not all(isinstance(v, str) and v for v in (tool_id, prompt)):
        return
    from . import consent, paths
    path = _state_path(worker)
    identity = _worker_identity(worker, runtime)
    with consent._strict_locked(path):
        state = paths.read_json(path, {})
        if not isinstance(state, dict):
            state = {}
        if data.get("hook_event_name") == "PreToolUse":
            if state.get("identity") != identity or state.get("prompt_id") != prompt:
                state = {"identity": identity, "prompt_id": prompt, "calls": {}}
            calls = state["calls"]
            call = {"tool": data.get("tool_name"), "input_digest": key(data.get("tool_input"))}
            if tool_id in calls and calls[tool_id] != call:
                state["invalid"] = True
            elif tool_id not in calls and len(calls) >= MAX_OPEN_CALLS:
                state["invalid"] = True
            else:
                calls[tool_id] = call
            state["updated_at"] = time.time()
            paths.write_json(path, state)
        elif (state.get("identity") == identity and state.get("prompt_id") == prompt
              and data.get("hook_event_name") in ("PostToolUse", "PostToolUseFailure")):
            state["calls"].pop(tool_id, None)
            paths.write_json(path, state)


def _recorded(worker, data, runtime):
    from . import paths
    state = paths.read_json(_state_path(worker))
    if state is None:
        return None, False  # legacy worker: bounded transcript fallback
    if (not isinstance(state, dict) or not isinstance(state.get("calls"), dict)
            or state.get("identity") != _worker_identity(worker, runtime)
            or state.get("prompt_id") != data.get("prompt_id") or state.get("invalid")):
        return None, True
    candidates = [cid for cid, call in state.get("calls", {}).items()
                  if call.get("tool") == data.get("tool_name")
                  and call.get("input_digest") == key(data.get("tool_input"))]
    return (candidates[0] if len(candidates) == 1 else None), True


def key(identity):
    return hashlib.sha256(canonical(identity).encode()).hexdigest()


def _from_transcript(worker, data):
    home = worker.get("home")
    filename, prompt = data.get("transcript_path"), data.get("prompt_id")
    if not all(isinstance(v, str) and v for v in (home, filename, prompt)):
        return None
    home, filename = os.path.realpath(home), os.path.realpath(filename)
    if not filename.endswith(".jsonl") or os.path.commonpath((home, filename)) != home:
        return None
    try:
        with open(filename, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                return None
            offset = max(0, before.st_size - MAX_TAIL_BYTES)
            if offset:
                stream.seek(offset - 1)
                if stream.read(1) != b"\n":
                    stream.readline()
            raw = stream.read(MAX_TAIL_BYTES)
            after = os.fstat(stream.fileno())
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            return None
        current, calls, closed = None, {}, set()
        for line in raw.decode("utf-8").splitlines():
            row = json.loads(line)
            if not isinstance(row, dict) or row.get("type") not in ("user", "assistant"):
                continue
            if row.get("sessionId") != data["session_id"]:
                return None
            message = row.get("message") or {}
            content = message.get("content")
            if row["type"] == "user":
                current = row.get("promptId")
                for block in content if isinstance(content, list) else []:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        closed.add(block.get("tool_use_id"))
            elif current == prompt:
                for block in content if isinstance(content, list) else []:
                    if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("id"):
                        calls[block["id"]] = block
        if current != prompt:
            return None
        matches = [cid for cid, call in calls.items() if cid not in closed
                   and call.get("name") == data.get("tool_name")
                   and canonical(call.get("input")) == canonical(data.get("tool_input"))]
        return matches[0] if len(matches) == 1 else None
    except (OSError, ValueError, TypeError, UnicodeError):
        return None
