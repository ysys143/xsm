"""P06 attachment copies, not document originals or a file-permission service.

G04/integrated delivery is a coordinator prerequisite, not established here.
product_limits() exposes the user-approved D05/D07 copy quotas/retention.
Inline fallback uses the same approved 4MiB request limit. JSON_BOUND is only
the manifest/private metadata parser bound, never the body or data packet cap.

Integration API (all callers supply an exact native identity):
  prepare_inline(caller, request_id, body, items, *, limits, previous=None)
    MCP: items contain name + exactly one of text/data/base64. No paths accepted.
  prepare_cli(caller, request_id, body, sources, *, limits, previous=None)
    CLI handler ONLY: reads with that CLI process's OS authority. Caller cwd is
    relative-path resolution, not permission. Never expose this as an MCP RPC.
    A server claiming permission via a root/cwd/string is not permission evidence;
    there is deliberately no MCP path-reading adapter without actual evidence.
  export_packet(caller, manifest_id, *, request_id, body, now=None)
    Rechecks owner/binding/copy bytes and CLI originals before export.
  export_frozen(caller, manifest_id, request_id, body, now=None)
    Explicit private snapshot reuse only; never reopens source paths and never
    claims current filesystem permission or a current original-file version.
  receive(receiver, packet, *, request_id, body, expected_reference, limits, now=None)
    Atomic copy storage; returns files-stored, NEVER body-delivered/read/applied.
    expected_reference is from the bound message, not recomputed from the packet.
  revalidate / manifest / read_copy / reference / negotiate / cleanup

Wire manifests omit source absolute paths. Originals are private metadata only;
cleanup never follows them. Storage paths use local generated IDs, never names.
Source descriptors use one opened file, component-wise O_NOFOLLOW, and fstat
before/after reads. A changed original requires a new snapshot/version. Old
copies remain independently readable until explicit cleanup.

Inline bytes were read by the caller, not verified by this server against a
claimed source path. This provenance is explicit; it cannot establish a new
filesystem permission. Shared exclusion policy applies to actual CLI sources.
"""
from __future__ import annotations

import base64
import binascii
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import errno
import fcntl
import hashlib
import json
import math
import os
import re
import stat
import time
import unicodedata
import uuid

from . import directory, paths

DIRECTORY = "file-copies"
SCHEMA = "xsm.files/v1"
JSON_BOUND = 2 * 1024 * 1024  # Structural parser bound, not a file quota.
REQUEST_BYTES = 4 * 1024 * 1024
_DELETE = re.compile(r"\A\.deleting-[0-9a-f]{32}-([0-9a-f]{32})\Z")
_STORE_ERRORS = (OSError, ValueError, TypeError, KeyError, RecursionError)


class FileError(ValueError):
    """stored=False before confirmed commit; None means post-commit IO unknown.

    Neither is permission to mark the message delivered. Retry receive with the
    same bound packet to read back a possibly committed copy after an unknown.
    """
    def __init__(self, code, message, request_id=None, stage="files"):
        super().__init__("%s: %s" % (code, message))
        self.code, self.request_id, self.stage = code, request_id, stage
        self.stored = False
        self.diagnostics = []


@dataclass(frozen=True)
class Limits:
    file_bytes: int
    total_bytes: int
    max_files: int
    quota_bytes: int
    retention_seconds: float
    inline_bytes: int

    def __post_init__(self):
        for field in ("file_bytes", "total_bytes", "max_files", "quota_bytes"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise FileError("invalid-limits", "positive explicit integer limits required")
        if type(self.inline_bytes) is not int or not 0 < self.inline_bytes <= REQUEST_BYTES:
            raise FileError("invalid-limits", "inline body limit must be within the approved 4MiB request limit")
        if isinstance(self.retention_seconds, bool) or not isinstance(self.retention_seconds, (int, float)) \
                or not math.isfinite(self.retention_seconds) or self.retention_seconds <= 0:
            raise FileError("invalid-limits", "explicit positive retention required")


def product_limits(*, inline_bytes=REQUEST_BYTES):
    """D05/D07 approved: 1MiB/file, 4MiB/bundle, 16 files, 256MiB/store, 7d.

    Inline uses the same 4MiB request limit (including original text/headers).
    JSON_BOUND applies only to manifest/private metadata, not body/data packets.
    File data uses a separate copy carrier. A full 4MiB bundle plus rendering
    overhead may not fit inline and must be explicitly refused, never truncated.
    """
    return Limits(file_bytes=1024 * 1024, total_bytes=4 * 1024 * 1024, max_files=16,
                  quota_bytes=256 * 1024 * 1024, retention_seconds=7 * 24 * 60 * 60,
                  inline_bytes=inline_bytes)


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _id(value):
    if not isinstance(value, str) or len(value) != 32 or any(c not in "0123456789abcdef" for c in value):
        raise FileError("invalid-id", "a full generated copy id is required")
    return value


def _clock(now):
    value = time.time() if now is None else now
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise FileError("invalid-time", "finite timestamp required")
    return value


def _owner(caller):
    if not isinstance(caller, dict) or caller.get("certainty") == "provisional" \
            or caller.get("basis") in ("cwd", "neighbor", "none"):
        raise FileError("caller-unverified", "exact native caller required")
    fields = [caller.get(k) for k in ("runtime", "home", "session_id")]
    if any(not isinstance(v, str) or not v.strip() for v in fields):
        raise FileError("caller-unverified", "runtime/home/session_id are required")
    if not os.path.isabs(os.path.expanduser(fields[1])):
        raise FileError("caller-unverified", "caller home must be absolute, never process cwd")
    home = os.path.realpath(os.path.expanduser(fields[1]))
    return {"runtime": fields[0], "home_id": _sha(os.fsencode(home)), "session_id": fields[2]}


def _binding(request_id, body):
    if not isinstance(request_id, str) or not request_id.strip() or not isinstance(body, str):
        raise FileError("invalid-request", "request id and exact body text required")
    try:
        return {"request_id": request_id, "body_sha256": _sha(body.encode("utf-8"))}
    except UnicodeError as exc:
        raise FileError("invalid-request", "body is not valid Unicode text", request_id) from exc


def safe_name(name):
    if not isinstance(name, str) or not name:
        raise FileError("invalid-name", "original name must be text")
    normalized = unicodedata.normalize("NFC", name)
    if normalized in (".", "..") or any(c in normalized for c in ("/", "\\", ":")) \
            or any(unicodedata.category(c).startswith("C") for c in normalized) \
            or len(normalized.encode("utf-8")) > 255:
        raise FileError("invalid-name", "name cannot contain traversal, separators or controls")
    return normalized


def _names(entries):
    seen = set()
    for item in entries:
        if not isinstance(item, dict):
            raise FileError("invalid-manifest", "file entries must be objects")
        name = safe_name(item.get("name"))
        key = name.casefold()
        if key in seen:
            raise FileError("name-collision", "duplicate names require explicit distinct aliases")
        seen.add(key)


def _signature(info):
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def _sensitive(path):
    parts = os.path.normpath(path).split(os.sep)
    name = parts[-1]
    return name in ("apikey.env", ".credentials.json") or \
        (".ssh" in parts and name.startswith("id_") and not name.endswith(".pub")) or \
        (name == "auth.json" and any(p == ".codex" or p.startswith(".codex-") for p in parts))


def _open_regular(path):
    """Open the already canonical absolute path without following any symlink."""
    fd = os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY)
    try:
        components = path.split(os.sep)[1:]
        for component in components[:-1]:
            nxt = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        result = os.open(components[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    finally:
        os.close(fd)
    return result


def _snapshot_cli(caller, source, limit):
    supplied = source.get("path") if isinstance(source, dict) else source
    if not isinstance(supplied, str) or not supplied or "\x00" in supplied:
        raise FileError("invalid-path", "CLI attachment path required")
    if not os.path.isabs(os.path.expanduser(supplied)):
        cwd = caller.get("cwd")
        if not isinstance(cwd, str) or not os.path.isabs(cwd):
            raise FileError("invalid-path", "relative paths require caller cwd")
        supplied = os.path.join(cwd, supplied)
    lexical = os.path.abspath(os.path.expanduser(supplied))
    canonical = os.path.realpath(lexical)
    if _sensitive(lexical) or _sensitive(canonical):
        raise FileError("credential-path", "credential sources cannot be attachments")
    if directory.excluded(canonical):
        raise FileError("excluded-or-unknown", "source disclosure policy is not included")
    expected = os.stat(canonical, follow_symlinks=False)
    fd = _open_regular(canonical)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise FileError("not-regular", "only regular source files are supported")
        if _signature(before) != _signature(expected):
            raise FileError("source-changed", "source changed before opening")
        if before.st_size > limit:
            raise FileError("file-too-large", "source exceeds explicit per-file limit")
        chunks, size = [], 0
        while True:
            chunk = os.read(fd, min(65536, limit + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise FileError("file-too-large", "source grew beyond explicit limit")
            chunks.append(chunk)
        after = os.fstat(fd)
        if _signature(before) != _signature(after) or os.path.realpath(lexical) != canonical \
                or _signature(os.stat(lexical)) != _signature(after):
            raise FileError("source-changed", "source changed while reading")
        data = b"".join(chunks)
    finally:
        os.close(fd)
    name = source.get("name") if isinstance(source, dict) else None
    original = os.path.basename(lexical)
    safe_name(original)
    return {"name": safe_name(name or original), "original_name": original,
            "source_version": source.get("source_version") if isinstance(source, dict) else None}, data, \
        {"path": lexical, "canonical": canonical, "signature": _signature(after)}


def _inline(item, limit):
    if not isinstance(item, dict) or set(item) - {"name", "text", "data", "base64", "source_version"}:
        raise FileError("mcp-path-unproven", "MCP accepts caller-read inline data and name only, never a server path")
    keys = set(item) & {"text", "data", "base64"}
    if len(keys) != 1:
        raise FileError("invalid-inline", "supply exactly one inline representation")
    key = next(iter(keys))
    value = item[key]
    if key == "text" and isinstance(value, str):
        if len(value) > limit:  # UTF-8 cannot be shorter than its character count.
            raise FileError("file-too-large", "inline text exceeds explicit limit")
        try:
            data = value.encode("utf-8")
        except UnicodeError as exc:
            raise FileError("invalid-inline", "inline text is not valid Unicode") from exc
    elif key == "data" and isinstance(value, bytes):
        data = value
    elif key == "base64" and isinstance(value, str):
        if len(value) > ((limit + 2) // 3) * 4:
            raise FileError("file-too-large", "base64 input exceeds explicit limit")
        try:
            data = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error):
            raise FileError("invalid-inline", "invalid base64")
    else:
        raise FileError("invalid-inline", "inline value has the wrong type")
    if len(data) > limit:
        raise FileError("file-too-large", "inline input exceeds explicit limit")
    return {"name": safe_name(item.get("name")), "original_name": item["name"],
            "source_version": item.get("source_version")}, data, None


@contextmanager
def _store():
    root = paths.path(DIRECTORY)
    os.makedirs(root, mode=0o700, exist_ok=True)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    lock = None
    try:
        if os.fstat(fd).st_uid != os.getuid():
            raise FileError("unsafe-store", "copy store is not owned by this uid")
        lock = os.open(".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield fd
    finally:
        if lock is not None:
            os.close(lock)
        os.close(fd)


@contextmanager
def _folder(parent, name, create=False):
    if create:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent)
        except FileExistsError:
            pass
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        if os.fstat(fd).st_uid != os.getuid():
            raise FileError("unsafe-store", "copy directory has another owner")
        yield fd
    finally:
        os.close(fd)


def _read_file(folder, name, bound):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > bound or info.st_nlink != 1:
            raise FileError("unsafe-store", "invalid or oversized stored copy")
        chunks, size = [], 0
        while True:
            data = os.read(fd, min(65536, bound + 1 - size))
            if not data:
                break
            chunks.append(data)
            size += len(data)
            if size > bound:
                raise FileError("copy-changed", "stored copy grew during read")
        if _signature(os.fstat(fd)) != _signature(info):
            raise FileError("copy-changed", "stored copy changed during read")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _document(folder):
    try:
        value = json.loads(_read_file(folder, "record.json", JSON_BOUND))
    except (ValueError, UnicodeError) as exc:
        raise FileError("invalid-store", "stored manifest is not readable JSON") from exc
    if not isinstance(value, dict):
        raise FileError("invalid-store", "stored manifest must be an object")
    return value


def _write_file(folder, name, data):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=folder)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError(errno.ENOSPC, "copy write made no progress")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _purge(parent, name):
    """Delete only a hidden deletion/staging namespace; never follow links."""
    with _folder(parent, name) as folder:
        for child in sorted(os.listdir(folder), key=lambda n: (n != "record.json", n)):
            if stat.S_ISDIR(os.stat(child, dir_fd=folder, follow_symlinks=False).st_mode):
                raise FileError("unsafe-store", "unexpected nested directory in copy bundle")
            os.unlink(child, dir_fd=folder)
    os.rmdir(name, dir_fd=parent)


def _remove(parent, name):
    # Rollback stages are already unpublished. Partial stages cannot enter the
    # replay namespace and retain their existing explicit orphan-age policy.
    if name.startswith(".staging-"):
        _id(name[len(".staging-"):])
        return _purge(parent, name)
    _id(name)
    tomb = ".deleting-" + uuid.uuid4().hex + "-" + name
    with _folder(parent, name) as opened:
        before = os.fstat(opened)
        os.rename(name, tomb, src_dir_fd=parent, dst_dir_fd=parent)
        moved = os.stat(tomb, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISDIR(moved.st_mode) or (before.st_dev, before.st_ino) != (moved.st_dev, moved.st_ino):
            raise FileError("unsafe-store", "deletion target changed; nothing followed")
        os.fsync(parent)  # Durable intent before the first child can disappear.
    _purge(parent, tomb)


def _diagnostic(diagnostics, kind, name, error, status="unknown"):
    # Local malformed filenames can contain undecodable/control bytes. Retain
    # their identity without letting diagnostics themselves break JSON storage.
    label = name if name.isascii() and name.isprintable() else "name-sha256:" + _sha(os.fsencode(name))
    key = (kind, label)
    if diagnostics is not None and key not in diagnostics:
        diagnostics[key] = {"kind": kind, "storage_id": label, "status": status,
                            "error": type(error).__name__ if isinstance(error, BaseException) else error,
                            "observed_at": time.time()}


def _copy_metadata(record):
    """Validate local receipt shape without opening any copied/source payload."""
    owner = record.get("owner")
    if not isinstance(owner, dict) or set(owner) != {"runtime", "home_id", "session_id"} \
            or any(not isinstance(v, str) or not v for v in owner.values()):
        raise FileError("invalid-store", "copy owner metadata missing")
    _check_manifest(record.get("manifest"))
    _clock(record.get("expires_at"))
    storage = record.get("storage")
    if not isinstance(storage, dict) or set(storage) != {e["id"] for e in record["manifest"]["files"]}:
        raise FileError("invalid-store", "copy storage mapping missing")
    for name in storage.values():
        if not isinstance(name, str) or not name.endswith(".blob"):
            raise FileError("invalid-store", "copy storage mapping is not a generated name")
        _id(name[:-5])


def _usage(root, diagnostics=None):
    """Conservative managed-file bytes, independent of manifest readability.

    Charge all regular files, renamed payloads, directory metadata and links'
    own bytes, including damaged/staging/deleting namespaces. Never open a link
    target or read source content. Unmeasurable usage is unknown, not free space.
    """
    def walk(folder):
        size = os.fstat(folder).st_size
        for child in os.listdir(folder):
            info = os.stat(child, dir_fd=folder, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                with _folder(folder, child) as nested:
                    size += walk(nested)
            else:
                size += info.st_size
        return size

    total = 0
    for kind in ("outgoing", "incoming"):
        with _folder(root, kind, create=True) as parent:
            for name in os.listdir(parent):
                try:
                    info = os.stat(name, dir_fd=parent, follow_symlinks=False)
                    if not stat.S_ISDIR(info.st_mode):
                        total += info.st_size
                        _diagnostic(diagnostics, kind, name, "non-directory-managed-entry")
                        continue
                    with _folder(parent, name) as folder:
                        total += walk(folder)
                        if diagnostics is not None and not name.startswith((".staging-", ".deleting-")):
                            try:
                                _id(name)
                                record = _document(folder)
                                _copy_metadata(record)
                            except _STORE_ERRORS as exc:
                                _diagnostic(diagnostics, kind, name, exc)
                except _STORE_ERRORS as exc:
                    _diagnostic(diagnostics, kind, name, exc)
                    unknown = FileError("quota-unknown", "managed usage cannot be measured without following unsafe paths")
                    unknown.diagnostics = list((diagnostics or {}).values())
                    raise unknown from exc
    return total


def _persist(root, kind, storage_id, record, blobs, limits, diagnostics=None):
    diagnostics = {} if diagnostics is None else diagnostics
    used = _usage(root, diagnostics)
    if diagnostics:
        record["diagnostics"] = list(diagnostics.values())
    encoded = _json(record)
    if len(encoded) > JSON_BOUND:
        raise FileError("manifest-too-large", "manifest exceeds structural bound")
    if used + sum(len(b) for b in blobs.values()) + len(encoded) > limits.quota_bytes:
        failure = FileError("quota-exceeded", "copy storage exceeds explicit byte quota")
        failure.diagnostics = list(diagnostics.values())
        raise failure
    with _folder(root, kind, create=True) as parent:
        staging = ".staging-" + uuid.uuid4().hex
        os.mkdir(staging, mode=0o700, dir_fd=parent)
        committed = False
        try:
            with _folder(parent, staging) as folder:
                opened = os.fstat(folder)
                for name, data in blobs.items():
                    _write_file(folder, name, data)
                    if _read_file(folder, name, len(data)) != data:
                        raise FileError("copy-verification-failed", "stored bytes differ from the fixed snapshot")
                _write_file(folder, "record.json", encoded)
                if _read_file(folder, "record.json", JSON_BOUND) != encoded:
                    raise FileError("copy-verification-failed", "stored manifest differs from prepared metadata")
                os.fsync(folder)
                if _usage(root) > limits.quota_bytes:
                    failure = FileError("quota-exceeded", "actual managed files exceed explicit quota")
                    failure.diagnostics = list(diagnostics.values())
                    raise failure
                try:
                    os.stat(storage_id, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise FileError("copy-conflict", "storage id already exists")
                os.rename(staging, storage_id, src_dir_fd=parent, dst_dir_fd=parent)
                current = os.stat(storage_id, dir_fd=parent, follow_symlinks=False)
                if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                    if stat.S_ISLNK(current.st_mode):
                        os.unlink(storage_id, dir_fd=parent)
                    raise FileError("store-changed", "copy bundle was replaced during commit")
                committed = True
                os.fsync(parent)
        except BaseException as exc:
            try:
                _remove(parent, staging)
            except FileNotFoundError:
                pass
            if committed and isinstance(exc, OSError):
                uncertain = FileError("storage-unknown", "copy commit needs same-id readback")
                uncertain.stored = None
                raise uncertain from exc
            raise


def _manifest_digest(value):
    return _sha(_json({k: v for k, v in value.items() if k != "sha256"}))


def _check_manifest(value, request_id=None, body=None):
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise FileError("unsupported-manifest", "unrecognized files schema")
    fields = {"schema", "id", "version", "previous", "owner", "binding", "created_at",
              "expires_at", "files", "size", "sha256"}
    if set(value) != fields:
        raise FileError("invalid-manifest", "manifest fields differ from this schema")
    try:
        if len(_json(value)) > JSON_BOUND:
            raise FileError("manifest-too-large", "manifest exceeds structural bound")
    except (TypeError, UnicodeError, RecursionError) as exc:
        raise FileError("invalid-manifest", "manifest is not serializable JSON") from exc
    _id(value.get("id"))
    if value["previous"] is not None:
        _id(value["previous"])
    if _clock(value["expires_at"]) <= _clock(value["created_at"]):
        raise FileError("invalid-manifest", "manifest lifetime must be positive")
    if not isinstance(value["owner"], dict) or set(value["owner"]) != {"runtime", "home_id", "session_id"} \
            or any(not isinstance(v, str) or not v for v in value["owner"].values()):
        raise FileError("invalid-manifest", "owner fields are invalid")
    binding = value.get("binding")
    if not isinstance(binding, dict) or set(binding) != {"request_id", "body_sha256"} \
            or not isinstance(binding["request_id"], str) or not binding["request_id"] \
            or not isinstance(binding["body_sha256"], str) or len(binding["body_sha256"]) != 64:
        raise FileError("invalid-manifest", "request binding fields invalid")
    if request_id is not None or body is not None:
        if binding != _binding(request_id, body):
            raise FileError("binding-mismatch", "copy belongs to another request/body", request_id)
    if value.get("sha256") != _manifest_digest(value):
        raise FileError("digest-mismatch", "manifest digest does not match", request_id)
    if isinstance(value.get("version"), bool) or not isinstance(value.get("version"), int) or value["version"] < 1:
        raise FileError("invalid-manifest", "invalid manifest version")
    if not isinstance(value.get("files"), list):
        raise FileError("invalid-manifest", "files must be a list")
    _names(value["files"])
    seen, total = set(), 0
    for entry in value["files"]:
        if set(entry) != {"id", "version", "name", "original_name", "source_version", "size",
                          "sha256", "copy", "input_source"}:
            raise FileError("invalid-manifest", "file fields differ from this schema")
        _id(entry.get("id"))
        if entry["id"] in seen or entry.get("copy") is not True or type(entry.get("version")) is not int \
                or entry["version"] != value["version"]:
            raise FileError("invalid-manifest", "file id/version/copy marker invalid")
        seen.add(entry["id"])
        size = entry.get("size")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise FileError("invalid-manifest", "file size invalid")
        safe_name(entry.get("original_name"))
        total += size
    if type(value.get("size")) is not int or value["size"] != total:
        raise FileError("size-mismatch", "manifest total differs from file sizes")


def _load(root, kind, storage_id, expected_owner=None):
    _id(storage_id)
    with _folder(root, kind) as parent, _folder(parent, storage_id) as folder:
        record = _document(folder)
        if not isinstance(record.get("manifest"), dict) or not isinstance(record.get("storage"), dict):
            raise FileError("invalid-store", "stored copy metadata is incomplete")
        if expected_owner is not None and record.get("owner") != expected_owner:
            raise FileError("owner-mismatch", "another caller owns these copies")
        manifest = record["manifest"]
        _check_manifest(manifest)
        binding = manifest["binding"]
        # Verify immutable digest here; the actual caller body is checked by APIs.
        if manifest.get("sha256") != _manifest_digest(manifest):
            raise FileError("digest-mismatch", "stored manifest changed")
        contents = {}
        for entry in manifest["files"]:
            name = record["storage"].get(entry["id"])
            if not isinstance(name, str) or not name.endswith(".blob") or name != _id(name[:-5]) + ".blob":
                raise FileError("invalid-store", "stored blob name is not a generated id")
            data = _read_file(folder, name, entry["size"])
            if len(data) != entry["size"] or _sha(data) != entry["sha256"]:
                raise FileError("digest-mismatch", "stored copy content changed", binding["request_id"])
            contents[entry["id"]] = data
        return record, contents


def _prepare(caller, request_id, body, items, *, limits, previous, mode, now):
    if not isinstance(limits, Limits):
        raise FileError("invalid-limits", "explicit Limits required")
    if not isinstance(items, (list, tuple)) or len(items) > limits.max_files:
        raise FileError("too-many-files", "attachment count exceeds explicit limit", request_id)
    owner, binding, now = _owner(caller), _binding(request_id, body), _clock(now)
    entries, blobs, sources, total = [], {}, {}, 0
    try:
        for item in items:
            meta, data, source = _snapshot_cli(caller, item, limits.file_bytes) if mode == "cli" else _inline(item, limits.file_bytes)
            total += len(data)
            if total > limits.total_bytes:
                raise FileError("total-too-large", "bundle exceeds explicit total limit")
            entry_id = uuid.uuid4().hex
            entry = dict(meta, id=entry_id, size=len(data), sha256=_sha(data), copy=True,
                         input_source="cli-os-read" if mode == "cli" else "caller-inline")
            if meta.get("source_version") is not None and not isinstance(meta["source_version"], str):
                raise FileError("invalid-version", "source version label must be text")
            entries.append(entry)
            blobs[entry_id + ".blob"] = data
            if source:
                sources[entry_id] = source
        _names(entries)
        with _store() as root:
            version = 1
            if previous is not None:
                prior, _ = _load(root, "outgoing", previous, owner)
                if prior["owner"] != owner:
                    raise FileError("owner-mismatch", "another caller owns the prior version")
                version = prior["manifest"]["version"] + 1
            for entry in entries:
                entry["version"] = version
            value = {"schema": SCHEMA, "id": uuid.uuid4().hex, "version": version,
                     "previous": previous, "owner": owner, "binding": binding,
                     "created_at": now, "expires_at": now + limits.retention_seconds,
                     "files": entries, "size": total}
            value["sha256"] = _manifest_digest(value)
            record = {"manifest": value, "owner": owner, "sources": sources,
                      "storage": {e["id"]: e["id"] + ".blob" for e in entries},
                      "expires_at": value["expires_at"], "limits": asdict(limits)}
            _persist(root, "outgoing", value["id"], record, blobs, limits)
            return value
    except FileError as exc:
        exc.request_id = request_id
        raise
    except OSError as exc:
        code = "disk-full" if exc.errno == errno.ENOSPC else "source-or-storage-unavailable"
        raise FileError(code, "attachment source/copy operation failed", request_id) from exc


def prepare_inline(caller, request_id, body, items, *, limits, previous=None, now=None):
    return _prepare(caller, request_id, body, items, limits=limits, previous=previous, mode="inline", now=now)


def prepare_cli(caller, request_id, body, sources, *, limits, previous=None, now=None):
    return _prepare(caller, request_id, body, sources, limits=limits, previous=previous, mode="cli", now=now)


def revalidate(caller, manifest_id, *, request_id, body, now=None):
    """Recheck frozen material and CLI sources; never replace bytes in-place."""
    with _store() as root:
        record, contents = _load(root, "outgoing", manifest_id, _owner(caller))
        value = record["manifest"]
        if record["owner"] != _owner(caller):
            raise FileError("owner-mismatch", "copy belongs to another caller", request_id)
        _check_manifest(value, request_id, body)
        if _clock(now) >= record["expires_at"]:
            raise FileError("expired", "attachment copy expired", request_id)
        try:
            for entry in value["files"]:
                source = record["sources"].get(entry["id"])
                if not source:
                    continue
                _, data, current = _snapshot_cli(caller, source["path"], entry["size"])
                if current != source or _sha(data) != entry["sha256"]:
                    raise FileError("source-changed", "prepare a new source version", request_id)
        except OSError as exc:
            raise FileError("source-changed", "original source is no longer readable", request_id) from exc
        return value


def export_packet(caller, manifest_id, *, request_id, body, now=None):
    revalidate(caller, manifest_id, request_id=request_id, body=body, now=now)
    with _store() as root:
        record, contents = _load(root, "outgoing", manifest_id, _owner(caller))
        return {"manifest": record["manifest"], "data": {
            entry_id: base64.b64encode(data).decode("ascii") for entry_id, data in contents.items()}}


def export_frozen(caller, manifest_id, request_id, body, now=None):
    """Export this caller's already-read immutable version, never its originals.

    This is private-copy read authority, not evidence that the MCP server/caller
    may currently read source paths. Fresh CLI inputs still use export_packet's
    original-path revalidation; callers must not silently substitute this API.
    """
    owner = _owner(caller)
    with _store() as root:
        record, contents = _load(root, "outgoing", manifest_id, owner)
        value = record["manifest"]
        _check_manifest(value, request_id, body)
        if value["owner"] != owner:
            raise FileError("owner-mismatch", "frozen manifest belongs to another caller", request_id)
        if _clock(now) >= min(_clock(record["expires_at"]), _clock(value["expires_at"])):
            raise FileError("expired", "frozen copy expired", request_id)
        return {"manifest": value, "data": {
            entry_id: base64.b64encode(data).decode("ascii") for entry_id, data in contents.items()}}


def reference(value):
    """Additive envelope.request_identity attachment reference; no absolute path."""
    return {"path": "manifest:" + _id(value["id"]), "id": value["id"],
            "version": value["version"], "sha256": value["sha256"], "size": value["size"]}


def _packet(packet, request_id, body, limits):
    if not isinstance(limits, Limits):
        raise FileError("invalid-limits", "explicit Limits required", request_id)
    if not isinstance(packet, dict) or set(packet) != {"manifest", "data"}:
        raise FileError("invalid-packet", "manifest and data are required", request_id)
    value, encoded = packet["manifest"], packet["data"]
    _check_manifest(value, request_id, body)
    if len(value["files"]) > limits.max_files or value["size"] > limits.total_bytes:
        raise FileError("total-too-large", "incoming bundle exceeds explicit limits", request_id)
    if not isinstance(encoded, dict) or set(encoded) != {e["id"] for e in value["files"]}:
        raise FileError("missing-files", "payload set differs from manifest", request_id)
    contents = {}
    for entry in value["files"]:
        text = encoded[entry["id"]]
        if entry["size"] > limits.file_bytes or not isinstance(text, str) \
                or len(text) > ((limits.file_bytes + 2) // 3) * 4:
            raise FileError("file-too-large", "incoming file exceeds limit", request_id)
        try:
            data = base64.b64decode(text, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise FileError("invalid-packet", "incoming base64 invalid", request_id) from exc
        if len(data) != entry["size"] or _sha(data) != entry["sha256"]:
            raise FileError("digest-mismatch", "incoming bytes differ from manifest", request_id)
        contents[entry["id"]] = data
    return value, contents


def _expect_reference(value, expected, request_id):
    if isinstance(expected, (list, tuple)) and len(expected) == 4:
        expected = dict(zip(("path", "sha256", "version", "size"), expected))
    actual = reference(value)
    if not isinstance(expected, dict) or any(expected.get(k) != actual[k]
            for k in ("path", "sha256", "version", "size")) \
            or ("id" in expected and expected["id"] != value["id"]):
        raise FileError("reference-mismatch", "packet differs from the message-bound manifest reference", request_id)


def receive(receiver, packet, *, request_id, body, limits, expected_reference=None, now=None):
    """Store all copies or raise. Idempotent readback after restart/response loss."""
    owner, now = _owner(receiver), _clock(now)
    try:
        value, contents = _packet(packet, request_id, body, limits)
        _expect_reference(value, expected_reference, request_id)
    except FileError as exc:
        exc.request_id = request_id
        raise
    if now >= value["expires_at"]:
        raise FileError("expired", "sender snapshot expired", request_id)
    diagnostics = {}
    try:
        with _store() as root:
            matched = None
            with _folder(root, "incoming", create=True) as parent:
                for sid in os.listdir(parent):
                    if sid.startswith(".staging-"):
                        continue
                    if sid.startswith(".deleting-"):
                        _diagnostic(diagnostics, "incoming", sid, "deletion-not-completed",
                                    "cleanup-pending" if _DELETE.fullmatch(sid) else "unknown")
                        continue
                    stored = None
                    try:
                        with _folder(parent, _id(sid)) as folder:
                            stored = _document(folder)
                        _copy_metadata(stored)
                    except _STORE_ERRORS as exc:
                        _diagnostic(diagnostics, "incoming", sid, exc)
                        if isinstance(stored, dict) and stored.get("owner") == owner \
                                and isinstance(stored.get("manifest"), dict) \
                                and stored["manifest"].get("id") == value["id"]:
                            raise FileError("existing-copy-unavailable", "matching receipt metadata is unknown; not silently replaced", request_id) from exc
                        continue
                    if stored.get("owner") == owner and stored["manifest"]["id"] == value["id"]:
                        if stored["manifest"] != value:
                            raise FileError("manifest-conflict", "manifest id was reused with different content", request_id)
                        if now >= stored["expires_at"]:
                            raise FileError("expired", "received copy retention expired; retry cannot renew it", request_id)
                        if matched is not None:
                            raise FileError("ambiguous-copy", "multiple prior copy receipts need readback", request_id)
                        matched = (sid, stored)
            if matched is not None:
                sid, stored = matched
                try:
                    _load(root, "incoming", sid, owner)
                except _STORE_ERRORS as exc:
                    _diagnostic(diagnostics, "incoming", sid, exc)
                    raise FileError("existing-copy-unavailable", "matching prior copy is damaged; it was not silently replaced", request_id) from exc
                history = stored.get("diagnostics") if isinstance(stored.get("diagnostics"), list) else []
                observed = list(diagnostics.values())
                evidence = observed + [r for r in history if r not in observed]
                return {"status": "files-stored", "storage_id": sid, "manifest": value,
                        "request_id": request_id, "replayed": True, "diagnostics": evidence,
                        "store_metadata": "unknown" if evidence else "known"}
            sid = uuid.uuid4().hex
            storage = {entry_id: uuid.uuid4().hex + ".blob" for entry_id in contents}
            record = {"manifest": value, "owner": owner, "storage": storage,
                      "received_at": now, "expires_at": now + limits.retention_seconds,
                      "limits": asdict(limits)}
            _persist(root, "incoming", sid, record, {storage[k]: v for k, v in contents.items()}, limits, diagnostics)
            evidence = record.get("diagnostics", [])
            return {"status": "files-stored", "storage_id": sid,
                    "manifest": value, "request_id": request_id, "replayed": False,
                    "diagnostics": evidence, "store_metadata": "unknown" if evidence else "known"}
    except FileError as exc:
        exc.request_id = request_id
        if not exc.diagnostics:
            exc.diagnostics = list(diagnostics.values())
        raise
    except OSError as exc:
        code = "disk-full" if exc.errno == errno.ENOSPC else "storage-unavailable"
        failure = FileError(code, "attachment copies were not confirmed stored", request_id)
        failure.diagnostics = list(diagnostics.values())
        raise failure from exc


def received_manifest(caller, storage_id, *, request_id, body, expected_reference, now=None):
    """Active receive/readback proof; unlike audit reads, recheck both expiries."""
    with _store() as root:
        record, _ = _load(root, "incoming", storage_id, _owner(caller))
        value = record["manifest"]
        _check_manifest(value, request_id, body)
        _expect_reference(value, expected_reference, request_id)
        if _clock(now) >= min(record["expires_at"], value["expires_at"]):
            raise FileError("expired", "received copies are no longer active", request_id)
        return value


def manifest(caller, storage_id, *, incoming=False):
    with _store() as root:
        record, _ = _load(root, "incoming" if incoming else "outgoing", storage_id, _owner(caller))
        if record["owner"] != _owner(caller):
            raise FileError("owner-mismatch", "another caller owns these copies")
        return record["manifest"]


def read_copy(caller, storage_id, entry_id, *, incoming=False):
    with _store() as root:
        record, data = _load(root, "incoming" if incoming else "outgoing", storage_id, _owner(caller))
        if record["owner"] != _owner(caller):
            raise FileError("owner-mismatch", "another caller owns these copies")
        if entry_id not in data:
            raise FileError("missing-file", "no such copied entry")
        return data[entry_id]


def negotiate(packet, *, request_id, body, capability, limits, fallback=None, body_limit=None):
    """No automatic fallback. Explicit inline changes body: coordinator must rebind."""
    value, contents = _packet(packet, request_id, body, limits)
    if not contents:
        return {"mode": "none", "body": body, "packet": None, "requires_rebinding": False}
    if isinstance(capability, dict) and capability.get("status") in ("declared", "observed") \
            and type(capability.get("version")) is int and capability["version"] == 1:
        return {"mode": "files", "body": body, "packet": packet, "reference": reference(value),
                "requires_rebinding": False}
    if fallback != "inline":
        raise FileError("files-unsupported-or-unknown", "explicit inline fallback or a files-capable peer required", request_id)
    if body_limit is not None and (type(body_limit) is not int or body_limit <= 0):
        raise FileError("invalid-limits", "carrier body limit must be an explicit positive byte count", request_id)
    pieces = [body]
    for entry in value["files"]:
        try:
            text = contents[entry["id"]].decode("utf-8")
        except UnicodeError as exc:
            raise FileError("fallback-not-text", "binary copies cannot silently become text", request_id) from exc
        pieces.append("\n\n[Attachment copy %s v%s: %s; sha256=%s]\n%s" % (
            value["id"], value["version"], entry["name"], entry["sha256"], text))
    rendered = "".join(pieces)
    effective = limits.inline_bytes if body_limit is None else min(limits.inline_bytes, body_limit)
    if len(rendered.encode("utf-8")) > effective:
        raise FileError("inline-too-large", "explicit inline fallback exceeds body limit", request_id)
    return {"mode": "inline", "body": rendered, "packet": None, "reference": reference(value),
            "original_binding": value["binding"], "binding": _binding(request_id, rendered),
            "requires_rebinding": True}


def cleanup(*, now=None, dry_run=False, orphan_after=None):
    """Remove only this module's expired copies; never use metadata source paths.

    Staging left by a process crash is retained unless an explicit orphan age is
    supplied. Unknown/corrupt records are reported, never guessed to be expired.
    """
    now = _clock(now)
    if orphan_after is not None and (isinstance(orphan_after, bool) or not isinstance(orphan_after, (int, float))
                                     or not math.isfinite(orphan_after) or orphan_after < 0):
        raise FileError("invalid-limits", "explicit nonnegative orphan age required")
    result = {"removed": [], "errors": [], "dry_run": bool(dry_run)}
    with _store() as root:
        for kind in ("outgoing", "incoming"):
            with _folder(root, kind, create=True) as parent:
                for sid in os.listdir(parent):
                    try:
                        deleting = _DELETE.fullmatch(sid)
                        if sid.startswith(".deleting-"):
                            if deleting is None:
                                raise FileError("invalid-store", "unknown deletion marker; retained")
                            with _folder(parent, sid) as folder:
                                try:
                                    record = _document(folder)
                                except FileNotFoundError:
                                    record = None  # Resume after record unlink, never source paths.
                                if record is not None:
                                    _copy_metadata(record)
                                    if now < record["expires_at"]:
                                        raise FileError("active-copy", "valid unexpired copy in deletion namespace; retained")
                            expired = True
                        elif sid.startswith(".staging-"):
                            if orphan_after is None:
                                continue
                            _id(sid[len(".staging-"):])
                            info = os.stat(sid, dir_fd=parent, follow_symlinks=False)
                            expired = now - info.st_mtime >= orphan_after
                        else:
                            _id(sid)
                            with _folder(parent, sid) as folder:
                                record = _document(folder)
                            _copy_metadata(record)
                            expired = now >= _clock(record["expires_at"])
                        if expired:
                            if not dry_run:
                                if deleting is not None:
                                    _purge(parent, sid)
                                else:
                                    _remove(parent, sid)
                            result["removed"].append({"kind": kind, "storage_id": sid})
                    except _STORE_ERRORS as exc:
                        result["errors"].append({"kind": kind, "storage_id": sid, "error": type(exc).__name__})
    return result
