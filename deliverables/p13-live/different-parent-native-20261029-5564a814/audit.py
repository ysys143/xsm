"""Read-only actual different-parent native evidence audit; no new native calls."""
from pathlib import Path
import json,hashlib,subprocess,collections,sys,os,base64
ROOT=Path('/private/tmp/different-parent-native-3jr1o8uv');PUBLIC=Path(__file__).resolve().parent
load=lambda p:json.loads(Path(p).read_text());sha=lambda x:hashlib.sha256(x if isinstance(x,bytes)else x.encode()).hexdigest()
d=load(ROOT/'result.json');plan=load(PUBLIC/'plan.json');threads=d['actual_native_threads'];roots={x['role']:x for x in threads if x['parent_thread_id']is None};children={x['role']:x for x in threads if x['parent_thread_id']is not None}
assert len(roots)==len(children)==2 and len({x['parent_thread_id']for x in children.values()})==2
for role,x in children.items():assert x['parent_thread_id']==roots[role]['id']
h={p.stem:load(p)for p in(ROOT/'state/handoffs').glob('*/*.json')};q={p.stem:load(p)for p in(ROOT/'state/questions').glob('*.json')};childIDs={x['id']for x in children.values()};instances=[];calls=[];raw=[];ACKed=set();reads=[];errors=[];known={x['pid']:x['lstart']for x in d['actors']};parent_calls=collections.Counter()
for role in roots:
 for folder in(ROOT/role/'proxies').iterdir():
  hh=load(folder/'handles.json');req={x['id']:x for x in map(json.loads,(folder/'client-wire.jsonl').read_text().splitlines())if x.get('method')=='tools/call'};cids=set()
  for rr in req.values():
   pp=rr['params'];cid=(pp.get('_meta')or{}).get('threadId');cids.add(cid);calls.append((pp['name'],pp.get('arguments')or{},cid));parent_calls[role]+=int(cid==roots[role]['id'])
  instances.append({'role':role,'MCP_pid':hh['server']['pid'],'calls':len(req),'CID_hashes':[sha(x)if x else None for x in cids]})
  for k in('server','proxy'):known[hh[k]['pid']]=hh[k]['lstart']
  for x in hh['native_ancestor_chain']:
   if Path(x['comm']).name=='codex':known[x['pid']]=x['lstart']
  for line in(folder/'server-wire.jsonl').read_text().splitlines():
   raw.append(line);res=json.loads(line);rr=req.get(res.get('id'))
   if not rr:continue
   pp=rr['params'];a=pp.get('arguments')or{};cid=(pp.get('_meta')or{}).get('threadId');result=res.get('result')or{}
   if result.get('isError'):errors.append({'tool':pp['name'],'error':str(result.get('content'))[:260]})
   for b in result.get('content',[]):
    if b.get('type')!='text':continue
    try:v=json.loads(b['text'])
    except ValueError:continue
    if pp['name']=='xsm_ack':
     for mid in v.get('acked',[]):assert h[mid]['receiver']['session_id']==cid and h[mid]['claim']['token']in a['tokens'];ACKed.add(mid)
    if pp['name']=='xsm_files'and a.get('entry_id')and'content'in v:
     kind='outgoing'if a.get('outgoing')else'incoming';f=load(ROOT/'state/file-copies'/kind/a['storage_id']/'record.json');item=next(x for x in f['manifest']['files']if x['id']==a['entry_id']);data=base64.b64decode(v['content'])if v.get('encoding')=='base64'else v['content'].encode();assert f['owner']['session_id']==cid and sha(data)==item['sha256'];reads.append({'kind':kind,'receiver_CID_hash':sha(cid),'request_ID_hash':sha(f['manifest']['binding']['request_id']),'content_SHA_matches':True})
assert all(n==0 for n in parent_calls.values());assert set(h)==ACKed and len(h)==8
sys.dont_write_bytecode=True;sys.path.insert(0,d['source']);os.environ['XSM_HOME']=str(ROOT/'state');from xsm import envelope
messages=[]
for mid,x in h.items():
 assert x['state']=='acknowledged';assert x['message']['sender']['session_id']in childIDs and x['receiver']['session_id']in childIDs;assert x['message']['sender']['session_id']!=x['receiver']['session_id'];assert any(x['claim']['token']in line for line in raw);assert x['digest']==envelope.request_digest(x['identity']);assert x['message']['body']==envelope.parse(x['message']['content']).body
 e=load(ROOT/'state/ledger'/(mid+'.json'))['evidence'];logical=x['message']['wake'];fallback=(logical is True and x.get('delivery_route')=='mcp-inbox'and 'unloaded spawned sub-agents (code -32600)'in(e.get('queued')or{}).get('detail',''))
 if fallback:assert e['queued']['ok']is False and e['wake']['ok']is False
 messages.append({'ID_hash':sha(mid),'kind':x['message']['kind'],'logical_requested_wake':logical,'delivery_route':x.get('delivery_route'),'typed_auto_fallback_observed':fallback,'native_queued':(e.get('queued')or{}).get('ok'),'native_wake':(e.get('wake')or{}).get('ok'),'actual_claim_ACK':True,'immutable_digest_valid':True})
questions=[]
for mid,x in q.items():
 finals=[z for z in x['replies']if z.get('outcome')in('succeeded','failed')];assert finals and finals[-1]['outcome']=='succeeded'
 for rr in x['replies']:assert h[rr['id']]['message']['reply_to']==mid and h[rr['id']]['message']['sender']['session_id']==x['target']['session_id']
 questions.append({'request_ID_hash':sha(mid),'sender_CID_hash':sha(x['sender']['session_id']),'target_CID_hash':sha(x['target']['session_id']),'original_wake':x['wake'],'body_math_excerpt':x['body'][:165],'reply_count':len(x['replies']),'partial_reply_count':sum(z.get('outcome')is None for z in x['replies']),'final_outcome':finals[-1]['outcome'],'final_reply_math_excerpt':finals[-1]['body'][:190],'original_reply_to_preserved':True})
assert len(q)==3 and any('2+2=5'in x['body']for x in q.values())and any('수정안'in x['body']and'2+2=4'in x['body']for x in q.values())and any('0+0=0'in x['body']for x in q.values());assert reads and all(x['kind']=='incoming'for x in reads)
relations=[]
for role,child in children.items():
 setup=next(x for x in d['actual_registration_setup']if x['CID']==child['id']);relations.append({'role':role,'child_name':setup['name'],'parent_CID_hash':sha(roots[role]['id']),'child_CID_hash':sha(child['id']),'actual_parent_thread_id_hash':sha(child['parent_thread_id']),'native_PID':setup['native_pid'],'native_lstart':setup['native_lstart'],'home_hash':sha(setup['home']),'cwd_hash':sha(setup['cwd'])})
assert len({x['native_PID']for x in relations})==2 and len({x['home_hash']for x in relations})==1 and len({x['cwd_hash']for x in relations})==1
for pid,start in known.items():assert(subprocess.run(['ps','-o','lstart=','-p',str(pid)],capture_output=True,text=True).stdout.strip()or None)!=start
(ROOT/'native-rollouts').mkdir(mode=0o700,exist_ok=True);turns=[]
for x in threads:
 data=Path(x['rollout_path']).read_bytes();(ROOT/'native-rollouts'/(sha(x['id'])+'.jsonl')).write_bytes(data);ev=[json.loads(y)for y in data.decode().splitlines()];count=collections.Counter((y.get('payload')or{}).get('type')for y in ev if y.get('type')=='event_msg');turns.append({'CID_hash':sha(x['id']),'task_started':count['task_started'],'task_complete':count['task_complete'],'raw_SHA':sha(data)})
m=load(plan['source_manifest']);assert all(sha((Path(m['snapshot'])/k).read_bytes())==v for k,v in m['files'].items())
common=subprocess.check_output(['git','-C',str(ROOT/'work'),'rev-parse','--git-common-dir'],text=True).strip();warnings=[{'role':role,'stderr':(ROOT/role/'native.stderr').read_text()}for role in roots if 'ERROR'in(ROOT/role/'native.stderr').read_text()]
summary={'label':'A15-05 one actual two-parent/one-child-each condition','result':'different actual parents, direct child correction/memo/final mutual receipt observed','source':d['source'],'source_manifest_files_verified':315,'primary_paths':135,'CLI':d['CLI'],'CODEX_HOME':'/Users/jaesolshin/.codex-3','private_git_common':str((ROOT/'work'/common).resolve())if not Path(common).is_absolute()else common,'parent_relations':relations,'distinct_parent_thread_ids_proven':True,'distinct_real_native_PIDs':True,'native_parent_CLI_launches':2,'actual_native_children':2,'initial_real_registration_setup_count':len(d['actual_registration_setup']),'model_condition_retries':0,'native_turn_events':turns,'actual_tools_calls':len(calls),'MCP_instances':instances,'shared_MCP_success_claimed':False,'parent_xsm_calls':dict(parent_calls),'parent_body_relay_or_manual_ACK_by_evaluator':False,'proxy_meta_ID_results_ACKs_modified':False,'messages':messages,'typed_auto_fallbacks':sum(x['typed_auto_fallback_observed']for x in messages),'explicit_quiet_messages':sum(x['logical_requested_wake']is False for x in messages),'question_roundtrips':questions,'incoming_file_content_reads':reads,'actual_claim_ACK_IDs':len(ACKed),'RPC_errors':errors,'runtime_warnings':warnings,'source_unchanged':d['source_unchanged'],'profile_unchanged':d['profile_unchanged'],'profile_drift_changed_names':[k for k,v in d['profile_before'].items()if v!=d['profile_after'].get(k)],'profile_drift_writer':'unknown; no evaluator profile edit','known_processes_alive':0,'private_raw_root':str(ROOT),'started_utc':d['started_utc'],'finished_utc':d['finished_utc'],'prior_condition_artifacts_unchanged':True,'no_additional_experiments':True,'whole_plan_pass_claimed':False}
(PUBLIC/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');(ROOT/'audit-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'parents':2,'children':2,'different_parent_relations':True,'registration_setup':len(d['actual_registration_setup']),'native_PID_count':2,'typed_auto_fallback':summary['typed_auto_fallbacks'],'quiet':summary['explicit_quiet_messages'],'ACKs':len(ACKed),'final_questions':len(q),'incoming_file_reads':len(reads),'RPC_errors':errors,'source_unchanged':d['source_unchanged'],'profile_unchanged':d['profile_unchanged'],'runtime_warning_count':len(warnings),'tools_calls':len(calls)}))
