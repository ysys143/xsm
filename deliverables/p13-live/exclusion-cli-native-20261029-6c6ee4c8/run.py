"""Current native caller: direct APIs and actual in-process CLI parser, no mocks."""
import os,sys,json,pathlib,hashlib,subprocess,sqlite3,time,uuid,stat,contextlib,inspect
ROOT=pathlib.Path('/private/tmp/exclusion-cli-native-jhehrztq')
PUBLIC=pathlib.Path(__file__).resolve().parent
REPO=PUBLIC.parents[2]
SOURCE=pathlib.Path('/private/tmp/xsm-doctor-privacy-frozen-47o6orah')
os.umask(0o077);sys.dont_write_bytecode=True
def sha(b):return hashlib.sha256(b).hexdigest()
def load(p):return json.loads(pathlib.Path(p).read_text())
def save(p,x):pathlib.Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');pathlib.Path(p).chmod(0o600)
def metadata(p):
 s=pathlib.Path(p).stat();return {'dev':s.st_dev,'inode':s.st_ino,'size':s.st_size,'mtime_ns':s.st_mtime_ns,'mode':stat.S_IMODE(s.st_mode)}
def artifact_counts(state):
 return {'ledger':len(list((state/'ledger').glob('*.json'))),'canonical':len(list((state/'handoffs').glob('*/*.json'))),'copy_records':len(list((state/'file-copies').glob('*/*/record.json'))),'copy_blobs':len(list((state/'file-copies').rglob('*.blob')))}
def worker(mode):
 state=ROOT/('state-'+mode);os.environ['XSM_HOME']=str(state);os.environ['PYTHONDONTWRITEBYTECODE']='1';sys.path.insert(0,str(SOURCE))
 from xsm import paths,config,registry,directory,files,cli
 paths.ensure_home();facts=load(ROOT/'native-facts.private.json');before=load(ROOT/'originals.private.json')
 assert not os.environ.get('CODEX_SANDBOX')and not os.environ.get('XSM_SANDBOXED')
 assert os.environ.get('CODEX_THREAD_ID')==facts['CID']and os.path.realpath(os.environ['CODEX_HOME'])==facts['home']
 assert os.path.realpath(os.getcwd())==facts['cwd']
 alias=ROOT/'repo-alias';assert os.path.realpath(alias)==facts['cwd']
 caller=registry.upsert('codex',facts['home'],facts['CID'],int(facts['native']['pid']),facts['cwd'],name=facts['name'])
 assert caller['cwd']==facts['cwd']and caller['lstart']==facts['native']['lstart']
 config.set_value('directory_excluded_paths',[str(alias)]if mode=='A17'else[str(ROOT/'excluded')])
 expected={'LICENSE','apikey.env',pathlib.Path(before['excluded']['path']).name}
 opens=[]
 def observe(event,args):
  if event=='open'and args and isinstance(args[0],(str,bytes)):
   path=os.fsdecode(args[0])
   if pathlib.Path(path).name in expected:opens.append({'at':time.time(),'path':path,'mode':str(args[1]),'flags':args[2]})
 sys.addaudithook(observe)
 result={'mode':mode,'trace':[],'caller_fields':caller,'caller_fields_not_forced':['basis','certainty','identity_certainty'],'API_signatures':{n:str(inspect.signature(fn))for n,fn in [('files.prepare_cli',files.prepare_cli),('directory.discover',directory.discover),('registry.upsert',registry.upsert),('cli.main',cli.main)]},'sandbox_markers_before':{k:k in os.environ for k in ['CODEX_SANDBOX','XSM_SANDBOXED']}}
 def direct(label,path):
  rid=uuid.uuid4().hex;entry={'kind':'direct files.prepare_cli API','label':label,'request_id':rid,'source':str(path)}
  try:
   value=files.prepare_cli(caller,rid,'attachment-negative-evaluation',[str(path)],limits=files.product_limits());entry.update({'unexpected_success':True,'manifest_id':value.get('id')})
  except files.FileError as exc:entry.update({'code':exc.code,'stored':exc.stored,'reason':str(exc),'body_sent':False})
  entry['counts']=artifact_counts(state);result['trace'].append(entry)
 if mode=='A17':
  result['same_realpath']=os.path.realpath(alias)==os.path.realpath(facts['cwd'])
  pointer_before={p.name:sha(p.read_bytes())for p in(state/'sessions').glob('*.json')}
  for label,expression in [('canonical',facts['cwd']),('alias',str(alias))]:
   blocked=registry.upsert('codex',facts['home'],facts['CID'],int(facts['native']['pid']),expression,name=facts['name'])
   result['trace'].append({'kind':'direct registry.upsert API','expression':label,'registered':blocked.get('registered'),'excluded':blocked.get('excluded'),'cwd':blocked.get('cwd')})
  result['pointer_bytes_unchanged']=pointer_before=={p.name:sha(p.read_bytes())for p in(state/'sessions').glob('*.json')}
  found=directory.discover(caller,records=[caller]);result['trace'].append({'kind':'direct directory.discover API','result':found})
  result['exclusion_status']={label:directory.exclusion_status(path)for label,path in [('canonical',facts['cwd']),('alias',str(alias))]}
  direct('canonical-public-LICENSE',REPO/'LICENSE');direct('alias-public-LICENSE',alias/'LICENSE')
 else:
  for label in ['excluded','sensitive']:direct(label,pathlib.Path(before[label]['path']))
  for label in ['excluded','sensitive']:
   rid=uuid.uuid4().hex;argv=['send','codex:'+facts['CID'],'--text','attachment-negative-evaluation','--attachment',before[label]['path'],'--request-id',rid,'--json']
   out=ROOT/(label+'.cli.stdout');err=ROOT/(label+'.cli.stderr')
   with out.open('w')as sout,err.open('w')as serr,contextlib.redirect_stdout(sout),contextlib.redirect_stderr(serr):
    try:code=cli.main(argv)
    except SystemExit as exc:code=exc.code
   ctx=registry.last_identity();output=out.read_text()+err.read_text()
   try:value=json.loads(output)
   except ValueError:value={'unparsed':True,'output_sha256':sha(output.encode())}
   result['trace'].append({'kind':'actual cli.main parser, in-process (not python -m subprocess)','label':label,'argv':argv,'exit_code':code,'response':value,'natural_identity_context':{'basis':getattr(ctx,'basis',None),'sure':getattr(ctx,'sure',None)},'counts':artifact_counts(state)})
 result['protected_content_open_events']=opens;result['counts_after']=artifact_counts(state);result['registry_records']=len(registry.raw_records());result['sandbox_markers_after']={k:k in os.environ for k in ['CODEX_SANDBOX','XSM_SANDBOXED']}
 result['original_stat_after']={key:metadata(x['path'])for key,x in before.items()}
 save(ROOT/(mode+'.private.json'),result)
 print(json.dumps({'mode':mode,'protected_content_open_events':len(opens),'counts':result['counts_after'],'codes':[x.get('code')or(x.get('response')or{}).get('code')for x in result['trace']if 'prepare_cli'in x['kind']or'cli.main'in x['kind']]}),flush=True)
def parent():
 assert not os.environ.get('CODEX_SANDBOX')and not os.environ.get('XSM_SANDBOXED'),'existing marker present; never clear it'
 home=pathlib.Path(os.environ['CODEX_HOME']).resolve();sid=os.environ['CODEX_THREAD_ID'];pid=os.getpid();chain=[];native=None
 for _ in range(12):
  row={k:subprocess.check_output(['ps','-o',k+'=','-p',str(pid)],text=True).strip()for k in ['pid','ppid','comm','lstart']};chain.append(row)
  if pathlib.Path(row['comm']).name=='codex':native=row;break
  if row['ppid']in ['','0','1']:break
  pid=int(row['ppid'])
 assert native
 con=sqlite3.connect('file:'+str(home/'state_5.sqlite')+'?mode=ro',uri=True)
 try:row=con.execute('select id,name,cwd,rollout_path from threads where id=?',(sid,)).fetchone()
 finally:con.close()
 assert row and row[0]==sid and os.path.realpath(row[2])==str(REPO.resolve())==os.path.realpath(os.getcwd())
 with pathlib.Path(row[3]).open()as stream:head=json.loads(stream.readline())
 assert head['payload']['id']==sid
 facts={'CID':sid,'home':str(home),'name':row[1],'cwd':os.path.realpath(row[2]),'native':native,'OS_chain':chain,'native_DB_verified':True,'rollout_header_verified':True}
 save(ROOT/'native-facts.private.json',facts)
 fm=load(REPO/'deliverables/p13-live/doctor-privacy-source-manifest.json');assert fm['snapshot']==str(SOURCE)
 assert all(sha((SOURCE/n).read_bytes())==h for n,h in fm['files'].items())
 (ROOT/'repo-alias').symlink_to(REPO,target_is_directory=True)
 (ROOT/'excluded').mkdir(mode=0o700);(ROOT/'materials').mkdir(mode=0o700)
 originals={}
 for label,path in [('excluded',ROOT/'excluded'/('private-note-'+uuid.uuid4().hex[:8]+'.txt')),('sensitive',ROOT/'materials/apikey.env')]:
  data=('SYNTHETIC_'+label+'_'+uuid.uuid4().hex+'\n').encode();path.write_bytes(data);path.chmod(0o600)
  originals[label]={'path':str(path),'setup_sha256':sha(data),'setup_stat':metadata(path),'digest_source':'generated bytes before exclusion; never reopen original'}
 license_path=REPO/'LICENSE';data=license_path.read_bytes();originals['LICENSE']={'path':str(license_path),'setup_sha256':sha(data),'setup_stat':metadata(license_path),'digest_source':'public LICENSE before private exclusion'};del data
 save(ROOT/'originals.private.json',originals)
 results=[]
 for mode in ['A17','A19']:
  args=[sys.executable,'-B',str(pathlib.Path(__file__).resolve()),'--worker',mode]
  proc=subprocess.run(args,cwd=str(REPO),env=dict(os.environ),capture_output=True,timeout=75)
  (ROOT/(mode+'.worker.stdout')).write_bytes(proc.stdout);(ROOT/(mode+'.worker.stderr')).write_bytes(proc.stderr)
  results.append({'mode':mode,'argv':args,'exit_code':proc.returncode,'stdout_sha256':sha(proc.stdout),'stderr_sha256':sha(proc.stderr)})
 save(ROOT/'worker-results.json',results)
 save(ROOT/'source-proof.json',{'frozen315_matches':all(sha((SOURCE/n).read_bytes())==h for n,h in fm['files'].items()),'current_primary_mismatches':[n for n in fm['stable_product_paths']if sha((REPO/n).read_bytes())!=fm['files'][n]],'new_models':0,'new_native_TUIs':0,'markers_cleared':False})
 print(json.dumps({'root':str(ROOT),'workers':[{'mode':x['mode'],'exit_code':x['exit_code']}for x in results]}),flush=True)
if __name__=='__main__':
 if len(sys.argv)>2 and sys.argv[1]=='--worker':worker(sys.argv[2])
 else:parent()
