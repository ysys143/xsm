"""One natural async-work native pair; observation never relays/ACKs/indexes."""
import csv,hashlib,importlib.util,json,os,shutil,subprocess,sys,tempfile,time
from pathlib import Path
BASE=Path(__file__).resolve().parent;SOURCE=Path('/private/tmp/xsm-final-receipt-frozen-i3u9pms3')
ROOT=Path(tempfile.mkdtemp(prefix='p13-recovery-passive-',dir='/private/tmp'));ROOT.chmod(0o700)
WORK=ROOT/'project';WORK.mkdir(mode=0o700);STATE=ROOT/'state';STATE.mkdir(mode=0o700)
POLICY={'traffic_control':{'mode':'strict','window_seconds':60,'max_same_body':1}}
(STATE/'config.json').write_text(json.dumps(POLICY));(STATE/'config.json').chmod(0o600)
subprocess.run(['git','init','-q',str(WORK)],check=True)
# Repository-local product skill copied verbatim; no evaluator tool procedure.
SKILL=WORK/'.agents/skills/xsm';SKILL.parent.mkdir(parents=True);shutil.copytree(SOURCE/'skills/xsm',SKILL)
spec=importlib.util.spec_from_file_location('native_utils',BASE/'post-claims-collaboration.py');U=importlib.util.module_from_spec(spec);spec.loader.exec_module(U)
U.REPO=WORK
REVIEWER_GOAL=('이 private 저장소의 산술 검토 담당 a1입니다. 동료의 산술 검토를 독립 계산해 원 요청에 회신하고 읽은 메시지를 확인하세요. '
 '이 격리 시험의 반복 제어 정책은 60초 동안 같은 발신자의 동일 본문을 한 번만 처리합니다. 첫 정상 질문과 뒤의 동일 문장 재요청을 관측하되, '
 '제품이 반복을 보류하면 이를 답한 것으로 처리하지 말고 원문이 재개될 때까지 대기하세요. 동료가 새 질문 ID를 만들지 않고 기존 보류 요청을 회복한 뒤 '
 '두 번째 실제 요청도 검산·회신하고 종료하세요. 권한·설정·파일은 바꾸지 마세요.')
SENDER_GOAL=('xsm 동료 a1에게 정확히 같은 공개 검토 문장 "2+2=5 주장이 맞는지 독립 검토해 주세요."로 먼저 정상 질문 한 번을 보내 실제 답을 읽고 확인하세요. '
 '그 뒤 바이트까지 같은 문장을 한 번 더 새 질문으로 보내 의미 없는 반복이 제품에 의해 보류되는지 관측하세요. '
 '이번 private fixture에는 60초 동안 같은 발신자의 동일 본문을 한 번만 허용하는 반복 정책이 이미 설정돼 있습니다. '
 '보류된 원 요청 ID로 상태를 조회해 요청과 원문이 보존되고 성공으로 끝나지 않았는지 확인하세요. '
 '제품이 안내한 재시도 시간을 실제로 기다린 뒤, 새 ID로 치환하지 않고 같은 원문·원 요청 ID의 기존 재전송 경로를 단 한 번 사용해 회복하세요. '
 '그 원 ID의 실제 최종 회신을 조회하고 읽은 답을 확인한 뒤 정상 질문·보류·회복 결과를 보고하세요. '
 '추가 질문·반복 재전송·권한 확대·설정 변경·수동 메시지 수정은 하지 마세요.')
U.REVIEWER_GOAL=REVIEWER_GOAL;U.INITIATOR_GOAL=SENDER_GOAL
os.environ['XSM_HOME']=str(STATE);sys.path.insert(0,str(SOURCE));sys.dont_write_bytecode=True
import importlib
modules={n:importlib.import_module('xsm.'+n) for n in ('registry','paths','identity','envelope')};modules['paths'].HOME=str(STATE)
manifest=json.loads((BASE/'final-source-manifest.json').read_text());checked,_=U.source_readback(SOURCE,manifest['files'])
if not checked['matches']:raise RuntimeError('frozen source mismatch; no actor started')
report={'scope':'A22-03 one strict repeated-question defer/query/same-ID recovery native pair','root':str(ROOT),'workspace':str(WORK),'state':str(STATE),'frozen_source':str(SOURCE),'frozen_manifest':'deliverables/p13-live/final-source-manifest.json','source_before':checked,
 'goals':{'reviewer':REVIEWER_GOAL,'sender':SENDER_GOAL},'setup_registry_calls':0,'actor_native_invocations':0,'controller_body_relays':0,'controller_ACKs':0,'controller_index_writes':0,'additional_user_prompts':0,'automatic_actor_retries':0,'condition_runs':1,'status':'running','factory_ignore_user_config':True,'profile':str(Path.home()/'.codex-3'),'skill_source':'frozen product copied verbatim to private repository .agents/skills/xsm','private_policy':POLICY,'started_at':time.time()}
profile_before=U.profile_guard();actors=[];used=set();seen={};observations=[];files_seen={}
OUT=BASE/'recovery-passive-closure-native.json'
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
