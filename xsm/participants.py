"""Read-only proof of a live protocol registration, not visibility or permission."""
from __future__ import annotations

import fcntl
import os
import re
import stat

from . import identity, paths, probe, registry

_HEX = re.compile(r'[0-9a-f]{64}\Z')
_GENERATION = re.compile(r'[0-9a-f]{32}\Z')


def live_binding(record, *, fresh=False):
    try:
        if (not isinstance(record, dict) or record.get('protocol_version') != '1'
                or record.get('registered') is not True or record.get('ended_at')
                or record.get('excluded') or record.get('remote')
                or record.get('uid', os.getuid()) != os.getuid()):
            return False
        runtime, sid, generation = (record.get(key) for key in ('runtime', 'session_id', 'protocol_generation'))
        if (not isinstance(runtime, str) or not identity.RUNTIME_SLUG.fullmatch(runtime)
                or runtime in ('claude', 'codex') or not isinstance(sid, str) or not _HEX.fullmatch(sid)
                or not isinstance(generation, str) or not _GENERATION.fullmatch(generation)):
            return False
        home = os.path.realpath(os.path.expanduser(record['home']))
        profile = os.path.basename(home)
        expected = os.path.join(os.path.realpath(paths.HOME), 'protocol-profiles', runtime, profile)
        if not _HEX.fullmatch(profile) or home != expected:
            return False
        pid = record.get('pid')
        if type(pid) is not int or pid <= 0 or not isinstance(record.get('lstart'), str) or not record['lstart']:
            return False
        filename = registry._record_path(runtime, sid)
        current = paths.read_json(filename)
        fields = ('runtime', 'session_id', 'protocol_version', 'protocol_generation', 'pid', 'lstart')
        if (not isinstance(current, dict) or any(current.get(key) != record.get(key) for key in fields)
                or current.get('registered') is not True or current.get('ended_at') or current.get('excluded')
                or os.path.realpath(current['home']) != home
                or os.path.realpath(current['cwd']) != os.path.realpath(record['cwd'])):
            return False
        if not identity.pid_alive(pid):
            return False
        started = ((probe.command(['ps', '-o', 'lstart=', '-p', str(pid)]) or '').strip()
                   if fresh else identity.lstart(pid))
        if started != record['lstart']:
            return False
        fd = os.open(filename + '.protocol-lock', os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                return False
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            else:
                fcntl.flock(fd, fcntl.LOCK_UN)
                return False
        finally:
            os.close(fd)
    except (OSError, ValueError, TypeError, KeyError):
        return False
