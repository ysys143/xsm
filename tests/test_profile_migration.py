"""Issue #27: explicit home transfer, source fencing and bounded forwarding."""
import os
from unittest import mock

from tests.test_xsm import TempState


class ProfileMigrationTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import registry
        self.a = registry.upsert('codex', self.tmp + '/a', 'copied-id', os.getpid(), self.tmp, name='old')
        self.b = registry.upsert('codex', self.tmp + '/b', 'copied-id', os.getpid(), self.tmp, name='new')
        self.peer = registry.upsert('codex', self.tmp + '/peer', 'peer', os.getpid(), self.tmp, name='peer')

    def migrate(self, authorize=None, **kwargs):
        from xsm import migration
        plan = migration.prepare(self.b, 'ref:' + self.a['ref'])
        return migration.execute(plan, authorize=authorize or (lambda _: 'fixture user approval'), **kwargs)

    def test_permission_is_required_and_a_no_changes_nothing(self):
        from tests import permission_harness
        from xsm import decisions, handoff, migration, registry, send
        plan = migration.prepare(self.b, 'ref:' + self.a['ref'])
        with self.assertRaises(migration.MigrationError):
            migration.execute(plan, authorize=lambda _: None)
        self.assertIsNone(migration.retirement(self.a))
        self.assertEqual(len(registry.raw_records()), 3)
        sent = send.send('ref:' + self.a['ref'], 'retained on denial', sender=self.peer, wake=False)
        arguments = {'source': 'ref:' + self.a['ref']}
        first, _ = permission_harness.invoke(self.b, 'xsm_migrate', arguments)
        request = permission_harness.pending(self.b, first['content'][0]['text'])
        permission_harness.answer(self.b, request, 'deny')
        refused, _ = permission_harness.invoke(self.b, 'xsm_migrate', arguments)
        self.assertTrue(refused.get('isError'), refused)
        self.assertEqual(decisions.read(request['id'])['status'], 'denied')
        self.assertIsNone(migration.retirement(self.a))
        self.assertEqual(handoff.status(self.a, sent.msg_id)['message']['body'], 'retained on denial')
        self.assertEqual(handoff.status(self.b, sent.msg_id)['status'], 'not-found')

    def test_source_cannot_reclaim_registration_or_send_after_transfer(self):
        from xsm import migration, registry, send
        receipt = self.migrate()
        self.assertEqual(receipt['status'], 'committed')
        self.assertEqual(migration.retirement(self.a)['id'], receipt['id'])
        resumed = registry.upsert('codex', self.a['home'], 'copied-id', os.getpid(), self.tmp)
        self.assertFalse(resumed['registered'])
        result = send.send('ref:' + self.peer['ref'], 'old task', sender=self.a, wake=False)
        self.assertEqual(result.status, 'refused')
        self.assertIn('retired', result.reason)

    def test_old_ref_forwards_to_successor_without_changing_sender(self):
        from xsm import handoff, migration, send
        self.migrate()
        result = send.send('ref:' + self.a['ref'], 'new input', sender=self.peer, wake=False)
        self.assertEqual(result.status, 'stored', result.lines())
        record = handoff.status(self.b, result.msg_id)
        self.assertEqual(record['message']['sender']['home'], self.peer['home'])
        self.assertEqual(record['receiver']['home'], self.b['home'])
        catchup = migration.status(self.b)['migrations'][0]['messages']
        self.assertEqual([item['id'] for item in catchup], [result.msg_id])
        self.assertIsNotNone(catchup[0]['addressed_via'])
        self.assertIsNone(catchup[0]['original_status'])

    def test_forwarding_expires_at_24_hours_but_retirement_does_not(self):
        from xsm import migration
        receipt = self.migrate()
        self.assertEqual(receipt['forward_until'] - receipt['committed_at'], 86400)
        forwarded, _ = migration.redirect(self.a, now=receipt['forward_until'] - .01)
        self.assertEqual(forwarded['home'], self.b['home'])
        with self.assertRaisesRegex(migration.MigrationError, 'expired'):
            migration.redirect(self.a, now=receipt['forward_until'])
        self.assertIsNotNone(migration.retirement(self.a))
        with self.assertRaisesRegex(migration.MigrationError, 'clock'):
            migration.redirect(self.a, now=receipt['committed_at'] - 1)

    def test_unread_original_survives_and_old_claim_cannot_ack_it(self):
        from xsm import handoff, receive, send
        result = send.send('ref:' + self.a['ref'], 'before transfer', sender=self.peer, wake=False)
        owner = {'type': 'native', 'id': 'test-reader-a'}
        claimed = handoff.claim(self.a, owner, 'generation-a')
        original = handoff.status(self.a, result.msg_id)
        self.migrate()
        copy = handoff.status(self.b, result.msg_id)
        self.assertEqual(copy['digest'], original['digest'])
        self.assertEqual(copy['message'], original['message'])
        self.assertIsNone(copy['claim'])
        self.assertEqual(copy['status'], 'pending')
        with self.assertRaises(ValueError):
            handoff.ack(self.a, claimed['claim']['token'], owner, 'generation-a')
        batch = receive.take_inbox_claims(self.b, owner={'type': 'native', 'id': 'test-reader-b'},
                                         generation='generation-b')
        self.assertTrue(batch['claims'], batch)
        self.assertIn('before transfer', '\n'.join(batch['messages']))

    def test_generation_change_during_question_prevents_transfer(self):
        from xsm import migration, registry
        plan = migration.prepare(self.b, 'ref:' + self.a['ref'])
        def changed(_):
            value = dict(self.a, lstart='a different execution')
            registry.save(value)
            return 'fixture user approval'
        with self.assertRaisesRegex(migration.MigrationError, 'changed'):
            migration.execute(plan, authorize=changed)
        self.assertIsNone(migration.retirement(self.a))

    def test_interrupted_fenced_transfer_resumes_without_another_permission(self):
        from xsm import migration
        plan = migration.prepare(self.b, 'ref:' + self.a['ref'])
        def crash(step):
            if step == 'fenced':
                raise RuntimeError('simulated interruption')
        with self.assertRaisesRegex(RuntimeError, 'simulated'):
            migration.execute(plan, authorize=lambda _: 'fixture user approval', fault=crash)
        self.assertIsNotNone(migration.retirement(self.a))
        resumed = migration.execute(plan, authorize=lambda _: self.fail('asked twice'))
        self.assertEqual(resumed['status'], 'committed')

    def test_replay_returns_the_same_transfer(self):
        first = self.migrate()
        second = self.migrate(authorize=lambda _: self.fail('repeated permission'))
        self.assertEqual(second['id'], first['id'])
        self.assertEqual(second['committed_at'], first['committed_at'])

    def test_cli_uses_the_same_transfer_service(self):
        import io
        from contextlib import redirect_stdout
        from xsm import cli, migration, registry
        out = io.StringIO()
        with mock.patch.object(registry, 'me', return_value=self.b), \
                mock.patch('xsm.workers.human_terminal', return_value=True), \
                mock.patch.object(migration, 'execute', wraps=migration.execute) as shared, redirect_stdout(out):
            self.assertEqual(cli.main(['migrate', 'ref:' + self.a['ref']]), 0)
        self.assertEqual(shared.call_count, 1)
        self.assertIn('committed', out.getvalue())

    def test_mcp_native_permission_applies_once_and_retired_tools_refuse(self):
        from tests import permission_harness
        from xsm import migration
        arguments = {'source': 'ref:' + self.a['ref']}
        first, _ = permission_harness.invoke(self.b, 'xsm_migrate', arguments)
        record = permission_harness.pending(self.b, first['content'][0]['text'])
        self.assertIsNone(migration.retirement(self.a))
        permission_harness.answer(self.b, record, 'allow')
        result, _ = permission_harness.invoke(self.b, 'xsm_migrate', arguments)
        self.assertFalse(result.get('isError'), result)
        self.assertIsNotNone(migration.retirement(self.a))
        second, frames = permission_harness.invoke(self.b, 'xsm_migrate', arguments)
        self.assertEqual(result, second)
        self.assertFalse(any(row.get('method') == 'elicitation/create' for row in frames))
        denied, _ = permission_harness.invoke(self.a, 'xsm_join', {'project': 'old-task'})
        self.assertTrue(denied.get('isError'), denied)
        self.assertIn('retired', denied['content'][0]['text'])

    def test_team_role_and_board_items_move_idempotently_after_effect_crash(self):
        from xsm import board, migration, teams
        teams.create(self.a, 'core')
        teams.set_lead(self.a, 'core', teams.member_of(self.a), 'fixture')
        board.set_item(self.a, 'core', 'owner/old', 'work remains')
        plan = migration.prepare(self.b, 'ref:' + self.a['ref'])
        def crash(step):
            if step == 'effect:teams':
                raise RuntimeError('simulated after team effect')
        with self.assertRaises(RuntimeError):
            migration.execute(plan, authorize=lambda _: 'fixture approval', fault=crash)
        before = len(board.log(self.b, 'core'))
        result = migration.execute(plan, authorize=lambda _: self.fail('asked twice'))
        self.assertEqual(result['status'], 'committed')
        self.assertEqual(len(board.log(self.b, 'core')), before)
        self.assertTrue(teams.is_lead(teams.require('core'), self.b))
        self.assertFalse(teams.is_member(teams.require('core'), self.a))
        self.assertIn('work remains', board.current('core')['owner/new'][0]['body'])

    def test_pending_user_permission_moves_as_a_request_not_an_old_allow(self):
        from tests import permission_harness
        from xsm import config, decisions, migration
        first, _ = permission_harness.invoke(self.a, 'xsm_join', {'project': 'pending-permission'})
        original = permission_harness.pending(self.a, first['content'][0]['text'])
        permission_harness.answer(self.a, original, 'allow')
        self.migrate()
        self.assertEqual(decisions.read(original['id'])['status'], 'superseded')
        self.assertNotIn('pending-permission', config.joined_projects(self.b))
        first, _ = permission_harness.invoke(self.b, 'xsm_join', {'project': 'pending-permission'})
        fresh = permission_harness.pending(self.b, first['content'][0]['text'])
        self.assertNotEqual(fresh['id'], original['id'])
        self.assertIsNone(fresh['answer'])
        self.assertEqual(len(migration.status(self.b)['migrations'][0]['permissions']), 1)

    def test_worker_link_and_already_notified_project_request_follow_successor(self):
        from xsm import delegation, send
        delegation.attach(self.a, self.peer, 'group')
        original_send = send.send
        def passive(*args, **kwargs):
            kwargs['wake'] = False
            return original_send(*args, **kwargs)
        with mock.patch.object(send, 'send', side_effect=passive):
            delegation.request_join(self.peer, self.a, 'new-scope')
        self.migrate()
        self.assertEqual(delegation.parent(self.peer)['ref'], self.b['ref'])
        with mock.patch.object(send, 'send', side_effect=AssertionError('duplicate parent notification')):
            text = delegation.request_join(self.peer, self.b, 'new-scope')
        self.assertIn(self.b['ref'], text)

    def test_held_message_remains_held_at_the_successor(self):
        from xsm import envelope, handoff, ledger, paths, receive, send
        result = send.send('ref:' + self.a['ref'], 'held input', sender=self.peer, wake=False)
        original = handoff.status(self.a, result.msg_id)
        parsed = envelope.parse(original['message']['content'])
        held = receive.hold('codex', 'fixture hold', {}, self.a, parsed)
        handoff.delivery(self.a, result.msg_id, 'held')
        ledger.receipt(result.msg_id, 'held', self.a, 'fixture hold')
        self.migrate()
        self.assertEqual(handoff.status(self.b, result.msg_id)['delivery_state'], 'held')
        self.assertEqual(paths.read_json(paths.path(paths.HELD, held + '.json'))['receiver_ref'], self.b['ref'])
        self.assertEqual(handoff.claim(self.b, {'type': 'native', 'id': 'b'}, 'generation')['status'], 'empty')

    def test_reclaim_requires_a_fresh_question_and_does_not_reuse_old_transfer(self):
        from tests import permission_harness
        from xsm import migration, registry, send
        first = self.migrate()
        old = registry.by_session('codex', 'copied-id', home=self.a['home'])
        args = {'source': 'ref:' + self.b['ref']}
        result, _ = permission_harness.invoke(old, 'xsm_migrate', args)
        question = permission_harness.pending(old, result['content'][0]['text'])
        self.assertIsNotNone(migration.retirement(self.a))
        permission_harness.answer(old, question, 'allow')
        result, _ = permission_harness.invoke(old, 'xsm_migrate', args)
        self.assertFalse(result.get('isError'), result)
        self.assertIsNone(migration.retirement(self.a))
        self.assertIsNotNone(migration.retirement(self.b))
        updated = registry.by_session('codex', 'copied-id', home=self.a['home'])
        plan = migration.prepare(registry.by_session('codex', 'copied-id', home=self.b['home']), 'ref:' + self.a['ref'])
        self.assertNotEqual(plan['id'], first['id'])
        sent = send.send('ref:' + self.b['ref'], 'after reclaim', sender=self.peer, wake=False)
        self.assertEqual(sent.target['home'], updated['home'])

    def test_question_effect_crash_keeps_the_ids_and_successor_can_answer_old_tasks(self):
        from xsm import migration, paths, question_groups, questions, registry
        paths.write_json(questions._filename('pending-question'), {
            'id': 'pending-question', 'sender': questions._handle(self.a), 'target': questions._handle(self.peer),
            'body': 'question', 'replies': [], 'purpose': 'question', 'created_at': 1.0})
        peer2 = registry.upsert('codex', self.tmp + '/peer2', 'peer2', os.getpid(), self.tmp, name='peer2')
        group = question_groups.ask_many(self.a, ['ref:' + self.peer['ref'], 'ref:' + peer2['ref']],
                                         'retained group question', wake='never')
        children = question_groups.child_ids(group['id'])
        self.assertEqual(len(children), 2)
        plan = migration.prepare(self.b, 'ref:' + self.a['ref'])
        def crash(step):
            if step == 'effect:questions':
                raise RuntimeError('simulated')
        with self.assertRaises(RuntimeError):
            migration.execute(plan, authorize=lambda _: 'fixture approval', fault=crash)
        result = migration.execute(plan, authorize=lambda _: self.fail('asked twice'))
        self.assertCountEqual(result['steps']['questions']['questions'], ['pending-question', *children])
        self.assertEqual(result['steps']['questions']['groups'], [group['id']])
        self.assertEqual(questions._native(paths.read_json(questions._filename('pending-question'))['sender']),
                         questions._native(self.b))
        from xsm import handover
        self.assertTrue(handover.succeeds(self.b, self.a))
        self.assertEqual(question_groups.status(self.a, group['id'])['status'], 'refused')
        self.assertTrue(questions.record_reply(self.b, self.peer,
            {'kind': 'reply', 'reply-to': children[0], 'id': 'late-group-reply', 'outcome': 'succeeded'},
            'late actual group result'))
        readback = question_groups.status(self.b, group['id'])
        self.assertEqual(len(readback['recipients']), 2)
        self.assertEqual(readback['replies'][0]['request_id'], children[0])

    def test_forwarding_does_not_reopen_after_expiry_then_clock_rollback(self):
        from xsm import migration
        record = self.migrate()
        with self.assertRaises(migration.MigrationError):
            migration.redirect(self.a, now=record['forward_until'])
        with self.assertRaises(migration.MigrationError):
            migration.redirect(self.a, now=record['committed_at'] + 1)

    def test_status_reports_an_interrupted_transfer_without_claiming_work(self):
        from tests import permission_harness
        from xsm import migration
        plan = migration.prepare(self.b, 'ref:' + self.a['ref'])
        def crash(step):
            if step == 'fenced': raise RuntimeError('simulated')
        with self.assertRaises(RuntimeError):
            migration.execute(plan, authorize=lambda _: 'fixture approval', fault=crash)
        result, _ = permission_harness.invoke(self.b, 'xsm_migrate', {})
        self.assertFalse(result.get('isError'), result)
        self.assertIn('fenced', result['content'][0]['text'])

    def test_native_delivery_wait_does_not_hold_the_profile_transfer_gate(self):
        import threading
        from xsm import adapters, handoff, ledger, send
        finished = threading.Event()
        errors = []
        def transfer():
            try: self.migrate()
            except BaseException as exc: errors.append(exc)
            finally: finished.set()
        worker = threading.Thread(target=transfer)
        self.addCleanup(worker.join, 5)
        def wait_for(ident, seconds):
            worker.start()
            self.assertTrue(finished.wait(4), 'waiting for native consumption blocked profile transfer')
            self.assertEqual(errors, [])
            return ledger.status(ident)
        with mock.patch.object(adapters, 'to_codex', return_value='Queued message fixture-queue'), \
                mock.patch.object(ledger, 'wait_for', side_effect=wait_for):
            result = send.send('ref:' + self.a['ref'], 'inflight original', sender=self.peer, wait=30)
        self.assertIn(result.status, ('sent-unconfirmed', 'delivered'))
        self.assertEqual(handoff.status(self.b, result.msg_id)['message']['body'], 'inflight original')

    def test_pending_attachment_bytes_and_digest_remain_available_to_successor(self):
        from xsm import context, files, handoff, receive, registry, send_service
        registry.note_capabilities(self.a, {'files': {'version': 1, 'status': 'observed'}}, reader_pid=os.getpid())
        result = send_service.execute({'target': 'ref:' + self.a['ref'], 'text': 'attached original',
            'request_id': 'attachment-transfer', 'wake': 'never',
            'attachments': [{'name': 'note.txt', 'text': 'exact file bytes'}]},
            caller=self.peer, call=context.of_record(self.peer, context.BASIS_SESSION))['result']
        self.assertEqual(result.status, 'stored', result.lines())
        original = handoff.status(self.a, result.msg_id)
        self.migrate()
        batch = receive.take_inbox_claims(self.b, owner={'type': 'native', 'id': 'attachment-reader'}, generation='new-reader')
        self.assertIn('attached original', '\n'.join(batch['messages']))
        sid = original['message']['file_storage']
        manifest = files.manifest(self.b, sid, incoming=True)
        copied = files.read_copy(self.b, sid, manifest['files'][0]['id'], incoming=True)
        self.assertEqual(copied, b'exact file bytes')
        self.assertEqual(handoff.status(self.b, result.msg_id)['digest'], original['digest'])

    def test_missing_successor_copy_is_not_reported_as_a_completed_transfer(self):
        from xsm import handoff, migration, send
        send.send('ref:' + self.a['ref'], 'must survive', sender=self.peer, wake=False)
        with mock.patch.object(handoff, 'transfer', return_value=[]):
            with self.assertRaisesRegex(migration.MigrationError, 'not transferred'):
                self.migrate()
        self.assertIsNotNone(migration.retirement(self.a))
        self.assertNotEqual(migration.retirement(self.a)['status'], 'committed')

    def test_unknown_previous_application_is_preserved_for_inspection_not_reexecution(self):
        from xsm import context, decisions, migration
        generation = context.of_record(self.a, context.BASIS_SESSION).generation
        args = {'project': 'uncertain-old-join'}
        scope = {'tool': 'xsm_join', 'arguments': args, 'cwd': self.tmp}
        key = decisions.invocation(self.a, 'xsm_join', args, generation)
        record = decisions.begin(key, self.a, scope, generation, 'Join?', choices=['allow', 'deny'])
        decisions.display(key, 'fixture', record['native_question'], 'native-user')
        decisions.response(key, {'result': {'action': 'accept', 'content': {'answer': 'allow'},
            '_meta': {'approvals_reviewer': 'user'}}}, 'native-user', displayed=record['native_question'])
        decisions.start_application(key, generation, scope)
        self.migrate()
        previous = decisions.read(key)
        self.assertEqual(previous['application']['phase'], 'started')
        self.assertNotEqual(previous['status'], 'applied')
        query = migration.status(self.b)['migrations'][0]['permissions']
        self.assertEqual(query[0]['action'], 'inspect-outcome')
        self.assertNotIn('answer', query[0])

    def test_old_receipt_cannot_read_new_messages_after_source_was_reclaimed(self):
        from xsm import migration, registry, send
        self.migrate()
        old = registry.by_session('codex', 'copied-id', home=self.a['home'])
        back = migration.prepare(old, 'ref:' + self.b['ref'])
        migration.execute(back, authorize=lambda _: 'fixture fresh approval')
        sent = send.send('ref:' + self.a['ref'], 'new private work after reclaim', sender=self.peer, wake=False)
        self.assertEqual(sent.status, 'stored', sent.lines())
        history = migration.status(self.b)['migrations'][0]['messages']
        self.assertNotIn('new private work after reclaim', [item['body'] for item in history])

    def test_reclaim_in_a_new_execution_does_not_unfence_the_original_process(self):
        from xsm import identity, migration, registry, send
        self.migrate()
        original_start = self.a['lstart']
        replacement_pid = 900001
        def started(pid):
            return 'replacement-execution' if pid == replacement_pid else original_start
        with mock.patch.object(identity, 'lstart', side_effect=started), \
                mock.patch.object(identity, 'pid_alive', return_value=True):
            registry.upsert('codex', self.a['home'], 'copied-id', replacement_pid, self.tmp, name='replacement')
            current = registry.by_session('codex', 'copied-id', home=self.a['home'])
            restore = migration.prepare(current, 'ref:' + self.b['ref'])
            migration.execute(restore, authorize=lambda _: 'fixture fresh approval')
            attempt = registry.upsert('codex', self.a['home'], 'copied-id', os.getpid(), self.tmp)
            self.assertFalse(attempt['registered'])
            self.assertEqual(registry.by_session('codex', 'copied-id', home=self.a['home'])['pid'], replacement_pid)
            refused = send.send('ref:' + self.peer['ref'], 'old process', sender=self.a, wake=False)
            self.assertEqual(refused.status, 'refused')
            with mock.patch.dict(os.environ, {'CODEX_HOME': self.a['home'], 'CODEX_THREAD_ID': 'copied-id'}), \
                    mock.patch.object(identity, 'ancestor_pid', return_value=os.getpid()):
                caller = registry.me()
            self.assertEqual(caller['pid'], os.getpid())
            self.assertTrue(caller['retired'])

    def test_a_foreground_copy_does_not_borrow_another_homes_worker_role(self):
        from xsm import consent, delegation, workers
        workers.save({'name': 'source-worker', 'runtime': 'codex', 'home': self.a['home'],
                      'session_id': 'copied-id', 'pid': self.a['pid'], 'cwd': self.tmp,
                      'mode': 'background', 'parent_ref': self.peer['ref']})
        with mock.patch.object(workers, 'state', return_value='running'):
            self.assertIsNotNone(consent.unattended(self.a))
            self.assertIsNone(consent.unattended(self.b))
            self.assertIsNone(delegation.parent(self.b))

    def test_retired_cli_cannot_narrow_the_shared_project_behind_the_successor(self):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        from xsm import cli, config
        config.join('kept-project', self.tmp)
        self.migrate()
        with mock.patch.dict(os.environ, {'CODEX_HOME': self.a['home'], 'CODEX_THREAD_ID': 'copied-id'}), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(['leave', 'kept-project']), cli.REFUSED)
        self.assertIn('kept-project', config.joined_projects(self.b))

    def test_old_exit_does_not_end_the_restored_new_execution(self):
        from xsm import identity, migration, registry
        self.migrate()
        original_start = self.a['lstart']
        with mock.patch.object(identity, 'lstart', side_effect=lambda pid: 'new-execution' if pid == 900002 else original_start), \
                mock.patch.object(identity, 'pid_alive', return_value=True):
            registry.upsert('codex', self.a['home'], 'copied-id', 900002, self.tmp)
            chosen = registry.by_session('codex', 'copied-id', home=self.a['home'])
            plan = migration.prepare(chosen, 'ref:' + self.b['ref'])
            migration.execute(plan, authorize=lambda _: 'fixture fresh approval')
            ended = registry.mark_ended('codex', 'copied-id', 'old exit', home=self.a['home'], pid=os.getpid())
            self.assertIsNone(ended)
            self.assertNotIn('ended_at', registry.by_session('codex', 'copied-id', home=self.a['home']))
