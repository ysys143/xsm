"""Observe actual pair traffic; throttle only with explicitly supplied limits.

``observe`` is a pure evaluation over caller-owned local observations. Append
its result to that journal under the caller's existing lock; separate CLI/hook
processes must use shared history, not a fresh process-local counter. Keep
observations for at least the configured window. History is transport evidence,
never fields accepted from a peer body. This module performs no policy reads,
permission changes, task completion, delivery or automatic replies. ``journal``
owns the shared evidence file; ``inbound`` adds explicit config policy and an
unknown result when policy/state cannot be established.

The default is observation only, including for unknown/native peers. The
60-second diagnostic window is not a blocking default. Strict mode requires a
Limits instance with at least one explicit threshold. A throttle retains the
request id and caller's recovery locator; the original request must already be
recoverable there. Persistence failures propagate from the caller and must not
be converted into success or an empty history. An empty history is valid only
when the caller knows this is a new journal.

Counters are per directed sender/recipient handle, never ancestry, task attempts
or total review turns. Repetition hashes full original body bytes and is distinct
from rate, duplicate request ids and independent N:N conversations. Source and
approval prose cannot disable a limit or confer permissions.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
import re
import time
import os
import json
import hashlib
import fcntl
import stat

from .provenance import body_sha256, _body_bytes

__all__ = ["Limits", "AbuseStateError", "observe", "endpoint", "journal", "inbound"]

OBSERVATION_WINDOW = 60.0
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_JOURNAL_MARK = b"xsm-traffic-v1\n"


def _private_open(filename, flags):
    fd = os.open(filename, flags | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise AbuseStateError("traffic state must be a UID-private regular file")
    except BaseException:
        os.close(fd)
        raise
    return fd


def endpoint(record):
    """Opaque complete native endpoint, independent of names and ancestry."""
    from .handoff import _identity
    raw = json.dumps(_identity(record), sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def journal(sender, recipient, body, *, request_id, recovery, mode="observe", limits=None, now=None):
    """Persist traffic under a pair lock before returning a limiter verdict.

    Production callers use observation mode. Strict activation requires explicit
    policy and thresholds from the caller; no new blocking default is inferred.
    Originals live at recovery, not here. Corrupt evidence raises rather than
    silently resetting counters or granting communication.
    """
    from . import paths
    sender_id, recipient_id = endpoint(sender), endpoint(recipient)
    pair = hashlib.sha256((sender_id + recipient_id).encode("ascii")).hexdigest()
    folder = paths.path("traffic")
    os.makedirs(folder, mode=0o700, exist_ok=True)
    fd = _private_open(os.path.join(folder, pair + ".lock"), os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        filename = os.path.join(folder, pair + ".json")
        try:
            history_fd = _private_open(filename, os.O_RDONLY)
            with os.fdopen(history_fd, "r", encoding="utf-8") as stream:
                history = json.load(stream)
        except FileNotFoundError:
            if os.read(fd, len(_JOURNAL_MARK)):
                raise AbuseStateError("traffic journal was deleted after initialization")
            history = []
        except (ValueError, OSError) as exc:
            raise AbuseStateError("traffic journal unavailable: " + type(exc).__name__) from exc
        if not isinstance(history, list):
            raise AbuseStateError("traffic journal must be an array")
        result = observe(sender_id, recipient_id, body, request_id=request_id,
                         recovery=recovery, history=history, mode=mode, limits=limits, now=now)
        paths.write_json(filename, history + [result])
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, _JOURNAL_MARK)
        os.ftruncate(fd, len(_JOURNAL_MARK))
        return result
    finally:
        os.close(fd)


def _unknown(body, request_id, recovery, mode, reason, error):
    try:
        digest, size = body_sha256(body), len(_body_bytes(body))
    except (TypeError, ValueError):
        digest, size = None, None
    strict = mode == "strict"
    return {"allowed": not strict, "status": "unknown", "retry_after": None,
            "mode": mode, "request_id": request_id, "recovery": recovery,
            "body_sha256": digest, "body_bytes": size, "task_outcome": None,
            "signals": ["traffic-unknown"], "violations": ["traffic-unknown"] if strict else [],
            "reason": reason, "error": type(error).__name__, "journal_status": "unknown"}


def inbound(sender, recipient, body, *, request_id, recovery, cfg=None, now=None):
    """Evaluate and persist pair traffic without changing a scope, request or task.

    allowed=True only means this traffic limiter does not block: callers still
    apply their existing scope/deny gate. Unknown strict evidence blocks; unknown
    observe evidence is diagnostic. recovery is retained verbatim and never run.
    No threshold or strict policy is enabled globally by this helper.

    L2/Low: the existing journal scan is O(n) and history grows without a bound.
    Retention policy is deliberately unchanged (D10 remains a user decision).
    """
    from . import config
    mode = "strict" if (isinstance(cfg, dict) and isinstance(cfg.get("traffic_control"), dict)
                         and cfg["traffic_control"].get("mode") == "strict") else "observe"
    try:
        selected = config.traffic_policy(cfg)
        policy = selected["policy"]
        mode = policy["mode"]
        if selected["error"]:
            return _unknown(body, request_id, recovery, mode, "traffic-policy-invalid",
                            config.PolicyError(selected["error"]))
        limits = None
        if any(key in policy for key in ("window_seconds", "max_messages", "max_same_body")):
            limits = Limits(policy.get("window_seconds", OBSERVATION_WINDOW),
                            max_messages=policy.get("max_messages"), max_same_body=policy.get("max_same_body"))
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        return _unknown(body, request_id, recovery, mode, "traffic-policy-unavailable", exc)
    try:
        result = journal(sender, recipient, body, request_id=request_id, recovery=recovery,
                         mode=mode, limits=limits, now=now)
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as exc:
        return _unknown(body, request_id, recovery, mode, "traffic-journal-unavailable", exc)
    return dict(result, policy_source=selected["source"], policy_error=None, journal_status="recorded")


class AbuseStateError(ValueError):
    """Local history is unusable; do not silently replace it with open defaults."""


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(label + " must be a finite number")
    try:
        valid = math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(label + " must be a finite number")
    return value


def _identifier(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " must be a nonempty string")
    return value


@dataclass(frozen=True)
class Limits:
    window_seconds: float
    max_messages: int | None = None
    max_same_body: int | None = None

    def __post_init__(self):
        if _number(self.window_seconds, "window_seconds") <= 0:
            raise ValueError("window_seconds must be positive")
        for name in ("max_messages", "max_same_body"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value <= 0):
                raise ValueError(name + " must be a positive integer or None")


def _event(row, now):
    if not isinstance(row, Mapping):
        raise AbuseStateError("observation must be a mapping")
    try:
        if type(row["version"]) is not int or row["version"] != 1:
            raise ValueError("unsupported observation version")
        for name in ("sender", "recipient", "request_id", "recovery"):
            _identifier(row[name], name)
        stamp = _number(row["at"], "observation timestamp")
        if stamp > now:
            raise ValueError("observation timestamp is ahead of the local clock")
        if not isinstance(row["body_sha256"], str) or not _SHA256.fullmatch(row["body_sha256"]):
            raise ValueError("invalid original body digest")
    except (KeyError, TypeError, ValueError) as exc:
        raise AbuseStateError("invalid local observation: " + str(exc)) from exc
    return row


def _retry_after(stamps, limit, now, window):
    # A retried request is itself a new traffic attempt: leave room for it.
    return max(0.0, sorted(stamps)[len(stamps) - limit] + window - now)


def observe(sender: str, recipient: str, body: str | bytes, *, request_id: str,
            recovery: str, history=(), mode: str = "observe",
            limits: Limits | None = None, now: float | None = None) -> dict:
    """Return a journal-ready observation, without changing history or a task.

    ``allowed`` means only that this limiter does not throttle delivery; it is
    not permission to send. The normal scope/deny/strict gate still applies.
    ``task_outcome`` is always None, even for throttles. ``recovery`` is an
    opaque local locator, never executed here. At the window's left boundary
    an event expires; invalid/future history raises instead of opening a limit.
    """
    if mode not in ("observe", "strict"):
        raise ValueError("mode must be observe or strict")
    if limits is not None and not isinstance(limits, Limits):
        raise TypeError("limits must be a Limits instance")
    if mode == "strict" and (limits is None or
                             (limits.max_messages is None and limits.max_same_body is None)):
        raise ValueError("strict requires explicit limits")
    for value, label in ((sender, "sender"), (recipient, "recipient"),
                         (request_id, "request_id"), (recovery, "recovery")):
        _identifier(value, label)
    at = _number(time.time() if now is None else now, "now")
    window = limits.window_seconds if limits is not None else OBSERVATION_WINDOW
    digest = body_sha256(body)
    matching = []
    content_conflict = False
    # Check the entire supplied journal, including expired rows: corruption is
    # evidence loss, not an excuse to substitute an empty/open observation set.
    for candidate in history:
        row = _event(candidate, at)
        if row["sender"] == sender and row["recipient"] == recipient:
            if row["request_id"] == request_id and row["body_sha256"] != digest:
                content_conflict = True
            if row["at"] > at - window:
                matching.append(row)
    stamps = [row["at"] for row in matching] + [at]
    same = [row["at"] for row in matching if row["body_sha256"] == digest] + [at]
    duplicates = 1 + sum(row["request_id"] == request_id for row in matching)
    signals = []
    if len(same) > 1:
        signals.append("repeated-body")
    if duplicates > 1:
        signals.append("duplicate-request")
    if content_conflict:
        # Request identity validation belongs to the delivery gate. An
        # observation must not introduce an implicit new rejection policy.
        signals.append("request-content-conflict")
    violations = []
    waits = []
    if limits is not None:
        for code, times, maximum in (("rate-limit", stamps, limits.max_messages),
                                     ("repeated-body-limit", same, limits.max_same_body)):
            if maximum is not None and len(times) > maximum:
                violations.append(code)
                waits.append(_retry_after(times, maximum, at, window))
    throttled = mode == "strict" and bool(violations)
    return {"version": 1, "at": at, "sender": sender, "recipient": recipient,
            "request_id": request_id, "recovery": recovery, "body_sha256": digest,
            "body_bytes": len(_body_bytes(body)), "mode": mode,
            "window_seconds": window, "message_count": len(stamps),
            "same_body_count": len(same), "request_count": duplicates,
            "rate_per_second": len(stamps) / window, "signals": signals,
            "violations": violations, "allowed": not throttled,
            "status": "rate-limited" if throttled else "observed",
            "retry_after": max(waits) if throttled else 0.0, "task_outcome": None}
