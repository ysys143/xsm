"""Owned execution journal, separate from inbox handoffs and approval outboxes.

A pool belongs to one full native owner. Contexts are worker + native sender +
work unit (or a fresh independent request). Reservations precede acceptance.
Unknown side effects are never automatically retried. No expiry/deletion policy
is introduced; requests/results survive removal of the worker record.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import time
import uuid

from . import envelope, handoff, identity, paths

DIRECTORY = 'owned-requests'
ACTIVE = ('reserved', 'acknowledged', 'running', 'unknown')


class OwnedError(ValueError):
    pass


def _native(record):
    try:
        return handoff._identity(record)
    except ValueError as exc:
        raise OwnedError(str(exc)) from exc


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def _path(owner):
    return paths.path(DIRECTORY, _hash(_native(owner)) + '.json')


@contextmanager
def _locked(owner):
    filename = _path(owner)
    os.makedirs(os.path.dirname(filename), mode=0o700, exist_ok=True)
    fd = os.open(filename + '.lock', os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        state = paths.read_json(filename)
        if state is None:
            if os.path.exists(filename):
                raise OwnedError('corrupt owned journal; retained for readback')
            state = {'version': 1, 'owner': _native(owner), 'requests': {}, 'contexts': {}, 'slots': {}}
        if (not isinstance(state, dict) or state.get('version') != 1 or
                state.get('owner') != _native(owner) or
                any(not isinstance(state.get(k), dict) for k in ('requests', 'contexts', 'slots'))):
            raise OwnedError('invalid owned journal; never reset silently')
        yield state
        handoff._write(filename, state)
    finally:
        os.close(fd)


def _load(owner):
    filename = _path(owner)
    if not os.path.exists(filename):
        return None
    state = paths.read_json(filename)
    if not isinstance(state, dict) or state.get('owner') != _native(owner) or state.get('version') != 1:
        raise OwnedError('invalid owned journal')
    return state


def _event(request, phase):
    request['state'] = phase
    request.setdefault('events', []).append({'phase': phase, 'at': time.time()})


def _process():
    pid = os.getpid()
    start = identity.lstart(pid)
    if not start:
        raise OwnedError('cannot reserve without actual controller generation')
    return {'pid': pid, 'lstart': start}


def _alive(process):
    if not process or not process.get('pid') or not process.get('lstart'):
        return None
    if not identity.pid_alive(process['pid']):
        return False
    start = identity.lstart(process['pid'])
    return start == process['lstart'] if start else None


def _get(state, request_id):
    handoff._id(request_id)
    request = state['requests'].get(request_id)
    if request is None:
        raise OwnedError('no owned request ' + request_id)
    return request


def _view(state, request):
    result = copy.deepcopy(request)
    result['status'] = result.pop('state')
    result['context'] = copy.deepcopy(state['contexts'][request['context_id']])
    result['persisted'] = True
    result['accepted'] = result['status'] != 'queued'  # admission, never task success
    result['side_effects_exactly_once'] = False
    execution = _unknown_child_state(request) if request['state'] == 'unknown' else None
    result['slot_occupied'] = request['state'] in ACTIVE and execution != 'exited'
    if execution is not None:
        result['execution_state'] = execution
    return result


def submit(owner, worker, sender, work_context, body, *, request_id=None, independent=False):
    if worker.get('mode') != 'owned' or worker.get('owned') is not True:
        raise OwnedError('ordinary sessions cannot be adopted as headless workers')
    if _native(worker.get('owner')) != _native(owner):
        raise OwnedError('worker belongs to another native owner')
    if not isinstance(work_context, str) or not work_context.strip():
        raise OwnedError('explicit work_context required')
    if not isinstance(body, str) or not body.strip() or not isinstance(independent, bool):
        raise OwnedError('nonempty body and boolean independent required')
    request_id = request_id or envelope.new_id()
    handoff._id(request_id)
    sender_id = _native(sender)
    plan = {'worker': {k: worker.get(k) for k in ('id', 'runtime', 'home', 'cwd', 'model', 'effort')},
            'sender': sender_id, 'work_context': work_context, 'independent': independent,
            'body': envelope.request_identity(request_id, sender, None, body, kind='task')['body']}
    digest = _hash(plan)
    context_id = _hash([worker['id'], sender_id, work_context, request_id if independent else None])
    with _locked(owner) as state:
        previous = state['requests'].get(request_id)
        if previous is not None:
            if previous['digest'] != digest:
                raise OwnedError('request ID differs in sender, work context, body or worker plan')
            return _view(state, previous)
        context_key = context_id
        context = next((c for c in state['contexts'].values()
                        if c.get('context_key', c['id']) == context_key and not c.get('retired')), None)
        if context is None:
            if context_id in state['contexts']:
                context_id = _hash([context_key, uuid.uuid4().hex])
            context = {'id': context_id, 'context_key': context_key, 'epoch': uuid.uuid4().hex, 'worker_id': worker['id'],
                       'sender': sender_id, 'work_context': work_context, 'independent': independent,
                       'native_session_id': None, 'session_seed': str(uuid.uuid4()),
                       'retired': False, 'unknown_request': None, 'created_at': time.time()}
            state['contexts'][context_id] = context
        else:
            context_id = context['id']
        request = {'id': request_id, 'digest': digest, 'owner': _native(owner),
                   'sender': copy.deepcopy(sender), 'worker': copy.deepcopy(worker),
                   'work_context': work_context, 'body': body, 'context_id': context_id,
                   'context_epoch': context['epoch'], 'created_at': time.time(),
                   'sequence': len(state['requests']),
                   'result': None, 'reply_id': None, 'send_evidence': None, 'reservation': None}
        _event(request, 'queued')
        state['requests'][request_id] = request
        return _view(state, request)


def status(owner, request_id, *, sender=None):
    handoff._id(request_id)
    state = _load(owner)
    if state is None or request_id not in state.get('requests', {}):
        return {'status': 'not-found', 'id': request_id}
    request = _get(state, request_id)
    if sender is not None and _native(sender) != _native(request['sender']):
        return {'status': 'refused', 'id': request_id}
    return _view(state, request)


def list_requests(owner, sender):
    """Recover caller-owned auto IDs after a cancelled/lost run response.

    Read-only metadata only: never return other senders' requests or answer
    bodies. Request/result journals remain available independently of workers.
    """
    wanted = _native(sender)
    state = _load(owner)
    if state is None:
        return []
    rows = []
    for request in state['requests'].values():
        if _native(request['sender']) != wanted:
            continue
        rows.append({'id': request['id'], 'status': request['state'],
                     'worker': request['worker']['name'], 'work_context': request['work_context'],
                     'context_id': request['context_id'], 'created_at': request['created_at'],
                     'digest': request['digest'], 'preview': envelope.preview(request['body']),
                     'reply_id': request['reply_id']})
    return rows


def retained_requests(sender, *, request_id=None, worker_name=None):
    """Read only this sender's archived requests after worker metadata is gone.

    The native sender, not the display name, authorizes history access. No
    service is recreated and no model or publication is started here.
    """
    wanted=_native(sender)
    try:
        names=os.listdir(paths.path(DIRECTORY))
    except FileNotFoundError:
        return []
    found=[]
    for name in names:
        if not name.endswith('.json'):continue
        state=paths.read_json(paths.path(DIRECTORY,name))
        if (not isinstance(state,dict) or state.get('version')!=1 or
                not isinstance(state.get('requests'),dict) or not isinstance(state.get('contexts'),dict)):
            raise OwnedError('retained journal is unavailable; no history was discarded')
        if name!=_hash(_native(state.get('owner')))+'.json':
            raise OwnedError('retained journal owner does not match its storage identity')
        for request in state['requests'].values():
            if (_native(request.get('sender'))!=wanted or
                    (request_id is not None and request.get('id')!=request_id) or
                    (worker_name is not None and (request.get('worker') or {}).get('name')!=worker_name)):
                continue
            value=_view(state,request)
            value['worker_record_present']=False
            found.append(value)
    return found


def _unknown_child_state(request):
    """Separate uncertain effects from whether an actual child still occupies a slot."""
    child = request.get('child')
    if not isinstance(child, dict) or not child.get('pid'):
        return 'unverified'
    if type(child.get('returncode')) is int:
        return 'exited'  # observed wait result, including a known nonzero exit
    alive = _alive(child)
    return 'exited' if alive is False else 'running' if alive is True else 'unverified'


def _occupies_slot(request):
    return (request['state'] in ACTIVE and
            (request['state'] != 'unknown' or _unknown_child_state(request) != 'exited'))


def _busy(state):
    # unknown remains ACTIVE for context fencing/retirement. A confirmed exited
    # child cannot consume execution capacity; no-child uncertainty still does.
    return sum(_occupies_slot(r) for r in state['requests'].values()) + len(state['slots'])


def _foreign(extra_busy, state):
    names = {s.get('worker_name') for s in state['slots'].values()}
    value = extra_busy(names) if callable(extra_busy) else extra_busy
    if type(value) is not int or value < 0:
        raise OwnedError('invalid external busy count')
    return value


def active_count(owner, *, extra_busy=0):
    state = _load(owner)
    state = state or {'requests': {}, 'slots': {}}
    return _busy(state) + _foreign(extra_busy, state)


def reserve(owner, request_id, capacity, *, extra_busy=0):
    if type(capacity) is not int or capacity < 0:
        raise OwnedError('capacity must be an explicit nonnegative integer')
    with _locked(owner) as state:
        request = _get(state, request_id)
        if request['state'] != 'queued':
            result = _view(state, request)
            result['reservation_acquired'] = False
            return result
        context = state['contexts'][request['context_id']]
        busy = _busy(state) + _foreign(extra_busy, state)
        reason = None
        if context.get('unknown_request'):
            reason = 'context-unknown'
        elif any(r['context_id'] == request['context_id'] and r['state'] in ACTIVE
                 for r in state['requests'].values()):
            reason = 'context-busy'
        elif any(r['context_id'] == request['context_id'] and r['state'] == 'queued'
                 and r.get('sequence', 0) < request.get('sequence', 0)
                 for r in state['requests'].values()):
            reason = 'context-order'
        elif busy >= capacity:
            reason = 'capacity'
        if reason:
            request['queue_reason'] = reason
            result = _view(state, request)
            result['capacity'] = {'limit': capacity, 'busy': busy, 'available': max(0, capacity - busy)}
            result['admission'] = 'overloaded' if reason == 'capacity' else reason
            return result
        request.pop('queue_reason', None)
        request['reservation'] = {'token': uuid.uuid4().hex, 'controller': _process()}
        _event(request, 'reserved')
        result = _view(state, request)
        result['reservation_acquired'] = True
        result['capacity'] = {'limit': capacity, 'busy': busy + 1, 'available': max(0, capacity - busy - 1)}
        return result


def reserve_worker_slot(owner, worker_name, capacity, *, extra_busy=0):
    """Bridge legacy TUI spawn admission to the same owned capacity lock."""
    with _locked(owner) as state:
        if any(s.get('worker_name') == worker_name for s in state['slots'].values()):
            raise OwnedError('worker startup is already reserved')
        busy = _busy(state) + _foreign(extra_busy, state)
        if busy >= capacity:
            raise OwnedError('max_workers capacity reserved/busy: %d/%d' % (busy, capacity))
        token = uuid.uuid4().hex
        state['slots'][token] = {'worker_name': worker_name, 'controller': _process(), 'created_at': time.time()}
        return token


def release_worker_slot(owner, token):
    with _locked(owner) as state:
        state['slots'].pop(token, None)


def _token(request, token):
    if not request.get('reservation') or request['reservation'].get('token') != token:
        raise OwnedError('invalid execution reservation token')


def acknowledge(owner, request_id, token):
    with _locked(owner) as state:
        request = _get(state, request_id)
        _token(request, token)
        if request['state'] == 'reserved':
            _event(request, 'acknowledged')
        elif request['state'] != 'acknowledged':
            raise OwnedError('request is not reserved for acknowledgement')
        return _view(state, request)


def begin(owner, request_id, token):
    with _locked(owner) as state:
        request = _get(state, request_id)
        _token(request, token)
        if request['state'] != 'acknowledged':
            raise OwnedError('execution requires durable acknowledgement')
        _event(request, 'running')
        request['run_attempts'] = request.get('run_attempts', 0) + 1
        return _view(state, request)


def release_reservation(owner, request_id, token):
    """Cancel before execution only; a begun effect requires unknown/readback."""
    with _locked(owner) as state:
        request = _get(state, request_id)
        _token(request, token)
        if request['state'] not in ('reserved', 'acknowledged'):
            raise OwnedError('cannot release an execution that may have effects')
        request['reservation'] = None
        _event(request, 'queued')
        return _view(state, request)


def note_child(owner, request_id, token, pid, lstart, *, argv=None, stdout=None, stderr=None):
    with _locked(owner) as state:
        request = _get(state, request_id)
        _token(request, token)
        if request['state'] != 'running':
            raise OwnedError('no active owned run')
        request['child'] = {'pid': pid, 'lstart': lstart, 'argv': copy.deepcopy(argv),
                            'stdout': stdout, 'stderr': stderr}


def note_exit(owner, request_id, token, returncode):
    """Persist the observed child exit before parsing or reconciling output."""
    if type(returncode) is not int:
        raise OwnedError('actual child return code required')
    with _locked(owner) as state:
        request = _get(state, request_id)
        _token(request, token)
        if request['state'] != 'running' or not request.get('child'):
            raise OwnedError('no recorded owned child')
        request['child']['returncode'] = returncode


def save_result(owner, request_id, token, result):
    if not isinstance(result, dict) or not isinstance(result.get('body'), str) or not result['body'].strip():
        raise OwnedError('actual model result body required; errors are not answers')
    if result.get('outcome') not in (None,) + envelope.OUTCOMES:
        raise OwnedError('invalid explicit outcome')
    native_id = result.get('native_session_id')
    if not isinstance(native_id, str) or not native_id:
        raise OwnedError('actual native conversation ID required')
    with _locked(owner) as state:
        request = _get(state, request_id)
        _token(request, token)
        context = state['contexts'][request['context_id']]
        if context['epoch'] != request['context_epoch']:
            raise OwnedError('context generation changed')
        if context['native_session_id'] not in (None, native_id):
            raise OwnedError('native conversation changed on resume')
        if request['result'] is not None:
            if request['result'] != result:
                raise OwnedError('stored result is immutable')
            return _view(state, request)
        if request['state'] not in ('running', 'unknown'):
            raise OwnedError('cannot store result without an owned run')
        context['native_session_id'] = native_id
        context['unknown_request'] = None
        request['result'] = copy.deepcopy(result)
        request['result_digest'] = _hash(result)
        request['reply_id'] = uuid.uuid4().hex[:16]
        _event(request, 'result-ready')
        return _view(state, request)


def mark_unknown(owner, request_id, token, reason):
    with _locked(owner) as state:
        request = _get(state, request_id)
        _token(request, token)
        if request['result'] is None:
            _event(request, 'unknown')
            request['error'] = str(reason)
            state['contexts'][request['context_id']]['unknown_request'] = request_id
        return _view(state, request)


def fail_not_started(owner, request_id, token, reason):
    """A proven process-creation failure is error, not a model answer."""
    with _locked(owner) as state:
        request = _get(state, request_id)
        _token(request, token)
        if request['state'] != 'running' or request.get('child'):
            raise OwnedError('cannot prove execution never started')
        _event(request, 'error')
        request['error'] = str(reason)
        return _view(state, request)


def claim_send(owner, request_id):
    with _locked(owner) as state:
        request = _get(state, request_id)
        if request['state'] != 'result-ready':
            result = _view(state, request)
            result['send_acquired'] = False
            return result
        request['send_owner'] = _process()
        request['send_token'] = uuid.uuid4().hex
        _event(request, 'sending')
        result = _view(state, request)
        result['send_acquired'] = True
        return result


def finish_send(owner, request_id, token, evidence):
    with _locked(owner) as state:
        request = _get(state, request_id)
        if request['state'] != 'sending' or request.get('send_token') != token:
            raise OwnedError('invalid result-send ownership')
        evidence = copy.deepcopy(evidence)
        if not isinstance(evidence, dict):
            raise OwnedError('explicit reply transport evidence required')
        if evidence.get('id') not in (None, request['reply_id']):
            raise OwnedError('transport changed the persisted reply ID')
        request['send_evidence'] = evidence
        delivery = evidence.get('status')
        accepted = delivery in ('sent-unconfirmed', 'delivered')
        _event(request, 'sent' if accepted else 'reply-stored' if delivery == 'stored' else 'result-ready')
        return _view(state, request)


def recover(owner):
    """Recover pre-run and send ownership, never rerun an uncertain side effect."""
    with _locked(owner) as state:
        for request in state['requests'].values():
            controller = (request.get('reservation') or {}).get('controller')
            if request['state'] in ('reserved', 'acknowledged') and _alive(controller) is False:
                request['reservation'] = None
                _event(request, 'queued')
            elif request['state'] == 'running' and _alive(controller) is False:
                _event(request, 'unknown')
                state['contexts'][request['context_id']]['unknown_request'] = request['id']
            elif request['state'] == 'sending' and _alive(request.get('send_owner')) is False:
                _event(request, 'result-ready')
        return [_view(state, r) for r in state['requests'].values()]


def retire_context(owner, context_id):
    """Explicit idle-only retirement; no new or busy context is evicted."""
    with _locked(owner) as state:
        if context_id not in state['contexts']:
            raise OwnedError('unknown context')
        if any(r['context_id'] == context_id and r['state'] in ACTIVE + ('queued', 'sending')
               for r in state['requests'].values()):
            raise OwnedError('cannot retire a busy or uncertain context')
        state['contexts'][context_id]['retired'] = True
