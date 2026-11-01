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
