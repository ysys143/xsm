#!/usr/bin/env python3
"""Actual installed OpenClaw XSM native wake and FYI; isolated scripted provider."""
import json,os,secrets,signal,socket,subprocess,tempfile,time
from pathlib import Path
import sys
import io, threading
repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo))
from integrations.openclaw import worker_session
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--native-cli',type=Path,required=True)
parser.add_argument('--node',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--reset-race',action='store_true')
options=parser.parse_args()
if not options.native_cli.is_absolute() or not options.node.is_absolute():parser.error('absolute native CLI and Node paths required')
if json.loads((options.native_cli.parent/'package.json').read_text()).get('version')!='2026.10.9':parser.error('OpenClaw2026.10.9 package required')
root=Path(tempfile.mkdtemp(prefix='xsm-openclaw-native-wake-')).resolve();out=options.output.absolute();out.mkdir(parents=True,exist_ok=False)
for name in ('home','state','workspace','xsm'):(root/name).mkdir()
bootstrap_env={k:os.environ[k] for k in ('PATH','LANG','TMPDIR') if k in os.environ}
bootstrap_env.update(HOME=str(root/'home'),XSM_HOME=str(root/'xsm'))
os.environ.clear();os.environ.update(bootstrap_env)
with socket.socket() as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
import importlib.util
spec=importlib.util.spec_from_file_location('fixture',repo/'scripts/probe-opencode-protocol.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
assistant=helper.AssistantFixture(out,warmup_inbox=True)
entered_model=threading.Event();release_model=threading.Event();blocked_marker=None
original_post=assistant.server.RequestHandlerClass.do_POST
def controlled_post(handler):
 data=handler.rfile.read(int(handler.headers['Content-Length']))
 handler.rfile=io.BytesIO(data)
 if blocked_marker and blocked_marker.encode() in data and not entered_model.is_set():
  entered_model.set();release_model.wait(20)
 try:return original_post(handler)
 except (BrokenPipeError,ConnectionResetError):
  if not options.reset_race:raise
assistant.server.RequestHandlerClass.do_POST=controlled_post
config={'gateway':{'mode':'local','bind':'loopback','port':port,'auth':{'mode':'token','token':secrets.token_hex(32)}},'agents':{'defaults':{'workspace':str(root/'workspace'),'heartbeat':{'every':'0m'}}},'cron':{'enabled':False},'plugins':{'enabled':False}}
config['agents']['defaults']['model']={'primary':'xsm-fixture/fixture','fallbacks':[]}
config['models']={'providers':{'xsm-fixture':{'api':'openai-completions','baseUrl':'http://127.0.0.1:'+str(assistant.server.server_port)+'/v1','apiKey':'explicit-no-network-fixture','agentRuntime':{'id':'openclaw'},'models':[{'id':'fixture','name':'fixture','reasoning':False,'input':['text'],'contextWindow':32000,'maxTokens':1000,'cost':{'input':0,'output':0,'cacheRead':0,'cacheWrite':0}}]}}}
config['plugins']={'enabled':True,'allow':['xsm'],'entries':{'xsm':{'enabled':True,'config':{'nativeWake':True},'hooks':{'allowConversationAccess':True,'allowPromptInjection':True}}}}
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

from xsm import host_install,handoff
installation=host_install.apply('openclaw',str(root/'state'))
report=dict(status='starting',root=str(root),runtimeRoot=installation['runtime_root'],modelCalls=0,checks=[],
 scope='actual installed XSM plugin, native gateway, context queue and background wake; scripted provider, no real model/UI/service')
def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
def check(name,value):
 if not value:raise AssertionError(name)
 report['checks'].append(name);save()
def rpc(name,params):
 r=backend_call(name,params);stem=name.replace('.','-')+'-'+str(len(report['checks']))
 (out/(stem+'.stdout')).write_text(r.stdout);(out/(stem+'.stderr')).write_text(r.stderr)
 if r.returncode:raise RuntimeError('native RPC refused '+name)
 return worker_session.decode_reply(r.stdout)
def records():return [json.loads(f.read_text()) for f in (root/'xsm/sessions').glob('*.json')]
def provider_rows():
 f=out/'assistant-fixture.jsonl'
 return [json.loads(line) for line in f.read_text().splitlines()] if f.exists() else []
def tool_results():
 for row in provider_rows():
  for message in row['request'].get('messages',[]):
   if message.get('role')=='tool' and isinstance(message.get('content'),str):
    try:value=json.loads(message['content'])
    except ValueError:continue
    if isinstance(value,dict):yield value
def user_prompt_contains(text):
 return any(message.get('role')=='user' and text in json.dumps(message.get('content',''))
  for row in provider_rows() for message in row['request'].get('messages',[]))
def delivery_reports():
 f=root/'xsm/protocol-delivery.jsonl'
 return [json.loads(line) for line in f.read_text().splitlines()] if f.exists() else []
def natural(locator,label):
 params=worker_session.agent_params(locator,'Run the explicit XSM fixture '+label,'native-'+label)
 admitted=rpc('agent',params);worker_session.accepted_run(admitted,locator,params['idempotencyKey'])
 terminal=rpc('agent.wait',{'runId':params['idempotencyKey'],'timeoutMs':15000})
 worker_session.completed_run(terminal,locator,params['idempotencyKey'])
 return terminal
async def messaging(receiver,locator):
 global blocked_marker
 import asyncio
 from xsm_client import XsmClient
 command=[sys.executable,'-B','-c',"import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('xsm',run_name='__main__')",str(repo),'protocol','serve','--stdio']
 async with await XsmClient.connect(command,cwd=str(root/'workspace'),env=env) as sender:
  me=await sender.session_open(runtime='native-wake-sender',profile='isolated',conversation='sender',cwd=str(root/'workspace'))
  mid='openclaw-wake-'+secrets.token_hex(8);original='XSM_NATIVE_WAKE_'+mid
  await sender.operation_call(me['session'],'xsm_send',dict(target='ref:'+receiver['ref'],text=original,wake='auto',request_id=mid))
  deadline=time.monotonic()+35
  while handoff.status(receiver,mid)['status']!='acknowledged':
   if time.monotonic()>deadline:raise TimeoutError('native peer wake did not ACK')
   await asyncio.sleep(.02)
  check('XSM peer message alone wakes native turn and gets exact ACK',True)
  deadline=time.monotonic()+10
  while not any(row.get('ref')==receiver['ref'] and row.get('activity')=='idle' for row in records()):
   if time.monotonic()>deadline:raise TimeoutError('native wake did not return idle')
   await asyncio.sleep(.02)
  check('background native wake settles to idle',True)
  check('native provider sees complete original as untrusted user context',user_prompt_contains(original))
  check('queue admission is reported separately from explicit ACK',any(item['id']==mid and item['state']=='admitted' for item in delivery_reports()))
  quiet='openclaw-fyi-'+secrets.token_hex(8);quiet_text='XSM_NATIVE_FYI_'+quiet
  before=len(provider_rows())
  await sender.operation_call(me['session'],'xsm_send',dict(target='ref:'+receiver['ref'],text=quiet_text,wake='never',request_id=quiet))
  await asyncio.sleep(.3)
  check('strict FYI does not start a provider request in idle window',len(provider_rows())==before)
  await asyncio.to_thread(natural,locator,'natural-fyi')
  check('first actual natural turn consumes strict FYI',handoff.status(receiver,quiet)['status']=='acknowledged')
  check('FYI first natural provider input has full original and nonce context',user_prompt_contains(quiet_text) and user_prompt_contains('[XSM peer context '))
  check('exact native model input observation reports FYI admission',any(item['id']==quiet and item['state']=='admitted' for item in delivery_reports()))
  check('background wake honors the configured model route',all(row['request'].get('model')=='fixture' for row in provider_rows()))
  if options.reset_race:
   cancelled_id='openclaw-reset-'+secrets.token_hex(8);blocked_marker='XSM_RESET_PENDING_'+cancelled_id
   await sender.operation_call(me['session'],'xsm_send',dict(target='ref:'+receiver['ref'],text=blocked_marker,wake='auto',request_id=cancelled_id))
   check('actual native wake reaches blocked provider before reset',await asyncio.to_thread(entered_model.wait,10))
   reset=await asyncio.to_thread(rpc,'sessions.reset',{'key':locator['native_session_key'],'agentId':'main','reason':'reset'})
   report['reset']=reset;release_model.set()
   check('real reset changes native execution revision',reset.get('ok') is True and
    reset.get('entry',{}).get('lifecycleRevision')!=locator['native_lifecycle_revision'])
   deadline=time.monotonic()+10
   while not any(row.get('ref')==receiver['ref'] and row.get('ended_at') for row in records()):
    if time.monotonic()>deadline:raise TimeoutError('reset did not end old XSM participation')
    await asyncio.sleep(.02)
   retained=handoff.status(receiver,cancelled_id)
   check('reset retains the unacknowledged original',retained['status'] not in ('acknowledged','not-found') and retained['message']['body']==blocked_marker)
   next_locator=dict(locator,native_session_id=reset['entry']['sessionId'],native_lifecycle_revision=reset['entry']['lifecycleRevision'])
   await asyncio.to_thread(natural,next_locator,'after-reset')
   next_peers=[row for row in records() if row.get('runtime')=='openclaw' and not row.get('ended_at')]
   same_native_id=reset['entry']['sessionId']==locator['native_session_id']
   check('native reset replaces XSM participation generation',len(next_peers)==1 and
    next_peers[0]['protocol_generation']!=receiver['protocol_generation'])
   check('XSM address follows actual native conversation identity',
    (next_peers[0]['ref']==receiver['ref']) is same_native_id)
   new_inputs=[row['request'] for row in provider_rows() if any(message.get('role')=='user' and
    'after-reset' in json.dumps(message.get('content','')) for message in row['request'].get('messages',[]))]
   if same_native_id:
    check('same conversation can consume retained original only in new generation',
     handoff.status(next_peers[0],cancelled_id)['status']=='acknowledged')
   else:
    check('reset cannot leak old peer data into the new conversation',bool(new_inputs) and all(blocked_marker not in json.dumps(value) for value in new_inputs))
  report.update(receiverRef=receiver['ref'],messageId=mid,fyiId=quiet,providerRequests=len(provider_rows()))
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
 rpc('health',{})
 created=rpc('sessions.create',worker_session.creation_params('main',str(root/'workspace')))
 locator=worker_session.created_locator(created,'main',str(root/'workspace'));report['locator']=locator
 natural(locator,'warmup')
 check('actual native model calls installed xsm_inbox',assistant.inbox_issued)
 check('actual native tool response returns the protocol inbox contract',any(item.get('tool',{}).get('name')=='xsm_inbox' and
  isinstance(item.get('result',{}).get('details',{}).get('claims'),list) for item in tool_results()))
 peers=[record for record in records() if record.get('runtime')=='openclaw' and not record.get('ended_at')]
 check('native tool context opens exactly one XSM participation',len(peers)==1)
 import asyncio
 asyncio.run(messaging(peers[0],locator))
 report['status']='passed'
except BaseException as error:report.update(status='failed',failureType=type(error).__name__,failure=str(error))
finally:
 release_model.set()
 if process and process.poll() is None:
  process.send_signal(signal.SIGTERM)
  try:process.wait(timeout=10)
  except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
 assistant.close();report['gatewayStopped']=process is not None and process.poll() is not None
 delivery=root/'xsm/protocol-delivery.jsonl'
 if delivery.exists():(out/'protocol-delivery.jsonl').write_bytes(delivery.read_bytes())
 log.close();save();print(json.dumps({key:report.get(key) for key in ('status','checks','failure','gatewayStopped')}))
raise SystemExit(0 if report['status']=='passed' else 1)
