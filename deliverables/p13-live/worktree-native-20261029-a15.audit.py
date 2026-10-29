"""Offline correction of the worktree sample collector, no native re-execution."""
import collections
import importlib.util
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PREFIX = 'worktree-native-20261029-a15'
spec = importlib.util.spec_from_file_location('worktree_observer', HERE / (PREFIX + '.py'))
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)
base = observer.base


def main():
    path = HERE / (PREFIX + '.json')
    original = path.read_bytes(); raw = json.loads(original)
    root = Path(raw['raw_root']); state = root / 'state'
    actors = {a['role']: a for a in raw['actors']}
    calls, shell = {}, []
    counts = {}
    for role, actor in actors.items():
        unique = {}
        for event in base.events(root / (role + '.jsonl')):
            item = event.get('item') or {}
            if event.get('type') != 'item.completed':
                continue
            if item.get('type') == 'mcp_tool_call':
                unique[item['id']] = item
            if item.get('type') == 'command_execution':
                command = item.get('command') or ''
                shell.append({'role': role, 'command': command, 'exit_code': item.get('exit_code'),
                              'output_sha256': base.sha(item.get('aggregated_output') or '')})
        calls[role] = list(unique.values())
        counts[role] = dict(collections.Counter(i['tool'] for i in calls[role]))
    questions = {p.stem: base.read_json(p) for p in (state / 'questions').glob('*.json')}
    originals = {r['id']: r for p in (state / 'handoffs').glob('*/*.json') if isinstance((r := base.read_json(p)), dict)}
    pairs = []
    for item in calls['initiator']:
        if item['tool'] != 'xsm_ask':
            continue
        answer = next((d for d in base.payloads(item) if isinstance(d, dict) and d.get('replies')), None)
        assert answer is not None, 'actual answer body missing'
        question = questions[answer['id']]
        request = originals[answer['id']]
        assert question['purpose'] == 'question'
        actual_reply = answer['replies'][0]
        reply = originals[actual_reply['id']]
        message = reply['message']
        index = len(pairs)
        # Interpret the actual question/reply context, not a substring's first
        # occurrence. The first asks proposal+boundary; second previews round3.
        phase = ('proposal-with-early-boundary', 'correction-with-boundary-preview', 'independent-boundary')[index]
        pairs.append({'phase': phase, 'request_id': answer['id'], 'reply_id': reply['id'],
            'reply_to': message['reply_to'], 'request_body': question['body'], 'reply_body': message['body'],
            'request_body_sha256': base.sha(question['body']), 'reply_body_sha256': base.sha(message['body']),
            'request_digest': request['digest'], 'reply_digest': reply['digest'],
            'actual_body_matches_response': actual_reply['body'] == message['body'],
            'exact_native_pair': request['message']['sender']['session_id'] == actors['initiator']['native_session_id']
                and request['receiver']['session_id'] == actors['reviewer']['native_session_id']
                and message['sender']['session_id'] == actors['reviewer']['native_session_id']
                and reply['receiver']['session_id'] == actors['initiator']['native_session_id'],
            'automatic_scope': request['message']['scope'],
            'reply_canonical_state': reply['state'], 'outcome': message['outcome']})
    assert len(pairs) == 3
    assert '1차 제안' in pairs[0]['request_body'] and '2+2=5' in pairs[0]['request_body']
    assert '수정 제안은 2+2=4' in pairs[1]['request_body'] and '다음 3차' in pairs[1]['request_body']
    assert '3차 별도 경계' in pairs[2]['request_body'] and '0+0=0' in pairs[2]['reply_body']
    forbidden = {'xsm_link', 'xsm_join', 'xsm_reach', 'xsm_publish', 'xsm_grant', 'xsm_approve', 'xsm_decide', 'xsm_setup'}
    forbidden_calls = [i['tool'] for items in calls.values() for i in items if i['tool'] in forbidden]
    forbidden_shell = [c['command'] for c in shell if re.search(r'\bxsm\s+(?:link|join|reach|publish|grant|approve|setup)\b', c['command'])]
    config = base.read_json(state / 'config.json') or {}
    policy_snapshot = base.read_json(state / 'config.last-valid.json') or {}
    effective = policy_snapshot.get('config') or {}
    scopes = {key: {'config': config.get(key), 'effective': effective.get(key)}
              for key in ('links', 'reaches', 'projects', 'scopes')}
    no_extra_scope = all(not d['config'] and not d['effective'] for d in scopes.values())
    publications = list((state / 'directory-publications').glob('*.json'))
    collaborations = list((state / 'collaborations').glob('*.json'))
    formal_handshakes = sum(q.get('purpose') == 'handshake' for q in questions.values())
    native_metadata = {}
    for role, actor in actors.items():
        sid = actor['native_session_id']; home = Path(actor['native_cwd_evidence']['home'])
        paths = list((home / 'sessions/2026/10/29').glob('*' + sid + '*.jsonl'))
        doc = None
        if len(paths) == 1:
            with paths[0].open() as stream:
                row = json.loads(stream.readline(131072))
            if row.get('type') == 'session_meta' and row['payload'].get('id') == sid:
                doc = {k: row['payload'].get(k) for k in ('id', 'cwd', 'cli_version', 'source', 'model_provider')}
        native_metadata[role] = {'bounded_session_meta': doc, 'kernel': actor['native_cwd_evidence']}
    same_common = raw['git_evidence'][0]['common_dir'] == raw['git_evidence'][1]['common_dir']
    different_cwd = raw['git_evidence'][0]['cwd'] != raw['git_evidence'][1]['cwd']
    actual_cwd_matches = all(d['bounded_session_meta'] and d['bounded_session_meta']['cwd'] == d['kernel']['registered_cwd']
        == d['kernel']['kernel_process_cwd'] and d['kernel']['native_generation_alive'] for d in native_metadata.values())
    exact_pairs = all(p['actual_body_matches_response'] and p['exact_native_pair'] and p['reply_to'] == p['request_id']
        and p['reply_canonical_state'] == 'acknowledged' and p['outcome'] == 'succeeded' for p in pairs)
    passed = (same_common and different_cwd and actual_cwd_matches and exact_pairs and not forbidden_calls
        and not forbidden_shell and no_extra_scope and not publications and not collaborations
        and all(a['exit_code'] == 0 and a['tool_error_count'] == 0 for a in actors.values()))
    protected = base.read_json('/tmp/p13-worktree-protected.json')
    protected_check = {p: base.sha((REPO / p).read_bytes()) == h for p, h in protected.items()}
    manifest = base.read_json(HERE / (PREFIX + '.manifest.json'))
    raw_hashes_ok = all(base.sha((root / p).read_bytes()) == h for p, h in manifest['files'].items())
    audit = {'scope': 'A15-01 same-repo/linked-worktree automatic native roundtrip only; not A24/J09 handshake proof',
        'A15_01_functional_sample': 'passed' if passed else 'not-verified',
        'original_automatic_status': raw['status'], 'original_result_sha256': base.sha(original),
        'original_result_preserved': path.read_bytes() == original,
        'collector_correction': 'all three were classified boundary: first combines proposal+boundary; correction quotes next boundary; actual request/reply bodies distinguish rounds',
        'native_reexecutions': 0, 'controller_product_repairs': 0, 'native_CLI_invocations': raw['native_CLI_invocations'],
        'native_metadata': native_metadata, 'git_evidence': raw['git_evidence'], 'same_git_common': same_common,
        'different_actual_native_cwd': different_cwd and actual_cwd_matches,
        'pairs': pairs, 'actual_correlated_math_request_reply_pairs': 3,
        'formal_handshakes': formal_handshakes,
        'MCP_discover_calls': sum(c.get('xsm_discover', 0) for c in counts.values()),
        'MCP_connect_calls': sum(c.get('xsm_connect', 0) for c in counts.values()),
        'native_CLI_list_calls': sum(bool(re.search(r'\bxsm\s+list\b', c['command'])) for c in shell),
        'discovery_scope': 'initiator natural a1 name resolution; reviewer actual product CLI list. No explicit candidate-discover/connect API trace',
        'permission_API_calls': forbidden_calls, 'permission_shell_calls': forbidden_shell,
        'scope_state': scopes, 'publications': len(publications), 'selected_collaboration_records': len(collaborations),
        'private_config_file_exists': (state / 'config.json').exists(),
        'policy_snapshot_source_exists': policy_snapshot.get('source_exists'),
        'initial_actual_native_registrations': raw['setup_registrations'], 'additional_human_inputs': 0,
        'controller_send_ACK_index_corrections': 0, 'agent_MCP_counts': counts,
        'agent_MCP_calls': sum(sum(c.values()) for c in counts.values()),
        'agent_shell_calls': len(shell), 'total_agent_tool_calls': sum(sum(c.values()) for c in counts.values()) + len(shell),
        'shell_nonzero': [c for c in shell if c['exit_code'] not in (None, 0)],
        'tool_errors': sum(a['tool_error_count'] for a in actors.values()),
        'profile_guard_unchanged': raw['profile_guard_unchanged'],
        'profile_guard_limit': 'guard differs; writer/file/cause not established. Equality guard only, per-file before values not persisted; no evaluator profile-write command observed',
        'source_unchanged': raw['source_unchanged'], 'raw_manifest_hashes_match': raw_hashes_ok,
        'old_QA_and_closed_audit_hashes': protected_check,
        'seconds': raw['seconds'], 'owned_alive_after': raw['owned_alive_after'],
        'separate_clone_native_negative_test': 'not run; existing fixture counterexample remains separate'}
    assert path.read_bytes() == original
    observer.write(HERE / (PREFIX + '.audit.json'), audit)
    print(json.dumps({k: audit[k] for k in ('A15_01_functional_sample', 'actual_correlated_math_request_reply_pairs',
        'formal_handshakes', 'same_git_common', 'different_actual_native_cwd', 'agent_MCP_calls', 'agent_shell_calls',
        'profile_guard_unchanged')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
