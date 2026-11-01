"""Owned two-file OpenClaw plugin installation; activation remains operator opt-in."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

from . import host_install as host, install

FILES = ("index.mjs", "openclaw.plugin.json")


def read_record(home):
    filename = host.record_path("openclaw", home)
    if os.path.islink(filename):
        raise install.InstallConflictError("host ownership symlink preserved")
    if not os.path.exists(filename):
        return None
    value = json.loads(Path(filename).read_text())
    valid_hash = lambda v: isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v)
    if (not isinstance(value, dict) or value.get("bindingInstall") != 2 or
            value.get("runtime") != "openclaw" or value.get("home") != home or
            value.get("file") != os.path.join(home, "extensions", "xsm") or
            value.get("phase") not in ("prepared", "installed", "removing", "removed") or
            not isinstance(value.get("install_id"), str) or
            not re.fullmatch(r"[0-9a-f]{32}", value["install_id"]) or
            not isinstance(value.get("root"), str) or not os.path.isabs(value["root"]) or
            not isinstance(value.get("files"), dict) or set(value["files"]) != set(FILES)):
        raise install.InstallConflictError("invalid OpenClaw ownership record preserved")
    for item in value["files"].values():
        if (not isinstance(item, dict) or not valid_hash(item.get("sha256")) or
                (item.get("previous_sha256") is not None and not valid_hash(item["previous_sha256"]))):
            raise install.InstallConflictError("invalid OpenClaw ownership digest preserved")
    return value


@contextlib.contextmanager
def directory(home, create=False):
    hfd, pfd = host._open_dirs(home, "extensions", create)
    fd = None
    try:
        if create:
            try:
                os.mkdir("xsm", mode=0o700, dir_fd=pfd)
            except FileExistsError:
                pass
        fd = os.open("xsm", os.O_RDONLY | host.DIRECTORY | host.NOFOLLOW, dir_fd=pfd)
        def guard():
            host._guard(home, "extensions", hfd, pfd)
            info = os.stat("xsm", dir_fd=pfd, follow_symlinks=False)
            if host._identity(info) != host._identity(os.fstat(fd)):
                raise install.InstallConflictError("OpenClaw plugin directory changed")
        guard()
        yield fd, guard
    finally:
        if fd is not None:
            os.close(fd)
        os.close(pfd)
        os.close(hfd)


def owned(content, name, record):
    if content is None:
        return
    if not record or record["phase"] == "removed":
        raise install.InstallConflictError("unowned OpenClaw plugin preserved")
    item = record["files"][name]
    allowed = {item["sha256"]}
    if record["phase"] in ("prepared", "removing"):
        allowed.add(item.get("previous_sha256"))
    if hashlib.sha256(content).hexdigest() not in allowed:
        raise install.InstallConflictError("edited OpenClaw plugin preserved")
    if name == "index.mjs" and not content.startswith(("// xsm managed OpenClaw plugin " + record["install_id"] + "\n").encode()):
        raise install.InstallConflictError("OpenClaw ownership marker differs")


def inspect(home):
    record = read_record(home)
    state = dict(runtime="openclaw", home=home, file=os.path.join(home, "extensions", "xsm"),
                 status="absent", requires_reload=True, activation="operator-opt-in",
                 runtime_root=(record or {}).get("root"), revisions={})
    try:
        with directory(home) as (fd, guard):
            for name in FILES:
                content, revision, _ = host._read_at(fd, name)
                owned(content, name, record)
                state["revisions"][name] = revision
            guard()
    except FileNotFoundError:
        return state
    present = sum(v != "missing" for v in state["revisions"].values())
    state["status"] = "managed" if present == len(FILES) else "partial" if present else "absent"
    return state


def assets(root):
    for name in ("integrations/openclaw/xsm.mjs", "integrations/openclaw/openclaw.plugin.json",
                 "integrations/openclaw/context-queue.mjs", "integrations/openclaw/tools.mjs",
                 "clients/typescript/component-lease.mjs", "clients/typescript/xsm-host.mjs",
                 "clients/typescript/xsm-client.mjs", "xsm/protocol.py"):
        if not os.path.isfile(os.path.join(root, name)):
            raise ValueError("runtime snapshot lacks OpenClaw assets")


def payloads(root, python, ident):
    command = [python, "-c", install.BOOT, root, "protocol", "serve", "--stdio"]
    uri = Path(root, "integrations/openclaw/xsm.mjs").as_uri()
    code = ("// xsm managed OpenClaw plugin " + ident + "\nimport binding from " + json.dumps(uri) +
            ";\nexport default { ...binding, register(api) { return binding.register(api, " +
            json.dumps(dict(command=command, runtimeRoot=root)) + "); } };\n")
    return {"index.mjs": code.encode(),
            "openclaw.plugin.json": Path(root, "integrations/openclaw/openclaw.plugin.json").read_bytes()}


def replace(fd, guard, name, data, revision, mode):
    staged = ".xsm-host-" + uuid.uuid4().hex
    descriptor = os.open(staged, os.O_CREAT | os.O_EXCL | os.O_WRONLY | host.NOFOLLOW,
                         mode or 0o600, dir_fd=fd)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), mode if mode is not None else 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        guard()
        if host._read_at(fd, name)[1] != revision:
            raise install.InstallConflictError("OpenClaw plugin changed before commit")
        os.replace(staged, name, src_dir_fd=fd, dst_dir_fd=fd)
        os.fsync(fd)
    finally:
        try:
            os.unlink(staged, dir_fd=fd)
        except FileNotFoundError:
            pass


def apply(home, dry_run=False):
    filename = os.path.join(home, "extensions", "xsm")
    with install._target_lock(filename):
        before = inspect(home)
        assets(install.REPO)
        if dry_run:
            return dict(before, action="install", dry_run=True)
        previous = read_record(home)
        python = install.resolve_python(None)
        probe = install.subprocess.run([python, "-c",
            "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"],
            capture_output=True, timeout=5)
        if probe.returncode:
            raise ValueError("native host requires Python 3.9 or newer")
        root = install.REPO if install.runtime_in_place() else install.make_snapshot()["path"]
        assets(root)
        ident = (previous or {}).get("install_id") or uuid.uuid4().hex
        data = payloads(root, python, ident)
        with directory(home, True) as (fd, guard):
            current = {name: host._read_at(fd, name) for name in FILES}
            for name, (content, revision, _) in current.items():
                owned(content, name, previous)
                if revision != before["revisions"].get(name, "missing"):
                    raise install.InstallConflictError("OpenClaw plugin changed after inspection")
            record = dict(bindingInstall=2, runtime="openclaw", home=home, file=filename,
                          root=root, python=python, install_id=ident, phase="prepared",
                          files={name: dict(sha256=hashlib.sha256(data[name]).hexdigest(),
                              previous_sha256=hashlib.sha256(current[name][0]).hexdigest()
                              if current[name][0] is not None else None) for name in FILES})
            host.save_record(record)
            changed = False
            for name, (content, revision, mode) in current.items():
                if content != data[name]:
                    replace(fd, guard, name, data[name], revision, mode)
                    changed = True
            guard()
            record["phase"] = "installed"
            for item in record["files"].values():
                item["previous_sha256"] = None
            host.save_record(record)
        return dict(inspect(home), status="installed", changed=changed)


def remove(home, dry_run=False):
    with install._target_lock(os.path.join(home, "extensions", "xsm")):
        before = inspect(home)
        if dry_run:
            return dict(before, action="remove", dry_run=True)
        record = read_record(home)
        if before["status"] == "absent":
            if record:
                host.save_record(dict(record, phase="removed"))
            return dict(before, changed=False)
        with directory(home) as (fd, guard):
            host.save_record(dict(record, phase="removing"))
            for name in FILES:
                guard()
                content, revision, _ = host._read_at(fd, name)
                owned(content, name, record)
                if revision != before["revisions"][name]:
                    raise install.InstallConflictError("OpenClaw plugin changed before removal")
                if content is not None:
                    os.unlink(name, dir_fd=fd)
                    os.fsync(fd)
            host.save_record(dict(record, phase="removed"))
        return dict(before, status="removed", changed=True)


def roots(record):
    result = [record["root"]] if record["phase"] != "removed" else []
    try:
        with directory(record["home"]) as (fd, guard):
            content, _, _ = host._read_at(fd, "index.mjs")
            guard()
            if content:
                result.extend(install.runtime_dir(sid) for sid in install._snapshot_ids(content.decode()))
    except FileNotFoundError:
        pass
    return result
