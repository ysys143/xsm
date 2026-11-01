"""Owned OpenCode TUI URI edits with a recoverable, content-free journal."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import uuid
from urllib.parse import unquote, urlsplit

from . import install
from .jsonc_edit import Document

FILES = ("tui.json", "tui.jsonc")
PHASES = ("prepared", "installed", "removing", "removed")


def sha(data):
    return hashlib.sha256(data).hexdigest() if data is not None else "missing"


def _locator(item):
    return item if isinstance(item, str) else item[0]


def _ours(uri):
    return unquote(urlsplit(uri).path).endswith("/integrations/opencode/tui.mjs")


def validate(home, record):
    if record is None:
        return
    if (not isinstance(record, dict) or record.get("version") != 1 or record.get("phase") not in PHASES or
            record.get("file") not in [os.path.join(home, name) for name in FILES] or
            not isinstance(record.get("root"), str) or not os.path.isabs(record["root"]) or
            record.get("uri") != Path(record["root"], "integrations/opencode/tui.mjs").as_uri() or
            not isinstance(record.get("fragment"), str) or not isinstance(record.get("created"), bool) or
            not isinstance(record.get("original_hash"), str) or
            (record["original_hash"] != "missing" and
             (len(record["original_hash"]) != 64 or any(c not in "0123456789abcdef" for c in record["original_hash"])) )):
        raise install.InstallConflictError("invalid native UI ownership record preserved")
    if (record["created"] != (record["original_hash"] == "missing") or
            json.dumps(record["uri"], ensure_ascii=False) not in record["fragment"] or
            not isinstance(record.get("expected_hash"), str) or len(record["expected_hash"]) != 64 or
            any(c not in "0123456789abcdef" for c in record["expected_hash"])):
        raise install.InstallConflictError("invalid native UI edit journal preserved")
    if record.get("previous_root") is not None:
        root = record["previous_root"]
        if (not isinstance(root, str) or not os.path.isabs(root) or
                record.get("previous_uri") != Path(root, "integrations/opencode/tui.mjs").as_uri()):
            raise install.InstallConflictError("invalid previous native UI reference preserved")
    elif record.get("previous_uri") is not None:
        raise install.InstallConflictError("native UI previous root missing")


def inspect(home, owned=None):
    from . import host_install as host
    validate(home, owned)
    try:
        hfd, pfd = host._open_dirs(home, ".", False)
    except FileNotFoundError:
        values = {name: (None, "missing", None) for name in FILES}
        identity = None
    else:
        try:
            values = {name: host._read_at(pfd, name) for name in FILES}
            host._guard(home, ".", hfd, pfd)
            identity = host._identity(os.fstat(hfd))
        finally:
            os.close(pfd)
            os.close(hfd)
    documents = {}
    allowed = {owned.get("uri"), owned.get("previous_uri")} if owned and owned["phase"] != "removed" else set()
    matches = []
    for name, (data, _, _) in values.items():
        if data is None:
            continue
        try:
            document = Document(data.decode("utf-8"))
            for index, (_, _, item) in enumerate(document.plugins()):
                uri = _locator(item)
                if _ours(uri):
                    if not owned or os.path.join(home, name) != owned["file"] or uri not in allowed:
                        raise ValueError("unowned native xsm UI plugin entry preserved")
                    if not isinstance(item, str):
                        raise ValueError("edited native xsm UI plugin options preserved")
                    matches.append((name, index, uri))
            documents[name] = document
        except (ValueError, UnicodeError) as error:
            raise install.InstallConflictError("native UI config conflict (%s): %s" % (name, error)) from error
    if len(matches) > 1:
        raise install.InstallConflictError("duplicate native xsm UI entries preserved")
    name = os.path.basename(owned["file"]) if owned and owned["phase"] != "removed" else (
        "tui.jsonc" if values["tui.jsonc"][0] is not None else "tui.json")
    return {"home": home, "name": name, "values": values, "documents": documents,
            "identity": identity, "match": matches[0] if matches else None}


def prepare(state, owned, root=None):
    name = state["name"]
    before, revision, mode = state["values"][name]
    document = state["documents"].get(name)
    match = state["match"]
    old = owned if owned and owned["phase"] != "removed" else None
    if root is not None:
        uri = Path(root, "integrations/opencode/tui.mjs").as_uri()
        if match:
            after = document.replace(match[1], uri).encode("utf-8")
            fragment = old["fragment"]
            for known in (old.get("uri"), old.get("previous_uri")):
                if known:
                    fragment = fragment.replace(json.dumps(known, ensure_ascii=False), json.dumps(uri, ensure_ascii=False))
            original_hash, created = old["original_hash"], old["created"]
        else:
            if document is None:
                after = ('{"plugin": [' + json.dumps(uri, ensure_ascii=False) + ']}\n').encode("utf-8")
                fragment = after.decode("utf-8")
            else:
                edited, fragment = document.insert(uri)
                after = edited.encode("utf-8")
            original_hash, created = sha(before), before is None
        previous_uri = match[2] if match else (old or {}).get("uri")
        previous_root = (old or {}).get("root")
        if old and previous_uri == old.get("previous_uri"):
            previous_root = old.get("previous_root")
        record = {"version": 1, "phase": "prepared", "file": os.path.join(state["home"], name),
                  "uri": uri, "root": root, "fragment": fragment, "original_hash": original_hash,
                  "created": created, "previous_root": previous_root,
                  "previous_uri": previous_uri, "expected_hash": sha(after)}
    else:
        record = dict(old, phase="removing") if old else None
        after = before
        if match:
            template = ('{"plugin": [' + json.dumps(match[2], ensure_ascii=False) + ']}\n').encode("utf-8")
            if old["created"] and before == template:
                after = None
            else:
                text, fragment = before.decode("utf-8"), old["fragment"]
                restored = text.replace(fragment, "", 1).encode("utf-8") if fragment and text.count(fragment) == 1 else None
                if restored is not None and sha(restored) == old["original_hash"]:
                    after = restored
                else:
                    after = document.remove(match[1]).encode("utf-8")
    return dict(state, before=before, after=after, revision=revision, mode=mode, record=record,
                changed=before != after)


def verify(plan, hfd):
    from . import host_install as host
    host._guard(plan["home"], ".", hfd, hfd)
    if plan["identity"] is not None and host._identity(os.fstat(hfd)) != plan["identity"]:
        raise install.InstallConflictError("native UI profile changed after inspection")
    for name, (_, revision, _) in plan["values"].items():
        if host._read_at(hfd, name)[1] != revision:
            raise install.InstallConflictError("native UI config changed after inspection")


def commit(plan, hfd):
    from . import host_install as host
    verify(plan, hfd)
    if not plan["changed"]:
        return
    name = plan["name"]
    if plan["after"] is None:
        os.unlink(name, dir_fd=hfd)
        os.fsync(hfd)
        return
    staged = ".xsm-ui-" + uuid.uuid4().hex
    fd = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_EXCL | host.NOFOLLOW, plan["mode"] or 0o600, dir_fd=hfd)
    try:
        os.fchmod(fd, plan["mode"] if plan["mode"] is not None else 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(plan["after"])
            stream.flush()
            os.fsync(stream.fileno())
        verify(plan, hfd)
        if plan["before"] is None:
            os.link(staged, name, src_dir_fd=hfd, dst_dir_fd=hfd, follow_symlinks=False)
        else:
            os.replace(staged, name, src_dir_fd=hfd, dst_dir_fd=hfd)
        os.fsync(hfd)
    finally:
        try:
            os.unlink(staged, dir_fd=hfd)
        except FileNotFoundError:
            pass


def roots(home, owned):
    validate(home, owned)
    if not owned or owned["phase"] == "removed":
        return []
    return [root for root in (owned.get("root"), owned.get("previous_root")) if root]


def actual_roots(home):
    """Preserve user-edited URI references too; ownership is only for mutation."""
    from . import host_install as host
    try:
        hfd, pfd = host._open_dirs(home, ".", False)
    except FileNotFoundError:
        return []
    found = set()
    try:
        for name in FILES:
            content, _, _ = host._read_at(pfd, name)
            if content is None:
                continue
            pending = [Document(content.decode("utf-8")).value]
            while pending:
                value = pending.pop()
                if isinstance(value, dict):
                    pending.extend(value.values())
                elif isinstance(value, list):
                    pending.extend(value)
                elif isinstance(value, str):
                    found.update(install._snapshot_ids(unquote(value)))
        host._guard(home, ".", hfd, pfd)
    finally:
        os.close(pfd)
        os.close(hfd)
    return [install.runtime_dir(sid) for sid in sorted(found)]
