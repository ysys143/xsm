"""Offline final-condition readback; no native/product call or state repair."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
PREFIX = 'interface-parity-native-v3-20261029-a16'
spec = importlib.util.spec_from_file_location('last_parity_observer', HERE / (PREFIX + '.py'))
observer = importlib.util.module_from_spec(spec); spec.loader.exec_module(observer)
base = observer.base


def main():
    path = HERE / (PREFIX + '.json'); original = path.read_bytes(); raw = json.loads(original)
    root = Path(raw['raw_root']); state = root / 'state'; calls = {}; finals = {}; attempts = []
    for role in ('reviewer', 'initiator'):
        counts = {}; messages = []
        for event in base.events(root / (role + '.jsonl')):
            item = event.get('item') or {}
            if item.get('type') == 'mcp_tool_call': counts[item['id']] = item['tool']
            if event.get('type') != 'item.completed': continue
            if item.get('type') == 'agent_message': messages.append(item.get('text') or '')
            if role == 'initiator' and item.get('type') == 'command_execution':
                output = item.get('aggregated_output') or ''
                code = re.search(r'(?:CLI_EXIT_CODE=|exit_code:\s*)(\d+)', output)
                if code:
                    rejection = json.loads(output.splitlines()[0])
                    attempts.append({'actual_CLI_exit': int(code[1]), 'outer_command_exit': item.get('exit_code'),
                        'command': item['command'], 'actual_result': rejection, 'output_SHA': base.sha(output)})
        calls[role], finals[role] = list(counts.values()), messages
    readiness = raw['files_readiness']
    assert readiness['ready'] is False and readiness['elapsed'] <= 15 and readiness['first_actual_MCP_call'] is None
    assert not any(r['records'] for r in readiness['observations'])
    assert len(attempts) == 1 and attempts[0]['actual_CLI_exit'] == 2
    assert attempts[0]['actual_result']['status'] == 'refused'
    assert "only stopped sessions match 'a1'" in attempts[0]['actual_result']['reason']
    assert calls['reviewer'] == calls['initiator'] == []
    questions = list((state / 'questions').glob('*.json'))
    handoffs = list((state / 'handoffs').glob('*/*.json'))
    copies = list((state / 'file-copies').rglob('record.json'))
    assert not questions and not handoffs and not copies
    prior = json.loads((HERE / 'interface-parity-native-v2-20261029-a16.audit.json').read_text())
    body_same = base.sha((root / 'body.txt').read_bytes()) == prior['prepared_body_SHA']
    file_same = base.sha((root / 'source-v1.txt').read_bytes()) == prior['prepared_material_SHA']
    processes = []
    for actor in raw['actors']:
        for kind, pid in (('native', actor['native_cwd_evidence']['native_pid']), ('MCP', actor['mcp_pid'])):
            ps = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], capture_output=True, text=True)
            processes.append({'role': actor['role'], 'kind': kind, 'pid': pid,
                'live_non_zombie': bool(ps.stdout.strip() and not ps.stdout.strip().startswith('Z'))})
    conditions = []
    for name in ('interface-parity-native-20261029-a16', 'interface-parity-native-v2-20261029-a16', PREFIX):
        p = HERE / (name + '.json'); record = json.loads(p.read_text())
        conditions.append({'condition': name, 'result_SHA': base.sha(p.read_bytes()),
            'native_launches': record['native_CLI_invocations'], 'automatic_native_retries': record['automatic_native_retries'],
            'original_status': record['status'], 'seconds': record['seconds']})
    manifest = base.read_json(HERE / (PREFIX + '.manifest.json'))
    audit = {'result': 'partial-final-condition; no paired actual replies/digests',
        'original_result_preserved': path.read_bytes() == original, 'original_SHA': base.sha(original),
        'readiness_budget_seconds': 15, 'readiness_elapsed': readiness['elapsed'],
        'actual_first_reviewer_MCP_call': None, 'actual_capability_advertisements': 0,
        'native_registration_is_not_files_ready': True, 'readiness_check_method': readiness['method'],
        'reviewer_harness_output': finals['reviewer'],
        'reviewer_output_is_not_peer_reply': 'harness final JSON only; no MCP request/reply_to/question/handoff exists',
        'evaluator_limits': ['reviewer goal with plain missing-material output rules was answered directly instead of listening',
            'after reviewer exit was observed, driver still started initiator under plain fallback; live reviewer prerequisite was not separately guarded'],
        'actual_CLI_attempts': attempts, 'MCP_calls': calls,
        'plain_pair': 'incomplete: CLI refused stopped reviewer, MCP ask not attempted',
        'files_pair': 'not attempted: readiness false, no fabricated capability or forced inline fallback',
        'questions': 0, 'handoffs': 0, 'copies': 0, 'actual_replies_ACKs': 0,
        'CLI_preflight': raw['CLI_preflight'], 'same_body_and_material_as_v2': body_same and file_same,
        'actors': raw['actors'], 'setup_registrations': raw['setup_registrations'],
        'controller_send_ACK_index_or_capability_writes': 0, 'additional_human_inputs': 0,
        'source': raw['source'], 'source_unchanged': raw['source_unchanged'],
        'profile_guard_unchanged': raw['profile_guard_unchanged'], 'profile_writer_cause': 'unknown; not investigated',
        'conditions': conditions, 'all_authorized_conditions': len(conditions),
        'all_native_launches': sum(c['native_launches'] for c in conditions),
        'all_automatic_native_retries': sum(c['automatic_native_retries'] for c in conditions),
        'post_cleanup_processes': processes, 'seconds': raw['seconds'],
        'raw_manifest_matches': all((root / p).is_file() and base.sha((root / p).read_bytes()) == h for p, h in manifest['files'].items()),
        'further_conditions_started': 0}
    assert path.read_bytes() == original
    observer.write(HERE / (PREFIX + '.audit.json'), audit)
    print(json.dumps({k: audit[k] for k in ('result', 'readiness_elapsed', 'actual_capability_advertisements',
        'all_authorized_conditions', 'all_native_launches', 'all_automatic_native_retries')}, ensure_ascii=False))


if __name__ == '__main__': main()
