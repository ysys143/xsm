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
parser.add_argument('--interrupt-frontend',action='store_true',help='Kill the owned frontend after native provider entry and recover by read-only status')
parser.add_argument('--crowded-profile',action='store_true',help='Seed 101 empty native sessions and verify an older owned context outside the default page')
parser.add_argument('--queued-native',action='store_true',help='Hold an independent native run so the owned target waits before provider execution')
parser.add_argument('--before-admission',action='store_true',help='Inject cancellation after durable bind but before native model admission')
parser.add_argument('--cancel',action='store_true',help='Cancel an exact running native request against the blocking provider fixture')
parser.add_argument('--lose-cancel-confirmation',action='store_true',help='Inject private confirmation loss and reconcile retained native stop evidence')
options=parser.parse_args()
if options.lose_cancel_confirmation and not (options.cancel or options.before_admission):parser.error('--lose-cancel-confirmation requires --cancel or --before-admission')
if options.queued_native and not options.cancel:parser.error('--queued-native requires --cancel')
if options.interrupt_frontend and (options.cancel or options.before_admission):parser.error('--interrupt-frontend is a separate recovery mode')
if not options.native_cli.is_absolute() or not options.node.is_absolute():parser.error('absolute native CLI and Node paths required')
if json.loads((options.native_cli.parent/'package.json').read_text()).get('version')!='2026.10.9':parser.error('OpenClaw2026.10.9 package required')
root=Path(tempfile.mkdtemp(prefix='xsm-openclaw-owned-create-')).resolve();out=options.output.absolute();out.mkdir(parents=True,exist_ok=False)
for name in ('home','state','workspace'):(root/name).mkdir()
with socket.socket() as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
import importlib.util
spec=importlib.util.spec_from_file_location('fixture',repo/'scripts/probe-opencode-protocol.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
assistant=helper.AssistantFixture(out)
config={'gateway':{'mode':'local','bind':'loopback','port':port,'auth':{'mode':'token','token':secrets.token_hex(32)}},'agents':{'defaults':{'workspace':str(root/'workspace'),'heartbeat':{'every':'0m'}}},'cron':{'enabled':False},'plugins':{'enabled':False}}
if options.queued_native:config['agents']['defaults']['maxConcurrent']=1
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
import threading,concurrent.futures
blocking=threading.Event();entered=threading.Event();release=threading.Event();external_blocker=threading.Event();external_entries=[]
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
 if external_blocker.is_set() and not rows:external_entries.append(time.monotonic())
 else:report['preProviderBindingObservations'].append(len(valid)==1 and all(valid))
 save()
 if blocking.is_set():entered.set();release.wait(45)
 try:return original_post(handler)
 except (BrokenPipeError,ConnectionResetError):pass
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
 first=run('first')
 if options.crowded_profile:
  seed=root/'seed-empty-sessions.mjs'
  seed.write_text("""import {readFileSync} from 'node:fs';import {createRequire} from 'node:module';import {pathToFileURL} from 'node:url';
const require=createRequire(process.argv[2]+'/package.json');
const {GatewayClient}=await import(pathToFileURL(require.resolve('openclaw/plugin-sdk/gateway-runtime')).href);
const config=JSON.parse(readFileSync(process.env.OPENCLAW_CONFIG_PATH,'utf8'));let client;
const ready=new Promise((resolve,reject)=>{client=new GatewayClient({url:'ws://127.0.0.1:'+config.gateway.port,
 token:config.gateway.auth.token,clientName:'gateway-client',clientDisplayName:'XSM isolated empty-session fixture',
 clientVersion:'0.0.0',mode:'backend',role:'operator',scopes:['operator.admin'],
 onHelloOk:resolve,onConnectError:()=>reject(new Error('native seed connection refused'))});});
const timer=setTimeout(()=>{client.stop();process.exitCode=1;},60000);
try {client.start();await ready;let count=0;
 for(;count<101;count++){const r=await client.request('sessions.create',{agentId:'main',cwd:process.argv[3],message:''});
 if(r.ok!==true || r.runStarted!==false)throw Error('empty native session unexpectedly started');}
 console.log(JSON.stringify({created:count}));
} catch {console.error('native empty-session fixture failed');process.exitCode=1;}
finally {clearTimeout(timer);client.stop();}
""")
  seeded=subprocess.run([str(options.node),str(seed),str(options.native_cli.parent),str(root/'workspace')],env=env,cwd=root/'workspace',capture_output=True,text=True,timeout=90)
  (out/'empty-session-seed.stdout').write_text(seeded.stdout);(out/'empty-session-seed.stderr').write_text(seeded.stderr)
  check('101 empty native sessions seeded without model execution',seeded.returncode==0 and json.loads(seeded.stdout)['created']==101)
  lookup=NativeRpc(str(options.node),str(options.native_cli),cwd=str(root/'workspace'),env=env)
  old_id=first['result']['native_session_id']
  resolved=lookup('sessions.resolve',worker_session.resolution_params(old_id,'main'))
  default_page=lookup('sessions.list',{})
  check('older native context is outside actual default page',default_page.get('hasMore') is True and all(row.get('sessionId')!=old_id for row in default_page['sessions']))
  try:worker_session.resolved_locator(resolved,default_page,old_id,'main',str(root/'workspace'))
  except worker_session.NativeSessionError:check('legacy first-page-only lookup reproduces failure',True)
  else:raise AssertionError('legacy lookup unexpectedly found truncated context')
  report['defaultPageEvidence']={'count':default_page.get('count'),'limitApplied':default_page.get('limitApplied'),'hasMore':default_page.get('hasMore')}
 second=run('second');separate=run('separate',work='separate-work')
 check('same work resumed exact native conversation',first['result']['native_session_id']==second['result']['native_session_id'])
 check('separate work allocated another native conversation',first['result']['native_session_id']!=separate['result']['native_session_id'])
 before=(out/'assistant-fixture.jsonl').read_text().splitlines()
 replay=run('first')
 check('request replay retained reply ID',replay['reply_id']==first['reply_id'])
 check('request replay made no provider call',(out/'assistant-fixture.jsonl').read_text().splitlines()==before)
 check('provider saw durable exact live child binding',len(report['preProviderBindingObservations'])==3 and all(report['preProviderBindingObservations']))
 check('logical worker indexes exact native IDs',set(workers.load('native-openclaw')['owned_sessions'])=={first['result']['native_session_id'],separate['result']['native_session_id']})
 report['providerFixtureRequests']=len(before)
 if options.interrupt_frontend:
  blocking.set();interrupted_text='Explicit interrupted frontend task.'
  with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
   future=pool.submit(workers.run_owned,'native-openclaw',owner,interrupted_text,
      work_context='interrupted-work',request_id='interrupted',
      reply_sender=lambda worker,row:workers.publish_owned(worker,row,wake=False))
   try:
    check('interrupted task actually entered native provider',entered.wait(20))
    current=workers.owned_status('native-openclaw',owner,'interrupted');child=current['child']
    check('only exact owned child is selected for interruption',identity.lstart(child['pid'])==child['lstart'])
    os.killpg(child['pid'],signal.SIGKILL)
    unknown=future.result(timeout=10)
   except BaseException:release.set();raise
  check('frontend death retains unknown effects and occupied slot',unknown['status']=='unknown' and unknown['slot_occupied'] is True and unknown['result'] is None)
  from integrations.openclaw.worker_cli import output_records
  bound,final=output_records(Path(unknown['child']['stdout']).read_text())
  check('actual bound record survives without final stdout',bound is not None and final is None and bound['locator']['native_session_id']==unknown['native_binding']['native_session_id'])
  pending=workers.reconcile_owned('native-openclaw',owner,'interrupted',reply_sender=lambda worker,row:workers.publish_owned(worker,row,wake=False))
  check('native task still running does not manufacture result',pending['status']=='unknown' and pending['result'] is None and pending['slot_occupied'] is True)
  check('pending reconciliation does not start another native task',len(report['preProviderBindingObservations'])==4)
  release.set();deadline=time.monotonic()+20
  while True:
   recovered=workers.reconcile_owned('native-openclaw',owner,'interrupted',reply_sender=lambda worker,row:workers.publish_owned(worker,row,wake=False))
   if recovered['status'] in ('sent','reply-stored'):break
   if time.monotonic()>deadline:
    (out/'interrupted-unrecovered.json').write_text(json.dumps(recovered,indent=2)+'\n')
    raise TimeoutError('native interrupted frontend recovery')
   time.sleep(.1)
  check('native host receipt recovers actual answer',recovered['result']['body']=='Explicit assistant fixture; no model inference.')
  check('native recovery retains original context identity',recovered['result']['native_session_id']==unknown['native_binding']['native_session_id'])
  check('native recovery preserves nonzero child exit',recovered['child']['returncode']==-signal.SIGKILL and recovered['result']['execution']['returncode']==-signal.SIGKILL)
  check('native status query provenance is retained',recovered['result']['execution']['recovered_from']=='native-host-status' and recovered['result']['native_evidence']['source']=='native-agent.wait')
  check('native recovery releases slot without declaring task success',recovered['slot_occupied'] is False and recovered['result']['outcome'] is None)
  replay=workers.run_owned('native-openclaw',owner,interrupted_text,work_context='interrupted-work',request_id='interrupted',reply_sender=lambda worker,row:workers.publish_owned(worker,row,wake=False))
  check('recovered request replay retains exact reply ID',replay['reply_id']==recovered['reply_id'])
  check('native host recovery and replay perform no inference resubmission',len(report['preProviderBindingObservations'])==4)
  (out/'interrupted-journal.json').write_text(json.dumps(recovered,indent=2)+'\n')
  report['frontendRecovery']=recovered['result']['execution'];report['providerHttpEntries']=len(report['preProviderBindingObservations'])

 if options.before_admission:
  from xsm import owned_requests
  original_bind=owned_requests.bind_native_context
  pre_original_confirm=owned_requests.confirm_native_stop
  if options.lose_cancel_confirmation:
   def pre_lost_confirm(*args,**kwargs):raise OSError('explicit pre-admission confirmation loss fixture')
   owned_requests.confirm_native_stop=pre_lost_confirm
  def cancel_after_binding(owner_arg,request_id,token,native_id):
   result=original_bind(owner_arg,request_id,token,native_id)
   if request_id=='before-admission':workers.cancel_owned('native-openclaw',owner,'before-admission')
   return result
  owned_requests.bind_native_context=cancel_after_binding
  try:
   before_admission=workers.run_owned('native-openclaw',owner,'Must not reach native model.',
      work_context='pre-admission-work',request_id='before-admission',
      reply_sender=lambda worker,row:workers.publish_owned(worker,row,wake=False))
  finally:
   owned_requests.bind_native_context=original_bind
   owned_requests.confirm_native_stop=pre_original_confirm
  if options.lose_cancel_confirmation:
   check('unstarted child with lost confirmation retains uncertainty',before_admission['cancellation']['native_state']=='unverified' and before_admission['slot_occupied'] is True)
   before_admission=workers.reconcile_owned('native-openclaw',owner,'before-admission')
   check('unstarted exact child output recovers native stop',before_admission['cancellation'].get('recovered_from')=='native-output')
  check('pre-admission cancel retains unknown task effects',before_admission['status']=='unknown' and before_admission['result'] is None and before_admission['reply_id'] is None)
  check('pre-admission cancellation confirms stopped native child',before_admission['cancellation']['native_state']=='stopped' and before_admission['slot_occupied'] is False)
  check('pre-admission cancel performs no provider call',(out/'assistant-fixture.jsonl').read_text().splitlines()==before)
  from integrations.openclaw.worker_cli import parse_cancellation
  output=Path(before_admission['child']['stdout']).read_text()
  evidence=parse_cancellation(output,before_admission['context'],agent_id='main',cwd=str(root/'workspace'))
  check('actual child emits strictly validated unstarted marker',evidence['native_evidence'].get('native_not_started') is True)
  check('unstarted child return code observed',before_admission['child']['returncode']==(1 if options.lose_cancel_confirmation else 130))
  (out/'pre-admission-journal.json').write_text(json.dumps(before_admission,indent=2)+'\n')
  report['preAdmissionCancellation']=before_admission['cancellation']

 if options.cancel:
  from xsm import owned_requests
  original_confirm=owned_requests.confirm_native_stop
  if options.lose_cancel_confirmation:
   def lost_confirm(*args,**kwargs):raise OSError('explicit lost private confirmation fixture')
   owned_requests.confirm_native_stop=lost_confirm
  blocking.set()
  blocker_rpc=None;blocker_locator=None;blocker_run=None
  if options.queued_native:
   blocker_rpc=NativeRpc(str(options.node),str(options.native_cli),cwd=str(root/'workspace'),env=env)
   blocker_created=blocker_rpc('sessions.create',worker_session.creation_params('main',str(root/'workspace')))
   blocker_locator=worker_session.created_locator(blocker_created,'main',str(root/'workspace'))
   external_blocker.set()
   blocker_run=blocker_rpc('agent',worker_session.agent_params(blocker_locator,'Explicit native queue holder.','fixture-native-queue-holder'))
   check('independent native queue holder entered provider',entered.wait(20) and len(external_entries)==1)
   external_blocker.clear();entered.clear()
  with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
   future=pool.submit(workers.run_owned,'native-openclaw',owner,'Blocking native cancellation fixture.',
      work_context='cancel-work',request_id='cancel',reply_sender=lambda worker,row:workers.publish_owned(worker,row,wake=False))
   try:
    if options.queued_native:
     deadline=time.monotonic()+20
     while True:
      candidate=workers.owned_status('native-openclaw',owner,'cancel')
      binding=candidate.get('native_binding',{})
      listing=blocker_rpc('sessions.list',{})
      target_rows=[row for row in listing.get('sessions',[]) if row.get('sessionId')==binding.get('native_session_id')]
      if len(target_rows)==1 and target_rows[0].get('hasActiveRun') is True:break
      if time.monotonic()>deadline:
       (out/'queue-before-cancel.json').write_text(json.dumps({'request':candidate,'native':listing},indent=2)+'\n')
       raise TimeoutError('native target was not observed in admitted queue')
      time.sleep(.1)
     check('owned target admitted while no provider request starts',len(report['preProviderBindingObservations'])==3 and not entered.is_set())
    else:check('native cancellation target entered provider',entered.wait(20))
    intruder=registry.upsert('codex',str(root/'intruder'),'different-native-sender',os.getpid(),str(root/'workspace'))
    try:workers.cancel_owned('native-openclaw',intruder,'cancel')
    except (workers.WorkerError,owned_requests.OwnedError):check('different sender cannot cancel native request',True)
    else:raise AssertionError('foreign sender cancellation accepted')
    started=time.monotonic()
    intent=workers.cancel_owned('native-openclaw',owner,'cancel')
    check('provider advertises exact native cancellation',intent['cancellation']['native_supported'] is True)
    check('intent is not a native stop',intent['cancellation']['native_state']=='unverified')
    stopped=future.result(timeout=35)
    report['nativeCancelSeconds']=round(time.monotonic()-started,3)
   except BaseException:
    release.set();raise
  owned_requests.confirm_native_stop=original_confirm
  check('stopped native turn does not create task result',stopped['status']=='unknown' and stopped['result'] is None and stopped['reply_id'] is None)
  if options.lose_cancel_confirmation:
   check('lost private confirmation retains native uncertainty',stopped['cancellation']['native_state']=='unverified' and stopped['slot_occupied'] is True)
   count=len(report['preProviderBindingObservations'])
   stopped=workers.reconcile_owned('native-openclaw',owner,'cancel')
   check('retained exact native evidence recovers stop',stopped['cancellation']['recovered_from']=='native-output')
   check('reconciliation does not execute another turn',len(report['preProviderBindingObservations'])==count)
  check('native stop separately confirmed',stopped['cancellation']['native_state']=='stopped')
  check('native stopped child releases occupied slot',stopped['slot_occupied'] is False)
  check('actual stopped child return code retained',stopped['child']['returncode'] in (1,130))
  expected_entries=3 if options.queued_native else 4
  check('cancel path preserves exact durable child binding',len(report['preProviderBindingObservations'])==expected_entries and all(report['preProviderBindingObservations']))
  if options.queued_native:
   from integrations.openclaw.worker_cli import final_frame
   stopped_output=final_frame(Path(stopped['child']['stdout']).read_text())
   check('native queue stop explicitly reports provider not started',stopped_output['terminal'].get('providerStarted') is False and stopped_output['stop_observation'].get('native_provider_not_started') is True)
   other=blocker_rpc('agent.wait',{'runId':blocker_run['runId'],'timeoutMs':100})
   check('cancelling queued task leaves independent native run active',other.get('status')=='timeout' and other.get('stopReason') is None)
   blocker_rpc('chat.abort',worker_session.cancellation_params(blocker_locator,blocker_run['runId']))
   report['nativeQueueHolderHttpEntries']=len(external_entries)
  (out/'cancel-journal.json').write_text(json.dumps(stopped,indent=2)+'\n')
  report['cancellation']=stopped['cancellation'];report['providerHttpEntries']=len(report['preProviderBindingObservations'])
  release.set()

 report['status']='passed'
except BaseException as error:
 report.update(status='failed',failure_type=type(error).__name__,failure=str(error));save()
finally:
 release.set()
 if process and process.poll() is None:
  os.killpg(process.pid,signal.SIGTERM)
  try:process.wait(timeout=10)
  except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
 assistant.close();log.close();report['gatewayStopped']=process is not None and process.poll() is not None;save();print(json.dumps(report))
raise SystemExit(0 if report['status']=='passed' else 1)
