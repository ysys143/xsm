"""One natural async-work native pair; observation never relays/ACKs/indexes."""
import csv,hashlib,importlib.util,json,os,shutil,subprocess,sys,tempfile,time
from pathlib import Path
BASE=Path(__file__).resolve().parent;SOURCE=Path('/private/tmp/xsm-final-receipt-frozen-i3u9pms3')
ROOT=Path(tempfile.mkdtemp(prefix='p13-async-independent-',dir='/private/tmp'));ROOT.chmod(0o700)
WORK=ROOT/'project';WORK.mkdir(mode=0o700);STATE=ROOT/'state';STATE.mkdir(mode=0o700)
subprocess.run(['git','init','-q',str(WORK)],check=True)
# Repository-local product skill copied verbatim; no evaluator tool procedure.
SKILL=WORK/'.agents/skills/xsm';SKILL.parent.mkdir(parents=True);shutil.copytree(SOURCE/'skills/xsm',SKILL)
spec=importlib.util.spec_from_file_location('native_utils',BASE/'post-claims-collaboration.py');U=importlib.util.module_from_spec(spec);spec.loader.exec_module(U)
U.REPO=WORK
REVIEWER_GOAL=('이 private 저장소의 산술 검토 담당 a1입니다. xsm으로 동료의 검토 질문 하나를 받아 원문을 읽고 독립적으로 검산한 결과를 원래 동료에게 회신하세요. '
               '동료의 질문을 처리할 때까지 대기하고, 회신과 읽은 메시지의 확인을 마친 뒤 결과를 보고하세요. 다른 세션·폴더·권한·설정은 바꾸지 마세요.')
SENDER_GOAL=('xsm의 동료 검토 담당 a1에게 1부터 200000까지 정수 중 7 또는 11의 배수인 수를 중복 없이 더한 합을 독립 검토해 달라고 질문하세요. '
             '그 답을 기다리는 동안 별도의 작업으로 1부터 8192까지의 정수와 제곱을 n,square 헤더의 data/squares.csv에 저장하고, '
             '데이터 행수·제곱합·그 CSV 파일의 SHA-256을 data/squares-summary.json에 보관하세요. '
             '별도 파일 작업을 끝낸 뒤 처음 질문의 실제 최종 회신을 회수해 답과 파일 검증 결과를 함께 보고하세요. '
             '같은 검토를 새 질문으로 중복시키지 말고 읽은 메시지는 확인을 마치세요. 다른 폴더·권한·설정은 바꾸지 마세요.')
U.REVIEWER_GOAL=REVIEWER_GOAL;U.INITIATOR_GOAL=SENDER_GOAL
os.environ['XSM_HOME']=str(STATE);sys.path.insert(0,str(SOURCE));sys.dont_write_bytecode=True
import importlib
modules={n:importlib.import_module('xsm.'+n) for n in ('registry','paths','identity','envelope')};modules['paths'].HOME=str(STATE)
manifest=json.loads((BASE/'final-source-manifest.json').read_text());checked,_=U.source_readback(SOURCE,manifest['files'])
if not checked['matches']:raise RuntimeError('frozen source mismatch; no actor started')
report={'scope':'A16-02 single actual-native async independent-work continuity cell','root':str(ROOT),'workspace':str(WORK),'state':str(STATE),'frozen_source':str(SOURCE),'frozen_manifest':'deliverables/p13-live/final-source-manifest.json','source_before':checked,
 'goals':{'reviewer':REVIEWER_GOAL,'sender':SENDER_GOAL},'setup_registry_calls':0,'actor_native_invocations':0,'controller_body_relays':0,'controller_ACKs':0,'controller_index_writes':0,'additional_user_prompts':0,'automatic_actor_retries':0,'condition_runs':1,'status':'running','factory_ignore_user_config':True,'profile':str(Path.home()/'.codex-3'),'skill_source':'frozen product copied verbatim to private repository .agents/skills/xsm','started_at':time.time()}
profile_before=U.profile_guard();actors=[];used=set();seen={};observations=[];files_seen={}
OUT=BASE/'async-independent-native-results.json'
def save():
 OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 (ROOT/'controller-observations.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2))
def refresh(actor):
 rows=actor.refresh(used)
 for index,row in enumerate(rows):
  key=(actor.role,index)
  if key not in seen:
   seen[key]=time.time();item=row.get('item') or {}
   observations.append({'role':actor.role,'index':index,'at':seen[key],'event':row.get('type'),'item_id':item.get('id'),'item_type':item.get('type'),'tool':item.get('tool'),'native_thread_id':row.get('thread_id')})
 return rows
try:
 reviewer=U.Actor('reviewer',Path.home()/'.codex-3',SOURCE,STATE,ROOT,modules);actors.append(reviewer);report['reviewer_invocation']=reviewer.start();report['actor_native_invocations']+=1
 end=time.monotonic()+60
 while time.monotonic()<end and reviewer.peer is None:
  refresh(reviewer)
  if reviewer.proc.poll() is not None:break
  time.sleep(.05)
 if reviewer.peer is None:raise RuntimeError('reviewer real endpoint not registered')
 report['setup_registry_calls']+=1;save()
 sender=U.Actor('initiator',Path.home()/'.codex-3',SOURCE,STATE,ROOT,modules);actors.append(sender);report['sender_invocation']=sender.start();report['actor_native_invocations']+=1
 deadline=time.monotonic()+420;sender_done=None
 while time.monotonic()<deadline:
  for actor in actors:
   before=actor.peer is not None;refresh(actor)
   if not before and actor.peer is not None:report['setup_registry_calls']+=1
   for call in actor.calls.values():
    item=call['item']
    if call['kind']=='mcp_tool_call' and item.get('tool') in U.FORBIDDEN:raise RuntimeError('unexpected permission/owned/publication operation '+item['tool'])
  for name in ('data/squares.csv','data/squares-summary.json'):
   p=WORK/name
   if p.exists():
    signature=(p.stat().st_size,p.stat().st_mtime_ns)
    if files_seen.get(name)!=signature:
     files_seen[name]=signature;observations.append({'kind':'work_file','path':name,'at':time.time(),'size':signature[0],'mtime_ns':signature[1],'sha256':U.sha(p.read_bytes())})
  cfg=U.read_json(STATE/'config.json') or {}
  if cfg.get('links') or cfg.get('reaches') or cfg.get('projects'):raise RuntimeError('scope widened; sample stopped')
  if sender.proc.poll() is not None:
   sender_done=sender_done or time.monotonic()
   if reviewer.proc.poll() is not None or time.monotonic()-sender_done>20:break
  save();time.sleep(.1)
 report['actors']=[a.summary() for a in actors];report['status']='captured-original-sample';report['ended_at']=time.time()
except Exception as e:
 report['status']='not-completed-original-sample';report['failure']={'type':type(e).__name__,'reason':str(e)};report['ended_at']=time.time()
finally:
 report['actors']=[a.summary() for a in actors];report['cleanup']=[]
 for a in actors:
  try:report['cleanup']+=a.finish()
  except Exception as e:report['cleanup'].append({'role':a.role,'error_type':type(e).__name__})
 report['owned_processes_after']=[{'role':a.role,'pid':a.proc.pid,'lstart':a.start_generation,'native_alive':a.proc.poll() is None,'mcp_pid':(a.mcp or {}).get('pid'),'mcp_same_generation_alive':bool(a.mcp and modules['identity'].pid_alive(a.mcp['pid']) and modules['identity'].lstart(a.mcp['pid'])==a.mcp['lstart'])} for a in actors]
 report['source_after']=U.source_readback(SOURCE,manifest['files'])[0];report['source_unchanged']=report['source_before']==report['source_after'];report['profile_settings_and_auth_metadata_unchanged']=profile_before==U.profile_guard();report['observations_path']=str(ROOT/'controller-observations.json');save()
 print(json.dumps({'root':str(ROOT),'status':report['status'],'native_invocations':report['actor_native_invocations'],'setup_registrations':report['setup_registry_calls'],'fail':report.get('failure')},ensure_ascii=False),flush=True)
