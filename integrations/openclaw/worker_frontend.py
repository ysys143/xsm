"""Native owned-turn ordering; transport and ownership policy remain external.

The RPC callable must be an authenticated native backend connection. No model
turn is submitted until the inherited private control channel accepts the actual
host session ID. RPC failure is uncertain execution, never permission to replay.
"""
from __future__ import annotations

import time

from . import worker_session as session


def run_turn(rpc, control, *, agent_id, cwd, message, request_id,
             native_session_id=None, wait_timeout_ms=20000):
    if type(wait_timeout_ms) is not int or not 1 <= wait_timeout_ms <= 30000:
        raise session.NativeSessionError('invalid native observation timeout')
    # Validate task fields before any mutation or native context allocation.
    session._text(request_id, 'request ID')
    if not isinstance(message, str) or not message.strip():
        raise session.NativeSessionError('native task body required')
    if native_session_id is None:
        created = rpc('sessions.create', session.creation_params(agent_id, cwd))
        locator = session.created_locator(created, agent_id, cwd)
    else:
        resolved = rpc('sessions.resolve', session.resolution_params(native_session_id, agent_id))
        listing = rpc('sessions.list', {})
        locator = session.resolved_locator(resolved, listing, native_session_id, agent_id, cwd)
    params = session.agent_params(locator, message, request_id)
    control.bind(locator['native_session_id'])
    admission = rpc('agent', params)
    run_id = session.accepted_run(admission, locator, request_id)
    while True:
        terminal = rpc('agent.wait', {'runId': run_id, 'timeoutMs': wait_timeout_ms})
        if terminal.get('runId') != run_id:
            raise session.NativeSessionError('native observation changed run identity')
        if terminal.get('status') not in ('timeout', 'pending'):
            break
        # An observation timeout is not a terminal run or a reason to resubmit.
        # Pending approval may return immediately; bound the observation rate.
        if terminal['status'] == 'pending':
            time.sleep(.2)
    reply = session.completed_run(terminal, locator, run_id)
    return {'locator': locator, 'admission': admission, 'terminal': terminal, 'reply': reply}
