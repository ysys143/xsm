#!/usr/bin/env python3
"""Run native owned lineage with explicit operator paths and live catalog validation."""
import asyncio,hashlib,json,os,sqlite3,subprocess,sys,tempfile,time,urllib.request
from pathlib import Path
repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo));sys.path.insert(0,str(repo/'clients/python'))
import argparse
parser=argparse.ArgumentParser(description='Actual Hermes owned parent/child lineage probe through an existing local subscription proxy; uses isolated profiles and no messenger.')
parser.add_argument('--native-source',type=Path,required=True)
parser.add_argument('--native-cli',type=Path,required=True)
parser.add_argument('--model',required=True)
parser.add_argument('--output',type=Path,required=True)
options=parser.parse_args()
source=options.native_source.resolve();executable=options.native_cli.absolute();native_python=executable.with_name('python')
if not executable.is_absolute() or not executable.is_file():parser.error('existing native Hermes CLI is required')
if options.output.exists():parser.error('output must be new; preserve previous evidence')
commit=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
if commit!=subprocess.check_output(['git','-C',str(source),'rev-parse','v0.22.5^{}'],text=True).strip():parser.error('Hermes v0.22.5 checkout required')
if subprocess.run(['git','-C',str(source),'diff','--quiet','HEAD']).returncode:parser.error('native tracked source must match its tag')
root=Path(tempfile.mkdtemp(prefix='xsm-owned-hermes-native-')).resolve();root.chmod(0o700);home=root/'home';home.mkdir(mode=0o700);workspace=root/'workspace';workspace.mkdir();profile=root/'hermes';profile.mkdir(mode=0o700);state=root/'state';out=options.output.absolute();out.mkdir(exist_ok=False);nonce=os.urandom(4).hex();model=options.model
with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:10100/v1/models',timeout=10) as response:catalog=json.load(response)
assert any(row.get('id')==model for row in catalog['data'])
env={key:os.environ[key] for key in ('PATH','LANG','TMPDIR') if key in os.environ};env.update(HOME=str(home),HERMES_HOME=str(profile),XSM_HOME=str(state),XSM_HERMES=str(executable),PYTHONPATH=str(source),PYTHONDONTWRITEBYTECODE='1');os.environ.clear();os.environ.update(env)
settings={'model':{'default':model,'provider':'custom','base_url':'http://127.0.0.1:10100/v1','api_key':'local-proxy-placeholder','api_mode':'chat_completions'},'fallback_providers':[],'agent':{'max_turns':6,'max_tokens':1536,'skip_context_files':True,'background_review':{'enabled':False}},'memory':{'enabled':False},'plugins':{'enabled':['xsm','xsm-lineage-probe']},'toolsets':['xsm','xsm-lineage-probe'],'gateway':{'standalone':True,'multiplex_profiles':False,'unmanaged_idle_exit_seconds':60},'terminal':{'cwd':str(workspace)}}
plugin=profile/'plugins/xsm-lineage-probe';plugin.mkdir(parents=True)
(plugin/'plugin.yaml').write_text('name: xsm-lineage-probe\nversion: 0.0.1\nprovides_tools: [xsm_lineage_probe]\n')
goal='Find xsm_owned and call it exactly once with '+json.dumps({'action':'create','name':'must-not-create','runtime':'claude','home':str(root/'must-not-exist')})+'. Do not retry. Reply exactly XSM_NATIVE_CHILD_REFUSED_'+nonce+' only if the actual tool result refuses max_depth; otherwise report failure.'
(plugin/'__init__.py').write_text('GOAL='+repr(goal)+'\n'+"def register(context):\n import json\n def probe(args,*,session_id='',**native):\n  lifecycle=context.subagent_lifecycle\n  handle=lifecycle.launch({'goal':GOAL,'role':'leaf','allowed_toolsets':['xsm'],'parent_session_id':session_id,'correlation_id':'native-owned-lineage'})\n  try:\n   status=lifecycle.wait(handle,timeout_seconds=60)\n   if not status.completed:raise RuntimeError('native child deadline')\n   result=lifecycle.result(handle)\n   return json.dumps({'ready':result.ready,'summary':result.summary,'api_calls':result.usage_metadata.get('api_calls')})\n  finally:\n   lifecycle.cancel(handle,reason='isolated owned lineage probe cleanup')\n context.register_tool(name='xsm_lineage_probe',toolset='xsm-lineage-probe',schema={'name':'xsm_lineage_probe','description':'Run the user-authorized isolated native child budget probe once.','parameters':{'type':'object','properties':{},'additionalProperties':False}},handler=probe,description='Isolated native child budget probe')\n")
(profile/'config.yaml').write_text(json.dumps(settings,indent=2));(profile/'config.yaml').chmod(0o600)
report={'status':'starting','scope':'actual xsm_owned operation, Hermes native CLI/model, shared journal and canonical reply/ACK; generic reference parent','root':str(root),'started_at':time.time(),'checks':[],'served_model':None,'requested_model':model,'native_source_commit':commit};
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
  async def run(request,prompt):
   result=await op('xsm_owned',{'action':'run','name':'native-hermes','text':prompt,'work_context':'shared-native','request_id':request})
   deadline=time.monotonic()+120
   while result['status'] not in ('sent','reply-stored','unknown','error') and time.monotonic()<deadline:
    await asyncio.sleep(.1);result=await op('xsm_owned',{'action':'status','name':'native-hermes','request_id':request})
   report[request+'_status']=result['status'];save()
   if result['status'] not in ('sent','reply-stored'):
    report[request+'_diagnostic']=result.get('send_evidence') or result.get('error') or result.get('unknown_reason');save();raise RuntimeError('native owned run did not publish')
   return result
  request='native-lineage-'+nonce
  expected='XSM_OWNED_LINEAGE_'+nonce
  prompt='Find and call xsm_lineage_probe exactly once using native tools. If and only if its actual summary is XSM_NATIVE_CHILD_REFUSED_'+nonce+', reply exactly '+json.dumps({'body':expected,'outcome':'succeeded'})+'. Otherwise report failure. Do not retry the probe.'
  result=await run(request,prompt)
  check('native owned parent confirms actual child result',result['result']['body']==expected and result['result']['outcome']=='succeeded')
  await read_reply(result['reply_id'],expected)
  sid=result['result']['native_session_id'];report['native_parent_id']=sid
  with sqlite3.connect('file:'+str(profile/'state.db')+'?mode=ro',uri=True) as db:
   children=list(db.execute('SELECT id,api_call_count,tool_call_count FROM sessions WHERE parent_session_id=?',(sid,)))
   check('native DB records exactly one actual child',len(children)==1)
   trace=[row[0] for row in db.execute("SELECT content FROM messages WHERE session_id=? AND role='tool' AND tool_name='xsm_owned'",(children[0][0],))]
   (out/'child-tool-results.json').write_text(json.dumps(trace,indent=2)+'\n')
   check('actual owned child tool refuses max_depth',len(trace)==1 and 'max_depth' in trace[0])
   report['child_api_calls']=children[0][1];report['child_tool_calls']=children[0][2]
  from xsm import workers,registry
  check('refused child service never created',workers.load('must-not-create') is None and not (root/'must-not-exist').exists())
  rows=[row for row in registry.raw_records() if row.get('protocol_parent')]
  check('actual child host retains native parent',len(rows)==1)
  check('actual child inherits publicly created owned budget',workers.for_record(rows[0])['id']==created['id'])
  (out/'lineage-records.json').write_text(json.dumps(rows,indent=2)+'\n')
  report['status']='passed'
 except BaseException as error:report.update(status='failed',failure_type=type(error).__name__)
 finally:
  if client:await client.close()
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
