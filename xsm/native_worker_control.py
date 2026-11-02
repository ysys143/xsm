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
    def __init__(self, bind):
        self.parent, self.child = socket.socketpair()
        self.bind = bind
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
                        if set(request) != {'jsonrpc', 'id', 'method', 'params'} or request['method'] != 'native.bind':
                            raise ControlError('unknown native control method')
                        params = request['params']
                        if not isinstance(params, dict) or set(params) != {'native_session_id'}:
                            raise ControlError('invalid native binding fields')
                        native_id = params['native_session_id']
                        if not isinstance(native_id, str) or not native_id or len(native_id) > 4096:
                            raise ControlError('invalid native conversation ID')
                        self.bind(native_id)
                        self.native_id = native_id
                        _write(stream, {'jsonrpc': '2.0', 'id': ident, 'result': {'bound': True}})
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

    @classmethod
    def from_environment(cls):
        value = os.environ.pop(ENV_FD, None)
        if not value or not value.isdecimal():
            raise ControlError('native frontend has no private worker control descriptor')
        return cls(int(value))

    def bind(self, native_id):
        self.serial += 1
        _write(self.stream, {'jsonrpc': '2.0', 'id': self.serial, 'method': 'native.bind',
                             'params': {'native_session_id': native_id}})
        reply = _read(self.stream)
        result = reply.get('result') if reply else None
        if (not reply or set(reply) != {'jsonrpc', 'id', 'result'} or type(reply.get('id')) is not int
                or reply['id'] != self.serial or not isinstance(result, dict)
                or set(result) != {'bound'} or result['bound'] is not True):
            raise ControlError('native context was not accepted')

    def close(self):
        self.stream.close()
        self.socket.close()
