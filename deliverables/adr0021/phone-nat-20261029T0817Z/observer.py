
import hashlib,json,os,runpy,sys,time
from pathlib import Path
root=Path(sys.argv[1]); audit=root/'raw'/'transport.jsonl'
def write(value):
    value['observed_at']=time.time(); value['observer_pid']=os.getpid()
    fd=os.open(audit,os.O_WRONLY|os.O_APPEND|os.O_CREAT,0o600)
    with os.fdopen(fd,'a') as stream: stream.write(json.dumps(value,separators=(',',':'))+'\n')
def digest(body):
    return hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()
from xsm.network_transport import Sidecar
dispatch=Sidecar._dispatch; request=Sidecar.request
def observed_dispatch(self,event):
    dispatch(self,event)
    kind=event.get('event')
    if kind not in ('ready','request','response','path'): return
    record={k:event[k] for k in ('event','id','request_id','origin','endpoint_id','bound_addresses','requested_port','port_fallback','relay_mode','relay_online') if k in event}
    record['native_pid']=self._process.pid
    if 'body' in event:
        record['body_sha256']=digest(event['body'])
        if isinstance(event['body'],dict) and event['body'].get('op') in ('join','join-status','ping','sync'):
            record['application_op']=event['body']['op']
    record['last_transport']=self.last_transport; record['native_transport']=event.get('transport')
    write(record)
def observed_request(self,peer,body,timeout=30):
    write({'event':'outbound-body','target_endpoint_id':peer.get('id'),'application_op':body.get('op'),'body_sha256':digest(body)})
    result=request(self,peer,body,timeout=timeout)
    write({'event':'roundtrip-proof','application_op':body.get('op'),'request_sha256':digest(body),'response_sha256':digest(result.get('body')),'origin':result.get('origin'),'target_endpoint_id':peer.get('id'),'native_transport':result.get('transport')})
    return result
Sidecar._dispatch=observed_dispatch; Sidecar.request=observed_request
sys.argv=['xsm.network','serve']
runpy.run_module('xsm.network',run_name='__main__')
