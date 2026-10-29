"""One condition. SSH bootstrap closes before process deny/preflight/data-plane."""
import importlib.util,json,os,shlex,shutil,socket,subprocess,sys,tempfile,time
from pathlib import Path
BASE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('no_ssh_lib',BASE/'no-ssh-native-lib.py');L=importlib.util.module_from_spec(s);s.loader.exec_module(L);C=L.C
ROOT=Path(tempfile.mkdtemp(prefix='p11-C-no-ssh-local-',dir='/private/tmp'));ROOT.chmod(0o700);(ROOT/'code').mkdir(mode=0o700)
FILES=('C-fixture-lib.py','C-native-base.py','no-ssh-native-lib.py','no-ssh-native-peer.py')
for n in FILES:shutil.copyfile(BASE/n,ROOT/'code'/n)
shutil.copyfile(Path.home()/'.reason/bin/reason-network',ROOT/'reason-network');(ROOT/'reason-network').chmod(0o700)
out={'root':str(ROOT),'scope':'C 0.12.10 bootstrap-complete, controlled-process TCP22 denied data-plane; not D12 selection','engine_sha256':C.ENGINE_SHA,'passed':False,'native_model_count':0,'ssh_calls_in_measurement':0,'global_policy_changed':False,'started_at':time.time()};node=None
L.note(ROOT,'result.json',out)
try:
 node=L.Node(ROOT,'local','/Users/jaesolshin/.codex-3');out['engine']=node.start();out['endpoint']=node.endpoint_hash();out['create']=node.create();out['registration']=node.register()
 ticket=node.capability();capsha=C.sha(ticket)
 bootstrap=r'''
import hashlib,json,os,pathlib,subprocess,sys,tempfile,time
header=json.loads(sys.stdin.buffer.readline());binary=sys.stdin.buffer.read();assert hashlib.sha256(binary).hexdigest()==header['engine_sha256']
root=pathlib.Path(tempfile.mkdtemp(prefix='p11-C-no-ssh-peer-',dir='/private/tmp'));root.chmod(0o700);(root/'code').mkdir(mode=0o700)
for name,text in header['files'].items():
 assert name in ('C-fixture-lib.py','C-native-base.py','no-ssh-native-lib.py','no-ssh-native-peer.py')
 p=root/'code'/name;p.write_text(text);p.chmod(0o600)
p=root/'reason-network';p.write_bytes(binary);p.chmod(0o700)
with open(root/'helper.stdout','w') as out,open(root/'helper.stderr','w') as err:
 child=subprocess.Popen(['/usr/bin/python3','-u',str(root/'code/no-ssh-native-peer.py'),str(root)],stdin=subprocess.PIPE,stdout=out,stderr=err,start_new_session=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
 child.stdin.write((json.dumps({'ticket':header.pop('ticket')})+'\n').encode());child.stdin.close()
 deadline=time.monotonic()+50
 while time.monotonic()<deadline:
  if (root/'ready.json').exists():print(json.dumps({'root':str(root),'ready':json.loads((root/'ready.json').read_text()),'helper_pid':child.pid}),flush=True);break
  if child.poll() is not None:raise RuntimeError('helper exited before readiness')
  time.sleep(.1)
 else:raise TimeoutError('bootstrap readiness')
'''
 payload=(json.dumps({'files':{n:(BASE/n).read_text() for n in FILES},'engine_sha256':C.ENGINE_SHA,'ticket':ticket})+'\n').encode()+(ROOT/'reason-network').read_bytes();ticket=None
 ssh=['/usr/bin/ssh']+L.SSH_OPTIONS+['jaesol-macmini','/usr/bin/python3 -c '+shlex.quote(bootstrap)]
 result=subprocess.run(ssh,input=payload,capture_output=True,timeout=65);payload=None
 out['bootstrap_ssh_exit']=result.returncode;out['all_owned_ssh_closed_at']=time.time()
 if result.returncode:raise RuntimeError('bootstrap SSH failed; no measurement')
 peer=json.loads(result.stdout);out['peer_root']=peer['root'];out['peer_bootstrap']=peer['ready'];out['capability']={'sha256':capsha,'channel':'memory -> SSH stdin -> detached helper stdin -> engine private IPC','raw_file_log_argv':False}
 if out['create']['team_id_sha256']!=peer['ready']['join']['team_id_sha256'] or capsha!=peer['ready']['join']['capability_sha256']:raise RuntimeError('private join mismatch')
 out['restriction']=L.deny_current();out['preflight']=L.probes('100.77.24.16');out['ssh_calls_in_restricted_preflight']=2
 deadline=time.monotonic()+100;ready=None
 while time.monotonic()<deadline:
  for m in node.inbox():
   if m.get('from')=='p11-c-peer/qa-peer' and m.get('body','').startswith(C.TASK+' READY '):ready=json.loads(m['body'].split(' READY ',1)[1]);node.ack([m['id']]);break
  if ready:break
  time.sleep(.2)
 if not ready:raise TimeoutError('peer no-SSH readiness absent')
 out['peer_restricted_ready']=ready;out['who_before']=node.who();out['team_before']=node.team()
 if out['team_before']['member_count']!=2 or ready['team']['member_count']!=2:raise RuntimeError('private two-node membership mismatch')
 if len(out['who_before']['sessions'])!=2 or len(ready['who']['sessions'])!=2:raise RuntimeError('two controlled registrations not visible')
 out['measurement_start_at']=time.time();L.note(ROOT,'result.json',out)
 body=('Request marker: '+C.TASK+'; phase: first. Review the claim 2+2=5. Return JSON with request_id, phase, claim_valid, corrected_sum, and a counterexample in one short sentence. Compute honestly; do not use any tools.')
 sent=node.send('p11-c-peer/qa-peer',body);rid=sent['ids'][0];out['request_id']=rid;out['request_sha256']=C.sha(body);reply=None;peer_final=None;deadline=time.monotonic()+220
 while time.monotonic()<deadline:
  for m in node.inbox():
   b=m.get('body','')
   if m.get('from')!='p11-c-peer/qa-peer':continue
   if b.startswith(C.TASK+' FAIL '):raise RuntimeError('peer reported failure; no retry')
   if b.startswith(C.TASK+' RESULT '):peer_final=json.loads(b.split(' RESULT ',1)[1]);node.ack([m['id']])
   elif m.get('reply_to')==rid:reply=m
  if reply and peer_final:break
  time.sleep(.15)
 if not reply or not peer_final:raise TimeoutError('engine-only native roundtrip absent')
 answer=json.loads(reply['body']);out['measurement_end_at']=time.time();out['reply_id']=reply['id'];out['reply_to']=reply['reply_to'];out['reply_sha256']=C.sha(reply['body']);out['answer']=answer;out['peer_native']=peer_final;out['native_model_count']=peer_final['native_attempts'];out['who_after']=node.who();out['team_after']=node.team();node.ack([reply['id']])
 native=peer_final['native'];out['passed']=(out['native_model_count']==1 and native['actual_native_call'] and native['received_body_sha256']==out['request_sha256'] and native['request_engine_id_sha256']==C.sha(rid) and C.sha(reply['id']) in native['reply_engine_ids_sha256'] and native['answer_sha256']==out['reply_sha256'] and answer['corrected_sum']==4 and answer['claim_valid'] is False and reply['reply_to']==rid)
except BaseException as e:out['failure']=C.safe_error(e)
finally:
 out.setdefault('measurement_end_at',time.time());out['cleanup']={}
 if node:
  try:out['cleanup']['local']=node.cleanup()
  except BaseException as e:out['cleanup']['error']=C.safe_error(e)
 out['controller_exiting_at']=time.time();L.note(ROOT,'result.json',out)
 print(json.dumps({'root':str(ROOT),'peer_root':out.get('peer_root'),'passed':out['passed'],'native_model_count':out['native_model_count'],'failure':out.get('failure')},ensure_ascii=False),flush=True)
