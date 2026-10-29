"""Evidence-only analysis. Does not run xsm or mutate live product state."""
import collections,hashlib,json,time
from pathlib import Path
OUT=Path(__file__).resolve().parent
sources=json.loads((OUT/'source-manifest.json').read_text());roots=json.loads((OUT/'roots.json').read_text())
result={'status':'incomplete; stopped on coordinator F3 admission/generation defect','source_manifest_sha256':hashlib.sha256((OUT/'source-manifest.json').read_bytes()).hexdigest(),'source_files':len(sources['files']),'engine':sources['engine'],'hosts':{},'wire_no_rewrite':{},'first_native_stop_reason':'F3 same-CID resume admission generation binding; native code-mode compatibility separately recorded','new_retries_after_stop':0,'manual_question_or_ACK_or_body_repairs':0,'source_changes':0,'global_profile_changes_observed':0}
for h in ('book','mini'):
 folder=OUT/(h+'-evidence');e=json.loads((folder/'preserved-evidence.json').read_text());f=json.loads((OUT/(h+'-final-observation.json')).read_text());state=e['product_state_read_only_snapshot'];toolcalls=[];wire=[];messages=[]
 for p in folder.glob('**/client-wire.jsonl'):
  for line in p.read_text().splitlines():
   value=json.loads(line)
   if value.get('method')=='tools/call':toolcalls.append({'trace':str(p.relative_to(OUT)),'id':value.get('id'),'tool':value.get('params',{}).get('name'),'arguments':value.get('params',{}).get('arguments')})
 for p in folder.glob('**/native.jsonl'):
  for line in p.read_text().splitlines():
   value=json.loads(line);item=value.get('item')or{}
   if item.get('type')=='agent_message':messages.append({'trace':str(p.relative_to(OUT)),'text':item.get('text')})
 for p in folder.glob('**/events.jsonl'):
  ev=[json.loads(x)for x in p.read_text().splitlines()]
  for direction in ('client','server'):
   actual=p.with_name(direction+'-wire.jsonl')
   if not actual.exists():continue
   recorded=[x for x in ev if x.get('direction')==direction];lines=actual.read_bytes().splitlines(keepends=True)
   wire.append({'trace':str(actual.relative_to(OUT)),'equal_line_count':len(recorded)==len(lines),'exact_bytes_sha_match':len(recorded)==len(lines)and all(x['bytes']==len(line)and x['sha256']==hashlib.sha256(line).hexdigest()for x,line in zip(recorded,lines))})
 owner_goals=[]
 for p in folder.glob('**/actor-owner.json'):
  v=json.loads(p.read_text());owner_goals.append({'trace':str(p.relative_to(OUT)),'role':v['role'],'goal_sha256':hashlib.sha256(v['goal'].encode()).hexdigest(),'actual_runtime':v['argv'][0],'model_override':v.get('model_override')})
 result['hosts'][h]={'root':roots[h],'profile_unchanged':e['profile_unchanged'],'source_sha_match':all(f['payload_verification'].values()),'actual_models':sorted({x['fields']['model']for x in e['observed_model_records']if x['fields'].get('model')}),'tool_calls':toolcalls,'agent_messages':messages,'question_ids':[v['id']for k,v in state.items()if k.startswith('state/questions/')],'inbound_message_ids':[v['id']for k,v in state.items()if k.startswith('state/network/messages/inbound/')],'canonical_states':[{k:v.get(k)for k in ('id','state','delivery_state','message','claim','acknowledged_at')if k in v}for k,v in state.items()if k.startswith('state/handoffs/')],'owned_actor_remaining':[x for x in f['all_attempt_owned_processes']if x['same_generation_alive']],'retained_services':{k:f['network_status'].get(k)for k in ('service_pid','engine_pid','endpoint_id','active','last_transport')},'goal_hashes':owner_goals,'keys_not_read':all(v['key_value_read']is False for v in f['key_metadata'])}
 result['wire_no_rewrite'][h]=wire
book=result['hosts']['book'];mini=result['hosts']['mini'];qid=book['question_ids'][0]if book['question_ids']else None
bs=json.loads((OUT/'book-evidence/preserved-evidence.json').read_text())['product_state_read_only_snapshot'];ms=json.loads((OUT/'mini-evidence/preserved-evidence.json').read_text())['product_state_read_only_snapshot']
question=next((v for k,v in bs.items()if k.startswith('state/questions/')and v['id']==qid),None);canonical=next((v for k,v in ms.items()if k.startswith('state/handoffs/')and v['id']==qid),None)
result['original_request']={'id':qid,'purpose':question.get('purpose')if question else None,'body':question.get('body')if question else None,'native_CID_requester':question.get('sender',{}).get('session_id')if question else None,'native_CID_reviewer':question.get('target',{}).get('session_id')if question else None,'canonical_body_equal':bool(question and canonical and question['body']==canonical['message']['body']),'canonical_state':canonical.get('state')if canonical else None,'actual_correlated_replies':len(question.get('replies',[]))if question else 0,'actual_consumer_ACK':bool(canonical and canonical.get('state')=='acknowledged'),'math_requests_dispatched':sum(c['tool']=='xsm_ask'for c in book['tool_calls'])}
result['actual_selected_candidates']=[c['arguments'].get('target')for c in book['tool_calls']if c['tool']=='xsm_connect']
result['p2p_deliver_evidence']=[]
be=[json.loads(x)for x in (OUT/'book-evidence/raw/transport.jsonl').read_text().splitlines()]
me=[json.loads(x)for x in (OUT/'mini-evidence/raw/transport.jsonl').read_text().splitlines()]
for event in be:
 if event.get('event')=='outbound-body'and event.get('application_op')=='deliver':
  incoming=[x for x in me if x.get('event')=='request'and x.get('body_sha256')==event['body_sha256']]
  result['p2p_deliver_evidence'].append({'sent_body_sha256':event['body_sha256'],'matching_remote_requests':len(incoming),'all_TLS_origins_match_actual_sender':bool(incoming)and all(x.get('origin')==book['retained_services']['endpoint_id']for x in incoming)})
result['frozen_network_sha256']=sources['files']['xsm/network.py']['sha256'];(OUT/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
manifest={str(p.relative_to(OUT)):{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}for p in sorted(OUT.rglob('*'))if p.is_file()and p.name!='artifact-manifest.json'};(OUT/'artifact-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'request':result['original_request'],'models':{h:result['hosts'][h]['actual_models']for h in ('book','mini')},'profile_unchanged':all(result['hosts'][h]['profile_unchanged']for h in ('book','mini')),'wire_integrity':all(x['exact_bytes_sha_match']for v in result['wire_no_rewrite'].values()for x in v),'tool_counts':{h:dict(collections.Counter(c['tool']for c in result['hosts'][h]['tool_calls']))for h in ('book','mini')}},ensure_ascii=False))
