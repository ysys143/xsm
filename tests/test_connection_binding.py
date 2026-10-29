"""Approval must stay bound to the target originally presented."""
from tests import test_one_yes


class ConnectionBindingTest(test_one_yes._Sessions):
    def test_replaced_session_cannot_use_the_previous_targets_yes(self):
        from xsm import connect, config
        msg = {"body": "hello b", "kind": "note"}
        first = connect.offer(self.me, self.you, self.target, msg, "out of scope")
        self.assertFalse(first.go)
        self._reply("yes")
        shown = connect.offer(self.me, self.you, self.target, msg, "out of scope")
        self.assertFalse(shown.go)
        self._waited()
        replacement = dict(self.you, session_id="replacement-session")
        result = connect.offer(self.me, replacement, self.target, msg, "out of scope")
        self.assertFalse(result.go, result.text)
        self.assertEqual(config.links(), [],
                         "the old target's approval must not connect its replacement")

    def test_held_resume_does_not_requeue_an_already_delivered_message(self):
        from xsm import config, ledger, outbox, send
        config.add_link(self.a, self.b, "test consent")
        held = outbox.put(self.me, self.target, {"body": "hello b", "kind": "note"})
        scope, _ = config.scope_for(self.me, self.you)
        ledger.queued(held["id"], self.me, self.you, scope, "note", "hello b")
        ledger.receipt(held["id"], "delivered", self.you)
        before = ledger.status(held["id"])
        result = send.send(self.target, "hello b", sender=self.me, kind="note")
        self.assertEqual(result.status, "delivered")
        self.assertEqual(self.sent, [])
        self.assertEqual(ledger.status(held["id"]), before)

    def test_held_resume_rejects_a_different_target_before_rewriting_ledger(self):
        from xsm import config, ledger, outbox, send
        config.add_link(self.a, self.b, "test consent")
        held = outbox.put(self.me, self.target, {"body": "hello b", "kind": "note"})
        scope, _ = config.scope_for(self.me, self.you)
        previous = dict(self.you, ref="abcdef")
        ledger.queued(held["id"], self.me, previous, scope, "note", "hello b")
        before = ledger.status(held["id"])
        result = send.send(self.target, "hello b", sender=self.me, kind="note")
        self.assertEqual(result.status, "refused")
        self.assertEqual(ledger.status(held["id"]), before)
        self.assertEqual(self.sent, [])

    def test_structured_answer_only_updates_its_bound_question(self):
        from xsm import consent, paths
        consent.take_or_request(self.me, "link", self.b, self.a)
        other = self.b + "-other"
        import os
        os.makedirs(other)
        consent.take_or_request(self.me, "link", other, self.a)
        self.assertTrue(consent.bind_question(self.me, "link", self.b, "question-1", self.a))
        self.assertTrue(consent.bind_question(self.me, "link", other, "question-2", self.a))
        consent.note_verdict(self.me, "yes", request="question-1")
        entries = [paths.read_json(p) for p in consent.pending_files(self.me["ref"])]
        by_question = {e["question_request"]: e for e in entries}
        self.assertEqual(by_question["question-1"]["verdict"], "yes")
        self.assertIsNone(by_question["question-2"]["verdict"])
        shown, go, note = consent.take_or_request(self.me, "link", self.b, self.a)
        self.assertEqual(shown, "yes")
        self.assertFalse(go)
        self.assertIn("question-1 (question-id)", note)

    def test_empty_structured_answer_is_not_a_verdict(self):
        from xsm import consent
        self.assertEqual(consent.answer_reply(
            '<send_user_message_question_reply>[{"answer":"","questionItemId":"q"}]'
            '</send_user_message_question_reply>'), (None, None))

    def test_two_peers_in_one_folder_do_not_erase_each_others_answer(self):
        from xsm import connect, consent, paths
        msg = {"body": "hello b", "kind": "note"}
        connect.offer(self.me, self.you, self.target, msg, "out of scope")
        second = dict(self.you, session_id="second", ref="fabcde")
        connect.offer(self.me, second, "ref:fabcde", msg, "out of scope")
        self.assertEqual(len(consent.pending_files(self.me["ref"])), 2)
        self._reply("yes")
        connect.offer(self.me, self.you, self.target, msg, "out of scope")
        entries = [paths.read_json(p) for p in consent.pending_files(self.me["ref"])]
        self.assertEqual([e["verdict"] for e in entries], ["yes", "yes"])

    def test_explicit_folder_approval_can_finish_a_send(self):
        from xsm import connect, consent
        consent.take_or_request(self.me, "link", self.b, self.a)
        self._reply("yes")
        consent.take_or_request(self.me, "link", self.b, self.a)
        self._waited()
        result = connect.offer(self.me, self.you, self.target,
                               {"body": "hello b", "kind": "note"}, "out of scope")
        self.assertTrue(result.go, result.text)

    def test_empty_structured_payload_does_not_fall_back_to_raw_prompt(self):
        from xsm import consent, paths
        consent.take_or_request(self.me, "link", self.b, self.a)
        consent.record(self.me, {"hook_event_name": "UserPromptSubmit", "prompt":
            '<send_user_message_question_reply>[{"answer":"","questionItemId":"q"}]'
            '</send_user_message_question_reply>'})
        entries = [paths.read_json(p) for p in consent.pending_files(self.me["ref"])]
        self.assertEqual(len(entries), 1)
        self.assertIsNone(entries[0]["verdict"])

    def test_failed_application_keeps_the_same_approval_and_message_for_retry(self):
        from xsm import config, consent, outbox
        from unittest import mock
        _, text = self._send()
        original = self._held_id(text)
        self._reply("yes")
        self._send()
        self._waited()
        with mock.patch.object(config, "add_link", side_effect=ValueError("temporary failure")):
            code, failed = self._send()
        self.assertEqual(code, 2, failed)
        self.assertIn(original, failed)
        code, resumed = self._send()
        self.assertEqual(code, 3, resumed)
        self.assertIn(original, resumed)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(outbox._records(), [])
