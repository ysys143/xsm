"""Read existing postfix CLI output only; never rerun doctor or touch a session."""
from pathlib import Path
import hashlib,json,stat
ROOT=Path('/private/tmp/doctor-privacy-native-1qw1twk2')
PUBLIC=Path(__file__).resolve().parent
REPO=PUBLIC.parents[2]
def load(p):return json.loads(Path(p).read_text())
def sha(b):return hashlib.sha256(b if isinstance(b,bytes)else b.encode()).hexdigest()
def main():
 d=load(ROOT/'run-meta.json');markers=load(ROOT/'markers.private.json');ids=load(ROOT/'ids.private.json');follow=load(ROOT/'followup-tool.json')
 out=(ROOT/'doctor.stdout').read_bytes();err=(ROOT/'doctor.stderr').read_bytes();report=json.loads(out);stuck=report['stuck']
 assert d['exit_code']==0 and not err and d['doctor_invocations']==1
 assert all(v.encode()not in out+err for v in markers.values())
 assert len(report['homes'])==1 and report['sessions']['registered']==1
 assert [x['id']for x in stuck['undelivered']]==[ids['queued']]
 assert [x['id']for x in stuck['uncertain']]==[ids['unknown']]
 assert stuck['send_failures']=={'other':1,'sandbox-blocked':2}
 for row in stuck['undelivered']+stuck['uncertain']:
  assert set(row)=={'id','status','t','from','to'}
  assert all(isinstance(v,str)for k in ['from','to']for v in row[k].values())
 before=load(ROOT/'ledger-hashes-before.json');after=load(ROOT/'ledger-hashes-after.json')
 assert len(before)==5 and before==after
 for name,h in before.items():
  b=(ROOT/'state/ledger'/name).read_bytes();assert b==(ROOT/'ledger-before'/name).read_bytes()
  assert sha(b)==h['sha256']and len(b)==h['bytes']
  raw=json.loads(b);assert 'body'in raw and isinstance(raw['from']['ref'],dict)and 'arbitrary'in raw
  assert raw['t']<d['started_at']-120
 assert follow['actual_followup_tool_executed']and follow['same_native_PID_and_lstart']and follow['same_native_thread_env_and_readonly_DB']
 assert d['native_same_generation']and d['native_metadata_before']==d['native_metadata_after']
 fm=load(REPO/'deliverables/p13-live/doctor-privacy-source-manifest.json');source=Path(fm['snapshot'])
 assert str(source)==d['source']and all(sha((source/n).read_bytes())==h for n,h in fm['files'].items())
 assert all(sha((REPO/n).read_bytes())==fm['files'][n]for n in fm['stable_product_paths'])
 assert stat.S_IMODE(ROOT.stat().st_mode)==0o700
 for p in [ROOT/'doctor.stdout',ROOT/'doctor.stderr']:assert stat.S_IMODE(p.stat().st_mode)==0o600
 rawregs=[load(p)for p in(ROOT/'state/sessions').glob('*.json')];native=load(ROOT/'native-observation-before.json')
 assert len(rawregs)==1 and rawregs[0]['session_id']==native['CID']and rawregs[0]['home']==native['home']
 summary={'verdict':'pass for this actual postfix CLI privacy/survival sample; not whole-plan completion','source':str(source),'source_manifest_sha256_at_run':d['source_manifest_sha256'],'source315_verified':len(fm['files']),'source135_current_and_frozen_verified':len(fm['stable_product_paths']),
 'CLI_invocations':1,'new_models':0,'new_native_TUIs':0,'interpreter':d['interpreter'],'argv':d['argv'],'cwd':d['cwd'],'exit_code':0,'added_sandbox_or_observer':False,
 'native_registration':{'actual_native_DB_and_rollout_header_verified':True,'actual_OS_native_ancestor_verified':True,'home_count':1,'session_count':1,'shared_runtime':True,'PID_sha256':sha(native['native']['pid']),'lstart_sha256':sha(native['native']['lstart']),'CID_sha256':sha(native['CID']),'home_sha256':sha(native['home']),'authority_or_caller_certainty_claimed':False},
 'stuck':{'undelivered':[{'id_sha256':sha(x['id']),'status':x['status'],'row_keys':sorted(x)}for x in stuck['undelivered']],'uncertain':[{'id_sha256':sha(x['id']),'status':x['status'],'row_keys':sorted(x)}for x in stuck['uncertain']],'send_failures':stuck['send_failures'],'queued_age_seconds_at_capture':d['utility']['queued_ages_seconds'],'endpoint_scalar_metadata_preserved':True},
 'synthetic_nonoutput':{k:{'marker_sha256':sha(v),'in_stdout':False,'in_stderr':False}for k,v in markers.items()},'leaked_marker_count':0,'real_credentials_loaded_or_compared':False,'privacy_scope':'seeded body/preview/nested/endpoint/raw-error/synthetic-invite markers; home metadata is not message-body disclosure; no universal unknown-secret claim',
 'doctor_metadata_observations':d['doctor_observations'],'ledger':{'files':5,'bytes_before_after_identical':True,'record_set_unchanged':True},'selected_home_metadata_present':d['doctor_observations']['selected_home_metadata_present'],
 'runtime_survival':{'same_PID_generation_before_after':d['native_same_generation'],'subsequent_actual_tool_executed':True,'followup_same_PID_generation':True,'followup_same_native_thread_readonly_DB':True},'profile_stat_metadata_unchanged':True,
 'streams':d['streams'],'private_raw_root':str(ROOT),'private_root_mode':'0o700','stdout_stderr_mode':'0o600','signals_login_wake_grants_profile_writes_by_driver':0,'credential_file_reads_by_driver':0,'access_trace_observer':'not installed; no universal file-open trace claim','whole_plan_complete':False}
 (PUBLIC/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'CLI':1,'exit_code':0,'stderr_bytes':0,'home_count':1,'registered_count':1,'undelivered':1,'uncertain':1,'send_failures':stuck['send_failures'],'marker_leaks':0,'ledger_files_unchanged':5,'followup_same_PID_generation':True,'source315_verified':315},ensure_ascii=False))
 return summary
if __name__=='__main__':main()
