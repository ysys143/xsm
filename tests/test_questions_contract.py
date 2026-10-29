"""P03 preparation (G02 not passed): characterize existing paths, not new APIs.

Passing these tests confirms the documented limitations; it does NOT pass G03
or A16. A16-01: send/wait returns delivery, not an answer. A16-07: forms
answer ping but consume other calls. Real harness/cancel races remain untested.
Only the runtime queue boundary is faked; send, ledger, inbox, receive and the
MCP reader/dispatcher run as implemented. No model, daemon or real user UI runs.
"""
import io
import json
import os
import unittest
from unittest import mock

from tests.test_xsm import TempState


class DeliveryVersusReplyTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import adapters, registry
        home = os.path.join(self.tmp, "codex")
        os.makedirs(home)
        self.me = registry.upsert("codex", home, "questioner", os.getpid(), self.tmp,
                                  name="questioner")
        self.peer = registry.upsert("codex", home, "answerer", os.getpid(), self.tmp,
                                    name="answerer")
        patch = mock.patch.object(adapters, "to_codex", return_value=None)
        self.queue = patch.start()
        self.addCleanup(patch.stop)

    def _question(self, reply_to=None):
        from xsm import receive, send

        def deliver(home, session, wire):
            # The receiver actually consumes the inbox and writes its receipt
            # before send reaches ledger.wait_for; no timing-dependent sleeps.
            self.assertEqual(session, self.peer["session_id"])
            self.assertEqual(len(receive.take_inbox(self.peer)), 1)
            if reply_to is not None:
                # Do not recurse into this queue callback for the reply.
                self.queue.side_effect = None
                self.reply = send.send("ref:" + self.me["ref"], "answer-token-redis",
                                       sender=self.peer, kind="reply", reply_to=reply_to,
                                       outcome="succeeded")
                self.assertEqual(self.reply.status, "sent-unconfirmed", self.reply.reason)
                self.reply_texts = receive.take_inbox(self.me)

        self.queue.side_effect = deliver
        return send.send("ref:" + self.peer["ref"], "Which cache?", sender=self.me,
                         kind="task", msg_id="question-1", wait=10)

    def test_receipt_alone_ends_send_wait_without_an_answer(self):
        from xsm import inbox, ledger
        result = self._question()
        self.assertEqual((result.status, result.msg_id), ("delivered", "question-1"))
        self.assertEqual(ledger.receipt_of(result.msg_id)["decision"], "delivered")
        self.assertEqual(inbox.count(self.me["session_id"]), 0)
        self.assertNotIn("outcome", ledger.status(result.msg_id))
        self.assertEqual(result.reason, "receiver recorded it")

    def test_real_reply_closes_task_but_wait_still_returns_only_delivery(self):
        from xsm import ledger
        result = self._question(reply_to="question-1")
        self.assertEqual(len(self.reply_texts), 1)
        self.assertIn("answer-token-redis", self.reply_texts[0])
        self.assertEqual(ledger.status(self.reply.msg_id)["reply_to"], "question-1")
        self.assertEqual(ledger.status("question-1")["outcome"], "succeeded")
        self.assertEqual(result.status, "delivered")
        self.assertNotIn("answer-token-redis", "\n".join(result.lines()))
        self.assertEqual(ledger.wait_for("question-1", 10)["status"], "delivered")

    def test_unrelated_reply_is_delivered_but_does_not_close_original_task(self):
        from xsm import ledger
        result = self._question(reply_to="nonexistent-question")
        self.assertEqual(len(self.reply_texts), 1)
        self.assertIn("answer-token-redis", self.reply_texts[0])
        self.assertEqual(ledger.status(self.reply.msg_id)["status"], "delivered")
        self.assertEqual(ledger.status(self.reply.msg_id)["reply_to"], "nonexistent-question")
        self.assertNotIn("outcome", ledger.status("question-1"))
        self.assertEqual(ledger.status("nonexistent-question"), {})
        self.assertEqual(result.status, "delivered")


class FormInputTest(TempState):
    def _run(self, during=(), after=()):
        from xsm import mcp
        messages = [
            {"id": 1, "method": "initialize", "params": {"capabilities": {"elicitation": {}}}},
            self._tool(2, "xsm_decide", {"question": "Which cache?"}),
            *during,
            {"id": "xsm-1", "result": {"action": "accept", "content": {"answer": "redis"}}},
            *after,
        ]
        stream = io.StringIO("".join(json.dumps(dict(jsonrpc="2.0", **m)) + "\n"
                                    for m in messages))
        out = io.StringIO()
        server = mcp.Server(stream, out)
        server.session = lambda: {"name": "tester", "alias": "fixture", "ref": "aaaaaa",
                                  "runtime": "claude", "cwd": self.tmp}
        self.assertEqual(server.serve(), 0)
        self.assertEqual(stream.read(), "")
        output = [json.loads(line) for line in out.getvalue().splitlines()]
        form = next(m for m in output if m.get("method") == "elicitation/create")
        self.assertEqual(form["id"], "xsm-1")
        response = next(m for m in output if m.get("id") == 2)
        self.assertFalse(response["result"]["isError"], response)
        self.assertIn("redis", response["result"]["content"][0]["text"])
        return output

    @staticmethod
    def _tool(mid, name="xsm_channel", arguments=None):
        return {"id": mid, "method": "tools/call",
                "params": {"name": name, "arguments": arguments or {}}}

    def test_ping_during_form_is_answered_before_form_completion(self):
        output = self._run(during=[{"id": 3, "method": "ping"}])
        ping = next(m for m in output if m.get("id") == 3)
        self.assertEqual(ping["result"], {})
        self.assertLess(output.index(ping), next(i for i, m in enumerate(output)
                                                if m.get("id") == 2))

    def test_tool_during_form_and_after_form_both_run(self):
        output = self._run(during=[self._tool(3)], after=[self._tool(4)])
        self.assertTrue(any(m.get("id") == 3 for m in output), output)
        later = next(m for m in output if m.get("id") == 4)
        self.assertFalse(later["result"]["isError"], later)

    def test_tool_effect_is_preserved_when_ping_is_interleaved(self):
        from xsm import channel
        output = self._run(during=[self._tool(3, "xsm_post", {"text": "lost-post"}),
                                   {"id": 4, "method": "ping"}],
                           after=[self._tool(5, "xsm_post", {"text": "kept-post"})])
        self.assertTrue(any(m.get("id") == 3 for m in output), output)
        self.assertEqual(next(m for m in output if m.get("id") == 4)["result"], {})
        self.assertFalse(next(m for m in output if m.get("id") == 5)["result"]["isError"])
        texts = [r["text"] for r in channel.read(channel.resolve(self.tmp)[1])]
        self.assertIn("lost-post", texts)
        self.assertIn("kept-post", texts)


if __name__ == "__main__":
    unittest.main()
