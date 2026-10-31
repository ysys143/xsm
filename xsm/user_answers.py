"""Read native Codex user evidence; never record or apply a permission.

``me`` must be the caller's exact runtime/home/session_id record, not a cwd
guess. Explicit provisional/cwd/neighbor identities are rejected. Only a
bounded first metadata line and bounded tail are read, with no transcript
search. Missing evidence fails closed. This is evidence inside the local uid
boundary, not authentication against a process that can rewrite native files.
"""
from __future__ import annotations

import json
import math
import os
import re
import stat
from datetime import datetime, timezone

from . import envelope, registry

TAIL_BYTES = 256 * 1024
MAX_TAIL_BYTES = 2 * 1024 * 1024
# Native session_meta embeds base instructions and can exceed 16 KiB.
# This separate bound is not a forward scan of transcript messages.
META_BYTES = 256 * 1024
_REPLY = re.compile(
    r"\A<send_user_message_question_reply>\s*(.*?)\s*"
    r"</send_user_message_question_reply>\Z", re.S)
_CONTROL = re.compile(
    r"\A<(?P<tag>codex_internal_context|system-reminder|task-notification|"
    r"environment_context|turn_aborted|user_shell_command|subagent_notification|"
    r"hook_prompt)>(?:(?!</(?P=tag)>).)*</(?P=tag)>\Z", re.S)
_GOAL_CONTROL = re.compile(
    r'\A<codex_internal_context source="goal">(?:(?!</codex_internal_context>).)*</codex_internal_context>\Z', re.S)


def _known_injection(text):
    """Only a complete known control/peer envelope is safe to skip.

    A peer marker mentioned inside user prose, unknown tags, partial controls,
    mixed control/user messages and invalid content remain conservative barriers.
    Text wrappers are evidence within the same local uid boundary as the rollout.
    """
    if not isinstance(text, str):
        return False
    text = text.strip()
    return bool(_CONTROL.fullmatch(text) or _GOAL_CONTROL.fullmatch(text)) or envelope.parse(text).peer


def _epoch(value):
    if isinstance(value, bool):
        return None
    try:
        if isinstance(value, (int, float)):
            result = float(value)
        elif isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return None
            result = parsed.astimezone(timezone.utc).timestamp()
        else:
            return None
        return result if math.isfinite(result) else None
    except (ValueError, OverflowError, OSError):
        return None


def _user_text(row):
    """(is native user, text); invalid user content is still a barrier."""
    payload = row.get("payload")
    if not isinstance(payload, dict):
        return False, None
    if row.get("type") == "response_item" and payload.get("type") == "message" \
            and payload.get("role") == "user":
        blocks = payload.get("content")
        if not isinstance(blocks, list) or not blocks or any(
                not isinstance(b, dict) or b.get("type") != "input_text"
                or not isinstance(b.get("text"), str) for b in blocks):
            return True, None
        return True, "\n".join(b["text"] for b in blocks)
    if row.get("type") == "event_msg" and payload.get("type") == "user_message":
        # Native event has no role field: user_message is its role evidence.
        if payload.get("role") in ("assistant", "tool", "developer", "system"):
            return False, None
        if payload.get("role", "user") != "user":
            return True, None
        return True, payload.get("message")
    return False, None


def _answer(text, request, question=None):
    if not isinstance(text, str) or not text.strip():
        return None
    text = text.strip()
    if envelope.looks_like_peer(text) or envelope.parse(text).peer:
        return None
    match = _REPLY.fullmatch(text)
    if not match:
        # Harness wrappers and slash commands are not a person's free reply.
        if request is not None or text.startswith(("<", "$xsm", "/")):
            return None
        return {"text": text, "answer": text, "question": None,
                "questionItemId": None, "answers": []}
    try:
        items = json.loads(match.group(1))
    except ValueError:
        return None
    if not isinstance(items, list) or not items:
        return None
    for item in items:
        if not isinstance(item, dict) or any(
                not isinstance(item.get(key), str) or not item[key].strip()
                for key in ("questionItemId", "answer", "question")):
            return None
    if request is not None:
        items = [item for item in items if item["questionItemId"] == request]
    if question is not None:
        items = [item for item in items if item["question"] == question]
    if not items or len({item["questionItemId"] for item in items}) != 1:
        return None
    if question is not None and len(items) != 1:
        return None  # duplicate native evidence for the same exact question
    kept = [{key: item[key] for key in ("questionItemId", "answer", "question")}
            for item in items]
    return {"text": "; ".join(i["question"] + " -> " + i["answer"] for i in kept),
            "questionItemId": kept[0]["questionItemId"],
            "answer": "\n".join(i["answer"] for i in kept),
            "question": "\n".join(i["question"] for i in kept), "answers": kept}


def read_answer(me, request=None, since=None, *, tail_bytes=TAIL_BYTES, latest_only=False, question=None):
    """Return native user evidence, or None (no writes or consumption).

    request is an exact questionItemId string. since is an inclusive Unix
    epoch or timezone-aware ISO timestamp. At least one bound is required;
    plain replies require since, structured replies must match request when
    supplied. Without request, only the latest native user message is eligible.
    With request, the newest matching structured answer in the bounded tail
    is eligible even if a newer user message exists (historical/research mode).
    Permission importers MUST use latest_only=True: with request, any subsequent
    actual user message blocks readback. Assistant/tool records and complete
    known peer/control envelopes do not supersede a user's answer; unknown or
    malformed user content blocks it conservatively. File order determines
    succession even when native timestamps are equal. The coordinator MUST
    check TTL, non-consumption and target/question binding before applying it.
    No user instruction is promoted into approval here. ``timestamp``
    preserves the native timestamp; ``t`` is its epoch. ``source_path``,
    ``native_type`` and ``native_role`` identify the native evidence. tail_bytes
    is a positive integer capped at 2 MiB (invalid values fail closed). The first
    metadata line is checked separately, even when outside the tail; filenames
    and the registry's DB lookup alone are never treated as session evidence.
    """
    if not isinstance(me, dict) or me.get("runtime") != "codex" \
            or me.get("certainty") == "provisional" \
            or me.get("basis") in ("cwd", "neighbor", "none"):
        return None
    home, session = me.get("home"), me.get("session_id")
    if not isinstance(home, str) or not home or not isinstance(session, str) or not session:
        return None
    if request is not None and (not isinstance(request, str) or not request.strip()):
        return None
    if not isinstance(latest_only, bool):
        return None
    if isinstance(tail_bytes, bool) or not isinstance(tail_bytes, int) \
            or not 0 < tail_bytes <= MAX_TAIL_BYTES:
        return None
    bound = _epoch(since) if since is not None else None
    if (since is not None and bound is None) or (request is None and bound is None):
        return None
    home = os.path.realpath(os.path.expanduser(home))
    try:
        path = registry.codex_rollout(home, session)
        if not path:
            return None
        path = os.path.realpath(path)
        if os.path.commonpath((home, path)) != home:
            return None
        with open(path, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                return None
            head = stream.readline(META_BYTES + 1)
            if len(head) > META_BYTES or not head.endswith(b"\n"):
                return None
            meta = json.loads(head)
            if not isinstance(meta, dict) or meta.get("type") != "session_meta" \
                    or not isinstance(meta.get("payload"), dict) \
                    or meta["payload"].get("id") != session:
                return None
            start = max(len(head), before.st_size - tail_bytes)
            stream.seek(start - 1)
            boundary = stream.read(1) == b"\n"
            tail = stream.read(min(tail_bytes, before.st_size - start))
            after = os.fstat(stream.fileno())
            # Concurrent truncation/rewrite/append is retried by the caller.
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != \
                    (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                return None
        if not boundary:
            tail = tail.partition(b"\n")[2]
        if tail and not tail.endswith(b"\n"):
            return None
        users = []
        for line in tail.splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                return None
            if row.get("type") == "session_meta":
                if not isinstance(row.get("payload"), dict) or row["payload"].get("id") != session:
                    return None
            user, text = _user_text(row)
            if user:
                users.append((row, text))
        if not users:
            return None
        candidates = reversed(users) if request is not None else users[-1:]
        for row, text in candidates:
            if latest_only and request is not None and _known_injection(text):
                continue
            answer = _answer(text, request, question)
            if answer is None:
                if latest_only and request is not None:
                    return None
                continue
            timestamp = row.get("timestamp")
            epoch = _epoch(timestamp)
            if epoch is None or (bound is not None and epoch < bound):
                return None
            answer.update(timestamp=timestamp, t=epoch, source_path=path,
                          native_role="user", native_type=row["type"],
                          native_payload_type=row["payload"]["type"],
                          native_role_source=("payload.role" if row["type"] == "response_item"
                                              else "payload.type=user_message"),
                          runtime="codex", home=home, session_id=session)
            return answer
        return None
    except (OSError, ValueError, TypeError, RecursionError):
        return None
