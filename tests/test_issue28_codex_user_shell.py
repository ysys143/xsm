"""#28: a command the person runs in their Codex session's shell box fires no hook, so
the environment is its only witness. A tool call carries Codex's own markers."""
import contextlib
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import test_xsm  # noqa: E402

TempState = test_xsm.TempState
SESSION = "01a20716-afce-77e0-948b-b3bf88f3e54e"


class CodexUserShellTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import registry, workers
        self.folder = os.path.realpath(os.path.join(self.tmp, "repo-a"))
        os.makedirs(self.folder, exist_ok=True)
        registry.upsert("codex", os.path.join(self.tmp, "homes", "codex"), SESSION, os.getpid(),
                        self.folder, name="coder")
        self.me = registry.by_session("codex", SESSION)
        base = {key: "" for key in ("CODEX_TOOL_CALL_ID", "CODEX_CI", "CODEX_SANDBOX",
                                    "CODEX_SANDBOX_NETWORK_DISABLED", "XSM_WORKER")}
        for patch in (mock.patch.object(registry, "me", return_value=self.me),
                      mock.patch.object(workers, "human_terminal", return_value=False),
                      mock.patch.dict(os.environ, dict(base, CODEX_THREAD_ID=SESSION,
                                                       CODEX_VERSION="0.170.0"))):
            patch.start()
            self.addCleanup(patch.stop)

    def _join(self, project="proj28"):
        from xsm import cli
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["join", project])
        return code, out.getvalue() + err.getvalue()

    def _joined(self, project="proj28"):
        from xsm import config
        scope = next((s for s in config._raw().get("scopes") or [] if s.get("id") == project), None)
        return bool(scope and scope.get("members"))

    def test_a_command_with_no_tool_markers_is_the_persons_own_and_joins(self):
        code, text = self._join()
        self.assertEqual(code, 0, text)
        self.assertNotIn("needs your user's yes", text)
        self.assertTrue(self._joined())
        from xsm import paths
        rows = [r for r in paths.read_jsonl("decisions.jsonl") if r.get("via") == "codex-user-shell"]
        self.assertEqual([(r["event"], r["verb"], r["target"]) for r in rows],
                         [("consent", "join", "proj28")], "the record says how it was known")
        from xsm import cli
        self.assertIn("Codex shell box", cli._by(), "what a link or a join records as the decider says it too")

    def test_each_tool_marker_makes_it_an_agents_call_and_it_is_refused(self):
        for marker in ("CODEX_TOOL_CALL_ID", "CODEX_CI", "CODEX_SANDBOX", "CODEX_SANDBOX_NETWORK_DISABLED"):
            with self.subTest(marker=marker), mock.patch.dict(os.environ, {marker: "1"}):
                code, text = self._join()
                self.assertEqual(code, 2, text)
                self.assertIn("needs your user's yes", text)
                self.assertFalse(self._joined())

    def test_another_threads_environment_is_not_this_sessions_person(self):
        with mock.patch.dict(os.environ, {"CODEX_THREAD_ID": "some-other-thread"}):
            code, text = self._join()
        self.assertEqual(code, 2, text)
        self.assertFalse(self._joined())

    def test_no_thread_in_the_environment_is_not_a_codex_shell_box(self):
        env = {k: v for k, v in os.environ.items() if k != "CODEX_THREAD_ID"}
        with mock.patch.dict(os.environ, env, clear=True):
            code, text = self._join()
        self.assertEqual(code, 2, text)

    def test_a_codex_version_nobody_measured_is_asked_as_before(self):
        for version in ("0.169.9", "0.172.0", "1.0.0", ""):
            with self.subTest(version=version), mock.patch.dict(os.environ, {"CODEX_VERSION": version}):
                code, text = self._join()
                self.assertEqual(code, 2, text)
                self.assertFalse(self._joined())
        with mock.patch.dict(os.environ, {"CODEX_VERSION": "0.171.3"}):
            code, text = self._join("proj28b")
        self.assertEqual(code, 0, text)

    def test_the_asks_that_name_an_id_or_a_plan_are_not_passed(self):
        """approve, unblock, handover, held deliver ... say nothing the person has seen."""
        from xsm import cli
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["unblock", "abc123"])
        self.assertEqual(code, 2, out.getvalue() + err.getvalue())
        self.assertIn("needs your user's yes", out.getvalue() + err.getvalue())
        from xsm import config
        self.assertFalse([r for r in __import__("xsm.paths", fromlist=["paths"]).read_jsonl("decisions.jsonl")
                          if r.get("via") == "codex-user-shell"])

    def test_a_binding_ask_is_not_passed_even_when_typed(self):
        from xsm import cli
        why = cli._person_or_refuse("migrating", "xsm_migrate", typed=("migrate", "x"),
                                    binding={"profile_migration": "id"})
        self.assertIn("needs your user's yes", why or "")

    def test_a_claude_session_gets_no_such_pass(self):
        from xsm import consent
        claude = dict(self.me, runtime="claude")
        self.assertFalse(consent.codex_user_shell(claude))
        self.assertTrue(consent.codex_user_shell(self.me))
        self.assertFalse(consent.codex_user_shell(None))

    def test_a_worker_is_never_the_person(self):
        from xsm import consent
        with mock.patch.object(consent, "unattended", return_value={"name": "w"}):
            self.assertFalse(consent.codex_user_shell(self.me))
        with mock.patch.dict(os.environ, {"XSM_WORKER": "w1"}):
            self.assertFalse(consent.codex_user_shell(self.me))

    def test_the_peer_message_or_output_text_is_still_no_consent(self):
        """The wrapper that reaches the model after the run is text, not a witness."""
        from xsm import consent
        wrapped = "<user_shell_command>\n<command>xsm join proj28</command>\n</user_shell_command>"
        self.assertTrue(consent.not_a_reply(wrapped))
        self.assertIsNone(consent.record(self.me, {"hook_event_name": "UserPromptSubmit", "prompt": wrapped}))
        code, text = self._join_with(["CODEX_TOOL_CALL_ID"])
        self.assertEqual(code, 2, text)

    def _join_with(self, markers):
        with mock.patch.dict(os.environ, {m: "x" for m in markers}):
            return self._join()


if __name__ == "__main__":
    unittest.main()
