"""Selected-pair consent service integration; transport only is simulated.

All xsm imports belong inside functions: TempState reloads the package.
Permission acquisition always uses connect.select, never send's folder offer.
"""
import os
from unittest import mock

from tests import test_xsm


class SelectedConnectionTest(test_xsm.TempState):
    def setUp(self):
        super().setUp()
        from xsm import config, context, registry
        self.peers = []
        for name, folder in (("sender", "a"), ("target", "b"),
                             ("other", "b"), ("sender-neighbor", "a")):
            cwd = os.path.join(self.tmp, folder)
            os.makedirs(cwd, exist_ok=True)
            self.peers.append(registry.upsert(
                "codex", os.path.join(self.tmp, "codex-home"), name,
                os.getpid(), cwd, name=name))
        self.sender, self.target, self.other, self.neighbor = self.peers
        self.call = context.of_record(self.sender, basis=context.BASIS_SESSION)
        self.outside = [(a, b, config.scope_for(a, b)[0], config.scope_for(b, a)[0])
                        for a, b in ((self.sender, self.other),
                                     (self.neighbor, self.target),
                                     (self.target, self.other))]

    def _record(self, text):
        from xsm import consent
        consent.record(self.sender, {"hook_event_name": "UserPromptSubmit", "prompt": text})

    def _pending(self):
        from xsm import consent, paths
        files = consent.pending_files(self.sender["ref"])
        self.assertEqual(len(files), 1, files)
        return files[0], paths.read_json(files[0])

    def _waited(self):
        from xsm import consent, paths
        filename, entry = self._pending()
        entry["shown_t"] -= consent.SHOW_DELAY + 1
        paths.write_json(filename, entry)

    def _select(self):
        from xsm import connect
        return connect.select(self.sender, self.target, call=self.call)

    def _outside_unchanged(self, before):
        from xsm import config
        self.assertEqual(config.load(), before)
        for a, b, forward, reverse in self.outside:
            self.assertEqual(config.scope_for(a, b)[0], forward)
            self.assertEqual(config.scope_for(b, a)[0], reverse)

    def test_korean_selection_show_rerun_pair_and_message_roundtrip(self):
        from xsm import adapters, collaboration, config, consent, envelope, ledger, receive, send
        before = config.load()
        self._record("target이랑 붙어서 일하자")
        shown = self._select()
        self.assertEqual(shown["status"], "selection-required", shown)
        self.assertIn("target이랑 붙어서 일하자", shown["reason"])
        self.assertEqual(shown["handshake"], "not-started")
        self.assertIsNone(config.scope_for(self.sender, self.target)[0])
        filename, pending = self._pending()
        self.assertEqual(pending["verdict"], "target이랑 붙어서 일하자")
        self.assertEqual(pending["verb"], "collaborate")
        self._outside_unchanged(before)
        self._waited()
        applied = self._select()
        self.assertEqual(applied["status"], "permitted", applied)
        self.assertEqual(applied["handshake"], "not-started")
        scope = applied["scope"]
        # ADR-0025 decision 13: a connect makes a team of two.
        record0 = collaboration.scope_for(self.sender, self.target)
        self.assertEqual(scope, "team:pair-" + record0["id"][:10])
        for a, b in ((self.sender, self.target), (self.target, self.sender)):
            self.assertEqual(config.scope_for(a, b)[0], scope)
        record = collaboration.scope_for(self.sender, self.target)
        self.assertEqual(record["verdict"], "target이랑 붙어서 일하자")
        self.assertFalse(os.path.exists(filename))
        self.assertEqual(consent.pending_files(self.sender["ref"]), [])
        self.assertEqual(self._select()["scope"], scope)
        self.assertEqual(collaboration.scope_for(self.sender, self.target), record)
        self._outside_unchanged(before)
        # Only after select grants the pair, exercise the actual send/receive
        # services. No send is used to request or acquire permission.
        with mock.patch.object(adapters, "to_codex", return_value=None) as transport:
            request_id = None
            for a, b, body in ((self.sender, self.target, "작업 요청"),
                               (self.target, self.sender, "작업 회신")):
                result = send.send("ref:" + b["ref"], body, sender=a,
                                   kind="reply" if request_id else "task",
                                   reply_to=request_id)
                self.assertEqual(result.status, "sent-unconfirmed", result.reason)
                parsed = envelope.parse(transport.call_args.args[2])
                self.assertEqual(parsed.header["scope"], scope)
                self.assertEqual(parsed.header.get("reply-to"), request_id)
                self.assertEqual(parsed.body, body)
                texts = receive.take_inbox(b)
                self.assertEqual(len(texts), 1, texts)
                self.assertTrue(texts[0].endswith("\n\n" + body), texts)
                self.assertEqual(ledger.receipt_of(result.msg_id)["decision"], "delivered")
                self.assertEqual(receive.take_inbox(b), [])
                request_id = result.msg_id
            self.assertEqual(transport.call_count, 2)
        self._outside_unchanged(before)

    def test_pending_request_resumes_after_record_without_new_ask(self):
        from xsm import collaboration, config
        before = config.load()
        first = self._select()
        self.assertEqual(first["status"], "selection-required", first)
        filename, original = self._pending()
        self._record("target이랑 붙어서 일하자")
        shown = self._select()
        self.assertEqual(shown["status"], "selection-required", shown)
        self.assertIn("target이랑 붙어서 일하자", shown["reason"])
        resumed_filename, resumed = self._pending()
        self.assertEqual(resumed_filename, filename)
        for field in ("t", "target", "session_id", "binding"):
            self.assertEqual(resumed[field], original[field])
        self.assertIsNone(collaboration.scope_for(self.sender, self.target))
        self._waited()
        self.assertEqual(self._select()["status"], "permitted")
        self._outside_unchanged(before)

    def test_two_character_a1_selection_shows_then_applies_without_another_prompt(self):
        from xsm import collaboration, config, consent, registry
        before = config.load()
        self.target = registry.upsert(
            self.target["runtime"], self.target["home"], self.target["session_id"],
            os.getpid(), self.target["cwd"], name="a1")
        self.assertEqual(registry.by_session("codex", self.target["session_id"])["name"], "a1")
        # A single real user prompt, before any ask exists. No second record()
        # supplies a reply: the selection itself must be shown as the verdict.
        self.assertEqual(consent.pending_files(self.sender["ref"]), [])
        self._record("a1이랑 붙어서 일하자")
        shown = self._select()
        self.assertEqual(shown["status"], "selection-required", shown)
        self.assertIn('your user replied: "a1이랑 붙어서 일하자"', shown["reason"])
        self.assertNotIn("ask who to collaborate with", shown["reason"])
        filename, pending = self._pending()
        self.assertEqual(pending["verdict"], "a1이랑 붙어서 일하자")
        self.assertEqual(pending["via"], "request")
        self.assertTrue(pending["shown"])
        self.assertIsNone(config.scope_for(self.sender, self.target)[0])
        self._waited()
        applied = self._select()
        self.assertEqual(applied["status"], "permitted", applied)
        self.assertEqual(applied["handshake"], "not-started")
        record = collaboration.scope_for(self.sender, self.target)
        self.assertEqual(record["verdict"], "a1이랑 붙어서 일하자")
        self.assertEqual(config.scope_for(self.target, self.sender)[0], applied["scope"])
        self.assertFalse(os.path.exists(filename))
        self.assertEqual(consent.pending_files(self.sender["ref"]), [])
        self._outside_unchanged(before)

    def test_weak_call_context_refused_before_consent_or_pair_write(self):
        from xsm import collaboration, connect, consent, context
        weak = context.of_record(self.sender)
        self.assertFalse(weak.sure)
        self._record("target이랑 붙어서 일하자")
        result = connect.select(self.sender, self.target, call=weak)
        self.assertEqual(result["status"], "refused", result)
        self.assertIn("guess", result["reason"])
        self.assertEqual(consent.pending_files(self.sender["ref"]), [])
        self.assertIsNone(collaboration.scope_for(self.sender, self.target))

    def test_ended_target_refused_before_and_during_consent_apply(self):
        from xsm import collaboration, registry
        ended = dict(self.target, state="ended")
        with mock.patch.object(registry, "records", return_value=[self.sender, ended]):
            self.assertEqual(self._select()["status"], "refused")
        self.assertEqual(self._select()["status"], "selection-required")
        self._record("target이랑 붙어서 일하자")
        self.assertEqual(self._select()["status"], "selection-required")
        self._waited()
        live = dict(self.target, state="live")
        with mock.patch.object(registry, "records", side_effect=[
                [self.sender, live], [self.sender, ended]]):
            result = self._select()
        self.assertEqual(result["status"], "refused", result)
        self.assertIn("ended before applying", result["reason"])
        self.assertIsNone(collaboration.scope_for(self.sender, self.target))

    def test_clear_one_character_selection_works_but_a_plan_label_is_not_consent(self):
        from xsm import connect, consent, registry
        target = registry.upsert("codex", self.target["home"], self.target["session_id"],
                                 os.getpid(), self.target["cwd"], name="b")
        self._record("Use plan b for the migration")
        plain = connect.select(self.sender, target, call=self.call)
        self.assertEqual(plain["status"], "selection-required")
        self.assertNotIn("your user replied", plain["reason"])
        # A new user instruction clearly selects this exact displayed name.
        self._record("b랑 붙어서 일하자")
        shown = connect.select(self.sender, target, call=self.call)
        self.assertIn('your user replied: "b랑 붙어서 일하자"', shown["reason"])
        self._waited()
        self.assertEqual(connect.select(self.sender, target, call=self.call)["status"], "permitted")
