"""Actual stdio server with failure-only process/decision observations on stderr.

Observers return the original answers unchanged; no alternate admission policy.
"""
import json
from pathlib import Path
import runpy
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from xsm import context, decisions, identity
from xsm.operations import OperationService
from xsm.protocol import Connection, ProtocolError

starts, states = {}, {}
simulate = sys.argv[1:] == ['--simulate-start-drift']
simulate_clock = sys.argv[1:] == ['--simulate-clock-rollback']
if sys.argv[1:] and not (simulate or simulate_clock):
    raise SystemExit('unknown observation fixture argument')
drift_pid = None
original_start = identity.lstart
original_state = identity.state_reason
original_current = OperationService._decision_current
original_response = Connection.decision_response
original_clock = time.time


def observed_start(pid):
    value = original_start(pid)
    if simulate and pid == drift_pid and value:
        value += ' [deliberate diagnostic simulation]'
    starts[pid] = value
    return value


def observed_state(record):
    value = original_state(record)
    states[(record.get('runtime'), record.get('session_id'))] = {
        'state': value[0], 'reason': value[1], 'pid': record.get('pid'),
        'savedStart': record.get('lstart'), 'observedStart': starts.get(record.get('pid')),
        'generation': context.of_record(record).generation, 'cwd': record.get('cwd')}
    return value


def observed_current(self, decision):
    global drift_pid
    drift_pid = decision['me'].get('pid') if simulate and decision['scope'].get('tool') == 'xsm_join' else None
    try:
        value = original_current(self, decision)
    finally:
        drift_pid = None
    if not value:
        me = decision['me']
        observation = dict(states.get((me.get('runtime'), me.get('session_id')), {}))
        observation['cwdSame'] = observation.pop('cwd', None) == me.get('cwd')
        record = decisions.read(decision['key'])
        observation.update(event='decision-current-refused', expectedGeneration=decision['generation'],
            simulatedStartDrift=simulate,
            decisionState=record.get('status'), created=record.get('created_at'),
            expires=record.get('expires_at'), now=time.time(),
            kernelStart=identity.process_start(observation['pid']) if observation.get('pid') else None)
        print(json.dumps(observation), file=sys.stderr, flush=True)
    return value


def observed_response(self, token, host, params):
    item = next(((key, item) for key, item in self.ui_requests.items()
                 if item['event']['questionId'] == params.get('questionId')), None)
    snapshot = decisions.read(item[0]) if item else {}
    clocks = []
    def observed_clock():
        value = original_clock()
        frame = sys._getframe(1)
        module = frame.f_globals.get('__name__')
        if simulate_clock and module == 'xsm.protocol' and snapshot:
            value = snapshot['created_at'] - 1
        if module in ('xsm.protocol', 'xsm.decisions'):
            clocks.append(dict(module=module, line=frame.f_lineno, value=value))
        return value
    try:
        time.time = observed_clock
        return original_response(self, token, host, params)
    except ProtocolError as error:
        observation = dict(event='decision-response-refused', code=error.code,
            message=error.message, decisionState=snapshot.get('status'),
            created=snapshot.get('created_at'), expires=snapshot.get('expires_at'),
            clocks=clocks, simulatedClockRollback=simulate_clock)
        print(json.dumps(observation), file=sys.stderr, flush=True)
        raise
    finally:
        time.time = original_clock


identity.lstart = observed_start
identity.state_reason = observed_state
OperationService._decision_current = observed_current
Connection.decision_response = observed_response
sys.argv = [str(ROOT / 'xsm'), 'protocol', 'serve', '--stdio']
runpy.run_module('xsm', run_name='__main__')
