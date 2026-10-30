"""The MCP form tools: what only a person decides is asked with a form, and
only the person's own choice acts. (The channel these lived beside was removed
in 0.5.1, ADR-0026; a decision is kept beside a team's board.)"""
import io
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.test_xsm import TempState  # noqa: E402

AGENT = {"kind": "agent", "name": "builder", "alias": "claude-4", "ref": "aaaaaa",
         "runtime": "claude"}


class McpServerTest(TempState):
    """The server speaks MCP over stdio and records only what the person chose."""

    def _run(self, *messages, session=AGENT, cwd=None):
        from xsm import mcp
        here = cwd or os.path.join(self.tmp, "proj")
        os.makedirs(here, exist_ok=True)
        inp = io.StringIO("".join(json.dumps(m) + "\n" for m in messages))
        out = io.StringIO()
        server = mcp.Server(inp, out)
        server.session = lambda: dict(session, cwd=here) if session else None
        server.serve()
        return [json.loads(l) for l in out.getvalue().splitlines()], here

    INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {"elicitation": {}}}}

    def _in_team(self, agent=AGENT):
        """The asking session as a member of team core, the one team it is in,
        so xsm_decide without `team` records beside core's board."""
        from xsm import teams
        home = os.path.join(self.tmp, "homes", "claude")
        os.makedirs(home, exist_ok=True)
        agent = dict(agent, home=home)
        teams.create(agent, "core")
        return agent

    def test_decide_asks_the_person_and_records_their_answer(self):
        from xsm import board
        agent = self._in_team()
        call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "xsm_decide", "arguments": {"question": "Which queue?",
                                                "options": ["sqs", "kafka"], "summary": "queue"}}}
        answer = {"jsonrpc": "2.0", "id": "xsm-1", "result": {"action": "accept",
                                                              "content": {"answer": "kafka"}}}
        out, here = self._run(self.INIT, call, answer, session=agent)
        elicit = next(m for m in out if m.get("method") == "elicitation/create")
        self.assertEqual(elicit["params"]["requestedSchema"]["properties"]["answer"]["enum"],
                         ["sqs", "kafka"])
        self.assertIn("beside team core's board (the one team this session is in): kafka",
                      next(m for m in out if m.get("id") == 2)["result"]["content"][0]["text"])
        rec = board.decisions("core")[-1]
        self.assertEqual((rec["question"], rec["answer"], rec["options"], rec["via"]),
                         ("Which queue?", "kafka", ["sqs", "kafka"], "mcp-elicitation"))
        self.assertIn("person via mcp-elicitation", rec["decided_by"])

    def test_decide_in_no_team_returns_the_answer_and_records_nothing(self):
        """T11: with no team to keep it beside, the person is still asked and
        their answer goes back to the agent, which is told it is not on record."""
        from xsm import paths
        call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "xsm_decide", "arguments": {"question": "Which queue?",
                                                "options": ["sqs", "kafka"]}}}
        answer = {"jsonrpc": "2.0", "id": "xsm-1", "result": {"action": "accept",
                                                              "content": {"answer": "kafka"}}}
        out, _ = self._run(self.INIT, call, answer)
        self.assertTrue(any(m.get("method") == "elicitation/create" for m in out))
        reply = next(m for m in out if m.get("id") == 2)["result"]
        text = reply["content"][0]["text"]
        self.assertFalse(reply["isError"])
        self.assertIn("your user answered: kafka", text)
        self.assertIn("not recorded as a decision: this session is in no team", text)
        self.assertIn("xsm team create", text)
        self.assertFalse(os.path.isdir(paths.path("teams")))

    def test_a_declined_question_records_nothing(self):
        from xsm import board
        agent = self._in_team()
        call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "xsm_decide", "arguments": {"question": "Ship it?"}}}
        answer = {"jsonrpc": "2.0", "id": "xsm-1", "result": {"action": "decline"}}
        out, here = self._run(self.INIT, call, answer, session=agent)
        reply = next(m for m in out if m.get("id") == 2)
        self.assertIn("did not answer", reply["result"]["content"][0]["text"])
        self.assertNotIn("xsm post", reply["result"]["content"][0]["text"])
        self.assertEqual(board.decisions("core"), [])

    def test_a_refusal_says_who_answered(self):
        from xsm import mcp
        said = lambda result: mcp.who_answered({"result": result})
        self.assertIn("automatic reviewer", said({"action": "decline", "_meta": {
            "approvals_reviewer": "auto_review", "message": "looks risky"}}))
        self.assertIn("looks risky", said({"action": "decline", "_meta": {
            "approvals_reviewer": "auto_review", "message": "looks risky"}}))
        self.assertIn("approval_policy", said({"action": "decline"}))
        self.assertIn("no choice", said({"action": "accept", "content": {}}))
        self.assertIn("'deny'", said({"action": "accept", "content": {"answer": "deny"}}))
        self.assertIn("dismissed", said({"action": "cancel"}))

    def test_a_join_answered_by_codex_itself_is_not_taken_for_the_user(self):
        from xsm import config
        call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "xsm_join", "arguments": {"project": "demo"}}}
        auto = {"jsonrpc": "2.0", "id": "xsm-1", "result": {
            "action": "accept", "content": {}, "_meta": {"approvals_reviewer": "auto_review"}}}
        out, _ = self._run(self.INIT, call, auto)
        text = next(m for m in out if m.get("id") == 2)["result"]["content"][0]["text"]
        self.assertIn("automatic reviewer", text)
        self.assertIn("xsm join demo", text)            # what the person can do instead
        self.assertEqual(config.projects(), [])

    def test_reach_asks_the_person_and_records_only_an_allow(self):
        from xsm import config, registry
        other = os.path.join(self.tmp, "other")
        os.makedirs(other)
        # A reach is bound to a running session's record, so the asker must be
        # one (a Codex record with a live pid reads live without a socket).
        home = os.path.join(self.tmp, "homes", "codex")
        os.makedirs(home, exist_ok=True)
        rec = registry.upsert("codex", home, "t-reach", os.getpid(), self.tmp, name="builder")
        agent = dict(AGENT, ref=rec["ref"])
        call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "xsm_reach", "arguments": {"dir": other, "reason": "hand over a task"}}}
        deny = {"jsonrpc": "2.0", "id": "xsm-1", "result": {"action": "accept",
                                                            "content": {"answer": "deny"}}}
        out, _ = self._run(self.INIT, call, deny, session=agent)
        self.assertIn("other", next(m for m in out if m.get("method") == "elicitation/create")
                      ["params"]["message"])
        self.assertEqual(config.reaches(), [])
        allow = dict(deny, result={"action": "accept", "content": {"answer": "allow"}})
        out, _ = self._run(self.INIT, call, allow, session=agent)
        self.assertIn("allowed", next(m for m in out if m.get("id") == 2)
                      ["result"]["content"][0]["text"])
        self.assertEqual([(r["ref"], r["root"]) for r in config.reaches()],
                         [(agent["ref"], os.path.realpath(other))])

    def _six(self, here):
        """The asking session, and each form tool with its arguments, the answer
        that would make it act, and what it changed — so a reply can be checked
        against all six at once. The session is a running record, so a reach
        allowed here is really added (test_a_persons_choice_acts_in_all_six)."""
        from xsm import board, config, doc, paths, registry, workers
        other = os.path.join(self.tmp, "other")
        os.makedirs(other, exist_ok=True)
        home = os.path.join(self.tmp, "homes", "codex")
        os.makedirs(home, exist_ok=True)
        rec = registry.upsert("codex", home, "t-six", os.getpid(), self.tmp, name="builder")
        agent = self._in_team(dict(AGENT, ref=rec["ref"]))
        node = doc.add(os.path.join(here, "d.md"), AGENT, "the report", ["report"])
        workers.save({"name": "w1", "parent_ref": agent["ref"], "created": 0})
        os.makedirs(paths.path(workers.APPROVALS), exist_ok=True)
        paths.write_json(paths.path(workers.APPROVALS, "r1.json"),
                         {"id": "r1", "worker": "w1", "status": "pending", "t": 1, "summary": "x"})
        decisions = lambda: board.decisions("core")
        grants = lambda: os.listdir(paths.path(workers.GRANTS)) \
            if os.path.isdir(paths.path(workers.GRANTS)) else []
        return agent, [
            ("xsm_decide", {"question": "Ship?", "options": ["yes", "no"]}, "yes", decisions),
            ("xsm_doc_endorse", {"doc": "d.md", "node": node["id"]}, "endorse",
             lambda: [n for n in doc.read(os.path.join(here, "d.md")) if "endorsed" in n["tags"]]),
            ("xsm_join", {"project": "demo"}, "allow", config.projects),
            ("xsm_reach", {"dir": other}, "allow", config.reaches),
            ("xsm_approve", {"id": "r1"}, "allow",
             lambda: [r for r in [paths.read_json(paths.path(workers.APPROVALS, "r1.json"))]
                      if r["status"] != "pending"]),
            ("xsm_grant", {"runtime": "codex", "options": ["full_access"], "reason": "r"},
             "allow once", grants),
        ]

    def _ask(self, name, args, reply, cwd=None, session=AGENT, init=None):
        call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": name, "arguments": args}}
        out, _ = self._run(init or self.INIT, call,
                           dict({"jsonrpc": "2.0", "id": "xsm-1"}, **reply),
                           cwd=cwd, session=session)
        return next(m for m in out if m.get("id") == 2)["result"]["content"][0]["text"]

    def test_a_persons_choice_acts_in_all_six(self):
        # What makes the refusals below mean something: the same setup acts
        # when the answer is a person's.
        here = os.path.join(self.tmp, "proj")
        os.makedirs(here, exist_ok=True)
        agent, six = self._six(here)
        for name, args, yes, changed in six:
            with self.subTest(name):
                self._ask(name, args, {"result": {"action": "accept", "content": {"answer": yes}}},
                          session=agent)
                self.assertNotEqual(changed(), [])

    def test_an_answer_from_an_automatic_reviewer_changes_nothing(self):
        here = os.path.join(self.tmp, "proj")
        os.makedirs(here, exist_ok=True)
        agent, six = self._six(here)
        for name, args, yes, changed in six:
            with self.subTest(name):
                text = self._ask(name, args, {"result": {
                    "action": "accept", "content": {"answer": yes},
                    "_meta": {"approvals_reviewer": "auto_review"}}}, session=agent)
                self.assertIn("automatic reviewer", text)
                self.assertEqual(changed(), [])

    def test_a_malformed_meta_is_no_answer_even_with_a_valid_choice(self):
        # A _meta that is there but not an object says nothing about who
        # answered; it was read as no _meta, and all six acted (2026-09-28).
        here = os.path.join(self.tmp, "proj")
        os.makedirs(here, exist_ok=True)
        agent, six = self._six(here)
        for name, args, yes, changed in six:
            for meta in (["invalid"], "auto_review"):
                with self.subTest(name, meta=meta):
                    text = self._ask(name, args, {"result": {
                        "action": "accept", "content": {"answer": yes}, "_meta": meta}},
                        session=agent)
                    self.assertIn("_meta", text)
                    self.assertEqual(changed(), [])

    def test_a_malformed_action_is_a_tool_result_not_a_dead_server(self):
        # action=[] with an automatic reviewer raised TypeError past serve(),
        # so the server exited without replying (2026-09-28).
        here = os.path.join(self.tmp, "proj")
        os.makedirs(here, exist_ok=True)
        agent, six = self._six(here)
        for name, args, yes, changed in six:
            for action in ([], {}, None):
                with self.subTest(name, action=action):
                    text = self._ask(name, args, {"result": {
                        "action": action, "content": {"answer": yes},
                        "_meta": {"approvals_reviewer": "auto_review"}}}, session=agent)
                    self.assertIn("not a form answer", text)
                    self.assertEqual(changed(), [])

    def test_a_malformed_answer_is_no_answer_and_no_crash(self):
        here = os.path.join(self.tmp, "proj")
        os.makedirs(here, exist_ok=True)
        replies = [{"result": {"action": "accept", "content": ["allow"]}},
                   {"result": {"action": "accept", "content": {"answer": None}}},
                   {"result": {"action": "accept", "content": {"answer": "  "}}},
                   {"result": {"action": "accept", "content": {"answer": "maybe"}}},
                   {"result": "accept"},
                   {"result": {"action": "accept", "content": {}, "_meta": ["x"]}},
                   {"error": "boom"}]
        agent, six = self._six(here)
        for name, args, _, changed in six:
            for reply in replies:
                with self.subTest(name, reply=reply):
                    text = self._ask(name, args, reply, session=agent)
                    self.assertNotIn("None", text)
                    self.assertEqual(changed(), [])

    def test_a_join_denied_by_the_person_offers_no_command(self):
        from xsm import config
        deny = {"result": {"action": "accept", "content": {"answer": "deny"}}}
        text = self._ask("xsm_join", {"project": "demo"}, deny)
        self.assertIn("they chose 'deny'", text)
        self.assertNotIn("xsm join", text)
        self.assertNotIn("terminal", text)
        self.assertEqual(config.projects(), [])

    def test_the_shell_command_is_one_the_agent_can_run_and_is_quoted(self):
        """Issue #9: the fallback is run by the agent from its own folder, and
        --dir is taken only from a person at a terminal, so it carries none."""
        import shlex
        from xsm import config
        here = os.path.join(self.tmp, "my proj")
        text = self._ask("xsm_join", {"project": "demo"}, {"result": {"action": "decline"}},
                         cwd=here)
        self.assertIn("`xsm join demo` in your shell", text)
        self.assertNotIn("--dir", text)
        self.assertIn("approval_policy", text)
        other = os.path.join(self.tmp, "other folder")
        os.makedirs(other)
        text = self._ask("xsm_reach", {"dir": other}, {"result": {"action": "cancel"}})
        self.assertIn("`xsm reach %s --session ref:%s`" % (
            shlex.quote(config.project_root(other)), AGENT["ref"]), text)

    def test_the_reach_command_names_the_absolute_root_of_a_relative_dir(self):
        # The person's terminal may be anywhere, so "../other folder" is named
        # as the root the form showed, taken from the asking session's folder.
        import shlex
        from xsm import config
        here = os.path.join(self.tmp, "proj")
        other = os.path.join(self.tmp, "other folder")
        os.makedirs(other)
        command = "`xsm reach %s --session ref:%s`" % (
            shlex.quote(config.project_root(other)), AGENT["ref"])
        text = self._ask("xsm_reach", {"dir": "../other folder"},
                         {"result": {"action": "decline"}}, cwd=here)
        self.assertIn(command, text)
        self.assertNotIn("..", text)
        init = dict(self.INIT, params={"protocolVersion": "2025-06-18", "capabilities": {}})
        call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "xsm_reach", "arguments": {"dir": "../other folder"}}}
        out, _ = self._run(init, call, cwd=here)
        self.assertIn(command, next(m for m in out if m.get("id") == 2)
                      ["result"]["content"][0]["text"])

    def test_a_bare_decline_is_unsure_only_for_codex_or_an_unnamed_client(self):
        init = lambda name: dict(self.INIT, params=dict(self.INIT["params"],
                                                        clientInfo={"name": name}))
        decline = {"result": {"action": "decline"}}
        text = self._ask("xsm_join", {"project": "demo"}, decline, init=init("codex-mcp-client"))
        self.assertIn("by Codex without showing the form", text)
        text = self._ask("xsm_join", {"project": "demo"}, decline)
        self.assertIn("by the client without showing the form (Codex does this", text)

    def test_a_decline_from_a_client_that_shows_forms_is_the_persons_no(self):
        """The MCP spec: decline is an explicit no, cancel a dismissal. A form
        tool read both as no answer and the agent asked again (2026-10-01)."""
        from xsm import board, config, mcp
        init = dict(self.INIT, params=dict(self.INIT["params"], clientInfo={"name": "claude-code"}))
        decline = {"result": {"action": "decline"}}
        cancel = {"result": {"action": "cancel"}}
        text = self._ask("xsm_join", {"project": "demo"}, decline, init=init)
        self.assertIn("your user declined", text)
        self.assertIn("do not ask again", text)
        self.assertNotIn("did not answer", text)
        self.assertNotIn("run `xsm join", text, "no road round a no")
        self.assertEqual(config.projects(), [])
        text = self._ask("xsm_join", {"project": "demo"}, cancel, init=init)
        self.assertIn("did not answer", text)
        self.assertIn("dismissed", text)
        self.assertIn("xsm join demo", text, "no answer: the agent may ask in words")
        self.assertEqual(mcp.person_answer({"result": {"action": "decline"}}, client="claude-code"),
                         (None, mcp.DECLINED))
        call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "xsm_decide", "arguments": {"question": "Ship it?"}}}
        out, here = self._run(init, call, {"jsonrpc": "2.0", "id": "xsm-1", "result": {
            "action": "decline"}}, session=self._in_team())
        said = next(m for m in out if m.get("id") == 2)["result"]["content"][0]["text"]
        self.assertIn("your user declined", said)
        self.assertEqual(board.decisions("core"), [])

    def test_decide_offers_options_as_they_are_compared(self):
        # " yes " was offered as is and compared stripped, so the person's
        # choice was refused (2026-09-28).
        from xsm import board
        agent = self._in_team()
        call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "xsm_decide", "arguments": {"question": "Ship?",
                                                "options": [" yes ", "no", "yes", "  "]}}}
        for chosen in ("yes", " yes "):
            with self.subTest(chosen=chosen):
                answer = {"jsonrpc": "2.0", "id": "xsm-1", "result": {
                    "action": "accept", "content": {"answer": chosen}}}
                out, here = self._run(self.INIT, call, answer, session=agent)
                elicit = next(m for m in out if m.get("method") == "elicitation/create")
                self.assertEqual(elicit["params"]["requestedSchema"]["properties"]["answer"]
                                 ["enum"], ["yes", "no"])
                self.assertIn("recorded decision", next(m for m in out if m.get("id") == 2)
                              ["result"]["content"][0]["text"])
                self.assertEqual(board.decisions("core")[-1]["answer"], "yes")

    def test_a_tool_that_fails_is_that_calls_error_not_the_servers_end(self):
        from xsm import mcp
        msgs = [self.INIT,
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                 "params": {"name": "xsm_send", "arguments": {"target": "x", "text": "x"}}},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}]
        out = io.StringIO()
        server = mcp.Server(io.StringIO("".join(json.dumps(m) + "\n" for m in msgs)), out)
        server.session = lambda: dict(AGENT, cwd=self.tmp)

        def boom(*a):
            raise TypeError("unhashable type: 'list'")
        server._call = boom
        self.assertEqual(server.serve(), 0)
        replies = {m["id"]: m for m in map(json.loads, out.getvalue().splitlines())}
        self.assertTrue(replies[2]["result"]["isError"])
        self.assertIn("unhashable", replies[2]["result"]["content"][0]["text"])
        self.assertIn("tools", replies[3]["result"])

    def test_a_tool_needs_a_registered_session(self):
        call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "xsm_send", "arguments": {"target": "x", "text": "hi"}}}
        out, _ = self._run(self.INIT, call, session=None)
        reply = next(m for m in out if m.get("id") == 2)["result"]
        self.assertTrue(reply["isError"])
        self.assertIn("not registered", reply["content"][0]["text"])

    def test_without_elicitation_support_decide_refuses(self):
        init = dict(self.INIT, params={"protocolVersion": "2025-06-18", "capabilities": {}})
        call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "xsm_decide", "arguments": {"question": "?"}}}
        out, _ = self._run(init, call)
        text = next(m for m in out if m.get("id") == 2)["result"]["content"][0]["text"]
        self.assertIn("cannot show a form", text)
        self.assertIn("nothing was recorded", text)
        self.assertNotIn("xsm post", text)
        self.assertNotIn("in a terminal", text)


if __name__ == "__main__":
    unittest.main()


class McpSendTest(TempState):
    def test_xsm_send_sends_as_the_session(self):
        import json as _json
        from xsm import mcp, registry, send
        seen = []
        send.send = lambda target, text, **kw: seen.append((target, text, kw["sender"]["ref"],
                                                            kw["kind"], kw["reply_to"])) or \
            type("R", (), {"status": "delivered", "reason": "ok"})()
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"capabilities": {}}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                    "name": "xsm_send", "arguments": {"target": "ref:abcdef@peer", "text": "56",
                                                      "kind": "reply", "reply_to": "m1"}}}]
        out = io.StringIO()
        server = mcp.Server(io.StringIO("".join(_json.dumps(m) + "\n" for m in msgs)), out)
        server.session = lambda: dict(AGENT, cwd=self.tmp)
        server.serve()
        self.assertEqual(seen, [("ref:abcdef@peer", "56", "aaaaaa", "reply", "m1")])
