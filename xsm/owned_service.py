"""Shared owned-action validation and dispatch; transports own wait/cancel pumps."""
from __future__ import annotations

from . import envelope, handoff, workers


class ActionError(ValueError):
    pass


def execute(me, arguments, *, run=None):
    args = dict(arguments)
    action, name = args.get('action'), args.get('name')
    if not isinstance(name, str) or not name:
        raise ActionError('owned worker name required')
    if action == 'create':
        return workers.create_owned(args.get('runtime'), caller=me, name=name, cwd=args.get('dir'),
            home=args.get('home'), model=args.get('model'), effort=args.get('effort'), grant=args.get('grant'))
    if action == 'status':
        return (workers.owned_status(name, me, args['request_id']) if args.get('request_id') else
                {'status': 'requests', 'requests': workers.owned_history(name, me)})
    if action == 'cancel':
        if not args.get('request_id'):
            raise ActionError('request_id required for cancellation')
        return workers.cancel_owned(name, me, args['request_id'])
    if action in ('retry', 'reconcile'):
        if not args.get('request_id'):
            raise ActionError('request_id required for reply recovery')
        function = workers.resend_owned if action == 'retry' else workers.reconcile_owned
        return function(name, me, args['request_id'])
    if action != 'run':
        raise ActionError('unknown owned action')
    request_id = args.get('request_id') or envelope.new_id()
    handoff._id(request_id)
    execute_run = run or workers.run_owned
    return execute_run(name, me, args.get('text') or '', work_context=args.get('work_context'),
                       request_id=request_id, independent=args.get('independent', False))


def public_result(value):
    """Model-facing projection; journals, leases and native process data stay private.

    The CLI/backend retain their diagnostic journal view. Model frontends share
    this projection before serialization rather than teaching each host to scrub.
    """
    import copy
    def fields(item, keys):
        return {key: copy.deepcopy(item[key]) for key in keys if key in item}
    def worker(item):
        return fields(item, ('id','name','mode','owned','runtime','cwd','model','effort',
            'created','depth','max_depth','parent_ref','session_id'))
    if value.get('mode') == 'owned' and 'status' not in value:
        return worker(value)
    out = fields(value, ('id','status','created_at','updated_at','work_context','context_id',
        'context_epoch','digest','body','reply_id','persisted','accepted','side_effects_exactly_once',
        'slot_occupied','execution_state','worker_record_present','admission','reason','waiter_cancelled'))
    if 'requests' in value:
        out['requests'] = [fields(row, ('id','status','created_at','work_context','reply_id',
            'worker_record_present','worker','context_id','digest','preview')) for row in value['requests']]
    if isinstance(value.get('worker'), dict): out['worker'] = worker(value['worker'])
    if isinstance(value.get('context'), dict):
        out['context'] = fields(value['context'], ('id','epoch','worker_id','work_context',
            'independent','native_session_id','retired','unknown_request','created_at'))
    for key, keys in (
        ('result', ('body','outcome','native_session_id')),
        ('send_evidence', ('id','status','reason','runtime_reached')),
        ('cancellation', ('requested_at','status','native_state','native_supported','observed_at')),
        ('capacity', ('limit','busy','available'))):
        if key in value:
            out[key] = fields(value[key], keys) if isinstance(value[key], dict) else None
    if isinstance(value.get('recover_at'), dict):
        recovery = value['recover_at']
        out['recover_at'] = {'tool': recovery['tool'],
            'arguments': fields(recovery['arguments'], ('action','name','request_id'))}
    return out
