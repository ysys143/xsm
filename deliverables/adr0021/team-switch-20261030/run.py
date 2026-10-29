from pathlib import Path
import copy, datetime, hashlib, json, os, socket, subprocess, sys, time
frozen=Path('/var/folders/hw/9m3g7fvn4_l3rp2y473km9sm0000gn/T/adr21-final-20261030-fx0yt4x3').resolve();sys.path.insert(0,str(frozen))
os.environ['XSM_NET_BINARY']=str(frozen/'native/xsm-net/target/release/xsm-net')
from tests import test_network_service as services
services.CLI_TIMEOUT=45
out=Path(__file__).resolve().parent
case=services.NativeNetworkServiceTests('test_one_time_response_loss_retry_restart_and_different_device_refusal')
record={'scope':'one host, three actual services and Rust QUIC; controlled loss of one real issuer response after actual signed admission','source_manifest_sha256':hashlib.sha256((frozen/'manifest.json').read_bytes()).hexdigest(),'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'completed':False}
nodes=[];joining=None
try:
 case.setUp();nodes=[case.a,case.b]
 old=case.initialize(case.a,'original-team');old_ticket,_=case.invite(case.a);case.join(case.b,old_ticket)
 fault=case.root/'issuer-response-fault';fault.mkdir(mode=0o700)
 (fault/'sitecustomize.py').write_text("import json,os,threading,time\nfrom pathlib import Path\nfrom xsm.network_transport import Sidecar\nfolder=Path(os.environ['XSM_JOIN_FAULT_ROOT']);local=threading.local();handle=Sidecar._handle;respond=Sidecar._respond\nlock=threading.Lock()\ndef observe(value):\n with lock:\n  with (folder/'events.jsonl').open('a') as f:f.write(json.dumps(dict(value,at=time.time()))+'\\n')\ndef observed_handle(self,identifier,origin,body,callback):\n local.op=body.get('op') if isinstance(body,dict) else None;local.origin=origin\n try:return handle(self,identifier,origin,body,callback)\n finally:local.op=None;local.origin=None\ndef fault_respond(self,identifier,body):\n if getattr(local,'op',None)=='join' and body.get('ok') and (folder/'armed').exists():\n  (folder/'armed').rename(folder/'dropped')\n  observe({'event':'dropped-real-join-response','request_id':identifier,'authenticated_origin':local.origin,'ok':True})\n  return\n if getattr(local,'op',None)=='join-status':observe({'event':'real-join-status-response','request_id':identifier,'authenticated_origin':local.origin,'ok':body.get('ok') is True})\n return respond(self,identifier,body)\nSidecar._handle=observed_handle;Sidecar._respond=fault_respond\n")
 c=services.ServiceNode(case,'new-team-root');case.addCleanup(c.cleanup);c.env['PYTHONPATH']=str(fault)+os.pathsep+str(frozen);c.env['XSM_JOIN_FAULT_ROOT']=str(fault);c.start();nodes.append(c)
 new=case.initialize(c,'requested-team');new_ticket,_=case.invite(c,once=True)
 active=case.b.home/'network/active.json';before=active.read_bytes();assert json.loads(before)['network_id']==old
 (fault/'armed').write_text('drop one issuer response')
 args=[sys.executable,'-B','-m','xsm','network','join','--ticket-file',str(new_ticket),'--machine-name',case.b.name]
 with (out/'lost-response-join.stdout').open('wb') as stdout,(out/'lost-response-join.stderr').open('wb') as stderr:
  started=time.monotonic();joining=subprocess.Popen(args,cwd=frozen,env=case.b.env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr)
  deadline=time.monotonic()+8
  while not (fault/'dropped').exists() and time.monotonic()<deadline:time.sleep(.025)
  assert (fault/'dropped').exists(),'real issuer response drop was not observed'
  during=case.b.cli('status');assert during['network']['network_id']==old and active.read_bytes()==before
  assert case.members(c)[case.b.identity]=='active'
  joining.wait(timeout=42);assert joining.returncode==0
  record['lost_response_seconds']=round(time.monotonic()-started,3)
 result=json.loads((out/'lost-response-join.stdout').read_text());case.assert_no_secrets(json.dumps(result));assert result['network']['network_id']==new
 after=case.b.cli('status');assert after['network']['network_id']==new and after['active']
 signed_before=case.state(c);case.join(case.b,new_ticket);assert case.state(c)==signed_before
 case.ping(case.b,c);case.ping(c,case.b)
 wrong=copy.deepcopy(json.loads(old_ticket.read_text()));wrong['network_id']=new
 wrong_path=case.private_ticket('wrong-team-switch',wrong);active_new=active.read_bytes()
 failed=case.join(case.b,wrong_path,success=False);assert active.read_bytes()==active_new
 assert case.b.cli('status')['network']['network_id']==new
 restored=case.join(case.b,old_ticket);assert restored['network']['network_id']==old;case.ping(case.b,case.a)
 case.join(case.b,new_ticket);assert case.b.cli('status')['network']['network_id']==new
 case.a.cli('remove',case.b.identity)
 active_before_refused_restore=active.read_bytes()
 denied_restore=case.join(case.b,old_ticket,success=False)
 assert active.read_bytes()==active_before_refused_restore
 assert case.b.cli('status')['network']['network_id']==new
 case.ping(case.b,c)
 events=[json.loads(line) for line in (fault/'events.jsonl').read_text().splitlines()]
 assert sum(row['event']=='dropped-real-join-response' for row in events)==1
 assert any(row['event']=='real-join-status-response' and row['ok'] for row in events)
 (out/'issuer-response-events.json').write_text(json.dumps(events,indent=2)+'\n')
 record.update(completed=True,old_network_id=old,requested_network_id=new,old_active_during_unknown=True,issuer_admitted_before_response=True,requested_network_readback=True,real_join_status_observed=True,idempotent_retry_unchanged_signed_state=True,failed_switch_code=failed['code'],failed_switch_retained_new=True,return_to_old_succeeded=True,removed_old_team_return_code=denied_restore['code'],removed_old_team_return_failed_without_active_rewrite=True,current_new_team_ping_after_failure=True)
finally:
 if joining is not None and joining.poll() is None:joining.terminate();joining.wait(timeout=4)
 pids=[n.process.pid for n in nodes]+[n.sidecar_pid for n in nodes]
 case.doCleanups();table=services.process_table();remaining=[pid for pid in pids if pid in table]
 record.update(owned_pids=pids,owned_pids_remaining=remaining,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 (out/'results.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n');assert not remaining
print(json.dumps({k:v for k,v in record.items() if not k.endswith('network_id')}))
