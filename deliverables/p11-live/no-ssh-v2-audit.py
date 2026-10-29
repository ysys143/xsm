"""Offline audit only; no native or network calls."""
import hashlib,json
from pathlib import Path
BASE=Path(__file__).resolve().parent;ROOT=Path('/private/tmp/p11-C-no-ssh-v2-local-51bqm_cj')
d=json.loads((ROOT/'result.json').read_text());p=json.loads((ROOT/'peer-raw/peer-final.json').read_text());a=json.loads((ROOT/'post-window-audit.json').read_text());n=json.loads((ROOT/'peer-raw/native/first/result.json').read_text())
events=[]
for line in (ROOT/'peer-raw/native/first/stdout.jsonl').read_text().splitlines():
 try:events.append(json.loads(line))
 except ValueError:pass
start,end=d['measurement_start_at'],d['measurement_end_at'];profile='(version 1) (allow default) (deny network-outbound (remote tcp "*:22"))'
local_ssh=[s for s in d['owned_spawns'] if s['exe']=='ssh'];peer_ssh=[s for s in p['owned_spawns'] if s['exe']=='ssh'];window_ssh=[dict(s,role=role) for role,rows in (('local',local_ssh),('peer',peer_ssh)) for s in rows if start<=s['at']<=end]
checks={
 'roundtrip_passed':d['passed'],
 'same_profile_local_peer_native':d['restriction']['profile']==p['restriction']['profile']==p['native_RootMetadata']['inherited_profile']==profile,
 'libproc_ps_baselines':d['baseline']['match_to_second'] and p['baseline']['match_to_second'],
 'local_generation_unchanged':d['baseline']['own']['generation']==d['restriction']['proc_metadata']['generation']==d['RootMetadata']['controller']['generation'],
 'peer_generation_unchanged':p['baseline']['own']['generation']==p['restriction']['proc_metadata']['generation']==p['RootMetadata_before_native']['helper']['generation'],
 'kernel_deny_both':d['preflight']['kernel']['errno']==p['preflight']['kernel']['errno']==1,
 'real_ssh_deny_both':d['preflight']['ssh_exit']==p['preflight']['ssh_exit']==255 and d['preflight']['ssh_errno_denial'] and p['preflight']['ssh_errno_denial'],
 'native_pid_kernel_deny':p['native_RootMetadata']['kernel_peer_tcp22']['errno']==1,
 'native_pid_generation_matches':p['native_RootMetadata']['own_process']['pid']==n['native_handle']['pid'] and p['native_RootMetadata']['own_process']['generation']==n['native_handle']['lstart'],
 'who_prepared_both_before_ssh_close':d['who_before_ssh_close']['session_count']==p['who_bootstrap']['session_count']==2,
 'team_private_two_nodes':all(row['member_count']==2 for row in (d['team_before'],d['team_after'],p['team_before_measurement'],p['team_after_reply'])),
 'team_endpoints_exact':all({m['endpoint_sha256'] for m in row['machines']}=={d['endpoint']['endpoint_sha256'],d['peer_bootstrap']['endpoint']['endpoint_sha256']} for row in (d['team_before'],d['team_after'],p['team_before_measurement'],p['team_after_reply'])),
 'bootstrap_ssh_closed_before_window':d['bootstrap_ssh_exit']==0 and d['all_owned_ssh_closed_at']<start,
 'no_window_ssh_spawns':not window_ssh,
 'post_window_readback_only':a['post_window_ssh_start']>end and a['post_window_ssh_exit']==0,
 'request_sha_received':d['request_sha256']==p['request_sha256']==p['native']['received_body_sha256'],
 'reply_sha_native_same':d['reply_sha256']==p['native']['answer_sha256'],
 'reply_to_original':d['reply_to']==d['request_id'],
 'engine_ids_bound':p['native']['request_engine_id_sha256']==hashlib.sha256(d['request_id'].encode()).hexdigest() and hashlib.sha256(d['reply_id'].encode()).hexdigest() in p['native']['reply_engine_ids_sha256'],
 'one_native_started_turn':sum(e.get('type')=='turn.started' for e in events)==1,
 'one_native_completed_turn':sum(e.get('type')=='turn.completed' for e in events)==1,
 'one_model_attempt':p['native_attempts']==d['native_model_count']==1,
 'actual_CID_bound':p['actual_native_CID']==n['native_conversation']==next(e['thread_id'] for e in events if e.get('type')=='thread.started'),
 'native_success':n['returncode']==0 and n['status']=='succeeded' and n['native_process_exited'],
 'no_model_tool_events':n['tool_events']==0,
 'cleanup_local_peer':d['cleanup']['local']['stopped'] and p['cleanup']['stopped'] and a['local_remaining']==a['peer_remaining']==0,
 'native_profile_metadata_unchanged':n['settings_metadata_before']==n['settings_metadata_after'],
}
assert all(checks.values()),{k:v for k,v in checks.items() if not v}
old=json.loads((BASE/'no-ssh-native-manifest.json').read_text());unchanged={name:hashlib.sha256(Path(name).read_bytes()).hexdigest()==sha for name,sha in old['files'].items()};assert all(unchanged.values())
result={'scope':'P11 C 0.12.10 one new fixture variant, post-bootstrap owned-process TCP22-denied data-plane; not SSH-free installation/global network isolation/all backends/D12 selection','passed':True,'checks':checks,'checks_passed':len(checks),'old_failure_files_unchanged':unchanged,'product_source_modified':False,'private_roots':{'local':str(ROOT),'peer':d['peer_root']},'engine_sha256':d['engine_sha256'],'profile':profile,'capability_handling':d['capability'],
 'phase_times':{'bootstrap_ssh_closed':d['all_owned_ssh_closed_at'],'measurement_start':start,'peer_received_request':p['measurement_request_seen_at'],'peer_reply_finished':p['measurement_end_at'],'measurement_end':end,'post_window_ssh_start':a['post_window_ssh_start']},'measurement_seconds':round(end-start,6),
 'SSH':{'local_pre_window_spawns':local_ssh,'peer_pre_window_spawns':peer_ssh,'data_window_spawns':window_ssh,'data_window_count':len(window_ssh),'post_window_readback_handle':a['post_window_ssh_handle'],'proof_local':d['preflight'],'proof_peer':p['preflight'],'multiplex_reuse':False,'global_firewall_changed':False,'existing_user_connections_closed':False},
 'who':{'local_before_ssh_close':d['who_before_ssh_close'],'peer_before_ssh_close':p['who_bootstrap'],'local_after':d['who_after'],'peer_after':p['who_after_reply']},'team':{'local_before':d['team_before'],'peer_before':p['team_before_measurement'],'local_after':d['team_after'],'peer_after':p['team_after_reply']},
 'request_id':d['request_id'],'reply_id':d['reply_id'],'reply_to':d['reply_to'],'request_sha256':d['request_sha256'],'reply_sha256':d['reply_sha256'],'answer':d['answer'],
 'native':{'model_count':1,'model_attempts':1,'automatic_retry_count':0,'CID':n['native_conversation'],'handle':p['native']['native_handle'],'cli_version':n['native_cli_version'],'returncode':n['returncode'],'native_elapsed_ms':n['native_elapsed_ms'],'tool_events':n['tool_events'],'turn_started_events':1,'turn_completed_events':1,'permissions':'existing C read-only, text-only native fixture; no new grants/allowedTools/auth changes'},
 'RootMetadata':{'local':d['RootMetadata'],'peer_before_native':p['RootMetadata_before_native'],'native_pre_exec':p['native_RootMetadata'],'baseline_local':d['baseline'],'baseline_peer':p['baseline'],'provenance':'SDK-layout actual libproc observations and actual kernel denial; evaluation metadata, not a native protocol RootMetadata event'},
 'cleanup':{'local':a['local_processes'],'peer':a['peer']['processes'],'local_remaining':0,'peer_remaining':0,'peer_ipc_connect_after_stop':a['peer']['ipc_connect_after_stop'],'local_ipc_connect_after_stop':d['cleanup']['local']['ipc_connect_after_stop']}}
(BASE/'no-ssh-v2-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'passed':True,'checks':len(checks),'seconds':result['measurement_seconds'],'model_count':1,'SSH_in_window':0,'remaining':0,'CID':result['native']['CID']},ensure_ascii=False))
