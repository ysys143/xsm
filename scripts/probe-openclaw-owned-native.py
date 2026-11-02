#!/usr/bin/env python3
"""Pinned native backend admission and terminal receipts; explicit model0 fixture."""
import json,os,secrets,signal,socket,subprocess,tempfile,time
from pathlib import Path
import sys
repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo))
from integrations.openclaw import worker_session, worker_frontend
from integrations.openclaw.worker_transport import NativeRpc
from xsm.native_worker_control import WorkerControl,WorkerControlClient,ControlError
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
env.update(XSM_HOME=str(root/'xsm'),XSM_OPENCLAW=str(options.native_cli),XSM_OPENCLAW_NODE=str(options.node),XSM_PYTHON=sys.executable,PYTHONDONTWRITEBYTECODE='1')
os.environ.clear();os.environ.update(env)
from xsm import host_install,identity,registry,workers
report={'status':'starting','root':str(root),'scope':'actual common owned engine/journal and native OpenClaw gateway; local model0 fixture, no protocol/UI certification','checks':[],'modelCalls':0,'preProviderBindingObservations':[]}
def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
def check(name,value):
 if not value:raise AssertionError(name)
 report['checks'].append(name);save()
original_post=assistant.server.RequestHandlerClass.do_POST
def observed_post(handler):
 rows=[]
 for journal in (root/'xsm/owned-requests').glob('*.json'):
  state=json.loads(journal.read_text())
  rows.extend(row for row in state.get('requests',{}).values() if row.get('state')=='running')
 valid=[]
 for row in rows:
  binding=row.get('native_binding',{});child=row.get('child',{})
  valid.append(bool(binding.get('native_session_id')) and binding.get('child_pid')==child.get('pid')
    and binding.get('child_lstart')==child.get('lstart')==identity.lstart(child.get('pid')))
 report['preProviderBindingObservations'].append(len(valid)==1 and all(valid));save()
 return original_post(handler)
assistant.server.RequestHandlerClass.do_POST=observed_post
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
 installed=host_install.apply('openclaw',str(root/'state'))
 report['runtime_root']=installed['runtime_root'];save()
 owner=registry.upsert('codex',str(root/'owner'),'owned-openclaw-probe',os.getpid(),str(root/'workspace'))
 worker=workers.create_owned('openclaw',caller=owner,name='native-openclaw',home=str(root/'state'))
 check('native provider selected exact roster agent',worker['native_provider']['agent_id']=='main')
 def run(request,work='same-work'):
  value=workers.run_owned('native-openclaw',owner,'Explicit fixture task '+request,work_context=work,request_id=request,
    reply_sender=lambda worker,row:workers.publish_owned(worker,row,wake=False))
  (out/(request+'-journal.json')).write_text(json.dumps(value,indent=2)+'\n')
  check('actual owned result published '+request,value['status'] in ('sent','reply-stored'))
  check('native answer retained '+request,value['result']['body']=='Explicit assistant fixture; no model inference.')
  check('native completion did not invent task outcome '+request,value['result']['outcome'] is None)
  check('private child bound before result '+request,value['native_binding']['native_session_id']==value['result']['native_session_id'])
  return value
 first=run('first');second=run('second');separate=run('separate',work='separate-work')
 check('same work resumed exact native conversation',first['result']['native_session_id']==second['result']['native_session_id'])
 check('separate work allocated another native conversation',first['result']['native_session_id']!=separate['result']['native_session_id'])
 before=(out/'assistant-fixture.jsonl').read_text().splitlines()
 replay=run('first')
 check('request replay retained reply ID',replay['reply_id']==first['reply_id'])
 check('request replay made no provider call',(out/'assistant-fixture.jsonl').read_text().splitlines()==before)
 check('provider saw durable exact live child binding',len(report['preProviderBindingObservations'])==3 and all(report['preProviderBindingObservations']))
 check('logical worker indexes exact native IDs',set(workers.load('native-openclaw')['owned_sessions'])=={first['result']['native_session_id'],separate['result']['native_session_id']})
 report['providerFixtureRequests']=len(before)
 report['status']='passed'
except BaseException as error:
 report.update(status='failed',failure_type=type(error).__name__,failure=str(error));save()
finally:
 if process and process.poll() is None:
  os.killpg(process.pid,signal.SIGTERM)
  try:process.wait(timeout=10)
  except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
 assistant.close();log.close();report['gatewayStopped']=process is not None and process.poll() is not None;save();print(json.dumps(report))
raise SystemExit(0 if report['status']=='passed' else 1)
