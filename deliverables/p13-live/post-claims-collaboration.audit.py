"""Offline readback of one post-claims sample; never starts a model/product call."""
import ast
import collections
import importlib.util
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
spec = importlib.util.spec_from_file_location('post_claims_runner', HERE / 'post-claims-collaboration.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def main():
    raw_path = HERE / 'post-claims-collaboration.json'
    raw_bytes = raw_path.read_bytes()
    raw = json.loads(raw_bytes)
    assert len(raw['conditions']) == 1
    condition = raw['conditions'][0]
    root = Path(condition['fixture_state']).parent
    manifest_path = HERE / 'post-qa-source-manifest.json'
    manifest = runner.read_json(manifest_path)
    snapshot = Path(manifest['snapshot'])
    source, _ = runner.source_readback(snapshot, manifest['files'])
    original_hashes = runner.read_json('/tmp/p13-post-claims-original-hashes.json')
    assert all(runner.sha((REPO / p).read_bytes()) == h for p, h in original_hashes.items())
    original_tree = ast.parse((HERE / 'natural-collaboration.py').read_text())
    copy_tree = ast.parse((HERE / 'post-claims-collaboration.py').read_text())
    goals = {n.targets[0].id: ast.literal_eval(n.value) for n in original_tree.body
             if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
             and n.targets[0].id in ('REVIEWER_GOAL', 'INITIATOR_GOAL')}
    def actor_method(tree, method):
        actor = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Actor')
        return ast.dump(next(n for n in actor.body if isinstance(n, ast.FunctionDef) and n.name == method))
    same_launch = all(actor_method(original_tree, k) == actor_method(copy_tree, k) for k in ('start', 'refresh'))
    prior_path = HERE / 'natural-collaboration-audit.json'
    prior_new = next(c for c in runner.read_json(prior_path)['conditions'] if c['condition'] == 'B05-final')
    prior_initiator = next(a for a in prior_new['actors'] if a['role'] == 'initiator')
    actors, private_evidence = [], []
    for summary in condition['actors']:
        role = summary['role']
        rows = runner.events(root / (role + '.jsonl'))
        started, completed, received, offers, acked, direct = {}, [], {}, {}, set(), []
        pending_claims, unnecessary, inboxes, host_errors = set(), [], [], []
        for index, row in enumerate(rows):
            item = row.get('item') or {}
            if row.get('type') in ('error', 'turn.failed'):
                host_errors.append({'event': index, 'type': row['type'], 'detail': row.get('error')})
            if item.get('type') != 'mcp_tool_call' or item.get('server') != 'xsm':
                continue
            key = item.get('id')
            if key not in started:
                started[key] = {'event': index, 'tool': item.get('tool')}
                if item.get('tool') == 'xsm_inbox':
                    inboxes.append(index)
                    if pending_claims:
                        unnecessary.append({'event': index,
                            'reason': 'inbox invoked while an already-read answer had an unacknowledged returned claim'})
            if row.get('type') != 'item.completed':
                continue
            tool, args = item.get('tool'), runner.args_object(item)
            completed.append({'event': index, 'tool': tool, 'error': runner.error_kind(item)})
            values = [p for p in runner.payloads(item) if isinstance(p, dict)]
            if tool in ('xsm_connect', 'xsm_ask', 'xsm_question_status'):
                for value in values:
                    for reply in value.get('replies', []):
                        received.setdefault(reply['id'], {'event': index, 'surface': tool,
                            'body_sha256': runner.sha(reply['body'])})
                    for claim in value.get('claims', []):
                        if claim['id'] in received:
                            offers[claim['token']] = {'id': claim['id'], 'event': index, 'surface': tool}
                            pending_claims.add(claim['id'])
            if tool == 'xsm_ack':
                successful = {mid for v in values for mid in v.get('acked', [])}
                for token in args.get('tokens', []):
                    offered = offers.get(token)
                    if offered and offered['id'] in successful:
                        between = [i for i in inboxes if offered['event'] < i < index]
                        direct.append({'reply_id_sha256': runner.sha(offered['id']),
                            'token_sha256': runner.sha(token), 'answer_surface': offered['surface'],
                            'answer_event': offered['event'], 'ack_event': index,
                            'intervening_inbox_calls': len(between), 'actual_ack_result': True})
                        acked.add(offered['id'])
                    pending_claims.difference_update(successful)
        counts = collections.Counter(v['tool'] for v in started.values())
        native_failed_first = bool(host_errors and not started)
        actor = {'role': role, 'native_session_id': summary['native_session_id'],
            'profile': condition[role + '_invocation']['profile'],
            'mcp_calls_started': len(started), 'mcp_calls_completed': len(completed),
            'mcp_by_tool': dict(counts), 'mcp_errors': [v for v in completed if v['error']],
            'shell_calls': summary['agent_shell_call_count'], 'tool_error_count': summary['tool_error_count'],
            'inbox_calls': counts['xsm_inbox'], 'unnecessary_inbox_calls': unnecessary,
            'direct_answer_ACKs': direct, 'native_host_failure_before_xsm_tools_call': native_failed_first,
            'native_errors': host_errors, 'native_terminal_events': [r['type'] for r in rows
                if r.get('type') in ('turn.completed', 'turn.failed')],
            'exit_code': summary['exit_code'], 'received_reply_bodies': received,
            'registration_preceded_agent_call': summary['registration_preceded_first_agent_call']}
        actors.append(actor)
        for suffix in ('.jsonl', '.stderr'):
            path = root / (role + suffix)
            private_evidence.append({'path': str(path), 'sha256': runner.sha(path.read_bytes()),
                                     'bytes': path.stat().st_size})
    state_messages = {}
    for path in (root / 'state/handoffs').glob('*/*.json'):
        row = runner.read_json(path)
        if isinstance(row, dict):
            state_messages[row['id']] = row
    initiator = next(a for a in actors if a['role'] == 'initiator')
    reviewer = next(a for a in actors if a['role'] == 'reviewer')
    reviews = []
    for mid, delivery in state_messages.items():
        message = delivery['message']
        if message.get('kind') != 'reply' or mid not in initiator['received_reply_bodies']:
            continue
        original = state_messages.get(message.get('reply_to'))
        if not original:
            continue
        request = original['message']
        question = runner.read_json(root / 'state/questions' / (message['reply_to'] + '.json')) or {}
        category = 'handshake' if question.get('purpose') == 'handshake' else runner.math_kind(request['body'])
        def endpoint_matches(endpoint, actor):
            return (endpoint.get('runtime') == 'codex' and endpoint.get('session_id') == actor['native_session_id']
                    and endpoint.get('home') == actor['profile'])
        reviews.append({'category': category, 'request_id': message['reply_to'], 'reply_id': mid,
            'request_body': request['body'], 'reply_body': message['body'],
            'request_body_sha256': runner.sha(request['body']), 'reply_body_sha256': runner.sha(message['body']),
            'request_digest': original['digest'], 'reply_digest': delivery['digest'],
            'reply_to_matches': question.get('id') == message['reply_to'],
            'actual_native_endpoint_pair_matches': endpoint_matches(message['sender'], reviewer)
                and endpoint_matches(delivery['receiver'], initiator)
                and endpoint_matches(request['sender'], initiator)
                and endpoint_matches(original['receiver'], reviewer),
            'received_actual_body': initiator['received_reply_bodies'][mid]['body_sha256'] == runner.sha(message['body']),
            'explicit_outcome': message.get('outcome'), 'canonical_state_after': delivery['state']})
    categories = collections.Counter(r['category'] for r in reviews)
    process_readbacks = []
    for role in ('reviewer', 'initiator'):
        old = next(a for a in condition['actors'] if a['role'] == role)
        for kind, pid in (('native', condition[role + '_invocation']['pid']), ('mcp', old['mcp_pid'])):
            process = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], capture_output=True, text=True)
            process_readbacks.append({'role': role, 'kind': kind, 'pid': pid,
                'live_non_zombie_at_audit': bool(process.stdout.strip() and not process.stdout.strip().startswith('Z'))})
    completed = (categories == {'proposal': 1, 'correction': 1, 'boundary': 1, 'handshake': 1}
                 and all(r['reply_to_matches'] and r['actual_native_endpoint_pair_matches']
                         and r['received_actual_body'] and r['canonical_state_after'] == 'acknowledged'
                         and r['explicit_outcome'] == 'succeeded' for r in reviews)
                 and len(initiator['direct_answer_ACKs']) == 4
                 and all(a['intervening_inbox_calls'] == 0 for a in initiator['direct_answer_ACKs'])
                 and all(a['exit_code'] == 0 and not a['mcp_errors'] for a in actors))
    audit = {'scope': 'one current post-claims natural sample only; not whole J03/J04 or old-product speed superiority',
        'business_goal': 'passed-this-sample' if completed else 'not-verified',
        'raw_result_sha256': runner.sha(raw_bytes), 'raw_result_preserved': raw_path.read_bytes() == raw_bytes,
        'original_two_condition_artifacts_preserved': True, 'original_artifact_hashes': original_hashes,
        'native_processes_started': len(condition['actors']), 'original_launch_and_registration_code_unchanged': same_launch,
        'native_reruns': 0, 'baseline_executed': False, 'goals_unchanged': raw['goals'] == {
            'reviewer': goals['REVIEWER_GOAL'], 'initiator': goals['INITIATOR_GOAL']},
        'invocation_conditions': 'original workspace-write/approval_policy=never/factory ignore-user-config retained; no added permission/model/tool override',
        'source_manifest': str(manifest_path.relative_to(REPO)), 'source_manifest_sha256': runner.sha(manifest_path.read_bytes()),
        'runner_sha256': runner.sha((HERE / 'post-claims-collaboration.py').read_bytes()),
        'snapshot_source_readback': source, 'primary_paths': len(manifest['stable_product_paths']),
        'profile_unchanged': condition['profile_settings_and_auth_metadata_unchanged'],
        'runtime_source_unchanged': condition['source_unchanged'], 'actors': actors, 'reviews': reviews,
        'actual_math_reviews': sum(categories[k] for k in ('proposal', 'correction', 'boundary')),
        'actual_handshakes': categories['handshake'], 'first_actual_reply_seconds': condition['first_actual_reply_seconds'],
        'first_reply_scope': 'initiator start to first observed actual returned body, includes handshake; controller polling granularity, not wire latency',
        'condition_seconds': condition['duration_seconds'], 'setup_initial_actual_native_registrations': condition['setup_registry_calls'],
        'bootstrap_protocol_calls': condition['bootstrap_protocol_calls'],
        'controller_message_calls': 0, 'controller_ACK_calls': 0, 'controller_index_repairs': 0,
        'additional_human_prompts_clicks_commands_approvals': 0,
        'agent_mcp_calls': sum(a['mcp_calls_started'] for a in actors),
        'agent_shell_calls': sum(a['shell_calls'] for a in actors),
        'total_agent_tool_calls': sum(a['mcp_calls_started'] + a['shell_calls'] for a in actors),
        'initiator_direct_answer_ACKs': len(initiator['direct_answer_ACKs']),
        'initiator_unnecessary_inbox_calls': len(initiator['unnecessary_inbox_calls']),
        'prior_new_condition_reference': {'path': 'deliverables/p13-live/natural-collaboration-audit.json',
            'sha256': runner.sha(prior_path.read_bytes()),
            'initiator_mcp_calls': prior_initiator['mcp_calls_started'],
            'initiator_inbox_calls': prior_initiator['mcp_by_tool'].get('xsm_inbox', 0),
            'all_actor_mcp_calls': sum(a['mcp_calls_started'] for a in prior_new['actors']),
            'scope': 'same business goals, previous new condition; observational call counts, not a matched speed benchmark'},
        'private_raw_evidence': private_evidence, 'cleanup_readback': process_readbacks}
    assert raw_path.read_bytes() == raw_bytes
    target = HERE / 'post-claims-collaboration.audit.json'
    target.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: audit[k] for k in ('business_goal', 'actual_math_reviews', 'actual_handshakes',
        'agent_mcp_calls', 'agent_shell_calls', 'initiator_direct_answer_ACKs', 'initiator_unnecessary_inbox_calls')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
