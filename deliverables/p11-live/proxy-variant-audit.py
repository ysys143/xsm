"""Offline integrity/correlation checks of the actual explicit-allow variant."""
import collections
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
location = json.loads((BASE/'proxy-variant-location-20261029.json').read_text())
ROOT = Path(location['local'])
raw = json.loads((ROOT/'proxy-variant-result.json').read_text())
native_path = ROOT/'peer-evidence/native/first/result.json'
native = json.loads(native_path.read_text())
phase = raw['phases'][0]
sha = lambda data: hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()

assert raw['passed'] and raw['counts_final']['native_model_attempts'] == 1
assert raw['native_model_calls'] == 1 and native['returncode'] == 0
assert native['status'] == 'succeeded' and native['tool_events'] == 0
assert native['native_process_exited'] and native['native_handle']['alive_after_start']
assert phase['peer_links'] == ['relay', 'relay']
assert phase['correlated_reply_and_SHA_confirmed']
assert native['digest'] == phase['request_body_sha256'] == raw['native']['received_body_sha256']
assert sha(native_path.with_name('request.txt').read_bytes()) == phase['request_body_sha256']
assert sha(json.dumps(native['actual_json_answer'], ensure_ascii=False)) == phase['answer_body_sha256']
assert phase['reply_engine_id_sha256'] in raw['native']['reply_engine_ids_sha256']
assert phase['request_engine_id_sha256'] == raw['native']['request_engine_id_sha256']
assert sha(native['native_conversation']) == raw['native']['native_conversation_sha256']
events = [json.loads(x) for x in native_path.with_name('stdout.jsonl').read_text().splitlines()]
assert sum(x.get('type') == 'thread.started' for x in events) == 1
assert sum(x.get('type') == 'turn.completed' for x in events) == 1

proxy_stats = {}
for role in ('local', 'peer'):
    pre = raw[role+'_preflight']
    assert pre['passed'] and pre['direct_child']['exit_code'] == 0
    assert all(x.get('errno') == 1 for x in pre['direct_child']['output'].values())
    assert pre['direct_UDP_no_datagram'] and pre['direct_TCP_no_connection']
    assert pre['external_TCP_child']['exit_code'] == 0 and pre['external_TCP_child']['output']['errno'] == 1
    assert pre['proxy_connection_child']['exit_code'] == 0 and pre['proxy_connection_child']['output']['proxy_connected']
    assert pre['TLS_tunnel']['exit_code'] == 0
    assert pre['TLS_tunnel']['result']['connect'] == '200' and pre['TLS_tunnel']['result']['tls_verify'] == '0'
    assert not pre['TLS_tunnel']['certificate_verification_disabled']
    records = raw['CONNECT_after_native'][role]['CONNECT_records']
    groups = collections.defaultdict(lambda: {'count': 0, 'up': 0, 'down': 0})
    for entry in records:
        key = (entry.get('phase'), entry.get('host'), entry.get('status'))
        value = groups[key]
        value['count'] += 1
        value['up'] += entry.get('client_to_upstream', 0)
        value['down'] += entry.get('upstream_to_client', 0)
    def relay_totals(snapshot):
        return [sum(e.get(field, 0) for e in snapshot['CONNECT_records']
                    if e.get('phase') == 'engine' and str(e.get('host', '')).startswith('relay-'))
                for field in ('client_to_upstream', 'upstream_to_client')]
    before = relay_totals(raw['CONNECT_before_native'][role])
    after = relay_totals(raw['CONNECT_after_native'][role])
    delta = [a-b for a,b in zip(after,before)]
    assert all(x > 0 for x in delta)
    accepted = [x for x in records if x.get('phase') == 'engine' and x.get('method') == 'CONNECT'
                and x.get('client_to_upstream', 0) > 0 and x.get('upstream_to_client', 0) > 0]
    assert accepted
    proxy_stats[role] = {'port': raw[role+'_proxy_preflight']['port'],
        'snapshot_scope': 'immediately after actual native reply, before final cleanup',
        'CONNECT_requests': sum(x.get('method') == 'CONNECT' for x in records),
        'accepted_engine_tunnels_with_bidirectional_bytes': len(accepted),
        'policy_rejected_CONNECT': sum(x.get('status') == 'destination-outside-approved-engine-services' for x in records),
        'unsupported_non_CONNECT_requests': sum(x.get('status') == 'not-CONNECT' for x in records),
        'native_window_relay_bytes_up_down': delta,
        'groups': [{'phase': k[0], 'host': k[1], 'status': k[2], **value} for k,value in groups.items()]}
    cleanup = raw['cleanup']['local_engine'] if role == 'local' else raw['cleanup']['peer']['engine']
    assert cleanup['stopped'] and cleanup['ipc_connect_after_stop'] == 61
    assert cleanup['private_state_removed'] and cleanup['engine_copy_removed']
    for handle in cleanup['handles']:
        assert handle['egress_profile'] == pre['profile'] and handle['exit_code'] in (0, -15)
        assert handle['HTTP_PROXY'] == handle['HTTPS_PROXY'] == 'http://127.0.0.1:'+str(proxy_stats[role]['port'])
assert raw['cleanup']['local_proxy']['connect_after_stop'] == 61
assert raw['cleanup']['peer']['proxy']['connect_after_stop'] == 61
assert raw['cleanup']['peer']['ssh_exit_code'] == 0
audit = json.loads((ROOT/'final-process-audit.json').read_text())
assert not audit['local_extra_owned_processes'] and not audit['peer_extra_owned_processes']
peer = json.loads((ROOT/'peer-evidence-manifest.json').read_text())
for row in peer['files']:
    assert sha(Path(row['local_copy']).read_bytes()) == row['sha256']

summary = {'scope_status': 'proven: owned engine CONNECT-proxy restriction only',
    'private_roots': location, 'engine_version': '0.12.10', 'engine_sha256': raw['binary_sha256'],
    'profile_kind': 'explicit-allow: deny UDP/all TCP, allow exact localhost proxy TCP port',
    'preflights': {role: raw[role+'_preflight'] for role in ('local','peer')},
    'proxy_stats': proxy_stats, 'roundtrip_ms': phase['roundtrip_ms'],
    'native_CLI_ms': native['native_elapsed_ms'], 'native_CLI_version': native['native_cli_version'],
    'native_PID_start': {k:v for k,v in native['native_handle'].items() if k in ('pid','lstart','alive_after_start')},
    'native_CID_sha256': sha(native['native_conversation']), 'native_CLI_exit': native['returncode'],
    'native_model_attempts': 1, 'native_automatic_retries': 0, 'native_tool_events': native['tool_events'],
    'task_marker': raw['task_marker'], 'request_engine_ID_sha256': phase['request_engine_id_sha256'],
    'reply_engine_ID_sha256': phase['reply_engine_id_sha256'], 'request_body_sha256': phase['request_body_sha256'],
    'reply_body_sha256': phase['answer_body_sha256'], 'reply_to_and_native_SHA_correlation_verified': True,
    'math_answer': {'claim_valid': False, 'corrected_sum': 4},
    'link_readback': phase['readback'], 'relay_connected_alone_used_as_proof': False,
    'encrypted_window_byte_limit': 'includes background/control traffic; not a packet-level isolated math-payload measurement',
    'proxy_DNS_destination_rejections': 'CONNECT to 1.1.1.1/8.8.8.8/9.9.9.9:443 refused by fixture host allowlist; no upstream bytes',
    'CONNECT_headers_or_payload_modified': False, 'TLS_MITM_or_verify_disabled': False,
    'native_and_SSH_outside_engine_network_profile': True,
    'capability_channel': 'Python memory -> existing strict-hostkey SSH stdin -> explicit private IPC; raw not stored',
    'actual_fixture_members': 2, 'production_Reason_team_used': False,
    'cleanup': {'local': raw['cleanup']['local_engine'], 'peer': raw['cleanup']['peer']['engine'],
                'both_proxy_connect_after_stop': 61, 'SSH_exit': 0, 'known_processes_alive': 0},
    'peer_nonstate_files_copied_and_SHA_verified': len(peer['files']),
    'old_proxy_failure_C_UDP_results_unchanged': True, 'product_source_1697_modified': False,
    'success_not_extended_to': ['global network/firewall', 'corporate authenticated proxy',
        'SSH-free onboarding', 'self-hosted relay', 'different NAT', 'P12 product integration', 'D12 selection'],
    'audit_native_model_calls': 0}
summary['peer_individual_PID_generation_audit'] = json.loads((ROOT/'peer-final-PID-audit.json').read_text())
assert not any(x['same_owned_process_alive'] for x in summary['peer_individual_PID_generation_audit'])
(BASE/'proxy-variant-summary-20261029.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
print(json.dumps({'passed': True, 'native_attempts': 1, 'relay_links': phase['peer_links'],
    'roundtrip_ms': phase['roundtrip_ms'], 'native_CLI_ms': native['native_elapsed_ms'],
    'proxy_stats': {k:{a:b for a,b in v.items() if a!='groups'} for k,v in proxy_stats.items()},
    'peer_files_verified': len(peer['files']), 'known_processes_alive': 0}))
