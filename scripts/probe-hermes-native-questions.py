"""Actual pinned AIAgent loop and installed native UI bridge, explicit model0/UI fixtures."""
import hashlib,json,logging,os,subprocess,sys,tempfile,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import argparse
parser=argparse.ArgumentParser(description='Pinned native AIAgent/UI bridge with explicit model0 and UI callback fixtures; no real inference or human UI.')
parser.add_argument('--native-source',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
options=parser.parse_args()
repo=Path(__file__).resolve().parents[1];source=options.native_source.resolve();out=options.output.absolute();out.mkdir(parents=True,exist_ok=False)
commit=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip();assert commit==subprocess.check_output(['git','-C',str(source),'rev-parse','v0.22.5^{}'],text=True).strip();subprocess.run(['git','-C',str(source),'diff','--quiet','HEAD'],check=True)
root=Path(tempfile.mkdtemp(prefix='xsm-hermes-ui-agent-'));root.chmod(0o700)
env={k:os.environ[k] for k in ('PATH','LANG','TMPDIR') if k in os.environ};env.update(HOME=str(root/'home'),HERMES_HOME=str(root/'hermes'),XSM_HOME=str(root/'state'),TERMINAL_CWD=str(root/'home'),PYTHONDONTWRITEBYTECODE='1')
for k in ('HOME','HERMES_HOME','XSM_HOME'):Path(env[k]).mkdir(mode=0o700)
os.environ.clear();os.environ.update(env);os.chdir(root/'home');sys.path[:0]=[str(repo),str(source)];logging.disable(logging.CRITICAL)
report={'status':'starting','scope':'actual AIAgent/tool loop, installed plugin and common protocol; scripted provider and UI callback; no real inference, human UI or messenger','modelCalls':0,'nativeSourceCommit':commit,'root':str(root),'checks':[],'sourceSha256':{name:hashlib.sha256((repo/name).read_bytes()).hexdigest() for name in ('integrations/hermes/xsm.py','clients/python/xsm_host.py','integrations/hermes/plugin.yaml','scripts/probe-hermes-native-questions.py')}};phase=0;requests=[];ui_shown=[];args={'question':'Native agent color fixture','options':['blue','green'],'decision_key':'agent-ui-fixture'}
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_POST(self):
  global phase
  value=json.loads(self.rfile.read(int(self.headers['Content-Length'])));available={t.get('function',{}).get('name') for t in value.get('tools',[])};(out/('request-'+str(len(requests))+'.json')).write_text(json.dumps(value,indent=2)+'\n');requests.append({'availableTools':sorted(n for n in available if isinstance(n,str)),'phase':phase})
  name=None;arguments=None;text='Explicit auxiliary fixture'
  if available:
   def find_pending(item):
    if isinstance(item,dict):
     if item.get('native_ui'):return item
     for v in item.values():
      found=find_pending(v)
      if found:return found
    elif isinstance(item,list):
     for v in item:
      found=find_pending(v)
      if found:return found
    elif isinstance(item,str):
     try:return find_pending(json.loads(item))
     except (ValueError,TypeError):pass
    return None
   if phase==0:name='tool_search';arguments={'queries':['xsm_decide'],'limit':1};phase=1
   elif phase==1:name='tool_call';arguments={'calls':[{'name':'xsm_decide','arguments':args}]};phase=2
   elif phase==2:
    pending=find_pending(value.get('messages',[]))
    if pending is None:text='XSM_NATIVE_UI_FIXTURE_FAILURE';phase=99
    else:name='clarify';arguments=pending['native_ui']['arguments'];phase=3
   elif phase==3:name='tool_call';arguments={'calls':[{'name':'xsm_decide','arguments':args}]};phase=4
   else:text='XSM_HERMES_NATIVE_UI_AGENT_COMPLETE'
   if name not in available and name is not None:raise RuntimeError('native tool unavailable: '+name)
  delta={'content':text};reason='stop'
  if name:
   delta={'tool_calls':[{'index':0,'id':'fixture-ui-call-'+str(phase),'type':'function','function':{'name':name,'arguments':json.dumps(arguments)}}]};reason='tool_calls'
  packets=[{'id':'fixture','object':'chat.completion.chunk','created':int(time.time()),'model':'explicit-fixture','choices':[{'index':0,'delta':delta,'finish_reason':None}]},{'id':'fixture','object':'chat.completion.chunk','created':int(time.time()),'model':'explicit-fixture','choices':[{'index':0,'delta':{},'finish_reason':reason}]}]
  body=(''.join('data: '+json.dumps(p)+'\n\n' for p in packets)+'data: [DONE]\n\n').encode();self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
settings={'model':{'default':'fixture','provider':'custom','base_url':'http://127.0.0.1:'+str(server.server_port)+'/v1','api_key':'explicit-fixture','api_mode':'chat_completions'},'fallback_providers':[],'agent':{'max_turns':6,'skip_context_files':True},'memory':{'enabled':False},'plugins':{'enabled':['xsm'],'entries':{'xsm':{'settings':{'native_questions':True}}}},'toolsets':['xsm','clarify'],'terminal':{'cwd':str(root/'home')}}
(root/'hermes/config.yaml').write_text(json.dumps(settings));agent=None
try:
 from xsm import host_install
 installation=host_install.apply('hermes',str(root/'hermes'));report['runtimeRoot']=installation['runtime_root']
 from run_agent import AIAgent
 def callback(questions):ui_shown.extend(questions);return {'answers':{'q0':questions[0]['choices'][0]},'outcome':'submitted'}
 agent=AIAgent(model='fixture',provider='custom',base_url=settings['model']['base_url'],api_key='explicit-fixture',api_mode='chat_completions',enabled_toolsets=['xsm','clarify'],max_iterations=6,max_tokens=1000,quiet_mode=True,skip_context_files=True,skip_memory=True,skip_background_review=True,save_trajectories=False,load_soul_identity=False,cwd=str(root/'home'),run_budget_seconds=60,clarify_callback=callback)
 from tools.registry import registry
 from hermes_cli.plugins import get_plugin_manager
 entry=registry.get_entry('xsm_decide',scope=get_plugin_manager().scope_key)
 report['bindings']=[]
 for cell in getattr(entry.handler,'__closure__',()) or ():
  item=cell.cell_contents
  if type(item).__name__=='HermesBinding':report['bindings'].append({'pluginId':item.context.plugin_id,'nativeQuestions':item.native_questions is not None,'setting':item.context.get_config('native_questions',False)})
 result=agent.run_conversation('Run the explicit user-authorized native question fixture. Use the provided tools.')
 tools=[m for m in result.get('messages',[]) if m.get('role')=='tool'];(out/'native-tool-results.json').write_text(json.dumps(tools,indent=2)+'\n')
 def check(name,value):
  if not value:raise AssertionError(name)
  report['checks'].append(name)
 check('actual native agent completed fixture loop',str(result.get('final_response','')).strip()=='XSM_HERMES_NATIVE_UI_AGENT_COMPLETE')
 check('actual UI callback invoked exactly once',len(ui_shown)==1)
 tools=[m for m in result.get('messages',[]) if m.get('role')=='tool'];(out/'native-tool-results.json').write_text(json.dumps(tools,indent=2)+'\n')
 check('actual native discovery and tools completed four operations',len(tools)==4)
 check('actual original operation retry received selected value',any('your user answered: blue' in str(m.get('content')) for m in tools))
 report.update(status='passed',providerRequests=len(requests),nativeSessionId=agent.session_id,uiQuestions=ui_shown)
except BaseException as error:report.update(status='failed',failureType=type(error).__name__,failure=str(error));raise
finally:
 try:
  from hermes_cli.plugins import get_plugin_manager
  get_plugin_manager().unload('xsm')
  report['pluginUnloaded']=True
 except Exception as error:report.update(status='failed',unloadFailure=type(error).__name__)
 server.shutdown();server.server_close();thread.join(timeout=2);report['requests']=requests
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k) for k in ('status','checks','failure','pluginUnloaded','unloadFailure')}))
