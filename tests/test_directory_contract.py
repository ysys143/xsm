"""P05 preparation against existing APIs; not evidence that G05 passed.

Only OS liveness observations are mocked. Registry/native files are real and
isolated. Exclusion enforcement is unimplemented, not a guessed config/API.
"""
import os
import tempfile
import unittest
from unittest import mock

from xsm import config, identity, paths, registry, resolve


class DirectoryContractTest(unittest.TestCase):
    def setUp(self):
        # TempState tests unload xsm modules. Refresh these references before
        # patching HOME so dynamically imported directory uses the same state.
        global config, identity, paths, registry, resolve
        from xsm import config, identity, paths, registry, resolve

        tmp = tempfile.TemporaryDirectory(prefix="xsm-directory-")
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.home = os.path.join(self.root, "claude")
        os.makedirs(self.home)
        for target, value in (("HOME", os.path.join(self.root, "state")),):
            patch = mock.patch.object(paths, target, value)
            patch.start()
            self.addCleanup(patch.stop)
        paths.ensure_home()
        for target, value in (("lstart", "start-A"), ("pid_alive", True),
                              ("socket_live", True), ("is_app_server", False)):
            patch = mock.patch.object(identity, target, return_value=value)
            patch.start()
            self.addCleanup(patch.stop)
        # No real process scans when a name is absent.
        patch = mock.patch.object(registry, "unregistered", return_value=[])
        patch.start()
        self.addCleanup(patch.stop)

    def register(self, sid="old", pid=41001, runtime="claude", **kwargs):
        return registry.upsert(runtime, self.home, sid, pid, self.root, **kwargs)

    def native(self, sid="old", pid=41001, name="review"):
        paths.write_json(os.path.join(self.home, "sessions", "%s.json" % pid),
                         {"sessionId": sid, "name": name, "nameSource": "user",
                          "messagingSocketPath": "/tmp/%s.sock" % pid})

    def test_resume_same_conversation_new_pid_revives_pointer_not_reach(self):
        first = self.register(socket="/tmp/41001.sock")
        registry.mark_ended("claude", "old", "worker-stopped", home=self.home)
        stored = registry.raw_records()[0]
        stored.update(adopted=True, unprompted=True)
        paths.write_json(registry._record_path("claude", "old"), stored)
        with mock.patch.object(identity, "lstart", return_value="start-B"):
            resumed = self.register(pid=41002)
        self.native(pid=41002)
        self.assertEqual(resumed["ref"], first["ref"])
        self.assertEqual(len(registry.raw_records()), 1)
        for key in ("ended_at", "end_reason", "adopted", "unprompted", "socket"):
            self.assertNotIn(key, resumed)
        self.assertTrue(config.reach_holds(first, first))
        self.assertFalse(config.reach_holds(first, resumed))
        with mock.patch.object(identity, "lstart", return_value="start-B"):
            self.assertEqual(registry.by_session("claude", "old")["state"], "live")

    def test_claude_new_on_same_pid_supersedes_only_old_conversation(self):
        old = self.register()
        new = self.register("new")
        self.native("new")
        rows = {r["session_id"]: r for r in registry.records()}
        self.assertEqual((rows["old"]["state"], rows["old"]["end_reason"]),
                         ("ended", "superseded"))
        self.assertEqual(rows["new"]["state"], "live")
        self.assertNotEqual(old["ref"], new["ref"])
        self.assertFalse(config.reach_holds(old, new))

    def test_native_rename_changes_lookup_without_changing_pointer_identity(self):
        first = self.register(name="cached-title")
        self.native(name="before")
        self.assertEqual(resolve.resolve("before").record["ref"], first["ref"])
        self.native(name="after")
        self.assertFalse(resolve.resolve("before").ok)
        renamed = resolve.resolve("after").record
        self.assertEqual((renamed["ref"], renamed["session_id"], renamed["name_source"]),
                         (first["ref"], "old", "user"))
        self.assertEqual(registry.raw_records()[0]["name"], "cached-title")

    def test_pid_reuse_is_stale_or_ended_even_with_answering_socket(self):
        rec = self.register()
        with mock.patch.object(identity, "lstart", return_value="different-process"):
            self.assertEqual(identity.state_reason(rec), ("stale", "lstart_changed"))
            ended = dict(rec, ended_at=1)
            self.assertEqual(identity.state_reason(ended), ("ended", "lstart_changed"))
            self.assertFalse(config.reach_holds(rec, dict(rec, lstart="different-process")))

    def test_unavailable_start_probe_is_not_evidence_of_pid_reuse(self):
        rec = self.register(runtime="codex")
        with mock.patch.object(identity, "lstart", return_value=None):
            self.assertEqual(identity.state_reason(rec), ("live", "live_unverified"))

    def test_codex_new_thread_detects_dead_or_reused_mcp_beacon(self):
        old = self.register(runtime="codex", mcp_pid=42001)
        new = self.register("new", runtime="codex", mcp_pid=42002)
        for reused in (False, True):
            with self.subTest(reused=reused), \
                    mock.patch.object(identity, "pid_alive", side_effect=lambda p: reused or p != 42001), \
                    mock.patch.object(identity, "lstart", side_effect=lambda p: "start-B" if p == 42001 else "start-A"):
                self.assertEqual(identity.state_reason(old), ("ended", "thread_replaced"))
                self.assertEqual(identity.state_of(new), "live")
                row = registry.by_session("codex", "old")
                self.assertEqual(row["end_reason"], "thread_replaced")

    def test_codex_without_beacon_cannot_detect_new_thread_from_pid_alone(self):
        old = self.register(runtime="codex")
        self.register("new", runtime="codex")
        self.assertEqual(identity.state_reason(old), ("live", "live"))

    def test_shared_daemon_uses_loaded_threads_instead_of_other_threads_beacon(self):
        from xsm import codex_daemon
        old = self.register(runtime="codex", mcp_pid=42001)
        old["app_server"] = True
        with mock.patch.object(codex_daemon, "loaded_threads", return_value={"old"}), \
                mock.patch.object(identity, "pid_alive", return_value=False):
            self.assertEqual(identity.state_reason(old), ("live", "thread_loaded"))
        with mock.patch.object(codex_daemon, "loaded_threads", return_value={"new"}):
            self.assertEqual(identity.state_reason(old), ("ended", "thread_unloaded"))

    def test_same_name_is_ambiguous_and_exact_handle_still_selects_conversation(self):
        old = self.register()
        self.register("new", pid=41002)
        self.native()
        self.native("new", 41002)
        answer = resolve.resolve("review")
        self.assertEqual(answer.status, "ambiguous")
        self.assertEqual({r["session_id"] for r in answer.candidates}, {"old", "new"})
        self.assertEqual(resolve.resolve("ref:" + old["ref"]).record["session_id"], "old")

    def test_ref_collision_refuses_selection_but_native_id_remains_exact(self):
        with mock.patch.object(identity, "ref_of", return_value="abcdef"):
            self.register()
            self.register("new", pid=41002)
        self.native()
        self.native("new", 41002)
        answer = resolve.resolve("ref:abcdef")
        self.assertEqual(answer.status, "ambiguous")
        self.assertEqual(len(answer.candidates), 2)
        self.assertEqual(resolve.resolve("claude:old").record["session_id"], "old")

    def test_goodbye_from_another_home_does_not_end_current_pointer(self):
        first = self.register()
        self.assertIsNone(registry.mark_ended("claude", "old", "exit", home=self.root))
        self.assertEqual(registry.raw_records(), [first])

    def test_exclusion_path_inputs_canonicalize_symlink_and_missing_descendant(self):
        """Existing normalization only; does NOT assert exclusion enforcement."""
        actual = os.path.join(self.root, "private")
        alias = os.path.join(self.root, "alias")
        os.mkdir(actual)
        os.symlink(actual, alias)
        for suffix in ("", "missing/child"):
            with self.subTest(suffix=suffix):
                cwd = os.path.join(alias, suffix)
                row = registry.upsert("claude", self.home, "old", 41001, cwd)
                expected = os.path.realpath(os.path.join(actual, suffix))
                self.assertEqual(row["cwd"], expected)
                self.assertEqual(registry.by_session("claude", "old")["cwd"], expected)
        self.assertEqual(identity.ref_of("claude", alias, "old"),
                         identity.ref_of("claude", actual, "old"))

    def test_exclusion_enforcement_across_registration_listing_and_attachments(self):
        """Registry enforcement and shared attachment policy, not attachment IO.

        The coordinator integrates attachment readers; this tests their shared
        path predicate rather than claiming that product integration happened.
        """
        from xsm import directory
        private = os.path.join(self.root, "private")
        allowed = os.path.join(self.root, "private-sibling")
        alias = os.path.join(self.root, "alias")
        os.mkdir(private)
        os.mkdir(allowed)
        os.symlink(private, alias)
        registry.upsert("claude", self.home, "private-old", 41001, private)
        public = registry.upsert("claude", self.home, "allowed", 41002, allowed)
        self.native("allowed", 41002)
        paths.write_json(paths.path(config.CONFIG), {directory.EXCLUSIONS_KEY: [private]})
        for path in (private, alias, os.path.join(alias, "missing", "child")):
            with self.subTest(path=path):
                self.assertTrue(directory.excluded(path))
                rejected = registry.upsert("claude", self.home, "private-new", 41003, path)
                self.assertTrue(rejected["excluded"])
                self.assertFalse(rejected["registered"])
                self.assertFalse(os.path.exists(registry._record_path("claude", "private-new")))
                self.assertTrue(directory.excluded(os.path.join(path, "attachment.txt")))
        self.assertFalse(directory.excluded(os.path.join(allowed, "attachment.txt")))
        self.assertEqual([r["session_id"] for r in registry.records()], ["allowed"])
        # Privacy filtering doesn't silently add a registration prerequisite to
        # the preexisting same-directory communication rule.
        peer = dict(public, session_id="unregistered-peer", registered=False)
        self.assertIsNotNone(config.scope_for(public, peer)[0])


if __name__ == "__main__":
    unittest.main()
