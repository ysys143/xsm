"""Explicit same-conversation profile transfers, durable fencing and address leases.

Native transcripts are not copied here. The user's scoped approval transfers xsm
state; it never transfers an old human permission answer to another profile.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import fcntl
import hashlib
import json
import os
import math
import time

from . import context, handoff, identity, paths, registry

DIRECTORY = 'profile-migrations'
FORWARD_SECONDS = 24 * 60 * 60
REVISION = 1


class MigrationError(ValueError):
    pass


def endpoint(record):
    return handoff._identity(record)


def key(record):
    return hashlib.sha256(json.dumps(endpoint(record), sort_keys=True).encode()).hexdigest()


def _file(ident):
    if not isinstance(ident, str) or len(ident) != 64 or any(c not in '0123456789abcdef' for c in ident):
        raise MigrationError('invalid migration ID')
    return paths.path(DIRECTORY, ident + '.json')


def _index(record, role='source'):
    return paths.path(DIRECTORY, role, key(record) + '.json')


def read(ident):
    return paths.read_json(_file(ident))


def retirement(record):
    if not isinstance(record, dict) or not all(record.get(k) for k in ('runtime', 'home', 'session_id')):
        return None
    value = paths.read_json(_index(record))
    if value and value.get('status') == 'retired':
        return read(value['id'])
    return None


def generation(record):
    return {k: record.get(k) for k in ('pid', 'lstart', 'protocol_generation')}


def generation_blocked(record):
    if not isinstance(record, dict) or not all(record.get(k) for k in ('runtime', 'home', 'session_id', 'pid')):
        return False
    marker = paths.read_json(_index(record), {})
    if marker.get('status') != 'active':
        return False
    actual = generation(record)
    for old in marker.get('blocked_generations', []):
        if old['pid'] == actual['pid'] and old.get('protocol_generation') == actual.get('protocol_generation'):
            if actual['lstart'] is None or old['lstart'] == actual['lstart']:
                return True
    return False


def has_generation_fences(record):
    if not isinstance(record, dict) or not all(record.get(k) for k in ('runtime', 'home', 'session_id')):
        return False
    return bool(paths.read_json(_index(record), {}).get('blocked_generations'))


def registration_blocked(candidate, published):
    if generation_blocked(candidate):
        return True
    marker = paths.read_json(_index(candidate), {})
    return bool(marker.get('status') == 'retired' and generation(candidate) in marker.get('blocked_generations', [])
                and published.get('pid') and generation(candidate) != generation(published))


def active_error(record):
    retired = retirement(record)
    if retired:
        owner = current_owner(record)
        return ('this xsm session is retired by migration %s; its place belongs to %s. '
                'It cannot register, send or claim work. A new user decision is required to reclaim it.'
                % (retired['id'], identity.address(owner) if owner else 'an incomplete transfer; inspect migration status'))
    if generation_blocked(record):
        return 'this execution was retired by profile migration; use the active conversation instance or obtain a new user decision'
    if isinstance(record, dict) and all(record.get(k) for k in ('runtime', 'home', 'session_id')):
        pending = paths.read_json(_index(record, 'target'))
        if pending:
            transfer = read(pending['id'])
            if transfer and transfer['status'] != 'committed':
                return 'profile migration %s is incomplete; resume that migration before acting' % transfer['id']
    return None


def assert_active(record):
    error = active_error(record)
    if error:
        raise MigrationError(error)


def current_owner(record):
    seen = set()
    while key(record) not in seen and len(seen) < 8:
        seen.add(key(record))
        moved = retirement(record)
        if not moved:
            if generation_blocked(record):
                return _current(record)
            return record
        if moved['status'] != 'committed':
            return None
        record = moved['target']
    return None


def fingerprint(record):
    return dict(endpoint(record), pid=record.get('pid'), lstart=record.get('lstart'),
                cwd=os.path.realpath(record.get('cwd') or ''), epoch=record.get('profile_epoch', 0),
                protocol_generation=record.get('protocol_generation'))


def _current(record):
    return registry.by_session(record['runtime'], record['session_id'], home=record['home'])


def _compatible(source, target):
    if endpoint(source) == endpoint(target):
        raise MigrationError('select the original conversation in another profile')
    native = lambda r: r.get('native_conversation') or r['session_id']
    if source['runtime'] != target['runtime'] or native(source) != native(target):
        raise MigrationError('profile migration requires copies of the same native conversation and runtime; use handover for other sessions')
    if os.path.realpath(source.get('cwd') or '') != os.path.realpath(target.get('cwd') or ''):
        raise MigrationError('the copied conversation is in a different folder')
    for record in (source, target):
        if record.get('profile_migration') != REVISION:
            raise MigrationError('a selected runtime predates profile migration support; reconnect or restart it before transferring')
    for beacon in registry.mcp_beacons():
        if beacon.get('ppid') in (source.get('pid'), target.get('pid')) and beacon.get('profile_migration') != REVISION:
            raise MigrationError('an active MCP reader predates profile fencing; reconnect it before transferring')


def prepare(me, source):
    from . import resolve
    if not all(me.get(k) for k in ('runtime', 'home', 'session_id', 'pid', 'lstart', 'cwd')):
        raise MigrationError('an exact registered foreground conversation is required')
    successor = _current(me)
    if not successor or (successor.get('state') != 'live' and not successor.get('retired')) or not identity.pid_alive(me['pid']):
        raise MigrationError('the successor is not a running foreground conversation')
    current_execution = {k: v for k, v in fingerprint(successor).items() if k != 'epoch'}
    caller_execution = {k: v for k, v in fingerprint(me).items() if k != 'epoch'}
    if current_execution != caller_execution:
        raise MigrationError('this execution is not the selected registered instance; use its current window')
    me = copy.deepcopy(successor)  # Epoch is server-owned; native bindings may cache the same live execution.
    found = resolve.resolve(source, include_offline=True, caller=me)
    if not found.ok or found.record.get('remote'):
        raise MigrationError(found.reason if not found.ok else 'select a local source')
    original = found.record
    _compatible(original, me)
    from . import handover
    if handover.load(original):
        raise MigrationError('the source already handed its place over; select its current owner')
    previous = retirement(original)
    if previous:
        if endpoint(previous['target']) != endpoint(me):
            raise MigrationError('this source has already transferred to another successor')
        return {'id': previous['id'], 'source': copy.deepcopy(previous['source']),
                'target': copy.deepcopy(me), 'resume': True}
    assert_active(original)
    target_retirement = retirement(me)
    if target_retirement and endpoint(target_retirement['target']) != endpoint(original):
        raise MigrationError('only the current successor can transfer this retired place back')
    ident = hashlib.sha256(json.dumps([fingerprint(original), fingerprint(me)], sort_keys=True).encode()).hexdigest()
    return {'id': ident, 'source': copy.deepcopy(original), 'target': copy.deepcopy(me), 'resume': False}


def question(plan):
    return ('Transfer the xsm place of session [%s] in %s to this conversation [%s] in %s? '
            'Retire the source, move its pending work and coordinator links, notify prior collaborators, and forward its old '
            'addresses for 24 hours. Pending human permissions require fresh answers here.' %
            (plan['source']['ref'], plan['source']['home'],
             plan['target']['ref'], plan['target']['home']))


@contextmanager
def _locked(plan):
    native = plan['source'].get('native_conversation') or plan['source']['session_id']
    lock = hashlib.sha256(json.dumps([plan['source']['runtime'], native]).encode()).hexdigest()
    filename = paths.path(DIRECTORY, 'locks', lock + '.lock')
    os.makedirs(os.path.dirname(filename), mode=0o700, exist_ok=True)
    with open(filename, 'a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _persist(record):
    handoff._write(_file(record['id']), record)


def _finalize(record):
    """Finish local activation even if a process stopped after the commit write."""
    with registry.lock_records([record['source'], record['target']]):
        marker = paths.read_json(_index(record['target']))
        expected = record.get('target_prior_retirement')
        if marker and marker['id'] not in (record['id'], expected):
            return  # A later transfer owns this endpoint; history cannot revive it.
        current = registry._read_pointer(record['target']['runtime'], record['target']['session_id'], record['target']['home'])
        if current:
            current['profile_epoch'] = max(current.get('profile_epoch', 0), record['target_epoch'])
            registry.save(current)
        blocked = (marker or {}).get('blocked_generations', [])
        blocked = [item for item in blocked if item != generation(record['target'])]
        paths.write_json(_index(record['target']), {'id': record['id'], 'status': 'active',
                         'active_generation': generation(record['target']), 'blocked_generations': blocked})


def execute(plan, *, authorize=None, fault=None, decision=None):
    """Apply/recover one transfer. Approval is collected before taking storage locks."""
    existing = read(plan['id'])
    if existing and existing['status'] == 'committed':
        _finalize(existing)
        from . import migration_state
        migration_state.notify(existing)
        return existing
    needs_answer = not existing or fingerprint(existing['target']) != fingerprint(plan['target'])
    approval = authorize(plan) if needs_answer and authorize else None
    if needs_answer and (not isinstance(approval, str) or not approval.strip()):
        raise MigrationError('profile migration needs the actual user approval source; nothing moved')
    with _locked(plan):
        record = read(plan['id'])
        if record and record['status'] == 'committed':
            _finalize(record)
            from . import migration_state
            migration_state.notify(record)
            return record
        with registry.lock_records([plan['source'], plan['target']]):
            target = _current(plan['target'])
            if (not target or fingerprint(target) != fingerprint(plan['target'])
                    or target.get('state') != 'live' and not target.get('retired')
                    or not identity.pid_alive(target['pid'])):
                raise MigrationError('successor execution changed while the question was open')
            if not record:
                source = _current(plan['source'])
                if not source or fingerprint(source) != fingerprint(plan['source']):
                    raise MigrationError('source execution changed while the question was open')
                _compatible(source, target)
                from . import migration_state
                record = {'id': plan['id'], 'version': REVISION, 'status': 'prepared',
                          'created_at': time.time(), 'source': source, 'target': target,
                          'approval': approval, 'decision': decision, 'steps': {}, 'snapshot': migration_state.snapshot(source, target),
                          'notices': {}, 'notes': [], 'target_epoch': target.get('profile_epoch', 0) + 1,
                          'target_prior_retirement': (retirement(target) or {}).get('id')}
                _persist(record)
            elif needs_answer:
                record.setdefault('approval_history', []).append(record['approval'])
                record.update(target=plan['target'], approval=approval)
                _persist(record)
            marker = paths.read_json(_index(record['source']), {})
            blocked = marker.get('blocked_generations', [])
            if generation(record['source']) not in blocked:
                blocked.append(generation(record['source']))
            paths.write_json(_index(record['source']), {'id': record['id'], 'status': 'retired',
                             'blocked_generations': blocked})
            paths.write_json(_index(record['target'], 'target'), {'id': record['id']})
            if record['status'] == 'prepared':
                record['status'] = 'fenced'
                _persist(record)
        if fault:
            fault('fenced')
        from . import migration_state
        for step, apply in migration_state.STEPS:
            if step not in record['steps']:
                value = apply(record)
                if fault:
                    fault('effect:' + step)
                record['steps'][step] = value
                record['status'] = 'moving'
                _persist(record)
            if fault:
                fault(step)
        # Stores/claims and registration share these short endpoint gates. A
        # sender queues under the same gate and releases it before waiting.
        with registry.lock_records([record['source'], record['target']]):
            record['steps']['messages'] = migration_state.messages(record)  # drain anything admitted before fencing
            migration_state.verify(record)
            record['status'] = 'committed'
            record['committed_at'] = time.time()
            record['committed_monotonic'] = time.clock_gettime(time.CLOCK_MONOTONIC)
            record['forward_until'] = record['committed_at'] + FORWARD_SECONDS
            _persist(record)
            _finalize(record)
        if fault:
            fault('committed')
        migration_state.notify(record)
        return read(record['id'])


def redirect(record, *, now=None):
    return _redirect(record, now=now, seen=set())


def _redirect(record, *, now, seen):
    if key(record) in seen or len(seen) >= 8:
        raise MigrationError('profile forwarding cycle or chain limit; inspect migration history')
    seen.add(key(record))
    transfer = retirement(record)
    if not transfer:
        return record, None
    if transfer['status'] != 'committed':
        raise MigrationError('profile migration %s is incomplete; original retained' % transfer['id'])
    now = time.time() if now is None else now
    _check_lease(transfer, now)
    successor = _current(transfer['target'])
    if not successor:
        raise MigrationError('profile successor is unavailable; source remains retired')
    if retirement(successor):
        return _redirect(successor, now=now, seen=seen)
    return successor, 'profile migrated to %s; old addresses forward for 24 hours' % identity.address(successor)


def _check_lease(transfer, now):
    filename = paths.path(DIRECTORY, 'leases', transfer['id'] + '.json')
    os.makedirs(os.path.dirname(filename), mode=0o700, exist_ok=True)
    with open(filename + '.lock', 'a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            lease = paths.read_json(filename, {})
            mono = time.clock_gettime(time.CLOCK_MONOTONIC)
            if now < max(transfer['committed_at'], lease.get('last_wall', transfer['committed_at'])) or mono < transfer['committed_monotonic']:
                raise MigrationError('profile forwarding clock is unknown; original is still retired')
            expired = (lease.get('expired') or now >= transfer['forward_until']
                       or mono - transfer['committed_monotonic'] >= FORWARD_SECONDS)
            paths.write_json(filename, {'last_wall': now, 'expired': bool(expired)})
            if expired:
                raise MigrationError('profile forwarding expired; use successor %s; source remains retired' %
                                     identity.address(transfer['target']))
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def forwarding_metadata(source, target):
    """Record the old address used, separately from the canonical recipient."""
    if not retirement(source):
        return None
    current, ids, seen = source, [], set()
    now = time.time()
    while retirement(current):
        if key(current) in seen or len(seen) >= 8:
            raise MigrationError('profile forwarding cycle')
        seen.add(key(current))
        record = retirement(current)
        if record['status'] != 'committed':
            raise MigrationError('profile migration is incomplete')
        _check_lease(record, now)
        ids.append(record['id'])
        current = record['target']
    if endpoint(current) != endpoint(target):
        raise MigrationError('profile target changed during routing')
    return {'ids': ids, 'source': endpoint(source), 'accepted_at': now}


def proves_copy(record, receiver):
    """Immutable request identity stays original; ownership changes only by a journal."""
    chain = record.get('migration_history') or []
    if not chain:
        return False
    canonical = record['identity']['to']
    previous = {'runtime': canonical['runtime'], 'home': canonical['home'], 'session_id': canonical['conversation']}
    for hop in chain:
        transfer = read(hop['id'])
        if (not transfer or transfer['status'] not in ('fenced', 'moving', 'committed')
                or endpoint(transfer['source']) != hop['source'] or endpoint(transfer['target']) != hop['target']
                or previous != hop['source']):
            return False
        previous = hop['target']
    from . import envelope
    return previous == endpoint(receiver) and envelope.request_digest(record['identity']) == record['digest']


def _json_files(folder):
    import glob
    return sorted(glob.glob(paths.path(folder, '*.json')))


def received(me):
    return [r for filename in _json_files(DIRECTORY)
            if (r := paths.read_json(filename)) and endpoint(r['target']) == endpoint(me)]


def file_source(me, storage_id):
    for original in handoff.records(me):
        if original.get('message', {}).get('file_storage') == storage_id and proves_copy(original, me):
            return original['message']['target']
    return None


def status(me, *, since=None):
    if since is not None and (type(since) not in (int, float) or not math.isfinite(since) or since < 0):
        raise MigrationError('since must be a nonnegative finite timestamp')
    from . import delivery_attempts, migration_state
    retired = retirement(me)
    owner = current_owner(me)
    return {'migrations': [migration_state.view(r, since=since) for r in received(me)],
            'retired': retired is not None, 'retired_by': retired['id'] if retired else None,
            'current_owner': identity.address(owner) if owner else None,
            'outgoing_failures': delivery_attempts.outgoing(me)}


def receipt(record):
    result = {k: record[k] for k in ('id', 'status', 'created_at', 'committed_at', 'forward_until')}
    result.update(source=identity.address(record['source']), target=identity.address(record['target']),
                  steps=record['steps'], notices=record['notices'], notes=record['notes'],
                  next='Read migration status before continuing; inspect unknown previous outcomes instead of repeating them.')
    return result


def diagnostics(rows):
    rows = list(rows)
    for filename in _json_files(DIRECTORY):
        transfer = paths.read_json(filename)
        if not transfer:
            continue
        for role in ('source', 'target'):
            saved = transfer[role]
            if not any(endpoint(row) == endpoint(saved) for row in rows):
                rows.append(dict(saved, state='unknown', registered=False))
    groups = {}
    for record in rows:
        native = record.get('native_conversation') or record['session_id']
        groups.setdefault((record['runtime'], native), []).append(record)

    def describe(record):
        transfer = retirement(record)
        owner = current_owner(record)
        current = _current(owner) if owner else None
        forwarding = None
        if transfer:
            if transfer['status'] != 'committed':
                forwarding = 'incomplete'
            else:
                try:
                    _check_lease(transfer, time.time())
                    forwarding = 'active'
                except MigrationError as exc:
                    forwarding = 'expired' if 'expired' in str(exc) else 'clock-unknown'
        return {'address': identity.address(record), 'home': record['home'], 'state': record.get('state'),
                'generation': generation(record), 'retired': transfer is not None,
                'migration': transfer['id'] if transfer else None, 'forwarding': forwarding,
                'forward_until': transfer.get('forward_until') if transfer else None,
                'current_owner': identity.address(owner) if owner else None,
                'owner_state': current.get('state', 'unknown') if current else 'unknown'}

    return [{'runtime': runtime, 'conversation': native, 'copies': [describe(r) for r in copies]}
            for (runtime, native), copies in groups.items() if len(copies) > 1 or any(retirement(r) for r in copies)]


def aliases():
    """Retired addresses survive pointer cleanup; no alias becomes a caller."""
    result = []
    for filename in _json_files(DIRECTORY):
        record = paths.read_json(filename)
        if record and (retirement(record['source']) or {}).get('id') == record['id']:
            result.append(dict(record['source'], registered=True, state='ended', retired=True))
    return result


def cli_inactive():
    """Cheap native-env fence; ordinary commands keep their existing lookup budget."""
    ids = [('claude', os.environ.get('CLAUDE_CODE_SESSION_ID'), registry.claude_home_here()),
           ('codex', os.environ.get('CODEX_THREAD_ID'), os.environ.get('CODEX_HOME') or os.path.expanduser('~/.codex'))]
    known = [(runtime, sid, home) for runtime, sid, home in ids if sid]
    if len(known) > 1:
        actor = registry.me()
        return active_error(actor) if actor else None
    if known:
        runtime, sid, home = known[0]
        actor = registry._read_pointer(runtime, sid, home)
        if actor:
            if retirement(actor):
                return active_error(actor)
            if has_generation_fences(actor):
                current = registry._caller_record(actor)
                return active_error(current) if current else 'active execution cannot be verified; use the native xsm MCP tools'
    return None
