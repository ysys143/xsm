"""Actual Codex actors: initial CID/provider/PID registration only."""
import hashlib,json,os,signal,sqlite3,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).parent;M=json.loads((ROOT/'manifest.json').read_text());PAYLOAD=ROOT/'payload';STATE=Path(M['state']);WORK=ROOT/'work'
sys.path.insert(0,str(PAYLOAD));os.environ['XSM_HOME']=str(STATE);os.environ['PYTHONDONTWRITEBYTECODE']='1'
from xsm import config,identity,paths,registry
paths.HOME=str(STATE)
def read(path,default=None):
 try:return json.loads(path.read_text())
 except (OSError,ValueError):return default
def rows(path):
 out=[]
 try:
  for line in path.read_text().splitlines():
   try:out.append(json.loads(line))
   except ValueError:pass
 except OSError:pass
 return out
def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');path.chmod(0o600)
def starttime(pid):return subprocess.run(['ps','-p',str(pid),'-o','lstart='],capture_output=True,text=True,timeout=3).stdout.strip()or None
ENV={'PATH':str(PAYLOAD/'bin')+':/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin','HOME':str(ROOT/'os-home'),
     'LANG':'en_US.UTF-8','XSM_HOME':str(STATE),'PYTHONPATH':str(PAYLOAD),'PYTHONDONTWRITEBYTECODE':'1','TMPDIR':str(ROOT/'t'),
     'XSM_TEMP':str(ROOT/'t'),'XSM_NET_BINARY':str(PAYLOAD/'bin/xsm-net'),'XSM_CODEX':M['codex']}
SUFFIX=' 제공된 협업 기능으로 동료와 업무를 수행하세요. 새 동료나 대화를 대신 만들거나 소스·설정·프로필·권한·질문 인덱스를 직접 수정하지 마세요. 작업 폴더 밖 상태파일을 직접 열거나 메시지 본문을 별도 경로로 중계하지 마세요. 한국어로 보고하세요.'
GOALS={
 'reviewer':'이 공유 작업 폴더의 검토 담당 a1입니다. 작성자가 보내는 제안을 독립적으로 검토하고 근거와 결론을 그 작성자에게 직접 회신하세요. 협업 준비 확인과 별도로 최초안, 수정안, 경계조건의 세 업무 검토가 모두 끝날 때까지 약 7분 동안 대기하세요. 실제 받은 업무만 검토하고 요청 내용을 미리 가정하지 마세요.',
 'phase0':'같은 작업 폴더의 검토 담당 a1을 찾아 2+2=5 제안의 타당성을 실제 검토받으세요. 동료의 독립적인 근거와 실제 회신을 확인하고 이번 검토 결과를 보고하세요. 이 턴에서는 최초안 검토만 마치세요.',
 'phase1':'앞선 실제 동료 검토의 근거를 반영해 최초안을 수정하고 같은 검토 담당 a1에게 재검토받으세요. 동료의 실제 회신을 확인해 수정안의 검토 결과를 보고하세요. 별도 경계조건 검토는 다음 업무로 남기세요.',
 'phase2':'새 업무로 0+0=0 경계조건을 같은 검토 담당 a1에게 독립 검토받으세요. 동료의 실제 근거와 회신을 확인한 뒤 이 협업의 세 업무 결과를 정리해 마치세요.'}
class Actor:
 def __init__(self,role):self.role=role;self.profile=ROOT/'actors'/role/'codex-home';self.cid=None;self.runs=[];self.proc=None
 def launch(self,phase):
  run=ROOT/'actors'/self.role/phase;run.mkdir(parents=True,mode=0o700);(run/'actor/proxies').mkdir(parents=True,mode=0o700)
  goal=GOALS['reviewer'if self.role=='reviewer'else phase]+SUFFIX
  args=[M['codex'],'exec','--ignore-user-config','--json','--sandbox','workspace-write','-c','approval_policy="never"',
   '-c','mcp_servers.xsm.command='+json.dumps(M['python']),'-c','mcp_servers.xsm.args='+json.dumps(['-B',str(PAYLOAD/'proxy.py'),str(run/'actor'),str(PAYLOAD)]),
   '-c','mcp_servers.xsm.cwd='+json.dumps(str(PAYLOAD))]
  env=dict(ENV,CODEX_HOME=str(self.profile))
  for key,value in env.items():
   if key in('XSM_HOME','CODEX_HOME','PYTHONPATH','PYTHONDONTWRITEBYTECODE','TMPDIR','XSM_TEMP','XSM_NET_BINARY','XSM_CODEX'):
    args+=['-c','mcp_servers.xsm.env.'+key+'='+json.dumps(value)]
  if self.cid:args+=['resume',self.cid]
  args+=[goal]
  out=(run/'native.jsonl').open('wb');err=(run/'native.stderr').open('wb')
  self.proc=subprocess.Popen(args,cwd=str(WORK),env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True);out.close();err.close()
  owner={'role':self.role,'phase':phase,'pid':self.proc.pid,'lstart':starttime(self.proc.pid),'argv':args,'model_override':False,'CODEX_HOME':str(self.profile),'run':str(run)}
  save(run/'owner.json',owner);self.runs.append(owner);return owner
 def refresh(self):
  if not self.runs:return None
  owner=self.runs[-1];run=Path(owner['run']);events=rows(run/'native.jsonl');cid=next((e.get('thread_id')for e in events if e.get('type')=='thread.started'),None)
  if cid and self.cid and cid!=self.cid:raise RuntimeError('resumed-actual-CID-changed')
  if cid:self.cid=cid
  registered=read(run/'registration.json');current=None;handle=None
  for path in(run/'actor/proxies').glob('*/handles.json'):
   value=read(path)
   if not value:continue
   native=next((r for r in value['native_ancestor_chain']if Path(r['comm']).name=='codex'and r['pid']==owner['pid']and r['lstart']==owner['lstart']and starttime(r['pid'])==r['lstart']),None)
   if native:current=native;handle=value;break
  if cid and current and handle:
   db=self.profile/'state_5.sqlite'
   if db.exists():
    con=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=1)
    try:row=con.execute('select id,name,cwd,rollout_path from threads where id=?',(cid,)).fetchone()
    finally:con.close()
    if row and os.path.realpath(row[2])==str(WORK)and (not registered or registered['native']['pid']!=current['pid']or registered['native']['lstart']!=current['lstart']):
     config.add_home(str(self.profile),'codex')
     record=registry.upsert('codex',str(self.profile),cid,current['pid'],row[2],name='a1'if self.role=='reviewer'else'writer',mcp_pid=handle['server']['pid'])
     registered={'CID':cid,'native':current,'MCP_server':handle['server'],'provider_row':list(row),'record':record,'basis':'actual thread.started + read-only provider DB + current live native PID and MCP ancestry; setup only'}
     save(run/'registration.json',registered)
  return {'role':self.role,'phase':owner['phase'],'CID':cid,'registered':bool(cid and registered and current and registered['CID']==cid and registered['native']['pid']==current['pid']and registered['native']['lstart']==current['lstart']),
    'alive':self.proc.poll()is None,'exit':self.proc.poll(),'events':len(events),'error':next((e.get('message')for e in reversed(events)if e.get('type')=='error'),None)}
 def cleanup(self):
  known=[]
  for owner in self.runs:
   known.append({'pid':owner['pid'],'lstart':owner['lstart']})
   for path in(Path(owner['run'])/'actor/proxies').glob('*/handles.json'):
    value=read(path)
    if value:known.extend([value['proxy'],value['server']]);known.extend(r for r in value['native_ancestor_chain']if Path(r['comm']).name in('codex','codex-code-mode-host'))
  signals=[]
  for item in known:
   if item.get('lstart')and starttime(item['pid'])==item['lstart']:
    try:os.kill(item['pid'],signal.SIGTERM);signals.append(item['pid'])
    except ProcessLookupError:pass
  if signals:time.sleep(.3)
  return {'signals':signals,'remaining_owned':[item for item in known if item.get('lstart')and starttime(item['pid'])==item['lstart']]}
def questions():
 result=[]
 for path in(STATE/'questions').glob('*.json'):
  value=read(path)
  if value:result.append(value)
 return result
