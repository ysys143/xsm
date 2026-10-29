"""Narrow native capability refusal, with real local storage/receive contracts."""
import os
from unittest import mock

from tests import test_xsm


NATIVE_REFUSAL = ("Error: failed to queue session message: thread/queue/add failed: "
                  "direct app-server input is not allowed for unloaded spawned sub-agents "
                  "(code -32600)")


class SubagentTransportTest(test_xsm.TempState):
    def setUp(self):
        super().setUp()
        from xsm import registry
        home = self.tmp + '/codex'
        os.makedirs(home)
        self.a = registry.upsert('codex', home, 'sender', os.getpid(), self.tmp, name='sender')
        self.b = registry.upsert('codex', home, 'receiver', os.getpid(), self.tmp, name='receiver')
        self.owner = {'type': 'native', 'id': 'real-test-reader'}

    def _native_failure(self, text=NATIVE_REFUSAL):
        from xsm import adapters
        real_delivery = adapters.to_codex
        def fail(*args):
            result = mock.Mock(returncode=1, stdout='', stderr=text)
            with mock.patch.object(adapters, 'codex_bins', return_value=['/fixture/codex']), \
                    mock.patch.object(adapters.subprocess, 'run', return_value=result):
                return real_delivery(*args)
        return mock.patch.object(adapters, 'to_codex', side_effect=fail)

    def _take(self, me=None, **kwargs):
        from xsm import receive
        return receive.take_inbox_claims(me or self.b, owner=self.owner, generation='generation', **kwargs)

    def test_exact_native_refusal_is_typed_without_direct_write_or_wake(self):
        from xsm import adapters
        for prefix in ('', 'Error: failed to queue session message: thread/queue/add failed: '):
            text = prefix + 'direct app-server input is not allowed for unloaded spawned sub-agents (code -32600)'
            result = mock.Mock(returncode=1, stdout='', stderr=text)
            with self.subTest(prefix=prefix), \
                    mock.patch.object(adapters, 'codex_bins', return_value=['/fixture/codex']), \
                    mock.patch.object(adapters.subprocess, 'run', return_value=result), \
                    mock.patch.object(adapters, 'queue_direct') as direct, \
                    mock.patch.object(adapters, 'wake_codex') as wake:
                with self.assertRaises(adapters.UnsupportedCapability) as cm:
                    adapters.to_codex(self.b['home'], 'receiver', 'wire')
                self.assertEqual(cm.exception.reason, 'unsupported-capability')
                self.assertEqual(cm.exception.capability, adapters.UNLOADED_SUBAGENT_INPUT)
                direct.assert_not_called()
                wake.assert_not_called()

    def test_fallback_preserves_full_request_and_honest_evidence(self):
        from xsm import envelope, handoff, inbox, ledger, send
        body = 'original\r\n' + 'x' * 240
        with self._native_failure():
            result = send.send('codex:receiver', body, sender=self.a, kind='task', msg_id='same-id')
        self.assertEqual(result.status, 'stored', result.reason)
        record = handoff.status(self.b, 'same-id')
        self.assertEqual(record['delivery_route'], 'mcp-inbox')
        self.assertEqual(record['delivery_state'], 'pending')
        self.assertEqual(record['message']['body'], body)
        self.assertIs(record['message']['wake'], True)
        self.assertNotIn('delivery_route', record['message'])
        identity = envelope.request_identity('same-id', self.a, self.b, body, kind='task',
                                            scope=record['message']['scope'], priority='next')
        self.assertEqual(record['digest'], envelope.request_digest(identity))
        evidence = ledger.evidence_of('same-id')
        self.assertTrue(evidence['steps']['stored']['ok'])
        self.assertFalse(evidence['steps']['queued']['ok'])
        self.assertFalse(evidence['steps']['wake']['ok'])
        self.assertFalse(evidence['runtime_reached'])
        self.assertFalse(evidence['acknowledged'])
        self.assertEqual(inbox.count('receiver'), 1)
        self.assertEqual(handoff.pending_ids(self.b), ['same-id'])

    def test_legacy_auto_export_survives_fallback_and_is_not_a_consumption_ACK(self):
        from xsm import handoff, inbox, ledger, paths, send
        with self._native_failure():
            result = send.send('codex:receiver', 'legacy pull copy', sender=self.a)
        filename = paths.path('inbox', 'receiver', result.msg_id+'.json')
        export = paths.read_json(filename)
        self.assertIsInstance(export, dict)
        self.assertEqual(export['id'], result.msg_id)
        self.assertEqual(export['receiver'], handoff._identity(self.b))
        self.assertNotIn('queued_id', export)
        original = handoff.status(self.b, result.msg_id)
        # An old destructive reader may remove its export. That is not new
        # runtime/consumption evidence and never removes the canonical original.
        os.unlink(filename)
        self.assertEqual(handoff.status(self.b, result.msg_id), original)
        self.assertEqual(handoff.pending_ids(self.b), [result.msg_id])
        self.assertFalse(ledger.evidence_of(result.msg_id)['acknowledged'])
        self.assertFalse(ledger.evidence_of(result.msg_id)['runtime_reached'])

    def test_fallback_actual_receive_ack_and_correlated_reply(self):
        import json
        from xsm import context, handoff, mcp, questions, send

        def server_for(me):
            server = mcp.Server()
            server._resolve = mock.Mock(return_value=(me, context.BASIS_THREAD, ('exact test native record',)))
            return server

        with self._native_failure():
            requested = questions.ask(self.a, 'codex:receiver', 'review 2+2=5', request_id='question')
        self.assertEqual(requested['status'], 'pending', requested)
        original = handoff.status(self.b, 'question')
        receiver = server_for(self.b)
        pack = json.loads(receiver.call('xsm_inbox', {}))
        self.assertEqual([c['id'] for c in pack['claims']], ['question'])
        ack = json.loads(receiver.call('xsm_ack', {'tokens': [pack['claims'][0]['token']]}))
        self.assertEqual(ack['acked'], ['question'])
        self.assertEqual(self._take(), {'messages': [], 'claims': []})
        with self._native_failure():
            reply = send.send('codex:sender', '2+2=4', sender=self.b, kind='reply',
                              reply_to='question', outcome='succeeded', msg_id='answer')
        self.assertEqual(reply.status, 'stored', reply.reason)
        sender = server_for(self.a)
        answer = json.loads(sender.call('xsm_inbox', {}))
        self.assertEqual([c['id'] for c in answer['claims']], ['answer'])
        sender.call('xsm_ack', {'tokens': [answer['claims'][0]['token']]})
        result = questions.status(self.a, 'question')
        self.assertEqual(result['status'], 'final')
        self.assertEqual(result['final_outcome'], 'succeeded')
        self.assertEqual(len(result['replies']), 1)
        current = handoff.status(self.b, 'question')
        self.assertEqual(current['digest'], original['digest'])
        self.assertEqual(current['message'], original['message'])

    def test_fallback_reply_keeps_recovery_cache_and_delivery_wait(self):
        from xsm import handoff, inbox, ledger, questions, send
        with self._native_failure():
            questions.ask(self.a, 'codex:receiver', 'review', request_id='wait-question')
        for status in ('delivered', 'held', 'blocked', 'queued'):
            mid = 'wait-reply-' + status
            receipt = {'status': status, 'receipt': {'reason': 'actual receiver fixture'}}
            with self.subTest(status=status), self._native_failure(), \
                    mock.patch.object(ledger, 'wait_for', return_value=receipt) as waiting:
                result = send.send('codex:sender', 'answer', sender=self.b, kind='reply',
                                   reply_to='wait-question', msg_id=mid, wait=7.5)
                waiting.assert_called_once_with(mid, 7.5)
                self.assertEqual(result.status, status if status != 'queued' else 'stored')
                cached = inbox.reply_copies(self.a, 'wait-question')
                self.assertTrue(any(item['id'] == mid for item in cached))
                original = handoff.status(self.a, mid)
                self.assertEqual(original['delivery_route'], 'mcp-inbox')
                self.assertIs(original['message']['wake'], True)

    def test_no_broad_error_fallback(self):
        from xsm import handoff, send
        for index, text in enumerate(('Error: invalid input (code -32600)',
                NATIVE_REFUSAL + '\nPermission denied',
                'Permission denied: ' + NATIVE_REFUSAL,
                NATIVE_REFUSAL.replace('-32600', '-32601'),
                'Error: readonly database', 'Error: Operation not permitted',
                'Error: scope refused', 'unknown failure')):
            with self.subTest(text=text), self._native_failure(text):
                result = send.send('codex:receiver', 'work', sender=self.a, msg_id='bad%d' % index)
            self.assertEqual(result.status, 'error')
            record = handoff.status(self.b, result.msg_id)
            self.assertEqual(record['delivery_route'], 'native')
            self.assertEqual(record['delivery_state'], 'error')
            self.assertNotIn(result.msg_id, handoff.pending_ids(self.b))

    def test_string_reason_alone_and_non_codex_cannot_select_fallback(self):
        from xsm import adapters, handoff, send
        with mock.patch.object(adapters, 'to_codex', side_effect=adapters.DeliveryError('unsupported-capability', NATIVE_REFUSAL)):
            result = send.send('codex:receiver', 'work', sender=self.a, msg_id='untyped')
        self.assertEqual(result.status, 'error')
        self.assertEqual(handoff.status(self.b, 'untyped')['delivery_state'], 'error')

        with mock.patch.object(adapters, 'to_codex', side_effect=adapters.UnsupportedCapability('other-capability', NATIVE_REFUSAL)):
            other = send.send('codex:receiver', 'work', sender=self.a, msg_id='other-capability')
        self.assertEqual(other.status, 'error')
        self.assertEqual(handoff.status(self.b, other.msg_id)['delivery_state'], 'error')

    def test_real_queue_with_not_loaded_wake_stays_native_unconfirmed(self):
        from xsm import adapters, handoff, ledger, send
        value = adapters.Queued('Queued message queue-id for thread receiver.')
        value.wake = 'not-loaded'
        with mock.patch.object(adapters, 'to_codex', return_value=value):
            result = send.send('codex:receiver', 'work', sender=self.a, msg_id='not-loaded')
        self.assertEqual(result.status, 'sent-unconfirmed')
        self.assertEqual(handoff.status(self.b, 'not-loaded')['delivery_route'], 'native')
        evidence = ledger.evidence_of('not-loaded')
        self.assertTrue(evidence['steps']['queued']['ok'])
        self.assertFalse(evidence['steps']['wake']['ok'])
        self.assertFalse(evidence['runtime_reached'])

    def test_explicit_never_route_keeps_logical_wake_false(self):
        from xsm import adapters, handoff, ledger, send
        with mock.patch.object(adapters, 'to_codex') as native, \
                mock.patch.object(ledger, 'wait_for') as waiting:
            result = send.send('codex:receiver', 'quiet', sender=self.a, wake=False, wait=7.5)
        native.assert_not_called()
        waiting.assert_not_called()
        self.assertEqual(result.status, 'stored')
        record = handoff.status(self.b, result.msg_id)
        self.assertEqual(record['delivery_route'], 'mcp-inbox')
        self.assertIs(record['message']['wake'], False)

    def test_scope_revoked_after_fallback_is_checked_before_body_handoff(self):
        from xsm import config, handoff, send
        with self._native_failure():
            result = send.send('codex:receiver', 'private-secret', sender=self.a)
        config.set_value('same_repo_scope', False)
        pack = self._take()
        self.assertEqual(pack['claims'], [])
        self.assertNotIn('private-secret', '\n'.join(pack['messages']))
        self.assertEqual(handoff.status(self.b, result.msg_id)['delivery_state'], 'held')
        self.assertEqual(handoff.pending_ids(self.b), [])

    def test_denied_before_send_never_attempts_transport(self):
        from xsm import adapters, config, send
        config.block(self.b['ref'])
        with mock.patch.object(adapters, 'to_codex') as native:
            result = send.send('codex:receiver', 'work', sender=self.a)
        self.assertEqual(result.status, 'refused')
        native.assert_not_called()

    def test_native_gate_block_receipt_is_not_pending_without_mutating_original(self):
        from pathlib import Path
        from xsm import adapters, envelope, handoff, inbox, ledger, paths, receive, send
        for held in (True, False):
            with self.subTest(held=held):
                mid = 'gate-held' if held else 'gate-blocked'
                queued = adapters.Queued('Queued message queue-id for thread receiver.')
                queued.wake = 'started'
                with mock.patch.object(adapters, 'to_codex', return_value=queued):
                    sent = send.send('codex:receiver', 'preserved original '+mid,
                                     sender=self.a, kind='task', msg_id=mid)
                self.assertEqual(sent.status, 'sent-unconfirmed')
                original = handoff.status(self.b, mid)
                self.assertEqual(original['delivery_state'], 'pending')
                export = Path(paths.path('inbox', 'receiver', mid+'.json'))
                self.assertTrue(export.exists())
                real_write = paths.write_json
                def write(path, value):
                    if not held and str(Path(path).parent) == paths.path(paths.HELD):
                        raise OSError('fixture held store unavailable')
                    return real_write(path, value)
                with mock.patch.object(receive, 'check', return_value=('block', 'scope denied')), \
                        mock.patch.object(receive, '_tell_held'), \
                        mock.patch.object(paths, 'write_json', side_effect=write):
                    receive._gate({'session_id': 'receiver', 'cwd': self.tmp}, 'codex',
                                  self.b, envelope.parse(original['message']['content']))
                self.assertEqual(ledger.receipt_of(mid)['decision'], 'held' if held else 'blocked')
                self.assertFalse(export.exists())
                self.assertEqual(handoff.status(self.b, mid), original)
                before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_ino)
                          for p in Path(self.tmp).rglob('*') if p.is_file()}
                with mock.patch.object(handoff, '_write', side_effect=AssertionError('read-only')):
                    self.assertEqual(handoff.pending_ids(self.b), [])
                    self.assertEqual(inbox.pending_status(self.b),
                                     {'count': 0, 'known_count': 0, 'diagnostics': []})
                    self.assertEqual(inbox.pending_fields(self.b), {'inbox_pending': 0})
                after = {str(p): (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_ino)
                         for p in Path(self.tmp).rglob('*') if p.is_file()}
                self.assertEqual(after, before)
                self.assertEqual(self._take(), {'messages': [], 'claims': []})
                self.assertEqual(handoff.status(self.b, mid), original)
