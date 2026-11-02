#!/usr/bin/env python3
"""Public owned operation and exact reply claims against native OpenClaw; model0."""
import json,os,secrets,signal,socket,subprocess,tempfile,time
from pathlib import Path
import sys
repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo))
import argparse
parser=argparse.ArgumentParser(description='Public owned OpenClaw native roundtrip with claimed/ACKed replies; local model0 fixture.')
parser.add_argument('--native-cli',type=Path,required=True)
parser.add_argument('--node',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--cancel',action='store_true',help='Exercise public exact-request cancellation after native provider entry')
parser.add_argument('--lose-cancel-confirmation',action='store_true',help='Inject private stop-report loss in the isolated protocol server and reconcile via public operation')
options=parser.parse_args()
if options.lose_cancel_confirmation and not options.cancel:parser.error('--lose-cancel-confirmation requires --cancel')
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
import asyncio
sys.path.insert(0,str(repo/'clients/python'))
from xsm import host_install
from xsm_client import XsmClient, RpcError
report={'status':'starting','root':str(root),'scope':'actual public protocol owned operation, native OpenClaw gateway and claimed replies; model0 fixture','checks':[],'modelCalls':0}
def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
def check(name,value):
 if not value:raise AssertionError(name)
 report['checks'].append(name);save()
import threading
blocking=threading.Event();entered=threading.Event();release=threading.Event();http_entries=[]
original_post=assistant.server.RequestHandlerClass.do_POST
def observed_post(handler):
 http_entries.append(time.monotonic())
 if blocking.is_set():entered.set();release.wait(45)
 try:return original_post(handler)
 except (BrokenPipeError,ConnectionResetError):pass
assistant.server.RequestHandlerClass.do_POST=observed_post
async def public_roundtrip():
 client=None
 try:
  host_install.apply('openclaw',str(root/'state'))
  server=[sys.executable,'-B','-c',"import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('xsm',run_name='__main__')",str(repo),'protocol','serve','--stdio']
  if options.lose_cancel_confirmation:
   server[3]="import runpy,sys\nsys.path.insert(0,sys.argv.pop(1))\nfrom xsm import owned_requests\noriginal=owned_requests.confirm_native_stop\ndef confirm(*args,**kwargs):\n if not kwargs.get('readback'):raise OSError('explicit private confirmation loss fixture')\n return original(*args,**kwargs)\nowned_requests.confirm_native_stop=confirm\nrunpy.run_module('xsm',run_name='__main__')\n"
  client=await XsmClient.connect(server,cwd=str(root/'workspace'),env=env)
  parent=await client.session_open(runtime='owned-reference',profile='isolated-openclaw-owned',conversation='public-owned-parent',cwd=str(root/'workspace'),capabilities=['messaging','inbox','events'])
  await client.events_subscribe(parent['session'])
  packets=[]
  async def op(name,arguments):
   result=await client.operation_call(parent['session'],name,arguments)
   if isinstance(result.get('incoming'),dict) and result['incoming'].get('claims'):packets.append(result['incoming'])
   return result
  async def read_reply(reply_id):
   packet=None
   for index,value in enumerate(packets):
    if any(claim['id']==reply_id for claim in value.get('claims',[])):
     packet=packets.pop(index);break
   if packet is None:packet=await op('xsm_inbox',{'message_ids':[reply_id]})
   claims=[claim for claim in packet.get('claims',[]) if claim['id']==reply_id]
   check('native reply claimed '+reply_id,len(claims)==1 and any('Explicit assistant fixture; no model inference.' in text for text in packet['messages']))
   ack=await op('xsm_ack',{'tokens':[claims[0]['token']]})
   check('native reply explicitly ACKed '+reply_id,ack['acked']==[reply_id])
  created=await op('xsm_owned',{'action':'create','name':'protocol-openclaw','runtime':'openclaw','home':str(root/'state')})
  check('public create admits OpenClaw provider',created['runtime']=='openclaw' and created['native_provider']['agent_id']=='main')
  async def run(request,work='same'):
   result=await op('xsm_owned',{'action':'run','name':'protocol-openclaw','text':'Explicit fixture task '+request,'work_context':work,'request_id':request})
   deadline=time.monotonic()+90
   while result['status'] not in ('sent','reply-stored','unknown','error'):
    if time.monotonic()>deadline:raise TimeoutError('public owned native execution')
    await asyncio.sleep(.1);result=await op('xsm_owned',{'action':'status','name':'protocol-openclaw','request_id':request})
   (out/(request+'-journal.json')).write_text(json.dumps(result,indent=2)+'\n')
   check('public run retained native reply '+request,result['status'] in ('sent','reply-stored') and result['result']['body']=='Explicit assistant fixture; no model inference.')
   check('public run did not invent task success '+request,result['result']['outcome'] is None)
   return result
  first=await run('first');await read_reply(first['reply_id'])
  second=await run('second');await read_reply(second['reply_id'])
  separate=await run('separate','separate');await read_reply(separate['reply_id'])
  check('public same-work native identity retained',first['result']['native_session_id']==second['result']['native_session_id'])
  check('public separate work native identity differs',first['result']['native_session_id']!=separate['result']['native_session_id'])
  before=(out/'assistant-fixture.jsonl').read_bytes()
  replay=await run('first')
  check('public replay retained exact reply ID',replay['reply_id']==first['reply_id'])
  check('public replay did not execute native model',(out/'assistant-fixture.jsonl').read_bytes()==before)
  report['providerFixtureRequests']=len(before.splitlines())
  if options.cancel:
   blocking.set();cancel_text='Explicit blocked public native task.'
   await op('xsm_owned',{'action':'run','name':'protocol-openclaw','text':cancel_text,'work_context':'public-cancel','request_id':'cancel'})
   check('public cancellation target actually entered native provider',await asyncio.to_thread(entered.wait,20))
   intruder=await client.session_open(runtime='owned-reference',profile='different-public-profile',conversation='intruder',cwd=str(root/'workspace'),capabilities=['messaging','inbox','events'])
   try:await client.operation_call(intruder['session'],'xsm_owned',{'action':'cancel','name':'protocol-openclaw','request_id':'cancel'})
   except RpcError:check('public different sender cancellation refused',True)
   else:raise AssertionError('different public sender could cancel native task')
   started=time.monotonic()
   intent=await op('xsm_owned',{'action':'cancel','name':'protocol-openclaw','request_id':'cancel'})
   check('public cancel advertises native capability',intent['cancellation']['native_supported'] is True)
   check('public intent does not claim native stop',intent['cancellation']['native_state']=='unverified')
   deadline=time.monotonic()+35
   while True:
    stopped=await op('xsm_owned',{'action':'status','name':'protocol-openclaw','request_id':'cancel'})
    if stopped['status']=='unknown' and type(stopped.get('child',{}).get('returncode')) is int:break
    if time.monotonic()>deadline:
     (out/'cancel-timeout.json').write_text(json.dumps(stopped,indent=2)+'\n')
     raise TimeoutError('public native stop observation')
    await asyncio.sleep(.1)
   if options.lose_cancel_confirmation:
    check('public lost confirmation retains occupied unknown request',stopped['cancellation']['native_state']=='unverified' and stopped['slot_occupied'] is True)
    count=len(http_entries)
    stopped=await op('xsm_owned',{'action':'reconcile','name':'protocol-openclaw','request_id':'cancel'})
    check('public reconcile recovers exact native output',stopped['cancellation'].get('recovered_from')=='native-output')
    check('public reconcile performs no native execution',len(http_entries)==count)
   check('public native stop confirmed',stopped['cancellation']['native_state']=='stopped')
   check('public confirmed native stop releases slot',stopped['slot_occupied'] is False)
   check('public native stop does not invent task answer',stopped['status']=='unknown' and stopped['result'] is None and stopped['reply_id'] is None)
   (out/'cancel-journal.json').write_text(json.dumps(stopped,indent=2)+'\n')
   count=len(http_entries)
   repeated=await op('xsm_owned',{'action':'run','name':'protocol-openclaw','text':cancel_text,'work_context':'public-cancel','request_id':'cancel'})
   check('public uncertain request replay remains unknown',repeated['status']=='unknown')
   check('public uncertain replay does not rerun native turn',len(http_entries)==count)
   report['nativeCancelSeconds']=round(time.monotonic()-started,3)
   report['providerHttpEntries']=len(http_entries);report['cancellation']=stopped['cancellation']
   release.set()

 finally:
  if client is not None:await client.close()
log=(out/'gateway.log').open('w');process=None
try:
 process=subprocess.Popen(command+['gateway','run'],cwd=root/'workspace',env=env,stdout=log,stderr=log,start_new_session=True)
 deadline=time.monotonic()+45
 while True:
  with socket.socket() as test:
   if test.connect_ex(('127.0.0.1',port))==0:break
  if process.poll() is not None or time.monotonic()>deadline:raise RuntimeError('native gateway startup')
  time.sleep(.1)
 asyncio.run(public_roundtrip());report['status']='passed'
except BaseException as error:report.update(status='failed',failure_type=type(error).__name__,failure=str(error))
finally:
 release.set()
 if process and process.poll() is None:
  os.killpg(process.pid,signal.SIGTERM)
  try:process.wait(timeout=10)
  except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
 assistant.close();log.close();report['gatewayStopped']=process is not None and process.poll() is not None;save();print(json.dumps(report))
raise SystemExit(0 if report['status']=='passed' else 1)
