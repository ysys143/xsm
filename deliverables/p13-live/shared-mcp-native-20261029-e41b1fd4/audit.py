"""Read-only audit of the real native calls, not a simulated shared server."""
import collections
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/private/tmp/shared-mcp-native-yjfl3mjl')
PUBLIC = Path(__file__).resolve().parent


def load(p):
    return json.loads(Path(p).read_text())


def sha(value):
    return hashlib.sha256(value if isinstance(value, bytes) else value.encode()).hexdigest()


def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


d = load(ROOT/'result.json')
root_cid = next(x['thread_id'] for x in rows(ROOT/'native.jsonl') if x.get('type')=='thread.started')
children = {x['id']:x for x in d['actual_native_threads'] if x['id']!=root_cid}
labels = {sid:('A' if 'review_five' in row['source'] else 'B') for sid,row in children.items()}
questions = {x.stem:load(x) for x in (ROOT/'state/questions').glob('*.json')}
instances, all_calls, send_checks, file_read_checks = [], [], [], []
known_processes = {d['handle']['pid']:d['handle']['lstart']}
for folder in sorted((ROOT/'proxies').iterdir()):
    h = load(folder/'handles.json')
    for key in ('proxy','server'):
        known_processes[h[key]['pid']]=h[key]['lstart']
    for a in h['native_ancestor_chain']:
        if Path(a['comm']).name=='codex':known_processes[a['pid']]=a['lstart']
    wire = rows(folder/'client-wire.jsonl')
    calls = {x['id']:x for x in wire if x.get('method')=='tools/call'}
    actual = [x for x in rows(folder/'events.jsonl') if x.get('direction')=='client' and x.get('method')=='tools/call']
    ids = {(x.get('actual_meta')or{}).get('threadId') for x in actual}
    for row in actual:
        cid = (row.get('actual_meta')or{}).get('threadId')
        all_calls.append({'at':row['at'],'server_pid':h['server']['pid'],'CID_sha256':sha(cid) if cid else None,
                          'label':labels.get(cid,'parent/unknown'),'tool':row['tool']})
    instances.append({'proxy_pid':h['proxy']['pid'],'server_pid':h['server']['pid'],
                      'server_lstart':h['server']['lstart'],'tools_calls':len(calls),
                      'actual_metadata_CIDs_sha256':[sha(x) if x else None for x in ids],
                      'labels':[labels.get(x,'parent/unknown') for x in ids],
                      'native_ancestors':[{'pid':x['pid'],'lstart':x['lstart']} for x in h['native_ancestor_chain']
                                          if Path(x['comm']).name=='codex']})
    for result in rows(folder/'server-wire.jsonl'):
        req = calls.get(result.get('id'))
        if not req:continue
        params=req['params'];cid=(params.get('_meta')or{}).get('threadId')
        for block in (result.get('result')or{}).get('content',[]):
            if block.get('type')!='text':continue
            try:value=json.loads(block['text'])
            except ValueError:continue
            if params['name']=='xsm_ask' and isinstance(value,dict) and value.get('id') in questions:
                q=questions[value['id']]
                send_checks.append({'request_id_sha256':sha(value['id']),'metadata_CID_sha256':sha(cid),
                    'stored_sender_CID_sha256':sha(q['sender']['session_id']),
                    'stored_target_CID_sha256':sha(q['target']['session_id']),
                    'sender_matches_actual_meta':q['sender']['session_id']==cid,
                    'target_is_other_real_child':q['target']['session_id'] in children and q['target']['session_id']!=cid,
                    'home_matches_runtime_and_native_DB':q['sender']['home']=='/Users/jaesolshin/.codex-3',
                    'native_replies':len(q.get('replies',[]))})
            if params['name']=='xsm_files':
                args=params.get('arguments')or{}
                kind='outgoing' if args.get('outgoing') else 'incoming'
                path=ROOT/'state/file-copies'/kind/str(args.get('storage_id'))/'record.json'
                if path.is_file():
                    record=load(path)
                    file_read_checks.append({'metadata_CID_sha256':sha(cid),'kind':kind,
                        'storage_id_sha256':sha(str(args.get('storage_id'))),
                        'record_owner_CID_sha256':sha(record['owner']['session_id']),
                        'owner_matches_actual_meta':record['owner']['session_id']==cid,
                        'isError':bool((result.get('result')or{}).get('isError'))})
copies=[]
for path in (ROOT/'state/file-copies').glob('*/*/record.json'):
    record=load(path);binding=record['manifest']['binding'];q=questions.get(binding['request_id'])
    if not q:continue
    kind=path.parent.parent.name;expected=q['sender'] if kind=='outgoing' else q['target']
    owner=record['owner']
    copies.append({'kind':kind,'storage_id_sha256':sha(path.parent.name),
        'request_id_sha256':sha(binding['request_id']),'owner_CID_sha256':sha(owner['session_id']),
        'expected_owner_CID_sha256':sha(expected['session_id']),
        'owner_matches_request_endpoint':owner['session_id']==expected['session_id'],
        'home_hash_matches_actual_profile':owner['home_id']==sha('/Users/jaesolshin/.codex-3'),
        'request_body_SHA_matches':binding['body_sha256']==sha(q['body'])})
assert len(children)==2
assert all(x['sender_matches_actual_meta'] and x['target_is_other_real_child'] and x['home_matches_runtime_and_native_DB'] for x in send_checks)
assert all(x['owner_matches_actual_meta'] for x in file_read_checks)
assert all(x['owner_matches_request_endpoint'] and x['home_hash_matches_actual_profile'] and x['request_body_SHA_matches'] for x in copies)
shared=[x for x in instances if len(x['actual_metadata_CIDs_sha256'])>1]
ordered=sorted(all_calls,key=lambda x:x['at'])
alternating=[]
for call in ordered:
    if call['label'] in ('A','B') and (not alternating or alternating[-1]['label']!=call['label']):
        alternating.append(call)
cleanup=[]
for pid,start in known_processes.items():
    current=subprocess.run(['ps','-o','lstart=','-p',str(pid)],capture_output=True,text=True).stdout.strip() or None
    cleanup.append({'pid':pid,'recorded_lstart':start,'current_lstart':current,'same_owned_process_alive':bool(current and current==start)})
assert not any(x['same_owned_process_alive'] for x in cleanup)
rollouts=load(ROOT/'native-rollout-manifest.json')
summary={'label':'A23-03 actual native subagent observation; required shared-process cell missing',
    'result':'native subagents use separate xsm MCP processes in this factory harness; no simulated shared success',
    'CLI':d['actual_CLI_version'],'source':d['source'],'source_unchanged':d['source_unchanged'],
    'native_CLI_evaluation_launches':1,'native_automatic_evaluation_retries':0,'provider_or_toolhost_failures':0,
    'native_conversations':len(d['actual_native_threads']),'actual_native_subagents':len(children),
    'native_turn_started_events':sum(x['event_types'].get('task_started',0) for x in rollouts),
    'native_turn_complete_events':sum(x['event_types'].get('task_complete',0) for x in rollouts),
    'turn_completion_limit':'remaining started turns have no task_complete in bounded copied evidence; do not infer backend request counts',
    'actual_initial_registration_setup_count':len(d['registration_setup']),
    'registration_note':'actual native DB source/parent chain and real MCP Codex ancestor only; early first calls may precede setup and are not claimed as post-setup identity proof',
    'instances':instances,'shared_process_with_multiple_actual_CIDs':shared,
    'shared_MCP_ABAB':'not obtained; no process has calls from both actual child CIDs',
    'cross_process_alternating_subsequence':alternating[:4],
    'cross_process_sequence_is_not_shared_evidence':True,
    'actual_tools_calls':len(all_calls),'tools_by_name':dict(collections.Counter(x['tool'] for x in all_calls)),
    'request_sender_target_checks':send_checks,'actual_file_read_checks':file_read_checks,'copy_owner_and_body_checks':copies,
    'ownership_mismatch_observed':False,
    'natural_QA_completion':'parent explicitly reports peer reply/memo cross-confirmation incomplete; requests or file storage are not successful business completion',
    'other_home_same_ID':'not executed: actual shared-process prerequisite not obtained; no copied or fabricated native identity',
    'inherited_foreign_harness_env':'not injected as separate condition after absent shared prerequisite',
    'home_evidence':'actual CLI/MCP runtime profile plus exact CID in native state DB; no process/global HOME string used as sole signature basis',
    'proxy':'per-process exact-byte recording only; no fan-in/metadata/result/body/ACK rewrite',
    'profile_unchanged':d['profile_unchanged'],'profile_drift_changed_names':[k for k,v in d['profile_before'].items() if v!=d['profile_after'].get(k)],
    'profile_drift_writer':'unknown; no evaluator profile edit; not a profile-unchanged claim',
    'known_process_final_audit':cleanup,'private_raw_root':str(ROOT),
    'started_utc':d['started_utc'],'finished_utc':d['finished_utc'],
    'A23_03_overall_pass_claimed':False,'product_changes':False,
    'prior_handoff_UDP_results_overwritten':False}
(PUBLIC/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
(ROOT/'identity-ownership-audit.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'native_CLI_launches':1,'native_subagents':2,'MCP_instances':len(instances),
     'shared_instances':len(shared),'actual_calls':len(all_calls),'sender_checks':len(send_checks),
     'file_read_checks':len(file_read_checks),'copy_owner_checks':len(copies),
     'mismatches':0,'known_processes_alive':0,'profile_unchanged':d['profile_unchanged']}))
