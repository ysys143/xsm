"""Issue #17/#18: unrelated sessions and stalled discovery cannot hold a lookup."""
import contextlib
import io
import json
import os
import sqlite3
import subprocess
import unittest
from unittest import mock

from tests import test_xsm


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
            commands.append(argv)
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
        self.assertEqual(commands[1], ["lsof", "-a", "-p", "101,102", "-d", "cwd", "-Fpn"])


if __name__ == "__main__":
    unittest.main()
