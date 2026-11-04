"""Worker entry paths use real task records, with process/transport boundaries faked."""
import concurrent.futures
import contextlib
import io
import os
import time
from types import SimpleNamespace
from unittest import mock

from tests.test_xsm import TempState


class AttemptPathTest(TempState):
    TEXT = "Implement the same task"

    def setUp(self):
        super().setUp()
        from xsm import registry, workers
        self.parent = {"ref": "parent", "runtime": "claude", "cwd": self.tmp}
        for patch in (mock.patch.object(registry, "me", return_value=self.parent),
                      mock.patch.object(workers, "refuse_inside_framework")):
            patch.start()
            self.addCleanup(patch.stop)

    def worker(self, name, task):
        from xsm import attempts, workers
        record = {"name": name, "runtime": "claude", "mode": "background",
                  "ref": name, "parent_ref": "parent", "cwd": self.tmp,
                  "created": time.time(), "pending_task": task,
                  "attempt_key": attempts.key_for(task["text"], self.tmp)}
        workers.save(record)
        return record

    def spawn_boundary(self, runtime, **args):
        return self.worker(args["name"], args["task"])

    def transport(self, target, text, **args):
        from xsm import attempts, workers
        worker = workers.load(target.removeprefix("ref:"))
        rows = attempts.read(worker["attempt_key"]).get("tries", [])
        self.assertTrue(any(r.get("task_id") == args["msg_id"] for r in rows),
                        "the actual entry path must record the attempt before sending")
        return SimpleNamespace(status="sent-unconfirmed", reason=None, msg_id=args["msg_id"])

    def test_immediate_cli_failures_are_counted_and_block_the_next_attempt(self):
        from xsm import attempts, cli, send, workers
        key = attempts.key_for(self.TEXT, self.tmp)
        with mock.patch.object(workers, "spawn", side_effect=self.spawn_boundary), \
                mock.patch.object(send, "send", side_effect=self.transport):
            for i in range(3):
                name = "immediate-%d" % i
                args = cli.build_parser().parse_args(["spawn", "claude", "--name", name,
                                                      "--task", self.TEXT])
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(cli.cmd_spawn(args), 0)
                worker = workers.load(name)
                workers.on_reply(name, worker["task_id"], self.parent, "failed")
                workers.stop(name, user_requested=True)
        self.assertEqual(attempts.failures(key), 3)
        with mock.patch.object(workers, "_check_installed"), \
                mock.patch.object(workers, "check_concurrency"):
            with self.assertRaisesRegex(workers.WorkerError, "task-attempts-exhausted"):
                workers.spawn("claude", name="fourth", cwd=self.tmp, caller=self.parent,
                              task={"id": "fourth-task", "text": self.TEXT})
        self.assertIsNone(workers.load("fourth"))

    def test_trust_delayed_path_also_records_before_sending(self):
        from xsm import attempts, paths, registry, send, workers
        worker = self.worker("delayed", {"id": "delayed-task", "text": self.TEXT})
        worker["waiting"] = "trust-request"
        workers.save(worker)
        paths.write_json(workers._approval_path("trust-request"), {"status": "approved"})
        with mock.patch.object(workers, "_press"), \
                mock.patch.object(workers, "_wait_for_registration"), \
                mock.patch.object(registry, "records", return_value=[self.parent]), \
                mock.patch.object(send, "send", side_effect=self.transport):
            self.assertEqual(workers.finish("delayed"), 0)
        self.assertEqual(len(attempts.read(worker["attempt_key"])["tries"]), 1)
        self.assertNotIn("pending_task", workers.load("delayed"))

    def test_stopping_a_trust_waiter_does_not_close_another_workers_attempt(self):
        from xsm import attempts, cli, workers
        active = self.worker("active", {"id": "active-task", "text": self.TEXT})
        key = active["attempt_key"]
        attempts.start(key, self.TEXT, self.tmp, "active", "active-task")
        active["task_id"] = "active-task"
        active.pop("pending_task")
        workers.save(active)
        waiting = self.worker("waiting", {"id": "waiting-task", "text": self.TEXT})
        waiting["waiting"] = "trust-request"
        workers.save(waiting)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.cmd_stop(cli.build_parser().parse_args(["stop", "waiting"])), 0)
        self.assertNotIn("ended_t", attempts.read(key)["tries"][0])
        workers.on_reply("active", "active-task", self.parent, "failed")
        self.assertEqual(attempts.failures(key), 1)

    def test_an_explicit_task_id_never_closes_an_unidentified_attempt(self):
        from xsm import attempts
        key = attempts.key_for(self.TEXT, self.tmp)
        attempts.start(key, self.TEXT, self.tmp, "legacy", None)
        attempts.finish(key, "failed", task_id="another-task")
        self.assertNotIn("ended_t", attempts.read(key)["tries"][0])


class AttemptHistoryTest(TempState):
    def test_prune_dry_run_preserves_a_legacy_record_without_creating_a_lock(self):
        from pathlib import Path
        from xsm import attempts, paths
        key = attempts.key_for("legacy", self.tmp)
        filename = Path(attempts._path(key))
        paths.write_json(str(filename), {"key": key, "tries": [{"t": 1}]})
        before = filename.read_bytes()
        self.assertEqual(attempts.prune(2, dry_run=True), [key])
        self.assertEqual(filename.read_bytes(), before)
        self.assertFalse(Path(str(filename) + ".lock").exists())

    def test_interrupted_history_does_not_erase_failures_and_success_still_resets(self):
        from xsm import attempts
        key = attempts.key_for("task", self.tmp)
        for i in range(2):
            attempts.start(key, "task", self.tmp, "failed", "failure-%d" % i)
            attempts.finish(key, "failed", task_id="failure-%d" % i)
        for i in range(25):
            task = "stop-%d" % i
            attempts.start(key, "task", self.tmp, "stopped", task)
            attempts.finish(key, None, "user stopped", task_id=task)
        self.assertEqual(attempts.failures(key), 2)
        self.assertLessEqual(len(attempts.read(key)["tries"]), attempts.KEEP)
        attempts.start(key, "task", self.tmp, "third", "third-failure")
        attempts.finish(key, "failed", task_id="third-failure")
        with self.assertRaises(attempts.AttemptsError):
            attempts.check(key, 3)
        attempts.start(key, "task", self.tmp, "success", "success")
        attempts.finish(key, "succeeded", task_id="success")
        for i in range(25):
            task = "after-success-%d" % i
            attempts.start(key, "task", self.tmp, "stopped", task)
            attempts.finish(key, None, task_id=task)
        self.assertEqual(attempts.failures(key), 0)
        attempts.check(key, 3)
        attempts.clear(key)
        self.assertFalse(attempts.read(key))

    def test_old_running_attempt_stays_finishable_until_it_is_closed(self):
        from xsm import attempts
        key = attempts.key_for("task", self.tmp)
        attempts.start(key, "task", self.tmp, "active", "active")
        for i in range(25):
            task = "stopped-%d" % i
            attempts.start(key, "task", self.tmp, "stopped", task)
            attempts.finish(key, None, task_id=task)
        self.assertTrue(any(t["task_id"] == "active" for t in attempts.read(key)["tries"]))
        attempts.finish(key, "failed", task_id="active")
        self.assertEqual(attempts.failures(key), 1)
        self.assertLessEqual(len(attempts.read(key)["tries"]), attempts.KEEP)

    def test_concurrent_attempts_keep_their_exact_records(self):
        from xsm import attempts
        key = attempts.key_for("task", self.tmp)
        def work(i):
            task = "concurrent-%d" % i
            attempts.start(key, "task", self.tmp, task, task)
            attempts.finish(key, "failed", task_id=task)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(work, range(12)))
        self.assertEqual(attempts.failures(key), 12)
        self.assertEqual(len(attempts.read(key)["tries"]), 12)
