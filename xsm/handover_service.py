"""Shared handover selection/mutation; trusted frontends collect the user's verdict."""
from __future__ import annotations

from . import handover, identity, probe, resolve


class DecisionRefused(handover.HandoverError):
    pass


def execute(me, arguments, *, resolved_target=None, authorize=None):
    if arguments.get('action') == 'show':
        return {'action': 'show', 'received': handover.received(me)}
    word, summary = arguments.get('target'), arguments.get('summary')
    if not isinstance(word, str) or not word.strip() or not isinstance(summary, str) or not summary.strip():
        raise handover.HandoverError('target and a nonempty context summary are required')
    if resolved_target is None:
        with probe.quick():
            found = resolve.resolve(word, caller=me)
        if not found.ok:
            raise handover.HandoverError(found.reason)
        resolved_target = found.record
    handover._check(me, resolved_target)
    source = authorize(resolved_target) if authorize else None
    if not isinstance(source, str) or not source.strip():
        raise DecisionRefused('handover requires the actual user approval source; nothing moved')
    # Revalidate the selected conversation after UI work, never the old alias.
    with probe.quick():
        current = resolve.resolve(identity.address(resolved_target), caller=me)
    if not current.ok:
        raise handover.HandoverError(current.reason)
    handover._check(me, current.record)
    record = handover.hand_over(me, current.record, summary, source)
    return {'action': 'hand_over', 'record': record}
