"""Question service integration with isolated state and simulated runtime queue."""
import concurrent.futures
import os
from unittest import mock

from tests import test_xsm


class QuestionsTest(test_xsm.TempState):
    def setUp(self):
        super().setUp()
        from xsm import adapters, registry
        self.a = registry.upsert('codex', self.tmp + '/home', 'a', os.getpid(), self.tmp, name='a')
        self.b = registry.upsert('codex', self.tmp + '/home', 'b', os.getpid(), self.tmp, name='b')
        self.spec = 'ref:' + self.b['ref']
        patcher = mock.patch.object(adapters, 'to_codex', return_value=None)
        self.queue = patcher.start()
        self.addCleanup(patcher.stop)

    def _ask(self, **kwargs):
        from xsm import questions
        return questions.ask(self.a, self.spec, 'Which cache?', request_id='q1', **kwargs)

    def _reply(self, reply_id='r1', body='redis', outcome=None, **kwargs):
        from xsm import questions
        return questions.record_reply(kwargs.get('receiver', self.a), kwargs.get('sender', self.b),
                                      {'kind': 'reply', 'id': reply_id,
                                       'reply-to': kwargs.get('reply_to', 'q1'), 'outcome': outcome}, body)

    def test_receipt_is_not_answer_and_late_reply_is_recovered(self):
        from xsm import inbox, ledger, questions, receive
        result = self._ask()
        self.assertEqual(result['status'], 'pending')
        self.assertEqual(result['wait_end_reason'], 'timeout')
        self.assertEqual(result['recover_at'], {
            'cli': ['xsm', 'question-status', 'q1'],
            'mcp': {'tool': 'xsm_question_status', 'arguments': {'id': 'q1'}}})
        self.assertTrue(result['capabilities']['attachments'])
        self.assertTrue(result['capabilities']['wake_control'])
        self.assertEqual(result['capabilities']['priority'], {'claude': ['next', 'now'], 'codex': ['next']})
        self.assertEqual(result['wake'], 'transport_policy')
        self.assertEqual(result['send_evidence']['status'], 'sent-unconfirmed')
        self.assertEqual(inbox.count(self.b['session_id']), 1)
        self.assertEqual(len(receive.take_inbox(self.b)), 1)
        self.assertEqual(ledger.receipt_of('q1')['decision'], 'delivered')
        after = questions.status(self.a, 'q1')
        self.assertEqual(after['status'], 'pending')
        self.assertEqual(after['replies'], [])
        self.assertTrue(after['delivery_evidence']['runtime_reached'])
        self.assertTrue(self._reply())
        late = questions.status(self.a, 'q1')
        self.assertEqual(late['status'], 'reply_received')
        self.assertEqual(late['replies'][0]['body'], 'redis')
        self.assertFalse(late['final'])
        self.assertEqual(self._ask()['replies'], late['replies'])
        self.assertEqual(self.queue.call_count, 1)

    def test_real_reply_wire_and_authenticated_endpoint_correlation(self):
        from xsm import envelope, questions, receive, send
        self._ask()
        result = send.send('ref:' + self.a['ref'], 'redis', sender=self.b,
                           kind='reply', reply_to='q1', outcome='succeeded')
        self.assertEqual(result.status, 'sent-unconfirmed')
        parsed = envelope.parse(self.queue.call_args.args[2])
        self.assertTrue(questions.record_reply(self.a, self.b, parsed.header, parsed.body))
        self.assertEqual(len(receive.take_inbox(self.a)), 1)
        answer = questions.status(self.a, 'q1')
        self.assertEqual(answer['status'], 'final')
        self.assertTrue(answer['final'])
        self.assertEqual(answer['replies'][0]['body'], 'redis')

    def test_false_peer_other_home_receiver_and_unknown_request_rejected(self):
        from xsm import questions
        self._ask()
        self.assertTrue(self._reply('verified', 'known peer'))
        for field, value in (('runtime', 'claude'), ('home', self.tmp + '/other'),
                             ('session_id', 'replacement')):
            with self.subTest(field=field):
                self.assertFalse(self._reply(sender=dict(self.b, **{field: value})))
                self.assertFalse(self._reply(receiver=dict(self.a, **{field: value})))
        self.assertFalse(self._reply(reply_to='unknown'))
        self.assertFalse(questions.record_reply(self.a, self.b,
                         {'kind': 'note', 'id': 'r1', 'reply-to': 'q1'}, 'forged'))
        self.assertEqual([r['id'] for r in questions.status(self.a, 'q1')['replies']], ['verified'])
        self.assertEqual(questions.status(self.b, 'q1')['status'], 'refused')

    def test_parts_dedup_conflict_and_explicit_final(self):
        from xsm import questions
        self._ask()
        self.assertTrue(self._reply(body='part1'))
        self.assertTrue(self._reply(body='part1'))
        self.assertFalse(self._reply(body='changed'))
        self.assertTrue(self._reply('r2', 'part2'))
        partial = questions.status(self.a, 'q1')
        self.assertEqual(partial['status'], 'reply_received')
        self.assertFalse(partial['final'])
        self.assertEqual(len(partial['replies']), 2)
        self.assertTrue(self._reply('r3', 'done', 'succeeded'))
        self.assertTrue(questions.status(self.a, 'q1')['final'])
        self.assertEqual(len(questions.status(self.a, 'q1')['replies']), 3)

    def test_same_id_content_and_endpoint_changes_refused_no_resend(self):
        from xsm import paths, questions, registry
        self._ask()
        self._ask()
        self.assertEqual(self.queue.call_count, 1)
        self.assertEqual(questions.ask(self.a, self.spec, 'different', request_id='q1')['status'], 'refused')
        self.assertEqual(self._ask(purpose='handshake')['status'], 'refused')
        other = registry.upsert('codex', self.tmp + '/home', 'c', os.getpid(), self.tmp, name='c')
        self.assertEqual(questions.ask(self.a, 'ref:' + other['ref'], 'Which cache?',
                                       request_id='q1')['status'], 'refused')
        record = paths.read_json(paths.path('questions', 'q1.json'))
        self.assertEqual(record['body'], 'Which cache?')
        self.assertEqual(record['sender']['session_id'], self.a['session_id'])
        self.assertEqual(record['target']['home'], self.b['home'])
        self.assertEqual(len(record['digest']), 64)
        self.assertEqual(self.queue.call_count, 1)

    def test_no_scope_or_revoked_scope_never_calls_folder_offer(self):
        from xsm import config, connect, questions
        with mock.patch.object(connect, 'offer', side_effect=AssertionError('folder widening')):
            with mock.patch.object(config, 'scope_for', return_value=(None, 'not selected')):
                result = self._ask()
                self.assertEqual(result['status'], 'selection-required')
                self.assertEqual(self.queue.call_count, 0)
            # Scope is lost between ask's precheck and send's own validation.
            with mock.patch.object(config, 'scope_for', side_effect=[('scope', 'allowed'), (None, 'revoked')]):
                result = self._ask()
                self.assertEqual(result['send_evidence']['status'], 'refused')
                self.assertEqual(result['status'], 'refused')
                self.assertEqual(self.queue.call_count, 0)
        self.assertEqual(config.links(), [])

    def test_timeout_cancel_keep_index_and_inbox_then_late_answer(self):
        from xsm import inbox, paths, questions
        self._ask()
        before = inbox.count(self.b['session_id'])
        result = questions.wait_for(self.a, 'q1', wait=1, cancelled=lambda: True)
        self.assertEqual(result['wait_end_reason'], 'cancelled')
        self.assertEqual(inbox.count(self.b['session_id']), before)
        self.assertTrue(os.path.exists(paths.path('questions', 'q1.json')))
        with mock.patch.object(questions.time, 'monotonic', side_effect=[10, 10.5, 11]), \
                mock.patch.object(questions.time, 'sleep'):
            result = questions.wait_for(self.a, 'q1', wait=0.1)
        self.assertEqual(result['wait_end_reason'], 'timeout')
        self.assertTrue(self._reply())
        self.assertEqual(questions.wait_for(self.a, 'q1', wait=0)['wait_end_reason'], 'reply')

    def test_pump_reentrant_reply_and_handshake_not_receipt(self):
        from xsm import questions, receive
        self._ask(purpose='handshake')
        receive.take_inbox(self.b)
        self.assertEqual(questions.status(self.a, 'q1')['handshake'], 'pending')
        def pump():
            self.assertEqual(questions.status(self.a, 'q1')['status'], 'pending')
            self.assertTrue(self._reply())
        result = questions.wait_for(self.a, 'q1', wait=1, pump=pump)
        self.assertEqual(result['handshake'], 'reply_received')
        self.assertEqual(result['wait_end_reason'], 'reply')
        self.assertFalse(result['final'])

    def test_concurrent_reply_file_updates_no_lost_parts(self):
        from xsm import questions
        self._ask()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            accepted = list(pool.map(lambda i: self._reply('r%d' % i, str(i)), range(32)))
        self.assertTrue(all(accepted))
        replies = questions.status(self.a, 'q1')['replies']
        self.assertEqual(len(replies), 32)
        self.assertEqual({r['body'] for r in replies}, {str(i) for i in range(32)})

    def test_concurrent_same_request_has_one_send(self):
        from xsm import questions
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: self._ask(), range(12)))
        self.assertTrue(all(r['status'] == 'pending' for r in results))
        self.assertEqual(self.queue.call_count, 1)
        self.assertEqual(questions.status(self.a, 'q1')['status'], 'pending')

    def test_invalid_ids_wait_and_purpose(self):
        from xsm import questions
        self.assertEqual(questions.ask(self.a, self.spec, 'x', request_id='../escape')['status'], 'refused')
        self.assertEqual(self._ask(purpose='other')['status'], 'refused')
        with self.assertRaises(ValueError):
            self._ask(wait=float('inf'))
        self.assertEqual(questions.status(self.a, '../escape')['status'], 'refused')
        self.assertEqual(self.queue.call_count, 0)

    def test_transport_error_is_visible_and_same_id_is_not_retried(self):
        from xsm import questions
        self.queue.side_effect = OSError('queue unavailable')
        first = self._ask(wait=1)
        self.assertEqual(first['status'], 'error')
        self.assertEqual(first['wait_end_reason'], 'error')
        self.assertEqual(first['send_evidence']['status'], 'error')
        self.assertEqual(self._ask()['status'], 'error')
        self.assertEqual(self.queue.call_count, 1)
        # A late authenticated reply still takes precedence over send failure.
        self.assertTrue(self._reply())
        self.assertEqual(questions.status(self.a, 'q1')['status'], 'reply_received')

    def test_client_eof_ends_wait_but_keeps_index_and_late_reply(self):
        from xsm import inbox, paths, questions
        self._ask()
        before = inbox.count(self.b['session_id'])
        result = questions.wait_for(self.a, 'q1', wait=30, pump=lambda: False)
        self.assertEqual(result['wait_end_reason'], 'client_closed')
        self.assertEqual(result['status'], 'pending')
        self.assertTrue(os.path.exists(paths.path('questions', 'q1.json')))
        self.assertEqual(inbox.count(self.b['session_id']), before)
        self.assertTrue(self._reply())
        self.assertEqual(questions.status(self.a, 'q1')['status'], 'reply_received')

    def test_reply_recorded_by_closing_pump_is_recovered_before_eof(self):
        from xsm import questions
        self._ask()
        def closing_pump():
            self.assertTrue(self._reply())
            return False
        result = questions.wait_for(self.a, 'q1', wait=1, pump=closing_pump)
        self.assertEqual(result['wait_end_reason'], 'reply')
        self.assertEqual(result['replies'][0]['body'], 'redis')

    def test_native_address_survives_short_ref_collision(self):
        from xsm import questions, registry
        other = registry.upsert('codex', self.tmp + '/home', 'collision',
                                os.getpid(), self.tmp, name='collision')
        rows = registry.raw_records()
        for row in rows:
            if row['session_id'] == other['session_id']:
                row['ref'] = self.b['ref']
        with mock.patch.object(registry, 'raw_records', return_value=rows):
            result = questions.ask(self.a, 'codex:' + self.b['session_id'],
                                   'Which cache?', request_id='q1', purpose='handshake')
        self.assertEqual(result['send_evidence']['status'], 'sent-unconfirmed', result)
        self.assertEqual(self.queue.call_args.args[:2], (self.b['home'], self.b['session_id']))
        self.assertTrue(self._reply(outcome='succeeded'))
        self.assertEqual(questions.status(self.a, 'q1')['handshake'], 'completed')

    def test_candidate_resolution_preserves_caller_and_address(self):
        from xsm import directory, questions, registry
        selected = 'candidate:opaque-selection'
        # The directory resolver is the coordinator-owned integration boundary.
        # Actual resolve.resolve and send services must both reach it as caller a.
        peer = registry.by_session('codex', self.b['session_id'])
        with mock.patch.object(directory, 'resolve_candidate', return_value=peer,
                               create=True) as candidate, \
                mock.patch.object(registry, 'adopt_open_codex', return_value=None):
            result = questions.ask(self.a, selected, 'Which cache?', request_id='q1',
                                   purpose='handshake')
            self.assertEqual(result['send_evidence']['status'], 'sent-unconfirmed', result)
            self.assertEqual(candidate.call_count, 2)
            for call in candidate.call_args_list:
                self.assertEqual(call.args, (self.a, 'opaque-selection'))
            changed = questions.ask(self.a, selected, 'Different body', request_id='q1',
                                    purpose='handshake')
            self.assertEqual(changed['status'], 'refused')
        self.assertEqual(self.queue.call_count, 1)
        self.assertEqual(self.queue.call_args.args[:2], (self.b['home'], self.b['session_id']))
        self.assertTrue(self._reply(outcome='succeeded'))
        self.assertEqual(questions.status(self.a, 'q1')['handshake'], 'completed')

    def test_initial_resolution_shares_outer_probe_budget_and_skips_spent_reads(self):
        from xsm import probe, questions, resolve
        work = mock.Mock(return_value='should not run')
        observed = []
        def lookup(spec):
            observed.append((probe._quick, probe._deadline))
            self.assertEqual(spec, self.spec)
            self.assertEqual(probe.limit(100), 0)
            self.assertEqual(probe.bounded(work, default='unknown'), 'unknown')
            return resolve.Resolution('not-found', reason='budget spent')
        with probe.quick(budget=0):
            deadline = probe._deadline
            # ask must inherit this deadline rather than restart a budget.
            with mock.patch.object(resolve, 'resolve', side_effect=lookup):
                result = self._ask()
            self.assertEqual(observed[0][1], deadline)
        self.assertIsNone(probe._quick)
        work.assert_not_called()
        self.assertEqual(result['status'], 'refused')
        self.assertEqual(self.queue.call_count, 0)

    def test_initial_resolution_is_bounded_and_delivery_runs_outside_budget(self):
        from xsm import probe, resolve, send
        original_resolve, original_send = resolve.resolve, send.send
        def lookup(*args, **kwargs):
            self.assertIsNotNone(probe._quick)
            self.assertLessEqual(probe.limit(100), probe.QUICK_TIMEOUT)
            return original_resolve(*args, **kwargs)
        def dispatch(*args, **kwargs):
            self.assertIsNone(probe._quick)
            return original_send(*args, **kwargs)
        with mock.patch.object(resolve, 'resolve', side_effect=lookup), \
                mock.patch.object(send, 'send', side_effect=dispatch):
            result = self._ask()
        self.assertEqual(result['send_evidence']['status'], 'sent-unconfirmed')
        self.assertEqual(self.queue.call_count, 1)

    def test_per_request_wake_support_keeps_automatic_transport_evidence(self):
        from xsm import adapters, questions
        queued = adapters.Queued('Queued message queue1 for thread b.')
        queued.wake = 'started'
        self.queue.return_value = queued
        result = self._ask()
        self.assertTrue(result['capabilities']['wake_control'])
        self.assertNotIn('wake', result['capabilities'])
        self.assertEqual(result['wake'], 'transport_policy')
        wake = result['delivery_evidence']['steps']['wake']
        self.assertTrue(wake['ok'])
        self.assertEqual(wake['detail'], 'started')
        self.assertEqual(questions.status(self.a, 'q1')['delivery_evidence']['steps']['wake'], wake)

    def test_expects_reply_matches_full_pair_readonly_even_after_final(self):
        from xsm import paths, questions
        self._ask()
        filename = paths.path('questions', 'q1.json')
        def snapshot():
            result = {}
            for folder, _, files in os.walk(self.tmp):
                for name in files:
                    path = os.path.join(folder, name)
                    with open(path, 'rb') as stream:
                        result[path] = stream.read()
            return result
        before = snapshot()
        self.assertTrue(questions.expects_reply(self.a, self.b, 'q1'))
        self.assertTrue(questions.expects_reply(
            dict(self.a, pid=1, name='renamed'), dict(self.b, pid=2), 'q1'))
        self.assertFalse(questions.expects_reply(self.b, self.a, 'q1'))
        for field, value in (('runtime', 'claude'), ('home', self.tmp + '/other'),
                             ('session_id', 'replacement')):
            with self.subTest(field=field):
                self.assertFalse(questions.expects_reply(
                    dict(self.a, **{field: value}), self.b, 'q1'))
                self.assertFalse(questions.expects_reply(
                    self.a, dict(self.b, **{field: value}), 'q1'))
        for request_id in ('unknown', '../escape', '', None, 42):
            self.assertFalse(questions.expects_reply(self.a, self.b, request_id))
        self.assertFalse(questions.expects_reply(None, self.b, 'q1'))
        self.assertEqual(snapshot(), before)
        self.assertTrue(self._reply(outcome='succeeded'))
        self.assertTrue(questions.expects_reply(self.a, self.b, 'q1'))
        self.assertTrue(os.path.exists(filename))

    def test_expects_reply_rejects_corrupt_or_mismatched_request(self):
        from xsm import paths, questions
        self._ask()
        filename = paths.path('questions', 'q1.json')
        original = paths.read_json(filename)
        for bad in (dict(original, id='different'), dict(original, sender={}),
                    dict(original, target=None), [], 'not a record'):
            paths.write_json(filename, bad)
            self.assertFalse(questions.expects_reply(self.a, self.b, 'q1'))
        with open(filename, 'w') as stream:
            stream.write('{')
        self.assertFalse(questions.expects_reply(self.a, self.b, 'q1'))

    def test_public_reply_homes_are_hashed_without_mutating_auth_records(self):
        import copy
        import hashlib
        import json
        from xsm import paths, questions
        self._ask()
        self.assertTrue(self._reply(outcome='succeeded'))
        filename = paths.path('questions', 'q1.json')
        record = paths.read_json(filename)
        before = copy.deepcopy(record)
        result = questions._result('q1', record)
        for endpoint, native in (('sender', self.b), ('receiver', self.a)):
            public = result['replies'][0][endpoint]
            self.assertNotIn('home', public)
            self.assertEqual(public['home_id'], hashlib.sha256(native['home'].encode()).hexdigest())
            self.assertNotIn(native['home'], json.dumps(result))
            self.assertEqual(record['replies'][0][endpoint]['home'], native['home'])
        self.assertEqual(record['target']['home'], self.b['home'])
        self.assertEqual(record, before)
        self.assertEqual(questions.status(self.a, 'q1')['replies'], result['replies'])
        result['replies'][0]['sender']['session_id'] = 'changed externally'
        self.assertEqual(record, before)
        self.assertEqual(paths.read_json(filename), before)
        self.assertTrue(questions.expects_reply(self.a, self.b, 'q1'))
        self.assertFalse(questions.expects_reply(self.a, dict(self.b, home='/other'), 'q1'))

    def test_handshake_tracks_latest_explicit_outcome_across_partial_replies(self):
        from xsm import questions
        initial = self._ask(purpose='handshake')
        self.assertEqual(initial['purpose'], 'handshake')
        self.assertIsNone(questions.status(self.a, 'missing')['purpose'])
        self.assertEqual(initial['handshake'], 'pending')
        self.assertIsNone(initial['final_outcome'])
        steps = [
            ('partial', None, 'reply_received', None),
            ('decline', 'failed', 'declined', 'failed'),
            ('detail', None, 'declined', 'failed'),
            ('ready', 'succeeded', 'completed', 'succeeded'),
            ('more', None, 'completed', 'succeeded'),
            ('withdraw', 'failed', 'declined', 'failed'),
        ]
        for reply_id, outcome, handshake, final_outcome in steps:
            with self.subTest(reply=reply_id):
                self.assertTrue(self._reply(reply_id, reply_id, outcome))
                result = questions.status(self.a, 'q1')
                self.assertEqual(result['purpose'], 'handshake')
                self.assertEqual(result['handshake'], handshake)
                self.assertEqual(result['final_outcome'], final_outcome)
                self.assertEqual(result['final'], final_outcome is not None)
                self.assertEqual(result['status'], 'final' if final_outcome else 'reply_received')

    def test_auto_id_cancel_lost_response_recovered_by_readonly_owner_list(self):
        import json
        from xsm import paths, questions
        # Simulate the client discarding the cancelled ask response, including ID.
        questions.ask(self.a, self.spec, 'recover my original question', wait=20,
                      cancelled=lambda: True, purpose='handshake')
        self.assertEqual(self.queue.call_count, 1)
        before = {}
        for folder, _, files in os.walk(self.tmp):
            for name in files:
                filename = os.path.join(folder, name)
                with open(filename, 'rb') as stream:
                    before[filename] = stream.read()
        rows = questions.list_requests(self.a)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['purpose'], 'handshake')
        self.assertEqual(row['preview'], 'recover my original question')
        self.assertEqual(row['status'], 'pending')
        self.assertNotIn('home', row['target'])
        self.assertNotIn(self.b['home'], json.dumps(rows))
        self.assertNotIn('replies', row)
        self.assertEqual(questions.list_requests(self.b), [])
        self.assertEqual(questions.list_requests(dict(self.a, session_id='new')), [])
        self.assertEqual(questions.list_requests(dict(self.a, home=self.tmp + '/other-home')), [])
        self.assertEqual(questions.list_requests(None), [])
        after = {}
        for folder, _, files in os.walk(self.tmp):
            for name in files:
                filename = os.path.join(folder, name)
                with open(filename, 'rb') as stream:
                    after[filename] = stream.read()
        self.assertEqual(before, after)
        self.assertEqual(self.queue.call_count, 1)
        self.assertEqual(questions.status(self.b, row['id'])['status'], 'refused')
        self.assertEqual(questions.status(dict(self.a, home='/other'), row['id'])['replies'], [])
        self.assertTrue(self._reply('late-auto', 'answer-secret', reply_to=row['id']))
        self.assertNotIn('answer-secret', json.dumps(questions.list_requests(self.a)))
        self.assertEqual(questions.list_requests(self.a)[0]['status'], 'reply_received')
        self.assertEqual(questions.status(self.a, row['id'])['replies'][0]['body'], 'answer-secret')

    def test_list_skips_invalid_records_and_other_owner_metadata(self):
        import copy
        import json
        from xsm import paths, questions
        self._ask()
        original = paths.read_json(paths.path('questions', 'q1.json'))
        bad_records = [[], {}, dict(original, id='wrong'), dict(original, sender={}),
                       dict(original, target={}), dict(original, created_at='bad'),
                       dict(original, digest='bad'), dict(original, replies='bad'),
                       dict(original, purpose='other')]
        for i, bad in enumerate(bad_records):
            request_id = 'bad%d' % i
            if isinstance(bad, dict) and bad.get('id') == 'q1':
                bad['id'] = request_id
            paths.write_json(paths.path('questions', request_id + '.json'), bad)
        foreign = copy.deepcopy(original)
        foreign.update(id='foreign', sender=dict(original['sender'], home=self.tmp + '/other'),
                       body='private-owner-title')
        paths.write_json(paths.path('questions', 'foreign.json'), foreign)
        with open(paths.path('questions', 'corrupt.json'), 'w') as stream:
            stream.write('{')
        os.symlink(paths.path('questions', 'q1.json'), paths.path('questions', 'symlink.json'))
        rows = questions.list_requests(self.a)
        self.assertEqual([r['id'] for r in rows], ['q1'])
        self.assertNotIn('private-owner-title', json.dumps(rows))
        self.assertEqual([r['id'] for r in questions.list_requests(
            dict(self.a, home=self.tmp + '/other'))], ['foreign'])
        self.assertEqual(self.queue.call_count, 1)

    def test_current_delivery_gate_and_errors_end_wait_without_timeout(self):
        from xsm import ledger, questions
        self._ask()
        for gate in ('held', 'blocked', 'refused', 'error'):
            with self.subTest(gate=gate):
                ledger.receipt('q1', gate, self.b, reason='current-' + gate)
                result = questions.status(self.a, 'q1')
                self.assertEqual(result['send_evidence']['status'], 'sent-unconfirmed')
                self.assertEqual(result['status'], gate)
                self.assertEqual(result['reason'], 'current-' + gate)
                self.assertEqual(result['wait_end_reason'], gate)
                pump = mock.Mock(side_effect=AssertionError('terminal gate must not wait'))
                waited = questions.wait_for(self.a, 'q1', wait=20, pump=pump)
                self.assertEqual(waited['wait_end_reason'], gate)
                pump.assert_not_called()
        # A real authenticated reply wins over transport/gate evidence.
        self.assertTrue(self._reply(outcome='succeeded'))
        self.assertEqual(questions.wait_for(self.a, 'q1', wait=20)['status'], 'final')
        self.assertEqual(questions.wait_for(self.a, 'q1', wait=20)['wait_end_reason'], 'reply')

    def test_current_ledger_failure_overrides_stale_send_snapshot(self):
        from xsm import ledger, questions
        self._ask()
        for state in ('refused', 'error'):
            with self.subTest(state=state):
                ledger.failed('q1', 'new-' + state, status=state)
                result = questions.status(self.a, 'q1')
                self.assertEqual(result['status'], state)
                self.assertEqual(result['reason'], 'new-' + state)
                self.assertEqual(result['wait_end_reason'], state)
                self.assertEqual(questions.list_requests(self.a)[0]['status'], state)

    def test_reply_cache_cannot_bypass_current_held_or_blocked_receipt(self):
        from xsm import envelope, inbox, ledger, questions, receive, send
        self._ask()
        sent = send.send('codex:' + self.a['session_id'], 'cached-answer', sender=self.b,
                         kind='reply', reply_to='q1')
        self.assertEqual(sent.status, 'sent-unconfirmed')
        wire = self.queue.call_args.args[2]
        parsed = envelope.parse(wire)
        inbox.keep_reply(self.a, parsed.header['id'], 'q1', wire)
        for gate in ('held', 'blocked'):
            with self.subTest(gate=gate):
                ledger.receipt('q1', gate, self.b, reason='question gate')
                ledger.receipt(parsed.header['id'], gate, self.a, reason='reply gate')
                self.assertEqual(receive.poll_replies(self.a, 'q1'), 0)
                self.assertEqual(questions.status(self.a, 'q1')['replies'], [])
                waited = questions.wait_for(self.a, 'q1', wait=20,
                                             pump=lambda: receive.poll_replies(self.a, 'q1'))
                self.assertEqual(waited['status'], gate)
                self.assertEqual(waited['wait_end_reason'], gate)
                self.assertEqual(len(inbox.reply_copies(self.a, 'q1')), 1)

    def test_same_id_canonical_body_equivalence_keeps_original_without_resend(self):
        from xsm import paths, questions
        original = 'caf\u00e9\r\n'
        equivalent = 'cafe\u0301\n'
        first = questions.ask(self.a, self.spec, original, request_id='canonical')
        self.assertEqual(first['send_evidence']['status'], 'sent-unconfirmed')
        filename = paths.path('questions', 'canonical.json')
        before = paths.read_json(filename)
        second = questions.ask(self.a, self.spec, equivalent, request_id='canonical')
        self.assertEqual(second['status'], first['status'])
        self.assertEqual(second['id'], first['id'])
        self.assertEqual(self.queue.call_count, 1)
        self.assertEqual(paths.read_json(filename), before)
        self.assertEqual(before['body'], original)
