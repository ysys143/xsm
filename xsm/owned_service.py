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
