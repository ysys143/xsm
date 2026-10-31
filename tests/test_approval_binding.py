"""Issue #25: answers belong to requests, not to a session's entire queue."""
import time
import unittest
import json
import os
from unittest import mock

from tests import test_person_decisions, test_xsm


class BindingTest(test_person_decisions.AskHelpers, test_xsm.TempState):
    def setUp(self):
        super().setUp()
        global consent, paths
        from xsm import consent, paths
        self.assertEqual(paths.HOME, self.tmp)

    def asks(self, *targets):
        for target in targets:
            consent.ask(self.me, "join", target)
        return {paths.read_json(p)["target"]: (p, paths.read_json(p))
                for p in consent.pending_files(self.me["ref"])}

    def test_plain_answer_does_not_fan_out(self):
        pending = self.asks("alpha", "beta")
        consent.record(self.me, {"hook_event_name": "UserPromptSubmit", "prompt": "yes"})
        self.assertTrue(all(paths.read_json(p)["verdict"] is None for p, _ in pending.values()))

    def test_missing_decision_id_does_not_cancel_unbound_permissions(self):
        self.asks("alpha", "beta")
        consent.cancel_bound_requests(self.me, None)
        self.assertEqual(len(consent.pending_status(self.me)["requests"]), 2)

    def test_expired_file_does_not_make_single_live_request_ambiguous(self):
        pending = self.asks("alpha", "beta")
        p, entry = pending["beta"]
        entry["t"] = time.time() - consent.ASK_MAX - 1
        paths.write_json(p, entry)
        consent.note_verdict(self.me, "yes")
        self.assertEqual(paths.read_json(pending["alpha"][0])["verdict"], "yes")

    def test_claude_questions_bind_independently(self):
        pending = self.asks("alpha", "beta")
        questions = {"Join %s? [xsm:%s]" % (target, entry["ask_id"]): answer
                     for target, (_, entry) in pending.items()
                     for answer in ["yes" if target == "alpha" else "no"]}
        consent.record(self.me, {"hook_event_name": "PostToolUse", "tool_name": "AskUserQuestion",
                                "tool_response": {"answers": questions}})
        self.assertIn("yes", paths.read_json(pending["alpha"][0])["verdict"])
        self.assertNotIn("no", paths.read_json(pending["alpha"][0])["verdict"])
        self.assertIn("no", paths.read_json(pending["beta"][0])["verdict"])

    def test_unrelated_structured_question_is_not_single_request_approval(self):
        pending = self.asks("alpha")
        consent.record(self.me, {"hook_event_name": "PostToolUse", "tool_name": "AskUserQuestion",
                                "tool_response": {"answers": {"Run tests?": "yes"}}})
        self.assertIsNone(paths.read_json(pending["alpha"][0])["verdict"])


    def test_native_questions_bind_independently_and_keep_unmatched_item(self):
        pending = self.asks("alpha", "beta")
        items = [{"questionItemId": target, "question": "Join? [xsm:%s]" % entry["ask_id"],
                  "answer": "yes" if target == "alpha" else "no"}
                 for target, (_, entry) in pending.items()]
        items.append({"questionItemId": "unrelated", "question": "Color?", "answer": "blue"})
        consent.record(self.me, {"hook_event_name": "UserPromptSubmit", "prompt":
            "<send_user_message_question_reply>" + json.dumps(items) + "</send_user_message_question_reply>"})
        self.assertEqual(paths.read_json(pending["alpha"][0])["verdict"], "yes")
        self.assertEqual(paths.read_json(pending["beta"][0])["verdict"], "no")
        self.assertEqual(consent.pending_status(self.me)["unbound"][0]["request"], "unrelated")

    def test_diagnostic_answers_do_not_cross_a_ref_collision(self):
        consent._unbound(self.me, "first session", "Q", "q1", "unmatched")
        other = dict(self.me, session_id="another-conversation")
        consent._unbound(other, "second session", "Q", "q2", "unmatched")
        self.assertEqual([a["answer"] for a in consent.pending_status(other)["unbound"]], ["second session"])
        self.assertEqual(consent.pending_status(self.me)["unbound"], [])

    def test_answer_claimed_by_a_pending_decision_cannot_authorize_a_permission(self):
        pending = self.asks("alpha")
        p, entry = pending["alpha"]
        question = "Join? [xsm:%s]" % entry["ask_id"]
        consent.note_verdict(self.me, "yes", request="shared-native-answer", question=question)
        consent.take_or_request(self.me, "join", "alpha")
        entry = paths.read_json(p)
        entry["shown_t"] -= consent.SHOW_DELAY + 1
        paths.write_json(p, entry)
        marker = consent.native_answer_path(self.me, "shared-native-answer")
        paths.write_json(marker, {"owner": "decision:another-operation", "consumed": False})
        self.assertFalse(consent.take_or_request(self.me, "join", "alpha")[1])

    def test_two_questions_sharing_one_native_item_can_each_be_consumed(self):
        pending = self.asks("alpha", "beta")
        for target, (p, entry) in pending.items():
            consent.note_verdict(self.me, "yes", request="same-native-item",
                                 question="Join %s? [xsm:%s]" % (target, entry["ask_id"]))
            consent.take_or_request(self.me, "join", target)
            shown = paths.read_json(p)
            shown["shown_t"] -= consent.SHOW_DELAY + 1
            paths.write_json(p, shown)
        self.assertTrue(all(consent.take_or_request(self.me, "join", target)[1] for target in pending))

    def test_a_pane_worker_keeps_the_form_fallback_for_its_person(self):
        from xsm import workers
        with mock.patch.dict(os.environ, {"XSM_WORKER": "pane-test"}), \
                mock.patch.object(workers, "load", return_value={"mode": "pane"}):
            self.assertIn("xsm_join MCP tool", consent.cannot_keep("joining", "xsm_join"))

    def test_status_does_not_delete_an_expired_request(self):
        pending = self.asks("alpha")
        p, entry = pending["alpha"]
        entry["t"] -= consent.ASK_MAX + 1
        paths.write_json(p, entry)
        from pathlib import Path
        before = Path(p).read_bytes()
        self.assertEqual(consent.pending_status(self.me)["requests"][0]["status"], "expired")
        self.assertEqual(Path(p).read_bytes(), before)

    def test_busy_binding_lock_does_not_record_a_verdict(self):
        pending = self.asks("alpha")
        with mock.patch.object(consent, "_lock", return_value=None):
            self.assertFalse(consent.note_verdict(self.me, "yes"))
        self.assertIsNone(paths.read_json(pending["alpha"][0])["verdict"])


if __name__ == "__main__":
    unittest.main()
