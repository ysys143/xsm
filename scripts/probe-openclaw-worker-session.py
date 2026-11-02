#!/usr/bin/env python3
"""Native session allocation before model admission, with isolated gateway state."""
import json,os,secrets,signal,socket,subprocess,tempfile,time
from pathlib import Path
import sys
repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo))
from integrations.openclaw import worker_session
from xsm.native_worker_control import WorkerControl,WorkerControlClient
import argparse
parser=argparse.ArgumentParser(description='Pinned OpenClaw native session creation/resolution and private bind contract; no agent turn.')
parser.add_argument('--native-cli',type=Path,required=True)
parser.add_argument('--node',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
options=parser.parse_args()
if not options.native_cli.is_absolute() or not options.node.is_absolute():parser.error('absolute native CLI and Node paths required')
if json.loads((options.native_cli.parent/'package.json').read_text()).get('version')!='2026.10.9':parser.error('OpenClaw2026.10.9 package required')
root=Path(tempfile.mkdtemp(prefix='xsm-openclaw-owned-create-')).resolve();out=options.output.absolute();out.mkdir(parents=True,exist_ok=False)
for name in ('home','state','workspace'):(root/name).mkdir()
with socket.socket() as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
config={'gateway':{'mode':'local','bind':'loopback','port':port,'auth':{'mode':'token','token':secrets.token_hex(32)}},'agents':{'defaults':{'workspace':str(root/'workspace'),'heartbeat':{'every':'0m'}}},'cron':{'enabled':False},'plugins':{'enabled':False}}
path=root/'state/openclaw.json';path.write_text(json.dumps(config));path.chmod(0o600)
env={k:os.environ[k] for k in ('PATH','LANG','TMPDIR') if k in os.environ};env.update(HOME=str(root/'home'),OPENCLAW_STATE_DIR=str(root/'state'),OPENCLAW_CONFIG_PATH=str(path),OPENCLAW_NO_RESPAWN='1')
command=[str(options.node),str(options.native_cli)]
report={'status':'starting','root':str(root),'modelCalls':0,'scope':'actual pinned native gateway and session creation, no agent turn'}
def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
log=(out/'gateway.log').open('w');process=None
try:
 process=subprocess.Popen(command+['gateway','run'],cwd=root/'workspace',env=env,stdout=log,stderr=log,start_new_session=True)
 deadline=time.monotonic()+45
 while True:
  if process.poll() is not None:raise RuntimeError('native gateway exited')
  with socket.socket() as test:
   if test.connect_ex(('127.0.0.1',port))==0:break
  if time.monotonic()>deadline:raise TimeoutError('native gateway startup')
  time.sleep(.1)
 for name,params in [('health',{}),('sessions.create',worker_session.creation_params('main',str(root/'workspace'))),('sessions.list',{})]:
  r=subprocess.run(command+['gateway','call',name,'--params',json.dumps(params),'--json'],cwd=root/'workspace',env=env,capture_output=True,text=True,timeout=30)
  (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr);report[name+'Exit']=r.returncode;save()
  if r.returncode:raise RuntimeError('native RPC refused '+name)
  if name=='sessions.list':
   resumed=worker_session.resolved_locator(worker_session.decode_reply((out/'sessions.resolve.stdout').read_text()),worker_session.decode_reply(r.stdout),created['sessionId'],'main',str(root/'workspace'))
   assert resumed==locator
   params=worker_session.agent_params(resumed,'must not execute','fixture-not-run')
   assert params['expectedExistingSessionId']==created['sessionId'] and params['expectedExistingSessionLifecycleRevision']==created['entry']['lifecycleRevision']
   report['exactResumeIdentityAndRevision']=True
   (out/'validated-run-params.json').write_text(json.dumps(params,indent=2)+'\n')
  if name=='sessions.create':
   created=worker_session.decode_reply(r.stdout)
   locator=worker_session.created_locator(created,'main',str(root/'workspace'))
   bindings=[];control=WorkerControl(bindings.append);client=WorkerControlClient(os.dup(control.child.fileno()));control.start()
   try:client.bind(locator['native_session_id'])
   finally:client.close();control.close()
   assert bindings==[created['sessionId']];report['actualNativeIDBoundBeforeTurn']=True
   params2=worker_session.resolution_params(created['sessionId'],'main')
   rr=subprocess.run(command+['gateway','call','sessions.resolve','--params',json.dumps(params2),'--json'],cwd=root/'workspace',env=env,capture_output=True,text=True,timeout=30)
   (out/'sessions.resolve.stdout').write_text(rr.stdout);(out/'sessions.resolve.stderr').write_text(rr.stderr);report['resolveExit']=rr.returncode
   if rr.returncode:raise RuntimeError('native resolve refused')
 report['status']='passed'
except BaseException as error:report.update(status='failed',failure_type=type(error).__name__)
finally:
 if process and process.poll() is None:
  os.killpg(process.pid,signal.SIGTERM)
  try:process.wait(timeout=10)
  except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
 report['gatewayStopped']=process is not None and process.poll() is not None;log.close();save();print(json.dumps(report))
