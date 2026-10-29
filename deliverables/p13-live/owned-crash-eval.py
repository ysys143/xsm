"""Real subscribed owned native turns; fault only at public journal checkpoints.
Raw evidence stays in a fresh private tmp. No executor/readback/result injection.
"""
import hashlib,json,os,signal,subprocess,sys,tempfile,time
from pathlib import Path
FROZEN=Path('/private/tmp/xsm-p13-postqa-frozen-bukwksw6')
REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(FROZEN))

def dump(path,value):
 path.write_text(json.dumps(value,ensure_ascii=False,indent=2));os.chmod(path,0o600)
def digest(value):
 return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def child_mode(root,cut,action):
 from xsm import workers,owned_requests
 f=json.loads((root/'fixture.json').read_text());owner=f['owner'];row=f['cases'][cut]
 def checkpoint(stage,request):
  if stage==cut:
   dump(root/(cut+'-cut.json'),{'stage':stage,'pid':os.getpid(),'at':time.time()})
   os.kill(os.getpid(),signal.SIGKILL)
 quiet=lambda w,r:workers.publish_owned(w,r,wake=False)
 if action=='run':
  result=workers.run_owned(f['worker'],owner,row['body'],work_context=row['context'],request_id=row['id'],reply_sender=quiet,checkpoint=checkpoint)
 elif action=='resume':
  result=workers.run_owned(f['worker'],owner,row['body'],work_context=row['context'],request_id=row['id'],reply_sender=quiet)
 elif action=='reconcile':result=workers.reconcile_owned(f['worker'],owner,row['id'],reply_sender=quiet)
 elif action=='retry':result=workers.resend_owned(f['worker'],owner,row['id'],reply_sender=quiet)
 else:raise ValueError(action)
 dump(root/(cut+'-'+action+'-result.json'),result)

def main():
 started=time.monotonic();deadline=started+25*60
 from xsm import registry,paths,workers,owned_requests,identity,config
 owner=registry.me()
 if not owner:raise RuntimeError('no real native owner')
 original=dict(owner)
 root=Path(tempfile.mkdtemp(prefix='p13-owned-crash-',dir='/private/tmp'));os.chmod(root,0o700)
 os.environ['XSM_HOME']=str(root/'state');paths.HOME=str(root/'state')
 # Preserve the exact existing owner endpoint and recorded cwd. No invented scope.
 owner=registry.upsert(owner['runtime'],owner['home'],owner['session_id'],owner['pid'],owner['cwd'],name=owner.get('name'))
 worker=workers.create_owned('codex',caller=owner,name='crash-native',cwd=owner['cwd'],home=owner['home'])
 stages=['request-stored','acknowledged','after-execution','result-stored','reply-sent']
 cases={}
 for n,cut in enumerate(stages):
  folder=root/('effect-'+str(n));folder.mkdir(mode=0o700)
  marker=folder/'counter.txt'
  body=('제품 종료경계 QA입니다. 자신의 기본 파일/셸 도구로 '+str(marker)+' 파일을 읽고 없으면 0으로 간주한 뒤 숫자를 정확히 1 증가시켜 저장하세요. '
        '이 파일 외에는 변경하지 마세요. 실패하거나 권한이 거부되면 우회하거나 재시도하지 말고 failed로 답하세요. '
        '최종 응답은 JSON 하나 {"body":"P13-owned-crash '+cut+' counter=<실제로 읽어 확인한 숫자>","outcome":"succeeded 또는 failed"}로 답하세요. '
        '동료 송신이나 별도 worker는 실행하지 마세요.')
  cases[cut]={'id':'p13-crash-'+root.name.rsplit('-',1)[-1]+'-'+str(n),'context':'isolated-cut-'+str(n),'body':body,'marker':str(marker)}
 fixture={'owner':owner,'worker':worker['name'],'cases':cases};dump(root/'fixture.json',fixture)
 manifest=json.loads((REPO/'deliverables/p13-live/post-qa-source-manifest.json').read_text())
 checks={p:hashlib.sha256((FROZEN/p).read_bytes()).hexdigest()==h for p,h in manifest['files'].items()}
 if not all(checks.values()):raise RuntimeError('frozen manifest mismatch')
 env=dict(os.environ);env['PYTHONPATH']=str(FROZEN);env['PYTHONDONTWRITEBYTECODE']='1'
 report={'private_root':str(root),'frozen':str(FROZEN),'manifest_checked_files':len(checks),'manifest_match':all(checks.values()),
 'owner_identity':'actual registry.me endpoint unchanged; registered only in private state','owner_recorded_cwd':original['cwd'],
 'fixture_fields':['worker display name','request IDs','work_context','task bodies','private effect paths'],
 'native_profile':'existing owner Codex home; no config/auth copy or override',
 'native_mcp':'existing profile default MCP settings, not factory override; tool events counted from native stdout',
 'publication':'actual publish_owned(wake=False); canonical private storage, not native UI delivery',
 'model_permissions_adjusted':False,'executor_mocked':False,'readback_injected':False,'automatic_model_retries':0,'cases':[]}
 out=REPO/'deliverables/p13-live/owned-crash-results.json'
 dump(out,report)
 def invoke(cut,action):
  remaining=deadline-time.monotonic()
  if remaining<=0:raise TimeoutError('25 minute cap')
  with open(root/(cut+'-'+action+'.stdout'),'w') as stdout,open(root/(cut+'-'+action+'.stderr'),'w') as stderr:
   p=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--child',str(root),cut,action],cwd=str(FROZEN),env=env,stdout=stdout,stderr=stderr)
   try:code=p.wait(timeout=min(200,remaining))
   except subprocess.TimeoutExpired:
    p.kill();p.wait();return {'returncode':-9,'controller_timeout':True}
  value={'returncode':code,'controller_pid':p.pid}
  f=root/(cut+'-'+action+'-result.json')
  if f.exists():value['status']=json.loads(f.read_text())['status']
  return value
 def state(cut):return workers.owned_status(worker['name'],owner,cases[cut]['id'])
 def summary(r):
  return {k:r.get(k) for k in ('id','status','reply_id','digest','result_digest','execution_state','slot_occupied')} | {'result_sha256':digest(r['result']) if r.get('result') else None}
 for cut in stages:
  row={'boundary':cut,'id':cases[cut]['id'],'resume_owner':'coordinator if this cell remains unverified','resume_condition':'same frozen source, retained private journal/native stdout and existing subscription authorization; no forced rerun of unknown effects'}
  try:
   row['initial']=invoke(cut,'run');before=state(cut);dump(root/(cut+'-before.json'),before)
   row['boundary_reached']=(root/(cut+'-cut.json')).exists();row['before']=summary(before)
   row['native_turns_at_cut']=int(bool(before.get('child')))
   row['effect_at_cut']=Path(cases[cut]['marker']).read_text().strip() if Path(cases[cut]['marker']).exists() else None
   owned_requests.recover(owner);recovered=state(cut);row['recovered']=summary(recovered)
   if row['boundary_reached']:
    if cut=='after-execution':
     # Same-ID resume MUST remain unknown, not start another native turn.
     row['fenced_same_id_resume']=invoke(cut,'resume')
     row['recovery_action']='reconcile default completed-native stdout readback'
     row['recovery']=invoke(cut,'reconcile')
    elif cut in ('result-stored','reply-sent'):
     row['recovery_action']='resend saved result only';row['recovery']=invoke(cut,'retry')
    else:
     row['recovery_action']='same ID/body/context resume after proven pre-run controller death';row['recovery']=invoke(cut,'resume')
   else:row['unverified_reason']='requested journal cut was not reached; no substitute run'
   final=state(cut);dump(root/(cut+'-final.json'),final);row['final']=summary(final)
   row['effect_final']=Path(cases[cut]['marker']).read_text().strip() if Path(cases[cut]['marker']).exists() else None
   child=final.get('child') or {};row['native_child']={k:child.get(k) for k in ('pid','lstart','returncode')}
   row['native_CID']=(final.get('result') or {}).get('native_session_id')
   row['native_evidence']=(final.get('result') or {}).get('native_evidence')
   row['native_turns_total']=int(bool(child));row['stored_reply_unchanged']=before.get('result')==final.get('result') if before.get('result') else None
   row['reply_id_unchanged']=before.get('reply_id')==final.get('reply_id') if before.get('reply_id') else None
   row['send_evidence']={k:(final.get('send_evidence') or {}).get(k) for k in ('id','status','wake')}
   stdout=Path(child['stdout']) if child.get('stdout') else None
   if stdout and stdout.exists():
    row['stdout_sha256']=hashlib.sha256(stdout.read_bytes()).hexdigest();events=[]
    for line in stdout.read_text().splitlines():
     try:events.append(json.loads(line))
     except ValueError:pass
    tools=[e.get('item',{}) for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type') in ('command_execution','mcp_tool_call','file_change')]
    row['native_tools']=[{k:t.get(k) for k in ('type','server','tool','exit_code','status') if k in t} for t in tools]
    row['actual_turn_started_events']=sum(e.get('type')=='turn.started' for e in events)
    row['terminal_completed_events']=sum(e.get('type')=='turn.completed' for e in events)
   row['remaining_child_alive']=owned_requests._alive(child)
  except Exception as exc:row['unverified_reason']=type(exc).__name__+': '+str(exc)
  report['cases'].append(row);report['elapsed_seconds']=round(time.monotonic()-started,2);dump(out,report)
  print(json.dumps({'boundary':cut,'reached':row.get('boundary_reached'),'final':row.get('final'),'effect':row.get('effect_final'),'unverified':row.get('unverified_reason')},ensure_ascii=False),flush=True)
 # Only proven owned child generations may be cleaned; never peer processes.
 report['cleanup']=[]
 for cut in stages:
  try:
   child=state(cut).get('child') or {}
   if owned_requests._alive(child) is True:
    os.kill(child['pid'],signal.SIGTERM);time.sleep(.5)
    if owned_requests._alive(child) is True:os.kill(child['pid'],signal.SIGKILL)
   report['cleanup'].append({'boundary':cut,'pid':child.get('pid'),'alive':owned_requests._alive(child)})
  except Exception as exc:report['cleanup'].append({'boundary':cut,'error':type(exc).__name__})
 report['source_unchanged_after']=all(hashlib.sha256((FROZEN/p).read_bytes()).hexdigest()==h for p,h in manifest['files'].items())
 report['elapsed_seconds']=round(time.monotonic()-started,2);dump(out,report)
 print('report='+str(out),flush=True)
if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='--child':child_mode(Path(sys.argv[2]),sys.argv[3],sys.argv[4])
 else:main()
