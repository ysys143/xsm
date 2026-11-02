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
import asyncio
sys.path.insert(0,str(repo/'clients/python'))
from xsm import host_install
from xsm_client import XsmClient
report={'status':'starting','root':str(root),'scope':'actual public protocol owned operation, native OpenClaw gateway and claimed replies; model0 fixture','checks':[],'modelCalls':0}
def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
def check(name,value):
 if not value:raise AssertionError(name)
 report['checks'].append(name);save()
async def public_roundtrip():
 client=None
 try:
  host_install.apply('openclaw',str(root/'state'))
  server=[sys.executable,'-B','-c',"import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('xsm',run_name='__main__')",str(repo),'protocol','serve','--stdio']
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
 if process and process.poll() is None:
  os.killpg(process.pid,signal.SIGTERM)
  try:process.wait(timeout=10)
  except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
 assistant.close();log.close();report['gatewayStopped']=process is not None and process.poll() is not None;save();print(json.dumps(report))
raise SystemExit(0 if report['status']=='passed' else 1)
