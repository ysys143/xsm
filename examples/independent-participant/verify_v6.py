"""Narrow v6 manifest/file-result fixtures; public checker is reported separately."""
import argparse
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path
from participant_v6 import Peer, UploadPlan, FileConsumer, RpcError, server_command, validate_schema, json_equal


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-executable',required=True)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--checker',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    command=server_command(args.server_executable)
    schema=json.loads((args.bundle/'file-result.schema.json').read_text(encoding='utf-8'))
    inbox_schema=json.loads((args.bundle/'inbox-result.schema.json').read_text(encoding='utf-8'))
    consumer=FileConsumer(schema)
    spec=importlib.util.spec_from_file_location('operator_public_checker_v6',args.checker)
    checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker);checker.Peer=Peer
    public=checker.run(command,'uploads',capture=True)
    (args.output/'public-uploads.json').write_text(json.dumps(public,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    public_summary={'suite':'uploads','status':public['status'],'checks':len(public['checks']),
                    'activeCheck':public.get('activeCheck'),'error':public.get('error')}
    print(json.dumps({'public_checker':public_summary}),flush=True)
    scenarios=[]

    def scenario(name,action):
        record={'name':name,'status':'running','checks':[],'refusals':[]};scenarios.append(record)
        with tempfile.TemporaryDirectory(prefix='independent-v6-') as cwd:
            peer=Peer(command,cwd=cwd)
            def expect(label,value,evidence=None):
                if not value:raise AssertionError({'check':label,'evidence':evidence})
                record['checks'].append(label)
            def refused(label,session,arguments,expected_code=-32602):
                try:result=peer.operation(session,'xsm_files',**arguments)
                except RpcError as error:
                    expect(label,expected_code is None or error.error['code']==expected_code,error.error)
                    record['refusals'].append({'case':label,'expected_code':expected_code,'error':error.error,
                        'scope':'protocol error observed; missing-copy domain code unspecified' if expected_code is None else 'specified fixture refusal'})
                    return error.error
                raise AssertionError({'check':label,'unexpected_success':result})
            try:
                peer.initialize();record['result']=action(peer,expect,refused);record['status']='passed'
            except Exception as error:record.update(status='failed',error=repr(error))
            finally:
                record['diagnostics']=peer.close()
                (args.output/(name+'-wire.json')).write_text(json.dumps(peer.trace,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(record,ensure_ascii=False),flush=True)

    def setup(peer):
        sender=peer.open('file-result-sender');receiver=peer.open('file-result-receiver');foreign=peer.open('file-result-foreign')
        peer.inbox(receiver,inbox_schema)
        data={'읽은-문서.txt':'Manifest bytes fixture 한글 α\n"quote" and \\ slash\n'.encode('utf-8'),
              'binary.bin':bytes(range(256))+b'\x00\xff\r\n'}
        plan=UploadPlan.snapshot('ref:'+receiver['ref'],'v6-file-result','Explicit local file-result fixture',
            [{'name':name,'data':value,'source_version':'호출자-label-α' if name.endswith('.txt') else None} for name,value in data.items()])
        prepared=peer.prepare_files(sender,plan).result
        for reference in prepared['references']:validate_schema(reference,schema,'fileReference')
        sent=peer.operation(sender,'xsm_send',target=plan.target,request_id=plan.request_id,text=plan.text,
                            manifest_id=prepared['manifest_id'],wake='never')
        if sent['send']['status']!='stored':raise AssertionError({'setup_send':sent})
        packet=peer.inbox(receiver,inbox_schema)
        if len(packet['claims'])!=1 or packet['claims'][0]['id']!=plan.request_id:raise AssertionError({'setup_inbox':packet})
        return sender,receiver,foreign,plan,data,prepared,sent,packet

    def owned_forms(peer,expect,refused):
        sender,receiver,foreign,plan,data,prepared,sent,packet=setup(peer)
        carrier=packet['items'][0]['files']
        source_reference=next(r for r in prepared['references'] if r['id']==prepared['manifest_id'])
        outgoing=consumer.read_manifest(peer,sender,storage_id=prepared['manifest_id'],manifest_id=prepared['manifest_id'],
            expected_sha256=source_reference['sha256'],version=source_reference['version'],outgoing=True)
        for reference in prepared['references']:consumer.verify_reference(reference,outgoing['manifest'])
        incoming=consumer.read_manifest(peer,receiver,storage_id=carrier['storage_id'],manifest_id=carrier['manifest_id'],
            expected_sha256=carrier['sha256'],version=carrier['version'])
        expect('outgoing digest independently verified against frozen preparation',outgoing['sha256']==source_reference['sha256'])
        expect('received digest independently verified against bound inbox metadata',incoming['sha256']==carrier['sha256'])
        expect('incoming and outgoing exact preimage bytes match',incoming['preimage']==outgoing['preimage'])
        expect('complete manifest values including owner are retained',json_equal(incoming['manifest'],outgoing['manifest']))
        expect('all fields except top-level sha256 are compared',set(incoming['parsed_preimage'])==set(incoming['manifest'])-{'sha256'})
        expect('Unicode is consumed from supplied exact UTF-8 bytes','호출자-label-α'.encode('utf-8') in incoming['preimage'])
        manifest=incoming['manifest']
        expect('source request binding matches actual fixture',manifest['binding']['request_id']==plan.request_id)
        expect('manifest aggregate size matches supplied bytes',manifest['size']==sum(map(len,data.values())))
        expect('each named copy is present',set(entry['original_name'] for entry in manifest['files'])==set(data))
        expected_carrier=[{k:entry[k] for k in ('id','name','size','sha256')} for entry in manifest['files']]
        expect('claim-bound file metadata matches full manifest',carrier['files']==expected_carrier)
        expect('manifest result has no entry or canonical discriminator','entry_id' not in incoming['ordinary'] and 'canonical_format' not in incoming['ordinary'])
        expect('canonical result is distinct from entry and manifest','manifest' not in incoming['canonical'] and 'entry_id' not in incoming['canonical'])
        for reference in sent['materials']['references']:
            consumer.verify_reference(reference,manifest)
        expect('manifest references bind id/version/size/digest',sent['materials']['references']==prepared['references'])
        reads=[]
        for direction,session,storage_id,flag,verified in [('incoming',receiver,carrier['storage_id'],False,incoming),
                                                         ('outgoing',sender,prepared['manifest_id'],True,outgoing)]:
            for entry in verified['manifest']['files']:
                content=consumer.read_entry(peer,session,storage_id=storage_id,metadata=entry,outgoing=flag)
                expected=data[entry['original_name']]
                expect(direction+' exact entry bytes '+entry['original_name'],content['data']==expected)
                expect(direction+' entry result kind '+entry['original_name'],'canonical_format' not in content['result'] and 'manifest' not in content['result'])
                if entry['original_name'].endswith('.txt'):
                    text=consumer.read_entry(peer,session,storage_id=storage_id,metadata=entry,outgoing=flag,encoding='text')
                    expect(direction+' UTF-8 text bytes '+entry['original_name'],text['data']==expected)
                reads.append({'direction':direction,'entry_id':entry['id'],'size':len(content['data']),
                              'sha256':hashlib.sha256(content['data']).hexdigest()})
        again=peer.operation(receiver,'xsm_files',storage_id=carrier['storage_id'],manifest_bytes=True)
        expect('byte lookup is stable without reserialization',again['content']==incoming['canonical']['content'])
        current=peer.inbox(receiver,inbox_schema,message_ids=[plan.request_id])
        expect('all file forms leave original claim unconsumed',current['claims']==packet['claims'])
        ack=peer.operation(receiver,'xsm_ack',tokens=[packet['claims'][0]['token']])
        expect('explicit fixture ACK follows intended reads',ack['acked']==[plan.request_id])
        return {'manifest':manifest,'parsed_preimage':incoming['parsed_preimage'],'preimage_length':len(incoming['preimage']),
                'independent_sha256':incoming['sha256'],'received_storage_id':carrier['storage_id'],
                'outgoing_storage_id':prepared['manifest_id'],'entry_reads':reads,
                'owner_scope':'original manifest owner label retained; local copy read authority tested separately'}

    def owners_and_failures(peer,expect,refused):
        sender,receiver,foreign,plan,data,prepared,sent,packet=setup(peer)
        carrier=packet['items'][0]['files'];entry=carrier['files'][0]
        # The same original owner label must not authorize reading a receiver copy.
        incoming=peer.operation(receiver,'xsm_files',storage_id=carrier['storage_id'])
        outgoing=peer.operation(sender,'xsm_files',storage_id=prepared['manifest_id'],outgoing=True)
        validate_schema(incoming,schema);validate_schema(outgoing,schema)
        expect('original owner label identical across independently owned copies',incoming['manifest']['owner']==outgoing['manifest']['owner'])
        for label,caller,storage,flag,file_id in [
            ('foreign received',foreign,carrier['storage_id'],False,entry['id']),
            ('foreign outgoing',foreign,prepared['manifest_id'],True,outgoing['manifest']['files'][0]['id']),
            ('sender received copy',sender,carrier['storage_id'],False,entry['id']),
            ('receiver outgoing source',receiver,prepared['manifest_id'],True,outgoing['manifest']['files'][0]['id'])]:
            for kind,extra in [('manifest',{}),('canonical',{'manifest_bytes':True}),('entry',{'entry_id':file_id,'encoding':'base64'})]:
                refused(label+' '+kind,caller,dict(storage_id=storage,outgoing=flag,**extra))
        base={'storage_id':carrier['storage_id']}
        for label,change in [('unknown storage',{'storage_id':'0'*32}),
            ('unknown entry',{'entry_id':'0'*32}),('entry plus manifest_bytes',{'entry_id':entry['id'],'manifest_bytes':True}),
            ('manifest_bytes wrong type',{'manifest_bytes':'true'}),('unsupported encoding',{'encoding':'rot13'}),
            ('outgoing wrong type',{'outgoing':'true'}),('unknown path parameter',{'path':'untrusted-label-not-a-source'})]:
            arguments=dict(base,**change)
            refused(label,receiver,arguments,expected_code=None if label in ('unknown storage','unknown entry') else -32602)
        current=peer.inbox(receiver,inbox_schema,message_ids=[plan.request_id])
        expect('refusals neither acknowledge nor change claim',current['claims']==packet['claims'])
        verified=consumer.read_manifest(peer,receiver,storage_id=carrier['storage_id'],manifest_id=carrier['manifest_id'],expected_sha256=carrier['sha256'])
        expect('authorized byte lookup still works after refusals',verified['sha256']==carrier['sha256'])
        # The negative-case fixture closes without pretending it consumed the copied entries.
        # Its outstanding claim is not automatically ACKed by this helper.
        return {'manifest_owner_label':verified['manifest']['owner'],'copy_storage_id':carrier['storage_id'],
                'claim_remains_unacked':True,'policy':'owner label is data, not local copy authority'}

    scenario('owned-three-forms',owned_forms)
    scenario('owner-and-errors',owners_and_failures)
    summary={'public_checker':public_summary,'own_scenarios':scenarios,'own_passed':sum(s['status']=='passed' for s in scenarios),
             'own_failed':sum(s['status']=='failed' for s in scenarios),'own_checkpoints':sum(len(s['checks']) for s in scenarios),
             'not_run':['server copy corruption/storage edits or OS source reads','real expiry, parent expiry evidence, clock changes',
                        'models, external network/agents, actual UI','time-based completion-token retention (not promised by public contract)']}
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 1 if public['status']!='passed' or summary['own_failed'] else 0

if __name__=='__main__':raise SystemExit(main())
