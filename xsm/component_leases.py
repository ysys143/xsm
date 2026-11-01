"""Read only registered UI component PIDs; never enumerate unrelated processes."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import subprocess
import uuid

from . import identity, install, paths


def hold(component="opencode-tui", expected_parent=None):
    """Called by a short-lived child of the native UI; serialize with pruning."""
    root = os.path.realpath(Path(__file__).resolve().parents[1])
    if component not in ("opencode-tui", "opencode-server"):
        raise install.InstallConflictError("unsupported native component")
    if os.path.dirname(root) != os.path.realpath(install.runtime_dir()) or not install._ID.fullmatch(os.path.basename(root)):
        raise install.InstallConflictError("native component did not load an installed snapshot")
    with install._target_lock(install.runtime_dir(install.CURRENT)):
        if not os.path.isdir(root):
            raise install.InstallConflictError("native component snapshot disappeared before registration")
        pid = os.getppid()
        if expected_parent is not None and pid != expected_parent:
            raise install.InstallConflictError("native component parent changed before registration")
        observed = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)],
                                  env={**os.environ, "LC_ALL": "C", "TZ": "UTC"}, capture_output=True, text=True, timeout=2)
        start = observed.stdout.strip()
        if not start or not identity.pid_alive(pid):
            raise install.InstallConflictError("native component parent generation unavailable")
        folder = Path(paths.path("component-leases"))
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = folder.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise install.InstallConflictError("component lease directory is not private")
        record = {"componentLease": 1, "id": uuid.uuid4().hex, "component": component,
                  "root": root, "pid": pid, "lstart": start, "clock": "utc-c"}
        paths.write_json(str(folder / (record["id"] + ".json")), record)
        return record


def configured_roots():
    folder = Path(paths.path("component-leases"))
    try:
        info = folder.lstat()
    except FileNotFoundError:
        return []
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise install.InstallConflictError("component lease directory is not private")
    roots = []
    for filename in folder.glob("*.json"):
        fd = os.open(filename, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or
                    info.st_size > 65536):
                raise install.InstallConflictError("invalid component lease file")
            with os.fdopen(fd, encoding="utf-8", closefd=False) as stream:
                value = json.load(stream)
        finally:
            os.close(fd)
        if (not isinstance(value, dict) or value.get("componentLease") != 1 or
                value.get("component") not in ("opencode-tui", "opencode-server") or not isinstance(value.get("id"), str) or
                value.get("clock") not in (None, "utc-c") or
                not re.fullmatch(r"[0-9a-f]{32}", value["id"]) or filename.name != value["id"] + ".json" or
                type(value.get("pid")) is not int or value["pid"] <= 0 or
                not isinstance(value.get("lstart"), str) or not value["lstart"].strip() or
                not isinstance(value.get("root"), str)):
            raise install.InstallConflictError("invalid component lease ownership")
        root = Path(value["root"])
        if (not root.is_absolute() or not re.fullmatch(r"[0-9a-f]{12}", root.name) or
                os.path.realpath(root.parent) != os.path.realpath(install.runtime_dir())):
            raise install.InstallConflictError("component lease root outside runtime directory")
        if not identity.pid_alive(value["pid"]):
            continue
        if value.get("clock") is None:
            roots.append(str(root))  # Legacy wall-clock zones cannot prove a live PID was reused.
            continue
        try:
            result = subprocess.run(["ps", "-o", "lstart=", "-p", str(value["pid"])],
                                    env={**os.environ, "LC_ALL": "C", "TZ": "UTC"}, capture_output=True, text=True, timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            roots.append(str(root))  # Unavailable evidence must not delete a live component's code.
            continue
        observed = result.stdout.strip()
        if not observed or observed == value["lstart"]:
            roots.append(str(root))
    return roots
