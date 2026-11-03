#!/usr/bin/env python3
"""Pinned native registered-plugin embedded-run target fence; explicit model0 fixture."""
import json,os,secrets,signal,socket,subprocess,tempfile,time
from pathlib import Path
import sys
repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo))
from integrations.openclaw import worker_session
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--native-cli',type=Path,required=True)
parser.add_argument('--node',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--guarded-admission',action='store_true')
options=parser.parse_args()
if not options.native_cli.is_absolute() or not options.node.is_absolute():parser.error('absolute native CLI and Node paths required')
if json.loads((options.native_cli.parent/'package.json').read_text()).get('version')!='2026.10.9':parser.error('OpenClaw2026.10.9 package required')
root=Path(tempfile.mkdtemp(prefix='xsm-openclaw-wake-spi-')).resolve();out=options.output.absolute();out.mkdir(parents=True,exist_ok=False)
for name in ('home','state','workspace','xsm'):(root/name).mkdir()
bootstrap_env={k:os.environ[k] for k in ('PATH','LANG','TMPDIR') if k in os.environ}
bootstrap_env.update(HOME=str(root/'home'),XSM_HOME=str(root/'xsm'))
os.environ.clear();os.environ.update(bootstrap_env)
with socket.socket() as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
import importlib.util
spec=importlib.util.spec_from_file_location('fixture',repo/'scripts/probe-opencode-protocol.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
assistant=helper.AssistantFixture(out)
config={'gateway':{'mode':'local','bind':'loopback','port':port,'auth':{'mode':'token','token':secrets.token_hex(32)}},'agents':{'defaults':{'workspace':str(root/'workspace'),'heartbeat':{'every':'0m'}}},'cron':{'enabled':False},'plugins':{'enabled':False}}
config['agents']['defaults']['model']={'primary':'xsm-fixture/fixture','fallbacks':[]}
config['models']={'providers':{'xsm-fixture':{'api':'openai-completions','baseUrl':'http://127.0.0.1:'+str(assistant.server.server_port)+'/v1','apiKey':'explicit-no-network-fixture','agentRuntime':{'id':'openclaw'},'models':[{'id':'fixture','name':'fixture','reasoning':False,'input':['text'],'contextWindow':32000,'maxTokens':1000,'cost':{'input':0,'output':0,'cacheRead':0,'cacheWrite':0}}]}}}
config['plugins']={'enabled':True,'allow':['xsm-wake-spi'],'entries':{'xsm-wake-spi':{'enabled':True}}}
path=root/'state/openclaw.json';path.write_text(json.dumps(config));path.chmod(0o600)
env={k:os.environ[k] for k in ('PATH','LANG','TMPDIR') if k in os.environ};env.update(HOME=str(root/'home'),XSM_HOME=str(root/'xsm'),OPENCLAW_STATE_DIR=str(root/'state'),OPENCLAW_CONFIG_PATH=str(path),OPENCLAW_NO_RESPAWN='1')
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
def backend_call(method,params,timeout=50):
 return subprocess.run([str(options.node),str(backend),str(options.native_cli.parent),method,json.dumps(params)],cwd=root/'workspace',env=env,capture_output=True,text=True,timeout=timeout)

plugin=root/'state/extensions/xsm-wake-spi';plugin.mkdir(parents=True)
(plugin/'openclaw.plugin.json').write_text(json.dumps(dict(id='xsm-wake-spi',name='XSM isolated wake SPI',
 activation={'onStartup':True},configSchema={'type':'object','properties':{},'additionalProperties':False})))
(plugin/'index.mjs').write_text(r"""import {appendFileSync} from 'node:fs';
export default {id:'xsm-wake-spi',register(api) {
 const cancelled=new AbortController();
 api.lifecycle.registerRuntimeLifecycle({id:'wake-spi',dispose:async()=>cancelled.abort()});
 api.registerGatewayMethod('xsmWakeSpi.run',async({params:p,respond})=>{
  const session=api.runtime.agent.session;
  const storePath=session.resolveStorePath(api.config.session?.store,{agentId:'main'});
  const scope={storePath,agentId:'main',sessionKey:p.sessionKey,readConsistency:'latest'};
  const before=session.getSessionEntry(scope);
  if(before?.sessionId!==p.sessionId) {respond(true,{rejected:true,stage:'fixture-target'});return;}
  let persisted=false,matched=false,revisionSame=false,runSignal;
  const execute=async signal=>{
   runSignal=signal;
   if(p.guarded){
    const current=session.getSessionEntry(scope);
    if(current?.sessionId!==p.sessionId||current?.lifecycleRevision!==p.expectedRevision)
     throw new Error('Captured plugin target revision changed before execution');
    if(p.pauseBeforeRun){
     appendFileSync(process.env.XSM_SPI_EVENTS,JSON.stringify({event:'guard-ready',runId:p.runId})+'\n');
     if(!signal.aborted)await new Promise(resolve=>signal.addEventListener('abort',resolve,{once:true}));
     appendFileSync(process.env.XSM_SPI_EVENTS,JSON.stringify({event:'native-call-after-interrupt',runId:p.runId})+'\n');
    }
   }
   return await api.runtime.agent.runEmbeddedAgent({
    config:api.config,workspaceDir:api.config.agents.defaults.workspace,
    agentId:'main',sessionId:p.sessionId,sessionKey:p.sessionKey,runId:p.runId,
    sessionTarget:{agentId:'main',sessionId:p.sessionId,sessionKey:p.sessionKey,storePath,
      expectedLifecycleRevision:p.expectedRevision},
    prompt:p.message,transcriptPrompt:p.message,timeoutMs:10000,
    provider:'xsm-fixture',model:'fixture',trigger:'manual',initialTurnTainted:true,
    inputProvenance:{kind:'inter_session',sourceTool:'xsm-wake-spi',sourceChannel:'xsm'},
    abortSignal:signal,
    onUserMessagePersisted:message=>{
     persisted=true;matched=JSON.stringify(message).includes(p.message);
     const current=session.getSessionEntry(scope);revisionSame=current?.lifecycleRevision===p.expectedRevision;
     appendFileSync(process.env.XSM_SPI_EVENTS,JSON.stringify({event:'persisted',runId:p.runId,
       matched,revisionSame,sessionSame:current?.sessionId===p.sessionId})+'\n');
    }
   });
  };
  try {
   const result=p.guarded?await session.runWithWorkAdmission({...scope,signal:cancelled.signal},execute):await execute(cancelled.signal);
   respond(true,{rejected:false,persisted,matched,revisionSame,
     metaKeys:Object.keys(result.meta??{}),errorKind:result.meta?.error?.kind??null});
  }catch(error){respond(true,{rejected:true,persisted,matched,revisionSame,
    stage:p.guarded?'guarded':'native',targetFailure:/lifecycle|revision|changed/i.test(String(error?.message)),errorType:error?.name,
    signalAborted:runSignal?.aborted===true,rootSignalAborted:cancelled.signal.aborted});}
 },{scope:'operator.admin'});
}};
""")
events=out/'events.jsonl';env['XSM_SPI_EVENTS']=str(events)
original_post=assistant.server.RequestHandlerClass.do_POST
def observed_post(handler):
 with events.open('a') as stream:stream.write(json.dumps({'event':'provider'})+'\n')
 return original_post(handler)
assistant.server.RequestHandlerClass.do_POST=observed_post
report=dict(status='starting',root=str(root),modelCalls=0,checks=[],guardedAdmission=options.guarded_admission,
 scope='actual isolated registered plugin and embedded run SPI; scripted local provider, no XSM delivery binding or real UI/service/model')
def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
def check(name,value):
 if not value:raise AssertionError(name)
 report['checks'].append(name);save()
def rpc(name,params):
 r=backend_call(name,params);stem=name.replace('.','-')+'-'+str(len(report['checks']))
 (out/(stem+'.stdout')).write_text(r.stdout);(out/(stem+'.stderr')).write_text(r.stderr)
 if r.returncode:raise RuntimeError('native RPC refused '+name)
 return worker_session.decode_reply(r.stdout)
def event_rows():return [json.loads(line) for line in events.read_text().splitlines()] if events.exists() else []
log=(out/'gateway.log').open('w');process=None;race_process=None
try:
 syntax=subprocess.run([str(options.node),'--check',str(plugin/'index.mjs')],capture_output=True,text=True)
 (out/'plugin-syntax.stderr').write_text(syntax.stderr)
 check('generated native plugin syntax valid',syntax.returncode==0)
 process=subprocess.Popen(command+['gateway','run'],cwd=root/'workspace',env=env,stdout=log,stderr=log,start_new_session=True)
 deadline=time.monotonic()+45
 while True:
  if process.poll() is not None:raise RuntimeError('native gateway exited')
  with socket.socket() as test:
   if test.connect_ex(('127.0.0.1',port))==0:break
  if time.monotonic()>deadline:raise TimeoutError('native gateway startup')
  time.sleep(.1)
 rpc('health',{})
 created=rpc('sessions.create',worker_session.creation_params('main',str(root/'workspace')))
 locator=worker_session.created_locator(created,'main',str(root/'workspace'))
 report['locator']=locator
 check('actual existing native session created',bool(locator['native_lifecycle_revision']))
 params=dict(sessionId=locator['native_session_id'],sessionKey=locator['native_session_key'],
  expectedRevision='deliberately-stale',runId='spi-stale-'+secrets.token_hex(5),message='XSM_SPI_STALE',guarded=options.guarded_admission)
 stale=rpc('xsmWakeSpi.run',params);report['stale']=stale;save()
 check(('guarded path rejects stale snapshot before native execution' if options.guarded_admission else
  'native stale revision refuses before persistence or provider'),stale.get('rejected') is True and
  stale.get('stage')==('guarded' if options.guarded_admission else 'native') and stale.get('targetFailure') is True and not stale.get('persisted') and not event_rows())
 params.update(expectedRevision=locator['native_lifecycle_revision'],runId='spi-valid-'+secrets.token_hex(5),message='XSM_SPI_VALID')
 valid=rpc('xsmWakeSpi.run',params);report['valid']=valid;report['events']=event_rows();save()
 check('actual plugin SDK run persists exact current native target',not valid.get('rejected') and valid.get('persisted') and valid.get('matched') and valid.get('revisionSame'))
 rows=event_rows();kinds=[row['event'] for row in rows]
 check('native persistence callback precedes actual provider request','persisted' in kinds and 'provider' in kinds and kinds.index('persisted')<kinds.index('provider'))
 check('callback readback retains exact native SID',all(row.get('sessionSame') for row in rows if row['event']=='persisted'))
 if options.guarded_admission:
  before_providers=sum(row['event']=='provider' for row in event_rows())
  params.update(runId='spi-reset-'+secrets.token_hex(5),message='XSM_SPI_RESET_RACE',pauseBeforeRun=True)
  race_process=subprocess.Popen([str(options.node),str(backend),str(options.native_cli.parent),'xsmWakeSpi.run',json.dumps(params)],
   cwd=root/'workspace',env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  deadline=time.monotonic()+10
  while not any(row.get('event')=='guard-ready' and row.get('runId')==params['runId'] for row in event_rows()):
   if race_process.poll() is not None:raise RuntimeError('native guarded race returned before barrier')
   if time.monotonic()>deadline:raise TimeoutError('native admission barrier')
   time.sleep(.02)
  report['reset']=rpc('sessions.reset',{'key':locator['native_session_key'],'agentId':'main','reason':'reset'})
  stdout,stderr=race_process.communicate(timeout=20)
  (out/'race.stdout').write_text(stdout);(out/'race.stderr').write_text(stderr)
  if race_process.returncode:raise RuntimeError('native race RPC failed')
  race=worker_session.decode_reply(stdout);report['race']=race;save()
  check('real reset interrupts native admission after target check',race.get('rejected') is True and
   race.get('signalAborted') is True and race.get('rootSignalAborted') is False)
  check('interrupted native SDK call reaches neither persistence nor provider',not race.get('persisted') and
   sum(row['event']=='provider' for row in event_rows())==before_providers and
   any(row['event']=='native-call-after-interrupt' for row in event_rows()))
 report['status']='passed'
except BaseException as error:report.update(status='failed',failureType=type(error).__name__,failure=str(error))
finally:
 if race_process is not None and race_process.poll() is None:
  race_process.terminate()
  try:race_process.communicate(timeout=5)
  except subprocess.TimeoutExpired:race_process.kill();race_process.communicate()
 if process and process.poll() is None:
  os.killpg(process.pid,signal.SIGTERM)
  try:process.wait(timeout=10)
  except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
 assistant.close();report['gatewayStopped']=process is not None and process.poll() is not None
 report['events']=event_rows();log.close();save()
 print(json.dumps({key:report.get(key) for key in ('status','checks','failure','gatewayStopped','stale','valid')}))
raise SystemExit(0 if report['status']=='passed' else 1)
