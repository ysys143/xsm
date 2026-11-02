"""OpenCode 1.19.5 native JSON framing; no policy or journal implementation."""
from __future__ import annotations

import json
import os
import re


class NativeCliError(ValueError):
    pass


def _native_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'ses_[A-Za-z0-9]{1,508}', value):
        raise NativeCliError('OpenCode returned an invalid native conversation ID')
    return value


def build_command(executable, worker, context):
    if not isinstance(executable, str) or not os.path.isabs(executable) or '\0' in executable:
        raise NativeCliError('an admitted absolute native executable is required')
    command = [executable, 'run', '--format', 'json']
    if context.get('native_session_id') is not None:
        command += ['--session', _native_id(context['native_session_id'])]
    for field, flag in (('model', '--model'), ('effort', '--variant')):
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
            raise NativeCliError('OpenCode returned duplicate JSON event keys')
        result[key] = value
    return result


def _constant(value):
    raise NativeCliError('OpenCode returned a non-JSON numeric value')


def parse_result(output, context):
    if not isinstance(output, str):
        raise NativeCliError('OpenCode native output must be text')
    try:
        events = [json.loads(line, object_pairs_hook=_unique, parse_constant=_constant)
                  for line in output.splitlines() if line.strip()]
    except (ValueError, RecursionError) as error:
        raise NativeCliError('OpenCode returned invalid native JSON events') from error
    if not events or any(not isinstance(event, dict) for event in events):
        raise NativeCliError('OpenCode returned no native event sequence')
    native_id = _native_id(events[0].get('sessionID'))
    if context.get('native_session_id') not in (None, native_id):
        raise NativeCliError('OpenCode changed the selected owned conversation')
    body, active, complete = [], False, False
    for event in events:
        if event.get('sessionID') != native_id:
            raise NativeCliError('OpenCode changed conversations within one turn')
        kind, part = event.get('type'), event.get('part')
        if kind == 'error':
            raise NativeCliError('OpenCode reported a native execution error')
        if not isinstance(part, dict) or part.get('sessionID') != native_id:
            raise NativeCliError('OpenCode returned an invalid native event part')
        if kind == 'step_start':
            if active:
                raise NativeCliError('OpenCode started a step before finishing its predecessor')
            body, active, complete = [], True, False
        elif not active:
            raise NativeCliError('OpenCode returned an event outside a native step')
        elif kind == 'text':
            if not isinstance(part.get('text'), str):
                raise NativeCliError('OpenCode returned invalid answer text')
            body.append(part['text'])
        elif kind == 'step_finish':
            active = False
            complete = part.get('reason') == 'stop'
        elif kind not in ('tool_use', 'reasoning'):
            raise NativeCliError('OpenCode returned an unknown native event')
    answer = ''.join(body)
    if active or not complete or events[-1].get('type') != 'step_finish' or not answer.strip():
        raise NativeCliError('OpenCode returned no complete native answer')
    return {'body': answer, 'native_session_id': native_id,
            'native_evidence': {'event_count': len(events), 'terminal_event': 'step_finish',
                                'finish_reason': 'stop'}}
