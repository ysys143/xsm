"""`xsm list` must not wait for a session's folder (2026-10-02, the Mac mini).

It read each session's `<cwd>/.claude/settings*.json` and ran `git rev-parse` per
folder, 42 git calls for 8 folders, with no limit that holds: one folder under
~/Documents whose opendir never returned froze `list` and `list -a` for good. A probe
that does not answer in a second is unknown, a folder is asked once, and a folder that
did not answer is not asked again."""
import contextlib
import io
import os
import subprocess
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import test_xsm  # noqa: E402

# Module names only: a class imported here by name would run its tests twice.
TempState = test_xsm.TempState


class _StuckGit:
    """A git that is in a read that never returns: communicate waits out its timeout,
    and kill changes nothing (the child is not interruptible)."""

    killed = 0

    def __init__(self, *args, **kwargs):
        self.stdout = io.StringIO()
        self.returncode = None

    def communicate(self, timeout=None):
        time.sleep(timeout)
        raise subprocess.TimeoutExpired("git", timeout)

    def kill(self):
        type(self).killed += 1


class BoundedTest(unittest.TestCase):
    def test_a_fast_answer_is_the_answer_and_a_raise_is_unknown(self):
        from xsm import probe
        self.assertEqual(probe.bounded(lambda: 7), 7)
        self.assertIsNone(probe.bounded(lambda: {}["nope"]))
        self.assertEqual(probe.bounded(lambda: 1 / 0, default="unknown"), "unknown")

    def test_a_read_that_never_returns_costs_the_deadline_and_no_more(self):
        from xsm import probe
        began = time.monotonic()
        self.assertEqual(probe.bounded(time.sleep, 30, timeout=0.2, default="unknown"), "unknown")
        self.assertLess(time.monotonic() - began, 2)

    def test_the_ordinary_deadline_is_read_when_it_is_asked_not_when_it_is_defined(self):
        from xsm import probe
        with mock.patch.object(probe, "READ_TIMEOUT", 0.2):
            began = time.monotonic()
            self.assertIsNone(probe.bounded(time.sleep, 30))
        self.assertLess(time.monotonic() - began, 2)

    def test_inside_quick_a_folder_that_did_not_answer_is_not_asked_again(self):
        from xsm import probe
        calls = []

        def slow():
            calls.append(1)
            time.sleep(30)

        with probe.quick(0.2):
            began = time.monotonic()
            for _ in range(5):
                probe.bounded(slow, folder="/stalled")
            self.assertEqual(len(calls), 1)
            self.assertLess(time.monotonic() - began, 1.5)
            self.assertEqual(probe.bounded(lambda: "ok", folder="/other"), "ok")
        # Outside it nothing is remembered: a folder that stalled once may answer later.
        self.assertEqual(probe.bounded(lambda: "ok", folder="/stalled"), "ok")

    def test_quick_caps_a_longer_deadline_and_remembers_one_answer_per_question(self):
        from xsm import probe
        asked = []
        with probe.quick(0.2):
            self.assertEqual(probe.limit(5.0), 0.2)
            for _ in range(4):
                probe.remember(("k", 1), lambda: asked.append(1) or "answer")
        self.assertEqual(len(asked), 1)
        self.assertEqual(probe.limit(5.0), 5.0, "and nothing is capped outside it")
        for _ in range(2):
            probe.remember(("k", 1), lambda: asked.append(1))
        self.assertEqual(len(asked), 3, "outside quick every call asks again")


class GitTest(TempState):
    def test_a_git_that_does_not_answer_is_killed_not_waited_for_and_unknown(self):
        from xsm import probe
        _StuckGit.killed = 0
        with mock.patch.object(probe.subprocess, "Popen", _StuckGit):
            began = time.monotonic()
            self.assertIsNone(probe.git("/stalled", "rev-parse", timeout=0.2))
        self.assertLess(time.monotonic() - began, 1.5)
        self.assertEqual(_StuckGit.killed, 1)

    def test_inside_quick_the_folder_that_stalled_costs_one_deadline_not_one_per_question(self):
        from xsm import probe
        _StuckGit.killed = 0
        with mock.patch.object(probe.subprocess, "Popen", _StuckGit):
            with probe.quick(0.2):
                began = time.monotonic()
                for _ in range(6):
                    self.assertIsNone(probe.git("/stalled", "rev-parse"))
                self.assertLess(time.monotonic() - began, 1.5)
            self.assertEqual(_StuckGit.killed, 1)

    def test_a_missing_git_or_a_failed_one_is_unknown_and_a_good_one_is_its_output(self):
        from xsm import probe
        with mock.patch.object(probe.subprocess, "Popen", side_effect=FileNotFoundError("git")):
            self.assertIsNone(probe.git("/x", "status"))
        self.assertIsNone(probe.git(os.path.join(os.sep, "nonexistent-folder-for-xsm"), "status"))
        folder = os.path.join(self.tmp, "a-repository")
        os.makedirs(folder)
        subprocess.run(["git", "init", "-q", folder], check=True)
        self.assertEqual(probe.git(folder, "rev-parse", "--is-inside-work-tree"), "true\n")


class FoldersTest(TempState):
    """A repository's top and a session's settings, asked once and never waited on."""

    def _repo(self, name):
        folder = os.path.realpath(os.path.join(self.tmp, "work", name))
        os.makedirs(folder)
        subprocess.run(["git", "init", "-q", folder], check=True)
        return folder

    def test_git_repo_is_asked_once_per_folder_inside_quick_and_each_time_outside(self):
        from xsm import config, probe
        folder = self._repo("one")
        with mock.patch.object(probe, "git", wraps=probe.git) as asked:
            with probe.quick():
                tops = {config.git_repo(folder) for _ in range(5)}
                config.project_root(folder)
            self.assertEqual(asked.call_count, 1)
            self.assertEqual(tops, {(folder, os.path.join(folder, ".git"))})
            config.git_repo(folder)
            config.git_repo(folder)
            self.assertEqual(asked.call_count, 3, "the MCP server must see a repository made later")

    def test_a_folder_that_is_no_repository_and_one_that_stalls_are_both_no_repository(self):
        from xsm import config, probe
        plain = os.path.join(self.tmp, "plain")
        os.makedirs(plain)
        self.assertEqual(config.git_repo(plain), (None, None))
        self.assertEqual(config.project_root(plain), os.path.realpath(plain))
        with mock.patch.object(probe.subprocess, "Popen", _StuckGit), probe.quick(0.2):
            self.assertEqual(config.git_repo("/stalled"), (None, None))

    def test_a_settings_file_in_a_folder_that_does_not_answer_tightens_nothing(self):
        from xsm import paths, probe, registry
        home = os.path.join(self.tmp, "claude-home")
        project = os.path.join(self.tmp, "project")
        paths.write_json(os.path.join(home, "settings.json"), {"crossSessionInbound": "accept"})
        paths.write_json(os.path.join(project, ".claude", "settings.json"),
                         {"crossSessionInbound": "refuse"})
        self.assertEqual(registry.inbound_setting(home, project), "refuse", "as it was")
        real = paths.read_json

        def stalled(path, *a, **k):
            if path.startswith(project):
                time.sleep(30)
            return real(path, *a, **k)

        with mock.patch.object(paths, "read_json", stalled), probe.quick(0.2):
            began = time.monotonic()
            self.assertEqual(registry.inbound_setting(home, project), "accept")
            self.assertEqual(registry.inbound_setting(home, project), "accept")
            self.assertLess(time.monotonic() - began, 1.5, "asked once, and not for long")

    def test_the_settings_of_a_folder_are_read_once_inside_quick(self):
        from xsm import paths, probe, registry
        home = os.path.join(self.tmp, "claude-home2")
        project = os.path.join(self.tmp, "project2")
        paths.write_json(os.path.join(project, ".claude", "settings.local.json"),
                         {"crossSessionInbound": "hold"})
        real = paths.read_json
        reads = []

        def counting(path, *a, **k):
            if path.startswith(project):
                reads.append(path)
            return real(path, *a, **k)

        with mock.patch.object(paths, "read_json", counting):
            with probe.quick():
                for _ in range(4):
                    self.assertEqual(registry.inbound_setting(home, project), "hold")
            self.assertEqual(len(reads), 2, "settings.json and settings.local.json, once")


class ListTest(TempState):
    """The command itself, with a folder whose git and files never answer."""

    def setUp(self):
        super().setUp()
        from xsm import registry, workers
        self.folders = []
        for n in range(4):
            folder = os.path.realpath(os.path.join(self.tmp, "work", "f%d" % n))
            os.makedirs(folder)
            subprocess.run(["git", "init", "-q", folder], check=True)
            self.folders.append(folder)
            registry.upsert("claude", os.path.join(self.tmp, "homes", "claude"), "s%d" % n,
                            os.getpid(), folder, name="n%d" % n)
        self.me = registry.by_session("claude", "s0")
        for patch in (mock.patch.object(registry, "me", return_value=self.me),
                      mock.patch.object(workers, "human_terminal", return_value=False)):
            patch.start()
            self.addCleanup(patch.stop)

    def _list(self, *argv):
        from xsm import cli
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["list"] + list(argv))
        self.err = err.getvalue()
        return code, out.getvalue()

    def test_it_asks_git_once_per_folder(self):
        from xsm import probe
        with mock.patch.object(probe, "git", wraps=probe.git) as asked:
            code, text = self._list("-a")
        self.assertEqual(code, 0, text)
        self.assertLessEqual(asked.call_count, len(self.folders), "it was 42 for 8 folders")
        self.assertEqual(len([l for l in text.splitlines() if "@claude" in l]), 4, text)

    def test_a_stalled_folder_is_listed_and_costs_about_a_second_at_most(self):
        from xsm import paths, probe
        stalled = self.folders[2]
        real_popen, real_read = subprocess.Popen, paths.read_json

        def popen(args, *a, **k):
            return _StuckGit() if args[:2] == ["git", "-C"] and args[2] == stalled \
                else real_popen(args, *a, **k)

        def read(path, *a, **k):
            if path.startswith(stalled):
                time.sleep(30)
            return real_read(path, *a, **k)

        with mock.patch.object(probe.subprocess, "Popen", popen), \
                mock.patch.object(paths, "read_json", read), \
                mock.patch.object(probe, "QUICK_TIMEOUT", 0.3):
            for argv in (["-a"], []):
                began = time.monotonic()
                code, text = self._list(*argv)
                took = time.monotonic() - began
                self.assertEqual(code, 0, text)
                self.assertLess(took, 3.0, "a folder that does not answer must not hold it")
                self.assertIn("git x", self.err, "and the list says it may be incomplete (OBS-1)")
                if argv:
                    self.assertIn("n2@", text, "the session in it is still listed")
                    self.assertEqual(len([l for l in text.splitlines() if "@claude" in l]), 4, text)


def _answers(out="ok\n", code=0):
    return mock.Mock(communicate=mock.Mock(return_value=(out, None)), returncode=code)


class UnansweredTest(TempState):
    """OBS-1: what did not answer is counted by kind, so a list that skipped a probe
    does not pass for complete."""

    def test_a_timeout_is_counted_under_the_commands_name(self):
        """OBS-1: `ps`, whatever path it was started by; the child is not waited for."""
        from xsm import probe
        child = mock.Mock(stdout=io.StringIO())
        child.communicate.side_effect = subprocess.TimeoutExpired("ps", 1)
        with mock.patch.object(probe.subprocess, "Popen", return_value=child):
            with probe.quick():
                self.assertIsNone(probe.command(["/bin/ps", "-x"]))
        self.assertEqual(probe.unanswered(), {"ps": 1})

    def test_a_spent_budget_and_a_stalled_folder_are_counted_as_skipped(self):
        """OBS-1: a probe never started is a probe that did not answer."""
        from xsm import probe
        with mock.patch.object(probe.subprocess, "Popen") as popen:
            with probe.quick(budget=0):
                probe.command(["lsof"])
                probe.command(["lsof"])
                probe.bounded(lambda: 1, folder="/x")
            self.assertEqual(probe.unanswered(), {"lsof": 2, "read": 1})
            with probe.quick():
                probe._gave_up("/stalled")
                probe.command(["git"], folder="/stalled")
                probe.bounded(lambda: 1, folder="/stalled")
            self.assertEqual(probe.unanswered(), {"git": 1, "read": 1})
        popen.assert_not_called()

    def test_a_read_that_runs_out_of_time_is_a_read_timeout(self):
        """OBS-1: kind `read`."""
        from xsm import probe
        with probe.quick(0.1):
            self.assertIsNone(probe.bounded(time.sleep, 30))
        self.assertEqual(probe.unanswered(), {"read": 1})

    def test_a_probe_that_answered_is_not_counted(self):
        """OBS-1: not an answer of no, not an exit code, not a read that raised."""
        from xsm import probe
        with mock.patch.object(probe.subprocess, "Popen", return_value=_answers("", 1)):
            with probe.quick():
                self.assertIsNone(probe.command(["git"]))
                self.assertEqual(probe.bounded(lambda: 1), 1)
                self.assertIsNone(probe.bounded(lambda: {}["nope"]))
        self.assertEqual(probe.unanswered(), {})

    def test_the_counts_are_reset_by_the_outermost_quick_and_readable_after_it(self):
        """OBS-1: a nested block adds to the same command's counts."""
        from xsm import probe
        with probe.quick(budget=0):
            probe.command(["ps"])
            with probe.quick():
                probe.command(["ps"])
                self.assertEqual(probe.unanswered(), {"ps": 2})
        self.assertEqual(probe.unanswered(), {"ps": 2})
        with probe.quick():
            self.assertEqual(probe.unanswered(), {})

    def test_each_count_goes_on_the_commands_span(self):
        """OBS-1: xsm.probe.<kind>.timeout / .skipped, the way xsm.state.* are."""
        from xsm import probe, telemetry
        if telemetry.DISABLED:
            self.skipTest("XSM_NO_TELEMETRY is set; there is no span to count on")
        child = mock.Mock(stdout=io.StringIO())
        child.communicate.side_effect = subprocess.TimeoutExpired("lsof", 1)
        with telemetry.span("xsm.cli.list") as span, mock.patch.object(
                probe.subprocess, "Popen", return_value=child):
            with probe.quick(1, 5):
                probe.command(["lsof"])
            with probe.quick(1, 0):
                probe.command(["lsof"])
                probe.command(["lsof"])
        self.assertEqual(span.attributes["xsm.probe.lsof.timeout"], 1)
        self.assertEqual(span.attributes["xsm.probe.lsof.skipped"], 2)

    def test_the_socket_and_the_daemon_count_what_the_budget_skipped(self):
        """OBS-1: kinds `socket` and `daemon`; a socket that does not answer in time is
        a timeout, and is still not alive."""
        import socket
        from xsm import codex_daemon, identity, probe
        os.makedirs(os.path.dirname(codex_daemon.socket_path(self.tmp)), exist_ok=True)
        with open(codex_daemon.socket_path(self.tmp), "w"):
            pass
        with probe.quick(budget=0):
            self.assertIsNone(identity.socket_live("/tmp/no-socket"))
            self.assertIsNone(codex_daemon.loaded_threads(self.tmp))
        self.assertEqual(probe.unanswered(), {"socket": 1, "daemon": 1})
        slow = mock.MagicMock()
        slow.__enter__.return_value.connect.side_effect = socket.timeout("timed out")
        with mock.patch.object(identity.socket, "socket", return_value=slow), probe.quick():
            self.assertIs(identity.socket_live("/tmp/no-answer"), False)
        self.assertEqual(probe.unanswered(), {"socket": 1})

    def _list_that_missed(self, *argv, missed=True):
        from xsm import cli, probe
        out, err = io.StringIO(), io.StringIO()

        def listing(args):
            if missed:
                probe.missed("lsof", "timeout")
                probe.missed("lsof", "skipped")
                probe.missed("git", "timeout")
            return 0

        with mock.patch.object(cli, "_cmd_list", listing), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(cli.main(["list"] + list(argv)), 0)
        return err.getvalue()

    def test_list_says_once_on_stderr_which_probes_did_not_answer(self):
        """OBS-1: one line, with the kinds and how often, in every format."""
        for argv in ([], ["--json"], ["--table"]):
            err = self._list_that_missed(*argv)
            lines = [l for l in err.splitlines() if "did not answer" in l]
            self.assertEqual(len(lines), 1, (argv, err))
            self.assertIn("git x1, lsof x2", lines[0])
            self.assertIn("incomplete", lines[0])
            self.assertIn("xsm doctor", lines[0])

    def test_list_prints_nothing_when_every_probe_answered(self):
        """OBS-1: no notice, and no empty line."""
        self.assertEqual(self._list_that_missed(missed=False), "")


if __name__ == "__main__":
    unittest.main()
