"""Verify the external checker with an independent fixture and deliberate faults."""
import importlib.util
import io
import os
from pathlib import Path
import sys
import unittest
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("blackbox_conformance", ROOT / "scripts/conform-host-protocol.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class ExternalConformanceTest(unittest.TestCase):
    def test_peer_rejects_non_utf8_duplicate_keys_and_non_json_constants(self):
        frame = '{"jsonrpc":"2.0","id":1,"result":{}}\n'
        invalid = [frame.encode('utf-16-be'), frame.encode('utf-32-be'),
                   b'{"jsonrpc":"2.0","id":1,"result":{},"result":{}}\n',
                   b'{"jsonrpc":"2.0","id":1,"result":{"value":NaN}}\n']
        with tempfile.TemporaryDirectory(prefix='xsm-checker-wire-') as folder:
            env = {'HOME': folder, 'XSM_HOME': folder + '/state'}
            for wire in invalid:
                with self.subTest(wire=wire[:30]):
                    process = mock.Mock(stdin=io.BytesIO(), stdout=io.BytesIO(wire))
                    with mock.patch.object(checker.subprocess, 'Popen', return_value=process):
                        peer = checker.Peer(['fixture-only'], folder, env)
                    try:
                        with self.assertRaises((ValueError, RuntimeError)):
                            peer.call('initialize', {'protocolVersion': '1'})
                    finally:
                        peer.close()

    def test_peer_rejects_unisolated_environment_before_starting_candidate(self):
        with tempfile.TemporaryDirectory(prefix='xsm-conformance-guard-') as folder:
            variants = ({}, {'HOME': folder}, {'XSM_HOME': folder + '/state'},
                        {'HOME': str(Path.home()), 'XSM_HOME': folder + '/state'},
                        {'HOME': folder, 'XSM_HOME': str(Path.home() / '.xsm')})
            with mock.patch.object(checker.subprocess, 'Popen', side_effect=AssertionError('unsafe process launch reached')) as spawn:
                for environment in variants:
                    with self.subTest(keys=sorted(environment)):
                        with self.assertRaisesRegex(ValueError, 'isolated HOME and XSM_HOME'):
                            checker.Peer(['must-not-start'], folder, environment)
                self.assertFalse(spawn.called)

    def candidate(self, fault=""):
        return [sys.executable, "-B", str(ROOT / "tests/fixtures/minimal_protocol_host.py"), fault]

    def test_independent_lifecycle_fixture_passes_without_user_environment(self):
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "must-not-inherit"}):
            result = checker.run(self.candidate())
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(len(result["checks"]), 16)

    def test_constant_generation_is_detected(self):
        result = checker.run(self.candidate("constant-generation"))
        self.assertEqual(result["status"], "failed", result)
        self.assertEqual(result["activeCheck"], "stable address new generation")

    def test_cross_connection_handle_is_detected(self):
        result = checker.run(self.candidate("shared-handles"))
        self.assertEqual(result["status"], "failed", result)
        self.assertEqual(result["activeCheck"], "connection-local handles")

    def test_missing_lifetime_lock_is_detected(self):
        result = checker.run(self.candidate("skip-lock"))
        self.assertEqual(result["status"], "failed", result)
        self.assertEqual(result["activeCheck"], "single live conversation owner")

    def delivery_candidate(self, fault):
        if fault == 'none':
            return [sys.executable, '-B', str(ROOT / 'tests/fixtures/protocol_observed_host.py')]
        return [sys.executable, '-B', str(ROOT / 'tests/fixtures/protocol_delivery_fault.py'), fault]

    def test_actual_server_delivery_contract(self):
        result = checker.run(self.delivery_candidate('none'), suite='messaging')
        self.assertEqual(result['status'], 'passed', {k: v for k, v in result.items() if k != 'observations'})
        self.assertEqual(len(result['checks']), 33)

    def test_launch_failure_retains_a_reportable_check_state(self):
        result = checker.run(['/nonexistent/xsm-conformance-candidate'])
        self.assertEqual(result['status'], 'failed')
        self.assertIsNone(result['activeCheck'])
        self.assertIn('FileNotFoundError', result['error'])

    def test_actual_server_grant_producer(self):
        result = checker.run(self.delivery_candidate('none'), suite='grants', capture=True)
        self.assertEqual(result['status'], 'passed', result)
        self.assertEqual(len(result['checks']), 24)
        grants = [o['frame']['result']['grant'] for o in result['observations']
                  if o.get('operation') == 'xsm_grant' and 'grant' in o['frame'].get('result', {})]
        self.assertEqual(len(grants), 2)
        self.assertEqual(grants[0], grants[1])

    def test_grant_missing_producer_is_detected(self):
        result = checker.run(self.delivery_candidate('grant-missing-producer'), suite='grants')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'grant issuance returns producer scope')

    def test_grant_replay_new_id_is_detected(self):
        result = checker.run(self.delivery_candidate('grant-replay-id'), suite='grants')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'grant retry preserves original producer snapshot')

    def test_actual_server_host_selection_approval(self):
        result = checker.run(self.delivery_candidate('none'), suite='selection', capture=True)
        self.assertEqual(result['status'], 'passed', result)
        self.assertEqual(len(result['checks']), 28)
        self.assertEqual(sum(row['frame'].get('method') == 'decision/request' for row in result['observations']), 3)

    def test_host_selection_automatic_publication_is_detected(self):
        result = checker.run(self.delivery_candidate('selection-auto-apply-publication'), suite='selection')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'host answer does not publish before retry')

    def test_host_selection_cached_handshake_is_detected(self):
        result = checker.run(self.delivery_candidate('selection-stale-handshake'), suite='selection')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'handshake recovery is live rather than cached approval output')

    def test_actual_server_correlated_questions(self):
        result = checker.run(self.delivery_candidate('none'), suite='questions', capture=True)
        self.assertEqual(result['status'], 'passed', result)
        self.assertEqual(len(result['checks']), 32)
        queried = [row['frame']['result'] for row in result['observations']
                   if row.get('operation') == 'xsm_question_status' and 'result' in row['frame']]
        self.assertEqual(sum(value.get('group') is True and value.get('status') == 'refused' for value in queried), 2)

    def test_question_foreign_group_internal_error_is_detected(self):
        result = checker.run(self.delivery_candidate('questions-foreign-internal'), suite='questions')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'foreign group status is a scoped refusal')

    def test_question_ack_erasing_answer_history_is_detected(self):
        result = checker.run(self.delivery_candidate('questions-erases-acked-answer'), suite='questions')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'ACK retains indexed group answer without a new claim')

    def test_actual_server_send_contract(self):
        result = checker.run(self.delivery_candidate('none'), suite='sending', capture=True)
        self.assertEqual(result['status'], 'passed', result)
        self.assertEqual(len(result['checks']), 30)
        sent = [row['frame'] for row in result['observations'] if row.get('operation') == 'xsm_send']
        self.assertEqual(len(sent), 7)
        self.assertEqual(sum('error' in frame for frame in sent), 1)

    def test_send_storage_claiming_native_arrival_is_detected(self):
        result = checker.run(self.delivery_candidate('send-storage-as-arrival'), suite='sending')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'send storage is not native arrival or ACK')

    def test_send_group_reusing_a_recipient_id_is_detected(self):
        result = checker.run(self.delivery_candidate('send-group-shared-id'), suite='sending')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'group delivery IDs are independent of group ID')

    def test_send_attachment_failure_claiming_body_sent_is_detected(self):
        result = checker.run(self.delivery_candidate('send-failure-body-sent'), suite='sending')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'attachment refusal retains frozen recovery identity')

    def test_actual_server_document_contract(self):
        result = checker.run(self.delivery_candidate('none'), suite='documents', capture=True)
        self.assertEqual(result['status'], 'passed', result)
        self.assertEqual(len(result['checks']), 28)
        actions = {row['action'] for row in result['observations'] if row.get('operation') == 'xsm_doc'}
        self.assertEqual(actions, {'add', 'show', 'log', 'leaves', 'next', 'render'})

    def test_document_wip_hiding_a_candidate_is_detected(self):
        result = checker.run(self.delivery_candidate('doc-wip-hides-candidate'), suite='documents')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'wip declaration neither hides nor becomes candidate')

    def test_document_limit_changing_total_is_detected(self):
        result = checker.run(self.delivery_candidate('doc-limit-changes-total'), suite='documents')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'document next limit preserves total and prefix')

    def test_actual_server_collaboration_contract(self):
        result = checker.run(self.delivery_candidate('none'), suite='collaboration', capture=True)
        self.assertEqual(result['status'], 'passed', result)
        self.assertEqual(len(result['checks']), 31)
        records = [r['frame']['result']['decisions'] for r in result['observations']
                   if r.get('operation') == 'xsm_board' and r.get('action') == 'decisions'
                   and 'result' in r['frame']]
        self.assertEqual([len(rows) for rows in records], [0, 0, 1])

    def test_collaboration_lost_parent_is_detected(self):
        result = checker.run(self.delivery_candidate('board-lost-parent'), suite='collaboration')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'board update links observed predecessor')

    def test_collaboration_wrong_decision_source_is_detected(self):
        result = checker.run(self.delivery_candidate('board-wrong-source'), suite='collaboration')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'retry persists host sourced board decision')

    def test_actual_server_discovery_contract(self):
        result = checker.run(self.delivery_candidate('none'), suite='discovery', capture=True)
        self.assertEqual(result['status'], 'passed', {k: v for k, v in result.items() if k != 'observations'})
        self.assertEqual(len(result['checks']), 24)
        discovered = [row['frame']['result'] for row in result['observations']
                      if row.get('operation') == 'xsm_discover' and 'result' in row['frame']]
        self.assertEqual(len(discovered), 4)

    def test_discovery_private_home_leak_is_detected(self):
        result = checker.run(self.delivery_candidate('discovery-private-home'), suite='discovery')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'discovery exposes no local home or process identity')

    def test_discovery_missing_observation_source_is_detected(self):
        result = checker.run(self.delivery_candidate('discovery-missing-source'), suite='discovery')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'discovery observations retain source and freshness')

    def test_ignored_targeted_inbox_filter_is_detected(self):
        result = checker.run(self.delivery_candidate('ignore-inbox-filter'), suite='messaging')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'targeted inbox returns current owned token')

    def test_automatic_consumption_on_admission_is_detected(self):
        result = checker.run(self.delivery_candidate('auto-consume-admitted'), suite='messaging')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'admitted original survives generation change')

    def test_reused_claim_token_is_detected(self):
        result = checker.run(self.delivery_candidate('reuse-token'), suite='messaging')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'retry rotates claim token')

    def test_successful_foreign_ack_response_is_detected(self):
        result = checker.run(self.delivery_candidate('accept-foreign-ack'), suite='messaging')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'foreign consumer cannot acknowledge')

    def test_actual_notification_is_captured_and_preserves_original(self):
        result = checker.run(self.delivery_candidate('none'), suite='events', capture=True)
        self.assertEqual(result['status'], 'passed', {k: v for k, v in result.items() if k != 'observations'})
        self.assertEqual(len(result['checks']), 36)
        events = [entry['frame'] for entry in result['observations'] if 'method' in entry['frame']]
        self.assertTrue(events, result)
        self.assertEqual(events[0]['method'], 'events/available')

    def test_actual_host_decision_contract(self):
        result = checker.run(self.delivery_candidate('none'), suite='decisions', capture=True)
        self.assertEqual(result['status'], 'passed', {k: v for k, v in result.items() if k != 'observations'})
        self.assertEqual(len(result['checks']), 46)
        methods = {e.get('method') for e in result['observations'] if 'result' in e['frame']}
        self.assertIn('decision.response', methods)
        self.assertIn('decision.abandon', methods)
        self.assertTrue(any(e['frame'].get('method') == 'decision/request' for e in result['observations']))

    def test_changed_display_acceptance_is_detected(self):
        command = [sys.executable, '-B', str(ROOT / 'tests/fixtures/protocol_decision_fault.py'), 'ignore-display']
        result = checker.run(command, suite='decisions')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'changed display cannot answer')

    def test_automatic_decision_application_is_detected(self):
        command = [sys.executable, '-B', str(ROOT / 'tests/fixtures/protocol_decision_fault.py'), 'auto-apply']
        result = checker.run(command, suite='decisions')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'stored answer has host source and no applied effect')

    def test_actual_worker_approval_contract(self):
        result = checker.run(self.delivery_candidate('none'), suite='approvals', capture=True)
        self.assertEqual(result['status'], 'passed', {k:v for k,v in result.items() if k != 'observations'})
        self.assertEqual(len(result['checks']), 26)

    def test_worker_approval_wire_defects_are_detected(self):
        for fault in ('approval-missing-producer', 'approval-wrong-id'):
            with self.subTest(fault=fault):
                result = checker.run(self.delivery_candidate(fault), suite='approvals')
                self.assertEqual(result['status'], 'failed', result)
                self.assertEqual(result['activeCheck'], 'approved snapshot binds exact request')

    def test_worker_board_decision_wire_defects_are_detected(self):
        for fault in ('decision-missing-producer', 'decision-recorded-flipped'):
            with self.subTest(fault=fault):
                result = checker.run(self.delivery_candidate(fault), suite='collaboration')
                self.assertEqual(result['status'], 'failed', result)
                self.assertEqual(result['activeCheck'], 'board decision returns structured recorded receipt')

    def test_actual_scope_mutations_and_revocation_contract(self):
        result = checker.run(self.delivery_candidate('none'), suite='scopes', capture=True)
        self.assertEqual(result['status'], 'passed', {k:v for k,v in result.items() if k != 'observations'})
        self.assertEqual(len(result['checks']), 41)

    def test_scope_failure_observer_retains_a_deliberately_changed_start(self):
        import json
        command = self.delivery_candidate('none') + ['--simulate-start-drift']
        result = checker.run(command, suite='scopes')
        self.assertEqual(result['status'], 'failed', result)
        observations = [json.loads(line) for log in result['diagnostics'] for line in log.splitlines()
                        if line.startswith('{')]
        self.assertTrue(observations, result)
        observed = observations[-1]
        self.assertEqual(observed['event'], 'decision-current-refused')
        self.assertEqual(observed['reason'], 'lstart_changed')
        self.assertEqual(observed['state'], 'stale')
        self.assertTrue(observed['simulatedStartDrift'])
        self.assertNotEqual(observed['savedStart'], observed['observedStart'])
        self.assertEqual(observed['generation'], observed['expectedGeneration'])

    def test_scope_wire_defects_are_detected(self):
        for fault, check in (('scope-missing-producer', 'link snapshot names canonical roots'),
                             ('scope-wrong-root', 'link snapshot names canonical roots'),
                             ('scope-stale-active', 'unlink snapshot reports change')):
            with self.subTest(fault=fault):
                result = checker.run(self.delivery_candidate(fault), suite='scopes')
                self.assertEqual(result['status'], 'failed', result)
                self.assertEqual(result['activeCheck'], check)

    def test_actual_document_endorsement_contract(self):
        result = checker.run(self.delivery_candidate('none'), suite='endorsements', capture=True)
        self.assertEqual(result['status'], 'passed', {k:v for k,v in result.items() if k != 'observations'})
        self.assertEqual(len(result['checks']), 25)

    def test_endorsement_wire_defects_are_detected(self):
        for fault in ('endorsement-missing-producer', 'endorsement-wrong-parent'):
            with self.subTest(fault=fault):
                result = checker.run(self.delivery_candidate(fault), suite='endorsements')
                self.assertEqual(result['status'], 'failed', result)
                self.assertEqual(result['activeCheck'], 'endorsement receipt binds original node')

    def test_actual_handover_result_contract(self):
        result = checker.run(self.delivery_candidate('none'), suite='handovers', capture=True)
        self.assertEqual(result['status'], 'passed', {k:v for k,v in result.items() if k != 'observations'})
        self.assertEqual(len(result['checks']), 28)

    def test_handover_wire_defects_are_detected(self):
        for fault, check in (('handover-missing-producer','applied handover returns transfer receipt'),
                             ('handover-wrong-successor','transfer receipt binds source and successor')):
            with self.subTest(fault=fault):
                result = checker.run(self.delivery_candidate(fault), suite='handovers')
                self.assertEqual(result['status'], 'failed', result)
                self.assertEqual(result['activeCheck'], check)

    def test_actual_owned_public_projection_contract(self):
        command = [sys.executable, '-B', str(ROOT / 'tests/fixtures/protocol_owned_fixture.py')]
        result = checker.run(command, suite='owned-fixture', capture=True)
        self.assertEqual(result['status'], 'passed', {k:v for k,v in result.items() if k != 'observations'})
        self.assertEqual(len(result['checks']), 32)

    def test_owned_fixture_suite_refuses_a_production_candidate_before_launch(self):
        result = checker.run(self.delivery_candidate('none'), suite='owned-fixture')
        self.assertEqual(result['status'], 'failed', result)
        self.assertEqual(result['activeCheck'], 'owned fixture candidate declares model0')

    def test_owned_public_projection_faults_are_detected(self):
        for fault, check in (('private-leak','owned creation exposes no profile or owner record'),
                             ('missing-result-body','owned result retains task outcome separately from reply storage')):
            with self.subTest(fault=fault):
                command=[sys.executable,'-B',str(ROOT/'tests/fixtures/protocol_owned_fixture.py'),fault]
                result=checker.run(command,suite='owned-fixture')
                self.assertEqual(result['status'],'failed',result)
                self.assertEqual(result['activeCheck'],check)

    def test_all_team_and_board_actions_return_contract_results(self):
        result=checker.run(self.delivery_candidate('none'),suite='team-board-actions',capture=True)
        self.assertEqual(result['status'],'passed',{k:v for k,v in result.items() if k!='observations'})
        self.assertEqual(len(result['checks']),37)
        observed={(row['operation'],row.get('action')) for row in result['observations'] if row.get('operation') in ('xsm_team','xsm_board')}
        self.assertEqual(len(observed),16)

    def test_team_board_mutation_wire_faults_are_detected(self):
        for fault, check in (('team-missing-change','team create includes structured receipt'),
                             ('team-empty-members','team create returns membership snapshot'),
                             ('board-missing-change','board set includes structured receipt'),
                             ('board-wrong-body','board set returns complete contribution receipt')):
            with self.subTest(fault=fault):
                result=checker.run(self.delivery_candidate(fault),suite='team-board-actions')
                self.assertEqual(result['status'],'failed',result)
                self.assertEqual(result['activeCheck'],check)

    def test_standard_errors_and_post_effect_failure_contract(self):
        command=[sys.executable,'-B',str(ROOT/'tests/fixtures/protocol_error_fixture.py')]
        result=checker.run(command,suite='errors-fixture',capture=True)
        self.assertEqual(result['status'],'passed',{k:v for k,v in result.items() if k!='observations'})
        self.assertEqual(len(result['checks']),27)
        codes={row['frame']['error']['code'] for row in result['observations'] if 'error' in row['frame']}
        self.assertEqual(codes,{-32700,-32600,-32601,-32602,-32603,-32001,-32002,-32003,-32004})

    def test_error_fault_suite_refuses_a_production_candidate(self):
        result=checker.run(self.delivery_candidate('none'),suite='errors-fixture')
        self.assertEqual(result['status'],'failed',result)
        self.assertEqual(result['activeCheck'],'error candidate declares isolated fault fixture')
