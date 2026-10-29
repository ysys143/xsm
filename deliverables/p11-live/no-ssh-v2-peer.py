"""Autonomous peer: receives request only from engine; inherited SSH deny."""
import importlib.util,json,os,sys,time
from pathlib import Path
root=Path(sys.argv[1]);s=importlib.util.spec_from_file_location('no_ssh_lib',root/'code/no-ssh-v2-lib.py');L=importlib.util.module_from_spec(s);s.loader.exec_module(L)
C=L.C;node=None;deadline=time.monotonic()+420;out={'baseline':L.P.baseline(),'scope':'owned peer autonomous engine pull','helper_pid':os.getpid(),'helper_lstart':C.process_start(os.getpid()),'native_attempts':0,'ssh_calls_in_measurement':0}
try:
 packet=json.loads(sys.stdin.readline());ticket=packet.pop('ticket');node=L.Node(root,'peer','/Users/jaesolshin/.codex-3');out['engine']=node.start();out['endpoint']=node.endpoint_hash();out['join']=node.join(ticket);ticket=None;packet=None;out['registration']=node.register();out['team_bootstrap']=node.team();out['who_bootstrap']=node.who();
 end=time.monotonic()+60
 while out['who_bootstrap']['session_count']!=2:
  if time.monotonic()>end:raise TimeoutError('peer two-session who readiness')
  time.sleep(.2);out['who_bootstrap']=node.who()
 L.note(root,'ready.json',out)
 # Bootstrap SSH parent returns as soon as ready is written. No command pipe remains.
 time.sleep(20)
 out['restriction']=L.deny_current();out['preflight']=L.probes('100.123.30.11');out['who_before_measurement']=node.who();out['team_before_measurement']=node.team();L.control_message(node,'READY',{'preflight':out['preflight'],'restriction':out['restriction'],'who':out['who_before_measurement'],'team':out['team_before_measurement']});L.note(root,'restricted.json',out)
 while time.monotonic()<deadline:
  messages=node.inbox();tasks=[m for m in messages if m.get('from')=='p11-c-local/qa-local' and C.TASK in m.get('body','') and '2+2=5' in m.get('body','')]
  if not tasks:time.sleep(.1);continue
  if len(tasks)!=1:raise RuntimeError('not exactly one actual request')
  message=tasks[0];out['measurement_request_seen_at']=time.time();out['request_id']=message['id'];out['request_sha256']=C.sha(message['body']);out['native_attempts']=1;L.note(root,'native-starting.json',out)
  out['RootMetadata_before_native']={'profile':L.PROFILE,'helper':L.P.info(os.getpid()),'engine':L.P.info(node.proc.pid),'kernel_ssh_preflight':out['preflight']}
  out['native']=node.process('first',out['request_sha256']);raw=json.loads((root/'native/first/result.json').read_text());out['actual_native_CID']=raw['native_conversation'];out['native_RootMetadata']=json.loads((root/'native/first/native-root-metadata.json').read_text());out['who_after_reply']=node.who();out['team_after_reply']=node.team();out['measurement_end_at']=time.time();L.control_message(node,'RESULT',out);break
 else:raise TimeoutError('autonomous pull deadline; no SSH fallback')
except BaseException as e:
 out['failure']=C.safe_error(e)
 if node:
  try:L.control_message(node,'FAIL',{'failure':out['failure'],'native_attempts':out['native_attempts']})
  except BaseException:pass
finally:
 if node:
  try:out['cleanup']=node.cleanup()
  except BaseException as e:out['cleanup_error']=C.safe_error(e)
 out['owned_spawns']=L.P.SPAWNS;out['helper_exiting_at']=time.time();L.note(root,'peer-final.json',out)
