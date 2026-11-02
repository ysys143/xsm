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


def _events(output, context):
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
    if any(event.get('sessionID') != native_id for event in events):
        raise NativeCliError('OpenCode changed conversations within one turn')
    return events, native_id


def parse_cancellation(output, context):
    if context.get('native_session_id') is None:
        raise NativeCliError('OpenCode cancellation requires a bound native conversation')
    events, native_id = _events(output, context)
    observations = [event for event in events if event.get('type') == 'xsm_native_cancelled']
    if observations:
        if len(observations) != 1:
            raise NativeCliError('OpenCode cancellation observation is ambiguous')
        observed = observations[0]
        if (observed.get('source') != 'opencode/1.19.5' or observed.get('native_idle') is not True
                or observed.get('native_error') != 'MessageAbortedError'
                or type(observed.get('native_completed')) is not int or observed['native_completed'] <= 0
                or any(not isinstance(observed.get(field), str) or not re.fullmatch(r'msg_[A-Za-z0-9]+', observed[field])
                       for field in ('native_input_message_id', 'native_assistant_message_id'))):
            raise NativeCliError('OpenCode cancellation observation lacks native evidence')
        trailing = events[events.index(observed) + 1:]
        if any(event.get('type') != 'error' or not isinstance(event.get('error'), dict)
               or event['error'].get('name') != 'MessageAbortedError'
               for event in trailing):
            raise NativeCliError('OpenCode continued after its cancellation observation')
        return {'native_session_id': native_id, 'native_evidence': {
            'native_state': 'stopped', 'terminal_event': 'xsm_native_cancelled',
            'native_error': 'MessageAbortedError', 'event_count': len(events),
            'native_input_message_id': observed['native_input_message_id'],
            'native_assistant_message_id': observed['native_assistant_message_id']}}
    terminal = events[-1]
    if (terminal.get('type') != 'error' or not isinstance(terminal.get('error'), dict)
            or terminal['error'].get('name') != 'MessageAbortedError'):
        raise NativeCliError('OpenCode returned no native aborted error')
    return {'native_session_id': native_id,
            'native_evidence': {'native_state': 'stopped', 'terminal_event': 'error',
                                'native_error': 'MessageAbortedError', 'event_count': len(events)}}


def parse_result(output, context):
    events, native_id = _events(output, context)
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
