#!/usr/bin/env python3
"""Validate native owned Pi execution and public cancellation with a loopback fixture, model0."""
import asyncio,hashlib,json,os,sqlite3,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo));sys.path.insert(0,str(repo/'clients/python'))
import argparse
parser=argparse.ArgumentParser(description='Pi1.4.0 native owned lifecycle with an explicit loopback assistant fixture; no LLM or credentials.')
parser.add_argument('--native-cli',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--remove-stopped-service',action='store_true',help='Verify safe metadata removal while retaining unknown effects and native data')
parser.add_argument('--lose-cancel-confirmation',action='store_true',help='Inject a stop-report failure and verify native-output recovery')
options=parser.parse_args()
if not options.native_cli.is_absolute() or not options.native_cli.is_file():parser.error('an existing absolute Pi1.4.0 CLI path is required')
if options.output.exists():parser.error('output must be new; preserve prior evidence')
executable=options.native_cli

root=Path(tempfile.mkdtemp(prefix='xsm-owned-pi-native-')).resolve();root.chmod(0o700);home=root/'home';home.mkdir(mode=0o700);workspace=root/'workspace';workspace.mkdir();profile=root/'pi';profile.mkdir(mode=0o700);state=root/'state';out=options.output.absolute();out.mkdir(exist_ok=False);nonce=os.urandom(4).hex();model='xsm-fixture/fixture'

env={key:os.environ[key] for key in ('PATH','LANG','TMPDIR') if key in os.environ};env.update(HOME=str(home),PI_CODING_AGENT_DIR=str(profile),XDG_DATA_HOME=str(root/'data'),XDG_CACHE_HOME=str(root/'cache'),XSM_PYTHON=sys.executable,XSM_HOME=str(state),XSM_PI=str(executable),PYTHONDONTWRITEBYTECODE='1');os.environ.clear();os.environ.update(env)
import importlib.util
spec=importlib.util.spec_from_file_location('opencode_probe',repo/'scripts/probe-opencode-protocol.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
assistant=module.AssistantFixture(out)
import threading
blocking={'enabled':False};entered=threading.Event();release=threading.Event();http_calls=[]
original_post=assistant.server.RequestHandlerClass.do_POST
def controlled_post(handler):
 if blocking['enabled']:
  http_calls.append(time.monotonic());entered.set();release.wait(20)
 try:original_post(handler)
 except (BrokenPipeError,ConnectionResetError):pass
assistant.server.RequestHandlerClass.do_POST=controlled_post
(profile/'models.json').write_text(json.dumps({'providers':{'xsm-fixture':{'baseUrl':'http://127.0.0.1:'+str(assistant.server.server_port)+'/v1','api':'openai-completions','apiKey':'explicit-no-network-fixture','models':[{'id':'fixture','name':'fixture','reasoning':False,'input':['text'],'contextWindow':32000,'maxTokens':1000,'cost':{'input':0,'output':0,'cacheRead':0,'cacheWrite':0}}]}}}))
(profile/'settings.json').write_text(json.dumps({'defaultProvider':'xsm-fixture','defaultModel':'fixture','compaction':{'enabled':False},'retry':{'enabled':False}}))

report={'status':'starting','scope':'actual public owned journal and Pi1.4.0 native CLI/control; scripted provider, model0','root':str(root),'started_at':time.time(),'checks':[],'served_model':None};
report['lost_confirmation_injected']=options.lose_cancel_confirmation
def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
def check(name,value):
 if not value:raise AssertionError(name)
 report['checks'].append(name);save()
async def main():
 from xsm import host_install
 from xsm_client import XsmClient
 client=None
 try:
  installed=host_install.apply('pi',str(profile));report['runtime_root']=installed['runtime_root'];save()
  command=[sys.executable,'-B','-c',"import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('xsm',run_name='__main__')",str(repo),'protocol','serve','--stdio']
  if options.lose_cancel_confirmation:command[3]="import runpy,sys\nsys.path.insert(0,sys.argv.pop(1))\nfrom xsm import owned_requests\noriginal=owned_requests.confirm_native_stop\ndef confirm(*args,**kwargs):\n if not kwargs.get('readback'):raise OSError('explicit lost-confirmation fixture')\n return original(*args,**kwargs)\nowned_requests.confirm_native_stop=confirm\nrunpy.run_module('xsm',run_name='__main__')\n"
  client=await XsmClient.connect(command,cwd=str(workspace),env=dict(os.environ))
  parent=await client.session_open(runtime='owned-reference',profile='private-owned-probe',conversation=nonce,cwd=str(workspace),capabilities=['messaging','inbox','events'])
  await client.events_subscribe(parent['session'])
  packets=[]
  async def op(name,arguments):
   value=await client.operation_call(parent['session'],name,arguments)
   if isinstance(value.get('incoming'),dict) and value['incoming'].get('claims'):packets.append(value['incoming'])
   return value
  async def read_reply(reply_id,expected):
   packet=None
   for index,value in enumerate(packets):
    if any(claim['id']==reply_id for claim in value.get('claims',[])):
     packet=packets.pop(index);break
   if packet is None:packet=await op('xsm_inbox',{'message_ids':[reply_id]})
   claims=[claim for claim in packet.get('claims',[]) if claim['id']==reply_id]
   check('actual claimed reply read '+reply_id,len(claims)==1 and any(expected in text for text in packet['messages']))
   ack=await op('xsm_ack',{'tokens':[claims[0]['token']]})
   check('actual reply explicitly acknowledged '+reply_id,ack['acked']==[reply_id])

  created=await op('xsm_owned',{'action':'create','name':'native-pi','runtime':'pi','home':str(profile),'model':model})
  check('public operation admits verified native Pi provider',created['runtime']=='pi' and bool(created.get('native_provider')))
  print(json.dumps({'status':'native provider admitted'}),flush=True)
  async def run(request,prompt,work='shared-native'):
   result=await op('xsm_owned',{'action':'run','name':'native-pi','text':prompt,'work_context':work,'request_id':request})
   deadline=time.monotonic()+120
   while result['status'] not in ('sent','reply-stored','unknown','error') and time.monotonic()<deadline:
    await asyncio.sleep(.1);result=await op('xsm_owned',{'action':'status','name':'native-pi','request_id':request})
   report[request+'_status']=result['status'];save()
   if result['status'] not in ('sent','reply-stored'):
    report[request+'_diagnostic']=result.get('send_evidence') or result.get('error') or result.get('unknown_reason');save();raise RuntimeError('native owned run did not publish')
   return result
  expected='Explicit assistant fixture; no model inference.'
  first=await run('first-'+nonce,'Explicit fixture request; do not call any tools.')
  check('actual CLI event answer retained',first['result']['body']==expected)
  await read_reply(first['reply_id'],expected)
  second=await run('second-'+nonce,'Second scripted fixture turn.')
  check('actual native opaque context resumed',second['result']['native_session_id']==first['result']['native_session_id'])
  await read_reply(second['reply_id'],expected)
  separate=await run('separate-'+nonce,'Separate scripted fixture turn.',work='separate-native')
  check('different work context creates another native conversation',separate['result']['native_session_id']!=first['result']['native_session_id'])
  await read_reply(separate['reply_id'],expected)
  from xsm import workers
  check('both native conversations belong to the same logical owned service',set(workers.load('native-pi')['owned_sessions'])=={first['result']['native_session_id'],separate['result']['native_session_id']})
  before=(out/'assistant-fixture.jsonl').read_text().splitlines()
  replay=await run('first-'+nonce,'Explicit fixture request; do not call any tools.')
  check('same request retained exact reply',replay['reply_id']==first['reply_id'])
  check('cached request performs no provider calls',(out/'assistant-fixture.jsonl').read_text().splitlines()==before)
  check('context bound before both native turns',all(row.get('native_binding',{}).get('native_session_id')==first['result']['native_session_id'] for row in (first,second)))
  report['providerFixtureRequests']=len(before)
  blocking['enabled']=True
  cancel_id='cancel-'+nonce
  await op('xsm_owned',{'action':'run','name':'native-pi','text':'Pending explicit provider fixture.','work_context':'cancel-native','request_id':cancel_id})
  check('actual native request reached blocking HTTP fixture',await asyncio.to_thread(entered.wait,15))
  from xsm import owned_requests
  states=[json.loads(p.read_text()) for p in (state/'owned-requests').glob('*.json')]
  saved=[value['requests'][cancel_id] for value in states if cancel_id in value.get('requests',{})]
  check('actual cancel target has one durable native request',len(saved)==1 and bool(saved[0].get('native_binding')))
  original=saved[0]
  from xsm_client import RpcError
  intruder=await client.session_open(runtime='owned-reference',profile='different-profile',conversation=nonce+'-intruder',cwd=str(workspace),capabilities=['messaging','inbox','events'])
  try:await client.operation_call(intruder['session'],'xsm_owned',{'action':'cancel','name':'native-pi','request_id':cancel_id})
  except RpcError:check('different native sender cannot cancel this request',True)
  else:raise AssertionError('foreign cancellation accepted')
  cancel_started=time.monotonic()
  pending=await op('xsm_owned',{'action':'cancel','name':'native-pi','request_id':cancel_id})
  check('admitted provider advertises native cancellation',pending['cancellation']['native_supported'] is True)
  check('intent alone does not claim native stop',pending['cancellation']['native_state']=='unverified')
  if options.lose_cancel_confirmation:
    deadline=time.monotonic()+15
    while True:
     current=await op('xsm_owned',{'action':'status','name':'native-pi','request_id':cancel_id})
     if current['status']=='unknown' and type(current.get('child',{}).get('returncode')) is int:break
     if time.monotonic()>deadline:raise TimeoutError('native CLI exit after lost confirmation')
     await asyncio.sleep(.05)
    (out/'native-cancel-output.jsonl').write_bytes(Path(current['child']['stdout']).read_bytes())
    check('failed confirmation keeps native state unverified',current['cancellation']['native_state']=='unverified' and current['slot_occupied'] is True)
    before=len(http_calls)
    current=await op('xsm_owned',{'action':'reconcile','name':'native-pi','request_id':cancel_id})
    check('native stop recovered from exact retained output',current['cancellation']['native_state']=='stopped' and current['cancellation']['recovered_from']=='native-output')
    check('readback releases only the verified native slot',current['slot_occupied'] is False)
    check('readback does not manufacture task answer',current['status']=='unknown' and current['result'] is None and current['reply_id'] is None)
    check('readback does not run another native request',len(http_calls)==before)
    again=await op('xsm_owned',{'action':'reconcile','name':'native-pi','request_id':cancel_id})
    check('repeated readback preserves same stop evidence',again['cancellation']==current['cancellation'])
  else:
    deadline=time.monotonic()+15
    while True:
     current=await op('xsm_owned',{'action':'status','name':'native-pi','request_id':cancel_id})
     if current.get('cancellation',{}).get('native_state')=='stopped' and type(current.get('child',{}).get('returncode')) is int:break
     if time.monotonic()>deadline:raise TimeoutError('native cancellation confirmation')
     await asyncio.sleep(.05)
    check('actual native aborted settle is recorded',current['cancellation']['status']=='native-stopped' and current['cancellation']['native_session_id']==current['native_binding']['native_session_id'])
    check('cancelled native turn is no invented answer',current['status']=='unknown' and current['result'] is None and current['reply_id'] is None)
  (out/'cancelled-request.json').write_text(json.dumps(current,indent=2)+'\n')
  if options.remove_stopped_service:
   from xsm import workers
   journal_files=list((state/'owned-requests').glob('*.json'))
   before_journals={str(path):(path.read_bytes(),path.stat().st_mtime_ns) for path in journal_files}
   workers.stop('native-pi')
   check('confirmed stopped service metadata removed',workers.load('native-pi') is None)
   retained=await op('xsm_owned',{'action':'status','name':'native-pi','request_id':cancel_id})
   check('unknown cancellation remains readable after removal',retained['status']=='unknown' and retained['worker_record_present'] is False and retained['cancellation']==current['cancellation'])
   check('native profile and original output retained',profile.is_dir() and Path(current['child']['stdout']).is_file())
   check('service removal does not rewrite request journals',all(Path(path).read_bytes()==value[0] and Path(path).stat().st_mtime_ns==value[1] for path,value in before_journals.items()))
  report['cancelHTTPRequests']=len(http_calls);report['cancel_observation_seconds']=round(time.monotonic()-cancel_started,3)
  report['status']='passed'
 except BaseException as error:report.update(status='failed',failure_type=type(error).__name__)
 finally:
  if client:await client.close()
  release.set();assistant.server.shutdown();assistant.server.server_close()
  report['finished_at']=time.time();save();print(json.dumps(report),flush=True)
 return 0 if report['status']=='passed' else 1
raise SystemExit(asyncio.run(main()))
