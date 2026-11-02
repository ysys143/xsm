"""Native OpenClaw session RPC contracts; no runtime, policy or model emulation."""
from __future__ import annotations

import json
import os
import math


class NativeSessionError(ValueError):
    pass


def _text(value, label):
    if (not isinstance(value, str) or not value or len(value) > 4096
            or any(ord(char) < 32 for char in value)):
        raise NativeSessionError('invalid native ' + label)
    return value


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise NativeSessionError('duplicate native RPC field')
        result[key] = value
    return result


def _constant(value):
    raise NativeSessionError('non-JSON native RPC number')


def _workspace(cwd):
    if not isinstance(cwd, str) or not os.path.isabs(cwd) or not os.path.isdir(cwd):
        raise NativeSessionError('existing absolute native workspace required')
    return os.path.realpath(cwd)


def decode_reply(output):
    try:
        value = json.loads(output, object_pairs_hook=_unique, parse_constant=_constant)
    except (ValueError, TypeError, RecursionError) as error:
        raise NativeSessionError('invalid native RPC reply') from error
    if not isinstance(value, dict):
        raise NativeSessionError('native RPC reply must be an object')
    return value


def creation_params(agent_id, cwd, *, model=None, idempotency_key=None):
    _workspace(cwd)
    # Omitting key lets the native host allocate a fresh key AND session ID.
    # No initial message may start inference before the private identity bind.
    params = {'agentId': _text(agent_id, 'agent ID'), 'cwd': cwd, 'message': ''}
    if model is not None: params['model'] = _text(model, 'model')
    if idempotency_key is not None: params['idempotencyKey'] = _text(idempotency_key, 'create key')
    return params


def created_locator(reply, agent_id, cwd):
    expected_cwd = _workspace(cwd)
    if reply.get('ok') is not True or reply.get('runStarted') is not False:
        raise NativeSessionError('native session creation did not confirm a non-running entry')
    sid, key = _text(reply.get('sessionId'), 'session ID'), _text(reply.get('key'), 'session key')
    entry = reply.get('entry')
    if not isinstance(entry, dict) or entry.get('sessionId') != sid or entry.get('execNode'):
        raise NativeSessionError('native session creation changed its local identity')
    revision = _text(entry.get('lifecycleRevision'), 'lifecycle revision')
    workspace = entry.get('spawnedCwd') or entry.get('sessionRoot')
    if (not isinstance(workspace, str) or not os.path.isabs(workspace)
            or os.path.realpath(workspace) != expected_cwd):
        raise NativeSessionError('native session creation changed workspace')
    return {'agent_id': _text(agent_id, 'agent ID'), 'native_session_id': sid,
            'native_session_key': key, 'native_lifecycle_revision': revision, 'cwd': expected_cwd}


def resolution_params(native_id, agent_id):
    return {'sessionId': _text(native_id, 'session ID'), 'agentId': _text(agent_id, 'agent ID')}


def resolved_key(reply, agent_id):
    if reply.get('ok') is not True or reply.get('agentId') != agent_id:
        raise NativeSessionError('native session resolution is missing or belongs to another agent')
    return _text(reply.get('key'), 'session key')


def description_params(key, agent_id):
    return {'key': _text(key, 'session key'), 'agentId': _text(agent_id, 'agent ID')}


def described_listing(reply, key, agent_id):
    """Normalize exactly one native description for the shared identity checks."""
    row = reply.get('session')
    if not isinstance(row, dict) or row.get('key') != key or row.get('agentId') != agent_id:
        raise NativeSessionError('native session description is missing or changed identity')
    return {'sessions': [row]}


def resolved_locator(reply, listing, native_id, agent_id, cwd):
    key = resolved_key(reply, agent_id)
    rows = listing.get('sessions')
    if not isinstance(rows, list): raise NativeSessionError('native session listing unavailable')
    matches = [row for row in rows if isinstance(row, dict) and row.get('key') == key]
    if (len(matches) != 1 or matches[0].get('sessionId') != native_id
            or matches[0].get('agentId') != agent_id):
        raise NativeSessionError('native session resolution changed or is ambiguous')
    return {'agent_id': _text(agent_id, 'agent ID'), 'native_session_id': _text(native_id, 'session ID'),
            'native_session_key': key, 'native_lifecycle_revision': _text(matches[0].get('lifecycleRevision'), 'lifecycle revision'),
            'cwd': _workspace(cwd)}


def agent_params(locator, message, request_id):
    """Build backend-only constraints, not an operator gateway-call payload.

    Native operator clients cannot dispatch these identity fences. Do not drop
    them to permit a reset between binding and admission to change context.
    Workspace is inherited from native creation; agent.cwd is plugin-only.
    """
    if not isinstance(message, str) or not message.strip(): raise NativeSessionError('native task body required')
    _workspace(locator.get('cwd'))
    return {'agentId': _text(locator.get('agent_id'), 'agent ID'), 'sessionId': _text(locator.get('native_session_id'), 'session ID'),
            'sessionKey': _text(locator.get('native_session_key'), 'session key'),
            'expectedExistingSessionId': locator['native_session_id'],
            'expectedExistingSessionLifecycleRevision': _text(locator.get('native_lifecycle_revision'), 'lifecycle revision'),
            'message': message,
            'idempotencyKey': _text(request_id, 'request ID'), 'deliver': False}


def accepted_run(reply, locator, request_id):
    """A native acceptance is not a terminal result or a delivery ACK."""
    if (reply.get('status') != 'accepted' or reply.get('runId') != request_id
            or reply.get('sessionKey') != locator.get('native_session_key')
            or reply.get('agentId') != locator.get('agent_id')):
        raise NativeSessionError('native admission changed run or session identity')
    return _text(reply.get('runId'), 'run ID')


def completed_run(reply, locator, run_id):
    """Accept only a completed native receipt for this bound session and turn."""
    receipt = reply.get('terminalReceipt')
    if (reply.get('status') != 'ok' or reply.get('stopReason') in ('rpc', 'aborted') or reply.get('runId') != run_id
            or not isinstance(receipt, dict) or receipt.get('runId') != run_id
            or receipt.get('turnId') != run_id
            or receipt.get('sessionId') != locator.get('native_session_id')):
        raise NativeSessionError('native terminal receipt is missing or changed identity')
    terminal = reply.get('terminalReply')
    if not isinstance(terminal, dict) or terminal.get('disposition') not in ('visible', 'silent', 'empty'):
        raise NativeSessionError('native terminal reply is missing')
    if (receipt.get('terminalDisposition') != terminal['disposition']
            or (terminal['disposition'] == 'visible' and not isinstance(terminal.get('text'), str))):
        raise NativeSessionError('native terminal reply conflicts with receipt')
    return dict(terminal)


def cancellation_params(locator, run_id):
    return {'agentId': _text(locator.get('agent_id'), 'agent ID'),
            'sessionKey': _text(locator.get('native_session_key'), 'session key'),
            'runId': _text(run_id, 'run ID'), 'preserveSideRuns': True}


def stopped_run(terminal, listing, locator, run_id, abort):
    """Abort acceptance alone is insufficient; require exact native settlement."""
    if (not isinstance(abort, dict) or abort.get('ok') is not True or abort.get('aborted') is not True
            or not isinstance(abort.get('runIds'), list) or run_id not in abort['runIds']):
        raise NativeSessionError('native abort was not accepted for this run')
    if (terminal.get('runId') != run_id or terminal.get('status') != 'error'
            or terminal.get('stopReason') != 'rpc'):
        raise NativeSessionError('native abort has no stopped terminal observation')
    start, end = terminal.get('startedAt'), terminal.get('endedAt')
    queued = terminal.get('providerStarted') is False
    if type(end) not in (int, float) or not math.isfinite(end) or end <= 0:
        raise NativeSessionError('native abort has no execution settlement times')
    if queued:
        if start is not None:
            raise NativeSessionError('native unstarted run contains a start time')
    elif type(start) not in (int, float) or not math.isfinite(start) or start <= 0 or end < start:
        raise NativeSessionError('native abort has no execution settlement times')
    rows = listing.get('sessions')
    if not isinstance(rows, list):
        raise NativeSessionError('native abort session observation unavailable')
    matches = [row for row in rows if isinstance(row, dict) and row.get('key') == locator.get('native_session_key')]
    if len(matches) != 1:
        raise NativeSessionError('native abort session observation is ambiguous')
    row = matches[0]
    if (row.get('sessionId') != locator.get('native_session_id') or row.get('agentId') != locator.get('agent_id')
            or row.get('lifecycleRevision') != locator.get('native_lifecycle_revision')
            or row.get('hasActiveRun') is not False or row.get('activeRunIds') != []):
        raise NativeSessionError('native abort session identity or settlement changed')
    if queued:
        fields = ('key', 'sessionId', 'agentId', 'lifecycleRevision', 'hasActiveRun', 'activeRunIds')
        return {**{name: row[name] for name in fields}, 'native_provider_not_started': True}
    if (row.get('lastRunId') != run_id or row.get('status') != 'killed' or row.get('abortedLastRun') is not True
            or row.get('startedAt') != start or row.get('endedAt') != end):
        raise NativeSessionError('native abort run settlement changed')
    fields = ('key', 'sessionId', 'agentId', 'lifecycleRevision', 'lastRunId', 'status',
              'abortedLastRun', 'hasActiveRun', 'activeRunIds', 'startedAt', 'endedAt')
    return {name: row[name] for name in fields}


def failed_run_settlement(terminal, row, locator, run_id):
    """Observe a closed native execution without turning its error into an answer."""
    def positive(value):
        try:
            return type(value) in (int,float) and math.isfinite(value) and value > 0
        except OverflowError:
            return False
    if (terminal.get('runId') != run_id or terminal.get('status') != 'error'
            or not positive(terminal.get('endedAt')) or terminal.get('pendingError') is not None
            or any(terminal.get(key) is not None and terminal.get(key) is not False
                   for key in ('yielded','retryableTransportError'))):
        raise NativeSessionError('native failure has no final execution observation')
    if (row.get('key') != locator.get('native_session_key') or row.get('sessionId') != locator.get('native_session_id')
            or row.get('agentId') != locator.get('agent_id') or row.get('lifecycleRevision') != locator.get('native_lifecycle_revision')
            or row.get('hasActiveRun') is not False or row.get('activeRunIds') != []):
        raise NativeSessionError('native failure identity or activity changed')
    queued = terminal.get('providerStarted') is False
    start,end = terminal.get('startedAt'),terminal['endedAt']
    if queued:
        if start is not None:
            raise NativeSessionError('native unstarted failure contains a start time')
    elif (not positive(start) or not positive(row.get('startedAt')) or row['startedAt'] != start
            or row.get('lastRunId') != run_id or row.get('status') not in ('failed','blocked','killed','error','done')
            or not positive(row.get('endedAt')) or not start <= row['endedAt'] <= end):
        raise NativeSessionError('native failure has no matching closed run interval')
    return {'native_state':'settled','source':'native-agent.wait','run_id':_text(run_id,'run ID'),
            'terminal_status':'error','native_status':None if queued else row['status'],
            'key':locator['native_session_key'],'lifecycle_revision':locator['native_lifecycle_revision'],
            'started_at':start,'ended_at':end,'native_ended_at':None if queued else row['endedAt'],
            'native_provider_not_started':queued}


def closed_success(row, locator, run_id):
    """A persisted closed session run, not a synthesized terminal receipt."""
    if (row.get('key') != locator.get('native_session_key') or row.get('agentId') != locator.get('agent_id')
            or row.get('sessionId') != locator.get('native_session_id')
            or row.get('lifecycleRevision') != locator.get('native_lifecycle_revision')
            or row.get('lastRunId') != run_id or row.get('status') != 'done'
            or row.get('abortedLastRun') is not False or row.get('hasActiveRun') is not False
            or row.get('activeRunIds') != []):
        raise NativeSessionError('native persisted run is not the bound closed execution')
    start,end=row.get('startedAt'),row.get('endedAt')
    if (any(type(value) not in (int,float) or not math.isfinite(value) or value <= 0 for value in (start,end))
            or end < start):
        raise NativeSessionError('native persisted run has no closed interval')
    return start,end


def history_result(history, locator, run_id):
    """Read one final model message by native run ownership, never by latest text."""
    if (history.get('sessionKey') != locator['native_session_key'] or history.get('sessionId') != locator['native_session_id']
            or not isinstance(history.get('sessionInfo'),dict) or not isinstance(history.get('messages'),list)):
        raise NativeSessionError('native history changed conversation identity')
    start,end=closed_success(history['sessionInfo'],locator,run_id)
    pending=history.get('pendingInputs')
    if not isinstance(pending,dict) or type(pending.get('total')) is not int or pending['total'] != 0 or pending.get('items') != []:
        raise NativeSessionError('native history has pending input')
    inputs=[];answers=[]
    for message in history['messages']:
        if not isinstance(message,dict):raise NativeSessionError('invalid native history message')
        meta=message.get('__openclaw')
        if not isinstance(meta,dict):continue
        if (message.get('role') == 'user' and message.get('idempotencyKey') == run_id+':user'
                and meta.get('idempotencyKey') == run_id+':user'):
            inputs.append((message,meta))
        if message.get('role') == 'assistant' and meta.get('runId') == run_id and message.get('stopReason') == 'stop':
            answers.append((message,meta))
    if len(inputs) != 1 or len(answers) != 1:
        raise NativeSessionError('native history has no unambiguous bound input and final answer')
    _input,user=inputs[0];answer,meta=answers[0]
    upos,apos=user.get('transcriptPosition'),meta.get('transcriptPosition')
    if (answer.get('phase') not in (None,'final') or answer.get('openclawStreamFallback') is not None
            or any(value is not None and value is not False for value in (meta.get('truncated'),answer.get('truncated')))
            or not isinstance(upos,dict) or not isinstance(apos,dict)
            or not isinstance(upos.get('source'),str) or not upos['source'] or upos['source'] != apos.get('source')
            or any(type(value) is not int or value <= 0 for value in (user.get('seq'),meta.get('seq'),upos.get('rawSeq'),apos.get('rawSeq')))
            or user['seq'] >= meta['seq'] or upos['rawSeq'] >= apos['rawSeq']):
        raise NativeSessionError('native history answer is partial or changed transcript branch')
    content=answer.get('content')
    if isinstance(content,str):text=content
    elif isinstance(content,list) and all(isinstance(part,dict) and part.get('type') in ('text','thinking','redactedThinking') for part in content):
        texts=[part.get('text') for part in content if part.get('type') == 'text']
        if any(not isinstance(value,str) for value in texts):raise NativeSessionError('invalid native answer text')
        text=''.join(texts)
    else:raise NativeSessionError('native history has no complete text answer')
    if not text.strip():raise NativeSessionError('native history answer is empty')
    return {'native_session_id':locator['native_session_id'],'body':text,
            'native_evidence':{'source':'native-chat.history','run_id':_text(run_id,'run ID'),
                'input_message_id':_text(user.get('id'),'input message ID'),
                'assistant_message_id':_text(meta.get('id'),'assistant message ID'),
                'transcript_source':apos['source'],'started_at':start,'ended_at':end}}
