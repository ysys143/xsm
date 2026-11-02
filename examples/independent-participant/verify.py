"""Execute public bundle fixtures through the independently written transport."""
import argparse
import importlib.util
import json
import queue
import tempfile
from pathlib import Path
from participant import Peer, server_command

def require(value, detail):
    if not value:
        raise AssertionError(detail)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-executable', required=True)
    parser.add_argument('--checker', required=True, type=Path,
                        help='trusted operator-selected public stdlib checker (Python code)')
    parser.add_argument('--output', required=True, type=Path, help='new evidence directory; must not exist')
    args = parser.parse_args()
    command = server_command(args.server_executable)
    output = args.output
    output.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('public_conformance', args.checker)
    public = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(public)
    public.Peer = Peer
    summaries = []
    for suite in ('lifecycle', 'messaging', 'events', 'decisions'):
        result = public.run(command, suite, capture=True)
        (output / (suite + '.json')).write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
        summary = dict(suite=suite, status=result['status'], checks=len(result['checks']), error=result.get('error'))
        summaries.append(summary)
        print(json.dumps(summary), flush=True)
    records = []
    with tempfile.TemporaryDirectory(prefix='independent-fixtures-') as folder:
        peer = Peer(command, cwd=folder)
        def check(name, action):
            try:
                value = action()
                records.append(dict(name=name, status='passed', output=value))
            except Exception as error:
                records.append(dict(name=name, status='failed', error=repr(error)))
            print(json.dumps(records[-1], ensure_ascii=False), flush=True)
        try:
            peer.initialize()
            a = peer.open('sender', ['messaging', 'inbox', 'events', 'user-decisions'])
            b = peer.open('receiver', ['messaging', 'inbox', 'events'])
            op = lambda name, **args: peer.operation(a, name, **args)
            def concurrent():
                fs = [peer.submit('session.update', dict(session=s['session'], name='fixture-'+str(i), state=state))
                      for i, (s, state) in enumerate([(a,'busy'), (b,'idle')] * 10)]
                frames = [f.result(timeout=5) for f in reversed(fs)]
                require(len({f['id'] for f in frames}) == 20, frames)
                require(all(f.get('result', {}).get('state') == ('busy' if i % 2 == 0 else 'idle') for i,f in enumerate(reversed(frames))), frames)
                return {'responses': len(frames), 'await_order': 'reverse submission'}
            check('concurrent request correlation', concurrent)
            check('unknown method', lambda: peer.call('not-a-method', {'session':a['session']}, error=-32601))
            check('unknown operation', lambda: peer.call('operation.call', dict(session=a['session'], operation='not-an-operation'), error=-32601))
            check('blocking wait unsupported', lambda: peer.call('operation.call', dict(session=a['session'], operation='xsm_send', arguments={'wait':1}), error=-32004))
            check('native transcript answer unsupported', lambda: peer.call('operation.call', dict(session=a['session'], operation='xsm_decide', arguments={'question':'fixture','answer_request':'forged'}), error=-32004))
            check('missing UI capability', lambda: peer.call('operation.call', dict(session=b['session'], operation='xsm_decide', arguments={'question':'fixture'}), error=-32004))
            def fyi():
                peer.call('events.subscribe', {'session':b['session']})
                op('xsm_send', target='ref:'+b['ref'], text='FYI fixture 한글', wake='never')
                try:
                    event = peer.notification(timeout=0.7)
                    raise AssertionError(event)
                except queue.Empty:
                    pass
                packet = peer.operation(b,'xsm_inbox')
                require(len(packet['claims']) == 1, packet)
                # items.wake value domain is not specified by the output schema.
                claim = packet['claims'][0]
                for state in ('queued','refused','unknown','admitted'):
                    p = dict(session=b['session'], id=claim['id'], state=state)
                    if state == 'admitted': p['token']=claim['token']
                    result = peer.call('delivery.report', p)
                    require(result['acknowledged'] is False, result)
                peer.operation(b,'xsm_ack',tokens=[claim['token']])
                return {'observation_window_seconds':0.7, 'packet':packet, 'admission':'synthetic fixture report'}
            check('FYI no unsolicited event and explicit consumption', fyi)
            check('team create', lambda: op('xsm_team', action='create', team='fixture-team'))
            check('team list', lambda: op('xsm_team', action='list'))
            check('team show', lambda: op('xsm_team', action='show', team='fixture-team'))
            def membership(action):
                args=dict(action=action,team='fixture-team',member='ref:'+b['ref'])
                result=op('xsm_team',**args)
                if result.get('status')=='waiting-for-user':
                    event=peer.notification()
                    require(event['params']['decisionId']==result['decision_id'],event)
                    peer.fixture_answer(event,'allow','synthetic-team-'+action)
                    result=op('xsm_team',**args)
                require(result.get('status')!='waiting-for-user',result)
                return {'result':result,'approval':'synthetic fixture only'}
            check('team add local member',lambda: membership('add'))
            check('team remove local member',lambda: membership('remove'))
            check('board set', lambda: op('xsm_board',action='set',team='fixture-team',item='progress',text='Fixture board value'))
            check('board show', lambda: op('xsm_board',action='show',team='fixture-team'))
            check('board log', lambda: op('xsm_board',action='log',team='fixture-team'))
            check('board decisions', lambda: op('xsm_board',action='decisions',team='fixture-team'))
            for action in ('mute','unmute','sync'):
                check('board '+action, lambda action=action: op('xsm_board',action=action,team='fixture-team'))
            check('nonmember board rejected', lambda: peer.call('operation.call',dict(session=b['session'],operation='xsm_board',arguments=dict(action='show',team='fixture-team')),error=-32602))
            def attachment():
                text='Inline attachment fixture 한글\n'
                result=op('xsm_send',target='ref:'+b['ref'],text='Attachment fixture',wake='never',
                          attachments=[{'name':'fixture.txt','text':text}],attachment_fallback='inline',request_id='inline-fixture')
                packet=peer.operation(b,'xsm_inbox')
                require(len(packet['claims']) == 1 and any('fixture.txt' in m for m in packet['messages']),packet)
                peer.operation(b,'xsm_ack',tokens=[c['token'] for c in packet['claims']])
                return {'send':result,'inbox':packet,'scope':'Inline input accepted and attachment notice received; content retrieval and forced inline fallback are not certified'}
            check('inline attachment input and manifest notice',attachment)
            check('attachment unknown field rejected', lambda: peer.call('operation.call', dict(session=a['session'],operation='xsm_send',arguments={'target':'ref:'+b['ref'],'text':'invalid fixture','attachments':[{'name':'x','path':'/forbidden'}]}),error=-32602))
            def decision_helpers():
                args=dict(question='Synthetic fixture only: choose',options=['blue','green'],decision_key='helper-fixture')
                pending=op('xsm_decide',**args)
                event=peer.notification()
                require(event['method']=='decision/request' and event['params']['decisionId']==pending['decision_id'],event)
                peer.abandon(event)
                op('xsm_decide',**args)
                fresh=peer.notification()
                answer=peer.fixture_answer(fresh,'blue','synthetic-helper-callback')
                return {'kind':'synthetic fixture, no human approval','answer':answer,'retry':op('xsm_decide',**args)}
            check('participant answer and abandon helpers',decision_helpers)
        finally:
            diagnostics=peer.close()
            (output/'participant-wire.json').write_text(json.dumps(peer.trace,ensure_ascii=False,indent=2)+'\n')
            (output/'fixtures.json').write_text(json.dumps({'checks':records,'diagnostics':diagnostics},ensure_ascii=False,indent=2)+'\n')
    (output/'summary.json').write_text(json.dumps({'public_suites':summaries,'fixture_passed':sum(r['status']=='passed' for r in records),'fixture_failed':sum(r['status']=='failed' for r in records)},indent=2)+'\n')
    return 1 if any(s['status']!='passed' for s in summaries) or any(r['status']=='failed' for r in records) else 0

if __name__ == '__main__':
    raise SystemExit(main())
