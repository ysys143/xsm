"""Real Git common dirs, registry files and native metadata; private temp state only."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import socket
import stat
import subprocess
import tempfile
import threading
import time
import unittest
from contextlib import closing
from unittest import mock

from xsm import config, directory, identity, network_directory as net, paths, probe, registry

LOCAL = "a" * 64
PEER = "b" * 64
OTHER = "c" * 64
REPOSITORY = "verified-repository-01"


class NetworkDirectoryTest(unittest.TestCase):
    def setUp(self):
        global config, directory, identity, net, paths, probe, registry
        from xsm import config, directory, identity, network_directory as net, paths, probe, registry
        self.temporary = tempfile.TemporaryDirectory(prefix="xsm-network-directory-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(os.path.realpath(self.temporary.name))
        patch = mock.patch.object(paths, "HOME", str(self.root / "state"))
        patch.start()
        self.addCleanup(patch.stop)
        paths.ensure_home()
        self.home = self.root / "codex"
        self.home.mkdir()
        config.add_home(str(self.home), "codex")
        self.repo = self.root / "checkout"
        self.repo.mkdir()
        self.git(self.repo, "init", "-q", "-b", "main")
        self.maps = net.RepositoryMap(self.root / "maps")
        self.start = identity.lstart(os.getpid()) or "fixture-start"
        self._database(self.home)

    def git(self, cwd, *args):
        proc = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=5)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.strip()

    def _database(self, home):
        with closing(sqlite3.connect(home / "state_5.sqlite")) as db, db:
            db.execute("create table threads (id text primary key, name text, rollout_path text)")

    def row(self, sid="session-one", **fields):
        value = {"runtime": "codex", "session_id": sid, "home": str(self.home), "cwd": str(self.repo),
                 "pid": os.getpid(), "lstart": self.start, "app_server": False,
                 "ref": "ref-" + sid, "name": "Cached title", "updated": time.time()}
        value.update(fields)
        return value

    def store(self, *rows):
        for row in rows:
            key = hashlib.sha256(json.dumps([row["runtime"], row["home"], row["session_id"]]).encode()).hexdigest()
            paths.write_json(paths.path(paths.SESSIONS, key + ".json"), row)

    def native(self, row, title="Current title", doing="Implement verified discovery"):
        home = Path(row["home"])
        rollout = home / (row["session_id"] + ".jsonl")
        stamp = time.time()
        lines = [
            {"type": "session_meta", "timestamp": stamp, "payload": {"id": row["session_id"]}},
            {"type": "response_item", "timestamp": stamp, "payload": {"type": "function_call", "name": "update_plan",
                "arguments": json.dumps({"plan": [{"step": doing, "status": "in_progress"}]})}},
            {"type": "event_msg", "timestamp": stamp, "payload": {"type": "task_started"}},
            {"type": "response_item", "payload": {"type": "message", "content": "PRIVATE RAW TRANSCRIPT"}},
        ]
        rollout.write_text("".join(json.dumps(line) + "\n" for line in lines))
        with closing(sqlite3.connect(home / "state_5.sqlite")) as db, db:
            db.execute("insert or replace into threads values (?, ?, ?)", (row["session_id"], title, str(rollout)))
        return rollout

    def publish(self, row):
        return directory.publish(row, user_source="explicit local operator publication")

    def candidates(self, repository=REPOSITORY, **filters):
        return net.local_candidates(PEER, repository, self.maps, LOCAL, **filters)

    def test_public_key_exact_real_home_and_opaque_generation(self):
        row = self.row()
        alias = self.root / "home-alias"
        alias.symlink_to(self.home, target_is_directory=True)
        endpoint = net.public_endpoint(row, LOCAL)
        self.assertEqual(set(endpoint), {"machine", "runtime", "home_id", "session_id", "generation"})
        self.assertEqual(endpoint["home_id"], hashlib.sha256(os.path.realpath(self.home).encode()).hexdigest())
        self.assertEqual(net.public_endpoint(dict(row, home=str(alias)), LOCAL), endpoint)
        self.assertEqual(net.public_endpoint(dict(row, name="renamed", updated=1), LOCAL), endpoint)
        for field, value in (("pid", row["pid"] + 1), ("lstart", "new-process"), ("mcp_pid", 123)):
            self.assertNotEqual(net.public_endpoint(dict(row, **{field: value}), LOCAL)["generation"], endpoint["generation"])
        for machine in ("display name", "100.64.0.1", "https://relay.invalid", None):
            self.assertIsNone(net.public_endpoint(row, machine))
        self.assertIsNone(net.public_endpoint(dict(row, registered=False), LOCAL))
        self.assertIsNone(net.public_endpoint(dict(row, lstart=None), LOCAL))
        self.assertNotIn(str(self.home), json.dumps(endpoint))

    def test_map_is_explicit_peer_scoped_private_and_persistent(self):
        self.assertIsNone(self.maps.for_local(self.repo))
        self.maps.bind(self.repo, REPOSITORY, [PEER])
        reopened = net.RepositoryMap(self.maps.root)
        self.assertEqual(reopened.for_local(self.repo), REPOSITORY)
        self.assertEqual(reopened.for_local(self.repo, PEER), REPOSITORY)
        self.assertIsNone(reopened.for_local(self.repo, OTHER))
        self.assertTrue(reopened.allows(PEER, REPOSITORY, self.repo))
        self.assertFalse(reopened.allows(PEER, "other-repository", self.repo))
        self.assertFalse(reopened.allows("display-name", REPOSITORY, self.repo))
        self.assertEqual(stat.S_IMODE(self.maps.root.stat().st_mode), 0o700)
        for name in ("repositories.json", "repositories.lock"):
            self.assertEqual(stat.S_IMODE((self.maps.root / name).stat().st_mode), 0o600)

    def test_worktree_subdirectory_symlink_share_actual_git_common(self):
        worktree = self.root / "topic"
        self.git(self.repo, "worktree", "add", "--orphan", "-b", "topic", str(worktree))
        child = worktree / "subdir"
        child.mkdir()
        alias = self.root / "repo-alias"
        alias.symlink_to(self.repo, target_is_directory=True)
        self.maps.bind(alias, REPOSITORY, [PEER])
        self.assertEqual(self.maps.for_local(child, PEER), REPOSITORY)
        self.assertEqual(self.maps.for_local(alias, PEER), REPOSITORY)

    def test_same_name_and_remote_url_are_never_repository_identity(self):
        other = self.root / "another-parent" / self.repo.name
        other.mkdir(parents=True)
        self.git(other, "init", "-q", "-b", "main")
        for path in (self.repo, other):
            self.git(path, "remote", "add", "origin", "https://example.invalid/shared/repository.git")
        self.maps.bind(self.repo, REPOSITORY, [PEER])
        self.assertIsNone(self.maps.for_local(other, PEER))
        self.assertFalse(self.maps.allows(PEER, REPOSITORY, other))
        self.maps.bind(other, REPOSITORY, [PEER])
        self.assertEqual(self.maps.for_local(other, PEER), REPOSITORY)

    def test_replaced_git_directory_does_not_inherit_verified_mapping(self):
        self.maps.bind(self.repo, REPOSITORY, [PEER])
        (self.repo / ".git").rename(self.root / "old-git")
        self.git(self.repo, "init", "-q", "-b", "main")
        self.assertIsNone(self.maps.for_local(self.repo, PEER))

    def test_bad_map_fails_closed_and_bind_does_not_repair_it(self):
        self.maps.bind(self.repo, REPOSITORY, [PEER])
        for data in (b"{", b'{"version":1,"version":1,"repositories":[]}',
                     b'{"version":1,"repositories":[{}]}', b"x" * (net.MAX_MAP_BYTES + 1)):
            self.maps.path.write_bytes(data)
            self.assertIsNone(self.maps.for_local(self.repo, PEER))
            self.assertFalse(self.maps.allows(PEER, REPOSITORY, self.repo))
            with self.assertRaises(ValueError):
                self.maps.bind(self.repo, REPOSITORY, [PEER])
            self.assertEqual(self.maps.path.read_bytes(), data)

    def test_map_symlink_permissions_fifo_and_busy_lock_fail_closed(self):
        self.maps.bind(self.repo, REPOSITORY, [PEER])
        self.maps.path.chmod(0o644)
        self.assertIsNone(self.maps.for_local(self.repo, PEER))
        self.maps.path.chmod(0o600)
        saved = self.maps.root / "saved.json"
        self.maps.path.rename(saved)
        self.maps.path.symlink_to(saved)
        self.assertIsNone(self.maps.for_local(self.repo, PEER))
        self.maps.path.unlink()
        os.mkfifo(self.maps.path, 0o600)
        self.assertIsNone(self.maps.for_local(self.repo, PEER))
        self.maps.path.unlink()
        saved.rename(self.maps.path)
        with self.maps._locked(writing=True):
            start = time.monotonic()
            self.assertIsNone(self.maps.for_local(self.repo, PEER))
            self.assertLess(time.monotonic() - start, 0.5)
        self.maps.root.chmod(0o755)
        self.assertIsNone(self.maps.for_local(self.repo, PEER))

    def test_map_concurrent_updates_and_failed_atomic_replace_preserve_old_data(self):
        other = self.root / "second"
        other.mkdir()
        self.git(other, "init", "-q")
        # Bind canonicalization is read-only; run writers together after resolution.
        self.maps.bind(self.repo, REPOSITORY, [PEER])
        expected = {str(self.repo): REPOSITORY, str(other): "second-id"}
        errors = []
        def write(path):
            try:
                self.maps.bind(path, expected[str(path)], [PEER])
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=write, args=(path,)) for path in (self.repo, other)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(5)
        self.assertFalse(errors)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(self.maps.for_local(other), "second-id")
        self.assertEqual(self.maps.for_local(self.repo), REPOSITORY)
        before = self.maps.path.read_bytes()
        with mock.patch.object(net.os, "replace", side_effect=OSError("injected")):
            with self.assertRaises(OSError): self.maps.bind(self.repo, "changed", [PEER])
        self.assertEqual(self.maps.path.read_bytes(), before)

    def test_published_or_verified_repository_union_uses_real_metadata(self):
        same = self.row("same")
        outside = self.root / "outside"
        outside.mkdir()
        published = self.row("published", cwd=str(outside))
        both = self.row("both")
        self.store(same, published, both)
        for row in (same, published, both): self.native(row)
        for row in (published, both): self.publish(row)
        self.maps.bind(self.repo, REPOSITORY, [PEER])
        rows = self.candidates()
        self.assertEqual(len(rows), 3)
        found = {c["handle"]["session_id"]: c for c in rows}
        self.assertEqual(found["same"]["discovery_basis"], ["same_repository"])
        self.assertEqual(found["published"]["discovery_basis"], ["published"])
        self.assertEqual(found["both"]["discovery_basis"], ["published", "same_repository"])
        self.assertIsNone(found["published"]["repository"])
        self.assertEqual(found["published"]["repository_status"], "unknown")
        for candidate in rows:
            self.assertEqual(candidate["machine"], LOCAL)
            self.assertFalse(candidate["is_self"])
            self.assertEqual(candidate["title"]["value"], "Current title")
            self.assertEqual(candidate["summary"]["value"], "Implement verified discovery")
            self.assertEqual(candidate["doing"], candidate["summary"])
            self.assertEqual(candidate["summary"]["freshness"], "fresh")
            self.assertEqual(candidate["state"]["value"], "live")
            self.assertTrue(candidate["target"].startswith("net:" + LOCAL + ":codex:"))
            for private in (str(self.root), "PRIVATE RAW TRANSCRIPT", '"cwd"', '"transcript_path"', '"pid"'):
                self.assertNotIn(private, json.dumps(candidate))

    def test_membership_or_same_local_repo_alone_never_publishes_or_enriches(self):
        hidden = self.row("hidden")
        self.store(hidden)
        self.native(hidden)
        for repository in (REPOSITORY, None):
            with mock.patch.object(directory, "_native", wraps=directory._native) as native, \
                    mock.patch.object(directory, "_title", wraps=directory._title) as title, \
                    mock.patch.object(directory, "_liveness", wraps=directory._liveness) as live:
                self.assertEqual(self.candidates(repository), [])
                self.assertEqual((native.call_count, title.call_count, live.call_count), (0, 0, 0))
        self.maps.bind(self.repo, REPOSITORY, [OTHER])
        self.assertEqual(self.candidates(), [])

    def test_published_unmapped_repo_is_unknown_even_with_matching_name_or_url(self):
        row = self.row()
        self.store(row)
        self.native(row)
        self.publish(row)
        self.git(self.repo, "remote", "add", "origin", "https://example.invalid/shared.git")
        candidate = self.candidates()[0]
        self.assertEqual(candidate["discovery_basis"], ["published"])
        self.assertIsNone(candidate["same_repository"])
        self.assertIsNone(candidate["repository_id"])

    def test_excluded_home_deny_and_provisional_never_enrich(self):
        self.maps.bind(self.repo, REPOSITORY, [PEER])
        row = self.row()
        self.publish(row)
        variants = [dict(row, registered=False), dict(row, excluded=True), dict(row, remote=True),
                    dict(row, machine="another-host"), dict(row, certainty="provisional"),
                    dict(row, identity_basis="neighbor"), dict(row, uid=os.getuid()+1)]
        unknown_home = self.root / "unregistered-home"
        unknown_home.mkdir()
        variants.append(dict(row, home=str(unknown_home)))
        for value in variants:
            with mock.patch.object(registry, "raw_records", return_value=[value]), \
                    mock.patch.object(directory, "_native") as native:
                self.assertEqual(self.candidates(), [])
                native.assert_not_called()
        self.store(row)
        for cfg in ({"directory_excluded_paths": [str(self.repo)]}, {"directory_excluded_paths": ["relative"]},
                    {"deny": [row["ref"]]}):
            paths.write_json(paths.path(config.CONFIG), cfg)
            with mock.patch.object(directory, "_native") as native:
                self.assertEqual(self.candidates(), [])
                native.assert_not_called()

    def test_machine_and_branch_filters_precede_native_and_liveness(self):
        row = self.row()
        self.store(row)
        self.publish(row)
        self.native(row)
        with mock.patch.object(registry, "raw_records", wraps=registry.raw_records) as records:
            self.assertEqual(self.candidates(machine=OTHER), [])
            self.assertEqual(self.candidates(machine="display-name"), [])
            records.assert_not_called()
        with mock.patch.object(directory, "_native", wraps=directory._native) as native, \
                mock.patch.object(directory, "_liveness", wraps=directory._liveness) as live:
            self.assertEqual(self.candidates(machine=LOCAL, branch="not-main"), [])
            native.assert_not_called()
            live.assert_not_called()
        self.assertEqual(len(self.candidates(work="verified", branch="main")), 1)
        with mock.patch.object(directory, "_liveness", wraps=directory._liveness) as live:
            self.assertEqual(self.candidates(work="absent-task"), [])
            live.assert_not_called()

    def test_real_local_record_only_is_used_for_metadata_no_fake_remote_caller(self):
        row = self.row()
        self.store(row)
        self.publish(row)
        with mock.patch.object(directory, "discover", wraps=directory.discover) as discover:
            self.assertEqual(len(self.candidates(None)), 1)
            actual = discover.call_args.args[0]
            self.assertEqual(actual["session_id"], row["session_id"])
            self.assertEqual(actual["home"], row["home"])
            self.assertNotEqual(actual.get("machine"), PEER)
            self.assertEqual(discover.call_args.kwargs["records"], [actual])

    def test_resolve_exact_home_runtime_generation_and_rename_only(self):
        row = self.row()
        self.store(row)
        self.native(row)
        self.publish(row)
        handle = self.candidates()[0]["handle"]
        self.assertEqual(net.resolve_local(handle, LOCAL)["session_id"], row["session_id"])
        self.native(row, title="Renamed title")
        self.assertEqual(net.resolve_local(handle, LOCAL)["name"], "Renamed title")
        for altered in (dict(handle, machine=OTHER), dict(handle, home_id="0"*64),
                        dict(handle, runtime="claude"), dict(handle, generation="0"*64),
                        dict(handle, session_id="another")):
            self.assertIsNone(net.resolve_local(altered, LOCAL))
        self.assertIsNone(net.resolve_local("net:" + LOCAL + ":codex:any:name", LOCAL))
        resumed = dict(row, lstart="new-generation")
        self.store(resumed)
        self.assertIsNone(net.resolve_local(handle, LOCAL))

    def test_resolve_rechecks_new_exclusion_deny_home_and_native_replacement(self):
        row = self.row()
        self.store(row)
        self.native(row)
        handle = net.public_endpoint(row, LOCAL)
        for cfg in ({"directory_excluded_paths": [str(self.repo)]}, {"deny": [row["ref"]]}):
            paths.write_json(paths.path(config.CONFIG), cfg)
            self.assertIsNone(net.resolve_local(handle, LOCAL))
        paths.write_json(paths.path(config.CONFIG), {})
        config.remove_home(str(self.home))
        self.assertIsNone(net.resolve_local(handle, LOCAL))
        config.add_home(str(self.home), "codex")
        rollout = self.native(row)
        rollout.write_text(json.dumps({"type":"session_meta", "payload":{"id":"replacement"}}) + "\n")
        self.assertIsNone(net.resolve_local(handle, LOCAL))

    def test_resolve_mid_lookup_resume_or_privacy_change_fails_closed(self):
        row = self.row()
        self.store(row)
        self.native(row)
        handle = net.public_endpoint(row, LOCAL)
        real_enrich = registry._enrich
        def resume(record):
            value = real_enrich(record)
            self.store(dict(row, lstart="resumed"))
            return value
        with mock.patch.object(registry, "_enrich", side_effect=resume):
            self.assertIsNone(net.resolve_local(handle, LOCAL))
        self.store(row)
        def exclude(record):
            value = real_enrich(record)
            paths.write_json(paths.path(config.CONFIG), {"directory_excluded_paths": [str(self.repo)]})
            return value
        with mock.patch.object(registry, "_enrich", side_effect=exclude):
            self.assertIsNone(net.resolve_local(handle, LOCAL))

    def test_zero_budget_and_unavailable_registry_expose_nothing(self):
        row = self.row()
        self.store(row)
        self.publish(row)
        with probe.quick(budget=0), mock.patch.object(directory, "_native") as native:
            self.assertEqual(self.candidates(), [])
            self.assertIsNone(net.resolve_local(net.public_endpoint(row, LOCAL), LOCAL))
            native.assert_not_called()
            self.assertTrue(probe.unanswered())
        with mock.patch.object(registry, "raw_records", side_effect=OSError("unavailable")):
            self.assertEqual(self.candidates(), [])

    def test_visibility_revoked_during_metadata_read_is_not_returned(self):
        row = self.row()
        self.store(row)
        self.native(row)
        real_title = directory._title
        self.publish(row)
        def revoke_publication(record, endpoint):
            title = real_title(record, endpoint)
            directory.publish(record, visible=False, user_source="local operator revoked publication")
            return title
        with mock.patch.object(directory, "_title", side_effect=revoke_publication):
            self.assertEqual(self.candidates(), [])
        self.maps.bind(self.repo, REPOSITORY, [PEER])
        def revoke_mapping(record, endpoint):
            title = real_title(record, endpoint)
            self.maps.bind(self.repo, REPOSITORY, [OTHER])
            return title
        with mock.patch.object(directory, "_title", side_effect=revoke_mapping):
            self.assertEqual(self.candidates(), [])

    def test_resolve_rejects_home_symlink_retarget_despite_realpath_memo(self):
        second_home = self.root / "second-home"
        second_home.mkdir()
        config.add_home(str(second_home), "codex")
        alias = self.root / "home-link"
        alias.symlink_to(self.home, target_is_directory=True)
        row = self.row(home=str(alias))
        self.store(row)
        self.native(row)
        handle = net.public_endpoint(row, LOCAL)
        real_enrich = registry._enrich
        def retarget(record):
            current = real_enrich(record)
            alias.unlink()
            alias.symlink_to(second_home, target_is_directory=True)
            return current
        with mock.patch.object(registry, "_enrich", side_effect=retarget):
            self.assertIsNone(net.resolve_local(handle, LOCAL))

    def test_candidate_cwd_symlink_retarget_cannot_bypass_exclusion(self):
        private = self.root / "private"
        private.mkdir()
        alias = self.root / "working-link"
        alias.symlink_to(self.repo, target_is_directory=True)
        row = self.row(cwd=str(alias))
        self.store(row)
        self.native(row)
        self.publish(row)
        paths.write_json(paths.path(config.CONFIG), {"directory_excluded_paths": [str(private)]})
        real_title = directory._title
        def retarget(record, endpoint):
            title = real_title(record, endpoint)
            alias.unlink()
            alias.symlink_to(private, target_is_directory=True)
            return title
        with mock.patch.object(directory, "_title", side_effect=retarget):
            self.assertEqual(self.candidates(), [])

    def test_stale_liveness_and_unknown_metadata_preserve_directory_schema(self):
        row = self.row(pid=2147483647, name="Cached /private/hidden/title", updated=time.time()-1000)
        self.store(row)
        self.publish(row)
        candidate = self.candidates()[0]
        self.assertEqual(candidate["state"]["value"], "stale")
        self.assertEqual(candidate["receive"]["value"], "unavailable")
        self.assertEqual(candidate["name_freshness"], "unknown")
        self.assertEqual(candidate["title"]["source"], "registry:hook.name")
        self.assertIsNone(candidate["summary"]["value"])
        self.assertNotIn("/private/hidden/title", json.dumps(candidate))

    def test_distinct_homes_with_same_session_id_resolve_only_exact_profile(self):
        second_home = self.root / "other-profile"
        second_home.mkdir()
        self._database(second_home)
        config.add_home(str(second_home), "codex")
        first = self.row()
        second = self.row(home=str(second_home))
        self.store(first, second)
        for row in (first, second):
            self.native(row)
            self.publish(row)
        candidates = self.candidates()
        self.assertEqual(len(candidates), 2)
        self.assertEqual(len({c["target"] for c in candidates}), 2)
        for candidate in candidates:
            resolved = net.resolve_local(candidate["handle"], LOCAL)
            self.assertEqual(net.public_endpoint(resolved, LOCAL), candidate["handle"])

    def test_candidate_registry_cwd_change_during_native_read_is_not_disclosed(self):
        private = self.root / "excluded-repository"
        private.mkdir()
        row = self.row()
        self.store(row)
        self.native(row)
        self.maps.bind(self.repo, REPOSITORY, [PEER])
        paths.write_json(paths.path(config.CONFIG), {"directory_excluded_paths": [str(private)]})
        original = directory._native
        def move_into_private(record, endpoint):
            metadata = original(record, endpoint)
            self.store(dict(row, cwd=str(private)))
            return metadata
        with mock.patch.object(directory, "_native", side_effect=move_into_private):
            self.assertEqual(self.candidates(), [])

    def test_claude_actual_native_title_todo_socket_and_replacement(self):
        home = self.root / "claude"
        home.mkdir()
        config.add_home(str(home), "claude")
        transcript = home / "conversation.jsonl"
        row = self.row(runtime="claude", home=str(home), transcript_path=str(transcript))
        stamp = time.time()
        transcript.write_text(json.dumps({"sessionId": row["session_id"], "type":"assistant", "timestamp":stamp,
            "message":{"content":[{"type":"tool_use", "name":"TodoWrite", "input":{"todos":[
                {"content":"Verify actual Claude discovery", "status":"in_progress"}]}}]}}) + "\n")
        # Short Unix path keeps this fixture within macOS sun_path's bound.
        with tempfile.TemporaryDirectory(prefix="xsm-nd-") as socket_root, socket.socket(socket.AF_UNIX) as server:
            socket_path = str(Path(socket_root) / "s")
            server.bind(socket_path)
            server.listen(16)
            native_path = home / "sessions" / (str(row["pid"]) + ".json")
            paths.write_json(str(native_path), {"sessionId":row["session_id"], "name":"Claude current title",
                                                "messagingSocketPath":socket_path})
            self.store(row)
            self.publish(row)
            candidate = self.candidates()[0]
            self.assertEqual(candidate["runtime"], "claude")
            self.assertEqual(candidate["title"]["value"], "Claude current title")
            self.assertEqual(candidate["doing"]["value"], "Verify actual Claude discovery")
            self.assertEqual(candidate["receive"]["value"], "available")
            self.assertEqual(candidate["title"]["source"], "claude:registry:current_name")
            self.assertNotIn(socket_path, json.dumps(candidate))
            self.assertEqual(net.resolve_local(candidate["handle"], LOCAL)["session_id"], row["session_id"])
            paths.write_json(str(native_path), {"sessionId":"replacement", "name":"new conversation"})
            self.assertIsNone(net.resolve_local(candidate["handle"], LOCAL))


if __name__ == "__main__":
    unittest.main()
