"""Owned native entrypoint and retained output framing; no ownership policy."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import stat

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from integrations.openclaw import worker_session as session
    from integrations.openclaw.worker_frontend import run_turn
    from integrations.openclaw.worker_transport import NativeRpc
else:
    from . import worker_session as session
    from .worker_frontend import run_turn
    from .worker_transport import NativeRpc
from xsm.native_worker_control import WorkerControlClient


def output_records(output):
    """Read legacy final JSON or a bound record followed by one final record."""
    if not isinstance(output,str):
        raise session.NativeSessionError('native output must be text')
    try:
        value = session.decode_reply(output)
        values = [value]
    except session.NativeSessionError:
        values = [session.decode_reply(line) for line in output.splitlines() if line.strip()]
    if not values or len(values) > 2:
        raise session.NativeSessionError('native output framing is ambiguous')
    bound = values[0] if values[0].get('type') == 'xsm_openclaw_bound' else None
    if bound is None:
        if len(values) != 1:
            raise session.NativeSessionError('native output lacks its bound header')
        return None, values[0]
    if set(bound) != {'type','context_id','context_epoch','run_id','locator'}:
        raise session.NativeSessionError('invalid native bound header')
    final = values[1] if len(values) == 2 else None
    if final is not None:
        if (final.get('type') not in ('xsm_openclaw_result','xsm_openclaw_cancelled')
                or any(final.get(key) != bound.get(key) for key in ('context_id','context_epoch','run_id','locator'))):
            raise session.NativeSessionError('native final output changed its bound execution')
    return bound, final


def final_frame(output):
    _bound, value = output_records(output)
    if value is None:
        raise session.NativeSessionError('native output has no final observation')
    return value


def parse_result(output, context, *, agent_id=None, cwd=None):
    value = final_frame(output)
    if (value.get('type') != 'xsm_openclaw_result'
            or value.get('context_id') != context.get('id')
            or value.get('context_epoch') != context.get('epoch')):
        raise session.NativeSessionError('native output belongs to another owned context generation')
    locator = value.get('locator')
    if not isinstance(locator, dict):
        raise session.NativeSessionError('native result lacks its bound locator')
    native_id = session._text(locator.get('native_session_id'), 'session ID')
    native_agent = session._text(locator.get('agent_id'), 'agent ID')
    session._text(locator.get('native_session_key'), 'session key')
    session._text(locator.get('native_lifecycle_revision'), 'lifecycle revision')
    if agent_id is not None and native_agent != agent_id:
        raise session.NativeSessionError('native result changed admitted agent')
    if cwd is not None and session._workspace(locator.get('cwd')) != session._workspace(cwd):
        raise session.NativeSessionError('native result changed admitted workspace')
    if context.get('native_session_id') != native_id:
        raise session.NativeSessionError('native result changed bound conversation')
    run_id = session.accepted_run(value.get('admission') or {}, locator, value.get('run_id'))
    reply = session.completed_run(value.get('terminal') or {}, locator, run_id)
    if reply['disposition'] != 'visible' or not reply['text'].strip():
        raise session.NativeSessionError('native result has no actual reply text')
    return {'native_session_id': native_id, 'body': reply['text'],
            'native_evidence': {'run_id': run_id, 'terminal_receipt': value['terminal']['terminalReceipt']}}


def parse_cancellation(output, context, *, agent_id=None, cwd=None):
    value = final_frame(output)
    locator = value.get('locator')
    if (value.get('type') != 'xsm_openclaw_cancelled' or value.get('cancelled') is not True
            or value.get('context_id') != context.get('id') or value.get('context_epoch') != context.get('epoch')
            or not isinstance(locator, dict) or locator.get('native_session_id') != context.get('native_session_id')):
        raise session.NativeSessionError('native stop observation changed owned generation')
    native_id = session._text(locator.get('native_session_id'), 'session ID')
    native_agent = session._text(locator.get('agent_id'), 'agent ID')
    session._text(locator.get('native_session_key'), 'session key')
    session._text(locator.get('native_lifecycle_revision'), 'lifecycle revision')
    if agent_id is not None and native_agent != agent_id:
        raise session.NativeSessionError('native stop changed admitted agent')
    if cwd is not None and session._workspace(locator.get('cwd')) != session._workspace(cwd):
        raise session.NativeSessionError('native stop changed admitted workspace')
    if value.get('native_not_started') is True:
        if any(value.get(key) is not None for key in ('admission', 'terminal', 'abort', 'stop_observation')):
            raise session.NativeSessionError('unstarted native stop contains an execution')
        proof = {'native_not_started': True}
    elif value.get('native_not_started') is False:
        run_id = session.accepted_run(value.get('admission') or {}, locator, value.get('run_id'))
        proof = session.stopped_run(value.get('terminal') or {}, {'sessions': [value.get('stop_observation')]},
                                    locator, run_id, value.get('abort'))
    else:
        raise session.NativeSessionError('native stop phase is unavailable')
    return {'native_session_id': native_id, 'native_evidence': {'native_state': 'stopped', **proof}}


def main():
    parser = argparse.ArgumentParser(description='Private owned OpenClaw native frontend')
    for flag in ('node', 'native-cli', 'agent-id', 'cwd', 'context-id', 'context-epoch', 'run-id'):
        parser.add_argument('--' + flag, required=True)
    for flag in ('native-session-id', 'model', 'thinking'):
        parser.add_argument('--' + flag)
    args = parser.parse_args()
    control = WorkerControlClient.from_environment()
    try:
        rpc = NativeRpc(args.node, args.native_cli, cwd=args.cwd, env=os.environ)
        def bound_record(locator):
            print(json.dumps(dict(type='xsm_openclaw_bound',context_id=args.context_id,
                                  context_epoch=args.context_epoch,run_id=args.run_id,locator=locator),
                             ensure_ascii=False,allow_nan=False),flush=True)
            if stat.S_ISREG(os.fstat(sys.stdout.fileno()).st_mode):
                os.fsync(sys.stdout.fileno())
        result = run_turn(rpc, control, agent_id=args.agent_id, cwd=args.cwd, message=sys.stdin.read(),
                          request_id=args.run_id, native_session_id=args.native_session_id,
                          model=args.model, thinking=args.thinking,on_bound=bound_record)
        result.update(type='xsm_openclaw_cancelled' if result.get('cancelled') else 'xsm_openclaw_result', context_id=args.context_id,
                      context_epoch=args.context_epoch, run_id=args.run_id)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)
        if result.get('cancelled'):
            control.report_stopped()
            return 130
    except Exception:
        # Preserve native state for journal recovery; never resubmit on failure.
        print('OpenClaw owned native execution unconfirmed; inspect retained native state.', file=sys.stderr)
        return 1
    finally:
        control.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
