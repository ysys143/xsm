"""One owned real TUI: observe pending MCP, one Esc, at most one follow-up."""
import os,sys,json,time,subprocess,pty,fcntl,termios,struct,select,threading,hashlib,signal,sqlite3
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path('/private/tmp/native-cancel-trusted-w23wicuo')
SOURCE=Path('/private/tmp/xsm-final-receipt-frozen-i3u9pms3')
PROFILE=Path('/Users/jaesolshin/.codex-3')
PUBLIC=Path(__file__).resolve().parent
REPO=Path('/Users/jaesolshin/Documents/GitHub/cross-session-messaging')
DEADLINE=datetime.fromisoformat('2026-10-29T00:52:00+00:00').timestamp()
GOAL='당신은 이 읽기전용 repository에서 실행하는 소유 평가 대화의 수신 대기 담당입니다. 평가용 제품 skill은 /private/tmp/xsm-final-receipt-frozen-i3u9pms3/skills/xsm/SKILL.md 입니다. 이를 읽고 이 대화의 xsm 수신함만 사용하세요. 다른 세션을 열거하거나 접촉하지 마세요.  아직 올 업무를 xsm의 수신 대기 도구로 약 1분 기다리세요. 빈 수신함을 반복 polling하거나 shell sleep으로 대신하지 말고 실제 도구 대기를 사용하세요. 실제 온 업무가 있으면 읽고 처리 확인을 하되 없으면 아직 없다고 구분하세요. 이 평가에서는 다른 서비스·팀·사용자 세션을 호출하거나 새 동료를 만들지 마세요. 파일·설정·권한·프로필을 수정하거나 상태파일을 직접 읽지 마세요.'
FOLLOWUP='대기 중 표준 취소를 했습니다. 같은 대화에서 취소된 대기와 업무 소비를 구분해 현재 xsm 수신 상태를 확인하세요. 실제 미확인 원문이 있으면 읽고 제품 도구의 처리 확인을 완료하되 원문이 없으면 없다고 보고하세요. 읽지 않은 자료나 ACK를 완료했다고 추정하지 마세요. 다른 세션·서비스 호출, 새 업무 전송·재시도, 상태파일·인덱스·권한·설정 변경 없이 짧게 결과를 보고하고 끝내세요.'
def sha(b):return hashlib.sha256(b).hexdigest()
def load(p):
 try:return json.loads(Path(p).read_text())
 except(OSError,ValueError):return None
def rows(p):
 try:
  result=[]
  for line in Path(p).read_text().splitlines():
   try:result.append(json.loads(line))
   except ValueError:pass
  return result
 except OSError:return []
def lstart(pid):return subprocess.run(['ps','-o','lstart=','-p',str(pid)],capture_output=True,text=True).stdout.strip()or None
def guard():return {n:sha((PROFILE/n).read_bytes())if(PROFILE/n).is_file()else None for n in ['config.toml','hooks.json','settings.json']}
out={'root':str(ROOT),'source':str(SOURCE),'started_at':time.time(),'CLI':subprocess.run(['codex','--version'],capture_output=True,text=True).stdout.strip(),'profile_before':guard(),'controller_Esc':0,'controller_model_prompts':1,'automatic_model_retries':0,'initial_actual_registration_setup':[],'canonical_setup_messages':0,'synthetic_MCP_notification_result_identity_ACK':0}
def save():
 (ROOT/'result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');(ROOT/'result.json').chmod(0o600)
env=dict(os.environ,CODEX_HOME=str(PROFILE),XSM_HOME=str(ROOT/'state'),PYTHONPATH=str(SOURCE),PYTHONDONTWRITEBYTECODE='1',TERM='xterm-256color',PATH=str(SOURCE/'bin')+os.pathsep+os.environ.get('PATH',''))
for key in ['CODEX_THREAD_ID','CLAUDE_CODE_SESSION_ID','CLAUDE_SESSION_ID','CLAUDE_CODE_MESSAGING_SOCKET','CLAUDECODE','ANTHROPIC_API_KEY','OPENAI_API_KEY','CODEX_API_KEY']:env.pop(key,None)
argv=['codex','--sandbox','read-only','--ask-for-approval','never','--no-alt-screen']
cfg={'mcp_servers.xsm.command':'/usr/bin/python3','mcp_servers.xsm.args':[str(ROOT/'proxy.py'),str(ROOT/'tui'),str(SOURCE)],'mcp_servers.xsm.cwd':str(SOURCE)}
for k in ['CODEX_HOME','XSM_HOME','PYTHONPATH','PYTHONDONTWRITEBYTECODE']:cfg['mcp_servers.xsm.env.'+k]=env[k]
for k,v in cfg.items():argv+=['-c',k+'='+json.dumps(v)]
argv+=[GOAL];out['argv']=argv;out['goal_sha256']=sha(GOAL.encode());out['followup_sha256']=sha(FOLLOWUP.encode())
fm=load(PUBLIC.parent/'final-source-manifest.json')
assert all(sha((SOURCE/p).read_bytes())==v for p,v in fm['files'].items())
out['frozen_files_verified_before']=len(fm['files'])
import tomllib
trustraw=(PROFILE/'config.toml').read_bytes()
assert (tomllib.loads(trustraw.decode()).get('projects')or{}).get(str(REPO),{}).get('trust_level')=='trusted'
out['trust_preflight_exact_verified']=True
out['primary_before']={n:sha((REPO/n).read_bytes())for n in fm['stable_product_paths']}
assert all(out['primary_before'][n]==fm['files'][n]for n in fm['stable_product_paths'])
save()
master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',45,130,0,0))
proc=subprocess.Popen(argv,cwd=str(REPO),env=env,stdin=slave,stdout=slave,stderr=slave,start_new_session=True);os.close(slave)
out['TUI_wrapper']={'pid':proc.pid,'lstart':lstart(proc.pid)};save();stop=threading.Event()
def reader():
 with(ROOT/'receiver.pty').open('ab',buffering=0)as f:
  while not stop.is_set():
   ready,_,_=select.select([master],[],[],.2)
   if not ready:continue
   try:b=os.read(master,65536)
   except OSError:break
   if not b:break
   f.write(b)
   if b'\x1b[6n'in b:os.write(master,b'\x1b[1;1R')
   if b'\x1b[c'in b:os.write(master,b'\x1b[?1;2c')
t=threading.Thread(target=reader,daemon=True);t.start()
registered=set();rollout=None;CID=None
def observe():
 global rollout,CID
 con=sqlite3.connect('file:'+str(PROFILE/'state_5.sqlite')+'?mode=ro',uri=True,timeout=1)
 try:
  observed=set()
  for folder in(ROOT/'tui/proxies').iterdir():
   for event in rows(folder/'client-wire.jsonl'):
    meta=(event.get('params')or{}).get('_meta')or{}
    if event.get('method')=='tools/call'and isinstance(meta,dict)and meta.get('threadId'):observed.add(meta['threadId'])
  if len(observed)>1:raise RuntimeError('more than one actual caller CID')
  rr=con.execute('select id,name,cwd,rollout_path from threads where id=?',(next(iter(observed)),)).fetchall()if observed else[]
 finally:con.close()
 if len(rr)>1:raise RuntimeError('more than one native CID in the single-condition workspace')
 if rr:
  assert rr[0][2]==str(REPO),'actual caller cwd differs from trusted evaluation repository'
  CID=rr[0][0];rollout=Path(rr[0][3]);out['actual_native_CID']=CID;out['actual_rollout_path']=str(rollout)
 for folder in(ROOT/'tui/proxies').iterdir():
  h=load(folder/'handles.json')
  if not h or not CID:continue
  native=next((x for x in h['native_ancestor_chain']if Path(x['comm']).name=='codex'),None)
  if not native or lstart(native['pid'])!=native['lstart']:continue
  if native['pid']!=proc.pid and native['ppid']!=proc.pid:raise RuntimeError('native ancestor differs from owned TUI')
  key=(CID,native['pid'])
  if key not in registered:
   os.environ['XSM_HOME']=str(ROOT/'state');os.environ['PYTHONDONTWRITEBYTECODE']='1';sys.dont_write_bytecode=True;sys.path.insert(0,str(SOURCE))
   from xsm import registry
   existing=registry.by_session('codex',CID)
   if not existing:
    rec=registry.upsert('codex',str(PROFILE),CID,native['pid'],str(REPO),name='cancel-observer',mcp_pid=h['server']['pid'])
    out['initial_actual_registration_setup'].append({'basis':'real provider CID/cwd + own TUI native PID/lstart/home','record':rec,'native':native})
   registered.add(key)
 save()
def until(fn,seconds,label):
 end=min(time.time()+seconds,DEADLINE)
 while time.time()<end:
  observe();v=fn()
  if v:return v
  if proc.poll()is not None:raise RuntimeError('own TUI exited before '+label)
  time.sleep(.1)
 raise RuntimeError(label)
def calls():
 result=[]
 for f in(ROOT/'tui/proxies').iterdir():
  rr={x['id']:x for x in rows(f/'server-wire.jsonl')if 'id'in x}
  for x in rows(f/'client-wire.jsonl'):
   p=x.get('params')or{}
   if x.get('method')=='tools/call':result.append((f,x,rr.get(x.get('id'))))
 return result
def pending():
 for folder,req,res in calls():
  p=req['params'];args=p.get('arguments')or{}
  if p.get('name')=='xsm_inbox'and float(args.get('wait')or 0)>0 and res is None:
   return {'folder':str(folder),'request':req,'observed_at':time.time()}
 return None
def native_events(kind):return [x for x in rows(rollout)if x.get('type')=='event_msg'and(x.get('payload')or{}).get('type')==kind]if rollout else[]
def snapshot(label):
 state={str(p.relative_to(ROOT)):load(p)for p in(ROOT/'state/handoffs').glob('*/*.json')}
 (ROOT/(label+'.json')).write_text(json.dumps({'at':time.time(),'handoffs':state},ensure_ascii=False,indent=2)+'\n')
try:
 wait=until(pending,150,'no pending actual xsm_inbox wait observed; no standard cancellation sent')
 time.sleep(.35)
 assert pending()and not any(req['id']==wait['request']['id']and res is not None for _,req,res in calls()),'wait already ended before cancellation'
 out['pending']=wait;snapshot('before-standard-cancel');out['standard_cancel_at']=time.time();os.write(master,b'\x1b');out['controller_Esc']=1;save()
 until(lambda:native_events('turn_aborted'),35,'standard Esc did not yield observed native turn_aborted')
 snapshot('after-standard-cancel');out['native_abort_observed_at']=time.time();save()
 time.sleep(.8)
 out['followup_input_at']=time.time();os.write(master,FOLLOWUP.encode()+b'\r');out['controller_model_prompts']=2;save()
 until(lambda:native_events('task_complete')or native_events('task_completed'),150,'same-CID follow-up did not complete')
 snapshot('after-followup');out['status']='one native standard cancellation condition executed'
except BaseException as exc:out['status']='original incomplete/unsupported; no retry';out['failure']={'type':type(exc).__name__,'message':str(exc)}
finally:
 if rollout and rollout.exists():(ROOT/'native-rollout.jsonl').write_bytes(rollout.read_bytes())
 out['measurement_end_at']=time.time();save()
 # Standard idle exit is cleanup, not a second pending-call cancellation.
 if proc.poll()is None:
  out['idle_exit_CtrlD_at']=time.time();os.write(master,b'\x04')
  try:proc.wait(timeout=5)
  except subprocess.TimeoutExpired:pass
 known={proc.pid:out['TUI_wrapper']['lstart']}
 for folder in(ROOT/'tui/proxies').iterdir():
  h=load(folder/'handles.json')
  if h:
   for key in ['proxy','server']:known[h[key]['pid']]=h[key]['lstart']
   for row in h['native_ancestor_chain']:
    if Path(row['comm']).name=='codex':known[row['pid']]=row['lstart']
 signals=[]
 for pid,stamp in known.items():
  if lstart(pid)==stamp:os.kill(pid,signal.SIGTERM);signals.append({'pid':pid,'lstart':stamp,'signal':'SIGTERM','at':time.time(),'purpose':'owned cleanup, never counted as cancellation notification'})
 try:proc.wait(timeout=5)
 except subprocess.TimeoutExpired:
  if lstart(proc.pid)==out['TUI_wrapper']['lstart']:proc.kill()
  proc.wait(timeout=4)
 for pid,stamp in known.items():
  if lstart(pid)==stamp:os.kill(pid,signal.SIGKILL);signals.append({'pid':pid,'signal':'SIGKILL','at':time.time(),'purpose':'owned cleanup only'})
 time.sleep(.3);stop.set();t.join(timeout=2);os.close(master)
 out['cleanup_signals']=signals;out['TUI_exit_code']=proc.returncode;out['known_process_final_audit']=[{'pid':pid,'lstart':stamp,'same_owned_process_alive':lstart(pid)==stamp}for pid,stamp in known.items()]
 out['profile_after']=guard();out['profile_unchanged']=out['profile_before']==out['profile_after'];out['frozen_files_verified_after']=len(fm['files'])if all(sha((SOURCE/p).read_bytes())==v for p,v in fm['files'].items())else False
 out['primary_after']={n:sha((REPO/n).read_bytes())for n in fm['stable_product_paths']};out['primary_unchanged']=out['primary_before']==out['primary_after'];out['finished_at']=time.time();save();print(json.dumps({'status':out['status'],'Esc':out['controller_Esc'],'model_prompts':out['controller_model_prompts'],'root':str(ROOT)}),flush=True)
