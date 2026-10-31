"""P07 lifecycle and actual MCP dispatch/stdio; no live model or external send."""
import io
import json
import os
import select
import subprocess
import sys
import time
from unittest import mock

from tests import test_xsm


def accepted(answer="approve", reviewer="user"):
    return {"result": {"action": "accept", "content": {"answer": answer},
                       "_meta": {"approvals_reviewer": reviewer}}}


class DecisionsTest(test_xsm.TempState):
    def setUp(self):
        super().setUp()
        from xsm import decisions
        self.d = decisions
        self.me = {"runtime": "codex", "home": self.tmp + "/profile", "session_id": "owner",
                   "pid": os.getpid(), "lstart": "fixture-generation", "cwd": self.tmp}
        self.scope = {"tool": "xsm_decide", "arguments": {"question": "Keep exact scope?"}, "cwd": self.tmp}
        self.generation = "generation-1"
        self.key = decisions.invocation(self.me, "xsm_decide", self.scope["arguments"], self.generation)
        self.question = "질문 원문\n  공백과 `기호`를 보존할까요?  "

    def begin(self, **kwargs):
        options = dict(now=100, ttl=30, waiter="first")
        options.update(kwargs)
        return self.d.begin(self.key, self.me, self.scope, self.generation, self.question, **options)

    def answer(self, **kwargs):
        self.begin()
        self.d.display(self.key, "first", self.question, "mcp-elicitation")
        return self.d.response(self.key, accepted(), "mcp-elicitation", now=101, **kwargs)

    def test_exact_owner_scope_generation_and_original_question_are_bound(self):
        record = self.begin()
        self.assertEqual(record["question"], self.question)
        self.assertEqual(record["owner"], self.d.owner(self.me))
        for owner in (dict(self.me, runtime="claude"), dict(self.me, home=self.tmp + "/other"),
                      dict(self.me, session_id="other")):
            with self.subTest(owner=owner), self.assertRaises(ValueError):
                self.d.begin(self.key, owner, self.scope, self.generation, self.question, now=101)
        for scope, generation, question in ((dict(self.scope, cwd=self.tmp + "/other"), self.generation, self.question),
                (self.scope, "generation-2", self.question), (self.scope, self.generation, self.question + "changed")):
            with self.subTest(scope=scope, generation=generation), self.assertRaises(ValueError):
                self.d.begin(self.key, self.me, scope, generation, question, now=101)
        self.assertIsNone(self.d.read(self.key)["application"])

    def test_changed_scope_or_generation_cannot_apply_an_answer(self):
        for scope, generation in ((dict(self.scope, target="different"), self.generation),
                                  (self.scope, "generation-2")):
            with self.subTest(scope=scope, generation=generation):
                # A fresh key per independent attempted application.
                self.key = self.d.digest([self.key, scope, generation])
                self.answer()
                result = self.d.applied(self.key, "must not apply", generation, scope, now=102)
                self.assertEqual(result["status"], "superseded")
                self.assertIsNone(result["application"])

    def test_display_digest_and_verbatim_answer_preserve_originals(self):
        self.begin()
        shown = self.question[:8] + "…"
        self.assertTrue(self.d.display(self.key, "first", shown, "mcp-elicitation", complete=False))
        reply = accepted("  승인합니다\n원문 그대로  ")
        record = self.d.response(self.key, reply, "mcp-elicitation", source_id="native-reply-7", now=101)
        self.assertEqual(record["question"], self.question)
        self.assertEqual(record["display"]["text"], shown)
        self.assertNotEqual(record["question_digest"], record["display"]["digest"])
        self.assertEqual(record["answer"]["reply"], reply)
        self.assertEqual(record["answer"]["source_id"], "native-reply-7")
        self.assertIsNone(record["display"]["human_saw"])
        with self.assertRaises(ValueError):
            self.d.applied(self.key, "not allowed", self.generation, self.scope, now=102)

    def test_reported_partial_display_never_upgrades_truncation_to_complete(self):
        self.begin()
        shown = self.question[:8] + "…"
        self.d.display(self.key, "first", shown, "mcp-elicitation", complete=False)
        record = self.d.response(self.key, accepted(), "mcp-elicitation", displayed=shown, now=101)
        self.assertFalse(record["display"]["complete"], "matching the truncated text is not a complete display")
        with self.assertRaises(ValueError):
            self.d.applied(self.key, "not allowed", self.generation, self.scope, now=102)

    def test_different_reported_display_refuses_application(self):
        self.answer(displayed="a different question")
        record = self.d.read(self.key)
        self.assertFalse(record["display"]["complete"])
        self.assertNotEqual(record["display"]["digest"], record["display"]["reported_digest"])
        with self.assertRaises(ValueError):
            self.d.applied(self.key, "not allowed", self.generation, self.scope, now=102)

    def test_late_answer_is_recorded_but_expired_never_applies(self):
        self.begin()
        self.d.display(self.key, "first", self.question, "mcp-elicitation")
        reply = accepted("late real answer")
        record = self.d.response(self.key, reply, "native-user", source_id="late-native", now=131)
        self.assertEqual(record["status"], "expired")
        self.assertEqual(record["answer"]["reply"], reply)
        result = self.d.applied(self.key, "must not happen", self.generation, self.scope, now=132)
        self.assertEqual(result["status"], "expired")
        self.assertIsNone(result["application"])

    def test_expiry_between_answer_and_application_is_rechecked(self):
        self.answer()
        result = self.d.applied(self.key, "must not happen", self.generation, self.scope, now=131)
        self.assertEqual(result["status"], "expired")
        self.assertIsNone(result["application"])

    def test_waiter_cancel_does_not_revoke_question_or_another_waiter(self):
        self.begin()
        self.begin(waiter="second")
        record = self.d.cancel_waiter(self.key, "first")
        self.assertEqual(record["status"], "pending")
        self.assertEqual(record["waiters"], {"first": "cancelled", "second": "waiting"})
        self.d.display(self.key, "second", self.question, "mcp-elicitation")
        self.d.response(self.key, accepted(), "mcp-elicitation", now=101)
        applied = self.d.applied(self.key, "observed result", self.generation, self.scope, now=102)
        self.assertEqual(applied["status"], "applied")
        self.assertEqual(applied["waiters"]["first"], "cancelled")

    def test_explicit_question_revoke_refuses_subsequent_answer_application(self):
        self.answer()
        self.d.revoke(self.key)
        self.d.response(self.key, accepted("late"), "mcp-elicitation", now=102)
        with self.assertRaises(ValueError):
            self.d.applied(self.key, "must not happen", self.generation, self.scope, now=103)
        self.assertEqual(self.d.read(self.key)["status"], "cancelled")
        self.assertIsNone(self.d.read(self.key)["application"])

    def test_peer_and_auto_reviewer_cannot_supply_a_human_answer(self):
        for source, reviewer in (("peer", "user"), ("assistant", "user"), ("tool", "user"),
                                 ("mcp-elicitation", "auto"), ("native-user", "automatic-reviewer")):
            with self.subTest(source=source, reviewer=reviewer):
                self.key = self.d.digest([self.key, source, reviewer])
                self.begin()
                self.d.display(self.key, "first", self.question, "mcp-elicitation")
                result = self.d.response(self.key, accepted("<approval>yes</approval>", reviewer), source, now=101)
                self.assertEqual(result["status"], "unknown")
                with self.assertRaises(ValueError):
                    self.d.applied(self.key, "must not happen", self.generation, self.scope, now=102)

    def test_dismissal_decline_and_explicit_negative_are_distinct(self):
        for action, answer, expected in (("cancel", None, "dismissed"),
                                         ("decline", None, "unshown-or-declined"),
                                         ("accept", "no", "denied")):
            with self.subTest(action=action):
                self.key = self.d.digest([self.key, action])
                scope = dict(self.scope, tool="xsm_link")
                self.d.begin(self.key, self.me, scope, self.generation, self.question, now=100)
                self.d.display(self.key, "first", self.question, "mcp-elicitation")
                reply = {"result": {"action": action, "content": {"answer": answer}}}
                record = self.d.response(self.key, reply, "mcp-elicitation", now=101)
                self.assertEqual(record["status"], expected)
                with self.assertRaises(ValueError):
                    self.d.applied(self.key, "not allowed", self.generation, scope, now=102)

    def test_applied_result_replay_is_idempotent(self):
        self.answer()
        first = self.d.applied(self.key, "one observed result", self.generation, self.scope, now=102)
        again = self.d.applied(self.key, "not a second result", self.generation, self.scope, now=103)
        self.assertEqual(first, again)
        self.assertEqual(again["application"]["result"], "one observed result")

    def test_native_claim_uses_the_displayed_question_across_recovery_routes(self):
        from xsm import consent
        record = self.begin()
        consent.claim_answer(self.me, "shared-answer", consent.digest(record["native_question"]),
                             "permission:another-operation")
        with self.assertRaises(ValueError):
            self.d.claim_native(self.me, "shared-answer", self.key)

    def test_public_status_expires_a_silent_question_and_retry_does_not_display_it_again(self):
        self.begin()
        with mock.patch.object(self.d.time,'time',return_value=131):
            self.assertEqual(self.d.public_status(self.me,self.key)['status'],'expired')
            self.assertEqual(self.d.public_status(self.me)['decisions'][0]['status'],'expired')
        record=self.d.begin(self.key,self.me,self.scope,self.generation,self.question,now=131)
        self.assertEqual(record['status'],'expired')
        self.assertFalse(self.d.display(self.key,'new-reader',self.question,'mcp-elicitation'))

    def test_clock_rollback_after_an_answer_does_not_apply_it(self):
        self.answer()
        result=self.d.applied(self.key,'must not apply',self.generation,self.scope,now=99)
        self.assertEqual(result['status'],'unknown')
        self.assertIsNone(result['application'])


class _DecisionWire:
    def __init__(self, testcase):
        self.test = testcase
        self.pending = bytearray()
        script = ('from xsm import mcp,registry\n'
                  's=mcp.Server()\n'
                  's.session=lambda: registry.by_session("codex","decision-owner")\n'
                  'raise SystemExit(s.serve())\n')
        self.proc = subprocess.Popen([sys.executable, "-u", "-c", script], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
                                     env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        testcase.addCleanup(self.close)

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill(); self.proc.wait(timeout=3)
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            stream.close()

    def send(self, value):
        self.proc.stdin.write((json.dumps(dict(jsonrpc="2.0", **value)) + "\n").encode())
        self.proc.stdin.flush()

    def read(self, timeout=5):
        deadline = time.monotonic() + timeout
        while b"\n" not in self.pending:
            left = deadline - time.monotonic()
            self.test.assertGreater(left, 0, "MCP response deadline exceeded")
            ready, _, _ = select.select([self.proc.stdout], [], [], left)
            self.test.assertTrue(ready, "MCP response not dispatched")
            chunk = os.read(self.proc.stdout.fileno(), 65536)
            self.test.assertTrue(chunk, "MCP stdio closed before the response")
            self.pending.extend(chunk)
        line, _, rest = self.pending.partition(b"\n")
        self.pending[:] = rest
        return json.loads(line)


class DecisionMcpTest(test_xsm.TempState):
    def setUp(self):
        super().setUp()
        from xsm import board, decisions, mcp, paths, registry, teams
        self.board, self.d, self.mcp, self.paths, self.registry = board, decisions, mcp, paths, registry
        home = self.tmp + "/profile"
        os.mkdir(home)
        registry.upsert("codex", home, "decision-owner", os.getpid(), self.tmp, name="fixture-owner")
        self.me = registry.by_session("codex", "decision-owner")
        teams.create(self.me, "core")       # its one team: where xsm_decide keeps the answer
        self.args = {"question": "원문 그대로 기록할까요?", "options": ["approve", "deny"],
                     "decision_key": "one-shared-human-decision"}

    def tool(self, mid, args=None):
        return {"id": mid, "method": "tools/call", "params": {
            "name": "xsm_decide", "arguments": dict(self.args if args is None else args)}}

    def records(self):
        return self.board.decisions("core")

    def decisions(self):
        from pathlib import Path
        return [json.loads(p.read_text()) for p in Path(self.paths.path(self.d.DIRECTORY)).glob("*.json")]

    def run_server(self, rows, before_answer=None, capabilities=None):
        initial = {"id": 0, "method": "initialize", "params": {
            "capabilities": {"elicitation": {}} if capabilities is None else capabilities, "clientInfo": {"name": "fixture-human-client"}}}
        inp = io.StringIO("".join(json.dumps(row) + "\n" for row in [initial] + rows))
        out = io.StringIO()
        server = self.mcp.Server(inp, out)
        server.session = lambda: self.registry.by_session("codex", "decision-owner")
        dispatch = server.dispatch
        def incoming(row):
            if row.get("id") == "xsm-1" and not row.get("method") and before_answer:
                before_answer()
            return dispatch(row)
        server.dispatch = incoming
        self.assertEqual(server.serve(), 0)
        self.assertIsNone(server.ctx)
        return [json.loads(line) for line in out.getvalue().splitlines()]

    def grant_call(self, mid):
        return {"id": mid, "method": "tools/call", "params": {"name": "xsm_grant", "arguments": {
            "runtime": "codex", "dir": self.tmp, "options": ["full_access"], "reason": "isolated fixture"}}}

    def test_mcp_grant_recovers_its_reply_without_bouncing_to_a_shell(self):
        from xsm import consent, workers
        self.run_server([self.grant_call(1)], capabilities={})
        consent.record(self.me, {"hook_event_name": "UserPromptSubmit", "prompt": "yes"})
        shown = self.run_server([self.grant_call(2)], capabilities={})
        self.assertIn("your user replied", json.dumps(shown))
        pending = consent.pending_files(self.me["ref"])[0]
        entry = self.paths.read_json(pending)
        entry["shown_t"] -= consent.SHOW_DELAY + 1
        self.paths.write_json(pending, entry)
        self.run_server([self.grant_call(3)], capabilities={})
        self.run_server([self.grant_call(4)], capabilities={})
        from pathlib import Path
        grants = list(Path(self.paths.path(workers.GRANTS)).glob("*.json"))
        self.assertEqual(len(grants), 1)
        record = self.decisions()[0]
        self.assertEqual(record["status"], "applied")
        self.assertEqual(record["permission_receipt"]["text"], "yes")
        self.assertEqual(record["application"]["source"], "input-consent")

    def test_cancelling_form_decision_clears_its_bound_reply_request(self):
        from xsm import consent
        self.run_server([self.grant_call(1)], capabilities={})
        record = self.decisions()[0]
        self.d.public_status(self.me, record["id"], cancel=True)
        self.assertEqual(consent.pending_status(self.me)["requests"], [])

    def test_changed_working_directory_does_not_replay_an_applied_result(self):
        self.run_server([self.tool(1), dict(id="xsm-1", **accepted())])
        self.assertEqual(len(self.records()), 1)
        changed = self.tmp + "/different-worktree"
        os.mkdir(changed)
        self.registry.upsert("codex", self.me["home"], "decision-owner", os.getpid(), changed,
                             name="fixture-owner")
        output = self.run_server([self.tool(2)], capabilities={})
        self.assertEqual(len(self.records()), 1, output)
        self.assertEqual(sorted(r["status"] for r in self.decisions()), ["applied", "pending"])

    def test_implicit_team_is_fixed_before_the_native_question_is_asked(self):
        from xsm import teams, user_answers
        self.run_server([self.tool(1)], capabilities={})
        first = self.decisions()[0]
        self.assertEqual(first["scope"]["arguments"]["team"], "core")
        teams.remove(self.me, "core", teams.member_of(self.me), None)
        teams.create(self.me, "other-team")
        evidence = {"question": first["native_question"], "answer": "approve", "questionItemId": "q"}
        args = dict(self.args, answer_request="q", original_question=first["native_question"])
        with mock.patch.object(user_answers, "read_answer", return_value=evidence):
            output = self.run_server([self.tool(2, args)], capabilities={})
        self.assertEqual(self.board.decisions("other-team"), [], output)

    def test_mcp_can_read_pending_consent_without_a_shell(self):
        self.run_server([self.grant_call(1)], capabilities={})
        call = {"id": 2, "method": "tools/call", "params": {"name": "xsm_decision_status", "arguments": {
            "pending_consent": True}}}
        output = self.run_server([call], capabilities={})
        response = next(row for row in output if row.get("id") == 2)
        self.assertEqual(len(json.loads(response["result"]["content"][0]["text"])["requests"]), 1)

    def test_no_form_retains_request_then_reads_an_actual_native_fixture_file(self):
        from datetime import datetime, timezone
        from unittest.mock import patch
        self.run_server([self.tool(1)], capabilities={})
        self.assertEqual(self.decisions()[0]["status"], "pending")
        path = os.path.join(self.me["home"], "native-answer.jsonl")
        question = self.decisions()[0]["native_question"]
        answer = "<send_user_message_question_reply>" + json.dumps([
            {"questionItemId": "verified-q", "question": question, "answer": "approve"}]) + "</send_user_message_question_reply>"
        rows = [{"type": "session_meta", "payload": {"id": self.me["session_id"]}},
                {"type": "response_item", "timestamp": datetime.now(timezone.utc).isoformat(),
                 "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": answer}]}}]
        with open(path, "w") as stream:
            stream.write("".join(json.dumps(row) + "\n" for row in rows))
        args = dict(self.args, answer_request="verified-q", original_question=question)
        with patch.object(self.registry, "codex_rollout", return_value=path):
            output = self.run_server([self.tool(2, args)], capabilities={})
        self.assertEqual(len(self.records()), 1, output)
        self.assertEqual(self.records()[0]["via"], "native-user")
        self.assertFalse(any(row.get("method") == "elicitation/create" for row in output))

    def test_verified_native_answer_records_its_real_source_and_cannot_be_reused(self):
        from unittest.mock import patch
        from xsm import user_answers
        # Persisted 0.5.1 requests had no scoped native-question marker. They
        # still need the single-use claim when upgrading.
        other = dict(self.args, decision_key="another-request")
        self.run_server([self.tool(10), self.tool(11, other)], capabilities={})
        for record in self.decisions():
            record.pop("native_question", None)
            self.paths.write_json(self.d.filename(record["id"]), record)
        args = dict(self.args, answer_request="native-question", original_question=self.args["question"])
        evidence = {"question": self.args["question"], "answer": "approve", "questionItemId": "native-question"}
        with patch.object(user_answers, "read_answer", return_value=evidence):
            output = self.run_server([self.tool(1, args), self.tool(2, dict(args, decision_key="another-request"))])
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(self.records()[0]["via"], "native-user")
        self.assertFalse(any(r.get("method") == "elicitation/create" for r in output))
        second = next(r for r in output if r.get("id") == 2)
        self.assertTrue(second["result"].get("isError"), second)

    def test_scoped_native_question_cannot_be_imported_for_another_decision(self):
        from unittest.mock import patch
        from xsm import user_answers
        other = dict(self.args, decision_key="other-decision")
        self.run_server([self.tool(10), self.tool(11, other)], capabilities={})
        records = self.decisions()
        self.assertNotEqual(records[0]["native_question"], records[1]["native_question"])
        wrong = next(r["native_question"] for r in records if r["scope"]["arguments"]["decision_key"] == self.args["decision_key"])
        with patch.object(user_answers, "read_answer", return_value={"question": wrong, "answer": "approve", "questionItemId": "q"}):
            output = self.run_server([self.tool(12, dict(other, answer_request="q", original_question=wrong))], capabilities={})
        self.assertEqual(self.records(), [], output)

    def test_unknown_application_is_not_replayed_after_a_domain_error(self):
        from unittest.mock import patch
        with patch.object(self.board, "record_decision", side_effect=OSError("injected domain failure")):
            self.run_server([self.tool(1), dict(id="xsm-1", **accepted())])
        record = self.decisions()[0]
        self.assertEqual(record["status"], "unknown")
        self.assertEqual(record["application"]["phase"], "started")
        output = self.run_server([self.tool(2)])
        self.assertEqual(self.records(), [], output)
        self.assertFalse(any(row.get("method") == "elicitation/create" for row in output))

    def test_native_question_mismatch_does_not_record_or_open_a_form(self):
        from unittest.mock import patch
        from xsm import user_answers
        args = dict(self.args, answer_request="native-question", original_question=self.args["question"])
        with patch.object(user_answers, "read_answer", return_value={"question": "Different?", "answer": "approve"}):
            output = self.run_server([self.tool(1, args)])
        self.assertEqual(self.records(), [])
        self.assertFalse(any(r.get("method") == "elicitation/create" for r in output))

    def test_real_server_nested_duplicate_and_retry_show_one_form_append_one_decision(self):
        output = self.run_server([self.tool(1), self.tool(2), dict(id="xsm-1", **accepted()), self.tool(3)])
        forms = [row for row in output if row.get("method") == "elicitation/create"]
        self.assertEqual(len(forms), 1)
        self.assertEqual(len(self.records()), 1)
        record = self.decisions()[0]
        self.assertEqual(record["status"], "applied")
        self.assertEqual(self.records()[0]["answer"], "approve")
        self.assertEqual(record["question"], self.args["question"])

    def test_real_server_generation_change_refuses_domain_application(self):
        def change():
            raw = self.paths.read_json(self.registry._record_path("codex", "decision-owner"))
            raw["lstart"] = "a different execution generation"
            self.paths.write_json(self.registry._record_path("codex", "decision-owner"), raw)
        self.run_server([self.tool(1), dict(id="xsm-1", **accepted())], before_answer=change)
        self.assertEqual(self.records(), [])
        self.assertEqual(self.decisions()[0]["status"], "superseded")

    def test_real_server_owner_identity_change_refuses_domain_application(self):
        for field, value in (("home", self.tmp + "/other-profile"), ("session_id", "another-conversation")):
            with self.subTest(field=field):
                count_before = len(self.records())
                # Restore the original native pointer for each independent request.
                self.paths.write_json(self.registry._record_path("codex", "decision-owner"), dict(self.me))
                self.args["decision_key"] = "owner-change-" + field
                def change():
                    raw = dict(self.me, **{field: value})
                    self.paths.write_json(self.registry._record_path("codex", "decision-owner"), raw)
                self.run_server([self.tool(1), dict(id="xsm-1", **accepted())], before_answer=change)
                self.assertEqual(len(self.records()), count_before,
                                 "a new owner must not apply an old owner's decision")

    def test_real_server_scope_cwd_change_refuses_domain_application(self):
        other = self.tmp + "/other-scope"
        os.mkdir(other)
        def change():
            self.paths.write_json(self.registry._record_path("codex", "decision-owner"), dict(self.me, cwd=other))
        self.run_server([self.tool(1), dict(id="xsm-1", **accepted())], before_answer=change)
        self.assertEqual(self.records(), [], "the decision must not be recorded after scope changes")
        self.assertIsNone(self.decisions()[0]["application"])

    def test_real_server_auto_review_never_posts_a_human_decision(self):
        self.run_server([self.tool(1), dict(id="xsm-1", **accepted(reviewer="auto"))])
        self.assertEqual(self.records(), [])
        record = self.decisions()[0]
        self.assertEqual(record["status"], "unknown")
        self.assertIsNone(record["application"])

    def test_real_server_expired_late_answer_is_kept_without_application(self):
        def expire():
            record = self.decisions()[0]
            record["expires_at"] = time.time() - 1
            self.paths.write_json(self.d.filename(record["id"]), record)
        reply = accepted("expired original answer")
        self.run_server([self.tool(1), dict(id="xsm-1", **reply)], before_answer=expire)
        record = self.decisions()[0]
        self.assertEqual(record["status"], "expired")
        self.assertEqual(record["answer"]["reply"]["result"], reply["result"])
        self.assertIsNone(record["application"])
        self.assertEqual(self.records(), [])

    def test_real_server_new_scope_with_same_label_needs_its_own_actual_form(self):
        changed = dict(self.args, question="A different exact question?")
        output = self.run_server([self.tool(1), dict(id="xsm-1", **accepted()),
                                 self.tool(2, changed), dict(id="xsm-2", **accepted("deny"))])
        forms = [row for row in output if row.get("method") == "elicitation/create"]
        self.assertEqual([row["params"]["message"] for row in forms],
                         [self.args["question"], changed["question"]])
        self.assertEqual(len(self.decisions()), 2)
        self.assertEqual(sorted(record["answer"] for record in self.records()), ["approve", "deny"])

    def test_real_server_late_response_after_waiter_cancel_is_recorded_without_side_effect(self):
        output = self.run_server([self.tool(1), {"method": "notifications/cancelled", "params": {"requestId": 1}},
                                 dict(id="xsm-1", **accepted("late original answer")), {"id": 9, "method": "ping"}])
        self.assertTrue(any(row.get("id") == 9 for row in output))
        self.assertEqual(self.records(), [])
        record = self.decisions()[0]
        self.assertEqual(record["answer"]["reply"]["result"]["content"]["answer"], "late original answer")
        self.assertEqual(record["waiters"]["1"], "cancelled")
        self.assertIsNone(record["application"])
        self.assertNotEqual(record["status"], "cancelled")

    def test_real_stdio_duplicate_question_and_completed_retry_append_once(self):
        wire = _DecisionWire(self)
        wire.send({"id": 0, "method": "initialize", "params": {"capabilities": {"elicitation": {}}}})
        self.assertEqual(wire.read()["id"], 0)
        wire.send(self.tool(1))
        form = wire.read()
        self.assertEqual(form["method"], "elicitation/create")
        wire.send(self.tool(2))
        second = wire.read()
        self.assertEqual(second["id"], 2, "a duplicate must join, not display a second form")
        wire.send(dict(id=form["id"], **accepted()))
        self.assertEqual(wire.read()["id"], 1)
        wire.send(self.tool(3))
        self.assertEqual(wire.read()["id"], 3)
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(len(self.decisions()), 1)

    def test_real_stdio_cancelled_waiter_late_reply_persists_but_does_not_post(self):
        wire = _DecisionWire(self)
        wire.send({"id": 0, "method": "initialize", "params": {"capabilities": {"elicitation": {}}}})
        wire.read()
        wire.send(self.tool(1))
        form = wire.read()
        wire.send({"method": "notifications/cancelled", "params": {"requestId": 1}})
        self.assertEqual(wire.read()["id"], 1)
        wire.send(dict(id=form["id"], **accepted()))
        wire.send({"id": 9, "method": "ping"})
        self.assertEqual(wire.read()["id"], 9)
        record = self.decisions()[0]
        self.assertEqual(record["status"], "answered")
        self.assertEqual(record["waiters"]["1"], "cancelled")
        self.assertIsNone(record["application"])
        self.assertEqual(self.records(), [])

    def test_real_stdio_changed_native_owner_home_cannot_append_a_decision(self):
        wire = _DecisionWire(self)
        wire.send({"id": 0, "method": "initialize", "params": {"capabilities": {"elicitation": {}}}})
        wire.read()
        wire.send(self.tool(1))
        form = wire.read()
        other_home = self.tmp + "/replacement-profile"
        os.mkdir(other_home)
        raw = self.paths.read_json(self.registry._record_path("codex", "decision-owner"))
        self.paths.write_json(self.registry._record_path("codex", "decision-owner"), dict(raw, home=other_home))
        wire.send(dict(id=form["id"], **accepted()))
        self.assertEqual(wire.read()["id"], 1)
        self.assertEqual(self.records(), [], "the real stdio response cannot authorize a changed native owner")
        self.assertIsNone(self.decisions()[0]["application"])
