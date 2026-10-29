"""Issue #17/#18: unrelated sessions and stalled discovery cannot hold a lookup."""
import collections
import contextlib
import io
import json
import os
import sqlite3
import subprocess
import time
import unittest
from unittest import mock

from tests import test_codex_wake, test_xsm


class DiscoveryTest(test_xsm.TempState):
    def setUp(self):
        super().setUp()
        from xsm import paths, registry
        self.home = os.path.join(self.tmp, "codex")
        self.here = os.path.join(self.tmp, "here")
        self.there = os.path.join(self.tmp, "there")
        os.makedirs(self.home)
        os.makedirs(self.here)
        os.makedirs(self.there)
        self.mine = registry.upsert("codex", self.home, "mine", os.getpid(), self.here,
                                    name="mine")
        self.peer = registry.upsert("codex", self.home, "peer", os.getpid(), self.here,
                                    name="peer")
        # Hundreds of unrelated pointers, without making hundreds of real ps calls.
        for n in range(350):
            row = dict(self.peer, session_id="elsewhere-%d" % n, cwd=self.there,
                       ref="%06x" % n, name="elsewhere-%d" % n)
            paths.write_json(registry._record_path("codex", row["session_id"]), row)
        os.environ["CODEX_THREAD_ID"] = "mine"
        self.addCleanup(os.environ.pop, "CODEX_THREAD_ID", None)

    def _cli(self, *args):
        from xsm import cli
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = cli.main(list(args))
        return rc, out.getvalue()

    def test_who_probes_only_itself_and_never_starts_global_discovery_or_prune(self):
        from xsm import housekeeping, registry
        with mock.patch.object(registry, "_enrich", wraps=registry._enrich) as enriched, \
                mock.patch.object(registry, "adopt_open_codex") as adopt, \
                mock.patch.object(housekeeping, "maybe_prune") as prune:
            rc, out = self._cli("who", "--table")
        self.assertEqual(rc, 0, out)
        self.assertIn("mine", out)
        self.assertEqual([c.args[0]["session_id"] for c in enriched.call_args_list], ["mine"])
        adopt.assert_not_called()
        prune.assert_not_called()

    def test_project_list_never_probes_unrelated_pointers(self):
        from xsm import registry
        with mock.patch.object(registry, "_enrich", wraps=registry._enrich) as enriched:
            rc, out = self._cli("list", "--table", "--dir", self.here)
        self.assertEqual(rc, 0, out)
        self.assertIn("peer", out)
        self.assertNotIn("elsewhere-", out)
        self.assertEqual({c.args[0]["session_id"] for c in enriched.call_args_list},
                         {"mine", "peer"})

    def test_runtime_and_home_filters_apply_before_peer_probes(self):
        from xsm import registry
        for filters, wanted in ((["--runtime", "claude"], set()),
                                (["--home", "missing"], set()),
                                (["--runtime", "codex", "--home", "codex"], {"mine", "peer"})):
            with mock.patch.object(registry, "_enrich", wraps=registry._enrich) as enriched:
                rc, out = self._cli("list", "--dir", self.here, "--json", *filters)
            self.assertEqual(rc, 0)
            self.assertEqual({r["session_id"] for r in json.loads(out)}, wanted)
            self.assertEqual({c.args[0]["session_id"] for c in enriched.call_args_list},
                             wanted | {"mine"})

    def test_discovery_does_not_register_threads_outside_the_selected_project(self):
        from xsm import registry
        opened = [("foreign", "foreign", self.there, None, 0, 0, os.getpid())]
        fresh = dict(self.peer, session_id="foreign-fresh", cwd=self.there, mcp_pid=99)
        with mock.patch.object(registry, "_hooks_will_register", return_value=True), \
                mock.patch.object(registry, "_open_codex_threads", return_value=opened), \
                mock.patch.object(registry, "fresh_codex_threads", return_value=[fresh]):
            adopted = registry.adopt_open_codex(accept=lambda r: r.get("cwd") == self.here)
        self.assertEqual(adopted, [])
        self.assertEqual(len(registry.raw_records()), 352)

    def test_a_fresh_beacon_is_found_without_enriching_registered_sessions(self):
        from xsm import adapters, registry
        beacon = {"pid": 9999, "ppid": 9998, "started": 1, "cwd": self.here}
        with mock.patch.object(registry, "mcp_beacons", return_value=[beacon]), \
                mock.patch.object(registry.identity, "pid_alive", return_value=True), \
                mock.patch.object(registry.identity, "comm", return_value="codex"), \
                mock.patch.object(adapters, "thread_of_process", return_value="fresh-thread"), \
                mock.patch.object(registry, "_enrich") as enriched:
            fresh = registry.fresh_codex_threads()
        self.assertEqual(fresh[0]["session_id"], "fresh-thread")
        enriched.assert_not_called()

    def test_a_sub_agent_finds_its_parent_by_id_without_enumerating_live_sessions(self):
        from xsm import paths, registry
        con = sqlite3.connect(os.path.join(self.home, "state_5.sqlite"))
        con.execute("create table threads (id text, name text, cwd text, source text)")
        con.execute("insert into threads values (?, ?, ?, ?)",
                    ("sub", "sub", self.here,
                     json.dumps({"subagent": {"thread_spawn": {"parent_thread_id": "mine"}}})))
        con.commit()
        con.close()
        with mock.patch.object(registry, "_hooks_will_register", return_value=True), \
                mock.patch.object(registry, "records") as enumerated:
            found = registry.adopt_codex_thread("sub", os.getpid(), [self.home])
        self.assertEqual(found["session_id"], "mine")
        self.assertIsNone(paths.read_json(registry._record_path("codex", "sub")))
        enumerated.assert_not_called()

    def test_clear_does_not_discover_windows_and_only_checks_the_selected_project(self):
        from xsm import paths, registry
        dead = dict(self.peer, session_id="dead", pid=999999, name="dead")
        paths.write_json(registry._record_path("codex", "dead"), dead)
        with mock.patch.object(registry, "_enrich", wraps=registry._enrich) as enriched, \
                mock.patch.object(registry, "adopt_open_codex") as adopt:
            rc, out = self._cli("list", "clear", "--dir", self.here)
        self.assertEqual(rc, 0, out)
        self.assertIn("cleared 1", out)
        adopt.assert_not_called()
        self.assertEqual({c.args[0]["session_id"] for c in enriched.call_args_list},
                         {"mine", "peer", "dead"})
        self.assertEqual(len(registry.raw_records()), 352)

    def test_stable_address_only_enriches_its_matches_and_keeps_collision_refusal(self):
        from xsm import paths, registry, resolve
        with mock.patch.object(registry, "_enrich", wraps=registry._enrich) as enriched:
            found = resolve.resolve("ref:" + self.peer["ref"])
        self.assertTrue(found.ok)
        self.assertEqual([c.args[0]["session_id"] for c in enriched.call_args_list], ["peer"])
        paths.write_json(registry._record_path("codex", "collision"),
                         dict(self.peer, session_id="collision"))
        self.assertEqual(resolve.resolve("ref:" + self.peer["ref"]).status, "ambiguous")

    def test_cli_send_to_known_ref_skips_discovery_and_reports_unconfirmed(self):
        from xsm import adapters, housekeeping, ledger, registry
        body = "한글 메시지 본문 " * 200
        with mock.patch.object(registry, "adopt_open_codex") as adopt, \
                mock.patch.object(housekeeping, "maybe_prune") as prune, \
                mock.patch.object(adapters, "to_codex", return_value="queued") as queue, \
                mock.patch.object(ledger, "wait_for", return_value={"status": "queued"}) as wait:
            rc, out = self._cli("send", "ref:" + self.peer["ref"], "--text", body, "--wait", "20")
        self.assertEqual(rc, 3, out)
        self.assertIn("sent-unconfirmed", out)
        self.assertIn(body, queue.call_args.args[2])
        self.assertEqual(wait.call_args.args[1], 20)
        adopt.assert_not_called()
        prune.assert_not_called()

    def test_cli_send_reports_transport_failure_and_records_it(self):
        from xsm import adapters, ledger, registry
        with mock.patch.object(registry, "adopt_open_codex") as adopt, \
                mock.patch.object(adapters, "to_codex",
                                  side_effect=adapters.DeliveryError("timeout", "queue stalled")):
            rc, out = self._cli("send", "ref:" + self.peer["ref"], "--text", "hello", "--json")
        result = json.loads(out)
        self.assertEqual(rc, 4)
        self.assertEqual(result["status"], "error")
        self.assertIn("queue stalled", result["reason"])
        self.assertEqual(ledger.status(result["id"])["status"], "error")
        adopt.assert_not_called()

    def test_recent_stopped_records_need_no_liveness_probe_during_prune(self):
        from xsm import housekeeping, identity
        with mock.patch.object(identity, "state_of") as state:
            result = housekeeping.prune(dry_run=True)
        self.assertEqual(result["sessions"], [])
        state.assert_not_called()


class ProbeBudgetTest(test_xsm.TempState):
    def test_scan_failure_or_no_tuis_does_not_call_lsof(self):
        from xsm import probe, registry
        for out in (None, "garbage\n104 /bin/codex app-server\n105 /bin/python\n"):
            with mock.patch.object(probe, "command", return_value=out) as command:
                self.assertEqual(registry._scan_codex(), [])
            command.assert_called_once_with(["ps", "-axo", "pid=,args="])

    def test_exhausted_budget_does_not_start_file_reads(self):
        from xsm import probe
        with probe.quick(budget=0):
            read = mock.Mock()
            self.assertEqual(probe.bounded(read, default="unknown"), "unknown")
            read.assert_not_called()

    def test_exhausted_budget_returns_unknown_for_process_and_daemon_probes(self):
        from xsm import codex_daemon, identity, probe
        os.makedirs(os.path.dirname(codex_daemon.socket_path(self.tmp)), exist_ok=True)
        with open(codex_daemon.socket_path(self.tmp), "w"):
            pass
        with mock.patch.object(probe.subprocess, "Popen") as popen, \
                mock.patch.object(codex_daemon, "_ask_loaded") as ask:
            with probe.quick(budget=0):
                self.assertIsNone(identity.comm(123))
                self.assertIsNone(identity.socket_live("/tmp/no-socket"))
                self.assertFalse(identity.is_app_server(123))
                self.assertIsNone(codex_daemon.loaded_threads(self.tmp))
        popen.assert_not_called()
        ask.assert_not_called()

    def test_process_commands_do_not_revisit_a_stalled_folder(self):
        from xsm import probe
        with probe.quick(), mock.patch.object(probe.subprocess, "Popen") as popen:
            probe._gave_up(self.tmp)
            self.assertIsNone(probe.command(["git"], folder=self.tmp))
        popen.assert_not_called()

    def test_many_stalled_processes_share_one_deadline_and_stop_starting_children(self):
        from xsm import probe
        clock = [0.0]
        waits = []

        class Stalled:
            def __init__(self, *args, **kwargs):
                self.stdout = io.StringIO()

            def communicate(self, timeout):
                waits.append(timeout)
                clock[0] += timeout
                raise subprocess.TimeoutExpired("lsof", timeout)

            def kill(self):
                pass

        with mock.patch.object(probe.time, "monotonic", side_effect=lambda: clock[0]), \
                mock.patch.object(probe.subprocess, "Popen", Stalled):
            with probe.quick(timeout=1, budget=2.5):
                for _ in range(350):
                    self.assertIsNone(probe.command(["lsof"]))
        self.assertEqual(waits, [1, 1, 0.5])
        self.assertEqual(probe.limit(5), 5, "the budget must not persist into the next command")

    def test_process_scan_batches_lsof_and_runs_once_across_homes(self):
        from xsm import probe, registry
        commands = []

        def output(argv, **kwargs):
            commands.append((argv, kwargs))
            if argv[0] == "ps":
                return "101 /bin/codex resume thread-a\n102 /bin/codex\n103 /bin/codex exec task\n"
            return "p101\nn%s\np102\nn%s\n" % (self.tmp, self.tmp)

        with mock.patch.object(probe, "command", side_effect=output), \
                mock.patch.object(registry.identity, "lstart", return_value=None):
            with probe.quick():
                for home in ("one", "two", "three"):
                    rows = probe.remember(("running_codex",), registry._scan_codex)
        self.assertEqual([r[3] for r in rows], [101, 102])
        self.assertEqual(rows[0][2], "thread-a")
        self.assertEqual(len(commands), 2)
        # SCAN-1: -b -w, and the output is read whatever lsof exits with.
        self.assertEqual(commands[1], (["lsof", "-b", "-w", "-a", "-p", "101,102", "-d", "cwd",
                                        "-Fpn"], {"any_exit": True}))


def _finished(out, code):
    """A Popen whose child has finished: `communicate` gives `out`, the exit code is `code`."""
    return mock.Mock(communicate=mock.Mock(return_value=(out, None)), returncode=code)


def _timed_out():
    """A Popen whose child never answers."""
    child = mock.Mock(stdout=io.StringIO())
    child.communicate.side_effect = subprocess.TimeoutExpired("lsof", 1)
    return child


class ProcessScanTest(test_xsm.TempState):
    """SCAN-1: lsof prints what it found and exits 1 when one pid of the batch is gone."""

    def scan(self, lsof):
        """_scan_codex over a process table of two Codex windows, 101 and 102, where
        `lsof` is the process it starts (or the error it raises)."""
        from xsm import probe, registry

        def popen(argv, **kwargs):
            if argv[0] == "ps":
                return _finished("101 /bin/codex\n102 /bin/codex\n", 0)
            if isinstance(lsof, Exception):
                raise lsof
            return lsof

        with mock.patch.object(probe.subprocess, "Popen", side_effect=popen), \
                mock.patch.object(registry.identity, "lstart", return_value=None):
            return registry._scan_codex()

    def test_a_closed_window_does_not_empty_the_scan(self):
        """SCAN-1: lsof exits 1 for the pid that is gone and still prints the other."""
        rows = self.scan(_finished("p101\nfcwd\nn%s\n" % self.tmp, 1))
        self.assertEqual([(r[0], r[3]) for r in rows], [(os.path.realpath(self.tmp), 101)])

    def test_only_the_scan_reads_an_exit_code_it_does_not_trust(self):
        """SCAN-1: every other command still gives nothing when it exits non-zero, and a
        timeout or a command that does not start gives nothing either way."""
        from xsm import probe
        with mock.patch.object(probe.subprocess, "Popen", return_value=_finished("partial\n", 1)):
            self.assertIsNone(probe.command(["lsof"]))
            self.assertEqual(probe.command(["lsof"], any_exit=True), "partial\n")
        with mock.patch.object(probe.subprocess, "Popen", return_value=_timed_out()):
            self.assertIsNone(probe.command(["lsof"], any_exit=True))
        with mock.patch.object(probe.subprocess, "Popen", side_effect=FileNotFoundError("lsof")):
            self.assertIsNone(probe.command(["lsof"], any_exit=True))

    def test_an_lsof_that_hangs_or_is_missing_gives_an_empty_scan(self):
        """SCAN-1: no answer is no windows, not a traceback."""
        self.assertEqual(self.scan(_timed_out()), [])
        self.assertEqual(self.scan(FileNotFoundError("lsof")), [])


class UnnamedWindowTest(test_xsm.TempState):
    """GUESS-1: a window whose start time is unknown is not matched to a thread by it."""

    def setUp(self):
        super().setUp()
        from xsm import config
        self.home = os.path.join(self.tmp, "codex")
        self.folder = os.path.realpath(os.path.join(self.tmp, "work"))
        os.makedirs(self.home)
        os.makedirs(self.folder)
        config.add_home(self.home, "codex")
        # (id, name, cwd, rollout, created_at, updated_at): the newest thread of the folder.
        self.thread = ("T-newest", "newest", self.folder, None, 1000, 2000)

    def open_threads(self, window):
        from xsm import registry
        registry._running_codex = lambda: [window]
        with mock.patch.object(registry, "_codex_recent_threads", return_value=[self.thread]):
            return [t[0] for t in registry._open_codex_threads(self.home)]

    def test_no_start_time_and_no_thread_id_chooses_no_thread(self):
        """GUESS-1: epoch 0 made `created >= epoch - 5` true for every thread of the
        folder; the window is skipped, and the cases that never used the epoch stay."""
        self.assertEqual(self.open_threads((self.folder, 0, None, 4242)), [])
        self.assertEqual(self.open_threads((self.folder, 500, None, 4242)), ["T-newest"])
        self.assertEqual(self.open_threads((self.folder, 0, "?", 4242)), ["T-newest"],
                         "the picker never used the epoch")
        self.assertEqual(self.open_threads((self.folder, 0, "T-newest", 4242)), ["T-newest"],
                         "a window that named its thread keeps it")

    def test_such_a_window_is_not_adopted_on_a_guess(self):
        """GUESS-1: no pointer is written for the folder's newest thread."""
        from xsm import registry
        registry._running_codex = lambda: [(self.folder, 0, None, 4242)]
        with mock.patch.object(registry, "_codex_recent_threads", return_value=[self.thread]), \
                mock.patch.object(registry, "_hooks_will_register", return_value=True):
            self.assertEqual(registry.adopt_open_codex(), [])
        self.assertEqual(registry.raw_records(), [])


class ClaudeNativeTest(test_xsm.TempState):
    def test_a_live_session_keeps_the_socket_claude_recorded_when_the_budget_is_spent(self):
        """NATIVE-1: the native file is small and in the Claude home, so it is read
        whatever is left of the budget; skipped, a pointer without `socket` read as
        stale and `list clear` deleted it."""
        from xsm import paths, probe, registry
        home = os.path.join(self.tmp, "claude")
        os.makedirs(os.path.join(home, "sessions"))
        sock = os.path.join(self.tmp, "inbox.sock")
        paths.write_json(os.path.join(home, "sessions", "%d.json" % os.getpid()),
                         {"pid": os.getpid(), "sessionId": "sid", "name": "native-name",
                          "nameSource": "user", "messagingSocketPath": sock})
        pointer = {"runtime": "claude", "home": home, "session_id": "sid", "pid": os.getpid(),
                   "cwd": self.tmp, "name": "pointer-name", "ref": "abc123"}
        with probe.quick(budget=0):
            row = registry._enrich(pointer)
        self.assertEqual(row["socket"], sock)
        self.assertEqual(row["name"], "native-name")
        self.assertNotIn(row["state"], ("stale", "ended"))


class IdentityProbeTest(test_xsm.TempState):
    """KILL-1: the walk up the process tree and the daemon check do not wait for a child
    they killed, as subprocess.run(timeout=) does."""

    def test_the_walk_up_asks_through_probe_command_not_subprocess_run(self):
        """KILL-1: a ps that answers is the answer; one that does not is None."""
        from xsm import identity
        table = {"100": "200 -zsh\n", "200": "300 /usr/local/bin/codex\n"}
        asked = []

        def ps(argv, *args, **kwargs):
            asked.append(argv)
            return table.get(argv[-1])

        with mock.patch.object(identity.os, "getppid", return_value=100), \
                mock.patch.object(identity.probe, "command", side_effect=ps), \
                mock.patch("subprocess.run", side_effect=AssertionError("waits for its child")):
            self.assertEqual(identity.ancestor_pid({"codex"}), 200)
            self.assertEqual(asked[0], ["ps", "-o", "ppid=,comm=", "-p", "100"])
            table.clear()
            self.assertIsNone(identity.ancestor_pid({"codex"}))

    def test_a_ps_that_never_answers_is_killed_and_not_waited_for(self):
        """KILL-1: no answer is None / False, the child is killed, and wait() is never called."""
        from xsm import identity
        child = _timed_out()
        with mock.patch.object(identity.os, "getppid", return_value=100), \
                mock.patch.object(identity.probe.subprocess, "Popen", return_value=child):
            self.assertIsNone(identity.ancestor_pid({"codex"}))
            self.assertFalse(identity.is_app_server(4242))
        self.assertEqual(child.kill.call_count, 2)
        child.wait.assert_not_called()

    def test_a_spent_budget_starts_no_ps(self):
        """KILL-1: both share the lookup budget."""
        from xsm import identity, probe
        with mock.patch.object(identity.os, "getppid", return_value=100), \
                mock.patch.object(probe.subprocess, "Popen") as popen:
            with probe.quick(budget=0):
                self.assertIsNone(identity.ancestor_pid({"codex"}))
                self.assertFalse(identity.is_app_server(4242))
        popen.assert_not_called()


class MeBudgetTest(test_xsm.TempState):
    def test_me_bounds_its_own_lookup_for_a_thread_with_no_pointer(self):
        """ME-1: inbox, join, ledger --mine ... reach the process scan through me();
        it runs inside the quick budget although the caller opened none."""
        from xsm import probe, registry
        seen = []
        os.environ["CODEX_THREAD_ID"] = "thread-with-no-pointer"
        with mock.patch.object(registry.identity, "ancestor_pid", return_value=None), \
                mock.patch.object(registry, "adopt_open_codex",
                                  side_effect=lambda *a, **k: seen.append(probe.limit(60)) or []):
            self.assertIsNone(registry.me())
        self.assertEqual(len(seen), 1)
        self.assertLessEqual(seen[0], probe.QUICK_TIMEOUT)
        self.assertEqual(probe.limit(60), 60, "and it is not left in force")


class ListOrderTest(test_xsm.TempState):
    """ORDER-1: a default list drops the pointers whose process is gone before it asks
    git where they are."""

    DEAD = 40

    def pointer(self, sid, cwd, pid, **extra):
        from xsm import identity, paths, registry
        row = {"runtime": "codex", "home": self.home, "alias": "codex", "session_id": sid,
               "pid": pid, "lstart": None, "cwd": cwd, "name": sid, "updated": time.time(),
               "ref": identity.ref_of("codex", self.home, sid), "app_server": False}
        row.update(extra)
        if pid is None:
            del row["pid"]
        paths.write_json(registry._record_path("codex", sid), row)

    def setUp(self):
        super().setUp()
        root = os.path.realpath(self.tmp)
        self.home = os.path.join(root, "codex")
        self.here = os.path.join(root, "here")
        self.far = os.path.join(root, "far")
        self.other = os.path.join(root, "other")
        for folder in (self.home, self.here, self.far, self.other):
            os.makedirs(folder)
        child = subprocess.Popen(["true"])
        child.wait()
        with self.assertRaises(ProcessLookupError):
            os.kill(child.pid, 0)
        dead = self.dead = child.pid
        # The daemon of the home lists "hosted" as loaded, though the pid on its pointer is gone.
        daemon = test_codex_wake.FakeDaemon(self.home, "started")
        daemon.loaded = [["hosted"]]
        self.addCleanup(daemon.close)
        self.pointer("mine", self.here, os.getpid())
        self.pointer("peer", self.here, os.getpid())
        self.pointer("hosted", self.here, dead, app_server=True)
        self.pointer("far-live", self.far, os.getpid())
        self.pointer("far-no-pid", self.other, None)
        for n in range(self.DEAD):
            self.pointer("dead-%d" % n, os.path.join(root, "dead", "d%02d" % n), dead)
        os.environ["CODEX_THREAD_ID"] = "mine"

    def list_json(self):
        from xsm import cli, probe
        asked = []
        out = io.StringIO()
        with mock.patch.object(probe, "git", side_effect=lambda folder, *a, **k: asked.append(folder)), \
                contextlib.redirect_stdout(out):
            code = cli.main(["list", "--dir", self.here, "--json"])
        self.assertEqual(code, 0)
        return {r["session_id"]: r for r in json.loads(out.getvalue())}, asked

    def test_git_is_asked_only_about_rows_that_can_still_be_live(self):
        """ORDER-1: 40 dead pointers in 40 folders cost no git call; the listing is the
        live peer, the caller, and the daemon-hosted thread whose recorded pid is dead."""
        rows, asked = self.list_json()
        self.assertEqual(sorted(rows), ["hosted", "mine", "peer"])
        self.assertEqual(rows["hosted"]["state"], "live")
        self.assertEqual(rows["mine"]["state"], "live")
        self.assertEqual(sorted(asked), sorted([self.here, self.far, self.other]))

    def test_what_is_never_dropped_before_the_project_check(self):
        """ORDER-1: no pid, a daemon-hosted Codex thread, and the caller's own pointer."""
        from xsm import cli
        me = {"ref": "r1"}
        gone = {"runtime": "claude", "pid": self.dead, "ref": "r2"}
        self.assertTrue(cli._provably_gone(gone, me))
        self.assertTrue(cli._provably_gone(dict(gone, runtime="codex", app_server=False), me))
        self.assertFalse(cli._provably_gone(dict(gone, pid=None), me))
        self.assertFalse(cli._provably_gone(dict(gone, runtime="codex", app_server=True), me))
        self.assertFalse(cli._provably_gone(dict(gone, ref="r1"), me))

    def test_all_and_clear_still_see_the_stopped_sessions(self):
        """ORDER-1: only the default listing skips them."""
        from xsm import cli
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["list", "-a", "--json"]), 0)
        names = {r["session_id"] for r in json.loads(out.getvalue())}
        self.assertEqual(len([n for n in names if n.startswith("dead-")]), self.DEAD)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["list", "clear", "-a"]), 0)
        self.assertIn("cleared %d stopped session(s)" % self.DEAD, out.getvalue())


class PruneUnknownTest(test_xsm.TempState):
    def test_a_pointer_past_the_window_goes_unless_it_is_live(self):
        """PRUNE-1: `unknown` (no pid) goes with `ended` and `stale`; an old live one stays."""
        from xsm import housekeeping, paths, registry
        old = time.time() - 30 * 86400
        child = subprocess.Popen(["true"])
        child.wait()
        base = {"runtime": "codex", "home": self.tmp, "updated": old, "app_server": False}
        for sid, extra in (("no-pid", {}), ("gone", {"pid": child.pid}),
                           ("running", {"pid": os.getpid()})):
            paths.write_json(registry._record_path("codex", sid),
                             dict(base, session_id=sid, name=sid, **extra))
        self.assertEqual(sorted(housekeeping.prune(dry_run=True)["sessions"]), ["gone", "no-pid"])
        housekeeping.prune()
        self.assertEqual([r["session_id"] for r in registry.raw_records()], ["running"])


class DoctorSessionsTest(test_xsm.TempState):
    """DOCTOR-1: the session lookups run once, under their own budget, and the report
    says what is stopped, how long pointers are kept and when the last prune finished."""

    def setUp(self):
        super().setUp()
        from xsm import paths, registry
        child = subprocess.Popen(["true"])
        child.wait()
        for sid, pid in (("running", os.getpid()), ("gone-1", child.pid), ("gone-2", child.pid)):
            paths.write_json(registry._record_path("codex", sid), {
                "runtime": "codex", "home": self.tmp, "session_id": sid, "pid": pid,
                "app_server": False, "name": sid, "cwd": self.tmp, "updated": time.time()})

    def doctor_output(self, *flags):
        from xsm import cli, housekeeping
        out = io.StringIO()
        with mock.patch.object(housekeeping, "maybe_prune"), contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["doctor"] + list(flags)), 0)
        return out.getvalue()

    def test_each_pointer_is_enriched_once(self):
        """DOCTOR-1: it was three times (stuck() once, the two counts)."""
        from xsm import install, registry
        with mock.patch.object(registry, "_enrich", wraps=registry._enrich) as enriched:
            report = install.doctor()
        self.assertEqual(enriched.call_count, 3)
        self.assertEqual((report["sessions"]["registered"], report["sessions"]["live"]), (3, 1))

    def test_the_lookups_run_inside_their_own_ten_second_budget(self):
        """DOCTOR-1: nobody opens a quick block around doctor, so it opens its own."""
        from xsm import install, probe, registry
        seen = []

        def records():
            seen.append((probe.limit(60), probe._deadline - time.monotonic()))
            return []

        with mock.patch.object(registry, "records", records), \
                mock.patch.object(registry, "unregistered", return_value=[]):
            install.doctor()
        ((each, budget),) = seen
        self.assertEqual(each, probe.QUICK_TIMEOUT)
        self.assertAlmostEqual(budget, 10, delta=1)
        self.assertEqual(probe.limit(60), 60, "and it ends with doctor's lookups")

    def test_the_report_counts_stopped_sessions_retention_and_the_last_prune(self):
        """DOCTOR-1: the sessions line keeps its old text as its prefix; the stamp's mtime
        is the last prune, and "never" when there is no stamp."""
        from xsm import cli, housekeeping, install, paths
        report = install.doctor()
        self.assertEqual(report["sessions"], {
            "registered": 3, "live": 1, "unregistered": 0, "stopped": 2,
            "retention_days": 7.0, "last_prune": None})
        self.assertEqual(dict(cli._doctor_rows(report))["sessions"],
                         "3 registered, 1 live, 0 unregistered; 2 stopped, pointers kept "
                         "7 days, last pruned never")
        stamp = paths.path(housekeeping.STAMP)
        housekeeping._touch(stamp)
        os.utime(stamp, (1_700_000_000, 1_700_000_000))
        report = install.doctor()
        self.assertEqual(report["sessions"]["last_prune"], 1_700_000_000)
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(1_700_000_000))
        text = self.doctor_output()
        self.assertIn("sessions   3 registered, 1 live, 0 unregistered; 2 stopped, pointers "
                      "kept 7 days, last pruned %s\n" % when, text)
        self.assertIn("| sessions | 3 registered, 1 live, 0 unregistered; 2 stopped, pointers "
                      "kept 7 days, last pruned %s |" % when, self.doctor_output("--table"))
        self.assertEqual(json.loads(self.doctor_output("--json"))["sessions"]["stopped"], 2)

    def test_a_probe_that_did_not_answer_has_a_probes_line_a_row_and_a_key(self):
        """OBS-1: named once in each form; no line, no row and an empty key otherwise."""
        from xsm import install, probe, registry
        quiet = self.doctor_output()
        self.assertNotIn("\nprobes ", quiet)
        self.assertNotIn("| probes |", self.doctor_output("--table"))
        self.assertEqual(json.loads(self.doctor_output("--json"))["probes"], {})
        with mock.patch.object(registry, "unregistered",
                               side_effect=lambda: probe.missed("lsof", "timeout") or []):
            report = install.doctor()
        self.assertEqual(report["probes"], {"lsof": 1})
        with mock.patch.object(install, "doctor", return_value=report):
            text, table, data = (self.doctor_output(), self.doctor_output("--table"),
                                 json.loads(self.doctor_output("--json")))
        line = [l for l in text.splitlines() if l.startswith("probes ")]
        self.assertEqual(len(line), 1, text)
        self.assertIn("lsof x1 did not answer", line[0])
        self.assertIn("| probes | lsof x1 did not answer", table)
        self.assertEqual(data["probes"], {"lsof": 1})


class SendResultLinesTest(unittest.TestCase):
    """OUT-1: the id of a message that went out is on its status line."""

    def lines(self, *args, **kwargs):
        from xsm import send
        return send.SendResult(*args, **kwargs).lines()

    def test_a_send_with_a_reason_ends_its_status_line_with_the_id(self):
        """OUT-1: the line still starts with `<status>: <reason>`."""
        for status, reason in (
                ("sent-unconfirmed", "queued; a Codex session picks the queue up within about 10 "
                                     "seconds when the thread is loaded and idle"),
                ("delivered", "receiver recorded it"),
                ("held", "the receiver's gate held it"),
                ("error", "timeout: queue stalled")):
            with self.subTest(status):
                self.assertEqual(self.lines(status, reason, "m1"),
                                 ["%s: %s (id m1)" % (status, reason)])

    def test_a_refusal_a_result_without_a_reason_and_one_without_an_id_are_unchanged(self):
        """OUT-1: a refusal says what to do and may name a kept message itself."""
        self.assertEqual(self.lines("refused", "out of scope: x", "m1"), ["refused: out of scope: x"])
        self.assertEqual(self.lines("held", "", "m1"), ["held: m1"])
        self.assertEqual(self.lines("sent-unconfirmed", "on peer"), ["sent-unconfirmed: on peer"])

    def test_notes_come_first_and_candidates_after_the_status_line(self):
        """OUT-1: nothing else about the lines changes."""
        from xsm import send
        result = send.SendResult("sent-unconfirmed", "queued", "m1", candidates=[
            {"name": "a", "alias": "h", "ref": "bbbbbb", "runtime": "codex", "state": "live",
             "cwd": "/q"}])
        result.notes = ["linked: x"]
        lines = result.lines()
        self.assertEqual(lines[:3], ["linked: x", "sent-unconfirmed: queued (id m1)", "candidates:"])
        self.assertEqual(len(lines), 4)


class Crowd(test_xsm.TempState):
    """Two live Codex threads in one folder and 350 pointers of sessions that ended
    elsewhere: their process is gone, so enriching one is cheap and every enrichment
    can be counted."""

    CROWD = 350

    def setUp(self):
        super().setUp()
        from xsm import registry
        self.home = os.path.join(self.tmp, "codex")
        self.here = os.path.join(self.tmp, "here")
        self.there = os.path.join(self.tmp, "there")
        os.makedirs(self.home)
        os.makedirs(self.here)
        # A real Codex server runs in the home of the session above it, and the
        # pointer it signs as carries that home. Without this the server's home
        # (the default) and the pointers' home differ, and a call is refused as
        # coming from another home (G01).
        os.environ["CODEX_HOME"] = self.home
        self.addCleanup(os.environ.pop, "CODEX_HOME", None)
        self.mine = registry.upsert("codex", self.home, "mine", os.getpid(), self.here, name="mine")
        self.peer = registry.upsert("codex", self.home, "peer", os.getpid(), self.here, name="peer")
        child = subprocess.Popen(["true"])
        child.wait()
        self.gone = child.pid
        for n in range(self.CROWD):
            self.stopped("elsewhere-%d" % n)
        os.environ["CODEX_THREAD_ID"] = "mine"
        self.addCleanup(os.environ.pop, "CODEX_THREAD_ID", None)

    def stopped(self, sid):
        """A pointer whose process is gone, named `sid`."""
        from xsm import identity, paths, registry
        paths.write_json(registry._record_path("codex", sid), dict(
            self.peer, session_id=sid, pid=self.gone, lstart=None, cwd=self.there, name=sid,
            ref=identity.ref_of("codex", self.home, sid), app_server=False))


class NameResolutionTest(Crowd):
    """NAME-1: a name looked up inside `quick` enriches each pointer once."""

    def lookup(self, name):
        """(the resolution, {session id: times it was enriched}) for `name` in one quick block."""
        from xsm import probe, registry, resolve
        with mock.patch.object(registry, "_enrich", wraps=registry._enrich) as enriched:
            with probe.quick():
                found = resolve.resolve(name)
        return found, collections.Counter(c.args[0]["session_id"] for c in enriched.call_args_list)

    def assert_once_each(self, counts):
        from xsm import registry
        self.assertEqual(len(counts), len(registry.raw_records()))
        self.assertEqual(set(counts.values()), {1}, counts.most_common(3))

    def test_a_name_that_matches_a_live_session(self):
        """NAME-1: it was twice (the known homes, then the pool)."""
        found, counts = self.lookup("peer")
        self.assertTrue(found.ok, found.reason)
        self.assertEqual(found.record["session_id"], "peer")
        self.assert_once_each(counts)

    def test_a_name_that_matches_only_a_stopped_session_keeps_its_answer(self):
        """NAME-1: stopped sessions stay in the pool, so `offline-only` and the resume
        hint do not change."""
        self.stopped("sleeper")
        found, counts = self.lookup("sleeper")
        self.assertEqual(found.status, "offline-only")
        self.assertIn("only stopped sessions match 'sleeper'", found.reason)
        self.assertIn("resume it with: CODEX_HOME=%s codex resume sleeper" % os.path.realpath(self.home),
                      found.reason)
        self.assert_once_each(counts)

    def test_a_name_that_matches_nothing_suggests_the_live_sessions(self):
        """NAME-1: it was three times, the last for the suggestions."""
        found, counts = self.lookup("nobody")
        self.assertEqual(found.status, "not-found")
        self.assertEqual(sorted(c["session_id"] for c in found.candidates), ["mine", "peer"])
        self.assert_once_each(counts)

    def test_nothing_is_kept_after_the_block(self):
        """NAME-1: the answers are reused inside one `quick` block and not beyond it."""
        from xsm import probe, registry, resolve
        with probe.quick():
            self.assertEqual(resolve.resolve("late").status, "not-found")
        registry.upsert("codex", self.home, "late-sid", os.getpid(), self.here, name="late")
        self.assertTrue(resolve.resolve("late").ok)


class McpCallerLookupTest(Crowd):
    """MCP-1: who is calling is found without enriching every pointer, inside one budget."""

    def call(self, name="xsm_inbox", args=None):
        """`Server.call` as the thread `mine`, whose process is this one."""
        from xsm import mcp
        server = mcp.Server(io.StringIO(), io.StringIO())
        server.call_thread = "mine"
        with mock.patch.object(mcp.identity, "ancestor_pid", return_value=os.getpid()):
            return server.call(name, args or {})

    def test_a_tool_call_enriches_only_the_pointers_of_the_callers_pid(self):
        """MCP-1: 350 other pointers cost the call nothing."""
        from xsm import mcp, registry
        self.assertEqual(len(registry.raw_records()), self.CROWD + 2)
        with mock.patch.object(mcp.Server, "_call", return_value='{"messages":[],"claims":[]}'), \
                mock.patch.object(registry, "_enrich", wraps=registry._enrich) as enriched:
            self.assertEqual(json.loads(self.call())["messages"], [])
        self.assertEqual(sorted(c.args[0]["session_id"] for c in enriched.call_args_list),
                         ["mine", "peer"])

    def test_the_lookup_has_the_quick_budget_and_the_channel_lookup_does_not(self):
        """MCP-1: the walk, the pointers and the tool run in turn, but the git lookup that
        decides the channel is not under a budget the lookup may have spent."""
        from xsm import channel, identity, mcp, probe, registry
        seen = []

        def watch(label, real):
            def inner(*args, **kwargs):
                seen.append((label, probe._quick))
                return real(*args, **kwargs)
            return inner

        server = mcp.Server(io.StringIO(), io.StringIO())
        server.call_thread = "mine"
        with mock.patch.object(identity, "ancestor_pid", watch("walk", lambda names: os.getpid())), \
                mock.patch.object(registry, "raw_records", watch("pointers", registry.raw_records)), \
                mock.patch.object(channel, "resolve", watch("channel", channel.resolve)), \
                mock.patch.object(mcp.Server, "_call", watch("tool", lambda *a, **k: '{"messages":[],"claims":[]}')):
            server.call("xsm_inbox", {})
        self.assertEqual([label for label, _ in seen], ["walk", "pointers", "channel", "tool"])
        for label, quick in seen[:2]:
            self.assertEqual(quick, probe.QUICK_TIMEOUT, label)
        for label, quick in seen[2:]:
            self.assertIsNone(quick, label)

    def test_send_to_a_registered_ref_does_not_look_for_open_threads_and_prints_the_id(self):
        """MCP-1, OUT-1: `xsm_send` to a ref the registry holds needs no discovery, and its
        result line carries the id."""
        from xsm import adapters, ledger, registry
        with mock.patch.object(registry, "adopt_open_codex") as adopt, \
                mock.patch.object(adapters, "to_codex", return_value="queued"):
            text = self.call("xsm_send", {"target": "ref:" + self.peer["ref"], "text": "hello",
                                          "wait": 0})
        adopt.assert_not_called()
        (entry,) = ledger.recent(5)
        first = text.splitlines()[0]
        self.assertTrue(first.startswith("sent-unconfirmed: queued"), text)
        self.assertTrue(first.endswith(" (id %s)" % entry["id"]), text)


class SendBudgetTest(Crowd):
    """SEND-1, OUT-1, OUT-2: what a send does after it found its target."""

    def send(self, spec, **kwargs):
        from xsm import registry, send
        return send.send(spec, "hello", sender=registry.by_session("codex", "mine"), **kwargs)

    def test_scope_and_delivery_never_run_under_the_discovery_budget(self):
        """SEND-1: a spent budget must not turn into an `out of scope` refusal, and the wait
        and the delivery have their own deadlines. resolve is the control: it is in the block."""
        from xsm import adapters, config, ledger, probe, resolve
        seen = {}

        def watch(label, real):
            def inner(*args, **kwargs):
                seen.setdefault(label, []).append(probe._quick)
                return real(*args, **kwargs)
            return inner

        with mock.patch.object(resolve, "resolve", watch("resolve", resolve.resolve)), \
                mock.patch.object(config, "scope_for", watch("scope", config.scope_for)), \
                mock.patch.object(adapters, "to_codex", watch("delivery", lambda *a, **k: "queued")), \
                mock.patch.object(ledger, "wait_for",
                                  watch("wait", lambda *a, **k: {"status": "queued"})):
            result = self.send("ref:" + self.peer["ref"], wait=5)
        self.assertEqual(result.status, "sent-unconfirmed", result.reason)
        self.assertEqual(seen["resolve"], [probe.QUICK_TIMEOUT])
        self.assertEqual({k: v for k, v in seen.items() if k != "resolve"},
                         {"scope": [None], "delivery": [None], "wait": [None]})

    def test_the_cli_prints_the_id_of_a_send_that_went_out(self):
        """OUT-1: the line `--resend <id>` needs the id from."""
        from xsm import adapters, cli, ledger
        out = io.StringIO()
        with mock.patch.object(adapters, "to_codex", return_value="queued"), \
                contextlib.redirect_stdout(out):
            code = cli.main(["send", "ref:" + self.peer["ref"], "--text", "hello", "--wait", "0"])
        self.assertEqual(code, 3, out.getvalue())
        (entry,) = ledger.recent(5)
        (line,) = out.getvalue().splitlines()
        self.assertTrue(line.startswith("sent-unconfirmed: queued; a Codex session picks"), line)
        self.assertTrue(line.endswith(" (id %s)" % entry["id"]), line)

    def test_a_claude_target_without_a_socket_is_refused_and_its_ledger_row_says_so(self):
        """OUT-2: the row was written `queued` before the socket was looked for, and stayed so
        for ever; doctor reported it as a message nobody had received."""
        from xsm import identity, ledger, registry
        claude_home = os.path.join(self.tmp, "claude")
        os.makedirs(os.path.join(claude_home, "sessions"))
        target = registry.upsert("claude", claude_home, "claude-sid", os.getpid(), self.here,
                                 name="no-socket")
        # A budget that could not ask reads as `live` (socket_blocked); with no socket named
        # the session would be stale, and refused before the ledger was touched.
        with mock.patch.object(identity, "socket_live", return_value=None):
            result = self.send("ref:" + target["ref"])
        self.assertEqual(result.status, "refused")
        self.assertEqual(result.reason, "target has no inbox socket")
        self.assertEqual(result.lines(), ["refused: target has no inbox socket"])
        state = ledger.status(result.msg_id)
        self.assertEqual(state["status"], "error")
        self.assertTrue(state["error"].startswith("no-inbox"), state)


if __name__ == "__main__":
    unittest.main()
