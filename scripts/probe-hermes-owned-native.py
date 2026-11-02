#!/usr/bin/env python3
"""Validate native owned Pi execution and public cancellation with a loopback fixture, model0."""
import asyncio,hashlib,json,os,sqlite3,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo));sys.path.insert(0,str(repo/'clients/python'))
import argparse
parser=argparse.ArgumentParser(description='Hermes0.22.5 native owned lifecycle with an explicit loopback assistant fixture; no LLM or credentials.')
parser.add_argument('--native-cli',type=Path,required=True)
parser.add_argument('--native-source',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--lose-cancel-confirmation',action='store_true',help='Inject a stop-report failure and verify native-output recovery')
options=parser.parse_args()
if not options.native_cli.is_absolute() or not options.native_cli.is_file():parser.error('an existing absolute Hermes0.22.5 CLI path is required')
if options.output.exists():parser.error('output must be new; preserve prior evidence')
executable=options.native_cli;native_python=executable.with_name('python');source=options.native_source.resolve()
commit=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
if commit!=subprocess.check_output(['git','-C',str(source),'rev-parse','v0.22.5^{}'],text=True).strip():parser.error('Hermes v0.22.5 checkout required')
if subprocess.run(['git','-C',str(source),'diff','--quiet','HEAD']).returncode:parser.error('native tracked source must match its tag')

root=Path(tempfile.mkdtemp(prefix='xsm-owned-hermes-native-')).resolve();root.chmod(0o700);home=root/'home';home.mkdir(mode=0o700);workspace=root/'workspace';workspace.mkdir();profile=root/'hermes';profile.mkdir(mode=0o700);state=root/'state';out=options.output.absolute();out.mkdir(exist_ok=False);nonce=os.urandom(4).hex();model='fixture'

env={key:os.environ[key] for key in ('PATH','LANG','TMPDIR') if key in os.environ};env.update(HOME=str(home),HERMES_HOME=str(profile),PYTHONPATH=str(source),XDG_DATA_HOME=str(root/'data'),XDG_CACHE_HOME=str(root/'cache'),XSM_PYTHON=sys.executable,XSM_HOME=str(state),XSM_HERMES=str(executable),PYTHONDONTWRITEBYTECODE='1');os.environ.clear();os.environ.update(env)
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
settings={'model':{'default':model,'provider':'custom','base_url':'http://127.0.0.1:'+str(assistant.server.server_port)+'/v1','api_key':'explicit-no-network-fixture','api_mode':'chat_completions'},'fallback_providers':[],'agent':{'max_turns':6,'max_tokens':1536,'skip_context_files':True,'background_review':{'enabled':False}},'memory':{'enabled':False},'plugins':{'enabled':['xsm']},'toolsets':['xsm'],'gateway':{'standalone':True,'multiplex_profiles':False,'unmanaged_idle_exit_seconds':60},'terminal':{'cwd':str(workspace)}}
(profile/'config.yaml').write_text(json.dumps(settings,indent=2));(profile/'config.yaml').chmod(0o600)

report={'status':'starting','scope':'actual public owned journal and Hermes0.22.5 native CLI/control; scripted provider, model0','root':str(root),'started_at':time.time(),'checks':[],'served_model':None};
report['lost_confirmation_injected']=options.lose_cancel_confirmation;report['native_source_commit']=commit
def save():(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
def check(name,value):
 if not value:raise AssertionError(name)
 report['checks'].append(name);save()
async def main():
 from xsm import host_install
 from xsm_client import XsmClient
 client=None
 try:
  installed=host_install.apply('hermes',str(profile));report['runtime_root']=installed['runtime_root'];save()
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

  created=await op('xsm_owned',{'action':'create','name':'native-hermes','runtime':'hermes','home':str(profile),'model':model})
  check('public operation admits verified native Hermes provider',created['runtime']=='hermes' and bool(created.get('native_provider')))
  print(json.dumps({'status':'native provider admitted'}),flush=True)
  async def run(request,prompt,work='shared-native'):
   result=await op('xsm_owned',{'action':'run','name':'native-hermes','text':prompt,'work_context':work,'request_id':request})
   deadline=time.monotonic()+120
   while result['status'] not in ('sent','reply-stored','unknown','error') and time.monotonic()<deadline:
    await asyncio.sleep(.1);result=await op('xsm_owned',{'action':'status','name':'native-hermes','request_id':request})
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
  check('both native conversations belong to the same logical owned service',set(workers.load('native-hermes')['owned_sessions'])=={first['result']['native_session_id'],separate['result']['native_session_id']})
  before=(out/'assistant-fixture.jsonl').read_text().splitlines()
  replay=await run('first-'+nonce,'Explicit fixture request; do not call any tools.')
  check('same request retained exact reply',replay['reply_id']==first['reply_id'])
  check('cached request performs no provider calls',(out/'assistant-fixture.jsonl').read_text().splitlines()==before)
  check('context bound before both native turns',all(row.get('native_binding',{}).get('native_session_id')==first['result']['native_session_id'] for row in (first,second)))
  report['providerFixtureRequests']=len(before)
  blocking['enabled']=True
  cancel_id='cancel-'+nonce
  await op('xsm_owned',{'action':'run','name':'native-hermes','text':'Pending explicit provider fixture.','work_context':'cancel-native','request_id':cancel_id})
  check('actual native request reached blocking HTTP fixture',await asyncio.to_thread(entered.wait,15))
  from xsm import owned_requests
  states=[json.loads(p.read_text()) for p in (state/'owned-requests').glob('*.json')]
  saved=[value['requests'][cancel_id] for value in states if cancel_id in value.get('requests',{})]
  check('actual cancel target has one durable native request',len(saved)==1 and bool(saved[0].get('native_binding')))
  original=saved[0]
  from xsm_client import RpcError
  intruder=await client.session_open(runtime='owned-reference',profile='different-profile',conversation=nonce+'-intruder',cwd=str(workspace),capabilities=['messaging','inbox','events'])
  try:await client.operation_call(intruder['session'],'xsm_owned',{'action':'cancel','name':'native-hermes','request_id':cancel_id})
  except RpcError:check('different native sender cannot cancel this request',True)
  else:raise AssertionError('foreign cancellation accepted')
  cancel_started=time.monotonic()
  pending=await op('xsm_owned',{'action':'cancel','name':'native-hermes','request_id':cancel_id})
  check('admitted provider advertises native cancellation',pending['cancellation']['native_supported'] is True)
  check('intent alone does not claim native stop',pending['cancellation']['native_state']=='unverified')
  if options.lose_cancel_confirmation:
    deadline=time.monotonic()+15
    while True:
     current=await op('xsm_owned',{'action':'status','name':'native-hermes','request_id':cancel_id})
     if current['status']=='unknown' and type(current.get('child',{}).get('returncode')) is int:break
     if time.monotonic()>deadline:raise TimeoutError('native CLI exit after lost confirmation')
     await asyncio.sleep(.05)
    (out/'native-cancel-output.jsonl').write_bytes(Path(current['child']['stdout']).read_bytes())
    check('failed confirmation keeps native state unverified',current['cancellation']['native_state']=='unverified' and current['slot_occupied'] is True)
    before=len(http_calls)
    current=await op('xsm_owned',{'action':'reconcile','name':'native-hermes','request_id':cancel_id})
    check('native stop recovered from exact retained output',current['cancellation']['native_state']=='stopped' and current['cancellation']['recovered_from']=='native-output')
    check('readback releases only the verified native slot',current['slot_occupied'] is False)
    check('readback does not manufacture task answer',current['status']=='unknown' and current['result'] is None and current['reply_id'] is None)
    check('readback does not run another native request',len(http_calls)==before)
    again=await op('xsm_owned',{'action':'reconcile','name':'native-hermes','request_id':cancel_id})
    check('repeated readback preserves same stop evidence',again['cancellation']==current['cancellation'])
  else:
    deadline=time.monotonic()+15
    while True:
     current=await op('xsm_owned',{'action':'status','name':'native-hermes','request_id':cancel_id})
     if current.get('cancellation',{}).get('native_state')=='stopped' and type(current.get('child',{}).get('returncode')) is int:break
     if time.monotonic()>deadline:raise TimeoutError('native cancellation confirmation')
     await asyncio.sleep(.05)
    check('actual native aborted settle is recorded',current['cancellation']['status']=='native-stopped' and current['cancellation']['native_session_id']==current['native_binding']['native_session_id'])
    check('cancelled native turn is no invented answer',current['status']=='unknown' and current['result'] is None and current['reply_id'] is None)
  (out/'cancelled-request.json').write_text(json.dumps(current,indent=2)+'\n')
  report['cancelHTTPRequests']=len(http_calls);report['cancel_observation_seconds']=round(time.monotonic()-cancel_started,3)
  report['status']='passed'
 except BaseException as error:report.update(status='failed',failure_type=type(error).__name__)
 finally:
  if client:await client.close()
  release.set();assistant.server.shutdown();assistant.server.server_close()
  cleanup="""import json,os,signal,time
from hermes_cli.gateway_profile_lifecycle import owned_gateway_pid
from gateway.status import _pid_exists
pid=owned_gateway_pid();stopped=None
if pid is not None:
 os.kill(pid,signal.SIGTERM);deadline=time.monotonic()+30
 while _pid_exists(pid) and time.monotonic()<deadline:time.sleep(.1)
 stopped=not _pid_exists(pid)
print(json.dumps({'owned_gateway_found':pid is not None,'gateway_stopped':stopped}))
"""
  try:
   stopped=subprocess.run([str(native_python),'-B','-c',cleanup],cwd=workspace,env=dict(os.environ),capture_output=True,text=True,timeout=40)
   report['cleanup']=json.loads(stopped.stdout.strip().splitlines()[-1]);report['cleanup_exit']=stopped.returncode
   if stopped.returncode or report['cleanup']['gateway_stopped'] is False:report['status']='failed'
  except BaseException as error:report.update(status='failed',cleanup_failure_type=type(error).__name__)
  report['finished_at']=time.time();save();print(json.dumps(report),flush=True)
 return 0 if report['status']=='passed' else 1
raise SystemExit(asyncio.run(main()))
