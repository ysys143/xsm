"""V3 contract participant; v2 transport source is retained unchanged."""
import argparse
import concurrent.futures
import json
import math
import os
import queue
import subprocess
import tempfile
import threading
from pathlib import Path

def server_command(executable):
    """Operator configuration only; never derived from a protocol frame."""
    path = Path(executable)
    if not path.is_absolute():
        raise ValueError('server executable must be an absolute operator-selected path')
    return [str(path), 'protocol', 'serve', '--stdio']


def reject_constant(value):
    raise ValueError('non-JSON numeric constant: ' + value)


def finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('number exceeds finite native representation')
    return number


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate JSON object key: ' + key)
        value[key] = item
    return value


def decode_json(text):
    return json.loads(text, parse_constant=reject_constant, parse_float=finite_float,
                      object_pairs_hook=unique_object)


def decode_frame(wire):
    # Explicit decoding prevents json.loads(bytes) from auto-detecting UTF-16/32.
    return decode_json(wire.decode('utf-8', errors='strict'))

class RpcError(Exception):
    def __init__(self, error):
        self.error = error
        super().__init__(str(error))

class Peer:
    def __init__(self, command, cwd=None, env=None, observations=None):
        if len(command) != 4 or list(command[1:]) != ['protocol', 'serve', '--stdio']:
            raise ValueError('expected operator-selected executable and fixed protocol argv')
        command = server_command(command[0])
        self.temp = tempfile.TemporaryDirectory(prefix='independent-participant-') if cwd is None else None
        self.cwd = str(Path(cwd or self.temp.name).resolve())
        supplied = env or os.environ
        clean = {k: supplied[k] for k in ('PATH', 'LANG', 'TMPDIR') if k in supplied}
        clean.update(HOME=self.cwd, XSM_HOME=self.cwd + '/state')
        self.observations = observations
        self.trace = []
        self.notifications = queue.Queue()
        self.pending = {}
        self.lock = threading.RLock()
        self.terminal_failure = None
        self.closed = False
        self.serial = 0
        self.errors = tempfile.TemporaryFile()
        try:
            self.process = subprocess.Popen(command, cwd=self.cwd, env=clean, stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE, stderr=self.errors)
        except BaseException:
            self.errors.close()
            if self.temp:
                self.temp.cleanup()
            raise
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _fail(self, error):
        with self.lock:
            if self.terminal_failure is None:
                self.terminal_failure = error
            failure = self.terminal_failure
            pending, self.pending = self.pending, {}
        for future, _ in pending.values():
            if not future.done():
                future.set_exception(failure)
        self.notifications.put(failure)

    def _read(self):
        try:
            while True:
                line = self.process.stdout.readline(4 * 1048576 + 1)
                if not line:
                    raise EOFError('server stdout closed')
                if not line.endswith(b'\n') or len(line) > 4 * 1048576:
                    raise ValueError('invalid output frame')
                frame = decode_frame(line)
                if not isinstance(frame, dict) or frame.get('jsonrpc') != '2.0':
                    raise ValueError('invalid JSON-RPC envelope')
                if 'id' not in frame:
                    if not isinstance(frame.get('method'), str) or not isinstance(frame.get('params'), dict):
                        raise ValueError('invalid notification')
                    self.trace.append({'direction': 'receive', 'frame': frame})
                    if self.observations is not None:
                        self.observations.append({'frame': frame})
                    self.notifications.put(frame)
                    continue
                if type(frame['id']) is not int or ('result' in frame) == ('error' in frame):
                    raise ValueError('invalid response envelope')
                if 'error' in frame and (not isinstance(frame['error'], dict) or
                    type(frame['error'].get('code')) is not int or not isinstance(frame['error'].get('message'), str)):
                    raise ValueError('invalid error envelope')
                with self.lock:
                    future, method = self.pending.pop(frame['id'])
                self.trace.append({'direction': 'receive', 'method': method, 'frame': frame})
                if self.observations is not None:
                    self.observations.append({'method': method, 'frame': frame})
                if not future.done():
                    future.set_result(frame)
        except BaseException as error:
            self._fail(error)

    def submit(self, method, params=None):
        with self.lock:
            if self.terminal_failure is not None:
                raise self.terminal_failure
            if self.closed or self.process.poll() is not None:
                failure = EOFError('server exited or participant closed')
                self._fail(failure)
                raise failure
            self.serial += 1
            future = concurrent.futures.Future()
            frame = dict(jsonrpc='2.0', id=self.serial, method=method, params=params or {})
            wire = (json.dumps(frame, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
            if len(wire.decode()) - 1 > 1048576:
                raise ValueError('input frame exceeds contract limit')
            self.pending[self.serial] = (future, method)
            self.trace.append({'direction': 'send', 'frame': frame})
            try:
                self.process.stdin.write(wire)
                self.process.stdin.flush()
            except BaseException as error:
                self._fail(error)
                raise
            return future

    def call(self, method, params=None, error=None):
        frame = self.submit(method, params).result(timeout=5)
        if error is not None:
            if frame.get('error', {}).get('code') != error:
                raise AssertionError(frame)
            return frame['error']
        if 'error' in frame:
            raise RpcError(frame['error'])
        return frame['result']

    def initialize(self):
        result = self.call('initialize', {'protocolVersion': '1'})
        lease = result.get('limits', {}).get('claimLeaseSeconds')
        try:
            valid = type(lease) in (int, float) and math.isfinite(lease) and lease > 0
        except OverflowError:
            valid = False
        if result.get('protocolVersion') != '1' or not valid:
            raise ValueError('invalid negotiated version or claim lease')
        return result

    def open(self, conversation, capabilities=None):
        return self.call('session.open', dict(runtime='independent', profile='fixture',
            conversation=conversation, cwd=self.cwd, capabilities=capabilities or ['messaging', 'inbox']))

    def operation(self, session, name, **arguments):
        return self.call('operation.call', dict(session=session['session'], operation=name, arguments=arguments))

    def notification(self, timeout=5):
        item = self.notifications.get(timeout=timeout)
        if isinstance(item, BaseException):
            raise item
        return item

    def inbox(self, session, schema, **arguments):
        packet = self.operation(session, 'xsm_inbox', **arguments)
        validate_inbox(packet, schema)
        return packet

    def fixture_response(self, event, action, source_id, answer=None):
        """Synthetic fixture callback; does not represent a human or apply effects."""
        p = event['params']
        return self.call('decision.response', dict(session=p['session'], questionId=p['questionId'],
            challenge=p['challenge'], displayed=p['question'], action=action,
            answer=answer, source_id=source_id))

    def fixture_answer(self, event, answer, source_id):
        """Synthetic display/callback fixture only; never human approval evidence."""
        p = event['params']
        displayed = p['question']
        return self.call('decision.response', dict(session=p['session'], questionId=p['questionId'],
            challenge=p['challenge'], displayed=displayed, action='accept', answer=answer, source_id=source_id))

    def abandon(self, event):
        p = event['params']
        return self.call('decision.abandon', {k: p[k] for k in ('session', 'questionId', 'challenge')})

    def close(self):
        with self.lock:
            if self.closed:
                return ''
            self.closed = True
        self._fail(EOFError('participant closed'))
        cleanup_errors = []
        diagnostics = ''

        def attempt(label, action):
            try:
                return action()
            except Exception as error:
                cleanup_errors.append(label + ': ' + repr(error))

        # A broken/failed stdin close must not skip reaping or any later cleanup.
        try:
            attempt('stdin.close', self.process.stdin.close)
            if not self.process.stdin.closed:
                raw = getattr(self.process.stdin, 'raw', None)
                if raw is not None:
                    attempt('stdin.raw.close', raw.close)
                else:
                    attempt('stdin descriptor close', lambda: os.close(self.process.stdin.fileno()))
            try:
                self.process.wait(timeout=3)
            except Exception as error:
                if not isinstance(error, subprocess.TimeoutExpired):
                    cleanup_errors.append('wait: ' + repr(error))
                attempt('kill', self.process.kill)
                attempt('wait after kill', lambda: self.process.wait(timeout=3))
            attempt('reader.join', lambda: self.reader.join(timeout=2))
            attempt('stdout.close', self.process.stdout.close)
            if self.reader.is_alive():
                attempt('reader.join after stdout.close', lambda: self.reader.join(timeout=2))
            attempt('stderr.seek', lambda: self.errors.seek(0))
            data = attempt('stderr.read', self.errors.read)
            if data is not None:
                diagnostics = data.decode('utf-8', errors='replace')
        finally:
            try:
                attempt('stderr.close', self.errors.close)
            finally:
                if self.temp:
                    attempt('temporary directory cleanup', self.temp.cleanup)
        if cleanup_errors:
            diagnostics += '\nCleanup failures: ' + '; '.join(cleanup_errors)
        return diagnostics

def validate_inbox(packet, schema):
    """Validate the supplied inbox schema subset and documented ID correlation.

    This is not a general Draft 2020-12 implementation. Unknown validation
    keywords fail closed rather than being silently treated as checked.
    """
    import re
    annotations = {'$schema', '$id', '$defs', '$comment', 'title', 'description'}
    supported = annotations | {'$ref', 'type', 'required', 'additionalProperties',
        'properties', 'items', 'minLength', 'minItems', 'maxItems', 'minimum', 'pattern'}

    def validate(value, rule, path):
        if set(rule) - supported:
            raise ValueError('unsupported schema keywords at ' + path)
        if '$ref' in rule:
            target = schema
            ref = rule['$ref']
            if not ref.startswith('#/'):
                raise ValueError('external schema refs are not supported')
            for key in ref[2:].split('/'):
                target = target[key.replace('~1', '/').replace('~0', '~')]
            validate(value, target, path)
        types = rule.get('type')
        if types is not None:
            types = [types] if isinstance(types, str) else types
            matches = {'object': isinstance(value, dict), 'array': isinstance(value, list),
                'string': isinstance(value, str), 'integer': type(value) is int,
                'boolean': type(value) is bool, 'null': value is None}
            if not any(matches.get(t, False) for t in types):
                raise ValueError('invalid type at ' + path)
        if isinstance(value, dict):
            if not set(rule.get('required', [])) <= set(value):
                raise ValueError('missing required field at ' + path)
            props = rule.get('properties', {})
            if rule.get('additionalProperties') is False and set(value) - set(props):
                raise ValueError('unknown field at ' + path)
            for key in value.keys() & props.keys():
                validate(value[key], props[key], path + '.' + key)
        if isinstance(value, list):
            if not rule.get('minItems', 0) <= len(value) <= rule.get('maxItems', float('inf')):
                raise ValueError('invalid array length at ' + path)
            if 'items' in rule:
                for item in value:
                    validate(item, rule['items'], path + '[]')
        if isinstance(value, str):
            if len(value) < rule.get('minLength', 0):
                raise ValueError('short string at ' + path)
            if 'pattern' in rule and re.search(rule['pattern'], value) is None:
                raise ValueError('pattern mismatch at ' + path)
        if type(value) is int and 'minimum' in rule and value < rule['minimum']:
            raise ValueError('below minimum at ' + path)

    validate(packet, schema, 'inbox')
    if [i['id'] for i in packet['items']] != [c['id'] for c in packet['claims']]:
        raise ValueError('inbox items/claims ID order mismatch')
    return packet


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-executable', required=True, help='trusted operator-selected absolute executable')
    parser.add_argument('--conversation', default='cli-fixture')
    args = parser.parse_args()
    peer = Peer(server_command(args.server_executable))
    try:
        initialized = peer.initialize()
        session = peer.open(args.conversation)
        print(json.dumps({'initialize': initialized, 'session': session}), flush=True)
        # Local JSON requests may use "$session" as the opaque handle placeholder.
        for line in __import__('sys').stdin:
            req = decode_json(line)
            if req['method'] == '$notification':
                print(json.dumps({'notification': peer.notification()}, ensure_ascii=False), flush=True)
                continue
            params = req.get('params', {})
            if params.get('session') == '$session':
                params['session'] = session['session']
            try:
                result = {'result': peer.call(req['method'], params)}
            except RpcError as error:
                result = {'error': error.error}
            print(json.dumps(result, ensure_ascii=False), flush=True)
    finally:
        peer.close()
