"""Own v5 upload fixtures, separate from operator-selected public checker."""
import argparse
import base64
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path
from participant_v5 import Peer, UploadPlan, RpcError, server_command

MiB=1048576


def plan(receiver,key,data=b'upload fixture',**options):
    return UploadPlan.snapshot('ref:'+receiver['ref'],key,'Own upload fixture '+key,
        [{'name':key+'.bin','data':data}],**options)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-executable',required=True)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--checker',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    command=server_command(args.server_executable)
    schema=json.loads((args.bundle/'inbox-result.schema.json').read_text(encoding='utf-8'))
    spec=importlib.util.spec_from_file_location('operator_public_checker_v5',args.checker)
    checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
    checker.Peer=Peer
    public=[]
    for name in ('lifecycle','messaging','events','decisions','uploads'):
        result=checker.run(command,name,capture=True)
        (args.output/('public-'+name+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        summary={'suite':name,'status':result['status'],'checks':len(result['checks']),'error':result.get('error'),'activeCheck':result.get('activeCheck')}
        public.append(summary);print(json.dumps(summary),flush=True)
    scenarios=[]

    def scenario(name,action):
        record={'name':name,'status':'running','checks':[],'expected_refusals':[]}
        scenarios.append(record)
        with tempfile.TemporaryDirectory(prefix='independent-v5-') as cwd:
            peer=Peer(command,cwd=cwd)
            def expect(label,value,evidence=None):
                if not value:raise AssertionError({'check':label,'evidence':evidence})
                record['checks'].append(label)
            def refused(label,callback,code=-32602):
                try:value=callback()
                except RpcError as error:
                    expect(label,error.error['code']==code,error.error)
                    record['expected_refusals'].append({'case':label,'error':error.error})
                    return error.error
                raise AssertionError({'check':label,'unexpected_success':value})
            try:
                peer.initialize();peer.require_uploads()
                record['result']=action(peer,expect,refused)
                record['status']='passed'
            except Exception as error:
                record.update(status='failed',error=repr(error))
            finally:
                record['diagnostics']=peer.close()
                (args.output/(name+'-wire.json')).write_text(json.dumps(peer.trace,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(record,ensure_ascii=False),flush=True)

    def four_mib(peer,expect,refused):
        sender=peer.open('own-four-mib-sender');receiver=peer.open('own-four-mib-receiver')
        peer.inbox(receiver,schema)
        data=[bytes((j+i*37)%256 for j in range(256))*4096 for i in range(4)]
        snapshot=UploadPlan.snapshot('ref:'+receiver['ref'],'own-four-mib','Four generated binary copies',
            [{'name':'own-%d.bin'%i,'data':d,'source_version':'fixture-v5-%d'%i} for i,d in enumerate(data)])
        expect('own bundle contains exactly 4 MiB',sum(len(f.data) for f in snapshot.files)==4*MiB)
        opened=peer.upload_open(sender,snapshot);token=opened['upload']
        first=peer.upload_write(sender,token,0,0,data[0][:17])
        replay=peer.upload_write(sender,token,0,0,data[0][:17])
        expect('exact first chunk replay does not advance twice',first==replay and replay['offset']==17,replay)
        refused('changed replay refused',lambda:peer.upload_write(sender,token,0,0,b'X'+data[0][1:17]))
        peer.upload_write(sender,token,0,17,data[0][17:31])
        subrange=peer.upload_write(sender,token,0,4,data[0][4:11])
        expect('exact already-present subrange does not change buffer end',peer.upload_status(sender,snapshot.request_id)['offsets']==[31,0,0,0],subrange)
        refused('changed already-present subrange refused',lambda:peer.upload_write(sender,token,0,4,b'changed'))
        refused('overlapping replay cannot extend buffer',lambda:peer.upload_write(sender,token,0,25,data[0][25:40]))
        changed=snapshot.params(sender);changed['text']='Changed active metadata'
        refused('changed active request metadata refused',lambda:peer.call('files.upload.open',changed))
        resumed=peer.upload_open(sender,snapshot)
        expect('same active metadata resumes exact offsets',resumed['upload']==token and resumed['offsets']==[31,0,0,0],resumed)
        receipt=peer.prepare_files(sender,snapshot)
        frozen=receipt.result
        expect('high-level preparation resumes same upload',receipt.upload==token,receipt)
        expect('commit freezes without sending body',frozen['state']=='frozen' and frozen['body_sent'] is False,frozen)
        replay_commit=peer.upload_commit(sender,token)
        expect('commit replay preserves frozen ID',replay_commit['manifest_id']==frozen['manifest_id'] and replay_commit['body_sent'] is False,replay_commit)
        writes_before=sum(t.get('frame',{}).get('method')=='files.upload.write' for t in peer.trace)
        again=peer.prepare_files(sender,snapshot)
        writes_after=sum(t.get('frame',{}).get('method')=='files.upload.write' for t in peer.trace)
        writes=[t['frame'] for t in peer.trace if t.get('direction')=='send' and t.get('frame',{}).get('method')=='files.upload.write']
        expect('all own chunks stay within encoded bound',all(len(t['params']['base64'])<=262144 for t in writes))
        expect('frozen reopen avoids re-upload',again.result['manifest_id']==frozen['manifest_id'] and writes_before==writes_after)
        expect('preparation creates no inbox original',peer.inbox(receiver,schema)['claims']==[])
        # A fresh full bundle proves successful commit released all reserved raw bytes.
        extra=UploadPlan.snapshot(snapshot.target,'after-four-mib','capacity after commit',
            [{'name':'capacity-%d'%i,'data':d} for i,d in enumerate(data)])
        extra_open=peer.upload_open(sender,extra)
        expect('commit releases full shared budget',extra_open['state']=='uploading')
        peer.upload_abort(sender,extra_open['upload'])
        sent=peer.operation(sender,'xsm_send',target=snapshot.target,request_id=snapshot.request_id,text=snapshot.text,
                            manifest_id=frozen['manifest_id'],wake='never')
        expect('explicit send is recorded separately',sent['send']['id']==snapshot.request_id and sent['send']['status']=='stored',sent)
        packet=peer.inbox(receiver,schema)
        expect('exactly one original with 4 copied entries',len(packet['claims'])==1 and packet['claims'][0]['id']==snapshot.request_id and len(packet['items'][0]['files']['files'])==4,packet)
        carrier=packet['items'][0]['files']
        expect('frozen ID survives explicit send',carrier['manifest_id']==frozen['manifest_id'],carrier)
        outgoing=peer.operation(sender,'xsm_files',storage_id=frozen['manifest_id'],outgoing=True)
        digests=[]
        for i,(entry,source) in enumerate(zip(carrier['files'],snapshot.files)):
            result=peer.operation(receiver,'xsm_files',storage_id=carrier['storage_id'],entry_id=entry['id'],encoding='base64')
            got=base64.b64decode(result['content'],validate=True)
            expected=hashlib.sha256(source.data).hexdigest()
            expect('own received 1 MiB bytes/hash '+str(i),got==source.data and len(got)==MiB and entry['size']==MiB and entry['sha256']==expected,result.keys())
            own_entry=outgoing['manifest']['files'][i]
            own=peer.operation(sender,'xsm_files',storage_id=frozen['manifest_id'],entry_id=own_entry['id'],outgoing=True,encoding='base64')
            expect('outgoing bytes '+str(i),base64.b64decode(own['content'],validate=True)==source.data)
            digests.append({'name':entry['name'],'size':len(got),'sha256':expected})
        peer.upload_abort(sender,token)
        expect('abort completion retains indexed frozen copy',peer.upload_status(sender,snapshot.request_id)['manifest_id']==frozen['manifest_id'])
        after_abort=peer.operation(sender,'xsm_files',storage_id=frozen['manifest_id'],outgoing=True,
            entry_id=outgoing['manifest']['files'][0]['id'],encoding='base64')
        expect('abort completion does not delete frozen source bytes',base64.b64decode(after_abort['content'],validate=True)==snapshot.files[0].data)
        current=peer.inbox(receiver,schema,message_ids=[snapshot.request_id])
        expect('abort completion does not consume original',current['claims']==packet['claims'])
        ack=peer.operation(receiver,'xsm_ack',tokens=[packet['claims'][0]['token']])
        expect('ACK only after intended copies were read',ack['acked']==[snapshot.request_id])
        expect('ACK removes canonical original',peer.inbox(receiver,schema)['claims']==[])
        return {'manifest_id':frozen['manifest_id'],'digests':digests,'generated_bytes':4*MiB,'writes':writes_after,
                'body_delivery':'explicit separate fixture send','consumer':'synthetic local byte reader, not native/model'}

    def failures(peer,expect,refused):
        sender=peer.open('failure-owner');receiver=peer.open('failure-reader');peer.inbox(receiver,schema)
        snapshot=plan(receiver,'size-and-offset',b'abcde');opened=peer.upload_open(sender,snapshot);token=opened['upload']
        refused('incomplete size refuses commit',lambda:peer.upload_commit(sender,token))
        expect('incomplete upload remains active',peer.upload_status(sender,snapshot.request_id)['state']=='uploading')
        refused('gap offset refused',lambda:peer.upload_write(sender,token,0,1,b'a'))
        refused('declared size overflow refused',lambda:peer.upload_write(sender,token,0,0,b'abcdef'))
        for label,overrides in [('strict invalid base64',{'base64':'!!!!'}),('negative offset',{'offset':-1}),
            ('out-of-range entry',{'entry':16}),('boolean entry',{'entry':False}),('write path injection',{'path':'/not-read'})]:
            parameters=dict(session=sender['session'],upload=token,entry=0,offset=0,base64='YQ==');parameters.update(overrides)
            refused(label,lambda parameters=parameters:peer.call('files.upload.write',parameters))
        huge=base64.b64encode(b'a'*196609).decode('ascii')
        refused('decoded chunk beyond 192 KiB refused',lambda:peer.call('files.upload.write',dict(session=sender['session'],upload=token,entry=0,offset=0,base64=huge)))
        peer.upload_write(sender,token,0,0,b'abc')
        refused('partial size refuses commit',lambda:peer.upload_commit(sender,token))
        expect('failed commit preserves correct partial offset',peer.upload_status(sender,snapshot.request_id)['offsets']==[3])
        correct=peer.prepare_files(sender,snapshot)
        expect('incomplete buffer can resume to frozen',correct.result['state']=='frozen')
        bad=plan(receiver,'bad-hash',b'abc');bad_params=bad.params(sender)
        corrupt=peer.call('files.upload.open',bad_params)
        peer.upload_write(sender,corrupt['upload'],0,0,b'abd')
        refused('hash mismatch refuses commit',lambda:peer.upload_commit(sender,corrupt['upload']))
        state=peer.upload_status(sender,bad.request_id)
        expect('corrupt buffer remains uploading at declared size',state['state']=='uploading' and state['offsets']==[3],state)
        refused('corrupt earlier bytes cannot be replaced',lambda:peer.upload_write(sender,corrupt['upload'],0,0,b'abc'))
        peer.upload_abort(sender,corrupt['upload'])
        expect('aborted corruption has no indexed intent',peer.upload_status(sender,bad.request_id)['state']=='unknown')
        refused('aborted token cannot accept new write',lambda:peer.upload_write(sender,corrupt['upload'],0,0,b'abc'))
        refused('aborted token cannot commit',lambda:peer.upload_commit(sender,corrupt['upload']))
        base=snapshot.params(sender)
        for label,change in [('file over 1 MiB',{'entries':[dict(base['entries'][0],size=MiB+1)]}),
            ('bundle over 4 MiB',{'entries':[dict(base['entries'][0],name=str(i),size=MiB) for i in range(5)]}),
            ('seventeen entries refused',{'entries':[dict(base['entries'][0],name=str(i),size=0) for i in range(17)]}),
            ('entry source path refused',{'entries':[dict(base['entries'][0],path='/not-read')]}),
            ('top-level source path refused',{'path':'/not-read'}),('uppercase hash refused',{'entries':[dict(base['entries'][0],sha256='A'*64)]})]:
            parameters=dict(base,request_id='invalid-'+str(len(peer.trace)));parameters.update(change)
            refused(label,lambda parameters=parameters:peer.call('files.upload.open',parameters))
        max_entries=UploadPlan.snapshot('ref:'+receiver['ref'],'sixteen-entries','sixteen tiny caller copies',
            [{'name':'entry-'+str(i),'data':bytes([i])} for i in range(16)])
        prepared_entries=peer.prepare_files(sender,max_entries)
        outgoing_entries=peer.operation(sender,'xsm_files',storage_id=prepared_entries.result['manifest_id'],outgoing=True)
        expect('valid sixteen-entry bundle commits',len(outgoing_entries['manifest']['files'])==16)
        last=outgoing_entries['manifest']['files'][15]
        read_last=peer.operation(sender,'xsm_files',storage_id=prepared_entries.result['manifest_id'],outgoing=True,entry_id=last['id'],encoding='base64')
        expect('entry index fifteen retains exact final byte',base64.b64decode(read_last['content'],validate=True)==bytes([15]))
        expect('validation and preparation do not send body',peer.inbox(receiver,schema)['items']==[])
        return {'valid_partial_recovery_manifest':correct.result['manifest_id'],'corrupt_status_before_abort':state}

    def budget(peer,expect,refused):
        a=peer.open('budget-a');b=peer.open('budget-b');receiver=peer.open('budget-target')
        two=lambda key:UploadPlan.snapshot('ref:'+receiver['ref'],key,key,[{'name':'a','data':b'a'*MiB},{'name':'b','data':b'b'*MiB}])
        pa=two('budget-two-a');pb=two('budget-two-b')
        aa=peer.upload_open(a,pa);bb=peer.upload_open(b,pb)
        expect('two sessions reserve shared 4 MiB',aa['state']==bb['state']=='uploading')
        extra=plan(receiver,'budget-extra',b'x')
        refused('shared connection budget rejects extra byte',lambda:peer.upload_open(a,extra))
        # Independent connection budget is separate, even with a shared isolated home.
        other=Peer(command,cwd=peer.cwd)
        try:
            other.initialize();c=other.open('budget-other-connection')
            four=UploadPlan.snapshot('ref:'+receiver['ref'],'other-four','other connection',
                [{'name':str(i),'data':b'z'*MiB} for i in range(4)])
            own=other.upload_open(c,four)
            expect('another connection has independent raw budget',own['state']=='uploading')
            other.upload_abort(c,own['upload'])
        finally:
            diagnostics=other.close();peer.trace.extend({'other_connection':t} for t in other.trace)
            expect('other budget process reaped without diagnostics',diagnostics=='',diagnostics)
        peer.upload_abort(a,aa['upload'])
        extra_open=peer.upload_open(a,extra)
        expect('abort releases reservation for another session',extra_open['state']=='uploading')
        peer.upload_abort(b,bb['upload']);peer.upload_abort(a,extra_open['upload'])
        expect('aborted volatile status becomes unknown',peer.upload_status(a,pa.request_id)['state']=='unknown')
        return {'reserved_bytes':4*MiB,'connection_scope':'two owners share one budget; separate process budget also observed'}

    def slots(peer,expect,refused):
        sender=peer.open('slots-a');second=peer.open('slots-b');receiver=peer.open('slots-target');peer.inbox(receiver,schema)
        opened=[]
        for i in range(16):
            owner=sender if i%2==0 else second
            p=plan(receiver,'slot-'+str(i),b'')
            opened.append((owner,p,peer.upload_open(owner,p)))
        expect('16 concurrent handles across sessions accepted',len({value['upload'] for _,_,value in opened})==16)
        refused('sixteen active handles reject a seventeenth',lambda:peer.upload_open(sender,plan(receiver,'slot-overflow',b'')))
        completed=peer.upload_commit(sender,opened[0][2]['upload'])
        expect('zero-byte entry freezes without body send',completed['state']=='frozen' and completed['body_sent'] is False)
        exact=peer.upload_commit(sender,opened[0][2]['upload'])
        expect('completion token exact replay works before pressure',exact['manifest_id']==completed['manifest_id'])
        try:
            pressure=peer.upload_open(sender,plan(receiver,'slot-pressure',b''))
        except RpcError as error:
            expect('pressure refusal uses invalid-parameters code',error.error['code']==-32602,error.error)
            pressure={'refused':error.error}
            peer.upload_abort(sender,opened[0][2]['upload'])
            eviction=False
        else:
            # The public text bounds retained metadata but does not define a
            # minimum lifetime/eviction policy for a completed token.
            refused('pressure evicts completion token instead of retaining 17',lambda:peer.upload_commit(sender,opened[0][2]['upload']))
            for owner,p,value in opened[1:]:
                active=peer.upload_status(owner,p.request_id)
                expect('active handle survives pressure '+p.request_id,active['state']=='uploading' and active['upload']==value['upload'])
            peer.upload_abort(sender,pressure['upload'])
            eviction=True
        replacement=peer.upload_open(second,plan(receiver,'slot-replacement',b''))
        expect('abort releases slot for replacement',replacement['state']=='uploading')
        recovered=peer.upload_open(sender,opened[0][1])
        expect('indexed frozen open needs no extra volatile slot',recovered['state']=='frozen' and recovered['manifest_id']==completed['manifest_id'])
        refused('full active slot bound remains enforced after frozen lookup',lambda:peer.upload_open(sender,plan(receiver,'still-overflow',b'')))
        for owner,p,value in opened[1:]:peer.upload_abort(owner,value['upload'])
        peer.upload_abort(second,replacement['upload'])
        expect('frozen index survives completion abort',peer.upload_status(sender,opened[0][1].request_id)['state']=='frozen')
        expect('slot activity does not deliver body',peer.inbox(receiver,schema)['claims']==[])
        return {'observable_slot_bound':16,'completion_token_eviction_observed':eviction,'pressure':pressure,
            'gap':'Minimum completed-token lifetime/pressure eviction order is not specified; do not rely on indefinite token replay',
            'empty_entry_sha256':hashlib.sha256(b'').hexdigest()}

    def ownership(peer,expect,refused):
        owner=peer.open('token-owner');foreign=peer.open('token-foreign');receiver=peer.open('token-target');peer.inbox(receiver,schema)
        volatile=plan(receiver,'volatile-owner',b'abc');opened=peer.upload_open(owner,volatile);token=opened['upload']
        for label,callback in [('foreign write',lambda:peer.upload_write(foreign,token,0,0,b'a')),
            ('foreign commit',lambda:peer.upload_commit(foreign,token)),('foreign abort',lambda:peer.upload_abort(foreign,token))]:refused(label,callback)
        expect('foreign status cannot recover owner intent',peer.upload_status(foreign,volatile.request_id)['state']=='unknown')
        peer.call('session.close',{'session':owner['session']});renewed=peer.open('token-owner')
        expect('reopen changes execution generation',renewed['generation']!=owner['generation'] and renewed['ref']==owner['ref'])
        refused('closed session handle refused',lambda:peer.call('files.upload.status',dict(session=owner['session'],request_id=volatile.request_id)),-32001)
        for label,callback in [('old generation write',lambda:peer.upload_write(renewed,token,0,0,b'a')),
            ('old generation commit',lambda:peer.upload_commit(renewed,token)),('old generation abort',lambda:peer.upload_abort(renewed,token))]:refused(label,callback)
        expect('new generation has no old volatile index',peer.upload_status(renewed,volatile.request_id)['state']=='unknown')
        durable=plan(receiver,'durable-owner',b'persisted bytes')
        done=peer.prepare_files(renewed,durable)
        peer.call('session.close',{'session':renewed['session']});again=peer.open('token-owner')
        status=peer.upload_status(again,durable.request_id)
        expect('new generation recovers frozen ID',status['state']=='frozen' and status['manifest_id']==done.result['manifest_id'],status)
        refused('old completion handle not inherited',lambda:peer.upload_commit(again,done.upload))
        changed=durable.params(again);changed['text']='changed frozen body'
        refused('changed frozen intent refused after generation change',lambda:peer.call('files.upload.open',changed))
        expect('same frozen metadata is recoverable',peer.upload_open(again,durable)['manifest_id']==done.result['manifest_id'])
        expect('generation recovery does not send',peer.inbox(receiver,schema)['claims']==[])
        return {'frozen_manifest':status['manifest_id'],'volatile_status':'unknown; not a global rollback claim'}

    def eof(peer,expect,refused):
        receiver=peer.open('eof-receiver');peer.inbox(receiver,schema)
        writer=Peer(command,cwd=peer.cwd)
        replacement=None
        try:
            writer.initialize();owner=writer.open('eof-owner')
            pending=plan(receiver,'eof-volatile',b'not complete');opened=writer.upload_open(owner,pending)
            writer.upload_write(owner,opened['upload'],0,0,b'not')
            durable=plan(receiver,'eof-durable',b'durable EOF fixture')
            done=writer.prepare_files(owner,durable)
            diagnostics=writer.close();expect('EOF owner process reaped',diagnostics=='',diagnostics)
            replacement=Peer(command,cwd=peer.cwd);replacement.initialize();renewed=replacement.open('eof-owner')
            expect('EOF releases lifetime ownership',renewed['ref']==owner['ref'] and renewed['generation']!=owner['generation'])
            refused('EOF volatile token rejected on new connection',lambda:replacement.upload_write(renewed,opened['upload'],0,3,b' complete'))
            expect('EOF volatile request has unknown index',replacement.upload_status(renewed,pending.request_id)['state']=='unknown')
            status=replacement.upload_status(renewed,durable.request_id)
            expect('EOF preserves frozen request-ID lookup',status['manifest_id']==done.result['manifest_id'],status)
            refused('EOF completion token rejected on new connection',lambda:replacement.upload_commit(renewed,done.upload))
            expect('EOF recovery is not body delivery',peer.inbox(receiver,schema)['claims']==[])
            sent=replacement.operation(renewed,'xsm_send',target=durable.target,request_id=durable.request_id,text=durable.text,
                manifest_id=status['manifest_id'],wake='never')
            packet=peer.inbox(receiver,schema);carrier=packet['items'][0]['files'];entry=carrier['files'][0]
            got=peer.operation(receiver,'xsm_files',storage_id=carrier['storage_id'],entry_id=entry['id'],encoding='base64')
            expect('explicit recovery send retains exact EOF bytes',base64.b64decode(got['content'],validate=True)==durable.files[0].data)
            peer.operation(receiver,'xsm_ack',tokens=[packet['claims'][0]['token']])
            return {'manifest_id':status['manifest_id'],'send_status':sent['send']['status']}
        finally:
            writer.close();peer.trace.extend({'writer':t} for t in writer.trace)
            if replacement:
                replacement.close();peer.trace.extend({'replacement':t} for t in replacement.trace)

    def capability(peer,expect,refused):
        sender=peer.open('capability-owner');fresh=peer.open('capability-fresh')
        snapshot=plan(fresh,'capability-recovery','Frozen capability bytes 한글'.encode('utf-8'))
        opened=peer.upload_open(sender,snapshot);token=opened['upload']
        error=refused('unknown file reader refuses preparation without fallback',lambda:peer.prepare_files(sender,snapshot))
        carrier=error['data']['attachment_error']
        expect('structured failure exposes frozen ID and no body send',carrier.get('manifest_id') and carrier.get('body_sent') is False,carrier)
        status=peer.upload_status(sender,snapshot.request_id)
        expect('status recovers failed preparation frozen index',status.get('manifest_id')==carrier['manifest_id'],status)
        # Capability can be established by the receiving host's actual operation.
        empty=peer.inbox(fresh,schema)
        expect('failed capability preparation delivered nothing',empty['claims']==[])
        frozen=peer.upload_commit(sender,token)
        expect('same commit revalidates indexed frozen ID',frozen['manifest_id']==carrier['manifest_id'] and frozen['body_sent'] is False,frozen)
        sent=peer.operation(sender,'xsm_send',target=snapshot.target,request_id=snapshot.request_id,text=snapshot.text,
            manifest_id=frozen['manifest_id'],wake='never')
        packet=peer.inbox(fresh,schema);file_meta=packet['items'][0]['files'];entry=file_meta['files'][0]
        content=peer.operation(fresh,'xsm_files',storage_id=file_meta['storage_id'],entry_id=entry['id'],encoding='base64')
        expect('capability recovery preserves frozen source bytes',base64.b64decode(content['content'],validate=True)==snapshot.files[0].data)
        peer.operation(fresh,'xsm_ack',tokens=[packet['claims'][0]['token']])
        inline_receiver=peer.open('capability-inline-fresh')
        inline=plan(inline_receiver,'upload-inline','Explicit upload fallback 한글'.encode('utf-8'),attachment_fallback='inline')
        prepared=peer.prepare_files(sender,inline)
        expect('explicit fallback authorizes fresh reader preparation',prepared.result['mode']=='inline' and prepared.result['body_sent'] is False,prepared.result)
        sent_inline=peer.operation(sender,'xsm_send',target=inline.target,request_id=inline.request_id,text=inline.text,
            manifest_id=prepared.result['manifest_id'],attachment_fallback='inline',wake='never')
        packet_inline=peer.inbox(inline_receiver,schema)
        expect('explicit upload fallback body includes supplied text',inline.files[0].data.decode('utf-8') in '\n'.join(packet_inline['messages']))
        expect('inline delivery has no files carrier',len(packet_inline['items'])==1 and 'files' not in packet_inline['items'][0])
        expect('fallback keeps prepared frozen ID',sent_inline['materials']['manifest_id']==prepared.result['manifest_id'])
        peer.operation(inline_receiver,'xsm_ack',tokens=[packet_inline['claims'][0]['token']])
        return {'failure':carrier,'recovered_manifest_id':frozen['manifest_id'],'inline_manifest_id':prepared.result['manifest_id'],
                'delivery':'explicit send after preparation; synthetic local consumption'}

    for name,action in [('own-four-mib',four_mib),('size-hash-and-input-errors',failures),('shared-budget',budget),
                        ('sixteen-slots',slots),('owner-and-generation',ownership),('eof-recovery',eof),('capability-recovery',capability)]:
        scenario(name,action)
    summary={'public_suites':public,'own_scenarios':scenarios,'own_passed':sum(s['status']=='passed' for s in scenarios),
        'own_failed':sum(s['status']=='failed' for s in scenarios),'own_checkpoints':sum(len(s['checks']) for s in scenarios),
        'not_run':['real 30-minute decision expiry (operator reports separate fixture; no evidence imported)',
                   'clock manipulation, actual UI, model/native admission, external network/agents',
                   'copy-store quota/7-day retention and backend fault injection']}
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 1 if summary['own_failed'] or any(s['status']!='passed' for s in public) else 0

if __name__=='__main__':
    raise SystemExit(main())
