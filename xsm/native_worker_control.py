"""Private JSON-RPC channel inherited only by an explicitly launched native frontend.

It binds a host-observed new conversation before its first model turn. It is not
an operation exposed to models and cannot collect or manufacture user decisions.
"""
from __future__ import annotations

import json
import os
import socket
import threading

ENV_FD = 'XSM_OWNED_CONTROL_FD'
MAX_FRAME = 16384


class ControlError(ValueError):
    pass


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ControlError('duplicate control field')
        result[key] = value
    return result


def _constant(value):
    raise ControlError('non-JSON native control value')


def _read(stream):
    line = stream.readline(MAX_FRAME + 1)
    if not line:
        return None
    if len(line) > MAX_FRAME or not line.endswith(b'\n'):
        raise ControlError('invalid native control frame')
    try:
        result = json.loads(line.decode('utf-8'), object_pairs_hook=_unique, parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ControlError('invalid native control JSON') from error
    if not isinstance(result, dict) or result.get('jsonrpc') != '2.0':
        raise ControlError('invalid native control envelope')
    return result


def _write(stream, value):
    data = (json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
    if len(data) > MAX_FRAME:
        raise ControlError('native control frame is too large')
    stream.write(data)
    stream.flush()


class WorkerControl:
    def __init__(self, bind, *, cancellation=None, stopped=None):
        self.parent, self.child = socket.socketpair()
        self.bind = bind
        self.cancellation = cancellation
        self.stopped = stopped
        self.native_id = None
        self.failure = None
        self.thread = None

    def start(self):
        self.child.close()
        self.thread = threading.Thread(target=self._serve, name='xsm-owned-native-control', daemon=True)
        self.thread.start()

    def _serve(self):
        try:
            with self.parent.makefile('rwb', buffering=0) as stream:
                while True:
                    request = _read(stream)
                    if request is None:
                        return
                    ident = request.get('id')
                    if type(ident) is not int:
                        raise ControlError('native control requires an integer request ID')
                    try:
                        if set(request) != {'jsonrpc', 'id', 'method', 'params'}:
                            raise ControlError('unknown native control method')
                        params = request['params']
                        if not isinstance(params, dict):
                            raise ControlError('invalid native control fields')
                        if request['method'] == 'native.bind':
                            if set(params) != {'native_session_id'}:
                                raise ControlError('invalid native binding fields')
                            native_id = params['native_session_id']
                            if not isinstance(native_id, str) or not native_id or len(native_id) > 4096:
                                raise ControlError('invalid native conversation ID')
                            if self.native_id not in (None, native_id):
                                raise ControlError('native conversation changed')
                            self.bind(native_id)
                            self.native_id = native_id
                            result = {'bound': True}
                        elif request['method'] == 'native.cancellation':
                            if params or self.native_id is None:
                                raise ControlError('cancellation query requires a bound context')
                            pending = self.cancellation() if self.cancellation else False
                            if type(pending) is not bool:
                                raise ControlError('invalid cancellation state')
                            result = {'requested': pending}
                        elif request['method'] == 'native.cancelled':
                            if (set(params) != {'native_session_id'} or self.native_id is None
                                    or params['native_session_id'] != self.native_id or not self.stopped
                                    or not self.cancellation or self.cancellation() is not True):
                                raise ControlError('native stop report has no matching cancellation')
                            self.stopped(self.native_id)
                            result = {'recorded': True}
                        else:
                            raise ControlError('unknown native control method')
                        _write(stream, {'jsonrpc': '2.0', 'id': ident, 'result': result})
                    except Exception as error:
                        self.failure = type(error).__name__
                        _write(stream, {'jsonrpc': '2.0', 'id': ident,
                                        'error': {'code': -32003, 'message': 'native context binding refused'}})
        except (OSError, ValueError) as error:
            self.failure = type(error).__name__
        finally:
            try:
                self.parent.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def close(self):
        self.child.close()
        try:
            self.parent.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        if self.thread:
            self.thread.join(timeout=3)
        self.parent.close()
        if self.thread and self.thread.is_alive():
            raise ControlError('native worker control did not stop')


class WorkerControlClient:
    def __init__(self, fd):
        self.socket = socket.socket(fileno=fd)
        self.socket.set_inheritable(False)
        self.stream = self.socket.makefile('rwb', buffering=0)
        self.serial = 0
        self.native_id = None
        self.lock = threading.Lock()

    @classmethod
    def from_environment(cls):
        value = os.environ.pop(ENV_FD, None)
        if not value or not value.isdecimal():
            raise ControlError('native frontend has no private worker control descriptor')
        return cls(int(value))

    def bind(self, native_id):
        if self.native_id not in (None, native_id):
            raise ControlError('native conversation changed')
        self._rpc('native.bind', {'native_session_id': native_id}, 'bound')
        self.native_id = native_id

    def _rpc(self, method, params, field):
        with self.lock:
            self.serial += 1
            _write(self.stream, {'jsonrpc': '2.0', 'id': self.serial, 'method': method, 'params': params})
            reply = _read(self.stream)
            result = reply.get('result') if reply else None
            if (not reply or set(reply) != {'jsonrpc', 'id', 'result'} or type(reply.get('id')) is not int
                    or reply['id'] != self.serial or not isinstance(result, dict)
                    or set(result) != {field} or type(result[field]) is not bool
                    or (field != 'requested' and result[field] is not True)):
                raise ControlError('native control request was not accepted')
            return result[field]

    def cancellation_requested(self):
        if self.native_id is None:
            raise ControlError('native context is not bound')
        return self._rpc('native.cancellation', {}, 'requested')

    def report_stopped(self):
        if self.native_id is None:
            raise ControlError('native context is not bound')
        self._rpc('native.cancelled', {'native_session_id': self.native_id}, 'recorded')

    def close(self):
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.stream.close()
        self.socket.close()
