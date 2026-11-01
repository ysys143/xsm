"""Owned native host loaders and TUI entries. No credentials or trust changes.

The loader is pinned to an immutable xsm snapshot. A protected write-ahead
ownership record permits recovery without restoring over later user edits.
All native-directory reads and mutations use anchored no-follow descriptors.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
import stat
import uuid
from urllib.parse import unquote

from . import install, paths

BINDINGS = {"hermes": ("plugins", "xsm", "integrations/hermes/xsm.py"),
            "pi": ("extensions", "xsm.js", "integrations/pi/xsm.mjs"),
            "opencode": ("plugins", "xsm.js", "integrations/opencode/xsm.mjs")}
SHARED = ("clients/typescript/xsm-client.mjs", "clients/typescript/xsm-host.mjs", "bin/xsm", "xsm/protocol.py")
NATIVE_ASSETS = {"opencode": ("integrations/opencode/ui-channel.mjs", "integrations/opencode/question-ui.mjs",
                               "integrations/opencode/tui.mjs", "integrations/opencode/component-lease.mjs")}
NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
DIRECTORY = getattr(os, "O_DIRECTORY", 0)


def target(runtime, home):
    if runtime not in BINDINGS:
        raise ValueError("unsupported native host binding")
    home = os.path.realpath(os.path.abspath(os.path.expanduser(home)))
    directory, filename, _ = BINDINGS[runtime]
    return home, directory, filename


def record_path(runtime, home):
    home = target(runtime, home)[0]
    key = hashlib.sha256((runtime + "\0" + home).encode()).hexdigest()
    return paths.path("host-installations", key + ".json")


def read_record(runtime, home):
    home = target(runtime, home)[0]
    if runtime == "hermes":
        from . import hermes_install
        return hermes_install.read_record(home)
    filename = record_path(runtime, home)
    if os.path.islink(filename):
        raise install.InstallConflictError("host ownership symlink preserved")
    if not os.path.exists(filename):
        return None
    with open(filename, encoding="utf-8") as stream:
        value = json.load(stream)
    if (not isinstance(value, dict) or value.get("bindingInstall") != 1 or
            value.get("runtime") != runtime or value.get("home") != home or
            value.get("phase") not in ("prepared", "installed", "removing", "removed") or
            not isinstance(value.get("install_id"), str) or not re.fullmatch(r"[0-9a-f]{32}", value["install_id"]) or
            not isinstance(value.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) or
            (value.get("previous_sha256") is not None and
             (not isinstance(value["previous_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["previous_sha256"]))) or
            not isinstance(value.get("root"), str) or not os.path.isabs(value["root"])):
        raise install.InstallConflictError("invalid host ownership record preserved")
    _, directory, basename = target(runtime, home)
    if value.get("file") != os.path.join(home, directory, basename):
        raise install.InstallConflictError("host ownership loader locator differs")
    if value.get("ui") is not None:
        from . import host_ui_config
        if runtime != "opencode":
            raise install.InstallConflictError("unexpected native UI ownership")
        host_ui_config.validate(home, value["ui"])
    return value


def save_record(record):
    paths.write_json(record_path(record["runtime"], record["home"]), record)


def _identity(info):
    return info.st_dev, info.st_ino


def _read_at(directory, name):
    try:
        info = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return None, "missing", None
    if not stat.S_ISREG(info.st_mode):
        raise install.InstallConflictError("non-regular native loader preserved")
    fd = os.open(name, os.O_RDONLY | NOFOLLOW, dir_fd=directory)
    try:
        if _identity(os.fstat(fd)) != _identity(info):
            raise install.InstallConflictError("native loader changed while reading")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            content = stream.read()
    finally:
        os.close(fd)
    metadata = [info.st_dev, info.st_ino, info.st_mtime_ns, info.st_mode, info.st_size]
    revision = hashlib.sha256(json.dumps(metadata).encode() + b"\0" + content).hexdigest()
    return content, revision, stat.S_IMODE(info.st_mode)


def _open_dirs(home, directory, create):
    if create:
        os.makedirs(home, mode=0o700, exist_ok=True)
    home_fd = os.open(home, os.O_RDONLY | DIRECTORY | NOFOLLOW)
    try:
        if create:
            try:
                os.mkdir(directory, mode=0o700, dir_fd=home_fd)
            except FileExistsError:
                pass
        parent_fd = os.open(directory, os.O_RDONLY | DIRECTORY | NOFOLLOW, dir_fd=home_fd)
        return home_fd, parent_fd
    except BaseException:
        os.close(home_fd)
        raise


def _guard(home, directory, home_fd, parent_fd):
    current = os.stat(home, follow_symlinks=False)
    child = os.stat(directory, dir_fd=home_fd, follow_symlinks=False)
    if (_identity(current) != _identity(os.fstat(home_fd)) or
            _identity(child) != _identity(os.fstat(parent_fd)) or not stat.S_ISDIR(child.st_mode)):
        raise install.InstallConflictError("native profile directory changed; user path preserved")


def _owned(content, record):
    if content is None:
        return
    if not record or record["phase"] == "removed":
        raise install.InstallConflictError("unowned native loader preserved")
    allowed = {record.get("sha256")}
    if record["phase"] in ("prepared", "removing"):
        allowed.add(record.get("previous_sha256"))
    if hashlib.sha256(content).hexdigest() not in allowed:
        raise install.InstallConflictError("edited native loader preserved")
    marker = ("// xsm managed host loader " + record["install_id"] + "\n").encode()
    if not content.startswith(marker):
        raise install.InstallConflictError("native loader ownership marker differs")


def _assets(root, runtime):
    required = SHARED + (BINDINGS[runtime][2],) + NATIVE_ASSETS.get(runtime, ())
    if any(not os.path.isfile(os.path.join(root, name)) for name in required):
        raise ValueError("runtime snapshot lacks native host assets; update xsm first")


def inspect(runtime, home):
    if runtime == "hermes":
        from . import hermes_install
        return hermes_install.inspect(target(runtime, home)[0])
    home, directory, name = target(runtime, home)
    record = read_record(runtime, home)
    extra = {}
    if runtime == "opencode":
        from . import host_ui_config
        state = host_ui_config.inspect(home, (record or {}).get("ui"))
        extra["ui"] = {"file": os.path.join(home, state["name"]),
                       "status": "managed" if state["match"] else "absent"}
    try:
        hfd, pfd = _open_dirs(home, directory, False)
    except FileNotFoundError:
        return dict(runtime=runtime, home=home, status="absent", file=os.path.join(home, directory, name), **extra)
    try:
        content, revision, mode = _read_at(pfd, name)
        _guard(home, directory, hfd, pfd)
        _owned(content, record)
        return {"runtime": runtime, "home": home, "status": "managed" if content else "absent",
                "file": os.path.join(home, directory, name), "revision": revision,
                "mode": mode, "runtime_root": (record or {}).get("root"), **extra}
    finally:
        os.close(pfd)
        os.close(hfd)


def apply(runtime, home, dry_run=False):
    if runtime == "hermes":
        from . import hermes_install
        return hermes_install.apply(target(runtime, home)[0], dry_run)
    home, directory, name = target(runtime, home)
    filename = os.path.join(home, directory, name)
    if dry_run:
        before = inspect(runtime, home)
        _assets(install.REPO, runtime)
        return dict(before, action="install", dry_run=True, requires_reload=True)
    with install._target_lock(filename):
        before = inspect(runtime, home)
        previous = read_record(runtime, home)
        ui_state = None
        if runtime == "opencode":
            from . import host_ui_config
            ui_state = host_ui_config.inspect(home, (previous or {}).get("ui"))
        _assets(install.REPO, runtime)
        python = install.resolve_python(None)
        probe = install.subprocess.run([python, "-c", "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"],
                                       capture_output=True, timeout=5)
        if probe.returncode:
            raise ValueError("native host requires Python 3.9 or newer")
        root = install.REPO if install.runtime_in_place() else install.make_snapshot()["path"]
        _assets(root, runtime)
        ui_plan = host_ui_config.prepare(ui_state, (previous or {}).get("ui"), root) if ui_state else None
        hfd, pfd = _open_dirs(home, directory, True)
        try:
            if ui_plan:
                host_ui_config.verify(ui_plan, hfd)
            content, revision, mode = _read_at(pfd, name)
            if revision != before.get("revision", "missing"):
                raise install.InstallConflictError("native loader changed after inspection")
            previous = read_record(runtime, home)
            _owned(content, previous)
            ident = (previous or {}).get("install_id") or uuid.uuid4().hex
            uri = Path(os.path.join(root, BINDINGS[runtime][2])).as_uri()
            command = [python, "-c", install.BOOT, root, "protocol", "serve", "--stdio"]
            native_import = "import { tool } from '@opencode-ai/plugin';\n" if runtime == "opencode" else ""
            native_options = ", schema: tool.schema, nativeUi: true, profile: " + json.dumps(home) if runtime == "opencode" else ""
            data = ("// xsm managed host loader %s\nimport binding from %s;\n%s"
                    "const command = %s;\nexport default api => binding(api, { command: "
                    "[process.env.XSM_PYTHON || command[0], ...command.slice(1)]%s });\n"
                    % (ident, json.dumps(uri), native_import, json.dumps(command), native_options)).encode()
            record = {"bindingInstall": 1, "runtime": runtime, "home": home, "file": filename, "install_id": ident,
                      "root": root, "python": python, "phase": "prepared", "sha256": hashlib.sha256(data).hexdigest(),
                      "previous_sha256": hashlib.sha256(content).hexdigest() if content is not None else None}
            if ui_plan:
                record["ui"] = ui_plan["record"]
            save_record(record)
            if content != data:
                _guard(home, directory, hfd, pfd)
                staged = ".xsm-host-" + uuid.uuid4().hex
                fd = os.open(staged, os.O_CREAT | os.O_EXCL | os.O_WRONLY | NOFOLLOW, mode or 0o600, dir_fd=pfd)
                try:
                    os.fchmod(fd, mode if mode is not None else 0o600)
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                    _guard(home, directory, hfd, pfd)
                    if _read_at(pfd, name)[1] != revision:
                        raise install.InstallConflictError("native loader changed before commit")
                    os.replace(staged, name, src_dir_fd=pfd, dst_dir_fd=pfd)
                    os.fsync(pfd)
                finally:
                    try:
                        os.unlink(staged, dir_fd=pfd)
                    except FileNotFoundError:
                        pass
            if ui_plan:
                host_ui_config.commit(ui_plan, hfd)
                record["ui"] = dict(ui_plan["record"], phase="installed", previous_root=None, previous_uri=None)
            record.update(phase="installed", revision=_read_at(pfd, name)[1], previous_sha256=None)
            save_record(record)
            return {"runtime": runtime, "home": home, "file": filename, "runtime_root": root,
                    "status": "installed", "changed": content != data or bool(ui_plan and ui_plan["changed"]),
                    "requires_reload": True, **({"ui": {"file": record["ui"]["file"], "uri": record["ui"]["uri"],
                                                       "status": "managed"}} if ui_plan else {})}
        finally:
            os.close(pfd)
            os.close(hfd)


def remove(runtime, home, dry_run=False):
    if runtime == "hermes":
        from . import hermes_install
        return hermes_install.remove(target(runtime, home)[0], dry_run)
    home, directory, name = target(runtime, home)
    filename = os.path.join(home, directory, name)
    if dry_run:
        return dict(inspect(runtime, home), action="remove", dry_run=True)
    with install._target_lock(filename):
        before = inspect(runtime, home)
        record = read_record(runtime, home)
        ui_plan = None
        if runtime == "opencode":
            from . import host_ui_config
            ui_plan = host_ui_config.prepare(host_ui_config.inspect(home, (record or {}).get("ui")),
                                             (record or {}).get("ui"))
        if before["status"] == "absent":
            if ui_plan and ui_plan["changed"]:
                hfd = os.open(home, os.O_RDONLY | DIRECTORY | NOFOLLOW)
                try:
                    host_ui_config.verify(ui_plan, hfd)
                    save_record(dict(record, phase="removing", ui=ui_plan["record"]))
                    host_ui_config.commit(ui_plan, hfd)
                finally:
                    os.close(hfd)
            if record:
                if ui_plan and ui_plan["record"]:
                    record = dict(record, ui=dict(ui_plan["record"], phase="removed"))
                save_record(dict(record, phase="removed"))
            return dict(before, changed=bool(ui_plan and ui_plan["changed"]))
        hfd, pfd = _open_dirs(home, directory, False)
        try:
            content, revision, _ = _read_at(pfd, name)
            _owned(content, record)
            if revision != before["revision"]:
                raise install.InstallConflictError("native loader changed before removal")
            if ui_plan:
                host_ui_config.verify(ui_plan, hfd)
                if ui_plan["record"]:
                    record = dict(record, ui=ui_plan["record"])
            save_record(dict(record, phase="removing"))
            if ui_plan:
                host_ui_config.commit(ui_plan, hfd)
            _guard(home, directory, hfd, pfd)
            if _read_at(pfd, name)[1] != revision:
                raise install.InstallConflictError("native loader changed before removal commit")
            os.unlink(name, dir_fd=pfd)
            os.fsync(pfd)
            if ui_plan and ui_plan["record"]:
                record = dict(record, ui=dict(ui_plan["record"], phase="removed"))
            save_record(dict(record, phase="removed"))
            return dict(before, status="removed", changed=True)
        finally:
            os.close(pfd)
            os.close(hfd)


def configured_roots():
    roots = []
    folder = Path(paths.path("host-installations"))
    for filename in folder.glob("*.json"):
        if filename.is_symlink():
            raise install.InstallConflictError("host ownership symlink")
        value = json.loads(filename.read_text())
        if not isinstance(value, dict) or not isinstance(value.get("runtime"), str) or not isinstance(value.get("home"), str):
            raise install.InstallConflictError("invalid host ownership reference")
        if target(value["runtime"], value["home"])[0] != value["home"]:
            raise install.InstallConflictError("noncanonical host ownership home")
        record = read_record(value["runtime"], value["home"])
        if record is None or filename != Path(record_path(value["runtime"], value["home"])):
            raise install.InstallConflictError("host ownership locator mismatch")
        if record["runtime"] == "hermes":
            from . import hermes_install
            roots.extend(hermes_install.roots(record))
            continue
        if record["phase"] != "removed":
            root = record.get("root")
            if not isinstance(root, str) or not os.path.isabs(root):
                raise install.InstallConflictError("host runtime reference unavailable")
            roots.append(root)
        from . import host_ui_config
        roots.extend(host_ui_config.roots(record["home"], record.get("ui")))
        if record["runtime"] == "opencode":
            roots.extend(host_ui_config.actual_roots(record["home"]))
        # Also preserve the actual loader's references during a prepared update,
        # including older journals and user edits that mutation must refuse.
        home, directory, basename = target(record["runtime"], record["home"])
        try:
            hfd, pfd = _open_dirs(home, directory, False)
        except FileNotFoundError:
            continue
        try:
            content, _, _ = _read_at(pfd, basename)
            _guard(home, directory, hfd, pfd)
            if content:
                text = content.decode("utf-8")
                ids = install._snapshot_ids(text) | install._snapshot_ids(unquote(text))
                roots.extend(install.runtime_dir(sid) for sid in ids)
        finally:
            os.close(pfd)
            os.close(hfd)
    return roots


def command(args):
    import sys
    try:
        if args.protocol_action == "install":
            result = apply(args.runtime, args.home, args.dry_run)
        elif args.protocol_action == "uninstall":
            result = remove(args.runtime, args.home, args.dry_run)
        else:
            result = inspect(args.runtime, args.home)
        print(json.dumps(result))
        return 0
    except (OSError, ValueError) as error:
        print("xsm host installation: " + str(error), file=sys.stderr)
        return 4
