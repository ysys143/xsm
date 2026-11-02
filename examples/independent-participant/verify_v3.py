"""Black-box fixtures derived only from the v3 public bundle; stdlib only."""
import argparse
import base64
import copy
import hashlib
import importlib.util
import json
import queue
import tempfile
from pathlib import Path
from participant_v3 import Peer, RpcError, server_command, validate_inbox, decode_frame


class RawProbe(Peer):
    """Fixture-only raw envelopes, including errors whose response ID is null."""
    def _read(self):
        try:
            while True:
                line=self.process.stdout.readline(4*1048576+1)
                if not line:raise EOFError('raw probe stdout closed')
                if len(line)>4*1048576 or not line.endswith(b'\n'):raise ValueError('invalid raw probe frame')
                frame=decode_frame(line)
                if not isinstance(frame,dict) or frame.get('jsonrpc')!='2.0':raise ValueError('invalid raw probe JSON-RPC')
                self.trace.append({'direction':'receive','frame':frame})
                self.notifications.put(frame)
        except BaseException as error:
            self._fail(error)

    def exchange(self,wire):
        if self.terminal_failure:raise self.terminal_failure
        self.trace.append({'direction':'send-raw-fixture','wire_utf8':wire.decode('utf-8')})
        self.process.stdin.write(wire);self.process.stdin.flush()
        return self.notification()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-executable', required=True)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--checker', type=Path, help='trusted operator-selected public stdlib conformance checker')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    command = server_command(args.server_executable)
    args.output.mkdir(parents=True, exist_ok=False)
    schema = json.loads((args.bundle/'inbox-result.schema.json').read_text(encoding='utf-8'))
    public_suites=[]
    if args.checker:
        spec=importlib.util.spec_from_file_location('operator_public_checker_v3',args.checker)
        public=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(public)
        public.Peer=Peer
        for suite in ('lifecycle','messaging','events','decisions'):
            result=public.run(command,suite,capture=True)
            (args.output/('public-'+suite+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            public_suites.append({'suite':suite,'status':result['status'],'checks':len(result['checks']),'error':result.get('error')})
            print(json.dumps(public_suites[-1]),flush=True)
    scenarios = []

    def scenario(name, action):
        record = {'name':name, 'status':'running', 'checks':[]}
        scenarios.append(record)
        with tempfile.TemporaryDirectory(prefix='independent-v3-') as cwd:
            peer = Peer(command, cwd=cwd)
            def expect(label, condition, evidence=None):
                if not condition:
                    raise AssertionError({'check':label,'evidence':evidence})
                record['checks'].append(label)
            try:
                peer.initialize()
                record['result'] = action(peer, expect)
                record['status'] = 'failed' if isinstance(record['result'],dict) and record['result'].get('contract_mismatches') else 'passed'
            except Exception as error:
                record.update(status='failed', error=repr(error))
            finally:
                record['diagnostics'] = peer.close()
                (args.output/(name+'-wire.json')).write_text(json.dumps(peer.trace,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(record,ensure_ascii=False),flush=True)

    def files(peer, expect):
        sender=peer.open('files-sender')
        receiver=peer.open('files-receiver')
        foreign=peer.open('files-foreign')
        peer.inbox(receiver,schema)  # Identified operation establishes file-reader observation.
        text='V3 text copy 한글\n'
        binary=b'\x00\xff\x80binary\r\n'
        body='File fixture body'
        sent=peer.operation(sender,'xsm_send',target='ref:'+receiver['ref'],text=body,wake='never',request_id='v3-files',
            attachments=[{'name':'copy.txt','text':text},{'name':'copy.bin','base64':base64.b64encode(binary).decode('ascii')}],attachment_fallback='inline')
        expect('structured sender metadata',isinstance(sent.get('send'),dict) and sent['send'].get('id')=='v3-files',sent)
        materials=sent['materials']
        expect('known reader retains files mode',materials['mode']=='files',materials)
        packet=peer.inbox(receiver,schema)
        expect('one claimed file-bearing original',len(packet['claims'])==1 and 'files' in packet['items'][0],packet)
        carrier=packet['items'][0]['files']
        expect('exact attachment entry set',sorted(e['name'] for e in carrier['files'])==['copy.bin','copy.txt'],carrier)
        expect('source manifest identity preserved',carrier['manifest_id']==materials['manifest_id'],carrier)
        expect('FYI wake boolean false',packet['items'][0]['wake'] is False,packet)
        received_manifest=peer.operation(receiver,'xsm_files',storage_id=carrier['storage_id'])
        outgoing_manifest=peer.operation(sender,'xsm_files',storage_id=materials['manifest_id'],outgoing=True)
        expect('recipient manifest ownership and metadata binding',received_manifest['storage_id']==carrier['storage_id'] and
            all(received_manifest['manifest'][key]==carrier[key] for key in ('version','sha256')) and received_manifest['manifest']['id']==carrier['manifest_id'],received_manifest)
        expect('outgoing frozen manifest identity',outgoing_manifest['storage_id']==materials['manifest_id'] and
            outgoing_manifest['manifest']['id']==materials['manifest_id'] and outgoing_manifest['manifest']['sha256']==carrier['sha256'],outgoing_manifest)
        expect('manifest entry metadata matches carrier',
            [{k:e[k] for k in ('id','name','size','sha256')} for e in received_manifest['manifest']['files']]==carrier['files'],received_manifest)
        expect('outgoing entry set',sorted(e['name'] for e in outgoing_manifest['manifest']['files'])==['copy.bin','copy.txt'],outgoing_manifest)
        outgoing_reads={}
        for entry in outgoing_manifest['manifest']['files']:
            expected=text.encode('utf-8') if entry['name']=='copy.txt' else binary
            value=peer.operation(sender,'xsm_files',storage_id=materials['manifest_id'],outgoing=True,entry_id=entry['id'],encoding='base64')
            expect('outgoing frozen bytes '+entry['name'],base64.b64decode(value['content'],validate=True)==expected,value)
            expect('outgoing ID binding '+entry['name'],value['storage_id']==materials['manifest_id'] and value['entry_id']==entry['id'],value)
            outgoing_reads[entry['name']]=value
        results={}
        for entry in carrier['files']:
            expected=text.encode('utf-8') if entry['name']=='copy.txt' else binary
            expect('metadata byte size and sha256 '+entry['name'],entry['size']==len(expected) and entry['sha256']==hashlib.sha256(expected).hexdigest(),entry)
            result=peer.operation(receiver,'xsm_files',storage_id=carrier['storage_id'],entry_id=entry['id'],encoding='base64')
            content=base64.b64decode(result['content'],validate=True)
            expect('received bytes '+entry['name'],content==expected,result)
            expect('received result ID/encoding binding '+entry['name'],result['storage_id']==carrier['storage_id'] and result['entry_id']==entry['id'] and result['encoding']=='base64',result)
            if entry['name']=='copy.txt':
                read_text=peer.operation(receiver,'xsm_files',storage_id=carrier['storage_id'],entry_id=entry['id'],encoding='text')
                expect('UTF-8 text copy',read_text['content']==text,read_text)
            results[entry['name']]=result
        # Manifest wrapper fields are observed structured wire data. No prose
        # decoding or filesystem-path derivation is used.
        current=peer.inbox(receiver,schema,message_ids=[packet['claims'][0]['id']])
        expect('file reads do not consume original',current['claims']==packet['claims'],current)
        try:
            foreign_result=peer.operation(foreign,'xsm_files',storage_id=carrier['storage_id'])
        except RpcError as error:
            foreign_result={'error':error.error}
        expect('foreign conversation has no file content', 'error' in foreign_result,foreign_result)
        ack=peer.operation(receiver,'xsm_ack',tokens=[packet['claims'][0]['token']])
        expect('explicit ACK after copy reads',ack['acked']==[packet['claims'][0]['id']],ack)
        return dict(sent=sent,carrier=carrier,received_manifest=received_manifest,outgoing_manifest=outgoing_manifest,outgoing_reads=outgoing_reads,reads=results,foreign=foreign_result)

    def fallback(peer,expect):
        sender=peer.open('inline-sender')
        receiver=peer.open('fresh-inline-receiver',['messaging','inbox','events'])
        peer.call('events.subscribe',{'session':receiver['session']})
        text='Fresh reader inline copy 한글\n'
        sent=peer.operation(sender,'xsm_send',target='ref:'+receiver['ref'],text='Explicit body fallback',wake='never',request_id='v3-inline',
            attachments=[{'name':'fallback.txt','text':text}],attachment_fallback='inline')
        expect('fresh reader uses inline mode',sent['materials']['mode']=='inline',sent)
        packet=peer.inbox(receiver,schema)
        expect('body includes intended UTF-8 copy',text.strip() in '\n'.join(packet['messages']),packet)
        expect('inline item carries no files',len(packet['items'])==1 and 'files' not in packet['items'][0],packet)
        expect('inline FYI is false',packet['items'][0]['wake'] is False,packet)
        retry_args=dict(target='ref:'+receiver['ref'],text='Explicit body fallback',wake='never',request_id='v3-inline',
            manifest_id=sent['materials']['manifest_id'],attachment_fallback='inline')
        try:
            retry=peer.operation(sender,'xsm_send',**retry_args)
        except RpcError as error:
            retry={'error':error.error}
        else:
            if retry['send']['status']=='refused':
                expect('committed request change is explicitly refused',True)
            else:
                expect('accepted committed inline retry keeps inline carrier',retry['materials']['mode']=='inline',retry)
        current=peer.inbox(receiver,schema,message_ids=[packet['claims'][0]['id']])
        expect('reader observation cannot rewrite committed original',current['messages']==packet['messages'] and current['claims']==packet['claims'] and 'files' not in current['items'][0],current)
        peer.operation(receiver,'xsm_ack',tokens=[packet['claims'][0]['token']])
        return dict(sent=sent,inbox=packet,retry_after_reader_observation=retry)

    def preparation(peer,expect):
        sender=peer.open('preparation-sender')
        receiver=peer.open('fresh-no-reader')
        body='Preparation recovery fixture'
        original=dict(target='ref:'+receiver['ref'],text=body,wake='never',request_id='v3-preparation',attachments=[{'name':'copy.txt','text':'Frozen preparation copy 한글'}])
        try:
            value=peer.operation(sender,'xsm_send',**original)
        except RpcError as error:
            error_value=error.error
        else:
            raise AssertionError({'expected':'documented preparation refusal for unknown reader without fallback','observed':value})
        recovery=error_value['data']['attachment_error']
        expect('structured preparation refusal',all(k in recovery for k in ('code','reason','request_id','manifest_id','body_sent','recovery')),recovery)
        expect('failed preparation has not sent its body',recovery['body_sent'] is False and recovery['request_id']=='v3-preparation',recovery)
        manifest=peer.operation(sender,'xsm_files',storage_id=recovery['manifest_id'],outgoing=True)
        packet=peer.inbox(receiver,schema) # Also establishes a reader for explicit recovery.
        expect('failed preparation leaves receiver empty',packet['claims']==[] and packet['messages']==[],packet)
        retry=dict(original)
        retry.pop('attachments')
        retry['manifest_id']=recovery['manifest_id']
        changed=dict(retry,text='Changed body forbidden for the frozen request')
        try:
            changed_result=peer.operation(sender,'xsm_send',**changed)
        except RpcError as error:
            changed_result={'error':error.error}
        expect('frozen manifest refuses changed body', 'error' in changed_result,changed_result)
        empty=peer.inbox(receiver,schema)
        expect('changed body refusal also leaves inbox empty',empty['claims']==[] and empty['messages']==[],empty)
        sent=peer.operation(sender,'xsm_send',**retry)
        expect('recovery keeps request and manifest IDs',sent['send']['id']=='v3-preparation' and sent['materials']['manifest_id']==recovery['manifest_id'],sent)
        packet=peer.inbox(receiver,schema)
        expect('recovery sends exactly one original',len(packet['claims'])==1 and packet['claims'][0]['id']=='v3-preparation',packet)
        carrier=packet['items'][0]['files']
        entry=carrier['files'][0]
        content=peer.operation(receiver,'xsm_files',storage_id=carrier['storage_id'],entry_id=entry['id'],encoding='text')
        expect('recovery uses frozen original bytes',content['content']=='Frozen preparation copy 한글',content)
        peer.operation(receiver,'xsm_ack',tokens=[packet['claims'][0]['token']])
        return dict(error=error_value,frozen_manifest=manifest,changed_body=changed_result,retry=sent)

    def wake(peer,expect):
        sender=peer.open('wake-sender')
        receiver=peer.open('wake-receiver',['messaging','inbox','events'])
        peer.call('events.subscribe',{'session':receiver['session']})
        peer.operation(sender,'xsm_send',target='ref:'+receiver['ref'],text='Auto policy fixture',request_id='v3-auto')
        event=peer.notification()
        expect('auto event receiver binding',event['method']=='events/available' and event['params']['session']==receiver['session'],event)
        packet=peer.inbox(receiver,schema)
        expect('auto wake boolean true',packet['items'][0]['wake'] is True,packet)
        peer.operation(receiver,'xsm_ack',tokens=[packet['claims'][0]['token']])
        # A null legacy/unknown stored policy cannot be produced by valid xsm_send.
        synthetic=copy.deepcopy(packet);synthetic['items'][0]['wake']=None
        validate_inbox(synthetic,schema)
        expect('null wake accepted by public schema locally',True)
        for invalid in ('never',0,1):
            bad=copy.deepcopy(packet);bad['items'][0]['wake']=invalid
            try:validate_inbox(bad,schema)
            except ValueError:pass
            else:raise AssertionError({'bad wake accepted':invalid})
        expect('string and numeric wake rejected locally',True)
        return dict(event=event,packet=packet,null_fixture='local synthetic schema acceptance only',unknown_server_wake='not run; no public producer of unknown stored policy')

    def precedence(peer,expect):
        session=peer.open('precedence')
        cases=[('unknown without handle','not-a-method',{},-32001),
               ('unknown with valid handle','not-a-method',{'session':session['session']},-32601),
               ('known unknown fields before handle','session.update',{'session':'invalid','extra':True},-32602),
               ('unknown operation','operation.call',dict(session=session['session'],operation='unknown'),-32601),
               ('negative wait','operation.call',dict(session=session['session'],operation='xsm_send',arguments={'wait':-1}),-32602),
               ('positive blocking wait','operation.call',dict(session=session['session'],operation='xsm_send',arguments={'wait':1}),-32004),
               ('negative inbox wait','operation.call',dict(session=session['session'],operation='xsm_inbox',arguments={'wait':-1}),-32602),
               ('negative status wait with declared minimum','operation.call',dict(session=session['session'],operation='xsm_question_status',arguments={'wait':-1}),-32602),
               ('wrong type precedes blocking restriction','operation.call',dict(session=session['session'],operation='xsm_send',arguments={'wait':'1'}),-32602)]
        results=[]
        mismatches=[]
        for label,method,params,code in cases:
            try:
                result=peer.call(method,params)
                observed={'result':result}
            except RpcError as error:
                observed={'error':error.error}
            matches=observed.get('error',{}).get('code')==code
            record={'case':label,'expected_code':code,'observed':observed,'matches':matches}
            results.append(record)
            if matches: expect(label,True)
            else: mismatches.append(record)
        return {'cases':results,'contract_mismatches':mismatches}

    def decisions(peer,expect):
        session=peer.open('decisions',['user-decisions','messaging','inbox'])
        def op(name,**kw):return peer.operation(session,name,**kw)
        def pending(key,options=None):
            arguments=dict(question='Synthetic v3 lifecycle '+key,decision_key='v3-'+key,options=options or ['yes','no'])
            result=op('xsm_decide',**arguments)
            event=peer.notification()
            expect('route correlation '+key,event['params']['decisionId']==result['decision_id'],event)
            return arguments,result,event
        results={}
        for action,wanted in [('decline','unshown-or-declined'),('cancel','dismissed')]:
            arguments,result,event=pending(action)
            response=peer.fixture_response(event,action,'fixture-'+action,answer=None)
            status=op('xsm_decision_status',id=result['decision_id'])
            results[action]=dict(response=response,status=status)
            # Document says recorded response state, not a universal domain status.
            expect('non-accept callback records '+wanted,status['status']==wanted and response['status']==wanted,status)
            expect('non-accept has no application '+action,not status.get('application'),status)
        arguments,result,event=pending('abandon')
        response=peer.abandon(event)
        status=op('xsm_decision_status',id=result['decision_id'])
        expect('abandon keeps pending and no answer',status['status']=='pending' and status['answer'] is None and not status['application'],status)
        expect('abandon display not requested',status['display']['status']=='not-requested',status)
        retry=op('xsm_decide',**arguments);fresh=peer.notification()
        expect('abandon redisplay preserves deadline',fresh['params']['expiresAt']==event['params']['expiresAt'],fresh)
        expect('abandon redisplay rotates route',fresh['params']['questionId']!=event['params']['questionId'],fresh)
        results['abandon']=dict(response=response,status=status,fresh=fresh)
        peer.abandon(fresh)
        arguments,result,event=pending('business-no')
        response=peer.fixture_response(event,'accept','fixture-business-no',answer='no')
        status=op('xsm_decision_status',id=result['decision_id'])
        expect('business no is answered not denied',status['status']=='answered' and status['answer']['reply']['result']['content']['answer']=='no',status)
        expect('accept does not automatically apply',not status['application'],status)
        applied=op('xsm_decide',**arguments)
        applied_status=op('xsm_decision_status',id=result['decision_id'])
        expect('explicit retry applies business no',applied_status['status']=='applied' and applied_status['answer']['reply']['result']['content']['answer']=='no',applied_status)
        results['business-no']=dict(response=response,before=status,retry=applied,after=applied_status)
        arguments,result,event=pending('withdraw')
        withdrawn=op('xsm_decision_status',id=result['decision_id'],cancel=True)
        expect('explicit withdrawal is cancelled',withdrawn['status']=='cancelled' and withdrawn['answer'] is None and not withdrawn['application'],withdrawn)
        results['withdraw']=withdrawn
        arguments,result,event=pending('blank-answer')
        error=peer.call('decision.response',dict(session=session['session'],questionId=event['params']['questionId'],challenge=event['params']['challenge'],displayed=event['params']['question'],action='accept',answer='',source_id='fixture-empty'),error=-32602)
        expect('empty accept answer rejected',True)
        peer.abandon(event)
        results['empty-answer']=error
        arguments,result,event=pending('cancel-content')
        response=peer.fixture_response(event,'cancel','fixture-cancel-content',answer='yes')
        status=op('xsm_decision_status',id=result['decision_id'])
        expect('non-accept content is not applied',status['status']=='dismissed' and not status['application'],status)
        results['cancel-content']=dict(response=response,status=status)
        return results

    def framing_precedence(peer,expect):
        probe=RawProbe(command,cwd=peer.cwd)
        results=[]
        def exchange(label,wire,code=None):
            result=probe.exchange(wire)
            if code is not None:
                expect(label,result.get('error',{}).get('code')==code,result)
            results.append({'case':label,'response':result})
            return result
        try:
            for label,wire in [
                ('nonfinite framing before initialization',b'{"jsonrpc":"2.0","id":1,"method":"not-a-method","params":{"x":NaN}}\n'),
                ('duplicate key framing before initialization',b'{"jsonrpc":"2.0","id":1,"id":2,"method":"not-a-method"}\n')]:
                result=exchange(label,wire)
                expect(label,result.get('error',{}).get('code') in (-32700,-32600),result)
            exchange('dispatch before initialization',b'{"jsonrpc":"2.0","id":3,"method":"not-a-method"}\n',-32002)
            result=exchange('valid initialize after malformed requests',b'{"jsonrpc":"2.0","id":4,"method":"initialize","params":{"protocolVersion":"1"}}\n')
            expect('valid initialization survived malformed input',result.get('result',{}).get('protocolVersion')=='1',result)
            exchange('repeat initialize precedes unknown field',b'{"jsonrpc":"2.0","id":5,"method":"initialize","params":{"protocolVersion":"1","extra":true}}\n',-32600)
            return {'responses':results,'framing_code_scope':'Malformed JSON is asserted as parse/invalid-frame class; no undocumented finer precedence inferred'}
        finally:
            diagnostics=probe.close()
            peer.trace.extend({'raw_probe':entry} for entry in probe.trace)
            if diagnostics:raise AssertionError({'raw_probe_diagnostics':diagnostics})

    def permission_decisions(peer,expect):
        owner=peer.open('permission-owner',['user-decisions','messaging','inbox'])
        guest=peer.open('permission-guest')
        def op(name,**kw):return peer.operation(owner,name,**kw)
        op('xsm_team',action='create',team='permission-fixture')
        initial=op('xsm_team',action='show',team='permission-fixture')['members']
        results={}
        for action,answer in [('decline',None),('cancel',None),('accept','deny')]:
            arguments=dict(action='add',team='permission-fixture',member='ref:'+guest['ref'],decision_key='v3-permission-'+action)
            pending=op('xsm_team',**arguments)
            event=peer.notification()
            expect('permission route '+action,event['params']['decisionId']==pending['decision_id'],event)
            response=peer.fixture_response(event,action,'fixture-permission-'+action,answer=answer)
            before=op('xsm_decision_status',id=pending['decision_id'])
            expect('permission callback has no application '+action,not before['application'],before)
            expect('callback has no team effect '+action,op('xsm_team',action='show',team='permission-fixture')['members']==initial)
            if action=='accept':
                expect('explicit deny has denied/answered state',before['status'] in ('denied','answered'),before)
                # The exact original invocation, never a new consent request.
                try: retry=op('xsm_team',**arguments)
                except RpcError as error: retry={'error':error.error}
                after=op('xsm_decision_status',id=pending['decision_id'])
                expect('permission deny retry cannot add member',op('xsm_team',action='show',team='permission-fixture')['members']==initial,after)
            elif action=='decline':
                try: retry=op('xsm_team',**arguments)
                except RpcError as error: retry={'error':error.error}
                after=op('xsm_decision_status',id=pending['decision_id'])
                expect('permission decline retry cannot add member',op('xsm_team',action='show',team='permission-fixture')['members']==initial,after)
            else:
                retry=None
                after=before
                expect('cancel is dismissal not withdrawal',before['status']=='dismissed',before)
            results[action]=dict(response=response,before=before,retry=retry,after=after)
        return results

    scenario('files',files)
    scenario('fresh-inline',fallback)
    scenario('preparation-recovery',preparation)
    scenario('wake',wake)
    scenario('error-precedence',precedence)
    scenario('framing-precedence',framing_precedence)
    scenario('decision-lifecycle',decisions)
    scenario('permission-decisions',permission_decisions)
    report={'public_suites':public_suites,'public_suite_scope':'lifecycle is repeated across suites; optional checker omission means not run', 'scenarios':scenarios,'passed':sum(r['status']=='passed' for r in scenarios),'failed':sum(r['status']=='failed' for r in scenarios),
            'checks_passed':sum(len(r['checks']) for r in scenarios),'not_run':[
                {'feature':'real expiry and clock rollback','reason':'expiresAt evaluated on server clock; no time travel or long-duration wait performed'},
                {'feature':'unknown stored wake null on real server','reason':'accepted producer schema permits auto/never only; storage mutation forbidden'},
                {'feature':'native human UI and external agents','reason':'outside authorized fixture scope'}]}
    (args.output/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 1 if report['failed'] or any(s['status']!='passed' for s in public_suites) else 0

if __name__=='__main__':
    raise SystemExit(main())
