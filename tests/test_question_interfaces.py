"""CLI/MCP question results share actual reply data; unread notes survive waits."""
import contextlib
import io
import json
import os
from unittest import mock
from tests.test_xsm import TempState


class QuestionInterfacesTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import adapters, context, registry
        home = os.path.join(self.tmp, "codex")
        self.home = home
        os.makedirs(home)
        self.me = registry.upsert("codex", home, "me", os.getpid(), self.tmp, name="me")
        self.peer = registry.upsert("codex", home, "peer", os.getpid(), self.tmp, name="peer")
        self.call = context.of_record(self.me, context.BASIS_SESSION)
        for patch in (mock.patch.object(registry, "me", return_value=self.me),
                      mock.patch.object(registry, "last_identity", return_value=self.call)):
            patch.start();self.addCleanup(patch.stop)
        transport = mock.patch.object(adapters, "to_codex", return_value=None)
        self.transport = transport.start()
        self.addCleanup(transport.stop)

    def cli(self, *args):
        from xsm import cli
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(args))
        return code, json.loads(out.getvalue())

    def server(self):
        from xsm import mcp
        server = mcp.Server(io.StringIO(), io.StringIO())
        server.session = lambda: self.me
        return server

    def auto_reply(self, home, session, wire):
        from xsm import envelope, receive, send
        request = envelope.parse(wire)
        self.transport.side_effect = None
        receive.take_inbox(self.peer)
        reply = send.send("ref:" + self.me["ref"], "actual-reply-token", sender=self.peer,
                          kind="reply", reply_to=request.header["id"], outcome="succeeded")
        self.assertEqual(reply.status, "sent-unconfirmed")

    def seed_note(self):
        from xsm import config, envelope, inbox
        scope, _ = config.scope_for(self.peer, self.me)
        wire = envelope.build("unrelated-note", msg_id="note-other", sender=self.peer, scope=scope)
        inbox.keep("me", "note-other", wire)

    def test_pending_view_unions_exact_endpoint_ids_without_claiming_and_ACK_clears(self):
        from xsm import handoff, inbox, receive, registry, send
        sent = send.send('ref:' + self.me['ref'], 'canonical only', sender=self.peer, wake=False)
        before = handoff.status(self.me, sent.msg_id)
        self.assertEqual(inbox.pending_status(self.me)['count'], 1)
        inbox.keep('me', sent.msg_id, before['message']['content'], receiver=self.me)
        self.assertEqual(inbox.pending_status(self.me)['count'], 1, 'canonical/export deduplicate by ID')
        foreign = registry.upsert('codex', self.home + '-other', 'me', os.getpid(), self.tmp, name='other-home')
        self.assertEqual(inbox.pending_status(foreign)['count'], 0)
        self.assertEqual(handoff.status(self.me, sent.msg_id), before)
        pack = receive.take_inbox_claims(self.me)
        receive.ack_inbox(self.me, [c['token'] for c in pack['claims']])
        # Even a stale compatibility export must not resurrect an ACKed ID.
        inbox.keep('me', sent.msg_id, before['message']['content'], receiver=self.me)
        self.assertEqual(inbox.pending_status(self.me)['count'], 0)

    def test_cli_and_MCP_wait_return_on_canonical_arrival_not_deadline(self):
        import threading, time
        from xsm import send
        for surface in ('cli', 'mcp'):
            with self.subTest(surface=surface):
                errors = []
                def arrive():
                    try:
                        send.send('ref:' + self.me['ref'], 'arrived canonical', sender=self.peer, wake=False)
                    except Exception as exc: errors.append(type(exc).__name__)
                worker = threading.Timer(.1, arrive); worker.start()
                started = time.monotonic()
                if surface == 'cli':
                    _, result = self.cli('inbox', '--wait', '3', '--json')
                    self.cli('ack', *[c['token'] for c in result['claims']])
                else:
                    server = self.server()
                    server.pump = lambda: True
                    result = json.loads(server.call('xsm_inbox', {'wait': 3}))
                    server.call('xsm_ack', {'tokens': [c['token'] for c in result['claims']]})
                worker.join()
                self.assertFalse(errors)
                self.assertLess(time.monotonic() - started, 2, 'canonical arrival wakes the existing bounded wait')
                self.assertEqual(len(result['claims']), 1)

    def test_canonical_pending_is_reported_without_claiming_unrelated_question(self):
        from xsm import handoff, send
        incoming = send.send('ref:' + self.me['ref'], 'peer question', sender=self.peer, kind='task', wake=False)
        before = handoff.status(self.me, incoming.msg_id)
        answer = json.loads(self.server().call('xsm_ask', {'target': 'ref:' + self.peer['ref'], 'text': 'my question'}))
        self.assertEqual(answer['inbox_pending'], 1)
        self.assertIn('inbox', answer['inbox_notice'])
        self.assertEqual(handoff.status(self.me, incoming.msg_id), before)

    def test_pending_counter_failure_keeps_real_answer_and_reports_unknown_not_zero(self):
        from xsm import handoff
        self.transport.side_effect = self.auto_reply
        with mock.patch.object(handoff, 'pending_ids', side_effect=OSError('unreadable count'), create=True):
            answer = json.loads(self.server().call('xsm_ask', {'target': 'ref:' + self.peer['ref'], 'text': 'answer survives', 'wait': 1}))
        self.assertTrue(answer['final'])
        self.assertEqual(answer['replies'][0]['body'], 'actual-reply-token')
        self.assertIsNone(answer['inbox_pending'])
        self.assertTrue(answer['inbox_pending_diagnostics'])

    def test_CLI_count_failure_does_not_print_a_false_empty_inbox(self):
        from xsm import cli, handoff
        output = io.StringIO()
        with mock.patch.object(handoff, 'pending_ids', side_effect=OSError('counter unavailable')), \
                contextlib.redirect_stdout(output):
            code = cli.main(['inbox'])
        self.assertEqual(code, 0)
        self.assertIn('pending count unknown', output.getvalue())
        self.assertNotIn('(no messages waiting)', output.getvalue())

    def test_internal_MCP_route_is_passive_without_mutating_logical_wake(self):
        from xsm import handoff, receive, send
        sent = send.send('ref:' + self.me['ref'], 'MCP route', sender=self.peer)
        original = handoff.status(self.me, sent.msg_id)
        handoff.delivery(self.me, sent.msg_id, 'pending', route='mcp-inbox')
        pack = receive.take_inbox_claims(self.me, passive_only=True)
        self.assertEqual([c['id'] for c in pack['claims']], [sent.msg_id])
        after = handoff.status(self.me, sent.msg_id)
        self.assertEqual(after['identity'], original['identity'])
        self.assertEqual(after['digest'], original['digest'])
        self.assertEqual(after['message']['wake'], original['message']['wake'])

    def test_wait_pumps_cancel_without_claim_and_original_can_be_recovered(self):
        from xsm import handoff, send
        server = self.server(); server.active_request = 'waiting-inbox'
        sent = []
        def cancel():
            sent.append(send.send('ref:' + self.me['ref'], 'cancel boundary', sender=self.peer, wake=False))
            server.cancelled.add('waiting-inbox')
            return True
        server.pump = cancel
        with self.assertRaisesRegex(Exception, 'cancel|closed'):
            server.call('xsm_inbox', {'wait': 3})
        self.assertEqual(handoff.status(self.me, sent[0].msg_id)['status'], 'pending')
        fresh = self.server()
        pack = json.loads(fresh.call('xsm_inbox', {}))
        self.assertEqual([c['id'] for c in pack['claims']], [sent[0].msg_id])

    def test_pending_count_preserves_live_dead_and_expired_lease_records(self):
        from xsm import handoff, inbox, send
        sent = send.send('ref:' + self.me['ref'], 'leased original', sender=self.peer, wake=False)
        handoff.claim(self.me, {'type': 'native', 'id': 'another-reader'}, 'other-generation', message_id=sent.msg_id)
        before = handoff.status(self.me, sent.msg_id)
        self.assertEqual(inbox.pending_status(self.me, owner_alive=lambda *a: True)['count'], 0)
        self.assertEqual(inbox.pending_status(self.me, owner_alive=lambda *a: False)['count'], 1)
        with mock.patch.object(handoff, '_monotonic', return_value=before['claim']['deadline_mono']):
            self.assertEqual(inbox.pending_status(self.me, owner_alive=lambda *a: True)['count'], 1)
        self.assertEqual(handoff.status(self.me, sent.msg_id), before, 'count never recovers or renews a lease')

    def test_pending_excludes_failed_delivery_and_foreign_runtime_exports(self):
        from xsm import handoff, inbox, send
        for delivery in ('error', 'held', 'refused'):
            sent = send.send('ref:' + self.me['ref'], 'failed ' + delivery, sender=self.peer)
            handoff.delivery(self.me, sent.msg_id, delivery)
        self.assertEqual(inbox.pending_status(self.me)['count'], 0)
        sent = send.send('ref:' + self.me['ref'], 'codex only', sender=self.peer, wake=False)
        row = handoff.status(self.me, sent.msg_id)
        inbox.keep('me', sent.msg_id, row['message']['content'], receiver=self.me)
        self.assertEqual(inbox.pending_status(dict(self.me, runtime='claude'))['count'], 0)

    def test_pending_notice_uses_cached_caller_without_another_registry_lookup(self):
        from xsm import cli, registry, send
        send.send('ref:' + self.me['ref'], 'counted without lookup', sender=self.peer, wake=False)
        err = io.StringIO()
        with mock.patch.object(registry, 'me', side_effect=AssertionError('extra caller lookup')), contextlib.redirect_stderr(err):
            cli._inbox_notice('ledger')
        self.assertIn('1 message', err.getvalue())

    def test_actual_Server_inbox_wait_dispatches_ping_cancel_and_EOF_without_claim(self):
        import threading
        from xsm import handoff, mcp, send
        for boundary in ('cancel', 'eof'):
            with self.subTest(boundary=boundary):
                frames = ([{'id': 'ping', 'method': 'ping'}, {'method': 'notifications/cancelled',
                          'params': {'requestId': 'wait'}}] if boundary == 'cancel' else [])
                output = io.StringIO()
                server = mcp.Server(io.StringIO(''.join(json.dumps(f) + '\n' for f in frames)), output)
                server.session = lambda: self.me
                sent = []
                def arrive(): sent.append(send.send('ref:' + self.me['ref'], boundary + ' original', sender=self.peer, wake=False))
                timer = threading.Timer(.05, arrive); timer.start()
                server.dispatch({'id': 'wait', 'method': 'tools/call', 'params': {
                    'name': 'xsm_inbox', 'arguments': {'wait': 3}}})
                timer.join()
                results = [json.loads(line) for line in output.getvalue().splitlines()]
                if boundary == 'cancel': self.assertEqual(results[0]['id'], 'ping')
                self.assertTrue(next(v for v in results if v['id'] == 'wait')['result']['isError'])
                self.assertEqual(handoff.status(self.me, sent[0].msg_id)['status'], 'pending')

    def test_answer_claims_allow_exact_ack_without_extra_inbox_on_all_public_surfaces(self):
        from xsm import handoff, receive, send
        for surface in ('cli-ask', 'cli-status', 'cli-connect', 'mcp-ask', 'mcp-status', 'mcp-connect'):
            with self.subTest(surface=surface):
                unrelated = send.send('ref:' + self.me['ref'], 'unrelated passive', sender=self.peer, wake=False)
                before = handoff.status(self.me, unrelated.msg_id)
                self.transport.side_effect = self.auto_reply
                server = self.server()
                if surface.startswith('cli'):
                    command = 'connect' if surface.endswith('connect') else 'ask'
                    args = [command, 'ref:' + self.peer['ref']]
                    if command == 'ask': args += ['--text', surface]
                    _, answer = self.cli(*args, '--wait', '1')
                else:
                    command = 'xsm_connect' if surface.endswith('connect') else 'xsm_ask'
                    args = {'target': 'ref:' + self.peer['ref'], 'wait': 1}
                    if command == 'xsm_ask': args['text'] = surface
                    answer = json.loads(server.call(command, args))
                if surface.endswith('status'):
                    # Release the first output's unconfirmed claim; status must
                    # offer the exact reply without another inbox read.
                    receive.release_inbox(self.me, [c['token'] for c in answer['claims']])
                    if surface.startswith('cli'):
                        _, answer = self.cli('question-status', answer['id'])
                    else:
                        answer = json.loads(server.call('xsm_question_status', {'id': answer['id']}))
                ids = [r['id'] for r in answer['replies']]
                self.assertEqual([c['id'] for c in answer['claims']], ids)
                self.assertEqual(handoff.status(self.me, unrelated.msg_id), before)
                for claim in answer['claims']:
                    self.assertEqual(claim['digest'], handoff.status(self.me, claim['id'])['digest'])
                with mock.patch.object(receive, 'take_inbox_claims', side_effect=AssertionError('extra inbox')):
                    if surface.startswith('cli'):
                        _, ack = self.cli('ack', *[c['token'] for c in answer['claims']])
                    else:
                        ack = json.loads(server.call('xsm_ack', {'tokens': [c['token'] for c in answer['claims']]}))
                self.assertEqual(ack['acked'], ids)
                again = json.loads(server.call('xsm_question_status', {'id': answer['id']}))
                self.assertEqual(again['replies'], answer['replies'])
                self.assertEqual(again['claims'], [])
                self.assertEqual(handoff.status(self.me, unrelated.msg_id), before)

    def test_cli_answer_print_failure_releases_exact_reply_claim(self):
        from xsm import cli, handoff, questions
        self.transport.side_effect = self.auto_reply
        with mock.patch('builtins.print', side_effect=BrokenPipeError('closed output')):
            with self.assertRaises(BrokenPipeError):
                cli.main(['ask', 'ref:' + self.peer['ref'], '--text', 'print failure', '--wait', '1'])
        request = questions.list_requests(self.me)[0]
        answer = questions.status(self.me, request['id'])
        self.assertEqual(handoff.status(self.me, answer['replies'][0]['id'])['status'], 'pending')

    def test_reply_claim_failure_preserves_verified_answer_and_recovery(self):
        from xsm import handoff, receive
        self.transport.side_effect = self.auto_reply
        _, original = self.cli('ask', 'ref:' + self.peer['ref'], '--text', 'retain answer', '--wait', '1')
        receive.release_inbox(self.me, [c['token'] for c in original['claims']])
        with mock.patch.object(receive, 'take_inbox_claims', side_effect=OSError('copy store unavailable')):
            _, answer = self.cli('question-status', original['id'])
        self.assertTrue(answer['final'])
        self.assertEqual(answer['replies'][0]['body'], 'actual-reply-token')
        self.assertEqual(answer['claims'], [])
        self.assertTrue(answer['claim_diagnostics'])
        self.assertEqual(answer['recover_at']['cli'][-1], answer['id'])
        self.assertEqual(handoff.status(self.me, answer['replies'][0]['id'])['status'], 'pending')

    def test_cached_only_reply_is_visible_without_manufacturing_a_canonical_claim(self):
        from xsm import questions
        request = questions.ask(self.me, 'ref:' + self.peer['ref'], 'legacy')
        questions.record_reply(self.me, self.peer, {'id': 'legacy-reply', 'kind': 'reply',
            'reply-to': request['id'], 'outcome': 'succeeded'}, 'legacy answer')
        _, answer = self.cli('question-status', request['id'])
        self.assertEqual(answer['replies'][0]['body'], 'legacy answer')
        self.assertEqual(answer['claims'], [])
        self.assertTrue(answer['claim_diagnostics'])

    def test_reply_handoff_rechecks_owner_generation_digest_and_receive_policy(self):
        from xsm import handoff, questions, receive, send
        request = questions.ask(self.me, 'ref:' + self.peer['ref'], 'bound answer')
        reply = send.send('ref:' + self.me['ref'], 'checked original', sender=self.peer,
                          kind='reply', reply_to=request['id'], outcome='succeeded', wake=False)
        receive.poll_replies(self.me, request['id'])
        answer = questions.status(self.me, request['id'])
        with mock.patch.object(receive, 'check', return_value=('block', 'traffic fixture limit')):
            blocked = receive.claim_question_replies(self.me, answer)
        self.assertEqual(blocked['claims'], [])
        self.assertEqual(blocked['replies'], answer['replies'])
        self.assertTrue(blocked['claim_diagnostics'])
        # Restore only the test's held delivery state for the next independent boundary.
        from xsm import ledger
        ledger.receipt(reply.msg_id, 'delivered', self.me)
        handoff.delivery(self.me, reply.msg_id, 'delivered')
        with mock.patch.object(handoff, 'status', wraps=handoff.status) as read:
            row = handoff.status(self.me, reply.msg_id)
            row['digest'] = '0' * 64
            read.return_value = row
            invalid = receive.claim_question_replies(self.me, answer)
        self.assertEqual(invalid['claims'], [])
        self.assertEqual(invalid['replies'], answer['replies'])
        offered = receive.claim_question_replies(self.me, answer)
        claim = offered['claims'][0]
        for owner, generation in ((dict(claim['owner'], id='different'), claim['generation']),
                                  (claim['owner'], 'different-generation')):
            with self.assertRaises(ValueError):
                receive.ack_inbox(self.me, [claim['token']], owner=owner, generation=generation)
        foreign = dict(self.me, home=self.home + '-other')
        self.assertEqual(receive.claim_question_replies(foreign, answer)['claims'], [])
        self.assertEqual(receive.ack_inbox(self.me, [claim['token']])['acked'], [reply.msg_id])

    def test_filtered_answers_leave_even_expired_unrelated_claims_and_other_partial_replies_untouched(self):
        from xsm import handoff, questions, receive, send
        unrelated = send.send('ref:' + self.me['ref'], 'unrelated', sender=self.peer, wake=False)
        with mock.patch.object(handoff, '_monotonic', return_value=0):
            handoff.claim(self.me, {'type': 'native', 'id': 'other-reader'}, 'older-generation',
                          message_id=unrelated.msg_id)
        before = handoff.status(self.me, unrelated.msg_id)
        request = questions.ask(self.me, 'ref:' + self.peer['ref'], 'partial question')
        ids = []
        for body, outcome in (('first part', None), ('final part', 'succeeded')):
            ids.append(send.send('ref:' + self.me['ref'], body, sender=self.peer,
                kind='reply', reply_to=request['id'], outcome=outcome, wake=False).msg_id)
        receive.poll_replies(self.me, request['id'])
        self.assertEqual(handoff.status(self.me, ids[0])['status'], 'pending', 'poll must stay non-consuming')
        self.assertEqual(receive.take_inbox_claims(self.me, message_ids=[]), {'messages': [], 'claims': []})
        _, answer = self.cli('question-status', request['id'])
        self.assertEqual({c['id'] for c in answer['claims']}, set(ids))
        self.assertEqual(handoff.status(self.me, unrelated.msg_id), before)

    def test_mcp_answer_cancel_or_output_failure_releases_its_handoff_call(self):
        from xsm import handoff, questions
        for cancelled in (False, True):
            with self.subTest(cancelled=cancelled):
                server = self.server()
                self.transport.side_effect = self.auto_reply
                if cancelled:
                    def write(payload):
                        self.assertTrue(payload['result']['isError'])
                    original = server.call
                    def call(*args, **kwargs):
                        result = original(*args, **kwargs)
                        server.cancelled.add('call-ack')
                        return result
                    server.call = call
                else:
                    def write(payload): raise BrokenPipeError('closed MCP output')
                server.send = write
                packet = {'id': 'call-ack', 'method': 'tools/call', 'params': {
                    'name': 'xsm_ask', 'arguments': {'target': 'ref:' + self.peer['ref'],
                    'text': 'cancelled output' if cancelled else 'failed output', 'wait': 1}}}
                if cancelled: server.dispatch(packet)
                else:
                    with self.assertRaises(BrokenPipeError): server.dispatch(packet)
                for request in questions.list_requests(self.me):
                    for reply in questions.status(self.me, request['id'])['replies']:
                        self.assertEqual(handoff.status(self.me, reply['id'])['status'], 'pending')

    def test_cli_returns_real_answer_and_wait_does_not_consume_other_inbox(self):
        from xsm import inbox
        self.seed_note()
        self.transport.side_effect = self.auto_reply
        code, answer = self.cli("ask", "ref:" + self.peer["ref"], "--text", "question",
                                "--wait", "1")
        self.assertEqual(code, 0)
        self.assertEqual(answer["replies"][0]["body"], "actual-reply-token")
        self.assertTrue(answer["final"])
        self.assertEqual(answer["wait_end_reason"], "reply")
        self.assertEqual(inbox.count("me"), 1, "only the returned answer is handed off; unrelated note survives")

    def test_mcp_reuses_the_same_reply_contract_and_json_stays_parseable(self):
        self.transport.side_effect = self.auto_reply
        result = json.loads(self.server().call("xsm_ask", {
            "target": "ref:" + self.peer["ref"], "text": "question", "wait": 1}))
        self.assertEqual(result["replies"][0]["body"], "actual-reply-token")
        self.assertEqual(result["wait_end_reason"], "reply")
        self.assertEqual(result["inbox_pending"], 0)
        status = json.loads(self.server().call("xsm_question_status", {"id": result["id"]}))
        self.assertEqual(status["replies"], result["replies"])
        self.assertEqual(status['claims'], result['claims'], 'same consumer recovers the existing token without another inbox')

    def test_permission_and_delivery_receipt_do_not_complete_handshake(self):
        from xsm import ledger
        code, result = self.cli("connect", "ref:" + self.peer["ref"])
        self.assertEqual(code, 3)
        self.assertEqual(result["handshake"], "pending")
        ledger.receipt(result["id"], "delivered", self.peer)
        code, still = self.cli("question-status", result["id"])
        self.assertEqual(code, 3)
        self.assertEqual(still["handshake"], "pending")
        self.assertEqual(still["replies"], [])

    def test_actual_peer_response_completes_handshake_and_timeout_id_is_reusable(self):
        self.transport.side_effect = self.auto_reply
        code, result = self.cli("connect", "ref:" + self.peer["ref"], "--wait", "1")
        self.assertEqual(code, 0)
        self.assertEqual(result["handshake"], "completed")
        before = self.transport.call_count
        code, repeated = self.cli("connect", "ref:" + self.peer["ref"], "--request-id", result["id"])
        self.assertEqual(code, 0)
        self.assertEqual(repeated["id"], result["id"])
        self.assertEqual(self.transport.call_count, before)

    def test_invalid_attachment_and_wake_mode_are_explicit_in_both_surfaces(self):
        from xsm import cli, mcp
        for flag in (["--attachment", "a.txt"], ["--wake", "now"]):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(["ask", "ref:" + self.peer["ref"], "--text", "q", *flag]), 2)
        for field in ({"attachments": ["a.txt"]}, {"wake": "now"}):
            with self.assertRaisesRegex(mcp.ToolError, "unsupported|attachment-error"):
                self.server().call("xsm_ask", {"target": "ref:" + self.peer["ref"], "text": "q", **field})
        self.assertEqual(self.transport.call_count, 0)

    def test_passive_question_uses_the_same_cli_mcp_id_without_transport(self):
        from xsm import receive
        code,result=self.cli('ask','ref:'+self.peer['ref'],'--text','quiet question','--wake','never')
        self.assertEqual(code,3)
        self.assertEqual(result['send_evidence']['status'],'stored')
        self.assertEqual(result['wake'],'never')
        again=json.loads(self.server().call('xsm_ask',{'target':'ref:'+self.peer['ref'],
                         'text':'quiet question','wake':'never','request_id':result['id']}))
        self.assertEqual(again['id'],result['id'])
        self.assertEqual(self.transport.call_count,0)
        self.assertIn('quiet question',receive.take_inbox_claims(self.peer)['messages'][0])

    def test_question_wait_reads_a_passive_canonical_reply_without_an_extra_inbox_call(self):
        from xsm import receive,send
        code,result=self.cli('ask','ref:'+self.peer['ref'],'--text','quiet request','--wake','never')
        self.assertEqual(code,3)
        receive.take_inbox_claims(self.peer)
        reply=send.send('ref:'+self.me['ref'],'quiet actual answer',sender=self.peer,
                       kind='reply',reply_to=result['id'],outcome='succeeded',wake=False)
        self.assertEqual(reply.status,'stored')
        answer=json.loads(self.server().call('xsm_question_status',{'id':result['id'],'wait':.05}))
        self.assertTrue(answer['final'])
        self.assertEqual(answer['replies'][0]['body'],'quiet actual answer')

    def test_mcp_recovers_when_an_older_hook_consumes_the_native_copy_first(self):
        from xsm import inbox, receive
        def older_hook(home, session, wire):
            self.auto_reply(home, session, wire)
            with mock.patch.object(receive, "_index_reply", return_value=False):
                self.assertEqual(len(receive.take_inbox(self.me)), 1)
            self.assertEqual(inbox.count("me"), 0)
        self.transport.side_effect = older_hook
        result = json.loads(self.server().call("xsm_ask", {
            "target": "ref:" + self.peer["ref"], "text": "question", "wait": 1}))
        self.assertEqual(result["replies"][0]["body"], "actual-reply-token")
        self.assertEqual(inbox.reply_copies(self.me, result["id"]), [],
                         "only the redundant cache is removed after the index persists")

    def test_queued_reply_cache_failure_does_not_claim_the_message_was_unsent(self):
        from xsm import inbox, questions, send
        request = questions.ask(self.me, "ref:" + self.peer["ref"], "question")
        with mock.patch.object(inbox, "keep_reply", side_effect=OSError("disk full")):
            reply = send.send("ref:" + self.me["ref"], "reply", sender=self.peer,
                              kind="reply", reply_to=request["id"])
        self.assertEqual(reply.status, "sent-unconfirmed")
        self.assertTrue(reply.msg_id)
        self.assertTrue(any("recovery copy" in note for note in reply.notes))

    def test_blocked_receipt_is_not_bypassed_by_a_saved_reply_copy(self):
        from xsm import ledger, questions, receive, send
        request = questions.ask(self.me, "ref:" + self.peer["ref"], "question")
        reply = send.send("ref:" + self.me["ref"], "blocked reply", sender=self.peer,
                          kind="reply", reply_to=request["id"], outcome="succeeded")
        ledger.receipt(reply.msg_id, "blocked", self.me, "fixture refusal")
        receive.poll_replies(self.me, request["id"])
        self.assertEqual(questions.status(self.me, request["id"])["replies"], [])

    def test_provisional_sender_is_not_promoted_into_a_bound_answer(self):
        from xsm import context, inbox, questions, receive, send
        request = questions.ask(self.me, "ref:" + self.peer["ref"], "question")
        weak = context.of_record(self.peer, context.BASIS_NEIGHBOR)
        reply = send.send("ref:" + self.me["ref"], "guessed identity", sender=self.peer,
                          kind="reply", reply_to=request["id"], outcome="succeeded", call=weak)
        self.assertEqual(reply.status, "sent-unconfirmed")
        self.assertEqual(inbox.reply_copies(self.me, request["id"]), [])
        receive.poll_replies(self.me, request["id"])
        self.assertEqual(questions.status(self.me, request["id"])["replies"], [])

    def test_codex_now_priority_and_nonreply_outcome_are_not_silently_ignored(self):
        from xsm import mcp, paths
        code, result = self.cli("ask", "ref:" + self.peer["ref"], "--text", "q", "--priority", "now")
        self.assertEqual(code, 2)
        self.assertIn("unsupported", result["reason"])
        self.assertEqual(self.transport.call_count, 0)
        self.assertFalse(os.path.exists(paths.path("questions")), "unsupported requests are not queued")
        with self.assertRaisesRegex(mcp.ToolError, "outcome"):
            self.server().call("xsm_send", {"target": "ref:" + self.peer["ref"], "text": "q",
                                           "kind": "note", "outcome": "succeeded"})

    def test_claude_now_priority_reaches_the_actual_unix_socket_frame(self):
        import socket, tempfile, threading, time
        from xsm import registry
        folder = tempfile.TemporaryDirectory(prefix="xsm-prio-", dir="/tmp")
        self.addCleanup(folder.cleanup)
        path = os.path.join(folder.name, str(os.getpid()) + ".sock")
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(path);listener.listen(8);listener.settimeout(.1)
        frames=[];stop=threading.Event()
        def accept():
            deadline=time.monotonic()+4
            while not stop.is_set() and time.monotonic()<deadline:
                try:conn,_=listener.accept()
                except socket.timeout:continue
                with conn:
                    data=b""
                    while b"\n" not in data:
                        chunk=conn.recv(65536)
                        if not chunk:break
                        data+=chunk
                    if data:
                        frames.append(json.loads(data))
                        return
        thread=threading.Thread(target=accept,daemon=True);thread.start()
        def cleanup():
            stop.set();thread.join(timeout=1);listener.close()
        self.addCleanup(cleanup)
        home=os.path.join(self.tmp,"claude");os.makedirs(home)
        target=registry.upsert("claude",home,"claude-peer",os.getpid(),self.tmp,
                               name="claude-peer",socket=path)
        result=self.server().call("xsm_send",{"target":"ref:"+target["ref"],"text":"priority probe",
                                              "priority":"now"})
        self.assertIn("sent-unconfirmed",result)
        thread.join(timeout=2)
        self.assertEqual(len(frames),1)
        self.assertEqual(frames[0]["priority"],"now")

    def test_unrelated_peer_cannot_close_the_original_questions_ledger_task(self):
        from xsm import ledger, questions, receive, registry, send
        request = questions.ask(self.me, "ref:" + self.peer["ref"], "question")
        other = registry.upsert("codex", self.home, "other", os.getpid(), self.tmp, name="other")
        sent = send.send("ref:" + self.me["ref"], "wrong peer", sender=other, kind="reply",
                         reply_to=request["id"], outcome="succeeded")
        self.assertEqual(sent.status, "sent-unconfirmed")
        self.assertEqual(len(receive.take_inbox(self.me)), 1, "ordinary peer messages still arrive")
        self.assertEqual(questions.status(self.me, request["id"])["replies"], [])
        self.assertNotIn("outcome", ledger.status(request["id"]))

    def test_missing_id_lists_only_this_callers_requests_in_cli_and_mcp(self):
        from xsm import mcp, questions
        request = questions.ask(self.me, "ref:" + self.peer["ref"], "find after cancellation")
        code, listing = self.cli("question-status")
        self.assertEqual(code, 0)
        self.assertEqual([r["id"] for r in listing["requests"]], [request["id"]])
        own = json.loads(self.server().call("xsm_question_status", {}))
        self.assertEqual([r["id"] for r in own["requests"]], [request["id"]])
        other = self.server();other.session = lambda: self.peer
        self.assertEqual(json.loads(other.call("xsm_question_status", {}))["requests"], [])
        self.assertEqual(self.transport.call_count, 1, "listing cannot execute the task again")
