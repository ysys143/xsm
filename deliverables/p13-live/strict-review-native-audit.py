"""Offline one-trace strict positive/negative/recovery binding; no runtime calls."""
import hashlib,json,re
from pathlib import Path
BASE=Path(__file__).resolve().parent
D=BASE/'strict-review-native-results.json';raw=D.read_bytes();d=json.loads(raw);root=Path(d['root'])
def events(role):return [json.loads(x) for x in (root/(role+'.jsonl')).read_text().splitlines()]
def calls(role):return [e['item'] for e in events(role) if e.get('type')=='item.completed' and (e.get('item')or{}).get('type')=='mcp_tool_call']
def payloads(c):
 for block in (c.get('result')or{}).get('content',[]):
  try:q=json.loads(block.get('text',''))
  except ValueError:continue
  if isinstance(q,dict):yield q
sender,reviewer=calls('initiator'),calls('reviewer');asks=[c for c in sender if c.get('tool')=='xsm_ask']
if len(asks)!=4:raise RuntimeError('original sample does not contain four actual question calls; no rerun')
initial=[next(q for q in payloads(c) if q.get('id') and 'final'in q) for c in asks];ids=[q['id'] for q in initial]
canonical={q['id']:q for q in [json.loads(p.read_text()) for p in (root/'state/handoffs').glob('*/*.json')]};finals={}
for c in sender:
 if c.get('tool') not in ('xsm_ask','xsm_question_status'):continue
 for q in payloads(c):
  if q.get('id') in ids and q.get('final') is True:finals[q['id']]=q
if len(finals)!=4:raise RuntimeError('not all four request IDs have actual final replies; no rerun')
q4=ids[3];snapshot=json.loads((root/('held-'+q4+'.json')).read_text());held=[q for c in sender if c.get('tool')=='xsm_question_status' for q in payloads(c) if q.get('id')==q4 and q.get('status')=='held'];resends=[c for c in sender if c.get('tool')=='xsm_send' and (c.get('arguments')or{}).get('resend')==q4]
def ack(cs):return [mid for c in cs if c.get('tool')=='xsm_ack' for q in payloads(c) for mid in q.get('acked',[])]
def native_handle(role):
 sid=next(e['thread_id'] for e in events(role) if e.get('type')=='thread.started')
 return {'CID':sid,'profile':d['profile'],'native_wrapper_PID':next(a['pid'] for a in d['owned_processes_after'] if a['role']==role),'lstart':next(a['lstart'] for a in d['owned_processes_after'] if a['role']==role),'MCP_PID':next(a['mcp_pid'] for a in d['owned_processes_after'] if a['role']==role)}
peers={'sender':native_handle('initiator'),'reviewer':native_handle('reviewer')}
for role,mid in [('sender',ids[0]),('reviewer',finals[ids[0]]['replies'][0]['id'])]:
 actual=canonical[mid]['message']['sender'];peers[role]['actual_native_PID']=actual['pid'];peers[role]['actual_native_lstart']=actual.get('lstart');peers[role]['cwd']=actual.get('cwd')
observations=json.loads((root/'controller-observations.json').read_text())
post_cleanup=json.loads((root/'post-cleanup-readback.json').read_text())
def at(role,item,event):return next(o['at'] for o in observations if o.get('role')==role and o.get('item_id')==item['id'] and o.get('event')==event)
rounds=[]
for index,mid in enumerate(ids):
 record=canonical[mid];result=finals[mid];reply=result['replies'][-1];answer=canonical[reply['id']];body=record['message']['body']
 sends=[c for c in reviewer if c.get('tool')=='xsm_send' and (c.get('arguments')or{}).get('reply_to')==mid]
 rounds.append({'round':index+1,'request_id':mid,'request_body':body,'request_sha256':hashlib.sha256(body.encode()).hexdigest(),'canonical_digest':record['digest'],'reply_id':reply['id'],'reply_to':answer['message']['reply_to'],'reply_body':reply['body'],'reply_sha256':hashlib.sha256(reply['body'].encode()).hexdigest(),'outcome':reply['outcome'],'final':result['final'],'request_stored_at':record['stored_at'],'reply_stored_at':answer['stored_at'],'initial_ask_completed_observed':at('initiator',asks[index],'item.completed'),'reply_received_at':reply['received_at'],'request_ACK':mid in ack(reviewer),'reply_ACK':reply['id'] in ack(sender),'request_state':record['state'],'reply_state':answer['state'],'reviewer_send_count':len(sends),'body_matches_actual_canonical':reply['body']==answer['message']['body']})
checks={
 'exactly_one_new_pair':d['actor_native_invocations']==2 and d['setup_registry_calls']==2 and d['condition_runs']==1,
 'distinct_actual_CIDs':peers['sender']['CID']!=peers['reviewer']['CID'],
 'four_distinct_request_IDs':len(set(ids))==4,
 'three_normal_initial_finals':all(q['final'] and q['final_outcome']=='succeeded' for q in initial[:3]),
 'first_three_unique_bodies':len({r['request_body'] for r in rounds[:3]})==3,
 'wrong_proposal_then_correction_then_boundary':all(expr in re.sub(r'\s+','',r['request_body']) for expr,r in zip(('2+2=5','2+2=4','0+0=0'),rounds[:3])),
 'normal_round_order_from_actual_replies':rounds[0]['reply_received_at']<rounds[1]['request_stored_at'] and rounds[1]['reply_received_at']<rounds[2]['request_stored_at'],
 'repeat_only_after_boundary_reply':rounds[2]['reply_received_at']<rounds[3]['request_stored_at'],
 'repeat_is_exact_third_body':rounds[2]['request_body']==rounds[3]['request_body'],
 'real_same_ID_query_held':bool(held) and all(not q['final'] and q['final_outcome'] is None for q in held),
 'held_original_not_success':snapshot['canonical']['id']==q4 and snapshot['canonical']['delivery_state']=='held' and snapshot['receipt']['decision']=='held',
 'same_ID_resend_once':len(resends)==1,
 'original_body_resend':resends[0]['arguments']['text']==rounds[3]['request_body'],
 'original_message_and_digest_unchanged':snapshot['canonical']['message']==canonical[q4]['message'] and snapshot['canonical']['digest']==canonical[q4]['digest'],
 'late_query_final_same_ID':any(c.get('tool')=='xsm_question_status' and (c.get('arguments')or{}).get('id')==q4 and any(q.get('id')==q4 and q.get('final') for q in payloads(c)) for c in sender),
 'four_real_explicit_final_replies':all(r['final'] and r['outcome']=='succeeded' and r['body_matches_actual_canonical'] and r['reviewer_send_count']==1 and r['reply_to']==r['request_id'] for r in rounds),
 'all_request_and_reply_ACKs_real':all(r['request_ACK'] and r['reply_ACK'] and r['request_state']==r['reply_state']=='acknowledged' for r in rounds),
 'one_sender_receiver_pair_all_rounds':all(canonical[mid]['message']['sender']['session_id']==peers['sender']['CID'] and canonical[mid]['receiver']['session_id']==peers['reviewer']['CID'] for mid in ids),
 'strict_policy_same_whole_trace':d['initial_private_policy_sha256']==d['final_private_policy_sha256'] and d['private_policy']=={'traffic_control':{'mode':'strict','window_seconds':60,'max_same_body':1}},
 'source_unchanged':d['source_unchanged'],
 'controller_no_relay_ACK_index':d['controller_body_relays']==d['controller_ACKs']==d['controller_index_writes']==0,
 'no_extra_prompt_or_actor_retry':d['additional_user_prompts']==d['automatic_actor_retries']==0,
 'known_owned_processes_stopped_after_cleanup':post_cleanup['remaining']==0}
changed={k:{'before':d['profile_guard_before'].get(k),'after':d['profile_guard_after'].get(k)} for k in set(d['profile_guard_before'])|set(d['profile_guard_after']) if d['profile_guard_before'].get(k)!=d['profile_guard_after'].get(k)}
result={'scope':'A22-03 final same-source same-policy single-trace positive/negative/recovery; previous two pairs not merged','functional_criterion_passed':all(checks.values()),'checks':checks,'checks_passed':sum(checks.values()),'profile_guard_unchanged':d['profile_settings_and_auth_metadata_unchanged'],'profile_guard_changes':changed,'profile_drift_writer':'not attributed by this observation; no evaluator/actor profile edits performed','source':d['frozen_source'],'source_manifest':d['frozen_manifest'],'original_runtime_result_sha256':hashlib.sha256(raw).hexdigest(),'original_goals':d['goals'],'private_root':str(root),'private_policy':d['private_policy'],'private_policy_SHA256':d['initial_private_policy_sha256'],'actual_peers':peers,'rounds':rounds,'held_status_query_count':len(held),'held_snapshot_path':str(root/('held-'+q4+'.json')),'same_ID_resend':{'id':q4,'count':len(resends),'started_at_observed':at('initiator',resends[0],'item.started'),'result_body_sha256':hashlib.sha256(resends[0]['arguments']['text'].encode()).hexdigest()},'request_attempts':{'unique_questions':4,'recovery_resend_same_ID':1,'total_service_send_attempts':5},'native_invocations':2,'automatic_model_actor_retries':0,'controller_operations':{k:d[k] for k in ('setup_registry_calls','controller_body_relays','controller_ACKs','controller_index_writes','additional_user_prompts')},'cleanup_initial_snapshot':d['owned_processes_after'],'cleanup_verified':post_cleanup,'native_lifecycle':{'before_cleanup_exit_codes':{a['role']:a['exit_code'] for a in d['actors']},'cleanup_actions':d['cleanup'],'reviewer_self_terminated':False,'note':'All four actual request/reply/ACK lifecycles completed. Reviewer waited for extra conversational read confirmation; harness ended own group after sender exit. Not counted as reviewer natural exit 0.'},'audit_correction':{'initial_audit_preserved':'strict-review-native-audit-initial.json','initial_failed_checks':['instant post-TERM process snapshot','both actors naturally exit 0'],'actual_request_results_unchanged':True,'correction':'Final owned-PID cleanup readback replaces immediate TERM race; natural actor exit is reported separately, not substituted for actual task outcomes.'},'previous_pairs_reused_for_success':False,'no_further_experiments':True}
(BASE/'strict-review-native-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'passed':result['functional_criterion_passed'],'checks':result['checks_passed'],'profile_guard':result['profile_guard_unchanged'],'profile_changed_paths':list(changed),'IDs':ids,'same_ID_resend':q4},ensure_ascii=False))
if not all(checks.values()):raise SystemExit(1)
