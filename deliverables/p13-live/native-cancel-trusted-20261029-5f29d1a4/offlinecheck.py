"""Audit one real native Esc and exact pending MCP wire without new calls."""
import json,pathlib,hashlib,re,subprocess,sys
ROOT=pathlib.Path('/private/tmp/native-cancel-trusted-w23wicuo')
PUBLIC=pathlib.Path(__file__).resolve().parent
REPO=pathlib.Path('/Users/jaesolshin/Documents/GitHub/cross-session-messaging')
def load(p):return json.loads(pathlib.Path(p).read_text())
def rows(p):
 if not pathlib.Path(p).exists():return[]
 out=[]
 for line in pathlib.Path(p).read_text().splitlines():
  try:out.append(json.loads(line))
  except ValueError:pass
 return out
def sha(b):return hashlib.sha256(b if isinstance(b,bytes)else b.encode()).hexdigest()
def lstart(pid):return subprocess.run(['ps','-o','lstart=','-p',str(pid)],capture_output=True,text=True).stdout.strip()or None
def main():
 d=load(ROOT/'result.json');pre=load(PUBLIC/'trust-preflight.json');post=load(PUBLIC/'trust-postflight.json')
 assert pre['trusted_verified']and pre['exact_project_entry']and post['trusted_verified']
 assert d['controller_Esc']==1 and d['automatic_model_retries']==0
 CID=d['actual_native_CID'];req=d['pending']['request'];mid=req['id'];folder=pathlib.Path(d['pending']['folder'])
 requests=rows(folder/'client-wire.jsonl');responses=rows(folder/'server-wire.jsonl');events=rows(folder/'events.jsonl')
 calls=[x for x in requests if x.get('method')=='tools/call'];notifications=[x for x in requests if x.get('method')=='notifications/cancelled']
 assert len(calls)==1 and calls[0]==req and req['params']['name']=='xsm_inbox'
 assert req['params']['arguments']['wait']==60
 meta=req['params']['_meta'];assert meta['threadId']==CID
 assert meta['x-codex-turn-metadata']['sandbox_mode']=='read-only'
 sent=next(x for x in events if x['direction']=='client'and x.get('id')==mid and x.get('method')=='tools/call')
 ended=next(x for x in events if x['direction']=='server'and x.get('id')==mid)
 assert sent['at']<d['standard_cancel_at']<ended['at']
 response=next(x for x in responses if x.get('id')==mid)
 value=json.loads(response['result']['content'][0]['text'])
 assert value=={'messages':[],'claims':[],'inbox_pending':0}and response['result']['isError']is False
 native=rows(ROOT/'native-rollout.jsonl')
 life=[{'timestamp':x.get('timestamp'),'type':x['payload']['type']}for x in native if x.get('type')=='event_msg'and(x.get('payload')or{}).get('type')in ['task_started','task_complete','task_completed','turn_aborted']]
 started=sum(x['type']=='task_started'for x in life);aborted=sum(x['type']=='turn_aborted'for x in life);completed=sum(x['type']in ['task_complete','task_completed']for x in life)
 assert started==1 and aborted==1 and completed==0
 commands=[];nested=[]
 for x in native:
  p=x.get('payload')or{}
  if x.get('type')=='response_item'and p.get('type')=='custom_tool_call':
   text=p.get('input','');names=re.findall(r'tools\.([A-Za-z_][A-Za-z0-9_]*)',text);nested.extend(names)
   commands.append({'tool':p.get('name'),'input_sha256':sha(text),'nested_tools':names})
 assert set(nested)=={'exec_command','mcp__xsm__xsm_inbox'}
 assert not notifications
 regs=[load(p)for p in(ROOT/'state/sessions').glob('*.json')]
 external=[x for x in regs if x.get('runtime')!='codex'or x.get('home')!='/Users/jaesolshin/.codex-3'or x.get('session_id')!=CID]
 assert len(regs)==1 and not external
 assert not list((ROOT/'state/handoffs').glob('*/*.json'))
 fm=load(PUBLIC.parent/'final-source-manifest.json');source=pathlib.Path(fm['snapshot'])
 assert all(sha((source/n).read_bytes())==h for n,h in fm['files'].items())
 assert d['primary_unchanged']and len(d['primary_before'])==135
 assert all(sha((REPO/n).read_bytes())==fm['files'][n]for n in fm['stable_product_paths'])
 known=[dict(x,current_lstart=lstart(x['pid']))for x in d['known_process_final_audit']]
 assert all(x['current_lstart']!=x['lstart']for x in known)
 remaining=[]
 for line in subprocess.check_output(['ps','-ax','-o','pid=,ppid=,comm=,args='],text=True).splitlines():
  a=line.strip().split(None,3)
  if len(a)==4 and str(ROOT)in a[3]and pathlib.Path(a[2]).name in ['codex','node']:remaining.append(int(a[0]))
 assert not remaining
 streams=rows(folder/'stream-events.jsonl');before=[x for x in streams if x['at']<=d['measurement_end_at']]
 pty=(ROOT/'receiver.pty').read_bytes();assert b'Error: interrupted'in pty and b'Conversation interrupted'in pty
 summary={'scope':'one trusted-cwd native Esc while actual inbox RPC pending; cancellation propagation not observed','CLI':d['CLI'],'source':str(source),'source315_verified':len(fm['files']),'repository_primary_before_after_verified':135,'repository_source_unchanged':True,
 'trust':{'exact_repository_preexisting':True,'preflight_config_sha256':pre['config_sha256'],'postflight_still_trusted':post['trusted_verified'],'trust_selection_saved_by_evaluator':False,'persisted_trust_override':False},
 'runtime_binding':'same invocation-only private XSM/frozen MCP proxy parameters; native read-only sandbox/approval-never flags; no persisted profile configuration edits',
 'native_CID_sha256':sha(CID),'native_TUI_launches':1,'native_task_started':started,'native_turn_aborted':aborted,'native_task_completed':completed,'controller_prompt_texts':d['controller_model_prompts'],'same_CID_followup_turn_started':False,'followup_limit':'follow-up text visible in PTY editor, no second task_started; evaluator 150-second wait ended; submission cause not established','model_condition_retries':0,
 'actual_pending_call':{'request_id':mid,'tool':'xsm_inbox','requested_wait':60,'caller_CID_matches_native':True,'sandbox_mode':'read-only','client_at':sent['at'],'standard_Esc_at':d['standard_cancel_at'],'server_at':ended['at'],'wire_request_sha256':sent['sha256'],'wire_response_sha256':ended['sha256'],'RPC_elapsed_seconds':ended['at']-sent['at'],'Esc_to_response_seconds':ended['at']-d['standard_cancel_at'],'standard_Esc_count':1,'native_abort_recorded':True},
 'MCP_cancelled_notifications':len(notifications),'MCP_cancelled_notification_correlated':False,'MCP_RPC_response':{'same_request_id':True,'isError':False,'messages':0,'claims':0,'inbox_pending':0},'native_UI_interrupted_error':True,'MCP_isError_count':sum(bool((x.get('result')or{}).get('isError'))for x in responses),'EOF_events_before_cleanup':before,'EOF_events_all':streams,'EOF_interpretation':'not observed; process cleanup/kill is never counted as EOF or cancelled notification',
 'actual_claim_ACK_calls':0,'canonical_messages':0,'late_original_preservation_recovery':'unobserved: no real original existed or was manually seeded','client_server_metadata_result_ACK_injection':0,'native_tool_calls':commands,'nested_tool_names':nested,'outgoing_send_or_other_service_tool_calls':0,'private_registry_records':len(regs),'private_registry_external_records':len(external),'controller_registration_setups':len(d['initial_actual_registration_setup']),
 'native_lifecycle':life,'original_failure':d.get('failure'),'profile_unchanged':d['profile_unchanged'],'profile_changed_names':[k for k,v in d['profile_before'].items()if d['profile_after'].get(k)!=v],'profile_drift_writer':'unknown; no evaluator/model profile edit command','cleanup_signals':d['cleanup_signals'],'known_process_final_audit':known,'remaining_owned_native_processes':remaining,'private_raw_root':str(ROOT),'all_A16_07_A18_02_proven':False}
 (PUBLIC/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'native_CID_count':1,'task_started':started,'turn_aborted':aborted,'completed':completed,'pending_MCP':len(calls),'standard_Esc':1,'cancel_notifications':len(notifications),'RPC_elapsed_seconds':round(ended['at']-sent['at'],3),'source135_unchanged':True,'registry_external':0,'owned_remaining':0},ensure_ascii=False))
 return summary
if __name__=='__main__':
 s=main()
 if '--require-native-cancellation-propagation'in sys.argv:
  print('PARTIAL: real native Esc observed; no MCP cancelled notification, second native turn, or late original recovery evidence',file=sys.stderr);sys.exit(1)
