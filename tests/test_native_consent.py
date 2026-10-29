"""Exact native answer recovery goes through the ordinary consent path."""
import json
import os
import time
from unittest import mock
from tests.test_xsm import TempState


class NativeConsentTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import registry
        home = os.path.join(self.tmp, "codex-home")
        os.makedirs(home)
        self.me = registry.upsert("codex", home, "me", os.getpid(), self.tmp, name="me")
        self.there = os.path.join(self.tmp, "other")
        os.makedirs(self.there)
        self.rollout = os.path.join(home, "rollout.jsonl")
        self.lookup = mock.patch.object(registry, "codex_rollout", return_value=self.rollout)
        self.lookup.start()
        self.addCleanup(self.lookup.stop)

    def answer(self, target=None, role="user", bind=True):
        from datetime import datetime, timezone
        from xsm import consent
        self.stamp = datetime.now(timezone.utc).isoformat()
        question = "Connect with %s?" % (target or self.there)
        consent.take_or_request(self.me, "link", self.there, self.tmp)
        if bind:
            consent.bind_question(self.me, "link", self.there, "q1", self.tmp,
                                  question="Connect with %s?" % self.there)
        payload = [{"questionItemId": "q1", "answer": "yes, connect it",
                    "question": "Connect with %s?" % (target or self.there)}]
        with open(self.rollout, "w") as stream:
            for row in [
                {"type": "session_meta", "payload": {"id": "me"}},
                {"type": "response_item", "timestamp": self.stamp,
                 "payload": {"type": "message", "role": role, "content": [
                     {"type": "input_text", "text": '<send_user_message_question_reply>' +
                      json.dumps(payload) + '</send_user_message_question_reply>'}]}}]:
                stream.write(json.dumps(row) + "\n")

    def take(self):
        from xsm import consent
        consent.answer_request = "q1"
        return consent.take_or_request(self.me, "link", self.there, self.tmp)

    def test_actual_native_answer_is_shown_then_consumed_once(self):
        from xsm import consent, paths
        self.answer()
        verdict, go, note = self.take()
        self.assertEqual(verdict, "yes, connect it")
        self.assertFalse(go)
        self.assertIn("native-question-id", note)
        p = consent.pending_files(self.me["ref"])[0]
        entry = paths.read_json(p)
        self.assertEqual(entry["native_evidence"]["timestamp"], self.stamp)
        self.assertEqual(entry["native_evidence"]["native_role"], "user")
        entry["shown_t"] -= consent.SHOW_DELAY + 1
        paths.write_json(p, entry)
        self.assertTrue(self.take()[1])
        self.assertIsNone(self.take()[0], "a consumed native question cannot approve a new ask")

    def test_wrong_question_or_assistant_cannot_supply_approval(self):
        self.answer(target="/unrelated-folder")
        self.assertIsNone(self.take()[0])
        self.answer(role="assistant")
        self.assertIsNone(self.take()[0])

    def test_reimports_do_not_extend_the_application_window(self):
        from xsm import consent, paths
        self.answer()
        self.take()
        p = consent.pending_files(self.me["ref"])[0]
        entry = paths.read_json(p)
        marker = paths.read_json(entry["native_marker"])
        marker["recovered_at"] = time.time() - consent.TTL - 1
        paths.write_json(entry["native_marker"], marker)
        entry["verdict_t"] = marker["recovered_at"]
        paths.write_json(p, entry)
        self.assertIsNone(self.take()[0])

    def test_hook_consumed_answer_cannot_be_recovered_again(self):
        from xsm import consent, paths
        self.answer()
        with open(self.rollout) as stream:
            last = json.loads(stream.readlines()[-1])
        prompt = last["payload"]["content"][0]["text"]
        consent.record(self.me, {"hook_event_name": "UserPromptSubmit", "prompt": prompt})
        consent.answer_request = None
        consent.take_or_request(self.me, "link", self.there, self.tmp)
        p = consent.pending_files(self.me["ref"])[0]
        entry = paths.read_json(p)
        entry["shown_t"] -= consent.SHOW_DELAY + 1
        paths.write_json(p, entry)
        self.assertTrue(consent.take_or_request(self.me, "link", self.there, self.tmp)[1])
        self.assertIsNone(self.take()[0])

    def test_old_native_source_and_different_question_are_not_approval(self):
        self.answer()
        with open(self.rollout) as stream:
            rows = stream.readlines()
        old = json.loads(rows[-1]);old["timestamp"] = "2020-01-01T00:00:00Z"
        with open(self.rollout, "w") as stream:
            stream.write(rows[0] + json.dumps(old) + "\n")
        self.assertIsNone(self.take()[0])
        self.answer()
        with open(self.rollout) as stream:
            text = stream.read()
        with open(self.rollout, "w") as stream:
            stream.write(text.replace("Connect with", "Should I unlink"))
        self.assertIsNone(self.take()[0])

    def test_later_real_user_message_prevents_recovering_earlier_yes(self):
        from datetime import datetime, timezone
        self.answer()
        with open(self.rollout, "a") as stream:
            stream.write(json.dumps({"type": "response_item", "timestamp":
                datetime.now(timezone.utc).isoformat(), "payload": {"type": "message",
                "role": "user", "content": [{"type": "input_text", "text":
                "Wait, do NOT connect it."}]}}) + "\n")
        self.assertIsNone(self.take()[0])

    def test_cli_binds_native_question_and_applies_without_direct_binder_call(self):
        import contextlib, io
        from xsm import cli, consent, config, paths, registry, workers
        self.answer(bind=False)
        args = ["link", self.there, "--answer-request", "q1", "--question",
                "Connect with %s?" % self.there]
        with mock.patch.object(registry, "me", return_value=self.me), \
                mock.patch.object(workers, "human_terminal", return_value=False):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                code = cli.main(args)
            self.assertEqual(code, 2, out.getvalue())
            self.assertIn("native-question-id", out.getvalue())
            self.assertEqual(config.links(), [])
            p = consent.pending_files(self.me["ref"])[0]
            entry = paths.read_json(p)
            self.assertEqual(entry["question_request"], "q1")
            entry["shown_t"] -= consent.SHOW_DELAY + 1
            paths.write_json(p, entry)
            with contextlib.redirect_stdout(io.StringIO()):
                code = cli.main(args)
            self.assertEqual(code, 0)
            self.assertEqual(len(config.links()), 1)
