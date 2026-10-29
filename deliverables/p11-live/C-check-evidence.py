"""Offline checks of this C fixture evidence; never starts engines or models."""
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

BASE = Path(__file__).resolve().parent


def check_result(data):
    assert data['scope_status'] == 'passed_controlled_two_machine_fixture'
    assert data['native_successes'] == 6
    conversations = set()
    for run in data['runs']:
        assert run['passed'] and run['native_model_calls'] == 3
        endpoints = {run['local_endpoint']['endpoint_sha256'], run['peer_endpoint']['endpoint_sha256']}
        assert len(endpoints) == 2
        assert run['membership_before']['only_controlled_endpoints']
        for readback in [run['membership_before']] + [p['readback'] for p in run['phases']]:
            for role in ('local', 'peer'):
                assert readback[role]['member_count'] == 2
                assert {m['endpoint_sha256'] for m in readback[role]['machines']} == endpoints
        assert [p['phase'] for p in run['phases']] == ['first', 'followup', 'reconnect-cached-readback', 'after-reconnect']
        for phase in run['phases']:
            if phase['phase'] == 'reconnect-cached-readback':
                assert phase['model_rerun'] is False
                assert all(phase[k] for k in ('original_reply_id_unchanged', 'original_body_unchanged', 'endpoint_unchanged'))
                assert phase['reply_engine_id_sha256'] == run['phases'][1]['reply_engine_id_sha256']
                continue
            native = phase['native']
            assert native['actual_native_call'] is True and native['native_process_exited']
            assert native['native_handle']['alive_after_start'] and native['tool_events'] == 0
            assert native['native_cli_version'] == 'codex-cli 0.163.0'
            assert native['request_engine_id_sha256'] == phase['request_engine_id_sha256']
            assert phase['reply_engine_id_sha256'] in native['reply_engine_ids_sha256']
            answer = phase['actual_json_answer']
            assert answer['request_id'] == data['task_marker'] and answer['phase'] == phase['phase']
            assert answer['claim_valid'] is False and answer['corrected_sum'] == 4 and answer['counterexample']
            assert hashlib.sha256(json.dumps(answer, ensure_ascii=False).encode()).hexdigest() == native['answer_sha256']
            conversations.add(native['native_conversation_sha256'])
        for role in ('local', 'peer'):
            cleanup = run['cleanup'][role]
            assert cleanup['stopped'] and cleanup['ipc_connect_after_stop'] != 0
            assert cleanup['private_state_removed'] and cleanup['engine_copy_removed']
            assert all(h['exit_code'] in (0, -15) for h in cleanup['handles'])
        assert run['cleanup']['peer']['ssh_exit_code'] == 0
    assert len(conversations) == 6
    assert data['final_process_verification']['peer']['all_owned_processes_gone']
    for role in ('local', 'peer'):
        for root in data['final_process_verification'][role]['roots']:
            assert not root['state_exists'] and not root['home_exists'] and not root['engine_exists']
            assert not root.get('extra_processes', root.get('extra_owned_processes'))


def main():
    data = json.loads((BASE / 'C-native-roundtrip-20261029.json').read_text())
    check_result(data)
    manifest = json.loads((BASE / 'C-native-evidence-manifest-20261029.json').read_text())
    for row in manifest['files']:
        content = Path(row['local_path']).read_bytes()
        assert len(content) == row['bytes'] and hashlib.sha256(content).hexdigest() == row['sha256']
    for row in data['native_evidence']:
        raw = json.loads(Path(row['local_result_path']).read_text())
        assert raw['status'] == 'succeeded' and raw['returncode'] == 0 and raw['actual_agent_task']
        assert hashlib.sha256(raw['native_conversation'].encode()).hexdigest() == row['native_conversation_sha256']
        assert raw['actual_json_answer']['request_id'] == data['task_marker']
        request = Path(row['local_result_path']).with_name('request.txt').read_bytes()
        assert hashlib.sha256(request).hexdigest() == raw['digest'] == row['received_body_sha256']
        schema = json.loads(Path(row['local_result_path']).with_name('schema.json').read_text())
        assert all('const' not in p and 'enum' not in p for p in schema['properties'].values())
    # The only public body is the requested arithmetic marker/task/answer.
    for path in BASE.glob('C-*'):
        if path.suffix in ('.py', '.json', '.md'):
            assert not re.search(rb'(?:rn1-|tincan1)[A-Za-z0-9_-]{40,}', path.read_bytes())
    mutations = []
    if '--self-test' in sys.argv:
        for label in ('synthetic-native', 'deleted-phase', 'model-reran-cache'):
            changed = copy.deepcopy(data)
            if label == 'synthetic-native':
                changed['runs'][0]['phases'][0]['native']['actual_native_call'] = False
            elif label == 'deleted-phase':
                changed['runs'][0]['phases'].pop()
            else:
                changed['runs'][0]['phases'][2]['model_rerun'] = True
            try:
                check_result(changed)
            except AssertionError:
                mutations.append({'case': label, 'rejected': True})
            else:
                raise AssertionError('mutation unexpectedly passed: ' + label)
    print(json.dumps({'passed': True, 'scope': 'offline recorded C fixture evidence only',
                      'hashed_files': len(manifest['files']), 'native_result_files': len(data['native_evidence']),
                      'native_model_calls_this_check': 0, 'mutations': mutations}, indent=2))


if __name__ == '__main__':
    main()
