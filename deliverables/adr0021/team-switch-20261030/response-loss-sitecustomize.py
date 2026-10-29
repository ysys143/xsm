import json,os,threading,time
from pathlib import Path
from xsm.network_transport import Sidecar
folder=Path(os.environ['XSM_JOIN_FAULT_ROOT']);local=threading.local();handle=Sidecar._handle;respond=Sidecar._respond
lock=threading.Lock()
def observe(value):
 with lock:
  with (folder/'events.jsonl').open('a') as f:f.write(json.dumps(dict(value,at=time.time()))+'\n')
def observed_handle(self,identifier,origin,body,callback):
 local.op=body.get('op') if isinstance(body,dict) else None;local.origin=origin
 try:return handle(self,identifier,origin,body,callback)
 finally:local.op=None;local.origin=None
def fault_respond(self,identifier,body):
 if getattr(local,'op',None)=='join' and body.get('ok') and (folder/'armed').exists():
  (folder/'armed').rename(folder/'dropped')
  observe({'event':'dropped-real-join-response','request_id':identifier,'authenticated_origin':local.origin,'ok':True})
  return
 if getattr(local,'op',None)=='join-status':observe({'event':'real-join-status-response','request_id':identifier,'authenticated_origin':local.origin,'ok':body.get('ok') is True})
 return respond(self,identifier,body)
Sidecar._handle=observed_handle;Sidecar._respond=fault_respond
