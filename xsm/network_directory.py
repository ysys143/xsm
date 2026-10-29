"""Remote discovery metadata and operator-verified repository bindings.

This module does not authenticate callers, admit members, grant session rights,
or expose bind over RPC. The coordinator supplies an authenticated machine key.
local_candidates returns a list; invalid/unavailable policy fails closed.
resolve_local accepts the full public handle, including generation, and returns
a private current registry record or None. It is not an authorization decision:
the coordinator must independently recheck the caller's visibility/session rights.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from . import config, directory, probe, registry

MAX_MAP_BYTES = 512 * 1024
MAX_REPOSITORIES = 1024
MAX_PEERS = 128
_KEY = re.compile(r"[0-9a-f]{64}\Z")
_REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}\Z")
_HANDLE = {"machine", "runtime", "home_id", "session_id", "generation"}
_GENERATION_FIELDS = ("pid", "lstart", "mcp_pid", "mcp_lstart", "native_start", "app_server")
_RESOLVE_FIELDS = _GENERATION_FIELDS + ("cwd", "ended_at", "end_reason", "excluded", "registered",
                                        "uid", "machine", "origin", "certainty", "identity_certainty",
                                        "basis", "identity_basis", "ref")
_METADATA = ("ref", "name", "title", "name_source", "name_freshness", "branch",
             "summary", "todo", "activity", "state", "receive")


class RepositoryMapError(ValueError):
    """Stable local configuration errors, without private path contents."""


def _key(value):
    return isinstance(value, str) and _KEY.fullmatch(value) is not None


def _repository(value):
    return isinstance(value, str) and _REPOSITORY.fullmatch(value) is not None


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(value):
    return hashlib.sha256(_json(value)).hexdigest()


def public_endpoint(record, machine_id):
    """Opaque exact native key, never a display name, IP, home path or pid."""
    if not _key(machine_id) or not registry._registered_pointer(record):
        return None
    with probe.quick():
        endpoint = directory._endpoint(record)
        if endpoint is None or record.get("remote") \
                or not directory._local_machine(record.get("machine")) \
                or not directory._local_machine(record.get("origin")) \
                or record.get("identity_certainty") == "provisional" \
                or record.get("identity_basis") in ("cwd", "neighbor", "none"):
            return None
        # Missing execution identity cannot safely distinguish a resumed process.
        if type(record.get("pid")) is not int or record["pid"] <= 0 \
                or not isinstance(record.get("lstart"), str) or not record["lstart"]:
            return None
        try:
            generation = _digest({"endpoint": endpoint,
                                  "execution": {k: record.get(k) for k in _GENERATION_FIELDS}})
        except (ValueError, TypeError, RecursionError):
            return None
        return {"machine": machine_id, "runtime": endpoint["runtime"],
                "home_id": hashlib.sha256(endpoint["home"].encode()).hexdigest(),
                "session_id": endpoint["session_id"], "generation": generation}


def _common(local_path):
    try:
        local_path = os.fspath(local_path)
    except TypeError:
        return None
    if not isinstance(local_path, str) or any(ord(c) < 32 for c in local_path):
        return None
    canonical = directory._real(local_path)
    if not canonical:
        return None
    out = probe.git(canonical, "rev-parse", "--git-common-dir")
    if not isinstance(out, str) or len(out) > 4096 or len(out.strip().splitlines()) != 1:
        return None
    value = out.strip()
    common = directory._real(value if os.path.isabs(value) else os.path.join(canonical, value))
    if not common:
        return None
    info = probe.bounded(os.stat, common, folder=canonical)
    if info is None or not stat.S_ISDIR(info.st_mode):
        return None
    return common, info.st_dev, info.st_ino


def _pairs(items):
    out = {}
    for key, value in items:
        if key in out:
            raise RepositoryMapError("invalid_repository_map")
        out[key] = value
    return out


def _invalid_number(_):
    raise RepositoryMapError("invalid_repository_map")


class RepositoryMap:
    """Local operator bindings keyed by actual Git common dir and inode.

    for_local returns the repository ID or None. Supplying peer_machine also
    requires an explicit grant to that public key; no wildcard/name/URL match.
    Reads fail closed and do not repair malformed data. bind raises on invalid
    data and serializes complete read/modify/atomic-replace operations.
    """

    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / "repositories.json"

    @contextmanager
    def _locked(self, writing=False):
        if writing:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() \
                or stat.S_IMODE(info.st_mode) != 0o700:
            raise RepositoryMapError("non_private_repository_map")
        fd = os.open(self.root / "repositories.lock", os.O_CREAT | os.O_RDWR
                     | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            self._private(os.fstat(fd))
            fcntl.flock(fd, fcntl.LOCK_EX if writing else fcntl.LOCK_SH | fcntl.LOCK_NB)
            yield
        finally:
            os.close(fd)

    @staticmethod
    def _private(info):
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() \
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1:
            raise RepositoryMapError("non_private_repository_map")

    @staticmethod
    def _validate(state):
        if not isinstance(state, dict) or set(state) != {"version", "repositories"} \
                or type(state["version"]) is not int or state["version"] != 1 \
                or not isinstance(state["repositories"], list) \
                or len(state["repositories"]) > MAX_REPOSITORIES:
            raise RepositoryMapError("invalid_repository_map")
        seen = set()
        for item in state["repositories"]:
            if not isinstance(item, dict) \
                    or set(item) != {"common_dir", "device", "inode", "repository_id", "peer_keys"}:
                raise RepositoryMapError("invalid_repository_map")
            common = item["common_dir"]
            peers = item["peer_keys"]
            if not isinstance(common, str) or not os.path.isabs(common) or len(common) > 4096 \
                    or any(ord(c) < 32 for c in common) or os.path.normpath(common) != common \
                    or common in seen or not _repository(item["repository_id"]) \
                    or type(item["device"]) is not int or item["device"] < 0 \
                    or type(item["inode"]) is not int or item["inode"] <= 0 \
                    or not isinstance(peers, list) or len(peers) > MAX_PEERS \
                    or any(not _key(peer) for peer in peers) or len(set(peers)) != len(peers):
                raise RepositoryMapError("invalid_repository_map")
            seen.add(common)
        return state

    def _read(self):
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
        except FileNotFoundError:
            return {"version": 1, "repositories": []}
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            self._private(before)
            if before.st_size > MAX_MAP_BYTES:
                raise RepositoryMapError("repository_map_too_large")
            data = stream.read(MAX_MAP_BYTES + 1)
            after = os.fstat(stream.fileno())
            if len(data) > MAX_MAP_BYTES or directory._signature(before) != directory._signature(after) \
                    or directory._signature(after) != directory._signature(os.stat(self.path, follow_symlinks=False)):
                raise RepositoryMapError("invalid_repository_map")
        try:
            state = json.loads(data, object_pairs_hook=_pairs, parse_constant=_invalid_number)
        except (ValueError, UnicodeError, RecursionError):
            raise RepositoryMapError("invalid_repository_map") from None
        return self._validate(state)

    def _snapshot(self):
        try:
            with self._locked():
                return self._read()
        except FileNotFoundError:
            # Nothing has been mapped yet. Read-only discovery/admission must
            # neither create a store nor classify this as an IO outage.
            return {"version": 1, "repositories": []}

    def bind(self, local_path, repository_id, peer_keys):
        """Operator-only mutation. The network coordinator must not route to it."""
        if not _repository(repository_id) or not isinstance(peer_keys, (list, tuple)) \
                or len(peer_keys) > MAX_PEERS or any(not _key(peer) for peer in peer_keys):
            raise RepositoryMapError("invalid_repository_binding")
        with probe.quick():
            common = _common(local_path)
        if common is None:
            raise RepositoryMapError("repository_unverified")
        item = {"common_dir": common[0], "device": common[1], "inode": common[2],
                "repository_id": repository_id, "peer_keys": sorted(set(peer_keys))}
        with self._locked(writing=True):
            state = self._read()
            state["repositories"] = [r for r in state["repositories"] if r["common_dir"] != common[0]] + [item]
            self._validate(state)
            data = _json(state)
            if len(data) > MAX_MAP_BYTES:
                raise RepositoryMapError("repository_map_too_large")
            fd, temporary = tempfile.mkstemp(prefix=".repositories-", dir=self.root)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
                directory_fd = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return dict(item)

    def for_local(self, local_path, peer_machine=None):
        if peer_machine is not None and not _key(peer_machine):
            return None
        with probe.quick():
            state = probe.bounded(self._snapshot)
            if state is None:
                return None
            if not state["repositories"] or peer_machine is not None and not any(
                    peer_machine in row["peer_keys"] for row in state["repositories"]):
                return None
            common = _common(local_path)
            if common is None:
                return None
            for item in state["repositories"]:
                if (item["common_dir"], item["device"], item["inode"]) == common \
                        and (peer_machine is None or peer_machine in item["peer_keys"]):
                    return item["repository_id"]
        return None

    def allows(self, peer_machine, repository_id, local_path):
        return bool(_key(peer_machine) and _repository(repository_id)
                    and self.for_local(local_path, peer_machine) == repository_id)


def _visible_record(record):
    endpoint = directory._endpoint(record)
    cfg = directory._settings()
    return bool(registry._registered_pointer(record) and endpoint
                and directory._allowed(record, endpoint) and isinstance(cfg, dict)
                and isinstance(cfg.get("deny", []), list) and record.get("ref") not in cfg.get("deny", [])
                and directory.exclusion_status(record.get("cwd"), cfg.get(directory.EXCLUSIONS_KEY, [])) == "included")


def _fresh_privacy(record, endpoint, cfg, homes, original_cwd):
    """Do not reuse realpath/home-policy memos across the final selection check."""
    real = lambda path: probe.bounded(directory._canonical, path, folder=path)
    if not isinstance(cfg, dict) or not isinstance(homes, list) \
            or not isinstance(cfg.get("deny", []), list) or record.get("ref") in cfg.get("deny", []):
        return False
    home, cwd = real(record.get("home")), real(record.get("cwd"))
    if home != endpoint["home"] or cwd is None or cwd != original_cwd:
        return False
    roots = cfg.get(directory.EXCLUSIONS_KEY, [])
    if not isinstance(roots, (list, tuple)):
        return False
    canonical_roots = [real(root) if isinstance(root, str) and not any(c in root for c in "*?[")
                       else None for root in roots]
    return bool(directory.exclusion_status(cwd, canonical_roots) == "included"
                and any(isinstance(h, dict) and h.get("runtime") == endpoint["runtime"]
                        and h.get("enabled", True) is not False and real(h.get("path")) == home for h in homes)
                and probe.bounded(directory._owned_home, home, folder=home, default=False) is True)


def local_candidates(origin_machine, caller_repository_id, mappings, local_machine_id,
                     machine=None, work=None, branch=None):
    """Sanitized candidates only: publication OR an explicit peer/repository grant.

    The real local record is passed unchanged to directory.discover solely after
    visibility is established; the remote caller is never fabricated as local.
    """
    if not _key(origin_machine) or not _key(local_machine_id) \
            or machine is not None and machine != local_machine_id \
            or any(value is not None and (not isinstance(value, str) or not value.strip())
                   for value in (work, branch)):
        return []
    result, seen = [], set()
    with probe.quick():
        records = probe.bounded(registry.raw_records)
        if not isinstance(records, list):
            return []
        records = sorted((r for r in records if isinstance(r, dict)),
                         key=lambda r: directory._timestamp(r.get("updated")) or 0, reverse=True)
        for record in records:
            handle = public_endpoint(record, local_machine_id)
            if not handle or not _visible_record(record):
                continue
            key = tuple(handle[k] for k in ("machine", "runtime", "home_id", "session_id"))
            if key in seen:
                continue
            seen.add(key)
            published = directory.is_published(record)
            same = bool(isinstance(mappings, RepositoryMap) and _repository(caller_repository_id)
                        and mappings.allows(origin_machine, caller_repository_id, record.get("cwd")))
            if not published and not same:
                continue
            original_cwd = directory._real(record.get("cwd"))
            # Do not replace the authenticated remote caller with an invented local
            # caller. This is the actual visible local target, for metadata only.
            found = directory.discover(record, records=[record], work=work, branch=branch)
            candidates = found.get("candidates", [])
            if len(candidates) != 1:
                continue
            latest = probe.bounded(registry.raw_records)
            if not isinstance(latest, list):
                continue
            current = [r for r in latest if public_endpoint(r, local_machine_id) == handle]
            if len(current) != 1 or any(record.get(k) != current[0].get(k) for k in _RESOLVE_FIELDS) \
                    or not _visible_record(current[0]):
                continue
            current = current[0]
            cfg, homes = probe.bounded(directory._read_settings), probe.bounded(config.homes)
            if not _fresh_privacy(current, directory._endpoint(record), cfg, homes, original_cwd):
                continue
            # Visibility may have been revoked while native metadata was read.
            published = directory.is_published(current)
            same = bool(same and mappings.allows(origin_machine, caller_repository_id, current.get("cwd")))
            if not published and not same:
                continue
            source = candidates[0]
            candidate = {k: copy.deepcopy(source[k]) for k in _METADATA if k in source}
            candidate.update(id=_digest(handle), target="net:{machine}:{runtime}:{home_id}:{session_id}".format(**handle),
                             handle=handle, machine=local_machine_id, runtime=handle["runtime"], is_self=False,
                             discovery_basis=(["published"] if published else []) + (["same_repository"] if same else []),
                             repository=caller_repository_id if same else None,
                             repository_id=caller_repository_id if same else None,
                             same_repository=True if same else None,
                             repository_status="verified" if same else "unknown")
            candidate["doing"] = copy.deepcopy(candidate.get("summary"))
            result.append(candidate)
    return result


def resolve_local(public_handle, local_machine_id):
    """Exact current native record, not a name/ref/new-conversation fallback.

    Privacy means current exclusion, deny, allowed local home and exact native
    identity here. Origin-dependent publication/repo and session rights remain
    the coordinator's responsibility; this function has no caller credentials.
    """
    if not _key(local_machine_id) or not isinstance(public_handle, dict) \
            or set(public_handle) != _HANDLE or public_handle.get("machine") != local_machine_id \
            or not _key(public_handle.get("home_id")) or not _key(public_handle.get("generation")):
        return None
    with probe.quick():
        rows = probe.bounded(registry.raw_records)
        if not isinstance(rows, list):
            return None
        matches = [r for r in rows if public_endpoint(r, local_machine_id) == public_handle]
        if len(matches) != 1 or not _visible_record(matches[0]):
            return None
        raw = matches[0]
        endpoint = directory._endpoint(raw)
        original_cwd = directory._real(raw.get("cwd"))
        current = probe.bounded(registry._enrich, raw, folder=endpoint["home"])
        if not isinstance(current, dict) or public_endpoint(current, local_machine_id) != public_handle \
                or current.get("native_session_id", endpoint["session_id"]) not in (None, endpoint["session_id"]) \
                or current.get("end_reason") in ("superseded", "thread_replaced", "thread_unloaded", "worker-stopped"):
            return None
        native = probe.bounded(directory._native_identity, current, endpoint, folder=endpoint["home"])
        if native is False:
            return None
        fresh = probe.bounded(registry.raw_records)
        if not isinstance(fresh, list):
            return None
        hits = [r for r in fresh if public_endpoint(r, local_machine_id) == public_handle]
        if len(hits) != 1 or any(raw.get(k) != hits[0].get(k) for k in _RESOLVE_FIELDS):
            return None
        # Bypass cached privacy/home observations at the final selection boundary.
        cfg = probe.bounded(directory._read_settings)
        homes = probe.bounded(config.homes)
        if not _fresh_privacy(hits[0], endpoint, cfg, homes, original_cwd):
            return None
        return current
