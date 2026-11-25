"""Shared handover selection/mutation; trusted frontends collect the user's verdict."""
from __future__ import annotations

import inspect

from . import handover, identity, probe, resolve


class DecisionRefused(handover.HandoverError):
    pass


def _takes_plan(authorize) -> bool:
    """Whether the approval callback takes the plan (a callback that takes only the target works as before)."""
    try:
        params = inspect.signature(authorize).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(p.name == 'plan' or p.kind is p.VAR_KEYWORD for p in params)


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
    # A successor that handed over itself is followed first, so the person approves the session
    # that will really take the place, and sees what is copied to it (plan -> apply).
    resolved_target, via = handover._check(me, resolved_target, resume=True)
    plan = handover.plan_links(me, resolved_target)
    if via:
        plan["redirected_from"] = via
    source = (authorize(resolved_target, plan=plan) if _takes_plan(authorize) else authorize(resolved_target)) \
        if authorize else None
    if not isinstance(source, str) or not source.strip():
        raise DecisionRefused('handover requires the actual user approval source; nothing moved')
    # Revalidate the selected conversation after UI work, never the old alias.
    with probe.quick():
        current = resolve.resolve(identity.address(resolved_target), caller=me)
    if not current.ok:
        raise handover.HandoverError(current.reason)
    current_record, _via = handover._check(me, current.record, resume=True)
    record = handover.hand_over(me, current_record, summary, source, plan)
    return {'action': 'hand_over', 'record': record}
