"""Read existing native/MCP/canonical evidence only. No messages or ACK writes."""
import collections,hashlib,json,os,sqlite3,sys,tarfile
from pathlib import Path
ROOT=Path(__file__).parent;M=json.loads((ROOT/'manifest.json').read_text());OUT=Path(M['report']);R=json.loads((OUT/'results.json').read_text())
sys.path.insert(0,str(ROOT/'payload'))
from xsm import handoff,paths
paths.HOME=M['state']
def read(p):return json.loads(p.read_text())
def events(p):
 result=[]
 for line in p.read_text().splitlines():
  try:result.append(json.loads(line))
  except ValueError:pass
 return result
calls=[];registrations=[];files=[];barriers=[]
for role in('reviewer','requester'):
 for run in sorted((ROOT/'actors'/role).glob('phase*')):
  reg=read(run/'registration.json');owner=read(run/'owner.json')
  registrations.append({'role':role,'phase':run.name,'CID':reg['CID'],'native_pid':reg['native']['pid'],
   'native_start':reg['native']['lstart'],'MCP_pid':reg['MCP_server']['pid'],'provider_row_matches_CID':reg['provider_row'][0]==reg['CID'],
   'provider_cwd':reg['provider_row'][2],'current_PID_matches_launch':reg['native']['pid']==owner['pid']and reg['native']['lstart']==owner['lstart']})
  files.extend(p for p in run.rglob('*')if p.is_file()and not p.is_symlink())
  for proxy in(run/'actor/proxies').iterdir():
   if not proxy.is_dir():continue
   if(proxy/'startup-barrier.json').exists():barriers.append(read(proxy/'startup-barrier.json'))
   responses={v.get('id'):v for v in events(proxy/'server-wire.jsonl')if'result'in v or'error'in v}
   for v in events(proxy/'client-wire.jsonl'):
    if v.get('method')!='tools/call':continue
    args=v['params'].get('arguments',{});args=json.loads(args)if isinstance(args,str)else args
    calls.append({'role':role,'phase':run.name,'tool':v['params']['name'],'arguments':args,'response':responses.get(v.get('id'))})
workflow=[]
for phase in R['phases']:
 for q in phase['questions']:
  canonical=handoff.status(q['target'],q['id']);reply=q['replies'][-1];received=handoff.status(q['sender'],reply['id'])
  workflow.append({'phase':phase['phase'],'request_id':q['id'],'reply_id':reply['id'],
   'request_body_sha256':hashlib.sha256(q['body'].encode()).hexdigest(),'request_raw_preserved':canonical['message']['body']==q['body'],
   'reply_raw_preserved':received['message']['body']==reply['body'],
   'request_actual_ask_seen':any(c['role']=='requester'and c['tool']=='xsm_ask'and c['arguments'].get('text')==q['body']for c in calls),
   'reply_actual_send_seen':any(c['role']=='reviewer'and c['tool']=='xsm_send'and c['arguments'].get('reply_to')==q['id']and c['arguments'].get('text')==reply['body']for c in calls),
   'request_actual_inbox_seen':any(c['role']=='reviewer'and c['tool']=='xsm_inbox'and q['body']in json.dumps(c['response'],ensure_ascii=False)for c in calls),
   'request_handoff_state':canonical['status'],'reply_handoff_state':received['status'],
   'requester_CID':q['sender']['session_id'],'reviewer_CID':q['target']['session_id']})
models={}
for role in('requester','reviewer'):
 con=sqlite3.connect('file:'+str(ROOT/'actors'/role/'codex-home/state_5.sqlite')+'?mode=ro',uri=True)
 try:row=con.execute('select rollout_path from threads where id=?',(R['actual_CIDs'][role],)).fetchone()
 finally:con.close()
 models[role]=sorted({e['payload']['model']for e in events(Path(row[0]))if e.get('type')=='turn_context'and isinstance(e.get('payload',{}).get('model'),str)})if row else[]
initial=read(OUT/'initial-services.json');probes=R['socket_probes']
baseline=next(p for p in probes if p['pid']==initial['a']['engine_pid'])
blocked=next(p for p in probes if p['pid']==R['book_blocked_status']['engine_pid'])
S={'completed':all(w['request_raw_preserved']and w['reply_raw_preserved']and w['request_actual_ask_seen']and w['reply_actual_send_seen']and w['request_actual_inbox_seen']and w['request_handoff_state']=='acknowledged'and w['reply_handoff_state']=='acknowledged'for w in workflow),
 'workflow':workflow,'registrations':registrations,'startup_barriers':barriers,'observed_model_IDs':models,'CLI_version':M['codex_version'],
 'actual_conversations':len({v['CID']for v in registrations}),'CLI_native_runs':len(registrations),'same_actual_work_folder':all(os.path.realpath(v['provider_cwd'])==M['work']for v in registrations),
 'MCP_counts':{role:dict(collections.Counter(c['tool']for c in calls if c['role']==role))for role in('requester','reviewer')},
 'baseline_socket_probe':baseline,'blocked_socket_probe':blocked,'same_probe_and_engine_PID':blocked['pid']==R['book_blocked_status']['engine_pid'],
 'Book_network_identity_preserved':initial['a']['endpoint_id']==R['book_blocked_status']['endpoint_id'],
 'Mini_service_stop':R['mini_stop'],'Book_before_restart_stop':R['book_stop_for_restart'],'Book_final_stop':R['cleanup']['network-a'],
 'final_actor_cleanup':read(OUT/'final-owned-cleanup.json'),'source_profile_unchanged':R['source_profile_unchanged'],'source_auth_metadata_unchanged':R['source_auth_metadata_unchanged'],
 'controller_body_relay_or_ACK_or_index_repair':False,'source_file_count':len(M['files']),
 'source_current_differences':[name for name,sha in M['files'].items()if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=sha]}
assert S['completed'],'existing native evidence mismatch'
(OUT/'summary.json').write_text(json.dumps(S,ensure_ascii=False,indent=2)+'\n')
with tarfile.open(OUT/'actual-actor-evidence.tar.gz','w:gz')as archive:
 for p in files:archive.add(p,arcname=str(p.relative_to(ROOT)),recursive=False)
for name in('actors.py','run.py','analyze.py','payload/proxy.py','payload/node.py','payload/observe.py','payload/bin/xsm-net'):
 p=ROOT/name;(OUT/('helper-'+p.name)).write_bytes(p.read_bytes())
for p in OUT.iterdir():
 if p.is_file():p.chmod(0o600)
print(json.dumps({'completed':S['completed'],'phases':[{'phase':w['phase'],'request':w['request_id'],'reply':w['reply_id'],'request_state':w['request_handoff_state'],'reply_state':w['reply_handoff_state']}for w in workflow],
 'observed_models':models,'MCP_counts':S['MCP_counts'],'same_probe_PID':S['same_probe_and_engine_PID'],'source_current_differences':S['source_current_differences']},ensure_ascii=False))
