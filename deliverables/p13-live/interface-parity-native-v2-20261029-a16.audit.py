"""Offline failure readback only: no CLI retry, model or product API call."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
PREFIX = 'interface-parity-native-v2-20261029-a16'
spec = importlib.util.spec_from_file_location('parity_observer', HERE / (PREFIX + '.py'))
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)
base = observer.base


def main():
    raw_path = HERE / (PREFIX + '.json'); original = raw_path.read_bytes(); raw = json.loads(original)
    root = Path(raw['raw_root']); state = root / 'state'
    body = (root / 'body.txt').read_bytes(); material = (root / 'source-v1.txt').read_bytes()
    roles, attempts = [], []
    for actor in raw['actors']:
        role = actor['role']; calls = {}; terminal = []
        for index, event in enumerate(base.events(root / (role + '.jsonl'))):
            item = event.get('item') or {}
            if event.get('type') in ('turn.completed', 'turn.failed', 'error'):
                terminal.append(event['type'])
            if item.get('type') == 'mcp_tool_call':
                calls[item['id']] = {'tool': item['tool'], 'completed': event.get('type') == 'item.completed'}
            if role == 'initiator' and event.get('type') == 'item.completed' and item.get('type') == 'command_execution':
                output = item.get('aggregated_output') or ''
                code = re.search(r'CLI_EXIT_CODE=(\d+)', output)
                if code:
                    attempts.append({'native_event': index, 'command': item['command'],
                        'outer_command_exit': item.get('exit_code'), 'actual_nested_CLI_exit': int(code[1]),
                        'argument_parser_rejected_ask': "invalid choice: 'ask'" in output,
                        'output': output, 'output_SHA': base.sha(output)})
        roles.append({'role': role, 'native_evidence': actor['native_cwd_evidence'],
            'native_CLI_version': raw['actual_cli_version'], 'original_exit_before_cleanup': actor['exit_code'],
            'calls': list(calls.values()), 'terminal_events': terminal})
    process_readbacks = []
    for actor in raw['actors']:
        for kind, pid in (('native', actor['native_cwd_evidence']['native_pid']), ('MCP', actor['mcp_pid'])):
            process = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], capture_output=True, text=True)
            process_readbacks.append({'role': actor['role'], 'kind': kind, 'pid': pid,
                'live_non_zombie_at_audit': bool(process.stdout.strip() and not process.stdout.strip().startswith('Z'))})
    manifest = base.read_json(HERE / (PREFIX + '.manifest.json'))
    raw_changes = [{'path': p, 'original_SHA': h, 'current_SHA': base.sha((root / p).read_bytes()) if (root / p).is_file() else None}
                  for p, h in manifest['files'].items() if not (root / p).is_file() or base.sha((root / p).read_bytes()) != h]
    current_manifest = {'scope': 'post-cleanup read-only evidence, original raw manifest preserved',
        'files': {str(p.relative_to(root)): base.sha(p.read_bytes()) for p in sorted(root.rglob('*'))
                  if p.is_file() and '.git' not in p.parts and '__pycache__' not in p.parts}}
    assert len(attempts) == 1 and attempts[0]['actual_nested_CLI_exit'] == 2 and not attempts[0]['argument_parser_rejected_ask']
    sender_calls = next(a['calls'] for a in roles if a['role'] == 'initiator')
    questions = list((state / 'questions').glob('*.json'))
    copies = list((state / 'file-copies').rglob('record.json'))
    assert not questions and len(copies)==1 and not any(c['tool'] == 'xsm_ask' for c in sender_calls)
    rejection=json.loads(attempts[0]['output'].split('CLI_EXIT_CODE=')[0].strip())
    assert rejection['code']=='files-unsupported-or-unknown' and rejection['body_sent'] is False
    record=base.read_json(copies[0])
    entry=record['manifest']['files'][0]
    assert entry['input_source']=='cli-os-read' and entry['sha256']==base.sha(material)
    owner=record['owner'];sender=next(a for a in raw['actors'] if a['role']=='initiator')
    actual_owner=owner=={'runtime':'codex','home_id':base.sha(sender['native_cwd_evidence']['home']),'session_id':sender['native_session_id']}
    audit = {'scope': 'one explicit CLI/MCP parity attempt; no natural/no-instruction claim',
        'result': 'partial-v2: frozen CLI parser verified, actual file capability unavailable; no paired answer/digest credit',
        'original_status': raw['status'], 'original_result_preserved': raw_path.read_bytes() == original,
        'original_result_SHA': base.sha(original), 'source': raw['source'], 'source_unchanged': raw['source_unchanged'],
        'actors': roles, 'actual_CLI_attempts': attempts, 'MCP_sender_ask_calls': 0,
        'question_records': len(questions), 'copy_records': len(copies), 'actual_reply_or_ACKs': 0, 'CLI_preflight':raw['CLI_preflight'], 'actual_rejection':rejection,
        'caller_OS_snapshot':{'manifest_id':record['manifest']['id'],'planned_request_id':record['manifest']['binding']['request_id'],
        'manifest_digest':record['manifest']['sha256'],'owner':owner,'owner_matches_actual_native_sender':actual_owner,
        'input_source':entry['input_source'],'content_SHA':entry['sha256'],'bytes':entry['size']},
        'prepared_body_SHA': base.sha(body), 'prepared_material_SHA': base.sha(material),
        'body_marker_and_file_marker_distinct': b'BODY_' in body and b'FILE_' in material and b'FILE_' not in body,
        'frozen_CLI_source_supports_ask': 'sub.add_parser("ask"' in (observer.SNAPSHOT / 'xsm/cli.py').read_text(),
        'resolved_native_shell_xsm_path': raw['CLI_preflight']['wrapper'],
        'failure_boundary': 'actual frozen CLI made caller-owned snapshot then refused unknown/unsupported peer files capability, body_sent=false; no permission/sandbox denial was returned',
        'evaluator_preparation_limit': 'original v1 omitted CLI executable binding; separately authorized v2 verified absolute wrapper/module/flags before native starts. No further condition is allowed',
        'automatic_model_retries': 0, 'native_launches': raw['native_CLI_invocations'],
        'controller_send_ACK_index_repairs': 0, 'additional_human_inputs': 0, 'seconds': raw['seconds'],
        'profile_guard_unchanged': raw['profile_guard_unchanged'],
        'profile_guard_attribution': 'unknown; no credential/profile inspection or evaluator config edit to diagnose it',
        'original_immediate_cleanup_flags': raw['owned_alive_after'], 'post_cleanup_kernel_readback': process_readbacks,
        'raw_changes_after_initial_manifest': raw_changes,
        'cleanup_limit': 'original immediate cleanup flags and later kernel readback are stored separately; no original flags rewritten',
        'no_source_ledger_plan_edits': True, 'no_native_reruns_for_audit': True}
    assert raw_path.read_bytes() == original
    observer.write(HERE / (PREFIX + '.audit.json'), audit)
    observer.write(HERE / (PREFIX + '.audit-manifest.json'), current_manifest)
    print(json.dumps({'result': audit['result'], 'actual_CLI_exit': 2, 'MCP_ask': 0,
        'questions':len(questions),'copies':len(copies),'native_retries':0,
        'owned_remaining': sum(p['live_non_zombie_at_audit'] for p in process_readbacks)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
