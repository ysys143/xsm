"""Real JSON-RPC input routing preserves calls and the caller of each form."""
import io
import json
import os
from tests.test_xsm import TempState


class McpDispatchTest(TempState):
    def tool(self, mid, who, name="xsm_decide", **args):
        return {"id": mid, "method": "tools/call", "params": {
            "name": name, "arguments": args, "_meta": {"threadId": who}}}

    def run_stream(self, rows):
        from xsm import mcp, context
        for who in ("a", "b"):
            os.makedirs(os.path.join(self.tmp, who), exist_ok=True)
        inp = io.StringIO("".join(json.dumps(x) + "\n" for x in [
            {"id": 0, "method": "initialize", "params": {"capabilities": {"elicitation": {}}}},
            *rows]))
        out = io.StringIO();server = mcp.Server(inp, out)
        def session():
            who = server.call_thread
            record = {"runtime": "claude", "home": self.tmp + "/home", "alias": "fixture",
                      "session_id": who, "ref": who * 6, "name": who,
                      "cwd": os.path.join(self.tmp, who)}
            server.ctx = context.of_record(record, context.BASIS_THREAD)
            return record
        server.session = session
        if hasattr(self, "inspect_call"):
            original = server._call
            server._call = lambda *args: self.inspect_call(original, *args)
        self.assertEqual(server.serve(), 0)
        self.assertIsNone(server.ctx, "a completed call must not remain caller authority")
        return [json.loads(x) for x in out.getvalue().splitlines()]

    def records(self, who):
        from xsm import channel
        return channel.read(channel.resolve(os.path.join(self.tmp, who))[1])

    def test_nested_forms_route_out_of_order_replies_to_their_own_caller(self):
        rows = [self.tool(1, "a", question="outer"), self.tool(2, "b", question="inner"),
                {"id": "xsm-1", "result": {"action": "accept", "content": {"answer": "A"}}},
                {"id": 3, "method": "ping"},
                {"id": "xsm-2", "result": {"action": "accept", "content": {"answer": "B"}}}]
        output = self.run_stream(rows)
        results = {x.get("id"): x for x in output if "result" in x}
        self.assertFalse(results[1]["result"]["isError"])
        self.assertFalse(results[2]["result"]["isError"])
        self.assertEqual(results[3]["result"], {})
        for who, answer in (("a", "A"), ("b", "B")):
            records = self.records(who)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["author"]["asked_by"], who * 6)
            self.assertTrue(records[0]["text"].endswith(" -> " + answer))

    def test_cancelled_form_does_not_apply_a_late_yes_and_next_tool_still_runs(self):
        output = self.run_stream([
            self.tool(1, "a", question="must not apply"),
            {"method": "notifications/cancelled", "params": {"requestId": 1}},
            {"id": "xsm-1", "result": {"action": "accept", "content": {"answer": "yes"}}},
            self.tool(2, "b", "xsm_post", text="still working")])
        self.assertEqual(self.records("a"), [])
        self.assertEqual([r["text"] for r in self.records("b")], ["still working"])
        result = next(x for x in output if x.get("id") == 1 and "result" in x)
        self.assertIn("nothing was recorded", result["result"]["content"][0]["text"])

    def test_nested_calls_do_not_inherit_another_callers_consent_globals(self):
        from xsm import consent
        observed = {}
        def inspect(original, name, args, me, where, author):
            if me["session_id"] == "a":
                consent.answer_request = "outer-question"
                consent.question_text = "outer-text"
                result = original(name, args, me, where, author)
                observed["restored"] = consent.answer_request
                return result
            observed["child"] = (consent.answer_request, consent.question_text)
            return original(name, args, me, where, author)
        self.inspect_call = inspect
        self.run_stream([self.tool(1, "a", question="outer"),
                         self.tool(2, "b", "xsm_post", text="child"),
                         {"id": "xsm-1", "result": {"action": "accept",
                          "content": {"answer": "yes"}}}])
        self.assertEqual(observed["child"], (None, None))
        self.assertEqual(observed["restored"], "outer-question")
