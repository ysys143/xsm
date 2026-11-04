"""Worker coordination links and project requests collected by the parent session."""
from __future__ import annotations
import hashlib
import json
import os
from . import config, paths, registry


def key(record):
    return hashlib.sha256(json.dumps([record.get(k) for k in ('runtime', 'home', 'session_id')]).encode()).hexdigest()


def binding(child):
    if not child or not child.get('session_id'):
        return None
    value = paths.read_json(paths.path('worker-links', key(child) + '.json'), {}) or {}
    saved = value.get('child') or {}
    if saved.get('cwd') != child.get('cwd'):
        return None
    return value or None


def parent(child):
    if not child or not child.get('session_id'):
        return None
    value = binding(child)
    if value:
        saved = value['parent']
        current = registry.by_session(saved['runtime'], saved['session_id'])
        if current and all(current.get(k) == saved.get(k) for k in ('home', 'cwd')):
            return current
        return dict(saved, state='ended')
    old = paths.read_json(paths.path('worker-links', key(child) + '.json'), {}) or {}
    if old.get('parent'):
        return dict(old['parent'], state='needs-relink')
    from . import workers
    worker = workers.for_session(child.get('session_id'))
    if worker and worker.get('parent_ref'):
        return next((r for r in registry.records() if r.get('ref') == worker['parent_ref']),
                    {'ref': worker['parent_ref'], 'state': 'ended'})
    return None


def attach(owner, child, project):
    if not all(r.get(k) for r in (owner, child) for k in ('runtime','home','session_id','ref','cwd')):
        raise ValueError('a coordinator link requires registered sessions')
    if key(owner) == key(child):
        raise ValueError('a session cannot be its own worker')
    fields = ('runtime', 'home', 'session_id', 'ref', 'cwd', 'pid', 'lstart', 'name')
    value = {'parent': {k: owner.get(k) for k in fields}, 'child': {k: child.get(k) for k in fields},
             'project': project}
    paths.write_json(paths.path('worker-links', key(child) + '.json'), value)


def related(a, b):
    for child, owner in ((a, b), (b, a)):
        value = binding(child)
        if value and key(value['parent']) == key(owner):
            return 'worker:' + owner.get('ref', '')
    return None


def request_join(child, owner, project, leaving=False):
    ident = hashlib.sha256(json.dumps([key(child), key(owner), project, child.get('cwd'), leaving]).encode()).hexdigest()[:24]
    filename = paths.path('worker-project-requests', ident + '.json')
    value = paths.read_json(filename, {}) or {'id': ident, 'project': project, 'worker': child['ref'], 'parent': owner['ref']}
    if owner.get('state') in ('ended', 'stale', 'needs-relink'):
        return 'Worker project request %s is waiting: parent [%s] is unavailable. No worker-local question was opened.' % (ident, owner['ref'])
    if value.pop('resolved', False):
        value['attempt'] = value.get('attempt', 0) + 1
        value['notified'] = False
    if not value.get('notified'):
        from . import send
        text = ('Worker [%s] needs project %s. Collect this request in your session: '
                'call xsm_join with project=%s, workers=["ref:%s"] and leave=%s. Ask your user here if needed; '
                'do not send the user to the worker terminal. Request %s.' %
                (child['ref'], project, project, child['ref'], str(leaving).lower(), ident))
        result = send.send('ref:' + owner['ref'], text, sender=child, kind='task', wait=0,
                           msg_id='worker-project-' + ident + '-' + str(value.get('attempt', 0)))
        value['notified'] = result.status in ('delivered', 'sent-unconfirmed', 'stored', 'pending')
        paths.write_json(filename, value)
    return 'Waiting for parent [%s] to handle project %s (request %s). No worker-local question was opened.' % (owner['ref'], project, ident)


def peer_directive(me, text):
    """Recognize a known coordinator's terminal-injected instruction header."""
    if not me or not isinstance(text, str):
        return False
    owner = parent(me)
    name = (owner or {}).get('name')
    return bool(name and any(text.lstrip().startswith('[' + name + suffix) for suffix in (' 지시]', ' 요청]', ' instruction]')))


def select_worker(target):
    """Orca launch handles resolve only to a registered native session, not a title."""
    from . import resolve
    if target.startswith('term_'):
        found = [r for r in registry.records() if r.get('framework_terminal') == target and r.get('state') == 'live']
        if len(found) != 1:
            raise ValueError('worker terminal is not registered yet or is ambiguous; retry from the coordinator without restarting the worker')
        return found[0]
    selected = resolve.resolve(target)
    if not selected.ok or selected.record.get('remote'):
        raise ValueError(selected.reason if not selected.ok else 'select a local worker')
    if selected.record.get('state') in ('ended', 'stale') or selected.record.get('ended_at'):
        raise ValueError('selected worker is no longer running; select an active registered worker')
    return selected.record


def resolve_requests(child, owner, project, leaving=False):
    """Close a delivered parent request when its requested membership takes effect."""
    ident = hashlib.sha256(json.dumps([key(child), key(owner), project, child.get('cwd'), leaving]).encode()).hexdigest()[:24]
    filename = paths.path('worker-project-requests', ident + '.json')
    value = paths.read_json(filename, {}) or {}
    if value:
        value['resolved'] = True
        paths.write_json(filename, value)
