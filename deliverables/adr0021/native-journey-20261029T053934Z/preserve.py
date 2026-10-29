"""Read-only evidence snapshot, then terminate only owned actors; services retained."""
import json,os,signal,sqlite3,subprocess,sys,time,hashlib,tarfile
from pathlib import Path
R=Path(sys.argv[1]);os.umask(0o077)
def load(p):
 try:return json.loads(p.read_text())
 except (OSError,ValueError):return None
def start(pid):return subprocess.run(['ps','-p',str(pid),'-o','lstart='],capture_output=True,text=True).stdout.strip()or None
def guard():
 values={}
 for p in Path('/Users/jaesolshin').glob('.codex*'):
  if not p.is_dir():continue
  for n in ('config.toml','hooks.json','settings.json','AGENTS.md'):
   f=p/n;values[str(f)]=hashlib.sha256(f.read_bytes()).hexdigest()if f.is_file()else None
  f=p/'auth.json'
  if f.is_file():s=f.stat();values[str(f)+':metadata-only']={'mode':s.st_mode&511,'size':s.st_size,'inode':s.st_ino,'mtime_ns':s.st_mtime_ns}
 return values
owned=[]
for f in [R/'actor-owner.json',R/'service-owner.json']:
 v=load(f)
 if v:owned.append(dict(v,kind='actor'if f.name=='actor-owner.json'else'service'))
for f in (R/'actor/proxies').glob('*/handles.json'):
 h=load(f)
 if h:
  owned.extend(dict(h[k],kind=k)for k in ('proxy','server'))
  owned.extend(dict(r,kind='native')for r in h['native_ancestor_chain']if Path(r['comm']).name=='codex')
before=[{'kind':v['kind'],'pid':v['pid'],'lstart':v['lstart'],'live_lstart':start(v['pid'])}for v in owned]
signals=[]
for v in owned:
 if v['kind']!='service'and start(v['pid'])==v['lstart']:
  try:os.kill(v['pid'],signal.SIGTERM);signals.append({'pid':v['pid'],'lstart':v['lstart'],'signal':'TERM'})
  except ProcessLookupError:pass
time.sleep(.3)
models=[];provider=[]
db=R/'codex-home/state_5.sqlite'
if db.exists():
 con=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
 try:
  cols=[x[1]for x in con.execute('pragma table_info(threads)')];wanted=[x for x in ('id','name','cwd','source','rollout_path','model_provider','model','sandbox_policy','approval_mode')if x in cols]
  rows=con.execute('select '+','.join(wanted)+' from threads').fetchall()
  for row in rows:
   item=dict(zip(wanted,row));provider.append(item)
   p=Path(item['rollout_path'])
   if p.is_file()and str(p).startswith(str(R)):
    for line in p.read_text().splitlines():
     try:e=json.loads(line)
     except ValueError:continue
     if e.get('type')in ('session_meta','turn_context'):
      pl=e.get('payload')or{};models.append({'rollout':str(p),'timestamp':e.get('timestamp'),'type':e['type'],'fields':{k:pl[k]for k in ('id','model','model_provider','cwd','approval_policy','sandbox_policy','cli_version')if k in pl}})
 finally:con.close()
state={}
for dirname,pattern in (('questions','*.json'),('ledger','*.json'),('handoffs','*/*.json'),('sessions','*.json'),('network/messages','*/*.json')):
 for p in (R/'state'/dirname).glob(pattern):state[str(p.relative_to(R))]=load(p)
after=guard();beforeprofile=load(R/'profile-before.json')
result={'at':time.time(),'root':str(R),'processes_before':before,'actor_stop_signals':signals,'processes_after':[{'kind':v['kind'],'pid':v['pid'],'lstart':v['lstart'],'same_generation_alive':start(v['pid'])==v['lstart']}for v in owned],'profile_before':beforeprofile,'profile_after':after,'profile_unchanged':beforeprofile==after,'provider_DB_rows':provider,'observed_model_records':models,'product_state_read_only_snapshot':state,'service_state_and_private_keys_retained':True,'new_native_attempts_halted':True}
(R/'preserved-evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
with tarfile.open(fileobj=sys.stdout.buffer,mode='w:gz')as archive:
 for name in ('preserved-evidence.json','preflight.json','profile-before.json','service-owner.json','actor-owner.json','registration.json','halt-observation.json','halt-signals.json','actor','initial-unregistered','code-host-first-attempt','disabled-host-resume','raw/transport.jsonl','raw/service.stdout','raw/service.stderr'):
  p=R/name
  if p.exists():archive.add(p,arcname=name)
