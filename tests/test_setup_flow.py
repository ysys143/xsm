"""P10 preparation fixtures; G04/G10 real-harness acceptance is not claimed."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import unittest
from unittest import mock

from tests.test_xsm import TempState


class SetupFlowTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import setup_flow
        self.flow = setup_flow
        self.target = {'runtime': 'codex', 'home': os.path.join(self.tmp, 'codex-custom')}
        Path(self.target['home']).mkdir()

    def record(self, state, step, status='succeeded', **kwargs):
        return self.flow.record(state['flow_id'], self.target, state['generation'], step, status, **kwargs)

    def _local_probe(self):
        from xsm import questions,registry
        me=registry.upsert('codex',self.target['home'],'probe-owner',os.getpid(),self.tmp,name='owner')
        peer=registry.upsert('codex',self.tmp+'/peer-home','probe-peer',os.getpid(),self.tmp,name='peer')
        result=questions.ask(me,'codex:probe-peer','probe',request_id='setup-probe',wake='never')
        self.assertEqual(result['send_evidence']['status'],'stored')
        return me,peer

    def _reply(self,me,peer):
        from xsm import receive,send
        reply=send.send('codex:probe-owner','actual fixture reply',sender=peer,kind='reply',
                       reply_to='setup-probe',outcome='succeeded',wake=False)
        self.assertEqual(reply.status,'stored')
        receive.poll_replies(me,'setup-probe')

    def test_actual_receive_path_completes_only_its_active_setup_flow_and_doctor_reads_proof(self):
        state=self.flow.begin(self.target)
        self.record(state,'runtime',evidence={'fixture':True})
        self.record(state,'harness',evidence={'fixture':True})
        me,peer=self._local_probe()
        self._reply(me,peer)
        current=self.flow.read(self.target)
        self.assertEqual(current['status'],'succeeded')
        report=self.flow.doctor_report({'homes':[{'runtime':'codex','path':self.target['home']}]})
        self.assertEqual(report['homes'][0]['first_roundtrip'],'fixture')
        self.assertIn('first_roundtrip_observed_at',report['homes'][0])

    def test_older_request_reply_does_not_complete_replacement_installation(self):
        state=self.flow.begin(self.target)
        self.record(state,'runtime',evidence={'fixture':True})
        self.record(state,'harness',evidence={'fixture':True})
        me,peer=self._local_probe()
        newer=self.flow.begin(self.target)
        self.record(newer,'runtime',evidence={'fixture':True})
        self.record(newer,'harness',evidence={'fixture':True})
        self._reply(me,peer)
        self.assertEqual(self.flow.read(self.target)['steps']['first-roundtrip']['status'],'pending')

    def test_failed_optional_setup_observation_never_hides_the_indexed_peer_answer(self):
        from xsm import questions,paths
        me,peer=self._local_probe()
        with mock.patch.object(self.flow,'observe_roundtrip',side_effect=OSError('observation denied')), \
             mock.patch.object(paths,'append_jsonl',side_effect=OSError('diagnostic denied')):
            self._reply(me,peer)
        self.assertEqual(questions.status(me,'setup-probe')['replies'][0]['body'],'actual fixture reply')

    def test_steps_are_durable_and_first_roundtrip_requires_actual_correlated_evidence(self):
        state = self.flow.begin(self.target)
        self.assertEqual(state['generation'], 1)
        self.assertEqual(self.flow.read(self.target), state)
        state = self.record(state, 'runtime')
        self.assertFalse(state['local_ready'])
        state = self.record(state, 'harness')
        self.assertTrue(state['local_ready'])
        self.assertEqual(state['status'], 'pending')
        with self.assertRaises(self.flow.SetupError):
            self.record(state, 'first-roundtrip')
        state = self.record(state, 'first-roundtrip', evidence={
            'request_id': 'q1', 'reply_to': 'q1', 'received': True,
            'replied': True, 'home_match': True, 'fixture': True})
        self.assertEqual(state['status'], 'succeeded')
        self.assertEqual(self.flow.read(self.target), state)
        self.assertEqual(stat.S_IMODE(Path(self.flow._flow(state['flow_id'])).stat().st_mode), 0o600)

    def test_login_success_does_not_claim_membership_or_harness_success(self):
        state = self.flow.begin(self.target, steps=('login', 'membership', 'harness'))
        state = self.record(state, 'login')
        self.assertEqual(state['steps']['membership']['status'], 'pending')
        state = self.record(state, 'membership', 'failed', evidence={'error_code': 'JOIN_FAILED'})
        self.assertEqual(state['status'], 'failed')
        self.assertEqual(state['steps']['login']['status'], 'succeeded')
        self.assertFalse(state['local_ready'])

    def test_optional_account_failure_preserves_completed_local_setup(self):
        state = self.flow.begin(self.target, steps=('runtime', 'harness', 'account'), optional_steps=('account',))
        state = self.record(state, 'runtime')
        state = self.record(state, 'harness')
        state = self.record(state, 'account', 'failed', evidence={'error_code': 'ACCOUNT_OFFLINE'})
        self.assertTrue(state['local_ready'])
        self.assertEqual(state['status'], 'partial')
        self.assertEqual(state['steps']['harness']['status'], 'succeeded')

    def test_replaced_flow_wrong_generation_and_wrong_target_cannot_apply(self):
        old = self.flow.begin(self.target)
        new = self.flow.begin(self.target)
        self.assertEqual(new['generation'], old['generation'] + 1)
        with self.assertRaises(self.flow.StaleFlowError):
            self.record(old, 'runtime')
        with self.assertRaises(self.flow.StaleFlowError):
            self.flow.record(new['flow_id'], self.target, old['generation'], 'runtime', 'succeeded')
        other = dict(self.target, home=os.path.join(self.tmp, 'another-home'))
        with self.assertRaises(self.flow.StaleFlowError):
            self.flow.record(new['flow_id'], other, new['generation'], 'runtime', 'succeeded')
        self.assertEqual(self.flow.read(self.target), new)
        self.assertTrue(Path(self.flow._flow(old['flow_id'])).exists())

    def test_flow_replaced_after_success_response_immediately_before_save_is_rejected(self):
        from xsm import install
        old = self.flow.begin(self.target)
        original = Path(self.flow._flow(old['flow_id'])).read_bytes()
        write = install._cas_bytes
        switched = []
        def replace_before_commit(filename, data, expected, **kwargs):
            if filename == self.flow._flow(old['flow_id']) and not switched:
                switched.append(True)
                self.flow.begin(self.target)
            return write(filename, data, expected, **kwargs)
        with mock.patch.object(install, '_cas_bytes', side_effect=replace_before_commit):
            with self.assertRaises(self.flow.StaleFlowError):
                self.record(old, 'runtime')
        self.assertEqual(Path(self.flow._flow(old['flow_id'])).read_bytes(), original)
        self.assertNotEqual(self.flow.read(self.target)['flow_id'], old['flow_id'])
        self.assertEqual(self.flow.read(self.target)['steps']['runtime']['status'], 'pending')

    def test_finisher_in_fresh_process_can_complete_after_original_waiter_is_gone(self):
        state = self.flow.begin(self.target, steps=('login',))
        program = ('import json,sys; from xsm import setup_flow as s; '
                   'x=json.loads(sys.argv[1]); '
                   's.record(x["flow_id"],x["target"],x["generation"],"login","succeeded")')
        subprocess.run([sys.executable, '-c', program, json.dumps(state)],
                       env=dict(os.environ, XSM_HOME=self.tmp), check=True, timeout=10)
        self.assertEqual(self.flow.read(self.target)['steps']['login']['status'], 'succeeded')

    def test_corrupt_or_nonprivate_state_is_an_error_not_a_new_generation(self):
        self.flow.begin(self.target)
        pending = Path(self.flow._pending(self.target))
        pending.write_text('[]')
        with self.assertRaises(ValueError):
            self.flow.begin(self.target)
        pending.write_text('{}')
        pending.chmod(0o644)
        with self.assertRaises(self.flow.SetupError):
            self.flow.read(self.target)

    def test_credentials_invites_and_raw_errors_are_not_evidence_fields(self):
        state = self.flow.begin(self.target)
        for key in ('token', 'authorization', 'invite', 'body', 'error', 'argv'):
            with self.subTest(key=key), self.assertRaises(self.flow.SetupError):
                self.record(state, 'runtime', evidence={key: 'secret-value'})
        with self.assertRaises(self.flow.SetupError):
            self.flow.begin(dict(self.target, token='secret-value'))
        self.assertNotIn('secret-value', Path(self.flow._flow(state['flow_id'])).read_text())

    def test_report_is_read_only_redacted_and_never_wakes_or_terminates_a_session(self):
        from xsm import install, paths
        settings = Path(self.target['home'], 'hooks.json')
        settings.write_text(json.dumps({'api_token': 'secret-token', 'body': 'private-original-body'}))
        before = {str(p): p.read_bytes() for p in Path(self.tmp).rglob('*') if p.is_file()}
        observations = [dict(self.target, trust=False, process=True, socket=False,
                             token='secret-token', error='private-original-body', invite='secret-invite',
                             runtime_version='secret-token', api_version='1.2')]
        with mock.patch.object(paths, 'write_json', side_effect=AssertionError('diagnostic write')), \
                mock.patch.object(install, 'git_head', return_value=None), \
                mock.patch.object(install.subprocess, 'run', side_effect=AssertionError('active process')):
            report = self.flow.report([{'runtime': 'codex', 'path': self.target['home']}], observations=observations)
        after = {str(p): p.read_bytes() for p in Path(self.tmp).rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        text = json.dumps(report)
        for private in ('secret-token', 'private-original-body', 'secret-invite', self.target['home']):
            self.assertNotIn(private, text)
        row = report['homes'][0]
        self.assertEqual(row['runtime_version'], 'unknown')
        self.assertEqual(row['api_version'], '1.2')
        self.assertEqual(row['trust'], 'not-observed')
        self.assertEqual(row['process'], 'observed')
        self.assertEqual(row['socket'], 'not-observed')
        self.assertTrue(all(value == 'unknown' for value in row['capabilities'].values()))
        self.assertNotIn('prerequisite',report)
        self.assertNotIn('gate',report)
        self.assertEqual(report['active_probe'], 'not-run')

    def test_first_roundtrip_report_requires_home_and_request_binding_and_marks_fixture(self):
        from xsm import install
        observation = dict(self.target, home_match=True, roundtrip={
            'request_id': 'q', 'reply_to': 'other', 'received': True, 'replied': True, 'fixture': True})
        home = {'runtime': 'codex', 'path': self.target['home']}
        with mock.patch.object(install, 'git_head', return_value=None):
            self.assertEqual(self.flow.report([home], observations=[observation])['homes'][0]['first_roundtrip'], 'not-observed')
            observation['roundtrip']['reply_to'] = 'q'
            self.assertEqual(self.flow.report([home], observations=[observation])['homes'][0]['first_roundtrip'], 'fixture')
            observation['home'] = '/different-home'
            row = self.flow.report([home], observations=[observation])['homes'][0]
            self.assertEqual(row['first_roundtrip'], 'not-observed')
            self.assertEqual(row['home_match'], 'unknown')


if __name__ == '__main__':
    unittest.main()
