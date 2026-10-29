"""One natural async-work native pair; observation never relays/ACKs/indexes."""
import csv,hashlib,importlib.util,json,os,shutil,subprocess,sys,tempfile,time
from pathlib import Path
BASE=Path(__file__).resolve().parent;SOURCE=Path('/private/tmp/xsm-final-receipt-frozen-i3u9pms3')
ROOT=Path(tempfile.mkdtemp(prefix='p13-strict-review-',dir='/private/tmp'));ROOT.chmod(0o700)
WORK=ROOT/'project';WORK.mkdir(mode=0o700);STATE=ROOT/'state';STATE.mkdir(mode=0o700)
POLICY={'traffic_control':{'mode':'strict','window_seconds':60,'max_same_body':1}}
(STATE/'config.json').write_text(json.dumps(POLICY));(STATE/'config.json').chmod(0o600)
subprocess.run(['git','init','-q',str(WORK)],check=True)
# Repository-local product skill copied verbatim; no evaluator tool procedure.
SKILL=WORK/'.agents/skills/xsm';SKILL.parent.mkdir(parents=True);shutil.copytree(SOURCE/'skills/xsm',SKILL)
spec=importlib.util.spec_from_file_location('native_utils',BASE/'post-claims-collaboration.py');U=importlib.util.module_from_spec(spec);spec.loader.exec_module(U)
U.REPO=WORK
REVIEWER_GOAL=('이 private 저장소의 독립 검토 담당 a1입니다. 구현자와 아래 전체 묶음을 끝까지 수행하세요. '
 '첫째 잘못된 산술안의 반례, 둘째 그 실제 답을 반영한 수정안 재검토, 셋째 독립 경계조건 검토를 실제 요청마다 원문을 읽고 독립 계산해 회신하세요. '
 '세 라운드만 끝났다고 종료하지 마세요. 이어 구현자가 세 번째 요청과 바이트까지 같은 본문으로 보내는 네 번째 고유 요청이 '
 '60초 동일본문 반복 정책에 보류될 수 있습니다. 보류는 검토 완료나 성공 답으로 취급하지 말고 원 요청이 재개될 때까지 대기하세요. '
 '구현자가 시간을 기다려 네 번째 원 ID를 한 번 재전송하면 실제 수신 뒤 다시 독립 검산하여 원 요청에 회신하세요. '
 '최종적으로 서로 다른 요청 ID 4개의 실제 검토와 회신·읽음 확인을 마쳐야 묶음이 끝납니다. '
 '같은 정책을 유지하고 다른 세션·폴더·권한·설정·원문을 바꾸지 마세요.')
SENDER_GOAL=('xsm 독립 검토 담당 a1과 이 전체 묶음을 한 대화에서 끝까지 수행하세요. '
 '1라운드로 2+2=5라는 잘못된 안을 보내 반례를 받고, 그 실제 회신을 읽고 확인한 뒤에만 2라운드 수정안을 만들어 재검토받으세요. '
 '2라운드의 실제 답을 읽고 확인한 다음 3라운드로 0+0=0 경계조건을 독립 검토받으세요. '
 '세 답만 받고 종료하지 마세요. 즉시 세 번째 검토 요청의 본문을 바이트까지 그대로 복사해, 의미 없는 반복인 네 번째 질문을 한 번 더 보내세요. '
 '이번 private fixture에는 모든 라운드에 동일하게 strict, window=60초, 동일발신자 동일본문 1회 정책이 이미 설정돼 있습니다. '
 '정상 세 라운드는 서로 다른 본문이어야 하며 정책은 바꾸지 마세요. 네 번째 요청이 held되면 원 ID로 상태를 조회해 '
 '보류·미완료와 원문 보존을 확인하세요. 안내된 실제 시간을 충분히 기다린 뒤, 새 ID로 치환하지 말고 '
 '같은 원문·원 ID의 기존 재전송 경로를 단 한 번 사용해 회복하세요. 마지막도 그 원 ID로 실제 최종 답을 회수·확인해야 종료입니다. '
 '전체 고유 질문은 4개이며, 회복용 같은 ID 재전송까지 전달 시도는 최대 5회입니다. '
 'unknown/held/pending을 성공으로 쓰지 말고 최종 답의 내용·원 ID·상태를 보고하세요. '
 '추가 질문·자동 재시도·반복 재전송·권한 확대·설정 변경·수동 본문/ACK/index 수정은 하지 마세요.')
U.REVIEWER_GOAL=REVIEWER_GOAL;U.INITIATOR_GOAL=SENDER_GOAL
os.environ['XSM_HOME']=str(STATE);sys.path.insert(0,str(SOURCE));sys.dont_write_bytecode=True
import importlib
modules={n:importlib.import_module('xsm.'+n) for n in ('registry','paths','identity','envelope')};modules['paths'].HOME=str(STATE)
manifest=json.loads((BASE/'final-source-manifest.json').read_text());checked,_=U.source_readback(SOURCE,manifest['files'])
if not checked['matches']:raise RuntimeError('frozen source mismatch; no actor started')
report={'scope':'A22-03 one final same-policy three-review rounds plus repeated-body defer and same-ID recovery trace','root':str(ROOT),'workspace':str(WORK),'state':str(STATE),'frozen_source':str(SOURCE),'frozen_manifest':'deliverables/p13-live/final-source-manifest.json','source_before':checked,
 'goals':{'reviewer':REVIEWER_GOAL,'sender':SENDER_GOAL},'setup_registry_calls':0,'actor_native_invocations':0,'controller_body_relays':0,'controller_ACKs':0,'controller_index_writes':0,'additional_user_prompts':0,'automatic_actor_retries':0,'condition_runs':1,'status':'running','factory_ignore_user_config':True,'profile':str(Path.home()/'.codex-3'),'skill_source':'frozen product copied verbatim to private repository .agents/skills/xsm','private_policy':POLICY,'started_at':time.time()}
profile_before=U.profile_guard();report['profile_guard_before']=profile_before;report['initial_private_policy_sha256']=U.sha((STATE/'config.json').read_bytes());actors=[];used=set();seen={};observations=[];files_seen={}
OUT=BASE/'strict-review-native-results.json'
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
  for record_path in (STATE/'handoffs').glob('*/*.json'):
   row=U.read_json(record_path) or {}
   if row.get('delivery_state')=='held' and not (ROOT/('held-'+row['id']+'.json')).exists():
    receipts=[U.read_json(p) for p in (STATE/'ledger').glob('*.recv.json')]
    receipt=next((x for x in receipts if x and x.get('id')==row['id']),None)
    (ROOT/('held-'+row['id']+'.json')).write_text(json.dumps({'observed_at':time.time(),'canonical':row,'receipt':receipt},ensure_ascii=False,indent=2))
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
 report['source_after']=U.source_readback(SOURCE,manifest['files'])[0];report['source_unchanged']=report['source_before']==report['source_after'];report['profile_guard_after']=U.profile_guard();report['profile_settings_and_auth_metadata_unchanged']=profile_before==report['profile_guard_after'];report['final_private_policy_sha256']=U.sha((STATE/'config.json').read_bytes());report['observations_path']=str(ROOT/'controller-observations.json');save()
 print(json.dumps({'root':str(ROOT),'status':report['status'],'native_invocations':report['actor_native_invocations'],'setup_registrations':report['setup_registry_calls'],'fail':report.get('failure')},ensure_ascii=False),flush=True)
