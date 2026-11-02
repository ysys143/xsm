"""Own black-box slot accounting diagnostic, no storage/implementation reads."""
import argparse
import json
import tempfile
from pathlib import Path
from participant_v5 import Peer, UploadPlan, RpcError, server_command


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-executable',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    command=server_command(args.server_executable)
    reports=[]
    for split in (False,True):
        for complete in (False,True):
            label=('two-owners' if split else 'one-owner')+('-one-completed' if complete else '-all-active')
            record={'case':label};reports.append(record)
            with tempfile.TemporaryDirectory(prefix='v5-slot-probe-') as cwd:
                peer=Peer(command,cwd=cwd)
                def observe(callback):
                    try:return {'result':callback()}
                    except RpcError as error:return {'error':error.error}
                try:
                    peer.initialize();a=peer.open('slot-owner-a');b=peer.open('slot-owner-b');receiver=peer.open('slot-receiver')
                    peer.operation(receiver,'xsm_inbox')
                    values=[]
                    for i in range(16):
                        owner=b if split and i%2 else a
                        snapshot=UploadPlan.snapshot('ref:'+receiver['ref'],'probe-'+str(i),'probe '+str(i),[{'name':'tiny','data':b'x'}])
                        values.append((owner,snapshot,peer.upload_open(owner,snapshot)))
                    if complete:
                        peer.upload_write(a,values[0][2]['upload'],0,0,b'x')
                        record['first_commit']=peer.upload_commit(a,values[0][2]['upload'])
                        record['completion_replay_before_overflow']=observe(lambda:peer.upload_commit(a,values[0][2]['upload']))
                    overflow=UploadPlan.snapshot('ref:'+receiver['ref'],'probe-overflow','overflow',[{'name':'tiny','data':b'x'}])
                    record['overflow']=observe(lambda:peer.upload_open(a,overflow))
                    retained=[]
                    for owner,snapshot,opened in values:
                        if complete and opened['upload']==values[0][2]['upload']:
                            result=observe(lambda owner=owner,opened=opened:peer.upload_commit(owner,opened['upload']))
                        else:
                            result=observe(lambda owner=owner,opened=opened:peer.upload_write(owner,opened['upload'],0,0,b''))
                        retained.append({'request_id':snapshot.request_id,'token':opened['upload'],'probe':result})
                    record['retained_handles']=retained
                    record['retained_original_count']=sum('result' in r['probe'] for r in retained)
                    record['observable_handle_count']=record['retained_original_count']+('result' in record['overflow'])
                    record['frozen_status_after_pressure']=peer.upload_status(a,values[0][1].request_id) if complete else None
                    record['status']='passed' if record['observable_handle_count']<=16 else 'failed'
                except Exception as error:record.update(status='failed',error=repr(error))
                finally:
                    record['diagnostics']=peer.close()
                    (args.output/(label+'-wire.json')).write_text(json.dumps(peer.trace,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(json.dumps(record,ensure_ascii=False),flush=True)
    with (args.output/'summary.json').open('x',encoding='utf-8') as handle:
        json.dump(reports,handle,ensure_ascii=False,indent=2)
    return 1 if any(r['status']=='failed' for r in reports) else 0

if __name__=='__main__':raise SystemExit(main())
