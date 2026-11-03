"""Deliberately invalid local stdio peers; no xsm imports or model calls."""
import json
import sys
import time


def serve(mode):
    request = json.loads(sys.stdin.readline())
    frame = {'jsonrpc': '2.0', 'id': request['id'], 'result': {'closed': True}}
    if mode == 'wrong-id': frame['id'] += 1
    elif mode == 'boolean-id': frame['id'] = True
    elif mode == 'both': frame['error'] = {'code': -32603, 'message': 'bad'}
    elif mode == 'missing-result': del frame['result']
    elif mode == 'bad-result': frame['result'] = {'closed': 'yes'}
    elif mode == 'unknown-error': frame = dict(jsonrpc='2.0', id=request['id'], error={'code': 999, 'message': 'bad'})
    elif mode == 'notification-id': frame = dict(jsonrpc='2.0', id=request['id'], method='events/available', params={})
    elif mode == 'duplicate':
        sys.stdout.write('{"jsonrpc":"2.0","id":1,"id":1,"result":{"closed":true}}\n'); return
    elif mode == 'nan':
        sys.stdout.write('{"jsonrpc":"2.0","id":1,"result":{"closed":NaN}}\n'); return
    elif mode == 'overflow':
        sys.stdout.write('{"jsonrpc":"2.0","id":1,"result":{"closed":1e999}}\n'); return
    elif mode == 'invalid-utf8': sys.stdout.buffer.write(b'\xff\n'); return
    elif mode == 'truncated': sys.stdout.write(json.dumps(frame)); return
    elif mode == 'batch': frame = [frame]
    elif mode == 'oversized': sys.stdout.write(' ' * (4*1048576+1) + '\n'); return
    elif mode == 'timeout': time.sleep(2); return
    elif mode == 'eof': return
    sys.stdout.write(json.dumps(frame)+'\n'); sys.stdout.flush()


if __name__ == '__main__':
    serve(sys.argv[1])
