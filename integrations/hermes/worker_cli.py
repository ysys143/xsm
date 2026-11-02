"""Hermes 0.22.5 CLI framing; admission, ownership and journaling remain in xsm.

The installed provider and owned journal perform admission and identity binding.
The caller supplies an admitted native executable, profile and workspace.
"""
from __future__ import annotations

import json
import os
import re


class NativeCliError(ValueError):
    pass


_NATIVE_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,511}\Z')


def _native_id(value):
    if not isinstance(value, str) or not _NATIVE_ID.fullmatch(value):
        raise NativeCliError('Hermes returned an invalid opaque native conversation ID')
    return value


def build_command(executable, worker, context):
    if not isinstance(executable, str) or not os.path.isabs(executable) or '\0' in executable:
        raise NativeCliError('an admitted absolute native executable is required')
    command = [executable, 'chat', '--format', 'stream-json', '--query-file', '-']
    native_id = context.get('native_session_id')
    if native_id is not None:
        return command + ['--resume', _native_id(native_id)]
    cwd = worker.get('cwd')
    if not isinstance(cwd, str) or not os.path.isabs(cwd) or '\0' in cwd:
        raise NativeCliError('an admitted absolute native workspace is required')
    command += ['--in', cwd]
    for field, flag in (('model', '--model'), ('effort', '--reasoning')):
        value = worker.get(field)
        if value is not None:
            if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
                raise NativeCliError('invalid native ' + field)
            command.append(flag + '=' + value)
    return command


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise NativeCliError('Hermes returned a duplicate JSON event key')
        result[key] = value
    return result


def _constant(value):
    raise NativeCliError('Hermes returned a non-JSON numeric value')


def parse_result(output, context):
    if not isinstance(output, str):
        raise NativeCliError('Hermes native output must be text')
    try:
        events = [json.loads(line, object_pairs_hook=_unique, parse_constant=_constant)
                  for line in output.splitlines() if line.strip()]
    except (ValueError, RecursionError) as error:
        raise NativeCliError('Hermes returned invalid native JSON events') from error
    if not events or any(not isinstance(event, dict) for event in events):
        raise NativeCliError('Hermes returned no native event sequence')
    initial = events[0]
    if initial.get('type') != 'system' or initial.get('subtype') != 'init':
        raise NativeCliError('Hermes native initialization event is missing')
    finals = [event for event in events if event.get('type') == 'result']
    if len(finals) != 1 or events[-1] is not finals[0]:
        raise NativeCliError('Hermes requires exactly one terminal native result')
    final = finals[0]
    if type(final.get('exit_code')) is not int or final['exit_code'] != 0 or final.get('error'):
        raise NativeCliError('Hermes reported a failed native turn')
    if any(event.get('type') == 'error' for event in events):
        raise NativeCliError('Hermes reported a native error event')
    native_id = _native_id(final.get('session_id'))
    expected = context.get('native_session_id')
    if expected is not None and _native_id(expected) != native_id:
        raise NativeCliError('Hermes changed the selected owned conversation')
    if initial.get('session_id') not in (None, '', native_id):
        raise NativeCliError('Hermes changed native conversations within one run')
    body = final.get('text')
    if not isinstance(body, str) or not body.strip():
        raise NativeCliError('Hermes native result lacks an actual answer')
    return {'body': body, 'native_session_id': native_id,
            'native_evidence': {'event_count': len(events), 'terminal_event': 'result',
                                'terminal_exit_code': 0}}
