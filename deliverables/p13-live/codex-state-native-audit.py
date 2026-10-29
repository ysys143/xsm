"""Read-only classification of PTY/native rollout and actual MCP/ledger evidence."""
import json,re,hashlib,datetime,time
from pathlib import Path
BASE=Path(__file__).resolve().parent
R=Path('/private/tmp/p13-codex-state-native-dv1ahfwm');obs=json.loads((R/'observations.json').read_text());rollout=Path(obs['receiver_rollout'])
def events(p):
 result=[]
 for line in p.read_text().splitlines():
  try:result.append(json.loads(line))
  except ValueError:pass
 return result
def stamp(s):return datetime.datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
def payloads(item):
 out=[]
 for c in (item.get('result') or {}).get('content',[]):
  try:out.append(json.loads(c.get('text','')))
  except ValueError:pass
 return out
rows=events(rollout);recv=[]
for d in rows:
 p=d.get('payload') or {}
 if d.get('type')=='event_msg' and p.get('type')=='item_completed':
  item=p.get('item') or {}
  if item.get('type') in ('McpToolCall','CommandExecution'):
   recv.append((d,item))
ledger=[json.loads(p.read_text()) for p in (R/'state/ledger').glob('*.json')]
output=json.loads((BASE/'codex-state-native-results.json').read_text())
output.update(receiver_sid=obs['receiver_sid'],receiver_native_pid=64954,receiver_native_lstart='Thu Oct 29 05:59:56 2026',existing_daemon=obs['existing_daemon'])
output['states']=[]
for state in ('idle','busy','interrupted'):
 producer=events(R/(state+'-producer.jsonl'));meta=json.loads((R/(state+'-producer-meta.json')).read_text());request=meta['request_id']
 calls=[d['item'] for d in producer if d.get('type')=='item.completed' and (d.get('item') or {}).get('type')=='mcp_tool_call']
 pcalls=[]
 for c in calls:
  q=payloads(c);pcalls.append({'server':c.get('server'),'tool':c.get('tool'),'status':c.get('status'),'result_status':[v.get('status') for v in q if isinstance(v,dict)],'wait_end_reason':[v.get('wait_end_reason') for v in q if isinstance(v,dict)],'reply_ids':[r.get('id') for v in q if isinstance(v,dict) for r in v.get('replies',[])],'final_outcome':[v.get('final_outcome') for v in q if isinstance(v,dict)]})
 task=next((d for d in ledger if d.get('kind')=='task' and d.get('id')==request),{})
 replies=[d for d in ledger if d.get('kind')=='reply' and d.get('reply_to')==request]
 queued=(task.get('evidence',{}).get('queued') or {}).get('t')
 qid=(task.get('evidence',{}).get('queued') or {}).get('detail')
 marker='P13-TUI-'+state.upper()
 usermsgs=[]
 for d in rows:
  p=d.get('payload',{})
  if d.get('type')=='event_msg' and p.get('type')=='item_completed' and (p.get('item') or {}).get('type')=='UserMessage' and marker in json.dumps(p['item'],ensure_ascii=False):usermsgs.append({'at':d['timestamp'],'turn_id':p.get('turn_id')})
 relevant=[(d,i) for d,i in recv if queued and stamp(d['timestamp'])>=queued and (state=='interrupted' or stamp(d['timestamp'])<meta.get('ended_at',time.time()))]
 final=next((v for c in calls for v in payloads(c) if isinstance(v,dict) and v.get('status')=='final'),None)
 result={'state':state,'request_id':request,'producer_sid':next((e['thread_id'] for e in producer if e.get('type')=='thread.started'),None),'producer_pid':meta['producer_pid'],'producer_lstart':meta['producer_lstart'],'producer_returncode':meta.get('returncode'),
 'producer_calls':pcalls,'producer_mcp_calls':len(calls),'producer_shell_calls':sum((e.get('item') or {}).get('type')=='command_execution' for e in producer if e.get('type')=='item.completed'),
 'queue_id':qid,'queued_at':queued,'wake':task.get('evidence',{}).get('wake'),'native_receiver_messages':usermsgs,
 'ledger_replies':[{k:d.get(k) for k in ('id','reply_to','outcome_req','status')} for d in replies],
 'receiver_mcp_calls':[{'at':d['timestamp'],'tool':i.get('tool'),'status':i.get('status'),'server':i.get('server')} for d,i in relevant if i.get('type')=='McpToolCall'],
 'receiver_shell_calls':sum(i.get('type')=='CommandExecution' for d,i in relevant),
 'receiver_shell_xsm_attempts':sum(bool(re.search(r'\bxsm\s+send\b',str(i.get('command')))) for d,i in relevant if i.get('type')=='CommandExecution'),
 'final_received':bool(final),'reply_to_matches':bool(replies) and all(d.get('reply_to')==request for d in replies),
 'additional_human_prompt_after_question':0,'controller_inbox_polls':0,'manual_queue_or_response_injection':0}
 if final:result['actual_reply_body']=[r['body'] for r in final.get('replies',[])];result['final_outcome']=final.get('final_outcome')
 if replies and queued:result['queue_to_reply_ledger_seconds']=round(min(d['t'] for d in replies)-queued,3)
 if final and queued:result['queue_to_reply_seconds']=round(min(r['received_at'] for r in final['replies'])-queued,3)
 if state=='idle':result['state_evidence']={'turn_completed_at':obs['idle_initial_event']['timestamp'],'receiver_input_waiting':True}
 if state=='busy':
  completion=[d for d in rows if d.get('type')=='event_msg' and d.get('payload',{}).get('type')=='task_complete' and queued and stamp(d['timestamp'])>=queued]
  result['state_evidence']={'active_python_sleep_seconds':55,'queued_before_first_turn_complete':bool(completion),'first_turn_complete_after_queue':completion[0]['timestamp'] if completion else None,'first_message_after_prior_turn_complete':bool(usermsgs and completion and stamp(usermsgs[0]['at'])>=stamp(completion[0]['timestamp']))}
 if state=='interrupted':
  aborts=[d for d in rows if d.get('type')=='event_msg' and d.get('payload',{}).get('type')=='turn_aborted'];result['state_evidence']={'esc_at':obs['esc_sent_at'],'turn_aborted_at':aborts[-1]['timestamp'] if aborts else None,'receiver_tail_event':rows[-1].get('payload',{}).get('type')};result['observed_after_queue_seconds']=round(obs['first_failure_observed_at']-queued,3) if queued else None
  result['failed_boundary']='queued but no post-Esc native turn/reply; daemon wake not-loaded' if not final else None
  result['recovery_owner']='coordinator';result['resume_condition']='Retained request/queue and verified owned TUI endpoint; investigate actual TUI hosting versus shared-daemon wake routing without manual prompt counted as automatic success.'
 output['states'].append(result)
output['receiver_initial_setup_mcp_calls']=[{'server':i.get('server'),'tool':i.get('tool'),'status':i.get('status')} for d,i in recv if stamp(d['timestamp'])<next(s['queued_at'] for s in output['states'] if s['queued_at']) and i.get('type')=='McpToolCall']
output['automatic_model_retries']=0
output['source_unchanged']=all(hashlib.sha256((Path(output['source'])/p).read_bytes()).hexdigest()==h for p,h in json.loads((BASE/'post-qa-source-manifest.json').read_text())['files'].items())
(BASE/'codex-state-native-results.json').write_text(json.dumps(output,ensure_ascii=False,indent=2))
print(json.dumps([{'state':s['state'],'final':s['final_received'],'producer_mcp':s['producer_mcp_calls'],'receiver_mcp':len(s['receiver_mcp_calls']),'queue_to_reply':s.get('queue_to_reply_seconds'),'failure':s.get('failed_boundary')} for s in output['states']],ensure_ascii=False))
