"""Shared question/handshake orchestration; frontends provide wait and input pumps."""
from __future__ import annotations

from . import connect as connection, envelope, ledger, materials, probe, question_groups, questions, receive, resolve, send_service, teams
from .instructions import HANDSHAKE_TEXT


class QuestionError(ValueError):
    pass


def ask(me, arguments, *, call=None, material_source='inline', wait=0, pump=None,
        pump_factory=None, cancelled=None, poll=None):
    args = dict(arguments)
    wake = args.get('wake', 'auto')
    if wake not in ('auto', 'never'):
        raise QuestionError('unsupported wake mode; use auto or never')
    targets = args.get('targets')
    if targets is None and teams.is_address(args.get('target') or ''):
        targets, args['target'] = [args['target']], None
    if targets is not None:
        if (not isinstance(targets, list) or not all(isinstance(t, str) for t in targets)
                or args.get('target') or args.get('request_id') or args.get('attachments') or args.get('manifest_id')):
            raise QuestionError('targets is a list of recipients, used instead of target, request_id and attachments')
        result = question_groups.ask_many(me, targets, args.get('text') or '', wait=wait,
            priority=args.get('priority', 'next'), wake=wake, pump=pump, cancelled=cancelled, poll=poll)
        return {'result': result, 'grouped': True, 'wait_applies': True}
    if not args.get('target'):
        raise QuestionError('target (or targets) is required')
    request_id = args.get('request_id') or envelope.new_id()
    prepared = send_service.prepare_materials(me, args, args.get('text') or '', request_id,
                                             call=call, source=material_source)
    result = questions.ask(me, args['target'], prepared['body'], wait=wait, request_id=request_id,
        priority=args.get('priority', 'next'), wake=wake,
        pump=pump_factory(request_id) if pump_factory else pump, cancelled=cancelled,
        attachments=prepared['attachments'], file_packet=prepared['file_packet'], file_limits=prepared['file_limits'])
    if prepared['manifest_id']:
        result['materials'] = materials.public(prepared)
    return {'result': result, 'grouped': False, 'wait_applies': True}


def connect(me, arguments, *, call=None, wait=0, pump=None, pump_factory=None, cancelled=None):
    with probe.quick():
        found = resolve.resolve(arguments.get('target', ''), caller=me)
    if not found.ok:
        raise QuestionError(found.reason)
    request_id = arguments.get('request_id')
    if request_id and (not questions.expects_reply(me, found.record, request_id)
                       or questions.status(me, request_id).get('purpose') != 'handshake'):
        raise QuestionError('request ID does not belong to this selected handshake')
    result = connection.select(me, found.record, call=call)
    if result['status'] != 'permitted':
        return {'result': result, 'grouped': False, 'wait_applies': False}
    current_id = request_id or envelope.new_id()
    active_pump = pump_factory(current_id) if pump_factory else pump
    if request_id:
        receive.poll_replies(me, request_id)
        result = questions.wait_for(me, request_id, wait=wait, pump=active_pump, cancelled=cancelled)
    else:
        result = questions.ask(me, arguments.get('target', ''), HANDSHAKE_TEXT, wait=wait,
            request_id=current_id, purpose='handshake', priority=arguments.get('priority', 'next'),
            wake=arguments.get('wake', 'auto'), pump=active_pump, cancelled=cancelled)
    return {'result': result, 'grouped': False, 'wait_applies': True}


def status(me, request_id=None, *, wait=0, pump=None, pump_factory=None, cancelled=None, poll=None):
    if request_id is None:
        if wait:
            raise QuestionError('an id is required to wait; omit wait to list your requests')
        return {'result': {'status': 'requests', 'requests': questions.list_requests(me)},
                'grouped': False, 'wait_applies': False}
    if question_groups.is_group(request_id):
        result = question_groups.wait_for(me, request_id, wait=wait, pump=pump,
                                          cancelled=cancelled, poll=poll)
        return {'result': result, 'grouped': True, 'wait_applies': True}
    network_state = None
    if str(ledger.status(request_id).get('scope') or '').startswith('network:'):
        from . import network
        network_state = network.reconcile(request_id, caller=me)
    receive.poll_replies(me, request_id)
    result = questions.wait_for(me, request_id, wait=wait,
        pump=pump_factory(request_id) if pump_factory else pump, cancelled=cancelled)
    if network_state is not None:
        for key in ('network_status', 'network_delivery'):
            if key in network_state:
                result[key] = network_state[key]
    return {'result': result, 'grouped': False, 'wait_applies': True}
