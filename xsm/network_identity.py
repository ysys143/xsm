"""Opaque remote conversation identities; never invent local filesystem homes."""
import re

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_CID = re.compile(r"[A-Za-z0-9_-]{1,160}\Z")


def endpoint(record):
    if not isinstance(record, dict) or record.get("runtime") not in ("codex", "claude"):
        raise ValueError("remote native endpoint required")
    if record.get("home") is not None:
        raise ValueError("remote endpoint must not carry a private home")
    if not all(isinstance(record.get(k), str) and _HEX.fullmatch(record[k])
               for k in ("machine", "home_id")):
        raise ValueError("remote machine key and opaque home required")
    if not isinstance(record.get("session_id"), str) or not _CID.fullmatch(record["session_id"]):
        raise ValueError("remote native conversation required")
    return {k: record[k] for k in ("machine", "runtime", "home_id", "session_id")}


def target(record):
    value = endpoint(record)
    return "net:" + ":".join(value[k] for k in ("machine", "runtime", "home_id", "session_id"))


def parse_target(value):
    if not isinstance(value, str) or not value.startswith("net:"):
        return None
    parts = value.split(":")
    if len(parts) != 5:
        raise ValueError("invalid remote target")
    return endpoint(dict(zip(("machine", "runtime", "home_id", "session_id"), parts[1:])))
