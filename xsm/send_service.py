"""Shared send orchestration; frontends own input bytes, identity proof and rendering."""
from __future__ import annotations

from . import envelope, materials, multisend, send, teams


class SendError(ValueError):
    """A request combination that cannot be sent."""


def prepare_materials(caller, arguments, body, request_id, *, call=None, source='inline'):
    return materials.prepare(caller, arguments.get('target') or '', body, request_id,
        arguments.get('attachments'), source=source, manifest_id=arguments.get('manifest_id'),
        previous=arguments.get('previous_manifest'), fallback=arguments.get('attachment_fallback'), call=call)


def execute(arguments, *, caller=None, call=None, material_source='inline', default_wait=15,
            group_retry=False):
    request = dict(arguments)
    kind = request.get('kind') or 'note'
    if request.get('outcome') and kind != 'reply':
        raise SendError('outcome belongs only to a reply that closes a task')
    wake = request.get('wake', 'auto')
    if wake not in ('auto', 'never'):
        raise SendError('unsupported wake mode; use auto or never')
    wait = request.get('wait', default_wait)
    wait = float(default_wait if wait is None else wait)
    if group_retry:
        result = multisend.resend_group(request['resend'], sender=caller, call=call, wait=wait)
        return {'result': result, 'materials': None, 'grouped': True}
    targets = request.get('targets')
    if targets is None and teams.is_address(request.get('target') or ''):
        targets = [request['target']]
        request['target'] = None
    if targets is not None:
        if (not isinstance(targets, list) or not all(isinstance(t, str) for t in targets)
                or request.get('target') or request.get('held') or request.get('resend')
                or request.get('attachments') or request.get('manifest_id')):
            raise SendError('targets is a list of recipients, used instead of target, held, resend and attachments')
        result = multisend.send_many(targets, request.get('text') or '', sender=caller, call=call,
            kind=kind, reply_to=request.get('reply_to'), priority=request.get('priority') or 'next',
            wait=wait, outcome=request.get('outcome') if kind == 'reply' else None, wake=wake != 'never')
        return {'result': result, 'materials': None, 'grouped': True}
    if request.get('held') and (request.get('attachments') or request.get('manifest_id')):
        raise SendError('held sends reuse their stored material; do not supply new attachments')
    request_id = request.get('resend') or request.get('request_id') or envelope.new_id()
    prepared = prepare_materials(caller, request, request.get('text') or '', request_id,
        call=call, source=material_source)
    has_materials = bool(prepared['manifest_id'])
    result = send.send(request.get('target') or '', prepared['body'], sender=caller, call=call,
        kind=kind, reply_to=request.get('reply_to'), priority=request.get('priority') or 'next', wait=wait,
        outcome=request.get('outcome') if kind == 'reply' else None,
        msg_id=request_id if request.get('resend') or request.get('request_id') or has_materials else None,
        resend=bool(request.get('resend')), held=request.get('held') or None, wake=wake != 'never',
        attachments=prepared['attachments'] if has_materials or material_source == 'inline' else None,
        file_packet=prepared['file_packet'], file_limits=prepared['file_limits'])
    return {'result': result, 'materials': prepared if has_materials else None, 'grouped': False}
