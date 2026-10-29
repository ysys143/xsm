"""Audit the original trust-preparation stop without launching a client."""
import hashlib,json,pathlib,sqlite3,subprocess,sys
ROOT=pathlib.Path('/private/tmp/native-cancel-yk9ht9a9')
PUBLIC=pathlib.Path(__file__).resolve().parent
def load(p):return json.loads(pathlib.Path(p).read_text())
def sha(b):return hashlib.sha256(b).hexdigest()
def start(pid):return subprocess.run(['ps','-o','lstart=','-p',str(pid)],capture_output=True,text=True).stdout.strip()or None
def main():
 d=load(ROOT/'result.json');block=load(ROOT/'preparation-blocker.json')
 pty=(ROOT/'receiver.pty').read_bytes()
 assert b'Trust this folder?'in pty and b'Your trust decision will be saved'in pty
 assert d['controller_Esc']==0 and not d.get('pending')and not d.get('actual_native_CID')
 assert not block['trust_response_sent']
 folders=list((ROOT/'tui/proxies').iterdir());calls=[];cancel=[];wire=[]
 for folder in folders:
  for n in ['client-wire.jsonl','server-wire.jsonl']:
   f=folder/n
   if not f.exists():continue
   wire.append({'path':str(f),'sha256':sha(f.read_bytes())})
   for line in f.read_text().splitlines():
    obj=json.loads(line)
    if n=='client-wire.jsonl'and obj.get('method')=='tools/call':calls.append(obj)
    if n=='client-wire.jsonl'and obj.get('method')=='notifications/cancelled':cancel.append(obj)
 con=sqlite3.connect('file:/Users/jaesolshin/.codex-3/state_5.sqlite?mode=ro',uri=True)
 try:threads=con.execute('select id from threads where cwd=?',(str(ROOT/'work'),)).fetchall()
 finally:con.close()
 assert not threads and not folders and not calls and not cancel
 assert not list((ROOT/'state/handoffs').glob('*/*.json'))
 known=[dict(x,current_lstart=start(x['pid']))for x in d['known_process_final_audit']]
 assert all(x['current_lstart']!=x['lstart']for x in known)
 remaining=[]
 for line in subprocess.check_output(['ps','-ax','-o','pid=,ppid=,comm=,args='],text=True).splitlines():
  a=line.strip().split(None,3)
  if len(a)==4 and str(ROOT)in a[3]and pathlib.Path(a[2]).name in ['codex','node']:remaining.append(int(a[0]))
 assert not remaining
 fm=load(PUBLIC.parent/'final-source-manifest.json');source=pathlib.Path(fm['snapshot'])
 assert all(sha((source/n).read_bytes())==h for n,h in fm['files'].items())
 s={'status':'preparation blocked by native TUI folder trust; native cancellation unobserved','blocker_phase':'before native CID/model/tool-host, not a product cancellation failure or runtime unsupported verdict','condition_difference':'prior PTY harness used already trusted repository cwd; this one condition used a new private Git cwd','CLI':d['CLI'],'source':str(source),'source_files_SHA_verified':len(fm['files']),'TUI_launches':1,'initial_goal_queued_to_TUI':1,'actual_native_CIDs':len(threads),'actual_native_model_turns':0,'followup_turns':0,'model_retries':0,'actual_MCP_servers':len(folders),'actual_tools_calls':len(calls),'pending_MCP_calls':0,'standard_pending_call_Esc':d['controller_Esc'],'notifications_cancelled':len(cancel),'MCP_EOF':'unobserved; no MCP stream opened','cancelled_request_correlation':'unobserved; no pending RPC existed','canonical_originals':0,'original_preservation_and_followup_recovery':'unobserved, no original was seeded or received','claim_ACK_results_injected':0,'raw_wire':wire,'private_raw_root':str(ROOT),'PTY_sha256':sha(pty),'PTY_bytes':len(pty),'trust_choice_saved_by_evaluator':False,'profile_configuration_unchanged':d['profile_unchanged'],'profile_hashes':{'before':d['profile_before'],'after':d['profile_after']},'cleanup':{'owned_controller_SIGINT':'preparation stop only, not MCP cancellation','idle_CtrlD':'cleanup at trust screen, not pending-tool cancel','TUI_exit_code':d['TUI_exit_code'],'owned_cleanup_signals':d['cleanup_signals'],'known_process_final_audit':known,'remaining_owned_native_candidates':remaining},'all_A16_07_A18_02_proven':False,'owner':'coordinator; no second condition executed','resume_precondition':'a separately authorized evaluation with its TUI folder-trust precondition satisfied; current task does not authorize saving a trust choice'}
 (PUBLIC/'summary.json').write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:s[k]for k in ['status','TUI_launches','actual_native_CIDs','actual_native_model_turns','actual_tools_calls','standard_pending_call_Esc','notifications_cancelled','source_files_SHA_verified']},ensure_ascii=False))
 return s
if __name__=='__main__':
 s=main()
 if '--require-native'in sys.argv:
  print('UNOBSERVED: folder trust stopped preparation before any native MCP wait/cancellation',file=sys.stderr)
  sys.exit(1)
