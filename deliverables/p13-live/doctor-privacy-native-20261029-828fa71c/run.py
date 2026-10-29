"""One default-permission postfix doctor CLI; seed only private diagnostic state."""
import os,sys,json,sqlite3,subprocess,time,hashlib,pathlib,uuid,shutil,stat
ROOT=pathlib.Path('/private/tmp/doctor-privacy-native-1qw1twk2')
PUBLIC=pathlib.Path(__file__).resolve().parent
REPO=PUBLIC.parents[2]
MANIFEST=REPO/'deliverables/p13-live/doctor-privacy-source-manifest.json'
os.umask(0o077);sys.dont_write_bytecode=True
def sha(b):return hashlib.sha256(b).hexdigest()
def load(p):return json.loads(pathlib.Path(p).read_text())
def save(p,x):
 pathlib.Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');pathlib.Path(p).chmod(0o600)
def ps(pid):
 out={}
 for key in ['pid','ppid','lstart','comm']:
  r=subprocess.run(['ps','-o',key+'=','-p',str(pid)],capture_output=True,text=True)
  out[key]=r.stdout.strip()
 return out
def metadata(home):
 result={}
 for name in ['config.toml','hooks.json','settings.json']:
  p=home/name
  try:s=p.stat();result[name]={'inode':s.st_ino,'size':s.st_size,'mtime_ns':s.st_mtime_ns,'mode':stat.S_IMODE(s.st_mode)}
  except FileNotFoundError:result[name]=None
 return result
def ledger_hashes():return {p.name:{'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())}for p in(ROOT/'state/ledger').glob('*.json')}
fm=load(MANIFEST);SOURCE=pathlib.Path(fm['snapshot']);sid=os.environ.get('CODEX_THREAD_ID');home=pathlib.Path(os.environ.get('CODEX_HOME','')).resolve()
assert sid and home.is_dir(),'actual current native identifiers unavailable'
assert all(sha((SOURCE/n).read_bytes())==h for n,h in fm['files'].items()),'frozen manifest mismatch'
assert sha((SOURCE/'xsm/install.py').read_bytes())=='a8e712de6e8b2b9f368946333a6c8793168c6734484be45a60dbe967d0aa1960'
chain=[];pid=os.getpid();native=None
for _ in range(12):
 row=ps(pid);chain.append(row)
 if pathlib.Path(row['comm']).name=='codex':native=row;break
 if row['ppid']in ['','0','1']:break
 pid=int(row['ppid'])
assert native and native['lstart'],'actual native ancestor unavailable'
con=sqlite3.connect('file:'+str(home/'state_5.sqlite')+'?mode=ro',uri=True)
try:
 row=con.execute('select id,name,cwd,source,rollout_path from threads where id=?',(sid,)).fetchone()
finally:con.close()
assert row and row[0]==sid,'actual native DB identity unavailable'
with pathlib.Path(row[4]).open()as stream:head=json.loads(stream.readline())
assert head.get('type')=='session_meta'and head['payload']['id']==sid,'actual native rollout header mismatch'
observed={'CID':sid,'home':str(home),'native':native,'process_chain':chain,'native_DB':dict(zip(['id','name','cwd','source','rollout_path'],row)),'header_CID_matches':True,'PID_is_shared_runtime':True,'scope':'observation only, never communication permission or caller certainty'}
save(ROOT/'native-observation-before.json',observed)
before_meta=metadata(home)
os.environ['XSM_HOME']=str(ROOT/'state');os.environ['PYTHONDONTWRITEBYTECODE']='1';sys.path.insert(0,str(SOURCE))
from xsm import paths,config,registry,ledger
paths.ensure_home();config.add_home(str(home),'codex')
record=registry.upsert('codex',str(home),sid,int(native['pid']),row[2],name=row[1])
assert len(config.homes())==1 and len(registry.raw_records())==1
assert record['session_id']==sid and record['home']==str(home)and record['lstart']==native['lstart']
save(ROOT/'registered-observation.json',record)
markers={name:'DOCTOR_'+name.upper()+'_'+uuid.uuid4().hex for name in ['body','nested','raw_error','unknown_error','known_detail','allowed_nested']}
markers['invite']='https://invite.invalid/'+uuid.uuid4().hex
ids={name:'privacy-'+name+'-'+uuid.uuid4().hex[:10]for name in ['queued','unknown','error','blocked1','blocked2']}
for name,mid in ids.items():
 ledger.queued(mid,record,record,'diagnostic-fixture-only','note',markers['body']+' '+markers['invite'])
 file=pathlib.Path(paths.path(paths.LEDGER,mid+'.json'));data=load(file)
 data['t']=time.time()-600;data['body']=markers['body'];data['arbitrary']={'nested':{'message':markers['nested'],'invite':markers['invite']}}
 data['to']['private']={'body':markers['nested']};data['from']['ref']={'body':markers['allowed_nested']}
 save(file,data)
ledger.unknown(ids['unknown'],markers['unknown_error']+' '+markers['invite'])
ledger.failed(ids['error'],markers['raw_error']+': '+markers['invite'])
for name in ['blocked1','blocked2']:ledger.failed(ids[name],'sandbox-blocked: '+markers['known_detail']+' '+markers['invite'])
event={'t':time.time(),'reason':'internal error '+markers['raw_error'],'body':markers['body'],'invite':markers['invite']}
(ROOT/'state/decisions.jsonl').write_text(json.dumps(event)+'\n');(ROOT/'state/decisions.jsonl').chmod(0o600)
save(ROOT/'markers.private.json',markers);save(ROOT/'ids.private.json',ids)
before=ledger_hashes();save(ROOT/'ledger-hashes-before.json',before)
for file in(ROOT/'state/ledger').glob('*.json'):shutil.copyfile(file,ROOT/'ledger-before'/file.name)
env=dict(os.environ,XSM_HOME=str(ROOT/'state'),PYTHONPATH=str(SOURCE),PYTHONDONTWRITEBYTECODE='1')
argv=[sys.executable,'-B','-m','xsm','doctor','--json']
result={'started_at':time.time(),'source':str(SOURCE),'source_manifest_sha256':sha(MANIFEST.read_bytes()),'argv':argv,'cwd':str(SOURCE),'private_root':str(ROOT),'interpreter':sys.version,'doctor_invocations':1,'new_models':0,'new_native_TUIs':0,'added_sandbox':False,'sitecustomize_observer':False,'native_PID_before':native,'native_CID_sha256':sha(sid.encode()),'actual_home_count':1,'actual_session_count':1,'registration_scope':'diagnostic only; no permission/caller-certainty claim','marker_hashes':{k:sha(v.encode())for k,v in markers.items()}}
save(ROOT/'run-meta.json',result)
stdout=ROOT/'doctor.stdout';stderr=ROOT/'doctor.stderr'
with stdout.open('wb')as out,stderr.open('wb')as err:
 stdout.chmod(0o600);stderr.chmod(0o600)
 proc=subprocess.Popen(argv,cwd=str(SOURCE),env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err)
 result['doctor_PID']=proc.pid;save(ROOT/'run-meta.json',result)
 try:code=proc.wait(timeout=90)
 except subprocess.TimeoutExpired:code=None;result['timeout']='owned diagnostic still pending; no signal sent'
result['exit_code']=code;result['finished_at']=time.time();result['native_PID_after']=ps(int(native['pid']));result['native_same_generation']=result['native_PID_after']['lstart']==native['lstart'];result['native_metadata_before']=before_meta;result['native_metadata_after']=metadata(home)
after=ledger_hashes();save(ROOT/'ledger-hashes-after.json',after);result['ledger_bytes_unchanged']=before==after
result['source315_after_matches']=all(sha((SOURCE/n).read_bytes())==h for n,h in fm['files'].items())
result['streams']={name:{'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p.read_bytes()),'mode':oct(stat.S_IMODE(p.stat().st_mode))}for name,p in [('stdout',stdout),('stderr',stderr)]}
if code is not None:
 raw=stdout.read_bytes()+stderr.read_bytes();result['marker_leaks']={k:v.encode()in raw for k,v in markers.items()}
 try:
  report=json.loads(stdout.read_bytes());stuck=report['stuck']
  utility={'queued_IDs':[x['id']for x in stuck['undelivered']],'uncertain_IDs':[x['id']for x in stuck['uncertain']],'send_failures':stuck['send_failures'],'queued_statuses':[x['status']for x in stuck['undelivered']],'uncertain_statuses':[x['status']for x in stuck['uncertain']],'queued_ages_seconds':[time.time()-x['t']for x in stuck['undelivered']],'diagnostic_row_keys':[sorted(x)for x in stuck['undelivered']+stuck['uncertain']],'scalar_endpoints':all(all(isinstance(v,str)for v in x[k].values())for x in stuck['undelivered']+stuck['uncertain']for k in ['from','to'])}
  result['utility']=utility;result['utility_preserved']=utility['queued_IDs']==[ids['queued']]and utility['uncertain_IDs']==[ids['unknown']]and utility['send_failures']=={'other':1,'sandbox-blocked':2}and utility['scalar_endpoints']
  result['doctor_observations']={'home_count':len(report.get('homes',[])),'sessions':report.get('sessions'),'selected_home_metadata_present':str(home).encode()in stdout.read_bytes(),'decisions_seen':report.get('decisions_seen'),'hook_errors_recent':report.get('hook_errors_recent'),'setup_status':(report.get('setup')or{}).get('status'),'setup_rows':[{k:r.get(k)for k in ['runtime','settings','trust','process','home_match','mcp','first_roundtrip']}for r in(report.get('setup')or{}).get('homes',[])]}
 except Exception as exc:result['parse_or_check_error']={'type':type(exc).__name__}
save(ROOT/'run-meta.json',result)
print(json.dumps({'root':str(ROOT),'exit_code':code,'marker_leaks':result.get('marker_leaks'),'utility_preserved':result.get('utility_preserved'),'ledger_bytes_unchanged':result['ledger_bytes_unchanged'],'native_same_generation':result['native_same_generation'],'source315_after_matches':result['source315_after_matches']},ensure_ascii=False))
