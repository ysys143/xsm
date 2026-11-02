"""Pinned Pi print-mode JSON framing; ownership and policy stay in xsm."""
from __future__ import annotations

import json
import os
import re
import uuid


class NativeCliError(ValueError):
    pass


def _native_id(value):
    try:
        if not isinstance(value, str) or str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, AttributeError) as error:
        raise NativeCliError('Pi requires an exact native conversation UUID') from error
    return value


def build_command(executable, worker, context):
    if not isinstance(executable, str) or not os.path.isabs(executable) or '\0' in executable:
        raise NativeCliError('an admitted absolute native executable is required')
    if not re.fullmatch(r'[0-9a-f]{32}', worker.get('id', '')) or not os.path.isabs(worker.get('home', '')):
        raise NativeCliError('an admitted worker and native profile are required')
    command = [executable, '--print', '--mode', 'json', '--session-id',
               _native_id(context.get('native_session_id') or context.get('session_seed')),
               '--session-dir', os.path.join(worker['home'], 'owned-sessions', worker['id'])]
    for field, flag in (('model', '--model'), ('effort', '--thinking')):
        value = worker.get(field)
        if value is not None:
            if (not isinstance(value, str) or not value.strip() or value.startswith('-')
                    or any(ord(c) < 32 for c in value)):
                raise NativeCliError('invalid native ' + field)
            command += [flag, value]
    return command


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise NativeCliError('Pi returned duplicate JSON event keys')
        result[key] = value
    return result


def _constant(value):
    raise NativeCliError('Pi returned a non-JSON numeric value')


def _events(output, context, cwd):
    if not isinstance(output, str):
        raise NativeCliError('Pi native output must be text')
    try:
        events = [json.loads(line, object_pairs_hook=_unique, parse_constant=_constant)
                  for line in output.splitlines() if line.strip()]
    except (ValueError, RecursionError) as error:
        raise NativeCliError('Pi returned invalid native JSON events') from error
    if len(events) < 3 or any(not isinstance(event, dict) for event in events):
        raise NativeCliError('Pi returned no complete native event sequence')
    header = events[0]
    if header.get('type') != 'session' or sum(e.get('type') == 'session' for e in events) != 1:
        raise NativeCliError('Pi native session header is missing or ambiguous')
    native_id = _native_id(header.get('id'))
    expected = _native_id(context.get('native_session_id') or context.get('session_seed'))
    if native_id != expected:
        raise NativeCliError('Pi changed the selected owned conversation')
    if cwd is not None and (not isinstance(header.get('cwd'), str)
                            or os.path.realpath(header['cwd']) != os.path.realpath(cwd)):
        raise NativeCliError('Pi changed the selected native workspace')
    return events, native_id


def parse_cancellation(output, context, cwd=None):
    events, native_id = _events(output, context, cwd)
    end, settled = events[-2:]
    if (end.get('type') != 'agent_end' or end.get('willRetry') is not False
            or settled.get('type') != 'agent_settled' or settled.get('aborted') is not True):
        raise NativeCliError('Pi returned no confirmed aborted native turn')
    return {'native_session_id': native_id,
            'native_evidence': {'event_count': len(events), 'terminal_event': 'agent_settled',
                                'aborted': True, 'native_state': 'stopped'}}


def parse_result(output, context, cwd=None):
    events, native_id = _events(output, context, cwd)
    end, settled = events[-2:]
    if (end.get('type') != 'agent_end' or end.get('willRetry') is not False
            or settled.get('type') != 'agent_settled' or settled.get('aborted') is not False):
        raise NativeCliError('Pi returned no settled native turn')
    messages = end.get('messages')
    answer = messages[-1] if isinstance(messages, list) and messages else None
    if (not isinstance(answer, dict) or answer.get('role') != 'assistant'
            or answer.get('stopReason') != 'stop' or not isinstance(answer.get('content'), list)):
        raise NativeCliError('Pi returned no successful native answer')
    if any(not isinstance(part, dict) for part in answer['content']):
        raise NativeCliError('Pi returned invalid answer content')
    texts = [part.get('text') for part in answer['content'] if part.get('type') == 'text']
    if not texts or any(not isinstance(text, str) for text in texts) or not ''.join(texts).strip():
        raise NativeCliError('Pi native answer lacks actual text')
    return {'body': ''.join(texts), 'native_session_id': native_id,
            'native_evidence': {'event_count': len(events), 'terminal_event': 'agent_settled',
                                'stop_reason': 'stop', 'aborted': False}}
