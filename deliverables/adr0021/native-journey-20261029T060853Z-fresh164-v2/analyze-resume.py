"""Evidence analysis only. Never changes live messaging state."""
import json,hashlib,collections,re
from pathlib import Path
OUT=Path(__file__).resolve().parent;BAD=re.compile('[\u3400-\u9fff\u3040-\u30ff]')
def load(p):return json.loads(p.read_text())
def sha(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def events(folder,name):
 p=folder/name
 return [json.loads(x)for x in p.read_text().splitlines()]if p.exists()else[]
def stage(root,folder):
 calls=[];responses=[];barriers=[];integrity=[]
 for p in (folder/'proxies').glob('*'):
  client=events(p,'client-wire.jsonl');server=events(p,'server-wire.jsonl');calls.extend(x for x in client if x.get('method')=='tools/call')
  for c in client:
   if c.get('method')=='tools/call':
    answer=next((x for x in server if x.get('id')==c['id']),None);responses.append({'call':c,'response':answer})
  if(p/'startup-barrier.json').exists():barriers.append(load(p/'startup-barrier.json'))
  audit=events(p,'events.jsonl')
  for direction in('client','server'):
   raw=p/(direction+'-wire.jsonl')
   if raw.exists():
    lines=raw.read_bytes().splitlines(keepends=True);notes=[x for x in audit if x.get('direction')==direction]
    integrity.append({'file':str(raw.relative_to(OUT)),'same_bytes':len(lines)==len(notes)and all(n['bytes']==len(line)and n['sha256']==hashlib.sha256(line).hexdigest()for n,line in zip(notes,lines))})
 native=events(folder,'native.jsonl');cids=[x.get('thread_id')for x in native if x.get('type')=='thread.started'];final=[x['item']['text']for x in native if x.get('type')=='item.completed'and(x.get('item')or{}).get('type')=='agent_message']
 return {'CIDs':cids,'tool_counts':dict(collections.Counter(x['params']['name']for x in calls)),'calls_and_responses':responses,'startup_barriers':barriers,'native_agent_messages':final,'wire_integrity':integrity}
def strings(v):
 if isinstance(v,str):return[v]
 if isinstance(v,dict):return sum((strings(x)for x in v.values()),[])
 if isinstance(v,list):return sum((strings(x)for x in v),[])
 return[]
summary={'condition':'same original two .164 CIDs; original source manifest; services restarted with same XSM_HOME/state/keys','manifest_sha256':hashlib.sha256((OUT/'source-manifest.json').read_bytes()).hexdigest(),'hosts':{},'workflow':[]}
for h in('book','mini'):
 root=OUT/(h+'-resume-evidence');before=load(OUT/(h+'-before-resume.json'));after=load(root/'resume-evidence/after-resume.json');stages={'before_pause':stage(root,root/'resume-evidence/phase0/actor'),'failed_registration_gate':stage(root,root/'resume-evidence/before-tool-exposure-corrected/actor'),'corrected_tool_gate':stage(root,root/'resume-evidence/before-recover/actor'),'recovery':stage(root,root/'actor')}
 summary['hosts'][h]={'CID':before['CID'],'initial_CLI':before['session_metadata'][0]['cli_version'],'CLI':before['CLI_version'],'profile_unchanged':after['profile_unchanged_since_resume'],'source_match':after['source_all_match'],'stages':stages,'message_IDs_before':sorted({x['id']for n,x in before['product_state'].items()if n.startswith('network/messages/')}),'message_IDs_after':sorted({x['id']for n,x in after['product_state'].items()if n.startswith('network/messages/')}),'cleanup':load(OUT/(h+'-resume-final-cleanup.json'))}
 summary['hosts'][h]['same_CID_in_every_stage']=all(set(s['CIDs'])=={before['CID']}for s in stages.values())
 summary['hosts'][h]['new_message_IDs_after_resume']=sorted(set(summary['hosts'][h]['message_IDs_after'])-set(summary['hosts'][h]['message_IDs_before']))
B=load(OUT/'book-before-resume.json');BA=load(OUT/'book-resume-evidence/resume-evidence/after-resume.json');M=load(OUT/'mini-before-resume.json');MA=load(OUT/'mini-resume-evidence/resume-evidence/after-resume.json')
for qid in('f411925587a64d35','85f7b01d4e4c4eed','9e17a98be37c40bc'):
 q=B['product_state']['questions/'+qid+'.json'];qa=BA['product_state']['questions/'+qid+'.json'];reply=q['replies'][0];r_id=reply['id'];mb=next(x for n,x in M['product_state'].items()if n.startswith('handoffs/')and x.get('id')==qid);ma=next(x for n,x in MA['product_state'].items()if n.startswith('handoffs/')and x.get('id')==qid);rb=next(x for n,x in B['product_state'].items()if n.startswith('handoffs/')and x.get('id')==r_id);ra=next(x for n,x in BA['product_state'].items()if n.startswith('handoffs/')and x.get('id')==r_id)
 recovery=summary['hosts']['book']['stages']['recovery']['calls_and_responses'];request_recovered=any(x['call']['params']['name']=='xsm_question_status'and x['call']['params'].get('arguments',{}).get('id')==qid and any(reply['body']in s for s in strings(x['response']))for x in recovery)
 mini_recovery=summary['hosts']['mini']['stages']['recovery']['calls_and_responses'];body_recovered=any(x['call']['params']['name']=='xsm_inbox'and any(q['body']in s for s in strings(x['response']))for x in mini_recovery)
 summary['workflow'].append({'question_id':qid,'purpose':q['purpose'],'question_body':q['body'],'reply_id':r_id,'reply_body':reply['body'],'outcome':reply.get('outcome'),'same_question_body':q['body']==qa['body'],'same_replies':q['replies']==qa['replies'],'request_state_before':mb['state'],'request_state_after':ma['state'],'reply_state_before':rb['state'],'reply_state_after':ra['state'],'original_request_digest_preserved':mb.get('digest')==ma.get('digest')and mb.get('identity')==ma.get('identity'),'original_network_packet_preserved':next(x['packet']for n,x in M['product_state'].items()if n.startswith('network/messages/inbound/')and x['id']==qid)==next(x['packet']for n,x in MA['product_state'].items()if n.startswith('network/messages/inbound/')and x['id']==qid),'request_body_recovered_in_real_MCP':body_recovered,'reply_body_recovered_in_real_MCP':request_recovered})
old='ed42ef075aff4b47';oldrow=next(x for n,x in MA['product_state'].items()if n.startswith('handoffs/')and x['id']==old)
summary['older_failed_sample']={'id':old,'canonical_state':oldrow['state'],'unchanged_files':{h:all(a['product_file_sha256'].get(n)==v for n,v in b['product_file_sha256'].items()if old in n)for h,b,a in [('book',B,BA),('mini',M,MA)]}}
summary['completed']=all(x['request_state_after']=='acknowledged'and x['reply_state_after']=='acknowledged'and x['same_question_body']and x['same_replies']and x['original_network_packet_preserved']and x['request_body_recovered_in_real_MCP']and x['reply_body_recovered_in_real_MCP']for x in summary['workflow'])and all(x['same_CID_in_every_stage']and not x['new_message_IDs_after_resume']and not x['cleanup']['remaining_owned']for x in summary['hosts'].values())
(OUT/'resume-results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'completed':summary['completed'],'workflow':[{'id':x['question_id'],'before':x['request_state_before'],'after':x['request_state_after'],'request_body_MCP':x['request_body_recovered_in_real_MCP'],'reply_body_MCP':x['reply_body_recovered_in_real_MCP']}for x in summary['workflow']],'same_CIDs':{h:v['same_CID_in_every_stage']for h,v in summary['hosts'].items()},'new_message_IDs':{h:v['new_message_IDs_after_resume']for h,v in summary['hosts'].items()},'old_sample':summary['older_failed_sample'],'profile_unchanged':{h:v['profile_unchanged']for h,v in summary['hosts'].items()}},ensure_ascii=False))
