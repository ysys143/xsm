"""Two factory parents, one real native child each. One condition, no retries."""
import hashlib,importlib,json,os,signal,sqlite3,subprocess,sys,time
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path('/private/tmp/different-parent-native-3jr1o8uv')
SOURCE=Path('/private/tmp/xsm-final-receipt-frozen-i3u9pms3')
PROFILE=Path('/Users/jaesolshin/.codex-3')
STOP_AT=datetime.fromisoformat('2026-10-28T22:34:15+00:00').timestamp()
GOALS={
 'parent-a1': '당신은 부모 A입니다. native 하위 동료 a1 한 명만 시작하세요. a1은 이 작업공간의 다른 부모가 둔 검토자 a2와 xsm으로 직접 협업해야 합니다. 2+2=5 제안을 a2에게 검토받고, 반례를 반영한 수정안 2+2=4와 자기 메모 사본을 다시 보내 최종 확인을 받으세요. a2의 0+0=0 경계 질문에도 직접 답하고 상대 자료를 읽어 내용 확인을 돌려주세요. 자식이 자기 대화로 실제 질문·수정 검토·메모·최종 회신을 직접 주고받도록 하세요. 당신은 자기 child 시작·대기·종결만 하고 본문 중계, 수동 ACK, 상태/index 보정을 하지 마세요. 상대가 아직 준비되지 않았으면 허용된 발견으로 기다리되 임의의 다른 세션을 선택하거나 권한을 열지 마세요. 실제 수행·미완을 구분해 보고하고 끝내세요.',
 'parent-a2': '당신은 부모 B입니다. native 하위 동료 a2 한 명만 시작하세요. a2는 이 작업공간의 다른 부모가 둔 a1과 xsm으로 직접 협업해야 합니다. a1의 2+2=5 제안을 독립 검토해 반례를 보내고, 뒤의 수정안 2+2=4와 받은 메모 사본을 실제로 확인해 최종 답을 돌려주세요. 0+0=0 경계도 a1에게 직접 물어 답과 상대 자료 내용을 확인하세요. 자식이 자기 대화로 실제 질문·수정 검토·메모·최종 회신을 직접 주고받도록 하세요. 당신은 자기 child 시작·대기·종결만 하고 본문 중계, 수동 ACK, 상태/index 보정을 하지 마세요. 상대가 아직 준비되지 않았으면 허용된 발견으로 기다리되 임의의 다른 세션을 선택하거나 권한을 열지 마세요. 실제 수행·미완을 구분해 보고하고 끝내세요.'}
def sha(value):
    return hashlib.sha256(value).hexdigest()

def save(name, value):
    p = ROOT / name
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    p.chmod(384)

def read(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None

def events(path):
    try:
        lines = Path(path).read_text().splitlines()
    except OSError:
        return []
    result = []
    for line in lines:
        try:
            result.append(json.loads(line))
        except ValueError:
            pass
    return result

def lstart(pid):
    return subprocess.run(['ps', '-o', 'lstart=', '-p', str(pid)], capture_output=True, text=True).stdout.strip() or None

def profile_guard():
    return {n: sha((PROFILE / n).read_bytes()) if (PROFILE / n).is_file() else None for n in ('config.toml', 'hooks.json', 'settings.json')}

def source_guard():
    return {str(p.relative_to(SOURCE)): sha(p.read_bytes()) for directory in ('xsm', 'hooks', 'skills') for p in sorted((SOURCE / directory).rglob('*')) if p.is_file() and '__pycache__' not in p.parts and (p.suffix != '.pyc')}
os.environ['XSM_HOME']=str(ROOT/'state');os.environ['PYTHONDONTWRITEBYTECODE']='1';sys.dont_write_bytecode=True;sys.path.insert(0,str(SOURCE));registry=importlib.import_module('xsm.registry')
out={'label':'A15-05 actual different-parent native children, single condition','status':'in-progress','source':str(SOURCE),'root':str(ROOT),'native_parent_CLI_launches':2,'model_condition_retries':0,'actual_registration_setup':[],'actors':[]}
actors={};registered=set()
def launch(role):
 folder=ROOT/role;env=dict(os.environ,CODEX_HOME=str(PROFILE),XSM_HOME=str(ROOT/'state'),PYTHONPATH=str(SOURCE),PYTHONDONTWRITEBYTECODE='1',PATH=str(SOURCE/'bin')+os.pathsep+os.environ.get('PATH',''))
 for key in ('CODEX_THREAD_ID','CLAUDE_CODE_SESSION_ID','CLAUDE_SESSION_ID','CLAUDE_CODE_MESSAGING_SOCKET','CLAUDECODE','ANTHROPIC_API_KEY','OPENAI_API_KEY','CODEX_API_KEY'):env.pop(key,None)
 args=['codex','exec','--ignore-user-config','--json','--sandbox','workspace-write','-c','approval_policy="never"','-c','mcp_servers.xsm.command="/usr/bin/python3"','-c','mcp_servers.xsm.args='+json.dumps([str(ROOT/'proxy.py'),str(folder),str(SOURCE)]),'-c','mcp_servers.xsm.cwd='+json.dumps(str(SOURCE))]
 for key in ('XSM_HOME','CODEX_HOME','PYTHONPATH','PYTHONDONTWRITEBYTECODE'):args+=['-c','mcp_servers.xsm.env.'+key+'='+json.dumps(env[key])]
 args.append(GOALS[role]);streams=[(folder/'native.jsonl').open('w'),(folder/'native.stderr').open('w')];proc=subprocess.Popen(args,cwd=str(ROOT/'work'),env=env,stdin=subprocess.DEVNULL,stdout=streams[0],stderr=streams[1],text=True,start_new_session=True);entry={'role':role,'pid':proc.pid,'lstart':lstart(proc.pid),'alive_after_start':proc.poll()is None,'argv':args,'goal_sha256':sha(GOALS[role].encode())};actors[role]={'proc':proc,'entry':entry,'streams':streams,'CID':None};out['actors'].append(entry);save('result.json',out)
def observe():
 for role,a in actors.items():a['CID']=a['CID']or next((x.get('thread_id')for x in events(ROOT/role/'native.jsonl')if x.get('type')=='thread.started'),None)
 con=sqlite3.connect('file:'+str(PROFILE/'state_5.sqlite')+'?mode=ro',uri=True,timeout=1)
 try:rows=con.execute('select id,name,cwd,source,rollout_path from threads where cwd=?',(str(ROOT/'work'),)).fetchall()
 finally:con.close()
 known={}
 for role,a in actors.items():
  if not a['CID']:continue
  for row in rows:
   try:parent=(((json.loads(row[3])or{}).get('subagent')or{}).get('thread_spawn')or{}).get('parent_thread_id')
   except(ValueError,AttributeError):parent=None
   if row[0]==a['CID']or parent==a['CID']:known[row[0]]={'id':row[0],'name':row[1],'cwd':row[2],'source':row[3],'rollout_path':row[4],'role':role,'parent_thread_id':parent}
  for folder in (ROOT/role/'proxies').iterdir():
   h=read(folder/'handles.json')
   if not h:continue
   ancestor=next((x for x in h['native_ancestor_chain']if Path(x['comm']).name=='codex'),None)
   if not ancestor or lstart(ancestor['pid'])!=ancestor['lstart']:continue
   if ancestor['pid']!=a['proc'].pid and ancestor['ppid']!=a['proc'].pid:raise RuntimeError('native ancestor does not match this actual parent CLI')
   observed={a['CID']}
   for e in events(folder/'events.jsonl'):
    meta=e.get('actual_meta')or{}
    if e.get('method')=='tools/call'and isinstance(meta,dict)and meta.get('threadId'):observed.add(meta['threadId'])
   for sid in observed:
    if sid not in known or known[sid]['role']!=role or(sid,ancestor['pid'])in registered:continue
    row=known[sid];name=role if sid==a['CID']else role.split('-')[-1];rec=registry.upsert('codex',str(PROFILE),sid,ancestor['pid'],row['cwd'],name=name,mcp_pid=h['server']['pid']);registered.add((sid,ancestor['pid']));out['actual_registration_setup'].append({'at':time.time(),'CID':sid,'name':name,'native_pid':ancestor['pid'],'native_lstart':ancestor['lstart'],'home':str(PROFILE),'cwd':row['cwd'],'parent_thread_id':row['parent_thread_id'],'server_pid':h['server']['pid'],'provider_source':row['source'],'basis':'actual provider DB CID/parent + actual MCP metadata and own native ancestry','record':rec})
 out['actual_native_threads']=list(known.values());out['parent_CIDs']={k:v['CID']for k,v in actors.items()};save('result.json',out)
before=source_guard();save('source-manifest.json',before);out['profile_before']=profile_guard();out['CLI']=subprocess.run(['codex','--version'],capture_output=True,text=True).stdout.strip();out['started_utc']=datetime.now(timezone.utc).isoformat()
try:
 for role in GOALS:launch(role)
 while time.time()<STOP_AT and any(a['proc'].poll()is None for a in actors.values()):observe();time.sleep(.05)
 out['status']='native completed'if all(a['proc'].poll()is not None for a in actors.values())else'bounded native stop'
except BaseException as e:out['status']='original evaluation failure; no retry';out['error']={'type':type(e).__name__,'message':str(e)}
finally:
 known={a['proc'].pid:a['entry']['lstart']for a in actors.values()}
 for role in actors:
  for folder in (ROOT/role/'proxies').iterdir():
   h=read(folder/'handles.json')
   if h:
    for k in('proxy','server'):known[h[k]['pid']]=h[k]['lstart']
    for row in h['native_ancestor_chain']:
     if Path(row['comm']).name=='codex':known[row['pid']]=row['lstart']
 signals=[]
 for pid,start in known.items():
  if lstart(pid)==start:os.kill(pid,signal.SIGTERM);signals.append({'pid':pid,'lstart':start,'signal':'SIGTERM'})
 for a in actors.values():
  try:a['proc'].wait(timeout=5)
  except subprocess.TimeoutExpired:
   if lstart(a['proc'].pid)==a['entry']['lstart']:a['proc'].kill()
   a['proc'].wait(timeout=5)
  a['entry']['exit_code']=a['proc'].returncode
  for stream in a['streams']:stream.close()
 for pid,start in known.items():
  if lstart(pid)==start:os.kill(pid,signal.SIGKILL);signals.append({'pid':pid,'lstart':start,'signal':'SIGKILL'})
 out['known_processes']=[{'pid':pid,'lstart':start}for pid,start in known.items()];out['cleanup_signals']=signals;out['profile_after']=profile_guard();out['profile_unchanged']=out['profile_before']==out['profile_after'];out['source_unchanged']=before==source_guard();out['finished_utc']=datetime.now(timezone.utc).isoformat();save('result.json',out);print(json.dumps({'status':out['status'],'parents':len(actors),'threads':len(out.get('actual_native_threads',[])),'root':str(ROOT)}),flush=True)
