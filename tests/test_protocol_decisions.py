"""Host-side question responses are scoped, single-use, and never self-apply."""
from unittest import mock
import tempfile

from tests.test_protocol import ProtocolFixture


class HostDecisionTest(ProtocolFixture):
    def participant(self, conversation="a"):
        return self.connection.dispatch("session.open", {
            "runtime": "ui-fixture", "profile": "profile", "conversation": conversation,
            "cwd": self.tmp, "capabilities": ["user-decisions"]})

    def question(self, session, question="Choose a color", key="first"):
        return self.operation(session, "xsm_decide", question=question,
                              options=["blue", "green"], decision_key=key)

    def event(self):
        events = list(self.connection.events())
        return next(e["params"] for e in events if e["method"] == "decision/request")

    def answer(self, event, **changes):
        args = {"session": event["session"], "questionId": event["questionId"],
                "challenge": event["challenge"], "displayed": event["question"],
                "action": "accept", "answer": "blue", "source_id": event["questionId"]}
        args.update(changes)
        return self.connection.dispatch("decision.response", args)

    def test_publication_host_answer_requires_retry_and_withdrawal_needs_fresh_approval(self):
        from xsm import directory
        a = self.participant('publisher')
        record = self.connection.sessions[a['session']].record
        pending = self.operation(a, 'xsm_publish')
        self.assertEqual(pending['status'], 'waiting-for-user')
        event = self.event()
        self.assertFalse(directory.is_published(record))
        self.answer(event, answer='allow')
        self.assertFalse(directory.is_published(record))
        self.assertEqual(self.operation(a, 'xsm_publish')['status'], 'published')
        self.assertTrue(directory.is_published(record))
        self.assertEqual(self.operation(a, 'xsm_publish', visible=False)['status'], 'hidden')
        again = self.operation(a, 'xsm_publish')
        self.assertEqual(again['status'], 'waiting-for-user')
        second = self.event()
        self.assertNotEqual(second['decisionId'], event['decisionId'])
        self.answer(second, answer='deny')
        self.assertEqual(self.operation(a, 'xsm_publish')['status'], 'refused')
        self.assertFalse(directory.is_published(record))

    def test_connect_host_answer_grants_only_pair_then_reads_live_handshake(self):
        from xsm import config
        a = self.participant('selector')
        outside = tempfile.TemporaryDirectory(prefix='xsm-host-selected-peer-')
        self.addCleanup(outside.cleanup)
        b = self.connection.dispatch('session.open', {'runtime':'ui-fixture', 'profile':'peer',
            'conversation':'outside', 'cwd':outside.name, 'capabilities':['messaging','inbox']})
        ar, br = (self.connection.sessions[x['session']].record for x in (a,b))
        self.assertIsNone(config.scope_for(ar, br)[0])
        pending = self.operation(a, 'xsm_connect', target='ref:' + b['ref'])
        self.assertEqual(pending['status'], 'waiting-for-user')
        event = self.event()
        self.answer(event, answer='allow')
        self.assertIsNone(config.scope_for(ar, br)[0])
        handshake = self.operation(a, 'xsm_connect', target='ref:' + b['ref'])
        self.assertIsNotNone(config.scope_for(ar, br)[0])
        self.assertEqual(handshake['handshake'], 'pending')
        self.operation(b, 'xsm_send', target='ref:' + a['ref'], text='actual selected reply',
            kind='reply', reply_to=handshake['id'], outcome='succeeded', wake='never', request_id='selected-peer-reply')
        completed = self.operation(a, 'xsm_connect', target='ref:' + b['ref'], request_id=handshake['id'])
        self.assertEqual(completed['handshake'], 'completed')
        self.assertEqual([c['id'] for c in completed['claims']], ['selected-peer-reply'])

    def test_publication_without_ui_keeps_selection_required(self):
        from xsm import directory
        a = self.open('publisher-no-ui')
        result = self.operation(a, 'xsm_publish')
        self.assertEqual(result['status'], 'selection-required')
        self.assertFalse(directory.is_published(self.connection.sessions[a['session']].record))
        self.assertEqual(list(self.connection.events()), [])

    def test_publication_mcp_uses_actual_elicitation_reader(self):
        import io, json
        from xsm import directory, mcp
        for reviewer in (None, 'auto_review', 'fake_native'):
            with self.subTest(reviewer=reviewer):
                a = self.participant('mcp-publisher-' + str(reviewer))
                record = self.connection.sessions[a['session']].record
                answer = {'action':'accept','content':{'answer':'allow'}}
                if reviewer == 'auto_review':
                    answer['_meta'] = {'approvals_reviewer': reviewer}
                messages = [
                    {'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-06-18','capabilities':{'elicitation':{}},'clientInfo':{'name':'fixture-user-ui'}}},
                    {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'xsm_publish','arguments':{}}},
                    {'jsonrpc':'2.0','id':'xsm-1','result':answer}]
                if reviewer == 'fake_native':
                    messages[1]['params']['arguments'] = {'answer_request':'invented-native-id','original_question':'invented question'}
                output = io.StringIO()
                server = mcp.Server(io.StringIO(''.join(json.dumps(x)+'\n' for x in messages)), output)
                server.session = lambda: record
                server.serve()
                frames = [json.loads(line) for line in output.getvalue().splitlines()]
                self.assertEqual(any(frame.get('method') == 'elicitation/create' for frame in frames), reviewer != 'fake_native')
                reply = next(frame for frame in frames if frame.get('id') == 2)
                self.assertNotIn('error', reply)
                self.assertFalse(reply['result'].get('isError', False), reply)
                self.assertEqual(directory.is_published(record), reviewer is None)

    def test_publication_unknown_application_is_not_replayed(self):
        from xsm import decisions, directory
        a = self.participant('publisher-error')
        self.operation(a, 'xsm_publish'); event = self.event(); self.answer(event, answer='allow')
        with mock.patch.object(directory, 'publish', side_effect=OSError('fixture persistence failure')) as apply:
            with self.assertRaises(OSError):
                self.operation(a, 'xsm_publish')
            self.assertEqual(decisions.read(event['decisionId'])['status'], 'unknown')
            self.assertEqual(self.operation(a, 'xsm_publish')['status'], 'refused')
            self.assertEqual(apply.call_count, 1)

    def test_connect_approval_does_not_follow_reassigned_target_name(self):
        from xsm import config, paths, registry
        a = self.participant('selector-name')
        outside = tempfile.TemporaryDirectory(prefix='xsm-host-name-peer-'); self.addCleanup(outside.cleanup)
        def peer(conversation):
            opened = self.connection.dispatch('session.open', {'runtime':'ui-fixture','profile':'peer',
                'conversation':conversation,'cwd':outside.name,'capabilities':['inbox']})
            return self.connection.sessions[opened['session']].record
        old = peer('old-target'); old['name']='picked'
        paths.write_json(registry._record_path(old['runtime'], old['session_id']), old)
        self.assertEqual(self.operation(a, 'xsm_connect', target='picked')['status'], 'waiting-for-user')
        event = self.event(); self.answer(event, answer='allow')
        old['name']='renamed'; paths.write_json(registry._record_path(old['runtime'], old['session_id']), old)
        new = peer('new-target'); new['name']='picked'
        paths.write_json(registry._record_path(new['runtime'], new['session_id']), new)
        self.assertEqual(self.operation(a, 'xsm_connect', target='picked')['status'], 'waiting-for-user')
        second = self.event(); self.assertNotEqual(event['decisionId'], second['decisionId'])
        caller = self.connection.sessions[a['session']].record
        self.assertIsNone(config.scope_for(caller, old)[0]); self.assertIsNone(config.scope_for(caller, new)[0])

    def test_noop_withdrawal_does_not_renew_denied_publication(self):
        from xsm import connect
        with self.assertRaises(ValueError):
            connect.publication(None, visible=False)
        a = self.participant('denied-noop-withdrawal')
        self.operation(a, 'xsm_publish'); event = self.event(); self.answer(event, answer='deny')
        self.assertEqual(self.operation(a, 'xsm_publish')['status'], 'refused')
        self.assertEqual(self.operation(a, 'xsm_publish', visible=False)['status'], 'hidden')
        self.assertEqual(self.operation(a, 'xsm_publish')['status'], 'refused')
        self.assertEqual(list(self.connection.events()), [])

    def test_display_rename_does_not_renew_denied_publication(self):
        from xsm import paths, registry
        a = self.participant('denied-renamed-publisher')
        self.operation(a, 'xsm_publish'); event = self.event(); self.answer(event, answer='deny')
        self.assertEqual(self.operation(a, 'xsm_publish')['status'], 'refused')
        record = self.connection.sessions[a['session']].record
        record['name'] = 'new display name'
        paths.write_json(registry._record_path(record['runtime'], record['session_id']), record)
        self.assertEqual(self.operation(a, 'xsm_publish')['status'], 'refused')
        self.assertEqual(list(self.connection.events()), [])

    def test_connect_same_identity_rename_preserves_answered_display(self):
        from xsm import paths, registry
        a = self.participant('selector-same-identity')
        outside = tempfile.TemporaryDirectory(prefix='xsm-host-renamed-peer-'); self.addCleanup(outside.cleanup)
        b = self.connection.dispatch('session.open', {'runtime':'ui-fixture','profile':'peer',
            'conversation':'same-target','cwd':outside.name,'capabilities':['inbox']})
        self.operation(a, 'xsm_connect', target='ref:' + b['ref']); event = self.event()
        self.answer(event, answer='allow')
        record = self.connection.sessions[b['session']].record
        record['name'] = 'renamed same conversation'
        paths.write_json(registry._record_path(record['runtime'], record['session_id']), record)
        result = self.operation(a, 'xsm_connect', target='ref:' + b['ref'])
        self.assertEqual(result['handshake'], 'pending')
        self.assertEqual(list(self.connection.events()), [])

    def test_exact_answer_replay_after_expiry_reports_expired_without_applying(self):
        from xsm import decisions
        a = self.participant()
        self.question(a)
        event = self.event()
        self.assertEqual(self.answer(event)['status'], 'answered')
        with mock.patch('xsm.decisions.time.time', return_value=event['expiresAt'] + 1):
            self.assertEqual(self.answer(event)['status'], 'expired')
        self.assertIsNone(decisions.read(event['decisionId'])['application'])

    def test_question_response_then_explicit_retry_applies(self):
        from xsm import decisions
        a = self.participant()
        pending = self.question(a)
        self.assertEqual(pending["status"], "waiting-for-user")
        event = self.event()
        self.assertEqual(pending["decision_id"], event["decisionId"])
        self.assertNotIn("challenge", pending)
        self.assertEqual(decisions.read(event["decisionId"])["status"], "pending")
        self.answer(event)
        record = decisions.read(event["decisionId"])
        self.assertEqual(record["status"], "answered")
        self.assertEqual(record["answer"]["source"], "host-user")
        result = self.question(a)
        self.assertIn("blue", str(result))
        self.assertEqual(decisions.read(event["decisionId"])["status"], "applied")
        self.assertEqual(list(self.connection.events()), [])

    def test_wrong_session_challenge_and_display_do_not_answer(self):
        from xsm import decisions
        from xsm.protocol import ProtocolError
        a, b = self.participant(), self.participant("b")
        self.question(a)
        event = self.event()
        for overrides in ({"session": b["session"]}, {"challenge": "wrong"},
                          {"displayed": "different question"}, {"answer": "red"},
                          {"action": "decline", "answer": {"untrusted": "answer"}}):
            with self.assertRaises(ProtocolError):
                self.answer(event, **overrides)
            self.assertIsNone(decisions.read(event["decisionId"])["answer"])

    def test_empty_question_never_waits_for_a_host_answer(self):
        from xsm.protocol import ProtocolError
        a = self.participant()
        with self.assertRaises(ProtocolError):
            self.question(a, question="  ")
        self.assertEqual(list(self.connection.events()), [])

    def test_one_question_cannot_answer_another_or_be_overwritten(self):
        from xsm import decisions
        from xsm.protocol import ProtocolError
        a = self.participant()
        self.question(a)
        first = self.event()
        self.question(a, question="Another color", key="second")
        second = self.event()
        self.answer(first)
        with self.assertRaises(ProtocolError):
            self.answer(first, answer="green")
        self.assertIsNone(decisions.read(second["decisionId"])["answer"])

    def test_repeated_pending_operation_does_not_repeat_question(self):
        a = self.participant()
        first = self.question(a)
        self.event()
        self.assertEqual(self.question(a), first)
        self.assertEqual(list(self.connection.events()), [])

    def test_closed_session_cannot_accept_late_reply(self):
        from xsm.protocol import ProtocolError
        a = self.participant()
        self.question(a)
        event = self.event()
        self.connection.dispatch("session.close", {"session": a["session"]})
        with self.assertRaises(ProtocolError):
            self.answer(event)

    def test_reopening_same_process_cannot_inherit_answered_approval(self):
        a = self.participant()
        old = self.question(a)
        event = self.event()
        self.answer(event)
        self.connection.dispatch("session.close", {"session": a["session"]})
        new = self.participant()
        pending = self.question(new)
        self.assertNotEqual(new["generation"], a["generation"])
        self.assertEqual(pending["status"], "waiting-for-user")
        self.assertNotEqual(old["decision_id"], pending["decision_id"])

    def test_same_host_answer_id_is_not_reusable_for_another_question(self):
        from xsm.protocol import ProtocolError
        a = self.participant()
        self.question(a)
        first = self.event()
        self.answer(first, source_id="same-native-answer")
        self.question(a, question="Another color", key="second")
        second = self.event()
        with self.assertRaises(ProtocolError):
            self.answer(second, source_id="same-native-answer")

    def test_expired_answer_never_applies(self):
        from xsm import decisions
        from xsm.protocol import ProtocolError
        a = self.participant()
        self.question(a)
        event = self.event()
        record = decisions.read(event["decisionId"])
        with mock.patch("xsm.decisions.time.time", return_value=record["expires_at"] + 1):
            with self.assertRaises(ProtocolError):
                self.answer(event)
        self.assertIsNone(decisions.read(event["decisionId"])["answer"])

    def test_host_answer_is_recorded_beside_team_board_with_its_source(self):
        from xsm import teams, board
        a = self.participant()
        record = self.connection.sessions[a["session"]].record
        teams.create(record, "colors")
        pending = self.question(a)
        event = self.event()
        self.answer(event)
        self.question(a)
        decisions = board.decisions("colors")
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["via"], "host-user")
        self.assertEqual(decisions[0]["answer"], "blue")

    def test_replaced_consumer_cannot_ack_previous_execution_claim(self):
        from xsm.protocol import ProtocolError
        a, b = self.open(), self.open("receiver")
        self.operation(a, "xsm_send", target="ref:" + b["ref"], text="retain claim", wait=0)
        old = self.operation(b, "xsm_inbox")["claims"][0]
        self.connection.dispatch("session.close", {"session": b["session"]})
        new = self.open("receiver")
        recovered = self.operation(new, "xsm_inbox")["claims"][0]
        self.assertEqual(old["id"], recovered["id"])
        self.assertNotEqual(old["generation"], recovered["generation"])
        with self.assertRaises(ValueError):
            self.operation(new, "xsm_ack", tokens=[old["token"]])
        self.operation(new, "xsm_ack", tokens=[recovered["token"]])

    def test_permission_effect_is_applied_once_only_after_host_reply_and_retry(self):
        from xsm import config
        a = self.participant()
        with tempfile.TemporaryDirectory(prefix="xsm-host-reach-") as other:
            pending = self.operation(a, "xsm_reach", dir=other)
            self.assertEqual(pending["status"], "waiting-for-user")
            event = self.event()
            self.assertEqual(config.reaches(), [])
            self.answer(event, answer="allow")
            self.assertEqual(config.reaches(), [])
            result = self.operation(a, "xsm_reach", dir=other)
            self.assertIn("allowed", str(result))
            self.assertEqual(len(config.reaches()), 1)
            self.assertEqual(self.operation(a, "xsm_reach", dir=other), result)
            self.assertEqual(len(config.reaches()), 1)

    def test_denied_permission_does_not_change_scope(self):
        from xsm import config
        from xsm.operation_schema import ToolError
        a = self.participant()
        with tempfile.TemporaryDirectory(prefix="xsm-host-denied-") as other:
            self.operation(a, "xsm_reach", dir=other)
            event = self.event()
            self.answer(event, answer="deny")
            with self.assertRaises(ToolError):
                self.operation(a, "xsm_reach", dir=other)
            self.assertEqual(config.reaches(), [])

    def test_abandon_display_does_not_answer_deny_or_apply_and_retries_fresh_display(self):
        from xsm import decisions
        from xsm.protocol import ProtocolError
        a = self.participant()
        pending = self.question(a)
        first = self.event()
        response = self.connection.dispatch("decision.abandon", {
            "session": first["session"], "questionId": first["questionId"],
            "challenge": first["challenge"]})
        self.assertEqual(response["status"], "pending")
        self.assertIsNone(decisions.read(first["decisionId"])["answer"])
        retried = self.question(a)
        self.assertEqual(retried["decision_id"], pending["decision_id"])
        self.assertNotEqual(retried["question_id"], pending["question_id"])
        second = self.event()
        self.assertNotEqual(first["questionId"], second["questionId"])
        with self.assertRaises(ProtocolError):
            self.answer(first)
        self.answer(second)

    def test_release_claim_rearms_notification_without_ack(self):
        from xsm import handoff
        a, b = self.open(), self.open("receiver")
        self.connection.dispatch("events.subscribe", {"session": b["session"]})
        self.operation(a, "xsm_send", target="ref:" + b["ref"], text="retry delivery", wait=0)
        self.assertEqual(len(list(self.connection.events())), 1)
        claim = self.operation(b, "xsm_inbox")["claims"][0]
        result = self.connection.dispatch("inbox.release", {"session": b["session"], "tokens": [claim["token"]]})
        self.assertEqual(result["released"], [claim["id"]])
        record = self.connection.sessions[b["session"]].record
        self.assertEqual(handoff.status(record, claim["id"])["status"], "pending")
        self.assertEqual(len(list(self.connection.events())), 1)
