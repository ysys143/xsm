"""Read-only checks of actual native lifetime evidence; no product execution."""
import hashlib,json,pathlib,subprocess,shutil,sys
ROOT=pathlib.Path('/private/tmp/session-lifetime-native-oj91jnav')
PUBLIC=pathlib.Path(__file__).resolve().parent
def sha(x):return hashlib.sha256(x if isinstance(x,bytes)else x.encode()).hexdigest()
def load(p):return json.loads(pathlib.Path(p).read_text())
def rows(p):return [json.loads(x)for x in pathlib.Path(p).read_text().splitlines()]if pathlib.Path(p).exists()else[]
def lstart(pid):return subprocess.run(['ps','-o','lstart=','-p',str(pid)],capture_output=True,text=True).stdout.strip()or None
def main():
 d=load(ROOT/'result.json');regs=d['actual_registration_setup'];byrole={x['role']:x for x in regs}
 evidence=[];errors=[];toolcounts={};metadata=[];actualACK=set();emptyinbox={};oldread=[];replycalls=[];unknowns=[];finalstatuses=[]
 states={p.stem:load(p)for p in(ROOT/'state/handoffs').glob('*/*.json')}
 for a in d['invocations']:
  role=a['role'];toolcounts[role]={};emptyinbox[role]=[]
  for folder in(ROOT/role/'proxies').iterdir():
   requests={x['id']:x for x in rows(folder/'client-wire.jsonl')if x.get('method')=='tools/call'}
   for req in requests.values():
    p=req['params'];toolcounts[role][p['name']]=toolcounts[role].get(p['name'],0)+1
    args=p.get('arguments')or{}
    if p['name']in('xsm_send','xsm_ask')and args.get('reply_to'):replycalls.append({'role':role,'reply_to':args['reply_to']})
    cid=(p.get('_meta')or{}).get('threadId');metadata.append({'role':role,'tool':p['name'],'real_CID_sha256':sha(cid)if cid else None,'matches_registration':cid==byrole.get(role,{}).get('CID')})
   for res in rows(folder/'server-wire.jsonl'):
    req=requests.get(res.get('id'))
    if not req:continue
    p=req['params'];args=p.get('arguments')or{};rpc=res.get('result')or{}
    if rpc.get('isError')or res.get('error'):errors.append({'role':role,'tool':p['name'],'response_sha256':sha(json.dumps(res,sort_keys=True))})
    for b in rpc.get('content',[]):
     if b.get('type')!='text':continue
     try:v=json.loads(b['text'])
     except(ValueError,TypeError):continue
     if not isinstance(v,dict):continue
     evidence.append({'role':role,'tool':p['name'],'request_id':req['id'],'response_sha256':sha(json.dumps(v,sort_keys=True))})
     if p['name']=='xsm_inbox':
      emptyinbox[role].append(not v.get('messages')and not v.get('claims'))
      if role=='resume':oldread.extend(v.get('claims')or[])
     if p['name']=='xsm_ack':
      for mid in v.get('acked',[]):
       rec=states[mid]
       assert rec['receiver']['session_id']==byrole[role]['CID']
       assert rec['claim']['token']in args['tokens']
       actualACK.add(mid)
     if p['name']=='xsm_question_status'and v.get('final'):finalstatuses.append(v)
     if p['name']=='xsm_discover':
      for c in v.get('candidates',[]):
       unknowns.append({'role':role,'CID_sha256':sha(c['handle']['session_id']),'name':c.get('name'),'name_source':c.get('name_source'),'name_freshness':c.get('name_freshness'),'summary':c.get('summary'),'todo':c.get('todo'),'activity':c.get('activity'),'state':c.get('state')})
 old=byrole.get('old',{}).get('CID');new=byrole.get('new',{}).get('CID');resumed=byrole.get('resume',{}).get('CID')
 snaps={n:load(ROOT/(n+'.json'))for n in d['stages']}
 original=None
 if 'old-offline-before-new'in snaps:
  originals=[x for x in snaps['old-offline-before-new']['handoffs'].values()if x['receiver']['session_id']==old and not x['message'].get('reply_to')]
  if len(originals)==1:original=originals[0]
 checks={'old_normal_wrapper_exit':next((x.get('exit_code')==0 for x in d['invocations']if x['role']=='old'),False),
 'same_display_name_setup':all(byrole.get(role,{}).get('record',{}).get('name')=='archivist'for role in ['old','new','resume']),
 'old_new_real_CID_different':bool(old and new and old!=new),'old_resume_real_CID_same':bool(old and resumed and old==resumed),
 'resume_new_actual_PID_generation':bool(byrole.get('old')and byrole.get('resume')and byrole['old']['native']['pid']!=byrole['resume']['native']['pid']and byrole['old']['record']['lstart']!=byrole['resume']['record']['lstart']),
 'new_native_inbox_called':bool(emptyinbox.get('new')),'new_native_inbox_empty':bool(emptyinbox.get('new'))and all(emptyinbox['new']),
 'all_actual_metadata_matches_real_registration':bool(metadata)and all(x['matches_registration']for x in metadata),
 'old_pending_at_offline':bool(original and original['state']=='pending'and original.get('claim')is None),
 'old_unchanged_through_new':False,'resumed_real_claim_original':False,'actual_ACK_original':False,'correlated_reply_original':False,'question_final_succeeded':False,
 'resume_ACK_then_actual_inbox_empty':False}
 originalID=original['id']if original else None
 if original:
  afternew=next((x for x in snaps.get('after-new-before-resume',{}).get('handoffs',{}).values()if x['id']==originalID),None)
  final=states.get(originalID)
  immutable=['id','receiver','identity','digest','message']
  checks['old_unchanged_through_new']=bool(afternew and all(original[k]==afternew[k]for k in immutable)and afternew['state']=='pending'and afternew.get('claim')is None)
  checks['resumed_real_claim_original']=any(x.get('id')==originalID for x in oldread)
  checks['actual_ACK_original']=originalID in actualACK
  checks['correlated_reply_original']=any(x['role']=='resume'and x['reply_to']==originalID for x in replycalls)
  qpath=ROOT/'state/questions'/(originalID+'.json');q=load(qpath)if qpath.exists()else{}
  checks['question_final_succeeded']=any(x.get('id')==originalID and x.get('final_outcome')=='succeeded'for x in finalstatuses)and bool(q.get('replies'))
  checks['resume_ACK_then_actual_inbox_empty']=checks['actual_ACK_original']and any(emptyinbox.get('resume',[]))
  checks['original_digest_body_receiver_preserved_after_resume']=bool(final and all(original[k]==final[k]for k in immutable))
 known=[dict(x,current_lstart=lstart(x['pid']))for x in d.get('known_processes',[])]
 for x in known:x['same_owned_process_alive_now']=x['current_lstart']==x['lstart']
 fm=load(PUBLIC.parent/'final-source-manifest.json');source=pathlib.Path(fm['snapshot'])
 assert all(sha((source/p).read_bytes())==h for p,h in fm['files'].items())
 turns=[]
 for a in d['invocations']:
  rr=rows(ROOT/a['role']/'native.jsonl');turns.append({'role':a['role'],'started':sum(x.get('type')=='turn.started'for x in rr),'completed':sum(x.get('type')=='turn.completed'for x in rr),'exit_code':a.get('exit_code')})
 (ROOT/'native-rollouts').mkdir(exist_ok=True)
 for reg in regs:
  path=pathlib.Path(reg['rollout_path']);dest=ROOT/'native-rollouts'/(sha(reg['CID'])+'.jsonl')
  if path.exists():shutil.copyfile(path,dest)
 summary={'scope':'A17-06 unread lifecycle native subset; no selected-pair grant; A17-04 partial metadata observation only','private_raw_root':str(ROOT),'status':d.get('status'),'original_failure':d.get('failure'),'CLI':d['CLI'],
 'source':d['source'],'source_frozen_files_hash_verified':len(fm['files']),'native_CLI_invocations':len(d['invocations']),'unique_native_CIDs':len(set(a.get('CID')for a in d['invocations']if a.get('CID'))),'same_CID_resume_invocations':sum(a['role']=='resume'for a in d['invocations']),'initial_actual_registration_setups':len(regs),'model_condition_retries':0,'native_turn_counts':turns,
 'checks':checks,'request_ID_sha256':sha(originalID)if originalID else None,'original_digest':original.get('digest')if original else None,'actual_ACK_ID_count':len(actualACK),'tools_by_role':toolcounts,'actual_calls':metadata,'responses':evidence,'RPC_errors':errors,
 'directory_observations':unknowns,'canonical_final_states':[{ 'ID_sha256':sha(k),'state':v['state'],'claimed':v.get('claim')is not None,'claim_token_sha256':sha(v['claim']['token'])if v.get('claim')else None}for k,v in states.items()],
 'ACK_limit':'model claimed completion, but no xsm_ack call; both canonical records remain handoff-recorded; empty inbox while claimed is not ACK dedup proof',
 'selected_pair_permission_lifecycle':{'status':'unfulfilled','reason':'no existing approved exact pair in new private fixture; create requires real affirmative consent; no consent fabricated and no grant created','native_permission_denial_tested':False},
 'A17_04':{'status':'partial/unproven complete criterion','condition':'actual native missing title/plan metadata, not extractor-disabled harness','extractor_removed':False,'native_title_plan_update_partial_record_TTL_matrix':'not newly executed'},
 'profile_unchanged':d.get('profile_unchanged'),'profile_changed_names':[k for k,v in d['profile_before'].items()if d['profile_after'].get(k)!=v],'profile_drift_writer':'unknown','known_process_final_audit':known,'controller_body_relay_manual_ACK_index_repair':0,'whole_A17_06_proven':False,'whole_A17_04_proven':False}
 (PUBLIC/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'checks':checks,'CLI_invocations':len(d['invocations']),'unique_CIDs':summary['unique_native_CIDs'],'RPC_errors':len(errors),'alive_owned_processes':sum(x['same_owned_process_alive_now']for x in known)},ensure_ascii=False))
 return summary
if __name__=='__main__':
 result=main()
 if '--require-complete'in sys.argv and (not all(result['checks'].values())or not result['whole_A17_06_proven']or not result['whole_A17_04_proven']):
  print('INCOMPLETE: actual ACK, selected-pair permission lifetime, and full extractor/update matrix are not proven',file=sys.stderr)
  sys.exit(1)
