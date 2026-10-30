"""Who the MCP server signs a call as (Server.session). Codex threads of one
CODEX_HOME share the app-server daemon's pid, so the pid cannot tell them
apart; Codex 0.158 names the thread in `params._meta.threadId` (measured
2026-09-29)."""
import io
import contextlib
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xsm import mcp, paths, registry  # noqa: E402
from tests import test_xsm  # noqa: E402

# Module name only: a class imported by name would run its tests twice.
TempState = test_xsm.TempState

DAEMON = 4242


def row(runtime, session_id, updated, pid=DAEMON, state="live", cwd="/tmp", home=None):
    return {"runtime": runtime, "session_id": session_id, "pid": pid, "state": state,
            "updated": updated, "name": session_id, "cwd": cwd,
            **(({"home": home}) if home else {})}


def serve_one(records, meta=None, pid=DAEMON, env=None):
    """Send one tools/call; return the `me` the server resolved and its reply."""
    seen = []
    params = {"name": "xsm_inbox", "arguments": {}}
    if meta is not None:
        params["_meta"] = meta
    msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params}
    out = io.StringIO()
    server = mcp.Server(io.StringIO(json.dumps(msg) + "\n"), out)

    def call(name, args):
        seen.append(server.session())
        return "ok"

    server.call = call
    # The rows already carry the state `_enrich` would compute for them.
    with _home_env(env), \
            mock.patch.object(mcp.identity, "ancestor_pid", return_value=pid), \
            mock.patch.object(mcp.registry, "raw_records", return_value=records), \
            mock.patch.object(mcp.registry, "_enrich", side_effect=lambda rec: rec), \
            mock.patch.object(mcp.registry, "adopt_codex_thread", return_value=None):
        server.serve()
    return seen, json.loads(out.getvalue())["result"]


@contextlib.contextmanager
def _home_env(env):
    """Set the runtime home variables for a call, clearing whatever the test
    process inherited (a live Codex or Claude session sets CODEX_HOME or
    CLAUDE_CONFIG_DIR, and the caller's home must be the one the test names)."""
    keys = ("CODEX_HOME", "CLAUDE_CONFIG_DIR")
    old = {k: os.environ.pop(k, None) for k in keys}
    os.environ.update(env or {})
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def serve_interleaved(records, metas, pid=DAEMON):
    """One server, several tools/calls, each naming a thread the way Codex does.
    Returns [(me, basis, certainty)] in call order, so a shared server's
    A/B/A/B interleaving can be checked for identity bleed (A17-02, A23-03)."""
    msgs = [{"jsonrpc": "2.0", "id": i, "method": "tools/call",
             "params": {"name": "xsm_inbox", "_meta": {"threadId": m}}} for i, m in enumerate(metas)]
    server = mcp.Server(io.StringIO("".join(json.dumps(m) + "\n" for m in msgs)), io.StringIO())
    seen = []

    def call(name, args):
        me = server.session()
        seen.append((me, server.ctx.basis, server.ctx.certainty,
                     server.ctx.conversation, server.ctx.home))
        return "ok"

    server.call = call
    with mock.patch.object(mcp.identity, "ancestor_pid", return_value=pid), \
            mock.patch.object(mcp.registry, "raw_records", return_value=records), \
            mock.patch.object(mcp.registry, "_enrich", side_effect=lambda rec: rec), \
            mock.patch.object(mcp.registry, "adopt_codex_thread", return_value=None):
        server.serve()
    return seen


class SharedServerInterleaveTest(unittest.TestCase):
    """A17-02/A23-03: one shared MCP server, two conversations calling it in
    turn. Each call's identity, folder and home must be its own; the server's
    `call_thread`, an inherited environment variable, or the neighbour of the
    previous call must not leak across (spec 4.1)."""

    TWO = [row("codex", "thread-a", 100, cwd="/proj/a"), row("codex", "thread-b", 200,
                                                               cwd="/proj/b")]

    def test_abab_calls_keep_their_own_thread_folder_and_home(self):
        seen = serve_interleaved(self.TWO, ["thread-a", "thread-b", "thread-a", "thread-b"])
        self.assertEqual([s[0]["session_id"] for s in seen],
                         ["thread-a", "thread-b", "thread-a", "thread-b"])
        self.assertEqual([s[0]["cwd"] for s in seen], ["/proj/a", "/proj/b", "/proj/a", "/proj/b"])
        self.assertEqual([s[1] for s in seen], ["thread_id"] * 4)
        self.assertEqual([s[2] for s in seen], ["certain"] * 4)
        self.assertEqual([s[3] for s in seen], ["thread-a", "thread-b", "thread-a", "thread-b"])

    def test_a_call_with_no_thread_id_is_marked_a_guess_not_the_last_thread(self):
        seen = serve_interleaved(self.TWO, ["thread-a"])
        self.assertEqual(seen[0][1], "thread_id")
        # A call that names no thread falls back to the newest record, and the
        # basis says so rather than reading as an exact identity.
        seen = serve_interleaved(self.TWO, [None, "thread-b"])
        self.assertEqual(seen[0][1], "neighbor")
        self.assertEqual(seen[0][2], "provisional")
        self.assertEqual(seen[1][1], "thread_id")

    def test_the_context_is_frozen_once_a_call_starts(self):
        seen = serve_interleaved(self.TWO, ["thread-a"])
        self.assertIsNotNone(seen[0])
        server = mcp.Server(io.StringIO(""), io.StringIO())
        server.call_thread = "thread-a"
        with mock.patch.object(mcp.identity, "ancestor_pid", return_value=DAEMON), \
                mock.patch.object(mcp.registry, "raw_records", return_value=self.TWO), \
                mock.patch.object(mcp.registry, "_enrich", side_effect=lambda rec: rec):
            server.session()
        ctx = server.ctx
        with self.assertRaises(AttributeError):
            ctx.home = "/somewhere/else"
        with self.assertRaises(AttributeError):
            ctx.conversation = "thread-b"


class DifferentHomeSameIdTest(unittest.TestCase):
    """A23-03: a thread id that exists in two CODEX_HOMEs names one pointer. A
    server running in home B must not sign as the record that lives in home A."""

    def test_a_record_from_another_home_is_not_taken(self):
        rec = row("codex", "thread-x", 100, cwd="/proj/a")
        rec["home"] = "/homes/codex-a"
        seen, _ = serve_one([rec], meta={"threadId": "thread-x"},
                            env={"CODEX_HOME": "/homes/codex-b"})
        # The other home's record is not used: nothing is signed rather than a
        # session in a home this server does not run in.
        self.assertIsNone(seen[0])

    def test_the_same_home_is_still_taken(self):
        rec = row("codex", "thread-x", 100, cwd="/proj/a")
        rec["home"] = "/homes/codex-a"
        seen, result = serve_one([rec], meta={"threadId": "thread-x"},
                                 env={"CODEX_HOME": "/homes/codex-a"})
        self.assertEqual(seen[0]["session_id"], "thread-x")
        self.assertFalse(result["isError"])


class InheritedEnvTest(unittest.TestCase):
    """A23-03: an inherited environment variable is a last resort, never an
    identity that overrides the call's own thread id."""

    def test_an_inherited_codex_home_does_not_change_the_named_thread(self):
        seen = serve_interleaved([row("codex", "thread-a", 100)], ["thread-a"])
        self.assertEqual(seen[0][0]["session_id"], "thread-a")
        self.assertEqual(seen[0][1], "thread_id")

    def test_a_named_thread_wins_over_an_inherited_other_thread(self):
        # A Codex started from another Codex's shell carries that thread id in
        # CODEX_THREAD_ID. The call's own threadId must decide, not the env.
        recs = [row("codex", "outer", 100), row("codex", "inner", 200)]
        with mock.patch.dict(os.environ, {"CODEX_THREAD_ID": "outer"}):
            seen = serve_interleaved(recs, ["inner"])
        self.assertEqual(seen[0][0]["session_id"], "inner")
        self.assertEqual(seen[0][1], "thread_id")


class HomeIsTheServersOwnTest(unittest.TestCase):
    """G01 review F1/O-F1: the home a server judges by is the home *it* runs in.
    Reading whichever home variable is set let a default-home server adopt
    another home's record (A23-03 bypassed), and made a Codex started from a
    Claude shell (CLAUDE_CONFIG_DIR inherited) refuse its own home's record
    (spec P01.1)."""

    def test_a_default_home_server_does_not_adopt_another_homes_record(self):
        rec = row("codex", "thread-x", 100, cwd="/proj/a", home="/homes/codex-a")
        seen, _ = serve_one([rec], meta={"threadId": "thread-x"}, env={})
        # No CODEX_HOME set: this server runs in the default home, and the record
        # is for another home, so it is not signed as it.
        self.assertIsNone(seen[0])

    def test_a_codex_keeps_its_own_home_record_when_it_inherits_claude_config_dir(self):
        # A Codex started from a Claude shell carries CLAUDE_CONFIG_DIR and the
        # Claude session id. Its own record lives in CODEX_HOME and must be used.
        rec = row("codex", "thread-y", 100, cwd="/proj/b")
        rec["home"] = "/homes/codex-b"
        seen, result = serve_one([rec], meta={"threadId": "thread-y"},
                                 env={"CODEX_HOME": "/homes/codex-b",
                                      "CLAUDE_CONFIG_DIR": "/homes/claude-a"})
        self.assertIsNotNone(seen[0], "its own home's record, not refused")
        self.assertEqual(seen[0]["session_id"], "thread-y")
        self.assertFalse(result["isError"])

    def test_a_claude_server_ignores_an_inherited_codex_home(self):
        rec = row("claude", "s-1", 100, cwd="/proj/c")
        rec["home"] = "/homes/claude-c"
        seen, result = serve_one([rec], env={"CODEX_HOME": "/homes/codex-a",
                                             "CLAUDE_CONFIG_DIR": "/homes/claude-c"})
        self.assertIsNotNone(seen[0])
        self.assertEqual(seen[0]["session_id"], "s-1")

    def test_a_default_home_codex_ignores_an_inherited_claude_config_dir(self):
        """G01 2nd review, F1 P2 (the exact 1차 반례): a Codex on its *default*
        home (no CODEX_HOME) that inherited CLAUDE_CONFIG_DIR from the Claude
        shell it was started in. Reading whichever home variable is set took the
        Claude home and refused the Codex its own record; the server's own
        runtime decides, so the default ~/.codex is used and the record is
        taken."""
        rec = row("codex", "thread-def", 100, cwd="/proj/d")
        rec["home"] = os.path.expanduser("~/.codex")
        seen, result = serve_one([rec], meta={"threadId": "thread-def"},
                                 env={"CLAUDE_CONFIG_DIR": "/homes/claude-a"})
        self.assertIsNotNone(seen[0], "its own (default) home's record, not refused")
        self.assertEqual(seen[0]["session_id"], "thread-def")
        self.assertFalse(result["isError"])


class SingleSessionIsExactTest(unittest.TestCase):
    """G01 review O-F1 (regression): Claude sends no `_meta.threadId`, so a call
    from a lone Claude session used to fall to the newest-live-record rule and
    read as a `neighbor` guess. The widening guard then refused every permission
    tool in a session's own name (spec P01.2, K07)."""

    def test_a_lone_claude_session_is_certain_and_not_a_guess(self):
        rec = row("claude", "solo", 100, cwd="/proj/a")
        seen = serve_interleaved([rec], [None])
        self.assertEqual(seen[0][1], "ancestor")
        self.assertEqual(seen[0][2], "certain")

    def test_a_lone_codex_thread_is_certain_even_with_no_thread_id(self):
        rec = row("codex", "only", 100, cwd="/proj/a")
        seen = serve_interleaved([rec], [None])
        self.assertEqual(seen[0][1], "ancestor")
        self.assertEqual(seen[0][2], "certain")

    def test_two_codex_threads_with_no_thread_id_are_still_a_guess(self):
        # The shared daemon case: several live threads, none named, is exactly
        # where a neighbor must stay provisional (P01 item 2).
        recs = [row("codex", "thread-a", 100), row("codex", "thread-b", 200)]
        seen = serve_interleaved(recs, [None])
        self.assertEqual(seen[0][1], "neighbor")
        self.assertEqual(seen[0][2], "provisional")


class ClaudeWideningThroughResolveTest(TempState):
    """O-F1: the guard must be exercised through the real `_resolve` path, not a
    context the test injected. A lone Claude session reaches the tool's own
    logic (the form path), which is the behaviour HEAD had and P01 must keep."""

    def _tool(self, name, args, records, pid=DAEMON, comm="claude"):
        seen = {}
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": args}}
        out = io.StringIO()
        server = mcp.Server(io.StringIO(json.dumps(msg) + "\n"), out)
        with _home_env({}), \
                mock.patch.object(mcp.identity, "ancestor_pid", return_value=pid), \
                mock.patch.object(mcp.identity, "comm", return_value=comm), \
                mock.patch.object(mcp.registry, "raw_records", return_value=records), \
                mock.patch.object(mcp.registry, "_enrich", side_effect=lambda r: r), \
                mock.patch.object(mcp.registry, "adopt_codex_thread", return_value=None):
            server.serve()
        seen["ctx"] = server.last_context
        return json.loads(out.getvalue())["result"], seen

    def test_a_lone_claude_session_reaches_the_grant_tool(self):
        rec = row("claude", "solo", 100, cwd=self.tmp)
        reply, seen = self._tool("xsm_grant", {"runtime": "codex", "options": ["full_access"],
                                                "reason": "why"}, [rec])
        self.assertEqual(seen["ctx"].basis, "ancestor")
        self.assertTrue(seen["ctx"].sure)
        # It got past the identity guard and failed only because this fake client
        # cannot show a form -- the same place HEAD sent it.
        self.assertIn("cannot show a form", reply["content"][0]["text"])
        self.assertNotIn("guess at which session", reply["content"][0]["text"])

    def test_a_lone_claude_session_reaches_approve(self):
        rec = row("claude", "solo", 100, cwd=self.tmp)
        reply, _ = self._tool("xsm_approve", {}, [rec])
        self.assertFalse(reply["isError"])
        self.assertIn("no waiting request", reply["content"][0]["text"])

    def test_a_guessed_neighbor_is_still_refused(self):
        recs = [row("codex", "thread-a", 100, cwd=self.tmp),
                row("codex", "thread-b", 200, cwd=self.tmp)]
        reply, seen = self._tool("xsm_grant", {"runtime": "codex", "options": ["full_access"],
                                                "reason": "why"}, recs, comm="codex")
        self.assertEqual(seen["ctx"].basis, "neighbor")
        self.assertTrue(reply["isError"])
        self.assertIn("guess at which session", reply["content"][0]["text"])

    def _tool_as_thread(self, name, args, records, thread, pid=DAEMON, comm="codex"):
        """One tools/call whose threadId is this, through serve()."""
        seen = {}
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": args, "_meta": {"threadId": thread}}}
        out = io.StringIO()
        server = mcp.Server(io.StringIO(json.dumps(msg) + "\n"), out)
        with _home_env({}), \
                mock.patch.object(mcp.identity, "ancestor_pid", return_value=pid), \
                mock.patch.object(mcp.identity, "comm", return_value=comm), \
                mock.patch.object(mcp.registry, "raw_records", return_value=records), \
                mock.patch.object(mcp.registry, "_enrich", side_effect=lambda r: r), \
                mock.patch.object(mcp.registry, "adopt_codex_thread", return_value=None):
            server.serve()
        seen["ctx"] = server.last_context
        return json.loads(out.getvalue())["result"], seen

    def test_a_named_thread_with_no_record_is_not_signed_as_the_only_other(self):
        """R2-1: the call names a thread that has no record (a sub-agent thread,
        or a home whose hook has not run) and adoption fails. The one live
        record here is a *different* session; signing as it would widen a
        permission for the wrong session (spec P01.2, IC01). The O-F1 fix must
        not promote it -- only a call that named no thread at all may use the
        lone record exactly."""
        parent = row("codex", "thread-parent", 100, cwd=self.tmp)
        reply, seen = self._tool_as_thread(
            "xsm_grant", {"runtime": "codex", "options": ["full_access"], "reason": "why"},
            [parent], thread="thread-sub")
        self.assertEqual(seen["ctx"].basis, "neighbor")
        self.assertFalse(seen["ctx"].sure)
        self.assertTrue(reply["isError"])
        self.assertIn("guess at which session", reply["content"][0]["text"])

    def test_a_named_thread_with_its_own_record_is_still_exact(self):
        """The matching branch is untouched: a named thread with a record is
        thread_id, certain."""
        rec = row("codex", "thread-me", 100, cwd=self.tmp)
        reply, seen = self._tool_as_thread(
            "xsm_grant", {"runtime": "codex", "options": ["full_access"], "reason": "why"},
            [rec], thread="thread-me")
        self.assertEqual(seen["ctx"].basis, "thread_id")
        self.assertTrue(seen["ctx"].sure)


class FileReadingNeedsSureIdentityTest(TempState):
    """G01 review F2/O-F4: `xsm_doc_endorse` reads a file from the caller's own
    folder, so a guessed neighbor must not reach it (spec P01.2, IC01). The path
    is taken from `me.cwd`; that the cwd is authority for the file is D07's
    question, but the identity must not be a guess."""

    def _tool(self, args, records, comm="codex"):
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "xsm_doc_endorse", "arguments": args}}
        out = io.StringIO()
        server = mcp.Server(io.StringIO(json.dumps(msg) + "\n"), out)
        with _home_env({}), \
                mock.patch.object(mcp.identity, "ancestor_pid", return_value=DAEMON), \
                mock.patch.object(mcp.identity, "comm", return_value=comm), \
                mock.patch.object(mcp.registry, "raw_records", return_value=records), \
                mock.patch.object(mcp.registry, "_enrich", side_effect=lambda r: r), \
                mock.patch.object(mcp.registry, "adopt_codex_thread", return_value=None):
            server.serve()
        return json.loads(out.getvalue())["result"]

    def test_a_guessed_neighbor_cannot_read_a_file(self):
        recs = [row("codex", "thread-a", 100, cwd=self.tmp),
                row("codex", "thread-b", 200, cwd=self.tmp)]
        reply = self._tool({"doc": "doc.md", "node": "n1"}, recs)
        self.assertTrue(reply["isError"])
        self.assertIn("guess at which session", reply["content"][0]["text"])

    def test_a_sure_caller_gets_past_the_guard(self):
        recs = [row("codex", "only", 100, cwd=self.tmp)]
        reply = self._tool({"doc": "missing.md", "node": "n1"}, recs)
        # Past the identity guard, it fails for its own reason: no such file.
        self.assertTrue(reply["isError"])
        self.assertNotIn("guess at which session", reply["content"][0]["text"])


class McpCallerIdentityTest(unittest.TestCase):
    TWO = [row("codex", "thread-a", 100), row("codex", "thread-b", 200)]

    def test_thread_named_in_the_call_wins_over_the_newest_record(self):
        seen, result = serve_one(self.TWO, meta={"threadId": "thread-a"})
        self.assertFalse(result["isError"])
        self.assertEqual(seen[0]["session_id"], "thread-a")
        seen, _ = serve_one(self.TWO, meta={"threadId": "thread-b"})
        self.assertEqual(seen[0]["session_id"], "thread-b")

    def test_each_call_uses_its_own_thread(self):
        metas = [{"threadId": "thread-a"}, {}, {"threadId": "thread-b"}]
        msgs = [{"jsonrpc": "2.0", "id": i, "method": "tools/call",
                 "params": {"name": "xsm_inbox", "_meta": m}} for i, m in enumerate(metas)]
        server = mcp.Server(io.StringIO("".join(json.dumps(m) + "\n" for m in msgs)), io.StringIO())
        got = []
        server.call = lambda name, args: got.append(server.call_thread) or "ok"
        server.serve()
        self.assertEqual(got, ["thread-a", None, "thread-b"])

    def test_unknown_thread_that_cannot_be_adopted_uses_the_most_recent(self):
        # Untrusted home / thread in no state DB: connect as the newest record
        # rather than refuse (user decision, 2026-09-30).
        seen, result = serve_one(self.TWO, meta={"threadId": "thread-z"})
        self.assertFalse(result["isError"])
        self.assertEqual(seen[0]["session_id"], "thread-b")

    def test_ended_thread_record_is_not_used(self):
        recs = [row("codex", "thread-a", 100, state="ended"), row("codex", "thread-b", 200)]
        seen, _ = serve_one(recs, meta={"threadId": "thread-a"})
        self.assertEqual(seen[0]["session_id"], "thread-b")

    def test_several_threads_without_a_thread_id_use_the_most_recent(self):
        seen, result = serve_one(self.TWO)
        self.assertFalse(result["isError"])
        self.assertEqual(seen[0]["session_id"], "thread-b")

    def test_single_codex_thread_needs_no_thread_id(self):
        seen, result = serve_one([row("codex", "thread-a", 100)])
        self.assertFalse(result["isError"])
        self.assertEqual(seen[0]["session_id"], "thread-a")

    def test_claude_path_is_unchanged(self):
        recs = [row("claude", "old", 100), row("claude", "new", 200),
                row("claude", "other-pid", 300, pid=1)]
        seen, _ = serve_one(recs)
        self.assertEqual(seen[0]["session_id"], "new")
        # Claude sends no thread id; a stray one does not change who it is.
        seen, result = serve_one(recs, meta={"threadId": "old"})
        self.assertFalse(result["isError"])
        self.assertEqual(seen[0]["session_id"], "new")

    def test_no_session_process_means_no_identity(self):
        seen, _ = serve_one(self.TWO, pid=None)
        self.assertEqual(seen, [None])


class AdoptUnknownThreadTest(unittest.TestCase):
    """A thread with no live record is registered on the spot (real registry
    in a temp XSM_HOME, fake Codex home with a state DB)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="xsm-mcpid-")
        self._old_home = paths.HOME
        paths.HOME = os.path.join(self.tmp, "xsm")
        paths.ensure_home()
        self.addCleanup(setattr, paths, "HOME", self._old_home)
        self.home = os.path.realpath(os.path.join(self.tmp, "codex"))
        os.makedirs(self.home)
        con = sqlite3.connect(os.path.join(self.home, "state_5.sqlite"))
        con.execute("create table threads (id text, name text, cwd text, source text)")
        con.execute("insert into threads values ('new-thread', 'Fresh', ?, 'cli')",
                    (os.path.join(self.tmp, "proj"),))
        con.execute("insert into threads values ('sub-thread', 'sub', '/x', ?)",
                    (json.dumps({"subagent": {"thread_spawn": {"parent_thread_id": "thread-a"}}}),))
        con.execute("insert into threads values ('orphan', 'orphan', '/x', ?)",
                    (json.dumps({"subagent": {"thread_spawn": {"parent_thread_id": "gone"}}}),))
        con.commit()
        con.close()
        self.env = mock.patch.dict(os.environ, {"CODEX_HOME": self.home})
        self.env.start()
        self.addCleanup(self.env.stop)

    def serve(self, thread, records, trusted=True):
        seen = []
        msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "xsm_inbox", "_meta": {"threadId": thread}}}
        server = mcp.Server(io.StringIO(json.dumps(msg) + "\n"), io.StringIO())
        server.call = lambda name, args: seen.append(server.session()) or "ok"
        with mock.patch.object(mcp.identity, "ancestor_pid", return_value=DAEMON), \
                mock.patch.object(registry, "_hooks_will_register", return_value=trusted), \
                mock.patch.object(registry.identity, "is_app_server", return_value=True), \
                mock.patch.object(registry, "raw_records", return_value=records), \
                mock.patch.object(registry, "_enrich", side_effect=lambda rec: rec), \
                mock.patch.object(registry, "by_session", side_effect=lambda runtime, sid:
                    next((r for r in records if r.get("runtime") == runtime
                          and r.get("session_id") == sid), None)):
            server.serve()
        return seen[0]

    def test_unknown_thread_in_a_trusted_home_is_registered_and_used(self):
        me = self.serve("new-thread", [row("codex", "thread-b", 200)])
        self.assertEqual(me["session_id"], "new-thread")
        self.assertEqual(me["home"], self.home)
        self.assertEqual(me["cwd"], os.path.realpath(os.path.join(self.tmp, "proj")))
        self.assertTrue(me["adopted"])
        self.assertEqual(me["pid"], DAEMON)
        self.assertTrue(me["app_server"])
        stored = paths.read_json(registry._record_path("codex", "new-thread"))
        self.assertEqual(stored["session_id"], "new-thread")
        self.assertTrue(stored["adopted"])

    def test_first_thread_of_a_daemon_with_no_records_is_registered(self):
        me = self.serve("new-thread", [])
        self.assertEqual(me["session_id"], "new-thread")

    def test_unknown_thread_in_an_untrusted_home_falls_back_to_the_most_recent(self):
        me = self.serve("new-thread", [row("codex", "thread-a", 100), row("codex", "thread-b", 200)],
                        trusted=False)
        self.assertEqual(me["session_id"], "thread-b")
        self.assertIsNone(paths.read_json(registry._record_path("codex", "new-thread")))

    def test_sub_agent_signs_as_its_live_parent(self):
        me = self.serve("sub-thread", [row("codex", "thread-a", 100), row("codex", "thread-b", 200)])
        self.assertEqual(me["session_id"], "thread-a")
        self.assertIsNone(paths.read_json(registry._record_path("codex", "sub-thread")))

    def test_orphan_sub_agent_is_registered_as_itself(self):
        me = self.serve("orphan", [row("codex", "thread-b", 200)])
        self.assertEqual(me["session_id"], "orphan")

    def test_exact_match_is_not_adopted_over(self):
        me = self.serve("thread-a", [row("codex", "thread-a", 100), row("codex", "thread-b", 200)])
        self.assertEqual(me["session_id"], "thread-a")
        self.assertNotIn("adopted", me)


if __name__ == "__main__":
    unittest.main()


class UnresolvedCodexCallTest(unittest.TestCase):
    """T0: a Codex call whose thread has no record and cannot be adopted used to
    read "no hook record for it" (the server's own env names no thread), which
    hid both the runtime and the cause. The refusal names the thread the call
    named and how the lookup ended."""

    def test_refusal_names_the_called_thread_and_the_lookup(self):
        server = mcp.Server(io.StringIO(""), io.StringIO())
        server.call_thread = "thread-new"
        env = {k: v for k, v in os.environ.items() if k not in ("CODEX_THREAD_ID", "CLAUDE_CODE_SESSION_ID")}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(mcp.identity, "ancestor_pid", return_value=DAEMON), \
                mock.patch.object(mcp.identity, "comm", return_value="codex"), \
                mock.patch.object(mcp.registry, "raw_records", return_value=[]), \
                mock.patch.object(mcp.registry, "adopt_codex_thread", return_value=None), \
                mock.patch.object(mcp.registry, "adopt_claude_process", return_value=None):
            with self.assertRaises(mcp.channel.ChannelError) as raised:
                server.call("xsm_inbox", {})
        text = str(raised.exception)
        self.assertIn("this Codex thread (thread-new) is not registered yet", text)
        self.assertIn("caller lookup: no record carries this pid", text)
        self.assertNotIn("no hook record for it", text)
