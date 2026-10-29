"""Read-only audit of the retained real-native crash sample; no model calls."""
import hashlib,json,subprocess,time
from pathlib import Path
BASE=Path(__file__).resolve().parent
report=json.loads((BASE/'owned-crash-results.json').read_text());root=Path(report['private_root'])
ps=[]
for line in subprocess.check_output(['ps','-axo','pid=,ppid=,pgid=,comm='],text=True).splitlines():
 fields=line.split(None,3)
 if len(fields)==4:ps.append({'pid':int(fields[0]),'ppid':int(fields[1]),'pgid':int(fields[2]),'comm':fields[3]})
ledger=[json.loads(p.read_text()) for p in (root/'state/ledger').glob('*.json')]
handoffs=[json.loads(p.read_text()) for p in (root/'state/handoffs').rglob('*.json')]
for row in report['cases']:
 cut=row['boundary'];before=json.loads((root/(cut+'-before.json')).read_text());after=json.loads((root/(cut+'-final.json')).read_text())
 row['immutable_request_preserved']=all(before.get(k)==after.get(k) for k in ('id','body','digest','sender','work_context','context_id'))
 row['same_native_execution_after_recovery']=before.get('child')==after.get('child') if before.get('child') else None
 row['final_outcome']=(after.get('result') or {}).get('outcome')
 row['native_mcp_calls']=sum(t['type']=='mcp_tool_call' for t in row.get('native_tools',[]))
 row['native_default_tool_calls']=len(row.get('native_tools',[]))
 row['reply_ledger']=[{k:d.get(k) for k in ('id','status','reply_to','resends')} for d in ledger if d.get('id')==after.get('reply_id') and d.get('kind')=='reply']
 matching=[h for h in handoffs if h.get('id')==after.get('reply_id')]
 row['canonical_reply_originals']=len(matching)
 row['canonical_reply_body_matches']=bool(matching) and all((h.get('message') or {}).get('body')==(after.get('result') or {}).get('body') for h in matching)
 pid=(after.get('child') or {}).get('pid')
 row['remaining_native_process_group']=[p for p in ps if p['pgid']==pid or p['pid']==pid]
 row['controller_still_present']=any(p['pid']==row['initial']['controller_pid'] for p in ps)
 row['verified']=all((row['boundary_reached'],row['initial']['returncode']==-9,row['immutable_request_preserved'],row['effect_final']=='1',row['final_outcome']=='succeeded',row['canonical_reply_originals']==1,not row['remaining_native_process_group'],not row['controller_still_present']))
report['audit_at']=time.time();report['total_native_started_turns']=sum(r.get('actual_turn_started_events',0) for r in report['cases'])
report['total_native_children']=sum(r.get('native_turns_total',0) for r in report['cases'])
report['total_default_tool_calls']=sum(r['native_default_tool_calls'] for r in report['cases'])
report['total_mcp_calls']=sum(r['native_mcp_calls'] for r in report['cases'])
report['boundaries_verified']=sum(r['verified'] for r in report['cases'])
(BASE/'owned-crash-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
manifest={'frozen_source':report['frozen'],'frozen_manifest':'deliverables/p13-live/post-qa-source-manifest.json','raw_root':str(root),'files':{}}
for p in [BASE/'owned-crash-eval.py',BASE/'owned-crash-audit.py',BASE/'owned-crash-results.json']:
 manifest['files'][p.name]=hashlib.sha256(p.read_bytes()).hexdigest()
manifest['private_evidence']={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and (p.name.endswith(('-before.json','-final.json','-cut.json')) or 'owned-runs' in p.parts)}
(BASE/'owned-crash-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps({k:report[k] for k in ('boundaries_verified','total_native_started_turns','total_native_children','total_default_tool_calls','total_mcp_calls','elapsed_seconds')},ensure_ascii=False))
for r in report['cases']:print(r['boundary'],r['canonical_reply_body_matches'],r['verified'])
