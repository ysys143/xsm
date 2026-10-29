"""One ordinary factory lifetime condition; recording proxy, no state repair."""
import hashlib, importlib, json, os, signal, sqlite3, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path('/private/tmp/session-lifetime-native-oj91jnav')
SOURCE=Path('/private/tmp/xsm-final-receipt-frozen-i3u9pms3')
PROFILE=Path('/Users/jaesolshin/.codex-3')
END=datetime.fromisoformat('2026-10-29T00:38:00+00:00').timestamp()
GOALS={
 'old':'당신은 이 private 평가 작업공간의 보관자 archivist입니다. 제품 xsm skill을 읽고 현재 동료가 있는지 확인하세요. 지금은 업무 중단점이므로 들어오는 미처리 요청을 열거나 ACK하지 말고 나중에 이 대화를 재개할 때 처리하도록 남겨 두세요. 동료가 나중 검토용 질문을 남길 시간을 주기 위해 약 90초 쉬었다가 준비 상태만 보고하고 정상 종료하세요. 새 동료를 만들거나 설정/권한/인덱스를 고치지 마세요.',
 'sender':'당신은 이 private 작업공간의 업무 요청자 initiator입니다. 제품 xsm skill로 실제 보관자 archivist를 확인하고, 나중에 재개해서 검토할 수 있도록 방해 없는 검토 질문 한 건을 남기세요: 2+2=5라는 주장에 반례가 있는지 검토하고 올바른 결과를 원 질문에 최종 회신해 달라는 과제입니다. 동명 새 대화에게 원문을 다시 보내지 말고 선택한 원 대화의 실제 최종 답장을 기다려 확인하세요. 약 6분 예산 안에서 실제 결과를 확인하고 끝내세요. 새 동료 생성, 설정/권한 변경, 본문 중계나 수동 ACK/인덱스 수정은 하지 마세요.',
 'new':'당신은 이 private 작업공간에서 새로 시작한 대화이며 표시 이름은 archivist입니다. 과거 동명 대화의 신원이나 권한을 이어받았다고 가정하지 마세요. 제품 xsm skill로 현재 동료와 본인 수신함을 확인하고, 본인에게 실제 온 업무가 있다면 처리하고 없다면 없다고 보고하세요. 과거 대화의 상태파일이나 원문을 직접 열지 말고 다른 대화용 메시지를 찾아가거나 재송신해 달라고 요청하지 마세요. 실제 통신 권한이 확인되지 않으면 그 한계를 보고하세요. 설정/프로필/권한/ACK/인덱스 직접 수정이나 새 동료 생성 없이 정상 종료하세요.',
 'resume':'같은 평가 대화를 재개했습니다. 중단점에 남겨 둔 실제 미처리 업무를 제품 xsm skill과 도구로 확인하고, 본인에게 온 질문을 검토해 원 질문에 직접 최종 답장하세요. 실제 수신과 처리 확인을 마치고, 이미 처리한 같은 업무가 다시 제공되는지도 확인한 뒤 결과를 보고하세요. 과거 상태파일을 직접 읽거나 본문 중계, 수동 ACK/인덱스 보정, 권한/프로필 변경, 새 동료 생성은 하지 마세요.'}
os.environ['XSM_HOME']=str(ROOT/'state'); os.environ['PYTHONDONTWRITEBYTECODE']='1'
sys.dont_write_bytecode=True;sys.path.insert(0,str(SOURCE))
registry=importlib.import_module('xsm.registry')
def sha(b):return hashlib.sha256(b).hexdigest()
def load(p):
 try:return json.loads(Path(p).read_text())
 except (OSError,ValueError):return None
def events(p):
 try:return [json.loads(x)for x in Path(p).read_text().splitlines()]
 except (OSError,ValueError):return []
def start(pid):return subprocess.run(['ps','-o','lstart=','-p',str(pid)],capture_output=True,text=True).stdout.strip()or None
def guard():return {n:sha((PROFILE/n).read_bytes())if(PROFILE/n).is_file()else None for n in ['config.toml','hooks.json','settings.json']}
def save():
 (ROOT/'result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
 (ROOT/'result.json').chmod(0o600)
actors=[];registered=set()
out={'started_utc':datetime.now(timezone.utc).isoformat(),'source':str(SOURCE),'root':str(ROOT),'CLI':subprocess.run(['codex','--version'],capture_output=True,text=True).stdout.strip(),'profile_before':guard(),'invocations':[],'actual_registration_setup':[],'stages':[],'model_condition_retries':0,'selected_pair_created':False}
def launch(role,cid=None):
 folder=ROOT/role
 env=dict(os.environ,CODEX_HOME=str(PROFILE),XSM_HOME=str(ROOT/'state'),PYTHONPATH=str(SOURCE),PYTHONDONTWRITEBYTECODE='1',PATH=str(SOURCE/'bin')+os.pathsep+os.environ.get('PATH',''))
 for key in ['CODEX_THREAD_ID','CLAUDE_CODE_SESSION_ID','CLAUDE_SESSION_ID','CLAUDE_CODE_MESSAGING_SOCKET','CLAUDECODE','ANTHROPIC_API_KEY','OPENAI_API_KEY','CODEX_API_KEY']:env.pop(key,None)
 argv=['codex','exec','--ignore-user-config','--json','--sandbox','workspace-write','-c','approval_policy="never"','-c','mcp_servers.xsm.command="/usr/bin/python3"','-c','mcp_servers.xsm.args='+json.dumps([str(ROOT/'proxy.py'),str(folder),str(SOURCE)]),'-c','mcp_servers.xsm.cwd='+json.dumps(str(SOURCE))]
 for key in ['XSM_HOME','CODEX_HOME','PYTHONPATH','PYTHONDONTWRITEBYTECODE']:argv+=['-c','mcp_servers.xsm.env.'+key+'='+json.dumps(env[key])]
 if cid:argv+=['resume',cid]
 argv+=[GOALS[role]]
 streams=[(folder/'native.jsonl').open('w'),(folder/'native.stderr').open('w')]
 proc=subprocess.Popen(argv,cwd=str(ROOT/'work'),env=env,stdin=subprocess.DEVNULL,stdout=streams[0],stderr=streams[1],start_new_session=True)
 entry={'role':role,'wrapper_pid':proc.pid,'wrapper_lstart':start(proc.pid),'argv':argv,'requested_resume_CID':cid}
 actor={'role':role,'folder':folder,'proc':proc,'entry':entry,'streams':streams,'CID':None}
 actors.append(actor);out['invocations'].append(entry);save();return actor
def observe():
 for a in actors:
  a['CID']=a['CID']or next((x['thread_id']for x in events(a['folder']/'native.jsonl')if x.get('type')=='thread.started'),None)
  a['entry']['CID']=a['CID']
  if not a['CID'] or a['proc'].poll()is not None:continue
  for folder in(a['folder']/'proxies').iterdir():
   h=load(folder/'handles.json')
   if not h:continue
   native=next((x for x in h['native_ancestor_chain']if Path(x['comm']).name=='codex'),None)
   if not native or start(native['pid'])!=native['lstart']:continue
   if native['pid']!=a['proc'].pid and native['ppid']!=a['proc'].pid:raise RuntimeError('actual ancestry mismatch')
   key=(a['CID'],native['pid'])
   if key in registered:continue
   con=sqlite3.connect('file:'+str(PROFILE/'state_5.sqlite')+'?mode=ro',uri=True)
   try:row=con.execute('select id,name,cwd,source,rollout_path from threads where id=?',(a['CID'],)).fetchone()
   finally:con.close()
   if not row or row[2]!=str(ROOT/'work'):continue
   name='initiator'if a['role']=='sender'else'archivist'
   record=registry.upsert('codex',str(PROFILE),a['CID'],native['pid'],row[2],name=name,mcp_pid=h['server']['pid'])
   registered.add(key);out['actual_registration_setup'].append({'role':a['role'],'at':time.time(),'CID':a['CID'],'native':native,'home':str(PROFILE),'cwd':row[2],'provider_title':row[1],'rollout_path':row[4],'record':record,'basis':'real thread.started + provider DB + verified own native ancestor; display name only'})
 save()
def until(fn,seconds,label):
 limit=min(time.time()+seconds,END)
 while time.time()<limit:
  observe();v=fn()
  if v:return v
  time.sleep(.15)
 raise RuntimeError(label)
def snap(stage):
 data={'stage':stage,'at':time.time(),'handoffs':{},'questions':{},'sessions':{}}
 for dirname,pattern in [('handoffs','*/*.json'),('questions','*.json'),('sessions','*.json')]:
  for p in(ROOT/'state'/dirname).glob(pattern):data[dirname][str(p.relative_to(ROOT))]=load(p)
 (ROOT/(stage+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');out['stages'].append(stage);save();return data
try:
 old=launch('old')
 until(lambda:any(x['role']=='old'for x in out['actual_registration_setup']),60,'old native registration unavailable')
 sender=launch('sender')
 until(lambda:old['proc'].poll()is not None,160,'old did not finish normally')
 assert old['proc'].returncode==0,'old failed before offline stage'
 snap('old-offline-before-new')
 new=launch('new')
 until(lambda:new['proc'].poll()is not None,110,'new same-name native did not finish')
 snap('after-new-before-resume')
 assert old['CID']and new['CID']and old['CID']!=new['CID']
 # Wait for the old actual native generation to exit; no active writer bypass.
 old_rows=[x for x in out['actual_registration_setup']if x['role']=='old']
 until(lambda:all(start(x['native']['pid'])!=x['native']['lstart']for x in old_rows),15,'old native generation still active')
 resumed=launch('resume',old['CID'])
 until(lambda:resumed['proc'].poll()is not None and sender['proc'].poll()is not None,220,'resume/sender bounded incomplete')
 snap('after-resume')
 out['status']='one condition executed; classify raw evidence'
except BaseException as exc:out['status']='original incomplete/failure, no retry';out['failure']={'type':type(exc).__name__,'message':str(exc)}
finally:
 known={a['proc'].pid:a['entry']['wrapper_lstart']for a in actors}
 for a in actors:
  for f in(a['folder']/'proxies').iterdir():
   h=load(f/'handles.json')
   if h:
    for key in ['proxy','server']:known[h[key]['pid']]=h[key]['lstart']
    for row in h['native_ancestor_chain']:
     if Path(row['comm']).name=='codex':known[row['pid']]=row['lstart']
 signals=[]
 for pid,stamp in known.items():
  if start(pid)==stamp:os.kill(pid,signal.SIGTERM);signals.append({'pid':pid,'signal':'SIGTERM','lstart':stamp})
 for a in actors:
  try:a['proc'].wait(timeout=4)
  except subprocess.TimeoutExpired:
   if start(a['proc'].pid)==a['entry']['wrapper_lstart']:a['proc'].kill()
   a['proc'].wait(timeout=4)
  a['entry']['exit_code']=a['proc'].returncode
  for stream in a['streams']:stream.close()
 for pid,stamp in known.items():
  if start(pid)==stamp:os.kill(pid,signal.SIGKILL);signals.append({'pid':pid,'signal':'SIGKILL','lstart':stamp})
 out['cleanup_signals']=signals;out['known_processes']=[{'pid':pid,'lstart':stamp,'same_owned_process_alive':start(pid)==stamp}for pid,stamp in known.items()]
 out['profile_after']=guard();out['profile_unchanged']=out['profile_before']==out['profile_after'];out['finished_utc']=datetime.now(timezone.utc).isoformat();save()
 print(json.dumps({'status':out['status'],'CLI_launches':len(actors),'CIDs':len(set(a['CID']for a in actors if a['CID'])),'root':str(ROOT)}),flush=True)
