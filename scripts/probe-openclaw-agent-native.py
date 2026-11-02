#!/usr/bin/env python3
"""Pinned native backend admission and terminal receipts; explicit model0 fixture."""
import json,os,secrets,signal,socket,subprocess,tempfile,time
from pathlib import Path
import sys
repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo))
from integrations.openclaw import worker_session
from xsm.native_worker_control import WorkerControl,WorkerControlClient
import argparse
parser=argparse.ArgumentParser(description='Pinned OpenClaw native backend run, exact identity checks, local model0 fixture.')
parser.add_argument('--native-cli',type=Path,required=True)
parser.add_argument('--node',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
options=parser.parse_args()
if not options.native_cli.is_absolute() or not options.node.is_absolute():parser.error('absolute native CLI and Node paths required')
if json.loads((options.native_cli.parent/'package.json').read_text()).get('version')!='2026.10.9':parser.error('OpenClaw2026.10.9 package required')
root=Path(tempfile.mkdtemp(prefix='xsm-openclaw-owned-create-')).resolve();out=options.output.absolute();out.mkdir(parents=True,exist_ok=False)
for name in ('home','state','workspace'):(root/name).mkdir()
with socket.socket() as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
import importlib.util
spec=importlib.util.spec_from_file_location('fixture',repo/'scripts/probe-opencode-protocol.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
assistant=helper.AssistantFixture(out)
config={'gateway':{'mode':'local','bind':'loopback','port':port,'auth':{'mode':'token','token':secrets.token_hex(32)}},'agents':{'defaults':{'workspace':str(root/'workspace'),'heartbeat':{'every':'0m'}}},'cron':{'enabled':False},'plugins':{'enabled':False}}
config['agents']['defaults']['model']={'primary':'xsm-fixture/fixture','fallbacks':[]}
config['models']={'providers':{'xsm-fixture':{'api':'openai-completions','baseUrl':'http://127.0.0.1:'+str(assistant.server.server_port)+'/v1','apiKey':'explicit-no-network-fixture','agentRuntime':{'id':'openclaw'},'models':[{'id':'fixture','name':'fixture','reasoning':False,'input':['text'],'contextWindow':32000,'maxTokens':1000,'cost':{'input':0,'output':0,'cacheRead':0,'cacheWrite':0}}]}}}
path=root/'state/openclaw.json';path.write_text(json.dumps(config));path.chmod(0o600)
env={k:os.environ[k] for k in ('PATH','LANG','TMPDIR') if k in os.environ};env.update(HOME=str(root/'home'),OPENCLAW_STATE_DIR=str(root/'state'),OPENCLAW_CONFIG_PATH=str(path),OPENCLAW_NO_RESPAWN='1')
command=[str(options.node),str(options.native_cli)]
backend=root/'backend.mjs'
backend.write_text("""import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
const {createRequire}=await import('node:module');
const require=createRequire(process.argv[2]+'/package.json');
const {GatewayClient}=await import(pathToFileURL(require.resolve('openclaw/plugin-sdk/gateway-runtime')).href);
const config=JSON.parse(readFileSync(process.env.OPENCLAW_CONFIG_PATH,'utf8'));
let client;
const connected=new Promise((resolve,reject)=>{
 client=new GatewayClient({url:'ws://127.0.0.1:'+config.gateway.port,
 token:config.gateway.auth.token,clientName:'gateway-client',
 clientDisplayName:'XSM isolated native backend probe',clientVersion:'0.0.0',
 mode:'backend',role:'operator',scopes:['operator.admin'],
 onHelloOk:resolve,onConnectError:()=>reject(new Error('native backend connect refused'))});
});
const deadline=setTimeout(()=>{client.stop();process.exitCode=1;},20000);
try {client.start();await connected;
 const result=await client.request(process.argv[3],JSON.parse(process.argv[4]));
 console.log(JSON.stringify(result));
} catch(error) {console.error(JSON.stringify({nativeError:true,expectedSessionChanged:/changed (while starting expected work|before expected work could start)/.test(String(error?.message))}));process.exitCode=1;}
finally {clearTimeout(deadline);client.stop();}
""")
def backend_call(method,params,timeout=30):
 return subprocess.run([str(options.node),str(backend),str(options.native_cli.parent),method,json.dumps(params)],cwd=root/'workspace',env=env,capture_output=True,text=True,timeout=timeout)
report={'status':'starting','root':str(root),'modelCalls':0,'scope':'actual native gateway agent turn; explicit scripted provider, no LLM inference'}
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
   params=worker_session.agent_params(resumed,'Return the explicit fixture reply.','fixture-native-run')
   assert params['expectedExistingSessionId']==created['sessionId'] and params['expectedExistingSessionLifecycleRevision']==created['entry']['lifecycleRevision']
   report['exactResumeIdentityAndRevision']=True
   (out/'validated-run-params.json').write_text(json.dumps(params,indent=2)+'\n')
   stale=dict(params,expectedExistingSessionLifecycleRevision='intentionally-stale-revision',idempotencyKey='fixture-stale-revision')
   refused=backend_call('agent',stale)
   (out/'stale-agent.stdout').write_text(refused.stdout);(out/'stale-agent.stderr').write_text(refused.stderr)
   if refused.returncode==0:raise RuntimeError('stale native revision was admitted')
   refusal=json.loads(refused.stderr.strip().splitlines()[-1])
   if refusal.get('expectedSessionChanged') is not True:raise RuntimeError('stale native refusal was not an identity check')
   if (out/'assistant-fixture.jsonl').exists():raise RuntimeError('stale native revision reached provider')
   report['staleRevisionRefusedBeforeProvider']=True;save()
   run=backend_call('agent',params)
   (out/'agent.stdout').write_text(run.stdout);(out/'agent.stderr').write_text(run.stderr)
   if run.returncode:raise RuntimeError('native agent admission failed')
   admitted=worker_session.decode_reply(run.stdout);run_id=worker_session.accepted_run(admitted,locator,params['idempotencyKey']);report['admission']=admitted;save()
   waited=backend_call('agent.wait',{'runId':admitted['runId'],'timeoutMs':15000})
   (out/'agent.wait.stdout').write_text(waited.stdout);(out/'agent.wait.stderr').write_text(waited.stderr)
   if waited.returncode:raise RuntimeError('native agent wait failed')
   report['terminal']=worker_session.decode_reply(waited.stdout)
   worker_session.completed_run(report['terminal'],locator,run_id)
   report['actualAgentCompleted']=True
   resume_params=worker_session.agent_params(resumed,'Return the explicit fixture reply again.','fixture-native-resume')
   resumed_run=backend_call('agent',resume_params)
   (out/'resume-agent.stdout').write_text(resumed_run.stdout);(out/'resume-agent.stderr').write_text(resumed_run.stderr)
   if resumed_run.returncode:raise RuntimeError('native same-session resume failed')
   resume_admission=worker_session.decode_reply(resumed_run.stdout)
   resume_id=worker_session.accepted_run(resume_admission,resumed,resume_params['idempotencyKey'])
   resume_wait=backend_call('agent.wait',{'runId':resume_id,'timeoutMs':15000})
   (out/'resume-agent.wait.stdout').write_text(resume_wait.stdout);(out/'resume-agent.wait.stderr').write_text(resume_wait.stderr)
   if resume_wait.returncode:raise RuntimeError('native same-session resume wait failed')
   resume_terminal=worker_session.decode_reply(resume_wait.stdout)
   worker_session.completed_run(resume_terminal,resumed,resume_id)
   report['resumeAdmission']=resume_admission;report['resumeTerminal']=resume_terminal
   report['sameNativeSessionResumed']=True
   report['providerFixtureRequests']=len((out/'assistant-fixture.jsonl').read_text().splitlines()) if (out/'assistant-fixture.jsonl').exists() else 0

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
 assistant.close()
 report['gatewayStopped']=process is not None and process.poll() is not None;log.close();save();print(json.dumps(report))

raise SystemExit(0 if report['status']=='passed' else 1)
