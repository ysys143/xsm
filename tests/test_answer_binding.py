"""Issue #25, what binding keeps: one answer, one decision, nothing lost in silence.

test_approval_binding covers the fan-out itself; this covers the ways round it (a
reply flag, a request, an old hook) and the ways it could cost the person a second
answer (a target named without a mark, a question asked before its ask)."""
import json
import os
import unittest
from unittest import mock

from tests import test_person_decisions, test_xsm


class _Asks(test_person_decisions.AskHelpers, test_xsm.TempState):
    def setUp(self):
        super().setUp()
        global consent, paths
        from xsm import consent, paths
        self.assertEqual(paths.HOME, self.tmp)
        consent.supplied = None

    def tearDown(self):
        consent.supplied = None
        super().tearDown()

    def asks(self, *targets):
        for target in targets:
            consent.ask(self.me, "join", target)
        return {paths.read_json(p)["target"]: (p, paths.read_json(p))
                for p in consent.pending_files(self.me["ref"])}

    def say(self, text):
        consent.record(self.me, {"hook_event_name": "UserPromptSubmit", "prompt": text})

    def question(self, question, answer):
        consent.record(self.me, {"hook_event_name": "PostToolUse", "tool_name": "AskUserQuestion",
                                 "tool_use_id": "toolu_%s" % abs(hash(question)),
                                 "tool_response": {"answers": {question: answer}}})

    def go(self, target):
        """Show, then pass the show delay, then go."""
        consent.take_or_request(self.me, "join", target)
        for p in consent.pending_files(self.me["ref"]):
            entry = paths.read_json(p)
            if entry and entry.get("shown_t"):
                entry["shown_t"] -= consent.SHOW_DELAY + 1
                paths.write_json(p, entry)
        return consent.take_or_request(self.me, "join", target)


class MarkTest(_Asks):
    def test_the_refusal_hands_the_agent_the_mark(self):
        pending = self.asks("alpha")
        consent.take_or_request(self.me, "join", "alpha")
        mark = "[xsm:%s]" % pending["alpha"][1]["ask_id"]
        self.assertIn(mark, consent.asks("Joining alpha", runtime="codex"))

    def test_a_form_that_fell_back_hands_over_the_mark_too(self):
        consent.ask(self.me, "join", "alpha")
        entry = paths.read_json(consent.pending_files(self.me["ref"])[0])
        self.assertIn(entry["ask_id"], consent.in_words("xsm join alpha", True, "codex"))

    def test_codex_is_told_the_tool_that_works_and_the_one_that_does_not(self):
        told = consent.how("codex")
        self.assertIn("request_user_input_async", told)
        self.assertIn("never the synchronous request_user_input", told)
        self.assertIn("Plan mode", told)

    def test_a_marked_answer_reaches_its_ask_and_only_that(self):
        pending = self.asks("alpha", "beta", "gamma")
        self.question("[xsm:%s] Join?" % pending["alpha"][1]["ask_id"], "Yes")
        self.assertIn("Yes", paths.read_json(pending["alpha"][0])["verdict"])
        self.assertIsNone(paths.read_json(pending["beta"][0])["verdict"])
        self.assertIsNone(paths.read_json(pending["gamma"][0])["verdict"])

    def test_a_stale_mark_does_not_fall_through_to_the_name(self):
        pending = self.asks("alpha")
        stale = pending["alpha"][1]["ask_id"]
        consent.drop_request(self.me, stale)
        fresh = self.asks("alpha")
        self.question("[xsm:%s] Join alpha?" % stale, "Yes")
        self.assertIsNone(paths.read_json(fresh["alpha"][0])["verdict"])
        self.assertIn("expired or is not known", consent.pending_status(self.me)["unbound"][-1]["reason"])

    def test_a_plain_answer_can_carry_the_mark(self):
        pending = self.asks("alpha", "beta")
        self.say("[xsm:%s] yes" % pending["beta"][1]["ask_id"])
        self.assertIn("yes", paths.read_json(pending["beta"][0])["verdict"])
        self.assertIsNone(paths.read_json(pending["alpha"][0])["verdict"])


class NamedTest(_Asks):
    def test_a_question_that_names_one_target_needs_no_mark(self):
        pending = self.asks("alpha", "beta")
        self.question("Join alpha?", "Yes")
        self.assertIn("Yes", paths.read_json(pending["alpha"][0])["verdict"])
        self.assertIsNone(paths.read_json(pending["beta"][0])["verdict"])

    def test_a_question_that_names_two_targets_binds_to_neither(self):
        pending = self.asks("alpha", "beta")
        self.question("Join alpha and beta?", "Yes")
        self.assertIsNone(paths.read_json(pending["alpha"][0])["verdict"])
        self.assertIsNone(paths.read_json(pending["beta"][0])["verdict"])

    def test_plain_words_that_name_one_target_bind_to_it(self):
        pending = self.asks("alpha", "beta")
        self.say("beta는 해도 돼")
        self.assertIn("beta", paths.read_json(pending["beta"][0])["verdict"])
        self.assertIsNone(paths.read_json(pending["alpha"][0])["verdict"])

    def test_this_session_names_nothing_in_a_question(self):
        p = consent._pending_path(self.me["ref"], "publishask")
        paths.write_json(p, {"verb": "publish", "target": "bee", "t": consent.time.time(),
                             "session_id": str(self.me.get("session_id") or ""), "ask_id": "a1",
                             "marked": True, "verdict": None})
        self.question("이 세션을 끝낼까요?", "Yes")
        self.assertIsNone(paths.read_json(p)["verdict"])

    def test_an_ask_from_before_marks_keeps_its_one_open_answer(self):
        pending = self.asks("alpha")
        p, entry = pending["alpha"]
        entry.pop("marked")
        paths.write_json(p, entry)
        self.question("Go ahead?", "Yes")
        self.assertEqual(paths.read_json(p)["answer_binding"], "single-open-unbound")


class OneAnswerOneDecisionTest(_Asks):
    def test_ambiguous_words_cannot_come_back_as_a_reply(self):
        pending = self.asks("alpha", "beta")
        self.say("응")
        consent.supplied = "응"
        reply, go, _ = consent.take_or_request(self.me, "join", "alpha")
        self.assertIsNone(reply)
        self.assertFalse(go)
        self.assertIsNone(paths.read_json(pending["alpha"][0])["verdict"])

    def test_words_bound_to_one_ask_cannot_be_given_for_another(self):
        pending = self.asks("alpha")
        self.say("응")
        self.assertEqual(paths.read_json(pending["alpha"][0])["verdict"], "응")
        consent.clear_request(self.me, "join", "alpha")
        consent.supplied = "응"
        reply, go, _ = consent.take_or_request(self.me, "join", "beta")
        self.assertIsNone(reply)
        self.assertFalse(go)

    def test_a_closed_ask_spends_its_reply(self):
        self.asks("alpha")
        self.say("응")
        consent.clear_request(self.me, "join", "alpha")
        kept = paths.read_json(consent._recent_path(self.me["ref"]))["prompts"]
        self.assertTrue(kept[-1].get("used"))

    def test_a_request_that_answered_one_ask_does_not_open_another(self):
        pending = self.asks("alpha", "beta")
        self.say("alpha 합류해줘")
        self.assertIn("alpha", paths.read_json(pending["alpha"][0])["verdict"])
        reply, go, _ = consent.take_or_request(self.me, "leave", "alpha")
        self.assertIsNone(reply)
        self.assertFalse(go)

    def test_an_older_hooks_fanned_out_reply_passes_neither(self):
        pending = self.asks("alpha", "beta")
        for p, entry in pending.values():
            entry.update(verdict="응", verdict_t=consent.time.time(), shown=False)
            entry.pop("answer_binding", None)
            paths.write_json(p, entry)
        reply, go, _ = consent.take_or_request(self.me, "join", "alpha")
        self.assertIsNone(reply)
        self.assertFalse(go)
        self.assertIn("older hook", consent.pending_note)

    def test_one_decision_asked_twice_counts_as_one(self):
        first = consent._pending_path(self.me["ref"], "peer1")
        second = consent._pending_path(self.me["ref"], "peer2")
        for p, ask in ((first, "a1"), (second, "a2")):
            paths.write_json(p, {"verb": "link", "target": "/x/repo", "here": None, "marked": True,
                                 "t": consent.time.time(), "ask_id": ask, "verdict": None,
                                 "session_id": str(self.me.get("session_id") or "")})
        self.say("yes")
        self.assertEqual(paths.read_json(first)["verdict"], "yes")
        self.assertEqual(paths.read_json(second)["verdict"], "yes")


class RefusalStandsTest(_Asks):
    def test_a_no_on_the_ask_is_not_replaced_by_earlier_words(self):
        """Security review: `--reply` with earlier words turned the person's no into a yes.
        These name the target, so only the kept answer stands in their way."""
        self.say("alpha looks good")
        pending = self.asks("alpha")
        self.say("no, do not do that")
        consent.supplied = "alpha looks good"
        reply, go, _ = consent.take_or_request(self.me, "join", "alpha")
        self.assertEqual(reply, "no, do not do that")
        self.assertFalse(go)
        self.assertEqual(paths.read_json(pending["alpha"][0])["verdict"], "no, do not do that")

    def test_after_a_refusal_earlier_words_stand_for_nothing(self):
        self.say("ok thanks, run the tests")
        consent.spend_recent(self.me)
        consent.supplied = "ok thanks"
        reply, go, _ = consent.take_or_request(self.me, "join", "alpha")
        self.assertIsNone(reply)
        self.assertFalse(go)

    def test_two_calls_of_a_form_tool_are_two_decisions(self):
        """Security review: one yes made two grants, the reason told apart two calls."""
        for key, decision in (("one", "d1"), ("two", "d2")):
            paths.write_json(consent._pending_path(self.me["ref"], key), {
                "verb": "grant", "target": "same", "here": None, "marked": True, "ask_id": key,
                "t": consent.time.time(), "verdict": None, "binding": {"mcp_decision": decision},
                "session_id": str(self.me.get("session_id") or "")})
        self.say("yes")
        verdicts = [paths.read_json(p)["verdict"] for p in consent.pending_files(self.me["ref"])]
        self.assertEqual(verdicts, [None, None])


class NothingLostTest(_Asks):
    def test_no_after_two_asks_is_shown_with_the_yes_before_it(self):
        pending = self.asks("alpha", "beta")
        self.question("[xsm:%s] Join?" % pending["alpha"][1]["ask_id"], "Yes")
        consent.take_or_request(self.me, "join", "alpha")
        self.say("취소해")
        entry = paths.read_json(pending["alpha"][0])
        self.assertFalse(entry["shown"])
        reply, go, kept = consent.take_or_request(self.me, "join", "alpha")
        self.assertFalse(go)
        consent.pending_note = None
        self.assertIn("취소해", consent.shown_refusal(reply, "joining", kept))

    def test_a_new_request_does_not_cost_the_reply_already_kept(self):
        pending = self.asks("alpha", "beta")
        self.question("[xsm:%s] Join?" % pending["alpha"][1]["ask_id"], "Yes")
        self.say("gamma 합류해줘")
        self.assertIn("Yes", paths.read_json(pending["alpha"][0])["verdict"])
        reply, go, _ = consent.take_or_request(self.me, "join", "gamma")
        self.assertIn("gamma", reply)
        self.assertFalse(go)

    def test_an_answer_that_bound_to_nothing_reaches_the_next_refusal_once(self):
        self.asks("alpha", "beta")
        self.question("Run tests?", "Yes")
        consent.take_or_request(self.me, "join", "alpha")
        self.assertIn("Run tests?", consent.asks("Joining alpha"))
        consent.take_or_request(self.me, "join", "alpha")
        self.assertNotIn("Run tests?", consent.asks("Joining alpha"))

    def test_a_team_decisions_answer_is_no_stray_answer(self):
        self.question("[xsm-decision:abc] Ship?", "ship")
        self.assertEqual(consent.pending_status(self.me)["unbound"], [])

    def test_a_team_decisions_answer_approves_no_permission_it_names(self):
        pending = self.asks("alpha")
        self.question("[xsm-decision:abc] Should the team drop alpha?", "Yes")
        self.assertIsNone(paths.read_json(pending["alpha"][0])["verdict"])

    def test_a_question_about_something_else_with_nothing_open_is_not_reported(self):
        self.question("Which database?", "postgres")
        consent.take_or_request(self.me, "join", "alpha")
        self.assertIsNone(consent.pending_note)

    def test_an_answer_without_structure_is_kept_and_applies_to_nothing(self):
        pending = self.asks("alpha")
        consent.record(self.me, {"hook_event_name": "PostToolUse", "tool_name": "AskUserQuestion",
                                 "tool_response": "Yes"})
        self.assertIsNone(paths.read_json(pending["alpha"][0])["verdict"])
        self.assertEqual(consent.pending_status(self.me)["unbound"][0]["answer"], "Yes")

    def test_an_expired_diagnostic_is_pruned(self):
        consent._unbound(self.me, "Yes", "Q", None, "unmatched")
        p = paths.path(consent.ASKED, self.me["ref"] + ".unbound.json")
        saved = paths.read_json(p)
        saved["answers"][0]["t"] -= consent.TTL + 1
        paths.write_json(p, saved)
        consent.prune()
        self.assertFalse(os.path.exists(p))

    def test_answers_are_selected_under_the_conversations_lock(self):
        pending = self.asks("alpha")
        real, taken = consent._strict_locked, []

        def spy(path, wait=None):
            taken.append(path)
            return real(path, wait)
        with mock.patch.object(consent, "_strict_locked", spy):
            self.say("yes")
        self.assertIn("consent-bindings", taken[0])
        self.assertEqual(paths.read_json(pending["alpha"][0])["verdict"], "yes")

    def test_an_older_hook_cannot_move_a_reply_from_one_ask_to_the_other(self):
        pending = self.asks("alpha", "beta")
        for p, entry in pending.values():
            entry.update(verdict="yes", verdict_t=consent.time.time(), shown=False)
            entry.pop("answer_binding", None)
            paths.write_json(p, entry)
        consent.take_or_request(self.me, "join", "alpha")
        self.assertIsNone(paths.read_json(pending["beta"][0])["verdict"])
        self.assertIsNone(consent.take_or_request(self.me, "join", "beta")[0])

    def test_a_question_item_claimed_by_question_blocks_older_readers(self):
        marker = consent.claim_answer(self.me, "item", "digest-1", "owner-1")
        self.assertTrue(marker)
        self.assertTrue(paths.read_json(consent.native_answer_path(self.me, "item"))["consumed"])

    def test_a_form_closed_meanwhile_takes_its_ask_with_it(self):
        from xsm import decisions
        binding = {"mcp_decision": "d1"}
        p = consent._pending_path(self.me["ref"], consent.digest(
            "join", "alpha", json.dumps(binding, sort_keys=True)))
        paths.write_json(p, {"verb": "join", "target": "alpha", "here": None, "ask_id": "a1", "marked": True,
                             "t": consent.time.time(), "verdict": "yes", "verdict_t": consent.time.time(),
                             "shown": True, "shown_t": 0, "answer_binding": "request-marker",
                             "binding": binding, "session_id": str(self.me.get("session_id") or "")})
        record = {"owner": decisions.owner(self.me), "generation": {}, "status": "denied"}
        with mock.patch.object(decisions, "read", return_value=record):
            self.assertEqual(consent.take_or_request(self.me, "join", "alpha", binding=binding)[:2],
                             (None, False))
        self.assertFalse(paths.read_json(p).get("verdict"))

    def test_two_peers_of_one_name_are_two_decisions(self):
        for key, pair in (("one", ["a", "b"]), ("two", ["a", "c"])):
            paths.write_json(consent._pending_path(self.me["ref"], key), {
                "verb": "collaborate", "target": "bee", "here": None, "marked": True, "ask_id": key,
                "t": consent.time.time(), "verdict": None, "binding": {"pair": pair},
                "session_id": str(self.me.get("session_id") or "")})
        self.say("yes")
        verdicts = [paths.read_json(p)["verdict"] for p in consent.pending_files(self.me["ref"])]
        self.assertEqual(verdicts, [None, None])

    def test_an_answer_after_expiry_says_so(self):
        pending = self.asks("alpha")
        p, entry = pending["alpha"]
        question = "[xsm:%s] Join?" % entry["ask_id"]
        entry["t"] -= consent.ASK_MAX + 1
        paths.write_json(p, entry)
        self.question(question, "Yes")
        consent.take_or_request(self.me, "join", "alpha")
        self.assertIn("expired", consent.pending_note)

    def test_a_question_asked_before_its_ask_counts_once_by_name(self):
        self.question("Join alpha?", "Yes")
        reply, go, _ = consent.take_or_request(self.me, "join", "alpha")
        self.assertIn("Yes", reply)
        self.assertFalse(go)
        self.assertEqual(consent.pending_status(self.me)["unbound"], [])
        self.assertTrue(self.go("alpha")[1])
        self.assertIsNone(consent.take_or_request(self.me, "join", "alpha")[0])

    def test_a_question_asked_before_its_ask_is_no_answer_to_another(self):
        self.question("Join alpha?", "Yes")
        self.assertIsNone(consent.take_or_request(self.me, "join", "beta")[0])

    def test_a_stale_ask_can_be_closed(self):
        pending = self.asks("alpha", "beta")
        self.assertTrue(consent.drop_request(self.me, "[xsm:%s]" % pending["alpha"][1]["ask_id"]))
        self.say("응")
        self.assertEqual(paths.read_json(pending["beta"][0])["verdict"], "응")
        self.assertFalse(consent.drop_request(self.me, "[xsm:unknown]"))

    def test_a_double_hook_keeps_one_diagnostic(self):
        self.asks("alpha", "beta")
        self.say("응")
        self.say("응")
        self.assertEqual(len(consent.pending_status(self.me)["unbound"]), 1)


class NativeTagTest(_Asks):
    """The form measured on 2026-10-31 (Codex 0.165, a direct answer in the TUI): one tag
    per question, the same call id, the index last."""

    def tag(self, call, index, question, answer):
        return ("<send_user_message_question_reply>\n%s\n</send_user_message_question_reply>" %
                json.dumps([{"answer": answer, "question": question, "questionItemId": json.dumps(
                    ["request_user_input_async", call, index], separators=(",", ":"))}]))

    def test_two_questions_of_one_call_arrive_apart_and_bind_apart(self):
        pending = self.asks("alpha", "beta")
        self.say(self.tag("call_1", 0, "[xsm:%s] one" % pending["alpha"][1]["ask_id"], "a"))
        self.say(self.tag("call_1", 1, "[xsm:%s] two" % pending["beta"][1]["ask_id"], "d"))
        self.assertEqual(paths.read_json(pending["alpha"][0])["verdict"], "a")
        self.assertEqual(paths.read_json(pending["beta"][0])["verdict"], "d")

    def test_an_unrelated_question_does_not_replace_the_reply(self):
        """0.5.1 did: `Multi two -> d` overwrote the verdict of an open link (2026-10-31)."""
        pending = self.asks("alpha")
        self.say(self.tag("call_1", 0, "[xsm:%s] Join?" % pending["alpha"][1]["ask_id"], "yes"))
        self.say(self.tag("call_2", 1, "Multi two", "d"))
        self.assertEqual(paths.read_json(pending["alpha"][0])["verdict"], "yes")


class CodexReachTest(unittest.TestCase):
    def test_no_tool_is_refused_before_it_reaches_the_person(self):
        """Codex under approval policy never refuses an unannotated tool outright, and
        none of the form tools or their recovery could be called (0.165, 2026-10-31)."""
        from xsm import mcp
        self.assertEqual([t["name"] for t in mcp.TOOLS if "annotations" not in t], [])


class UnattendedTest(_Asks):
    def test_a_background_worker_is_known_by_its_record_without_the_environment(self):
        from xsm import workers
        worker = {"name": "w", "mode": "background", "parent_ref": "abc123", "pid": 1}
        with mock.patch.dict(os.environ), mock.patch.object(workers, "for_session", return_value=worker), \
                mock.patch.object(workers, "state", return_value="running"):
            os.environ.pop("XSM_WORKER", None)
            self.assertEqual(consent.take_or_request(self.me, "publish", "bee"), (None, False, False))
            self.assertFalse(consent.ask(self.me, "join", "alpha"))
            self.assertIn("ref:abc123", consent.cannot_keep("Publishing", None, self.me))

    def test_an_owned_worker_is_unattended_too(self):
        from xsm import workers
        with mock.patch.dict(os.environ), mock.patch.object(
                workers, "for_session", return_value={"name": "w", "mode": "owned"}):
            os.environ.pop("XSM_WORKER", None)
            self.assertTrue(consent.unattended(self.me))

    def test_a_person_who_resumed_a_finished_worker_is_that_sessions_person(self):
        from xsm import workers
        with mock.patch.dict(os.environ), mock.patch.object(
                workers, "for_session", return_value={"name": "w", "mode": "background"}), \
                mock.patch.object(workers, "state", return_value="gone"):
            os.environ.pop("XSM_WORKER", None)
            self.assertIsNone(consent.unattended(self.me))

    def test_a_pane_worker_has_its_person(self):
        from xsm import workers
        with mock.patch.dict(os.environ, {"XSM_WORKER": "p"}), \
                mock.patch.object(workers, "load", return_value={"mode": "pane"}):
            self.assertIsNone(consent.unattended(self.me))


if __name__ == "__main__":
    unittest.main()
