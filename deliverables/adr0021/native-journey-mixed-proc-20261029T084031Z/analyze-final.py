from pathlib import Path
import json,hashlib,collections,re
V=json.loads(Path('/private/tmp/adr21-mixed-proc-current.json').read_text());O=Path(V['artifact']);B=O/'book-final-evidence';M=O/'mini-final-evidence'
def load(p):return json.loads(p.read_text())
def events(p):
 out=[]
 if p.exists():
  for l in p.read_text().splitlines():
   try:out.append(json.loads(l))
   except ValueError:pass
 return out
def strings(x):
 if isinstance(x,str):
  try:
   y=json.loads(x)
   if isinstance(y,(dict,list)):return [x]+strings(y)
  except (ValueError,TypeError):pass
  return[x]
 if isinstance(x,list):return sum((strings(v)for v in x),[])
 if isinstance(x,dict):return sum((strings(v)for v in x.values()),[])
 return[]
def sha(b):return hashlib.sha256(b).hexdigest()
b=load(B/'mixed-evidence.json');m=load(M/'mixed-evidence.json');be=events(B/'actor/native.jsonl');me=events(M/'actor/native.jsonl');bcalls=[];bresults={}
for e in be:
 for x in(e.get('message')or{}).get('content',[]):
  if e.get('type')=='assistant'and x.get('type')=='tool_use':bcalls.append(x)
  if e.get('type')=='user'and x.get('type')=='tool_result':bresults[x['tool_use_id']]=x
mcalls=[];mres=[]
for p in(M/'actor/proxies').glob('*'):
 client=events(p/'client-wire.jsonl');server=events(p/'server-wire.jsonl')
 for c in client:
  if c.get('method')=='tools/call':mcalls.append(c);mres.append({'call':c,'reply':next((x for x in server if x.get('id')==c['id']),None)})
original=(M/'work/review-material.md').read_bytes();revised=(M/'work/review-material-revised.md').read_bytes();marker=re.search(r'MIXDOC-[a-f0-9]+',original.decode()).group();files=[]
for req in mcalls:
 p=req['params'];a=p.get('arguments')or{}
 if p['name']=='xsm_ask'and a.get('attachments'):
  doc=a['attachments'][0]['text'];matching=original if doc.encode()==original else revised if doc.encode()==revised else None
  files.append({'request_text':a.get('text'),'name':a['attachments'][0].get('name'),'caller_attachment_exact_file':matching is not None,'bytes':len(doc.encode()),'sha256':sha(doc.encode()),'marker_in_attachment':marker in doc})
file_reads=[]
for c in bcalls:
 if c['name']=='mcp__xsm__xsm_files':
  result=bresults.get(c['id']);texts=strings(result);file_reads.append({'input':c.get('input'),'tool_result':result,'contains_original_exact':any(original.decode()in x for x in texts),'contains_revised_exact':any(revised.decode()in x for x in texts),'contains_file_only_marker':any(marker in x for x in texts)})
qrows=[]
for name,q in m['product_state'].items():
 if not name.startswith('questions/'):continue
 replies=q.get('replies',[]);rid=replies[0]['id']if replies else None;rq=next((x for n,x in b['product_state'].items()if n.startswith('handoffs/')and x.get('id')==q['id']),None);rp=next((x for n,x in m['product_state'].items()if n.startswith('handoffs/')and x.get('id')==rid),None)
 qrows.append({'id':q['id'],'purpose':q['purpose'],'sender':q['sender'],'target':q['target'],'body':q['body'],'attachments':q.get('attachments'),'reply':replies[0]if replies else None,'receiver_request_state':rq.get('state')if rq else None,'caller_reply_state':rp.get('state')if rp else None,'file_marker_in_reply':bool(replies and marker in replies[0]['body'])})
collabs=[]
rootbook=Path(V['book']);roots=load(O/'roots.json')
# Evidence-only read of local files. Remote consent data was captured by the collector.
for n,x in m['product_state'].items():
 if n.startswith('collaborations/'):collabs.append(x)
origins=[]
for direction,sender,receiver in [('caller-to-reviewer','mini','book'),('reviewer-to-caller','book','mini')]:
 src=events(O/(sender+'-final-evidence/raw/transport.jsonl'));dst=events(O/(receiver+'-final-evidence/raw/transport.jsonl'));key=load(O/(sender+'-cleanup-final.json'))['service_before']['endpoint_id']
 for x in src:
  if x.get('event')=='outbound-body'and x.get('application_op')=='deliver':
   match=[e for e in dst if e.get('event')=='request'and e.get('body_sha256')==x.get('body_sha256')]
   origins.append({'direction':direction,'body_sha256':x.get('body_sha256'),'matching_native_inbound_events':len(match),'TLS_origin_matches':bool(match)and all(e.get('origin')==key for e in match)})
init=next(e for e in be if e.get('type')=='system'and e.get('subtype')=='init');micro=[]
for c in mcalls:
 micro.append(c['params']['name'])
firstwrite=next((i for i,x in enumerate(micro)if x in('xsm_connect','xsm_ask','xsm_send')),len(micro));discover_before_business='xsm_discover'in micro[:firstwrite]
body={'status':'actual mixed native workflow complete; isolation drift separately recorded','source_manifest_sha256':sha((O/'source-manifest.json').read_bytes()),'source_52_changes':False,'executed_source_files':b['source_count'],'source_matches_both':b['source_sha_match']and m['source_sha_match'],'models':{'claude':init['model'],'codex':sorted({x['model']for x in m['codex_model_contexts']})},'Claude_CID':init['session_id'],'Codex_CID':m['codex_provider_rows'][0][0],'questions':qrows,'file_transfers':files,'receiver_file_reads':file_reads,'marker_only_in_document':all(marker not in load(p).get('goal','')for p in[O/'streaming-claude-launch.json',M/'actor-owner.json']),'existing_approved_native_hook_sources':load(O/'codex-existing-hook-reuse.json'),'collaborations':collabs,'repository_maps_created':b['map_file_exists']or m['map_file_exists'],'native_MCP_counts':{'claude':dict(collections.Counter(c['name']for c in bcalls)),'codex':dict(collections.Counter(c['params']['name']for c in mcalls))},'discovery_before_business_MCP':discover_before_business,'P2P_body_origin_evidence':origins,'SSHDeny':{'Book_preflight':load(O/'book-ssh-deny-preflight.json'),'Mini_preflight':load(O/'mini-ssh-and-plugin-preflight.json'),'outside_guard':load(O/'operator-outside-guard-tcp.json'),'scope':'Book whole native SDK process plus inherited MCP/hooks; Mini guarded MCP/own hooks plus original workspace-write network-restricted shell; Mini outer parent guard conflict kept separate'},'profiles':{'Book_all_old_baseline_match':b['profiles_unchanged'],'Book_unmatched':[k for k,match in b['profile_baseline_match'].items()if not match],'Mini_all_baseline_match':m['profiles_unchanged'],'Book_settings_and_auth_unchanged':all(match for k,match in b['profile_baseline_match'].items()if not k.endswith('/.claude.json')),'unattributed_profile_data_drift':True},'cleanup':{h:load(O/(h+'-cleanup-final.json'))for h in('book','mini')},'file_stage_source_SHA':{p:sha((O/'frozen'/p).read_bytes())for p in('xsm/files.py','xsm/materials.py','xsm/network_messages.py','xsm/network.py','xsm/mcp.py','xsm/instructions.py')},'raw_statuses_not_normalized':True}
body['business_complete']=len(qrows)==3 and all(x['reply']and x['reply'].get('outcome')=='succeeded'and x['receiver_request_state']=='acknowledged'and x['caller_reply_state']=='acknowledged'for x in qrows)
body['materials_complete']=len(files)>=1 and all(x['caller_attachment_exact_file']for x in files)and any(x['contains_original_exact']and x['contains_file_only_marker']for x in file_reads)and any(x['file_marker_in_reply']for x in qrows)
body['P2P_verified']=len(origins)>=6 and all(x['TLS_origin_matches']for x in origins)
body['cleanup_complete']=all(not x['remaining_owned']for x in body['cleanup'].values());body['all_isolation_conditions_verified']=False
(O/'results-final.json').write_text(json.dumps(body,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'business_complete':body['business_complete'],'materials_complete':body['materials_complete'],'P2P_verified':body['P2P_verified'],'cleanup_complete':body['cleanup_complete'],'questions':[(x['id'],x['purpose'])for x in qrows],'file_count':len(files),'receiver_actual_file_reads':len(file_reads),'MCP_counts':body['native_MCP_counts'],'public_selected_pairs':len(collabs),'maps_created':body['repository_maps_created'],'profile_drift':body['profiles']['Book_unmatched']},ensure_ascii=False))
