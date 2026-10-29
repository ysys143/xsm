"""Owned workers must not persist a rejected directory registration."""
import os
from unittest import mock
from tests.test_xsm import TempState


class WorkerDirectoryRegistrationTest(TempState):
    def worker(self, folder):
        home = os.path.join(self.tmp, "codex")
        os.makedirs(home, exist_ok=True)
        return {"name": "worker", "home": home, "pid": os.getpid(), "cwd": folder, "created": 10}

    def register(self, worker):
        from xsm import registry, workers
        with mock.patch.object(registry, "_codex_recent_threads", return_value=[
                ("worker-thread", "worker", worker["cwd"], "native.jsonl", 10, 10)]):
            workers._register_named_thread(worker)

    def test_excluded_worker_keeps_native_id_without_an_addressable_pointer(self):
        from xsm import config, paths, registry
        private = os.path.join(self.tmp, "private");os.mkdir(private)
        paths.write_json(paths.path(config.CONFIG), {"directory_excluded_paths": [private]})
        worker = self.worker(private)
        self.register(worker)
        self.assertEqual(worker["session_id"], "worker-thread")
        self.assertFalse(os.path.exists(registry._record_path("codex", "worker-thread")))
        self.assertIsNone(registry.by_session("codex", "worker-thread"))

    def test_unexcluded_worker_still_gets_its_exact_registered_thread(self):
        from xsm import registry
        worker = self.worker(self.tmp)
        self.register(worker)
        registered = registry.by_session("codex", "worker-thread")
        self.assertTrue(registered["ref"])
        self.assertEqual(registered["session_id"], worker["session_id"])

    def test_any_rejected_upsert_cannot_be_rewritten_as_adopted(self):
        from xsm import registry
        worker = self.worker(self.tmp)
        with mock.patch.object(registry, "upsert", return_value={"registered": False}):
            self.register(worker)
        self.assertFalse(os.path.exists(registry._record_path("codex", "worker-thread")))
