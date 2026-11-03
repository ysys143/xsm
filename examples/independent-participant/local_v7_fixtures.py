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


def action_cases(examples):
    """Local root-valid substitutions; these are not server executions."""
    owned = [e for e in examples if e['operation'] == 'xsm_owned']
    handover = [e for e in examples if e['operation'] == 'xsm_handover']
    service = next(e['value'] for e in owned if e['arguments']['action'] == 'create')
    listing = next(e['value'] for e in owned if e['value'].get('status') == 'requests')
    task = next(e['value'] for e in owned if e['arguments']['action'] == 'run')
    shown = next(e['value'] for e in handover if e['arguments']['action'] == 'show')
    applied = next(e['value'] for e in handover if e['value'].get('handover', {}).get('action') == 'hand_over')
    pending = next(e['value'] for e in handover if e['value'].get('status') == 'waiting-for-user')
    legacy = next(e['value'] for e in handover if set(e['value']) == {'text'})
    cases = []
    def add(name, op, args, value, accept):
        cases.append(dict(name=name, operation=op, arguments=args, value=value, accept=accept))
    for action in ('create','run','cancel','retry','reconcile'):
        for shape, value in [('service',service),('listing',listing),('task',task)]:
            add('owned-'+action+'-'+shape,'xsm_owned',{'action':action},value,
                shape == ('service' if action == 'create' else 'task'))
    for exact in (False,True):
        for shape, value in [('service',service),('listing',listing),('task',task)]:
            args={'action':'status'}
            if exact: args['request_id']=task['id']
            add('owned-status-'+('exact' if exact else 'history')+'-'+shape,'xsm_owned',args,value,
                shape == ('task' if exact else 'listing'))
    add('owned-status-wrong-task-id','xsm_owned',{'action':'status','request_id':'another-request'},task,False)
    add('owned-required-action-missing','xsm_owned',{},task,False)
    for label,args in [('show',{'action':'show'}),('explicit',{'action':'hand_over'}),('default',{})]:
        for shape,value in [('show',shown),('applied',applied),('pending',pending),('legacy',legacy)]:
            add('handover-'+label+'-'+shape,'xsm_handover',args,value,
                shape in (('show','legacy') if label=='show' else ('applied','pending','legacy')))
    add('handover-explicit-null-is-not-default','xsm_handover',{'action':None},applied,False)
    add('handover-lost-original-context','xsm_handover',None,applied,False)
    return cases


if __name__ == '__main__':
    serve(sys.argv[1])
