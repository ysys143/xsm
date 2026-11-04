"""Sender-owned failed delivery evidence, never an authenticated incoming task."""
import time

from . import handoff, paths

DIRECTORY = 'delivery-attempts'


def current_epoch(actor):
    from . import migration, registry
    current = registry._read_pointer(actor['runtime'], actor['session_id'], actor['home'])
    return current.get('profile_epoch', 0) if current and migration.generation(current) == migration.generation(actor) else actor.get('profile_epoch', 0)


def public(value):
    from . import identity
    result = {k: v for k, v in value.items() if k not in ('sender', 'target')}
    result['sender'] = identity.address(value['sender'])
    result['target'] = identity.address(value['target']) if value.get('target') and value['target'].get('home') else None
    return result


def record(sender, spec, body, result, *, target=None, kind='note', reply_to=None, outcome=None):
    if not isinstance(body, str):
        return
    try:
        owner = handoff._identity(sender)
    except ValueError:
        return
    ident = handoff._id(result.msg_id)
    filename = paths.path(DIRECTORY, ident + '.json')
    previous = paths.read_json(filename)
    if previous and any(previous.get(k) != v for k, v in (
            ('sender', owner), ('body', body), ('target_spec', spec), ('kind', kind),
            ('reply_to', reply_to), ('outcome', outcome))):
        from . import envelope
        ident = envelope.new_id()
        filename = paths.path(DIRECTORY, ident + '.json')
        previous = None  # Keep the conflicting original; a rejected retry is separate evidence.
    value = {'id': ident, 'sender': owner, 'target_spec': spec, 'body': body, 'kind': kind,
             'sender_epoch': current_epoch(sender), 'target_epoch': current_epoch(target) if target and target.get('home') else None,
             'reply_to': reply_to, 'outcome': outcome, 'status': result.status, 'reason': result.reason,
             'at': previous['at'] if previous else time.time()}
    try:
        value['target'] = handoff._identity(target) if target else None
    except ValueError:
        value['target'] = None
    paths.write_json(filename, value)


def all_records():
    import glob
    return [value for filename in sorted(glob.glob(paths.path(DIRECTORY, '*.json')))
            if isinstance(value := paths.read_json(filename), dict)]


def outgoing(actor, *, epoch=None):
    owner = handoff._identity(actor)
    epoch = current_epoch(actor) if epoch is None else epoch
    return [public(value) for value in all_records() if value['sender'] == owner and value.get('sender_epoch', 0) == epoch]


def get_owned(actor, ident):
    handoff._id(ident)
    value = paths.read_json(paths.path(DIRECTORY, ident + '.json'))
    return value if value and value['sender'] == handoff._identity(actor) else None


def incoming(actor, *, epoch=None):
    """Unknown short refs disclose only metadata; full bodies stay with the sender."""
    owner = handoff._identity(actor)
    epoch = current_epoch(actor) if epoch is None else epoch
    refs = {'ref:' + actor['ref']} if actor.get('ref') else set()
    from . import identity
    refs.add(identity.address(actor))
    result = []
    for value in all_records():
        known = value.get('target') == owner and value.get('target_epoch', 0) == epoch
        if not known and (value.get('target') is not None or value['target_spec'] not in refs):
            continue
        projected = {k: value[k] for k in ('id', 'target_spec', 'status', 'reason', 'at')}
        projected.update(sender=identity.address(value['sender']) if value['sender'].get('home') else value['sender'],
                         target_verified=known, body_at_sender=True)
        if known:
            projected['body'] = value['body']
        result.append(projected)
    return result
