"""Issue #27: native conversation IDs are scoped to their config home."""
import os
from unittest import mock

from tests.test_xsm import TempState


class RegistryProfilesTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import identity
        self.a = os.path.realpath(os.path.join(self.tmp, 'home-a'))
        self.b = os.path.realpath(os.path.join(self.tmp, 'home-b'))
        for home in (self.a, self.b):
            os.makedirs(home)
        for patcher in (mock.patch.object(identity, 'lstart', return_value='fixture-start'),
                        mock.patch.object(identity, 'state_reason', return_value=('live', 'fixture'))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def register(self, home, pid=101, runtime='claude'):
        from xsm import registry
        return registry.upsert(runtime, home, 'copied-id', pid, self.tmp)

    def test_repeated_registration_keeps_both_homes_and_their_refs(self):
        from xsm import registry
        first = self.register(self.a)
        second = self.register(self.b, 202)
        self.register(self.a, 303)
        records = registry.raw_records()
        self.assertEqual(len(records), 2)
        self.assertEqual({r['ref'] for r in records}, {first['ref'], second['ref']})
        self.assertEqual(registry.by_session('claude', 'copied-id', home=self.b)['pid'], 202)

    def test_a_lookup_without_home_does_not_choose_one_of_two_copies(self):
        from xsm import registry
        self.register(self.a)
        self.register(self.b, 202)
        self.assertIsNone(registry.by_session('claude', 'copied-id'))

    def test_mcp_thread_lookup_checks_its_own_home_before_adopting_a_copy(self):
        from tests import test_mcp_identity as fixture
        rows = [fixture.row('codex', 'copied-id', 2, home=self.a),
                fixture.row('codex', 'copied-id', 1, home=self.b)]
        seen, _ = fixture.serve_one(rows, meta={'threadId': 'copied-id'},
                                    env={'CODEX_HOME': self.b})
        self.assertIsNotNone(seen[0])
        self.assertEqual(seen[0]['home'], self.b)

    def test_claude_caller_uses_its_own_home_after_other_home_registers(self):
        from xsm import registry
        expected = self.register(self.b, 202)
        self.register(self.a)
        with mock.patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': self.b,
                                         'CLAUDE_CODE_SESSION_ID': 'copied-id'}):
            caller = registry.me()
        self.assertEqual(caller['ref'], expected['ref'])
        self.assertEqual(caller['home'], self.b)

    def test_default_profiles_cannot_borrow_the_only_copy_in_another_home(self):
        from xsm import identity, registry
        for runtime, variable in [('claude', 'CLAUDE_CODE_SESSION_ID'), ('codex', 'CODEX_THREAD_ID')]:
            with self.subTest(runtime=runtime):
                self.register(self.b, runtime=runtime)
                with mock.patch.dict(os.environ, {variable: 'copied-id'}), \
                        mock.patch.object(identity, 'ancestor_pid', return_value=None), \
                        mock.patch.object(registry, 'adopt_self', return_value=None), \
                        mock.patch.object(registry, 'adopt_codex_self', return_value=None):
                    self.assertIsNone(registry.me())

    def test_codex_caller_uses_its_own_home_after_other_home_registers(self):
        from xsm import registry
        expected = self.register(self.b, 202, 'codex')
        self.register(self.a, runtime='codex')
        with mock.patch.dict(os.environ, {'CODEX_HOME': self.b, 'CODEX_THREAD_ID': 'copied-id'}):
            caller = registry.me()
        self.assertEqual(caller['ref'], expected['ref'])

    def test_send_preserves_exact_sender_and_recipient_for_copied_native_id(self):
        from xsm import handoff, registry, send
        b = self.register(self.b, 202)
        a = self.register(self.a)
        with mock.patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': self.b,
                                         'CLAUDE_CODE_SESSION_ID': 'copied-id'}):
            result = send.send('ref:' + a['ref'], 'message from B', wake=False, wait=0)
        self.assertIsNotNone(result.msg_id, result.lines())
        original = handoff.status(a, result.msg_id)
        self.assertEqual(original['message']['sender']['home'], b['home'])
        self.assertEqual(original['receiver']['home'], a['home'])
        self.assertEqual(handoff.status(b, result.msg_id)['status'], 'not-found')

    def test_session_end_in_one_home_does_not_end_the_other_copy(self):
        import time
        from xsm import housekeeping, identity, registry
        self.register(self.a)
        self.register(self.b, 202)
        registry.mark_ended('claude', 'copied-id', 'test-exit', home=self.a)
        self.assertIn('ended_at', registry.by_session('claude', 'copied-id', home=self.a))
        self.assertNotIn('ended_at', registry.by_session('claude', 'copied-id', home=self.b))
        with mock.patch.object(identity, 'state_of', side_effect=lambda row: 'ended' if row.get('ended_at') else 'live'):
            housekeeping.prune(now=time.time() + 365 * 86400)
        self.assertIsNone(registry.by_session('claude', 'copied-id', home=self.a))
        self.assertEqual(registry.by_session('claude', 'copied-id', home=self.b)['pid'], 202)

    def test_resume_in_the_same_home_preserves_metadata(self):
        from xsm import paths, registry
        first = self.register(self.a)
        first['custom_metadata'] = 'keep'
        paths.write_json(registry._record_path('claude', 'copied-id'), first)
        registry.mark_ended('claude', 'copied-id', 'test-exit', home=self.a)
        resumed = self.register(self.a, 303)
        self.assertEqual(resumed['ref'], first['ref'])
        self.assertEqual(resumed['custom_metadata'], 'keep')
        self.assertNotIn('ended_at', resumed)

    def test_legacy_pointer_moves_only_to_its_recorded_home(self):
        from xsm import identity, paths, registry
        legacy = paths.path(paths.SESSIONS, 'claude-copied-id.json')
        old = {'runtime': 'claude', 'session_id': 'copied-id', 'home': self.a,
               'pid': 101, 'lstart': 'fixture-start', 'cwd': self.tmp,
               'ref': identity.ref_of('claude', self.a, 'copied-id'),
               'custom_metadata': 'original'}
        paths.write_json(legacy, old)
        copy = self.register(self.b, 202)
        self.assertNotIn('custom_metadata', copy)
        original = self.register(self.a, 303)
        self.assertEqual(original['custom_metadata'], 'original')
        self.assertFalse(os.path.exists(legacy), 'old storage is retired after exact-home import')
        self.assertEqual(len(registry.raw_records()), 2)

    def test_one_copy_cannot_refresh_another_homes_capabilities(self):
        from xsm import registry
        a = self.register(self.a, os.getpid())
        b = self.register(self.b, os.getpid())
        with mock.patch('xsm.identity.pid_alive', return_value=True):
            self.assertEqual(registry._capability_endpoint(a)['home'], self.a)
            self.assertEqual(registry._capability_endpoint(b)['home'], self.b)

    def test_new_pointer_wins_if_old_file_import_was_interrupted(self):
        from xsm import paths, registry
        current = self.register(self.a, 202)
        legacy = dict(current, pid=101)
        paths.write_json(paths.path(paths.SESSIONS, 'claude-' + 'copied-id.json'), legacy)
        self.assertEqual(len(registry.raw_records()), 1)
        self.assertEqual(registry.by_session('claude', 'copied-id')['pid'], 202)

    def test_worker_names_are_not_borrowed_from_a_copy_in_another_home(self):
        from xsm import registry, workers
        a = self.register(self.a, runtime='codex')
        b = self.register(self.b, runtime='codex')
        workers.save({'name': 'worker-a', 'runtime': 'codex', 'home': self.a,
                      'session_id': 'copied-id', 'mode': 'background'})
        workers.save({'name': 'worker-b', 'runtime': 'codex', 'home': self.b,
                      'session_id': 'copied-id', 'mode': 'background'})
        self.assertEqual(registry.by_session('codex', 'copied-id', home=self.a)['name'], 'worker-a')
        self.assertEqual(registry.by_session('codex', 'copied-id', home=self.b)['name'], 'worker-b')
        self.assertIsNone(workers.for_session('copied-id'))
