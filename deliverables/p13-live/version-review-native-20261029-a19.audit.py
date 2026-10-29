"""Read-only body/owner/version/ACK audit. No product API or native rerun."""
import base64
import collections
import importlib.util
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
PREFIX = 'version-review-native-20261029-a19'
spec = importlib.util.spec_from_file_location('version_observer', HERE / (PREFIX + '.py'))
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)
base = observer.base


def main():
    raw_path = HERE / (PREFIX + '.json'); raw_bytes = raw_path.read_bytes(); raw = json.loads(raw_bytes)
    root = Path(raw['raw_root']); state = root / 'state'
    actors = {a['role']: a for a in raw['actors']}
    sources = [(root / 'source-v1.txt').read_bytes(), (root / 'source-final.txt').read_bytes()]
    markers = [re.search(r'^evidence_marker:\s*(\S+)\s*$', b.decode(), re.M).group(1) for b in sources]
    incoming = {p.parent.name: (p, base.read_json(p)) for p in (state / 'file-copies/incoming').glob('*/record.json')}
    outgoing = {p.parent.name: (p, base.read_json(p)) for p in (state / 'file-copies/outgoing').glob('*/record.json')}
    original_messages = {r['id']: r for p in (state / 'handoffs').glob('*/*.json') if isinstance((r := base.read_json(p)), dict)}
    calls, shell, reads, summaries = {}, {}, [], []
    for role, actor in actors.items():
        completed = []; commands = []
        for index, event in enumerate(base.events(root / (role + '.jsonl'))):
            item = event.get('item') or {}
            if event.get('type') != 'item.completed': continue
            if item.get('type') == 'command_execution':
                commands.append({'command': item.get('command') or '', 'output': item.get('aggregated_output') or '',
                                 'exit_code': item.get('exit_code'), 'event': index})
            if item.get('type') != 'mcp_tool_call': continue
            args = base.args_object(item)
            values = [d for d in base.payloads(item) if isinstance(d, dict)]
            completed.append({'tool': item['tool'], 'arguments': args, 'values': values,
                              'event': index, 'error': base.error_kind(item)})
            if role == 'reviewer' and item['tool'] == 'xsm_files' and args.get('entry_id') and not args.get('outgoing', False):
                content = next((d for d in values if d.get('entry_id') == args['entry_id'] and d.get('storage_id') == args['storage_id']), None)
                if not content: continue
                data = base64.b64decode(content['content']) if content['encoding'] == 'base64' else content['content'].encode()
                path, record = incoming[args['storage_id']]; manifest = record['manifest']
                entry = next(e for e in manifest['files'] if e['id'] == args['entry_id'])
                blob = (path.parent / record['storage'][entry['id']]).read_bytes()
                owner = record['owner']; expected_home = base.sha(actor['native_cwd_evidence']['home'])
                reads.append({'event': index, 'storage_id': args['storage_id'], 'entry_id': entry['id'],
                    'manifest_id': manifest['id'], 'version': manifest['version'], 'entry_bytes': len(data),
                    'entry_SHA': entry['sha256'], 'actual_content_SHA': base.sha(data),
                    'returned_content_matches_blob': data == blob, 'SHA_matches_entry': base.sha(data) == entry['sha256'],
                    'actual_reviewer_owner': owner == {'runtime': 'codex', 'home_id': expected_home,
                                                     'session_id': actor['native_session_id']},
                    'owner': owner, 'marker_SHA': base.sha(re.search(r'^evidence_marker:\s*(\S+)\s*$', data.decode(), re.M).group(1))})
        calls[role], shell[role] = completed, commands
        summaries.append({'role': role, 'native_evidence': actor['native_cwd_evidence'],
            'observed_native_CLI_version': raw['actual_cli_version'],
            'exit_code': actor['exit_code'], 'MCP_calls': len(completed),
            'MCP_by_tool': dict(collections.Counter(c['tool'] for c in completed)),
            'MCP_errors': [{'tool': c['tool'], 'event': c['event'], 'error': c['error']} for c in completed if c['error']],
            'shell_calls': len(commands), 'shell_nonzero': [{'event': c['event'], 'exit_code': c['exit_code']}
                for c in commands if c['exit_code'] not in (None, 0)]})
    versions = []
    for manifest_id, (path, record) in sorted(outgoing.items(), key=lambda pair: pair[1][1]['manifest']['version']):
        m = record['manifest']; version = m['version']; request = original_messages[m['binding']['request_id']]
        matches = [c for c in calls['initiator'] if c['tool'] == 'xsm_ask'
                   and any(v.get('id') == request['id'] for v in c['values'])]
        assert len(matches) == 1
        call = matches[0]; items = call['arguments']['attachments']; assert len(items) == 1
        inline = items[0]['text'].encode() if 'text' in items[0] else base64.b64decode(items[0]['base64'])
        entry = m['files'][0]
        version_reads = [r for r in reads if r['manifest_id'] == manifest_id]
        replies = [r for r in original_messages.values() if r['message'].get('reply_to') == request['id']
                   and r['message'].get('kind') == 'reply']
        versions.append({'version': version, 'request_id': request['id'], 'manifest_id': manifest_id,
            'previous_manifest': m['previous'], 'manifest_digest': m['sha256'], 'owner': record['owner'],
            'source_bytes': len(sources[version - 1]), 'content_SHA': entry['sha256'], 'marker_SHA': base.sha(markers[version - 1]),
            'caller_inline_actual_source_match': inline == sources[version - 1], 'server_source_paths': record['sources'],
            'input_source': entry['input_source'], 'binding_body_SHA_matches': m['binding']['body_sha256'] == base.sha(request['message']['body']),
            'sender_actual_read_observed': any(base64.b64encode(sources[version - 1]).decode() in c['output']
                or sources[version - 1].decode() in c['output'] for c in shell['initiator']),
            'received_storage_ids': sorted({r['storage_id'] for r in version_reads}),
            'actual_read_events': [r['event'] for r in version_reads],
            'request_native_pair_matches': request['message']['sender']['session_id'] == actors['initiator']['native_session_id']
                and request['receiver']['session_id'] == actors['reviewer']['native_session_id'],
            'request_canonical_state': request['state'], 'request_digest': request['digest'],
            'replies': [{'reply_id': r['id'], 'reply_to': r['message']['reply_to'], 'outcome': r['message'].get('outcome'),
                'body': r['message']['body'], 'body_SHA': base.sha(r['message']['body']),
                'digest': r['digest'], 'canonical_state': r['state'],
                'actual_native_pair_matches': r['message']['sender']['session_id'] == actors['reviewer']['native_session_id']
                    and r['receiver']['session_id'] == actors['initiator']['native_session_id']} for r in replies]})
    tokens_in_bodies = [r['id'] for r in original_messages.values() if any(t in r['message']['body'] for t in markers)]
    first = [r for r in reads if r['version'] == 1]; second = [r for r in reads if r['version'] == 2]
    reread = bool(first and second and any(r['event'] > second[0]['event'] for r in first))
    unchanged = (len(first) >= 2 and len({(r['storage_id'], r['entry_id'], r['actual_content_SHA'], r['marker_SHA'], r['entry_bytes'])
                                        for r in first}) == 1)
    passed = (len(versions) == 2 and [v['version'] for v in versions] == [1, 2]
        and versions[1]['previous_manifest'] == versions[0]['manifest_id'] and versions[0]['request_id'] != versions[1]['request_id']
        and markers[0] != markers[1] and not tokens_in_bodies and reread and unchanged
        and all(r['actual_reviewer_owner'] and r['returned_content_matches_blob'] and r['SHA_matches_entry'] for r in reads)
        and all(v['caller_inline_actual_source_match'] and v['sender_actual_read_observed'] and v['binding_body_SHA_matches']
            and v['input_source'] == 'caller-inline' and not v['server_source_paths'] and v['request_native_pair_matches']
            and v['request_canonical_state'] == 'acknowledged'
            and any(r['outcome'] == 'succeeded' for r in v['replies'])
            and all(r['canonical_state'] == 'acknowledged' and r['actual_native_pair_matches'] for r in v['replies']) for v in versions)
        and all(a['exit_code'] == 0 and not a['MCP_errors'] for a in summaries))
    manifest = base.read_json(HERE / (PREFIX + '.manifest.json'))
    audit = {'scope': 'A19-06 one actual two-version file-review cell; not all A19/P06',
        'result': 'passed-this-two-version-native-sample' if passed else 'not-verified',
        'original_result_preserved': raw_path.read_bytes() == raw_bytes, 'original_result_SHA': base.sha(raw_bytes),
        'source': raw['source'], 'source_unchanged': raw['source_unchanged'], 'seconds': raw['seconds'],
        'source_manifest': 'deliverables/p13-live/final-source-manifest.json',
        'native_launches': raw['native_CLI_invocations'], 'automatic_model_retries': raw['automatic_native_retries'],
        'actors': summaries, 'versions': versions, 'actual_incoming_entry_reads': reads,
        'v2_read_then_same_v1_reread': reread, 'v1_bytes_digest_marker_unchanged': unchanged,
        'raw_marker_in_message_bodies': tokens_in_bodies,
        'setup_actual_native_registrations': raw['setup_registrations'], 'controller_send_ACK_index_repairs': 0,
        'additional_human_inputs': 0, 'profile_guard_unchanged': raw['profile_guard_unchanged'],
        'profile_limit': 'equality guard differs; config/auth metadata writer and cause not established; no evaluator profile edit commanded',
        'owned_alive_after': raw['owned_alive_after'], 'raw_root': str(root),
        'raw_manifest_hashes_match': all(base.sha((root / p).read_bytes()) == h for p, h in manifest['files'].items()),
        'native_reruns_for_audit': 0}
    audit['agent_MCP_calls'] = sum(a['MCP_calls'] for a in summaries)
    audit['agent_shell_calls'] = sum(a['shell_calls'] for a in summaries)
    audit['total_agent_tool_calls'] = audit['agent_MCP_calls'] + audit['agent_shell_calls']
    assert raw_path.read_bytes() == raw_bytes
    observer.write(HERE / (PREFIX + '.audit.json'), audit)
    print(json.dumps({k: audit[k] for k in ('result', 'native_launches', 'v2_read_then_same_v1_reread',
        'v1_bytes_digest_marker_unchanged', 'raw_marker_in_message_bodies')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
