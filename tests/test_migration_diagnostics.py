"""Migration audit/alias diagnostics use real temporary storage, no models."""
import io
import os
from contextlib import redirect_stdout
from unittest import mock

from tests.test_xsm import TempState


class MigrationDiagnosticsTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import registry
        self.a = registry.upsert('codex', self.tmp + '/a', 'copy', os.getpid(), self.tmp, name='old')
        self.b = registry.upsert('codex', self.tmp + '/b', 'copy', os.getpid(), self.tmp, name='new')
        self.peer = registry.upsert('codex', self.tmp + '/peer', 'peer', os.getpid(), self.tmp, name='peer')

    def move(self):
        from xsm import migration
        return migration.execute(migration.prepare(self.b, 'ref:' + self.a['ref']),
                                 authorize=lambda _: 'fixture user permission')

    def test_ref_and_qualified_name_forward_after_pointer_cleanup(self):
        from xsm import handoff, registry, send
        self.move()
        os.unlink(registry._record_path('codex', 'copy', self.a['home']))
        for target in ('ref:' + self.a['ref'], 'old@a'):
            with self.subTest(target=target):
                result = send.send(target, 'retained alias', sender=self.peer, wake=False)
                self.assertEqual(result.status, 'stored', result.lines())
                self.assertEqual(handoff.status(self.b, result.msg_id)['message']['body'], 'retained alias')

    def test_unresolved_failure_is_retained_but_not_delivered_or_body_disclosed(self):
        from xsm import delivery_attempts, migration, send
        result = send.send('ref:dead00', 'private failed body', sender=self.peer, wake=False)
        self.assertEqual(result.status, 'refused')
        self.assertTrue(result.msg_id)
        owned = delivery_attempts.get_owned(self.peer, result.msg_id)
        self.assertEqual(owned['body'], 'private failed body')
        self.assertIsNone(delivery_attempts.get_owned(self.b, result.msg_id))
        lookalike = dict(self.a, ref='dead00')
        incoming = delivery_attempts.incoming(lookalike)
        self.assertFalse(incoming[0]['target_verified'])
        self.assertNotIn('body', incoming[0])

    def test_failed_send_preserves_the_callers_persisted_request_id(self):
        from xsm import delivery_attempts, send
        result = send.send('ref:dead00', 'failed reply', sender=self.peer, wake=False,
                           msg_id='persisted-reply-id')
        self.assertEqual(result.status, 'refused')
        self.assertEqual(result.msg_id, 'persisted-reply-id')
        self.assertEqual(delivery_attempts.get_owned(self.peer, result.msg_id)['body'], 'failed reply')

    def test_known_failed_target_and_outgoing_work_follow_the_transfer(self):
        from xsm import migration, registry, send
        # A stopped source is an exact known target; no native process is touched.
        stopped = dict(self.a, ended_at=1, end_reason='worker-stopped')
        registry.save(stopped)
        failed = send.send('ref:' + self.a['ref'], 'known failed input', sender=self.peer, wake=False)
        self.assertEqual(failed.status, 'refused')
        outgoing = send.send('ref:dead01', 'old outgoing work', sender=self.a, wake=False)
        self.move()
        status = migration.status(self.b)['migrations'][0]
        self.assertEqual(status['incoming_failures'][0]['id'], failed.msg_id)
        self.assertEqual(status['incoming_failures'][0]['body'], 'known failed input')
        self.assertEqual(status['outgoing_failures'][0]['body'], 'old outgoing work')

    def test_duplicate_home_diagnostics_are_exposed_by_doctor(self):
        from xsm import cli, install, migration, registry
        report = {'session_profiles': migration.diagnostics([registry._enrich(self.a), registry._enrich(self.b)])}
        out = io.StringIO()
        with mock.patch.object(install, 'doctor', return_value=report), \
                mock.patch('xsm.policy.report', return_value={}), \
                mock.patch('xsm.setup_flow.doctor_report', return_value={}), redirect_stdout(out):
            self.assertEqual(cli.main(['doctor', '--json']), 0)
        self.assertIn('session_profiles', out.getvalue())
        self.assertIn(self.a['home'], out.getvalue())

    def test_doctor_retains_retirement_and_unknown_owner_after_pointer_cleanup(self):
        from xsm import identity, migration, registry
        receipt = self.move()
        for record in (self.a, self.b):
            os.unlink(registry._record_path(record['runtime'], record['session_id'], record['home']))
        with mock.patch('xsm.migration.time.time', return_value=receipt['forward_until']):
            group = migration.diagnostics([])[0]
        source = next(item for item in group['copies'] if item['address'] == identity.address(self.a))
        self.assertTrue(source['retired'])
        self.assertEqual(source['forwarding'], 'expired')
        self.assertEqual(source['current_owner'], identity.address(self.b))
        self.assertEqual(source['owner_state'], 'unknown')
        self.assertIn('pid', source['generation'])

    def test_unrelated_reclaimed_epoch_does_not_leak_into_old_catchup(self):
        from xsm import migration, registry, send
        self.move()
        # A later epoch belongs to a different execution of the old endpoint.
        later = dict(self.a, profile_epoch=9)
        registry.save(later)
        send.send('ref:dead02', 'later private failure', sender=later, wake=False)
        self.assertEqual(migration.status(self.b)['migrations'][0]['outgoing_failures'], [])
