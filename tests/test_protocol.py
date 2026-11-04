"""Public protocol behavior, using real canonical storage and isolated homes."""
import io
import json
import os
import sys
import time
from unittest import mock

from tests.test_xsm import TempState


class ProtocolFixture(TempState):
    def setUp(self):
        super().setUp()
        from xsm.protocol import Connection
        self.connection = Connection()
        self.addCleanup(self.connection.close)
        self.connection.dispatch("initialize", {"protocolVersion": "1"})

    def tearDown(self):
        self.connection.close()
        super().tearDown()

    def open(self, conversation="a", profile="p", runtime="fixture"):
        return self.connection.dispatch("session.open", {
            "runtime": runtime, "profile": profile,
            "conversation": conversation, "cwd": self.tmp,
            "capabilities": ["messaging", "inbox", "events"]})

    def operation(self, session, name, **args):
        return self.connection.dispatch("operation.call", {
            "session": session["session"], "operation": name, "arguments": args})


class ProtocolTest(ProtocolFixture):
    def test_string_length_bounds_use_unicode_characters(self):
        from xsm.protocol import ProtocolError, validate
        schema = {'type': 'string', 'minLength': 1, 'maxLength': 1}
        validate('\U0001f30a', schema)
        validate('한', schema)
        for value in ('', '한글', 'e\u0301'):
            with self.subTest(value=value), self.assertRaises(ProtocolError) as refused:
                validate(value, schema)
            self.assertEqual(refused.exception.code, -32602)

    def test_empty_document_path_is_rejected_before_service_dispatch(self):
        from xsm.protocol import ProtocolError
        opened = self.open('empty-document-path')
        host = self.connection.sessions[opened['session']]
        with mock.patch.object(host, 'call', side_effect=AssertionError('invalid path reached service')) as call:
            with self.assertRaises(ProtocolError) as refused:
                self.operation(opened, 'xsm_doc', action='render', doc='')
            self.assertEqual(refused.exception.code, -32602)
        call.assert_not_called()

    def test_foreign_question_group_refuses_without_losing_owner_state(self):
        owner, other = self.open('group-owner'), self.open('group-other')
        group = self.operation(owner, 'xsm_ask', targets=['ref:' + other['ref']],
                               text='retain owner question', wake='never')
        denied = self.operation(other, 'xsm_question_status', id=group['id'])
        self.assertEqual(denied['status'], 'refused')
        self.assertEqual(denied['replies'], [])
        self.assertEqual(denied['recipients'], [])
        self.assertEqual(denied['claims'], [])
        self.assertEqual(self.operation(owner, 'xsm_question_status', id=group['id'])['status'], 'pending')

    def test_group_reply_claims_remain_aggregated_for_explicit_ack(self):
        owner, peer = self.open('group-claims-owner'), self.open('group-claims-peer')
        group = self.operation(owner, 'xsm_ask', targets=['ref:' + peer['ref']],
                               text='group claims question', wake='never')
        child = group['recipients'][0]['id']
        self.operation(peer, 'xsm_send', target='ref:' + owner['ref'], text='partial selected answer',
                       kind='reply', reply_to=child, request_id='group-claims-reply', wake='never')
        answer = self.operation(owner, 'xsm_question_status', id=group['id'])
        self.assertEqual([claim['id'] for claim in answer['claims']], ['group-claims-reply'])
        self.assertEqual(answer['claims'], answer['recipients'][0]['claims'])
        self.operation(owner, 'xsm_ack', tokens=[claim['token'] for claim in answer['claims']])
        retained = self.operation(owner, 'xsm_question_status', id=group['id'])
        self.assertEqual(retained['replies'][0]['body'], 'partial selected answer')
        self.assertEqual(retained['claims'], [])

    def test_team_queries_project_public_labels_and_running_state(self):
        opened = self.open('team-result-contract')
        self.assertEqual(self.operation(opened, 'xsm_team', action='list')['teams'], [])
        self.operation(opened, 'xsm_team', action='create', team='contract-probe')
        listed = self.operation(opened, 'xsm_team', action='list')['teams']
        shown = self.operation(opened, 'xsm_team', action='show', team='contract-probe')
        self.assertEqual(len(listed), 1)
        self.assertEqual(set(listed[0]), {'name', 'lead', 'members'})
        self.assertEqual(listed[0]['name'], 'contract-probe')
        self.assertIsNone(listed[0]['lead'])
        self.assertEqual(len(shown['members']), 1)
        self.assertEqual(shown['members'], [{'member': listed[0]['members'][0], 'running': True}])
        self.assertEqual(set(shown), {'name', 'lead', 'members', 'inbox_pending'})

    def test_public_bundle_requires_query_contracts_and_examples(self):
        import shutil
        from pathlib import Path
        from xsm import protocol_contract
        root = Path(self.tmp, 'contract-copy')
        source = Path(__file__).resolve().parents[1]
        for name in protocol_contract.REQUIRED:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, target)
        for name in ('discovery-result.schema.json', 'discovery-result-examples.json',
                     'team-result.schema.json', 'team-result-examples.json',
                     'board-result.schema.json', 'board-result-examples.json',
                     'doc-result.schema.json', 'doc-result-examples.json',
                     'send-result.schema.json', 'send-result-examples.json',
                     'question-result.schema.json', 'question-result-examples.json',
                     'question-results.md', 'publication-result.schema.json', 'publication-result-examples.json',
                     'decision-status-result.schema.json', 'decision-status-result-examples.json',
                     'grant-result.schema.json', 'grant-result-examples.json',
                     'approval-result.schema.json', 'approval-result-examples.json',
                     'decision-result.schema.json', 'decision-result-examples.json',
                     'scope-result.schema.json', 'scope-result-examples.json',
                     'endorsement-result.schema.json', 'endorsement-result-examples.json',
                     'handover-result.schema.json', 'handover-result-examples.json',
                     'owned-result.schema.json', 'owned-result-examples.json',
                     'error-contract.md', 'error.schema.json', 'error-examples.json'):
            target = root / 'docs/protocol' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / 'docs/protocol' / name, target)
        for name in ('discovery-result.schema.json', 'discovery-result-examples.json',
                     'team-result.schema.json', 'team-result-examples.json',
                     'board-result.schema.json', 'board-result-examples.json',
                     'doc-result.schema.json', 'doc-result-examples.json',
                     'send-result.schema.json', 'send-result-examples.json',
                     'question-result.schema.json', 'question-result-examples.json',
                     'question-results.md', 'publication-result.schema.json', 'publication-result-examples.json',
                     'decision-status-result.schema.json', 'decision-status-result-examples.json',
                     'grant-result.schema.json', 'grant-result-examples.json',
                     'approval-result.schema.json', 'approval-result-examples.json',
                     'decision-result.schema.json', 'decision-result-examples.json',
                     'scope-result.schema.json', 'scope-result-examples.json',
                     'endorsement-result.schema.json', 'endorsement-result-examples.json',
                     'handover-result.schema.json', 'handover-result-examples.json',
                     'owned-result.schema.json', 'owned-result-examples.json',
                     'error-contract.md', 'error.schema.json', 'error-examples.json'):
            target = root / 'docs/protocol' / name
            data = target.read_bytes()
            target.unlink()
            try:
                with self.subTest(artifact=name), self.assertRaisesRegex(ValueError, 'artifacts missing'):
                    protocol_contract.bundle(root)
            finally:
                target.write_bytes(data)

    def test_close_marker_failure_does_not_leave_a_live_pid_ghost_owner(self):
        from xsm import registry
        opened = self.open('close-marker-failure')
        with mock.patch.object(registry, 'mark_ended', side_effect=OSError('fixture marker failure')):
            with self.assertRaises(OSError):
                self.connection.dispatch('session.close', {'session': opened['session']})
        resumed = self.open('close-marker-failure')
        self.assertEqual(resumed['address'], opened['address'])
        self.assertNotEqual(resumed['generation'], opened['generation'])

    def test_conversation_owner_lock_cannot_follow_a_symlink(self):
        from pathlib import Path
        from xsm import registry
        from xsm.protocol import ProtocolError
        opened = self.open('unsafe-owner-lock')
        record = self.connection.sessions[opened['session']].record
        self.connection.dispatch('session.close', {'session': opened['session']})
        target = Path(self.tmp) / 'unchanged-fixture'
        target.write_text('not a conversation lease')
        lock = Path(registry._record_path(record['runtime'], record['session_id']) + '.protocol-lock')
        lock.unlink(); lock.symlink_to(target)
        with self.assertRaises((ProtocolError, OSError)):
            self.open('unsafe-owner-lock')
        self.assertEqual(target.read_text(), 'not a conversation lease')

    def test_wire_input_requires_utf8_and_preserves_character_limit(self):
        from xsm import protocol
        multibyte = (json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                      'params': {'protocolVersion': '한' * 400000}}, ensure_ascii=False) + '\n').encode('utf-8')
        oversized = (json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                      'params': {'protocolVersion': '한' * protocol.MAX_LINE}}, ensure_ascii=False) + '\n').encode('utf-8')
        invalid = b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"\xff"}}\n'
        for payload, expected in ((multibyte, -32002), (oversized, -32600), (invalid, -32700)):
            with self.subTest(expected=expected):
                out = io.StringIO()
                inp = io.TextIOWrapper(io.BytesIO(payload), encoding='utf-8', errors='surrogateescape')
                protocol.serve(inp, out)
                self.assertEqual(json.loads(out.getvalue())['error']['code'], expected)

    def test_generic_runtime_question_reaches_canonical_receiver(self):
        from xsm import handoff
        sender, receiver = self.open('generic-sender'), self.open('generic-receiver')
        result = self.operation(sender, 'xsm_ask', target='ref:' + receiver['ref'],
                                text='generic question', wake='never')
        record = self.connection.sessions[receiver['session']].record
        self.assertIn(result['id'], handoff.pending_ids(record))

    def test_generic_team_address_and_session_address_resolve_full_identity(self):
        from xsm import resolve, teams
        session = self.open('generic-team-peer')
        record = self.connection.sessions[session['session']].record
        address = teams.address(teams.member_of(record))
        found = resolve.resolve(address)
        self.assertTrue(found.ok, found.reason)
        self.assertEqual(found.record['home'], record['home'])
        self.assertEqual(session['address'], address)

    def test_opaque_peer_address_separates_profiles_and_ignores_incomplete_pointers(self):
        from xsm import identity, registry, resolve
        session = self.open('same-conversation')
        first = self.connection.sessions[session['session']].record
        second = dict(first, home=os.path.join(self.tmp, 'other-profile'))
        with mock.patch.object(registry, 'raw_records', return_value=[
                {'session_id': 'incomplete'}, first, second]):
            self.assertFalse(resolve.resolve('ref:' + first['ref']).ok)
            for record in (first, second):
                found = resolve.resolve(identity.address(record))
                self.assertTrue(found.ok, found.reason)
                self.assertEqual(found.record['home'], record['home'])
            self.assertFalse(resolve.resolve('peer:invalid').ok)

    def test_negative_wait_precedes_transport_capability_refusal(self):
        from xsm.protocol import ProtocolError
        session = self.open()
        for operation in ('xsm_send', 'xsm_inbox', 'xsm_question_status'):
            for value, code in ((-1, -32602), (1, -32004)):
                with self.subTest(operation=operation, wait=value):
                    with self.assertRaises(ProtocolError) as raised:
                        self.operation(session, operation, wait=value)
                    self.assertEqual(raised.exception.code, code)

    def test_targeted_inbox_recovers_current_owned_tokens_without_renewing(self):
        from xsm import handoff
        a, b = self.open(), self.open('owned-token')
        self.operation(a, 'xsm_send', target='ref:' + b['ref'], text='do once', wait=0)
        claim = self.operation(b, 'xsm_inbox')['claims'][0]
        rec = self.connection.sessions[b['session']].record
        before = handoff.status(rec, claim['id'])['claim']
        self.assertEqual(self.operation(b, 'xsm_inbox')['claims'], [])
        pack = self.operation(b, 'xsm_inbox', message_ids=[claim['id']])
        self.assertEqual(pack['claims'][0]['token'], claim['token'])
        self.assertEqual(handoff.status(rec, claim['id'])['claim'], before)
        self.operation(b, 'xsm_ack', tokens=[claim['token']])
        self.assertEqual(self.operation(b, 'xsm_inbox', message_ids=[claim['id']])['claims'], [])

    def test_targeted_inbox_cannot_read_another_conversation_or_take_unselected_messages(self):
        a, b, c = self.open(), self.open('target-b'), self.open('target-c')
        self.operation(a, 'xsm_send', target='ref:' + c['ref'], text='foreign', wait=0)
        foreign = self.operation(c, 'xsm_inbox')['claims'][0]
        self.operation(a, 'xsm_send', target='ref:' + b['ref'], text='unselected', wait=0)
        self.assertEqual(self.operation(b, 'xsm_inbox', message_ids=[foreign['id']])['claims'], [])
        self.assertEqual(len(self.operation(b, 'xsm_inbox')['claims']), 1)

    def test_targeted_byte_budget_does_not_release_an_existing_claim(self):
        from xsm import handoff
        a, b = self.open(), self.open('owned-byte-budget')
        for text in ('first', 'second' * 2000):
            self.operation(a, 'xsm_send', target='ref:' + b['ref'], text=text, wait=0)
        packet = self.operation(b, 'xsm_inbox')
        rec = self.connection.sessions[b['session']].record
        claims = packet['claims']
        before = [handoff.status(rec, claim['id'])['claim'] for claim in claims]
        bounded = self.operation(b, 'xsm_inbox', message_ids=[claim['id'] for claim in claims],
                                 max_bytes=len(packet['messages'][0].encode('utf-8')) + 20)
        self.assertEqual(len(bounded['claims']), 1)
        self.assertEqual([handoff.status(rec, claim['id'])['claim'] for claim in claims], before)

    def test_targeted_inbox_rejects_invalid_ids(self):
        from xsm.protocol import ProtocolError
        from xsm.operation_schema import ToolError
        a = self.open()
        for value in (None, [], 'id', [True], ['../bad'], ['bad\n'], ['x' * 161], ['x'] * 101):
            with self.subTest(value=repr(value)):
                # Provider-portable schema hints can reach the exact service
                # validator, whose ToolError becomes -32602 on the wire too.
                with self.assertRaises((ProtocolError, ToolError)):
                    self.operation(a, 'xsm_inbox', message_ids=value)

    def test_send_metadata_stays_request_local_when_passive_text_is_appended(self):
        from xsm import handoff
        a, b = self.open('meta-a'), self.open('meta-b')
        incoming = self.operation(b, 'xsm_send', target='ref:' + a['ref'], text='passive to a', wake='never', wait=0)
        value = self.operation(a, 'xsm_send', target='ref:' + b['ref'], text='a sends', wake='never', wait=0, request_id='send-with-passive')
        self.assertEqual(value['send']['id'], 'send-with-passive')
        self.assertIn('passive to a', value['text'])
        self.assertIs(value['grouped'], False)
        record = self.connection.sessions[a['session']].record
        self.assertNotEqual(handoff.status(record, incoming['send']['id'])['status'], 'acknowledged')
        self.assertNotIn('send', self.operation(a, 'xsm_team', action='list'))

    def test_send_provides_producer_metadata_without_parsing_display_text(self):
        sender, receiver = self.open('send-meta-sender'), self.open('send-meta-receiver')
        self.operation(receiver, 'xsm_inbox')
        value = self.operation(sender, 'xsm_send', target='ref:' + receiver['ref'], text='source metadata', wait=0,
            request_id='source-metadata', wake='never', attachments=[{'name': 'owned.txt', 'text': 'outgoing bytes'}])
        self.assertEqual(value['send']['id'], 'source-metadata')
        self.assertEqual(value['send']['status'], 'stored')
        self.assertIs(value['grouped'], False)
        manifest = self.operation(sender, 'xsm_files', storage_id=value['materials']['manifest_id'], outgoing=True)['manifest']
        content = self.operation(sender, 'xsm_files', storage_id=value['materials']['manifest_id'],
            entry_id=manifest['files'][0]['id'], outgoing=True)['content']
        self.assertEqual(content, 'outgoing bytes')
        self.assertIn('stored', value['text'])

    def test_attachment_prepare_failure_has_structured_recovery_data(self):
        from xsm.operation_schema import ToolError
        sender, receiver = self.open('prepare-error-sender'), self.open('prepare-error-new-reader')
        with self.assertRaises(ToolError) as caught:
            self.operation(sender, 'xsm_send', target='ref:' + receiver['ref'], text='preserve request', wait=0,
                request_id='file-recovery-data', attachments=[{'name': 'memo.txt', 'text': 'frozen bytes'}])
        data = caught.exception.data['attachment_error']
        self.assertEqual(data['request_id'], 'file-recovery-data')
        self.assertTrue(data['manifest_id'])
        self.assertIs(data['body_sent'], False)
        value = self.operation(sender, 'xsm_send', target='ref:' + receiver['ref'], text='preserve request', wait=0,
            request_id=data['request_id'], manifest_id=data['manifest_id'], attachment_fallback='inline', wake='never')
        self.assertEqual(value['send']['id'], data['request_id'])
        self.assertEqual(value['materials']['mode'], 'inline')

    def test_inbox_file_metadata_drives_copy_read_without_parsing_prose(self):
        import base64, hashlib
        from xsm import handoff
        from xsm.files import FileError
        sender, receiver = self.open('file-meta-sender'), self.open('file-meta-receiver')
        self.operation(receiver, 'xsm_inbox')  # establish a live file reader observation
        data = b'fixture bytes\x00\xff\n'
        self.operation(sender, 'xsm_send', target='ref:' + receiver['ref'], text='file payload', wait=0,
                       request_id='metadata-file', wake='never', attachments=[{'name': 'fixture.bin', 'base64': base64.b64encode(data).decode()}])
        packet = self.operation(receiver, 'xsm_inbox')
        metadata = packet['items'][0]['files']
        entry = metadata['files'][0]
        self.assertEqual(entry['name'], 'fixture.bin')
        self.assertEqual(entry['size'], len(data))
        self.assertEqual(entry['sha256'], hashlib.sha256(data).hexdigest())
        value = self.operation(receiver, 'xsm_files', storage_id=metadata['storage_id'],
                               entry_id=entry['id'], encoding='base64')
        self.assertEqual(base64.b64decode(value['content']), data)
        from xsm.operation_schema import ToolError
        with self.assertRaises(ToolError) as denied:
            self.operation(sender, 'xsm_files', storage_id=metadata['storage_id'], entry_id=entry['id'])
        self.assertEqual(denied.exception.data['file_error']['code'], 'owner-mismatch')
        record = self.connection.sessions[receiver['session']].record
        self.assertNotEqual(handoff.status(record, packet['claims'][0]['id'])['status'], 'acknowledged')
        self.operation(receiver, 'xsm_ack', tokens=[packet['claims'][0]['token']])

    def test_fresh_unobserved_reader_can_request_explicit_inline_fallback(self):
        sender, receiver = self.open('fallback-sender'), self.open('fallback-new-reader')
        self.operation(sender, 'xsm_send', target='ref:' + receiver['ref'], text='fallback payload', wait=0,
                       request_id='metadata-inline', wake='never', attachment_fallback='inline',
                       attachments=[{'name': 'fixture.txt', 'text': 'fallback-content-sentinel'}])
        packet = self.operation(receiver, 'xsm_inbox')
        self.assertIn('fallback-content-sentinel', '\n'.join(packet['messages']))
        self.assertNotIn('files', packet['items'][0])
        self.assertIs(packet['items'][0]['wake'], False)

    def test_unknown_stored_wake_policy_does_not_emit_a_wake_event(self):
        from pathlib import Path
        from xsm import handoff
        sender, receiver = self.open('wake-sender'), self.open('wake-receiver')
        self.operation(sender, 'xsm_send', target='ref:' + receiver['ref'], text='retain unknown policy', wait=0, request_id='unknown-wake')
        record = self.connection.sessions[receiver['session']].record
        path = Path(handoff._folder(record), 'unknown-wake.json')
        stored = json.loads(path.read_text()); stored['message']['wake'] = 'not-a-boolean'; path.write_text(json.dumps(stored))
        self.connection.dispatch('events.subscribe', {'session': receiver['session']})
        self.assertEqual(list(self.connection.events()), [])
        packet = self.operation(receiver, 'xsm_inbox')
        self.assertIsNone(packet['items'][0]['wake'])
        self.assertEqual(len(packet['claims']), 1)

    def test_text_operation_results_are_not_guessed_from_json_looking_content(self):
        actor = self.open('text-result')
        host = self.connection.sessions[actor['session']]
        for text in ('true', '17', '["letter"]', '{"status":"delivered"}'):
            with self.subTest(text=text), mock.patch.object(host, 'call', return_value=text):
                self.assertEqual(self.operation(actor, 'xsm_handover', action='show'), {'text': text})

    def test_declared_json_operation_results_require_an_object(self):
        from xsm.protocol import ProtocolError
        actor = self.open('json-result-shape')
        host = self.connection.sessions[actor['session']]
        for text in ('true', '17', '["not-a-packet"]', 'not json'):
            with self.subTest(text=text), mock.patch.object(host, 'call', return_value=text):
                with self.assertRaises(ProtocolError) as caught:
                    self.operation(actor, 'xsm_inbox')
                self.assertEqual(caught.exception.code, -32603)

    def test_team_and_board_json_results_keep_shape_with_passive_incoming(self):
        from xsm import handoff
        sender, receiver = self.open('json-sender'), self.open('json-receiver')
        self.operation(receiver, 'xsm_team', action='create', team='json-core')
        cases = [('xsm_team', {'action': 'list'}, 'teams'),
                 ('xsm_team', {'action': 'show', 'team': 'json-core'}, 'name'),
                 ('xsm_board', {'action': 'log', 'team': 'json-core'}, 'nodes'),
                 ('xsm_board', {'action': 'decisions', 'team': 'json-core'}, 'decisions')]
        for index, (name, arguments, field) in enumerate(cases):
            with self.subTest(operation=name, arguments=arguments):
                self.operation(sender, 'xsm_send', target='ref:' + receiver['ref'], text='passive-%s' % index,
                               wait=0, wake='never')
                value = self.operation(receiver, name, **arguments)
                self.assertIn(field, value)
                self.assertIn('passive-%s' % index, '\n'.join(value['incoming']['messages']))
                claims = value['incoming']['claims']
                self.assertEqual(len(claims), 1)
                record = self.connection.sessions[receiver['session']].record
                self.assertNotEqual(handoff.status(record, claims[0]['id'])['status'], 'acknowledged')
                self.operation(receiver, 'xsm_ack', tokens=[claims[0]['token']])

    def test_public_board_decisions_and_sync_use_member_scoped_service(self):
        actor = self.open('board-extension')
        self.operation(actor, 'xsm_team', action='create', team='extension')
        self.assertEqual(self.operation(actor, 'xsm_board', action='decisions', team='extension'), {'decisions': [], 'inbox_pending': 0})
        with mock.patch('xsm.board_sync.sync', return_value=['fixture sync']) as sync:
            self.assertEqual(self.operation(actor, 'xsm_board', action='sync', team='extension'),
                {'text':'fixture sync','board':{'action':'sync','team':'extension','sync_notes':['fixture sync']}})
        self.assertEqual(sync.call_args.args[0]['name'], 'extension')

    def test_inbox_byte_budget_counts_rendered_utf8_and_retains_the_remainder(self):
        a, b = self.open(), self.open('byte-budget')
        for index in range(3):
            self.operation(a, 'xsm_send', target='ref:' + b['ref'], text='item-%s ' % index + '한글🚀 ' * 1000, wait=0)
        packets = [self.operation(b, 'xsm_inbox', max_bytes=15000) for _ in range(3)]
        self.assertEqual([len(packet['claims']) for packet in packets], [1, 1, 1])
        for packet in packets:
            self.assertEqual(packet['rendered_bytes'], len('\n\n'.join(packet['messages']).encode('utf-8')))
            self.assertLessEqual(packet['rendered_bytes'], 15000)
        self.assertTrue(packets[0]['batch_limited'])
        self.assertEqual(len({claim['id'] for packet in packets for claim in packet['claims']}), 3)

    def test_one_oversized_original_is_returned_whole_without_starving(self):
        a, b = self.open(), self.open('oversized')
        text = 'whole original ' + '끝🚀' * 2000
        self.operation(a, 'xsm_send', target='ref:' + b['ref'], text=text, wait=0)
        packet = self.operation(b, 'xsm_inbox', max_bytes=1)
        self.assertEqual(len(packet['claims']), 1)
        self.assertIn(text, packet['messages'][0])
        self.assertGreater(packet['rendered_bytes'], 1)

    def test_invalid_inbox_byte_budgets_are_refused(self):
        from xsm.protocol import ProtocolError
        a = self.open()
        for value in (None, True, 0, -1, 1048577, 1.5, '2'):
            with self.assertRaises(ProtocolError):
                self.operation(a, 'xsm_inbox', max_bytes=value)

    def test_bounded_notice_cursor_reaches_later_originals_without_consuming_deferred_ones(self):
        from xsm import receive
        a, b = self.open(), self.open('notice-cursor')
        for text in ('defer-one', 'defer-two', 'allowed-last'):
            self.operation(a, 'xsm_send', target='ref:' + b['ref'], text=text, wait=0)
        check = receive.check
        def pending(parsed, me):
            if parsed.body.startswith('defer-'):
                return 'block', 'P2P admission temporarily unavailable: fixture'
            return check(parsed, me)
        with mock.patch.object(receive, 'check', side_effect=pending):
            first = self.operation(b, 'xsm_inbox', limit=2, max_bytes=10000)
            self.assertEqual(len(first['messages']), 2)
            self.assertEqual(first['claims'], [])
            self.assertIsNotNone(first['next_after'])
            second = self.operation(b, 'xsm_inbox', limit=2, max_bytes=10000, after_id=first['next_after'])
            self.assertEqual(len(second['claims']), 1)
            self.assertIn('allowed-last', second['messages'][0])
            again = self.operation(b, 'xsm_inbox', limit=2)
            self.assertEqual(len(again['messages']), 2)
            self.assertEqual(again['claims'], [])

    def test_bounded_inbox_retains_unselected_originals_and_requires_explicit_ack(self):
        from xsm import handoff
        a, b = self.open(), self.open('bounded')
        for index in range(5):
            self.operation(a, 'xsm_send', target='ref:' + b['ref'], text='batch-%s' % index, wait=0)
        packets = [self.operation(b, 'xsm_inbox', limit=2) for _ in range(3)]
        self.assertEqual([len(packet['messages']) for packet in packets], [2, 2, 1])
        claims = [claim for packet in packets for claim in packet['claims']]
        self.assertEqual(len({claim['id'] for claim in claims}), 5)
        receiver = self.connection.sessions[b['session']].record
        self.assertTrue(all(handoff.status(receiver, claim['id'])['status'] != 'acknowledged' for claim in claims))
        self.assertEqual(self.operation(b, 'xsm_inbox', limit=2)['messages'], [])
        ack = self.operation(b, 'xsm_ack', tokens=[claim['token'] for claim in claims])
        self.assertEqual(len(ack['acked']), 5)

    def test_invalid_inbox_limits_are_refused(self):
        from xsm.protocol import ProtocolError
        a = self.open()
        for limit in (None, 0, -1, 101, 1.5, True, '2'):
            with self.assertRaises(ProtocolError, msg=repr(limit)):
                self.operation(a, 'xsm_inbox', limit=limit)

    def test_existing_numeric_schema_bounds_reject_before_business_dispatch(self):
        from xsm.protocol import ProtocolError
        a = self.open()
        cases = [('xsm_owned', {'action': 'status', 'name': 'unstarted', 'wait': 61}, 'exceeds maximum'),
                 ('xsm_owned', {'action': 'status', 'name': 'unstarted', 'wait': 2 ** 2048}, 'exceeds maximum'),
                 ('xsm_owned', {'action': 'status', 'name': 'unstarted', 'wait': -1}, 'below minimum'),
                 ('xsm_ask', {'targets': ['ref:000000'], 'text': 'not sent', 'wait': -1}, 'below minimum'),
                 ('xsm_question_status', {'id': 'not-opened', 'wait': -1}, 'below minimum'),
                 ('xsm_connect', {'target': 'ref:000000', 'wait': -1}, 'below minimum')]
        for name, args, message in cases:
            with self.assertRaisesRegex(ProtocolError, message):
                self.connection.dispatch('operation.call', {
                    'session': a['session'], 'operation': name, 'arguments': args})

    def test_open_separates_profiles_and_opaque_handles(self):
        a, b = self.open(), self.open(profile="second")
        self.assertNotEqual(a["session"], b["session"])
        self.assertNotEqual(a["ref"], b["ref"])
        self.assertNotIn(self.tmp, json.dumps(a))

    def test_connection_handle_cannot_select_another_connection(self):
        from xsm.protocol import Connection, ProtocolError
        other = Connection()
        other.dispatch("initialize", {"protocolVersion": "1"})
        with self.assertRaises(ProtocolError):
            other.dispatch("session.update", {"session": self.open()["session"], "state": "busy"})

    def test_generic_host_uses_shared_service_without_mcp_transport(self):
        from xsm.operations import OperationService
        self.assertNotIn("xsm.mcp", sys.modules)
        opened = self.open()
        host = self.connection.sessions[opened["session"]]
        self.assertIsInstance(host, OperationService)
        self.assertEqual(host._invoke_operation.__func__.__module__, "xsm.operations")

    def test_native_impersonation_and_identity_replacement_rejected(self):
        from xsm.protocol import ProtocolError
        for runtime in ("claude", "codex", "../bad", "remote:foo"):
            with self.assertRaises(ProtocolError):
                self.open(runtime=runtime)
        a = self.open()
        with self.assertRaises(ProtocolError):
            self.connection.dispatch("session.update", {"session": a["session"], "cwd": "/"})

    def test_live_duplicate_refused_close_reopens_same_address(self):
        from xsm.protocol import ProtocolError
        a = self.open()
        with self.assertRaises(ProtocolError):
            self.open()
        record = self.connection.sessions[a["session"]].record
        self.connection.dispatch("session.close", {"session": a["session"]})
        from xsm import registry
        self.assertEqual(registry.by_session("fixture", record["session_id"])["state"], "ended")
        b = self.open()
        self.assertEqual(a["ref"], b["ref"])
        self.assertNotEqual(a["session"], b["session"])
        self.assertNotEqual(a["generation"], b["generation"])

    def test_user_answer_cannot_be_fabricated(self):
        from xsm.protocol import ProtocolError
        a = self.open()
        with self.assertRaises(ProtocolError) as caught:
            self.connection.dispatch("decision.response", {"session": a["session"], "answer": "yes"})
        self.assertEqual(caught.exception.code, -32004)

    def test_unknown_operation_and_arguments_rejected(self):
        from xsm.protocol import ProtocolError
        a = self.open()
        for name, args in [("shell", {}), ("xsm_send", {"sender": "someone"}),
                           ("xsm_send", {"wake": "always"}), ("xsm_inbox", {"wait": True})]:
            with self.assertRaises(ProtocolError):
                self.operation(a, name, **args)

    def test_protocol_send_does_not_call_codex_and_roundtrips_ack(self):
        from xsm import adapters, handoff
        a, b = self.open(), self.open("b")
        with mock.patch.object(adapters, "to_codex", side_effect=AssertionError("wrong runtime")):
            result = self.operation(a, "xsm_send", target="ref:" + b["ref"], text="hello", wait=0)
        self.assertIn("stored", str(result))
        pack = self.operation(b, "xsm_inbox")
        self.assertEqual(len(pack["claims"]), 1, pack)
        self.assertIn("hello", str(pack["messages"]))
        claim = pack["claims"][0]
        rec = self.connection.sessions[b["session"]].record
        self.assertNotEqual(handoff.status(rec, claim["id"])["status"], "acknowledged")
        self.operation(b, "xsm_ack", tokens=[claim["token"]])
        self.assertEqual(handoff.status(rec, claim["id"])["status"], "acknowledged")

    def test_fyi_never_emits_event_but_can_be_consumed(self):
        a, b = self.open(), self.open("b")
        self.connection.dispatch("events.subscribe", {"session": b["session"]})
        self.operation(a, "xsm_send", target="ref:" + b["ref"], text="later", wake="never", wait=0)
        self.assertEqual(list(self.connection.events()), [])
        pack = self.operation(b, "xsm_inbox")
        self.assertIn("later", str(pack["messages"]))
        self.assertEqual(len(pack["claims"]), 1)

    def test_notification_does_not_claim_and_delivery_report_does_not_ack(self):
        from xsm import handoff
        a, b = self.open(), self.open("b")
        self.connection.dispatch("events.subscribe", {"session": b["session"]})
        self.operation(a, "xsm_send", target="ref:" + b["ref"], text="now", wait=0)
        events = list(self.connection.events())
        self.assertEqual(len(events), 1)
        mid = events[0]["params"]["ids"][0]
        record = self.connection.sessions[b["session"]].record
        self.assertEqual(handoff.status(record, mid)["status"], "pending")
        report = self.connection.dispatch("delivery.report", {"session": b["session"], "id": mid, "state": "queued"})
        self.assertFalse(report["acknowledged"])
        self.assertEqual(handoff.status(record, mid)["status"], "pending")
        self.assertEqual(list(self.connection.events()), [])

    def test_fetch_release_and_queue_report_never_forge_native_consumption(self):
        from xsm import ledger
        a, b = self.open(), self.open("b")
        self.operation(a, "xsm_send", target="ref:" + b["ref"], text="native admission may fail", wait=0)
        pack = self.operation(b, "xsm_inbox")
        mid = pack["claims"][0]["id"]
        self.assertFalse(ledger.evidence_of(mid)["runtime_reached"])
        self.assertIsNone(ledger.receipt_of(mid))
        self.connection.dispatch("inbox.release", {"session": b["session"], "tokens": [pack["claims"][0]["token"]]})
        self.assertFalse(ledger.evidence_of(mid)["runtime_reached"])
        self.connection.dispatch("delivery.report", {"session": b["session"], "id": mid, "state": "queued"})
        self.assertFalse(ledger.evidence_of(mid)["runtime_reached"])
        current = self.operation(b, "xsm_inbox")
        self.operation(b, "xsm_ack", tokens=[current["claims"][0]["token"]])
        self.assertTrue(ledger.evidence_of(mid)["runtime_reached"])
        self.assertEqual(ledger.receipt_of(mid)["decision"], "delivered")

    def test_native_admission_requires_own_claim_and_is_separate_from_consumption(self):
        from xsm import ledger, handoff
        from xsm.protocol import ProtocolError
        a, b = self.open(), self.open("b")
        self.operation(a, "xsm_send", target="ref:" + b["ref"], text="native admitted", wait=0)
        claim = self.operation(b, "xsm_inbox")["claims"][0]
        for token in (None, "wrong"):
            with self.assertRaises(ProtocolError):
                self.connection.dispatch("delivery.report", {"session": b["session"], "id": claim["id"],
                    "state": "admitted", "token": token})
        self.assertFalse(ledger.evidence_of(claim["id"])["runtime_reached"])
        self.connection.dispatch("delivery.report", {"session": b["session"], "id": claim["id"],
            "state": "admitted", "token": claim["token"]})
        self.assertTrue(ledger.evidence_of(claim["id"])["runtime_reached"])
        receiver = self.connection.sessions[b["session"]].record
        self.assertNotEqual(handoff.status(receiver, claim["id"])["status"], "acknowledged")

    def test_committed_consumption_survives_receipt_mirror_failure(self):
        from xsm import receive, ledger
        a, b = self.open(), self.open("b")
        self.operation(a, "xsm_send", target="ref:" + b["ref"], text="committed read", wait=0)
        claim = self.operation(b, "xsm_inbox")["claims"][0]
        with mock.patch.object(receive, "protocol_receipt", side_effect=OSError("mirror interrupted")):
            with self.assertRaises(OSError):
                self.operation(b, "xsm_ack", tokens=[claim["token"]])
        self.assertIsNone(ledger.receipt_of(claim["id"]))
        with mock.patch.object(ledger.time, "sleep", side_effect=AssertionError("committed ACK must not wait")):
            self.assertTrue(ledger.wait_for(claim["id"], 1)["delivery"]["acknowledged"])
        self.assertEqual(self.operation(b, "xsm_inbox")["claims"], [])

    def test_closed_connection_preserves_unacknowledged_original(self):
        from xsm import handoff
        a, b = self.open(), self.open("b")
        self.operation(a, "xsm_send", target="ref:" + b["ref"], text="retain", wait=0)
        record = dict(self.connection.sessions[b["session"]].record)
        self.connection.close()
        self.assertTrue(handoff.pending_ids(record))

    def test_uninitialized_and_unsupported_version(self):
        from xsm.protocol import Connection, ProtocolError
        c = Connection()
        for method, args in [("operations/list", {}), ("initialize", {"protocolVersion": "999"})]:
            with self.assertRaises(ProtocolError):
                c.dispatch(method, args)

    def test_omitted_wait_cannot_inherit_legacy_blocking_default(self):
        a = self.open()
        host = self.connection.sessions[a["session"]]
        with mock.patch.object(host, "call", return_value="{}") as call:
            self.operation(a, "xsm_send", target="ref:123456", text="hello")
        self.assertEqual(call.call_args[0][1]["wait"], 0)

    def test_continuous_requests_do_not_starve_event_polling(self):
        from xsm.protocol import serve, Connection
        ticks = iter([i * 0.3 for i in range(200)])
        request = json.dumps({"jsonrpc": "2.0", "id": 1,
                              "method": "initialize", "params": {"protocolVersion": "1"}})
        out = io.StringIO()
        with mock.patch("xsm.protocol.time.monotonic", side_effect=lambda: next(ticks)), \
                mock.patch.object(Connection, "events", return_value=iter(())) as events:
            serve(io.StringIO((request + "\n") * 12), out)
        self.assertGreater(events.call_count, 1)

    def test_internal_request_errors_have_generic_wire_errors_and_keep_connection(self):
        from xsm.protocol import Connection, serve
        for index, kind in enumerate((RuntimeError, OSError, KeyError)):
            with self.subTest(kind=kind.__name__):
                connection = Connection()
                connection.dispatch('initialize', {'protocolVersion': '1'})
                opened = connection.dispatch('session.open', {'runtime': 'fixture', 'profile': 'fault',
                    'conversation': str(index), 'cwd': self.tmp, 'capabilities': ['messaging', 'inbox']})
                host = connection.sessions[opened['session']]
                original, calls = host.call, []
                def fault_then_healthy(name, args):
                    calls.append(name)
                    if len(calls) == 1:
                        raise kind('private-fixture-detail')
                    return original(name, args)
                request = lambda mid: {'jsonrpc': '2.0', 'id': mid, 'method': 'operation.call',
                    'params': {'session': opened['session'], 'operation': 'xsm_inbox', 'arguments': {}}}
                class BrokenReporter(io.StringIO):
                    def write(self, value):
                        raise OSError('private-diagnostic-detail')
                out = io.StringIO()
                errors = BrokenReporter() if kind is OSError else io.StringIO()
                with mock.patch('xsm.protocol.Connection', return_value=connection), \
                        mock.patch.object(host, 'call', side_effect=fault_then_healthy), \
                        mock.patch('sys.stderr', errors):
                    status = serve(io.StringIO('\n'.join(json.dumps(request(mid)) for mid in (1, 2)) + '\n'), out)
                self.assertEqual(status, 0)
                frames = [json.loads(line) for line in out.getvalue().splitlines()]
                self.assertEqual(frames[0], {'jsonrpc': '2.0', 'id': 1,
                    'error': {'code': -32603, 'message': 'internal server error'}})
                self.assertEqual(frames[1]['result']['claims'], [])
                self.assertNotIn('private-fixture-detail', out.getvalue() + errors.getvalue())
                self.assertNotIn('Traceback', out.getvalue() + errors.getvalue())

    def test_invalid_internal_result_is_not_reported_as_bad_arguments(self):
        from xsm.protocol import serve
        original, called = self.connection.dispatch, []
        def invalid_once(method, params):
            called.append(method)
            if len(called) == 1:
                return {'internal_nonfinite': float('nan')}
            return original(method, params)
        requests = [{'jsonrpc': '2.0', 'id': mid, 'method': 'operations/list', 'params': {}}
                    for mid in (1, 2)]
        out = io.StringIO()
        with mock.patch('xsm.protocol.Connection', return_value=self.connection), \
                mock.patch.object(self.connection, 'dispatch', side_effect=invalid_once):
            self.assertEqual(serve(io.StringIO('\n'.join(map(json.dumps, requests)) + '\n'), out), 0)
        frames = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual(frames[0]['error'], {'code': -32603, 'message': 'internal server error'})
        self.assertTrue(frames[1]['result']['operations'])

    def test_internal_error_after_claim_keeps_original_for_explicit_token_recovery(self):
        from xsm import handoff
        from xsm.protocol import serve
        sender, receiver = self.open('error-sender'), self.open('error-receiver')
        self.operation(sender, 'xsm_send', target='ref:' + receiver['ref'], text='retain after error', wait=0)
        host = self.connection.sessions[receiver['session']]
        mid = handoff.pending_ids(host.record)[0]
        original, claimed = host.call, []
        def after_claim(name, args):
            result = original(name, args)
            if not claimed:
                claimed.extend(json.loads(result)['claims'])
                raise RuntimeError('private-post-effect-detail')
            return result
        requests = [{'jsonrpc': '2.0', 'id': index, 'method': 'operation.call', 'params': {
            'session': receiver['session'], 'operation': 'xsm_inbox', 'arguments': args}}
            for index, args in enumerate(({}, {'message_ids': [mid]}), 1)]
        out, errors = io.StringIO(), io.StringIO()
        with mock.patch('xsm.protocol.Connection', return_value=self.connection), \
                mock.patch.object(host, 'call', side_effect=after_claim), mock.patch('sys.stderr', errors):
            self.assertEqual(serve(io.StringIO('\n'.join(map(json.dumps, requests)) + '\n'), out), 0)
        frames = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual(frames[0]['error']['code'], -32603)
        self.assertEqual(frames[1]['result']['claims'][0]['token'], claimed[0]['token'])
        self.assertNotEqual(handoff.status(host.record, mid)['status'], 'acknowledged')
        self.assertNotIn('private-post-effect-detail', out.getvalue() + errors.getvalue())

    def test_unknown_method_is_not_misclassified_as_unknown_session(self):
        from xsm.protocol import ProtocolError
        with self.assertRaises(ProtocolError) as failure:
            self.connection.dispatch('fixture.unknown', {})
        self.assertEqual(failure.exception.code, -32601)
        self.assertEqual(self.connection.sessions, {})

    def test_stdio_recovers_after_bad_json_and_unknown_method(self):
        from xsm.protocol import serve
        inp = io.StringIO('broken\n' + json.dumps({"jsonrpc": "2.0", "id": 1,
            "method": "initialize", "params": {"protocolVersion": "1"}}) + '\n')
        out = io.StringIO()
        self.assertEqual(serve(inp, out), 0)
        results = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual(results[0]["error"]["code"], -32700)
        self.assertEqual(results[1]["result"]["protocolVersion"], "1")


class ProtocolRequestFieldsTest(ProtocolFixture):
    def test_unknown_parameters_are_refused_before_effects(self):
        from xsm.protocol import ProtocolError
        opened = self.open()
        requests = {
            'operations/list': {},
            'events.subscribe': {'session': opened['session']},
            'inbox.release': {'session': opened['session'], 'tokens': ['unknown']},
            'delivery.report': {'session': opened['session'], 'id': 'unknown', 'state': 'queued'},
            'operation.call': {'session': opened['session'], 'operation': 'xsm_inbox', 'arguments': {}},
            'session.close': {'session': opened['session']},
        }
        for method, params in requests.items():
            with self.subTest(method=method):
                with self.assertRaises(ProtocolError) as refused:
                    self.connection.dispatch(method, dict(params, injected='not accepted'))
                self.assertEqual(refused.exception.code, -32602)
        self.assertIn(opened['session'], self.connection.sessions)
        self.assertEqual(self.connection.subscriptions, set())

    def test_initialize_unknown_parameter_is_refused_without_initializing(self):
        from xsm.protocol import Connection, ProtocolError
        connection = Connection()
        with self.assertRaises(ProtocolError) as refused:
            connection.dispatch('initialize', {'protocolVersion': '1', 'injected': True})
        self.assertEqual(refused.exception.code, -32602)
        self.assertFalse(connection.initialized)

    def test_public_schema_binds_every_runtime_method_and_field(self):
        from pathlib import Path
        from xsm.protocol import REQUEST_FIELDS
        schema = json.loads((Path(__file__).resolve().parents[1] / 'docs/protocol/request.schema.json').read_text())
        self.assertEqual(set(schema['properties']['method']['enum']), set(REQUEST_FIELDS))
        bindings = {item['if']['properties']['method']['const']:
                    item['then']['properties']['params']['$ref'].split('/')[-1]
                    for item in schema['allOf']}
        self.assertEqual(set(bindings), set(REQUEST_FIELDS))
        for method, fields in REQUEST_FIELDS.items():
            definition = schema['$defs'][bindings[method]]
            self.assertEqual(set(definition['properties']), fields, method)
            self.assertIs(definition['additionalProperties'], False, method)

    def test_public_output_contract_covers_methods_and_known_notifications(self):
        from pathlib import Path
        from xsm.protocol import REQUEST_FIELDS
        root = Path(__file__).resolve().parents[1]
        schema = json.loads((root / 'docs/protocol/output.schema.json').read_text())
        self.assertEqual(set(schema['x-methodResults']), set(REQUEST_FIELDS))
        for reference in schema['x-methodResults'].values():
            self.assertIn(reference.split('/')[-1], schema['$defs'])
        notifications = {branch['properties']['method']['const'] for branch in schema['oneOf']
                         if 'method' in branch['properties']}
        self.assertEqual(notifications, {'events/available', 'decision/request'})
        examples = json.loads((root / 'docs/protocol/output-examples.json').read_text())
        self.assertEqual({e['method'] for e in examples if 'result' in e['frame']}, set(REQUEST_FIELDS))

    def test_public_operation_schema_matches_runtime_structural_contract(self):
        from pathlib import Path
        from xsm.protocol_contract import operation_schema
        from xsm.operation_schema import TOOLS
        import copy
        before = copy.deepcopy(TOOLS)
        actual = operation_schema()
        artifact = json.loads((Path(__file__).resolve().parents[1] / 'docs/protocol/operations.schema.json').read_text())
        self.assertEqual(artifact, actual)
        self.assertEqual(TOOLS, before)
        self.assertEqual(len(actual['$defs']), 22)
        for tool in TOOLS:
            arguments = actual['$defs'][tool['name']]
            self.assertIs(arguments['additionalProperties'], False)
            for name in ('wait', 'wait_secs'):
                if name in arguments['properties']:
                    self.assertEqual(arguments['properties'][name]['const'], 0)
