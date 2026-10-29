"""ADR-0024 local directory: real Git/native fixtures, no product integration."""
import json
import os
import sqlite3
import subprocess
import tempfile
import time
import unittest
from contextlib import closing
from unittest import mock

from xsm import config, directory as d, paths, probe, registry


class DirectoryTest(unittest.TestCase):
    def setUp(self):
        global config, d, paths, probe, registry
        from xsm import config, directory as d, paths, probe, registry

        self.tmp = tempfile.TemporaryDirectory(prefix="xsm-p05-")
        self.addCleanup(self.tmp.cleanup)
        self.root = os.path.realpath(self.tmp.name)
        self.state = os.path.join(self.root, "state")
        patch = mock.patch.object(paths, "HOME", self.state)
        patch.start()
        self.addCleanup(patch.stop)
        paths.ensure_home()
        self.home = os.path.join(self.root, "codex")
        self.claude = os.path.join(self.root, "claude")
        os.mkdir(self.home)
        os.mkdir(self.claude)
        config.add_home(self.home, "codex")
        config.add_home(self.claude, "claude")
        self.repo = os.path.join(self.root, "repo")
        os.mkdir(self.repo)
        self.git("init", "-q", "-b", "main")
        self.git("-c", "user.name=Directory test", "-c", "commit.gpgsign=false",
                 "commit", "-q", "--allow-empty", "-m", "fixture")
        self.outside = os.path.join(self.root, "outside")
        os.mkdir(self.outside)
        self.caller = self.row("caller")
        patch = mock.patch.object(d.identity, "state_reason", return_value=("live", "live"))
        self.state_mock = patch.start()
        self.addCleanup(patch.stop)
        with closing(sqlite3.connect(os.path.join(self.home, "state_5.sqlite"))) as con, con:
            con.execute("create table threads (id text primary key, name text, rollout_path text)")

    def git(self, *args, **kwargs):
        result = subprocess.run(["git", "-C", kwargs.get("cwd", self.repo)] + list(args),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def row(self, sid="one", **updates):
        value = dict(runtime="codex", home=self.home, session_id=sid, cwd=self.repo,
                     pid=os.getpid(), app_server=False, ref="abcdef", name="stale cached name")
        value.update(updates)
        return value

    def discover(self, rows, **filters):
        return d.discover(self.caller, records=rows, **filters)

    def candidates(self, rows, **filters):
        return self.discover(rows, **filters)["candidates"]

    def publish(self, row, visible=True):
        return d.publish(row, visible=visible, user_source="native user publication instruction")

    def cfg(self, **values):
        paths.write_json(paths.path(config.CONFIG), values)

    def store(self, *rows):
        for row in rows:
            paths.write_json(registry._record_path(row["runtime"], row["session_id"]), row)

    def native(self, row=None, rows=None, name="Current native title", stamp=None):
        row = row or self.row()
        stamp = time.time() if stamp is None else stamp
        sid = row["session_id"]
        path = os.path.join(row["home"], sid + ".jsonl")
        meta = {"type": "session_meta", "timestamp": stamp,
                "payload": {"id": sid, "git": {"branch": "historical"}}}
        plan = {"type": "response_item", "timestamp": stamp, "payload": {
            "type": "function_call", "name": "update_plan", "arguments": json.dumps({
                "plan": [{"step": "Implement native directory discovery", "status": "in_progress"}]})}}
        with open(path, "w") as stream:
            for item in [meta] + ([plan] if rows is None else rows):
                stream.write(json.dumps(item) + "\n")
        with closing(sqlite3.connect(os.path.join(row["home"], "state_5.sqlite"))) as con, con:
            con.execute("insert or replace into threads values (?, ?, ?)", (sid, name, path))
        return path

    def test_union_of_publication_and_same_repo_without_duplicates(self):
        same = self.row("same")
        both = self.row("both")
        public = self.row("public", cwd=self.outside)
        private = self.row("private", cwd=self.outside)
        self.publish(both)
        self.publish(public)
        got = {r["handle"]["session_id"]: r for r in self.candidates([same, both, public, private, both])}
        self.assertEqual(set(got), {"same", "both", "public"})
        self.assertEqual(got["both"]["discovery_basis"], ["published", "same_repo"])
        self.assertEqual(got["same"]["discovery_basis"], ["same_repo"])

    def test_real_linked_worktree_is_same_repo(self):
        worktree = os.path.join(self.root, "worktree")
        self.git("worktree", "add", "-q", "-b", "feature", worktree)
        sub = os.path.join(worktree, "sub")
        os.mkdir(sub)
        got = self.candidates([self.row(cwd=sub)])
        self.assertEqual(got[0]["discovery_basis"], ["same_repo"])
        self.assertEqual(got[0]["branch"]["value"], "feature")
        self.assertEqual(got[0]["repository"], "repo")

    def test_same_remote_url_and_name_do_not_merge_independent_clones(self):
        other = os.path.join(self.outside, "repo")
        os.mkdir(other)
        self.git("init", "-q", cwd=other)
        for path in (self.repo, other):
            self.git("remote", "add", "origin", "https://example.invalid/shared.git", cwd=path)
        self.assertEqual(self.candidates([self.row(cwd=other)]), [])

    def test_private_outside_is_not_enriched_or_counted(self):
        private = self.row("private", cwd=self.outside, name="SECRET")
        with mock.patch.object(d, "_native") as native, mock.patch.object(d, "_title") as title:
            got = self.discover([private])
        native.assert_not_called()
        title.assert_not_called()
        self.state_mock.assert_not_called()
        self.assertEqual(got, dict(candidates=[], status="ok", reason=None, unanswered={}))
        self.assertNotIn("SECRET", json.dumps(got))

    def test_publication_is_exact_and_survives_rename_resume(self):
        row = self.row(cwd=self.outside)
        evidence = self.publish(row)
        self.assertTrue(d.is_published(dict(row, pid=99, lstart="resumed", name="renamed")))
        self.assertFalse(d.is_published(dict(row, session_id="replacement")))
        self.assertFalse(d.is_published(dict(row, runtime="claude", home=self.claude)))
        self.assertFalse(d.is_published(dict(row, remote=True, machine="macmini")))
        self.assertEqual(evidence["endpoint"]["session_id"], row["session_id"])
        file = paths.path(d.PUBLICATIONS, d._key(evidence["endpoint"]) + ".json")
        self.assertEqual(os.stat(file).st_mode & 0o777, 0o600)

    def test_home_and_short_ref_collision_do_not_inherit_publication(self):
        row = self.row(cwd=self.outside)
        self.publish(row)
        home2 = os.path.join(self.root, "codex2")
        os.mkdir(home2)
        config.add_home(home2, "codex")
        self.assertFalse(d.is_published(dict(row, home=home2)))
        self.assertFalse(d.is_published(dict(row, session_id="new", name=row["name"])))

    def test_ref_and_name_collisions_keep_distinct_exact_handles(self):
        a, b = self.row("a"), self.row("b")
        self.native(a, name="same name")
        self.native(b, name="same name")
        got = self.candidates([a, b])
        self.assertEqual([r["name"] for r in got], ["same name", "same name"])
        self.assertEqual(len({r["id"] for r in got}), 2)
        self.assertEqual(len({r["handle"]["session_id"] for r in got}), 2)

    def test_native_rename_is_current_and_resume_retains_id(self):
        row = self.row()
        self.native(row, name="before")
        before = self.candidates([row])[0]
        self.native(row, name="after")
        after = self.candidates([dict(row, pid=99)])[0]
        self.assertEqual((before["name"], after["name"]), ("before", "after"))
        self.assertEqual(before["id"], after["id"])

    def test_publish_does_not_expand_communication_scope(self):
        row = self.row(cwd=self.outside)
        before = config.load()
        self.assertIsNone(config.scope_for(self.caller, row)[0])
        self.publish(row)
        self.assertEqual(config.load(), before)
        self.assertIsNone(config.scope_for(self.caller, row)[0])
        self.assertEqual(self.candidates([row])[0]["discovery_basis"], ["published"])

    def test_withdrawal_removes_only_publication_not_same_repo(self):
        outside, same = self.row(cwd=self.outside), self.row("same")
        for row in (outside, same):
            self.publish(row)
            self.publish(row, visible=False)
            self.assertFalse(d.is_published(row))
        self.assertEqual([r["handle"]["session_id"] for r in self.candidates([outside, same])], ["same"])

    def test_publication_requires_exact_local_identity_and_user_source(self):
        for row in (dict(self.row(), certainty="provisional"), dict(self.row(), basis="cwd"),
                    dict(self.row(), machine="macmini"), dict(self.row(), session_id="")):
            with self.assertRaises(ValueError):
                self.publish(row)
        with self.assertRaises(ValueError):
            d.publish(self.row())

    def test_allowed_homes_and_same_uid_are_required(self):
        unknown = os.path.join(self.root, "not-allowed")
        os.mkdir(unknown)
        for row in (self.row(home=unknown), self.row(uid=os.getuid() + 1),
                    self.row(registered=False), self.row(machine="macmini"), self.row(origin="macmini")):
            self.assertEqual(self.candidates([row]), [])
        with mock.patch.object(d, "_owned_home", return_value=False):
            self.assertEqual(self.candidates([self.row()]), [])

    def test_exclusions_canonical_symlink_missing_descendants_and_sibling(self):
        private = os.path.join(self.repo, "private")
        sibling = os.path.join(self.repo, "private-other")
        alias = os.path.join(self.repo, "alias")
        os.mkdir(private)
        os.mkdir(sibling)
        os.symlink(private, alias)
        self.cfg(directory_excluded_paths=[private])
        for path in (private, alias, os.path.join(alias, "missing", "child")):
            self.assertTrue(d.excluded(path))
        self.assertFalse(d.excluded(sibling))
        got = self.candidates([self.row("private", cwd=alias), self.row("allowed", cwd=sibling)])
        self.assertEqual([r["handle"]["session_id"] for r in got], ["allowed"])

    def test_explicit_exclusion_list_is_the_shared_policy(self):
        self.assertTrue(d.excluded(os.path.join(self.repo, "missing"), [self.repo]))
        self.assertFalse(d.excluded(self.repo, []))
        for policy in (["relative"], [None], "bad"):
            self.assertTrue(d.excluded(self.repo, policy))

    def test_excluded_publication_and_deny_never_enriched(self):
        self.publish(self.row())
        self.cfg(directory_excluded_paths=[self.repo])
        with mock.patch.object(d, "_native") as native:
            self.assertEqual(self.candidates([self.row()]), [])
        native.assert_not_called()
        self.cfg(deny=["abcdef"])
        self.assertEqual(self.candidates([self.row()]), [])

    def test_remote_placeholder_unknown_and_same_name_cannot_shadow_local(self):
        local = self.row()
        self.native(local, name="review")
        remote = self.row("remote", machine="macmini", name="review")
        self.assertEqual(len(self.candidates([remote, local])), 1)
        got = self.discover([remote, local], machine="macmini")
        self.assertEqual(got["status"], "unknown")
        self.assertEqual(got["candidates"], [])
        self.assertNotIn("review", json.dumps(got))

    def test_branch_filter_precedes_native_enrichment(self):
        with mock.patch.object(d, "_native") as native, mock.patch.object(d, "_title") as title:
            self.assertEqual(self.candidates([self.row()], branch="not-main"), [])
        native.assert_not_called()
        title.assert_not_called()

    def test_work_filter_precedes_liveness_and_uses_native_not_cached_prose(self):
        self.native(name="Review native metadata")
        self.assertEqual(self.candidates([self.row()], work="cached"), [])
        self.state_mock.assert_not_called()
        self.assertEqual(len(self.candidates([self.row()], work="DIRECTORY")), 1)
        self.assertEqual(len(self.candidates([self.row()], work="review native")), 1)

    def test_codex_native_summary_branch_source_freshness_and_busy_idle(self):
        now = time.time()
        path = self.native(stamp=now)
        with open(path, "a") as stream:
            stream.write(json.dumps({"type": "event_msg", "timestamp": now,
                                    "payload": {"type": "task_started"}}) + "\n")
        got = self.candidates([self.row()])[0]
        self.assertEqual(got["summary"]["value"], "Implement native directory discovery")
        self.assertEqual(got["summary"]["source"], "codex:rollout:update_plan")
        self.assertEqual(got["summary"]["timestamp"], now)
        self.assertEqual(got["summary"]["freshness"], "fresh")
        self.assertEqual(got["branch"]["value"], "main")
        self.assertEqual(got["activity"]["value"], "busy")
        self.assertEqual(got["receive"]["value"], "available")
        with open(path, "a") as stream:
            stream.write(json.dumps({"type": "event_msg", "timestamp": now,
                                    "payload": {"type": "task_complete"}}) + "\n")
        self.assertEqual(self.candidates([self.row()])[0]["activity"]["value"], "idle")

    def test_stale_metadata_is_labeled_not_consent_or_live_work(self):
        self.native(stamp=time.time() - d.STALE_SECONDS - 100)
        got = self.candidates([self.row()])[0]
        self.assertEqual(got["summary"]["freshness"], "stale")
        self.assertNotIn("approved", got)

    def test_claude_native_title_and_documented_todowrite_schema(self):
        row = self.row("claude-session", runtime="claude", home=self.claude, socket="/tmp/fixture.sock")
        native = os.path.join(self.claude, "sessions", "%s.json" % row["pid"])
        paths.write_json(native, dict(sessionId=row["session_id"], name="Claude current title"))
        transcript = os.path.join(self.claude, "native-transcript.jsonl")
        row["transcript_path"] = transcript
        with open(transcript, "w") as stream:
            stream.write(json.dumps({"sessionId": row["session_id"], "type": "assistant", "timestamp": time.time(),
                "message": {"content": [{"type": "tool_use", "name": "TodoWrite", "input": {
                    "todos": [{"content": "Review directory", "activeForm": "Reviewing directory", "status": "in_progress"}]}}]}}) + "\n")
        got = self.candidates([row])[0]
        self.assertEqual(got["name"], "Claude current title")
        self.assertEqual(got["summary"]["value"], "Review directory")
        self.assertEqual(got["summary"]["source"], "claude:transcript:TodoWrite")
        self.assertEqual(got["activity"]["status"], "unknown")
        paths.write_json(native, dict(sessionId="different-conversation", name="DO NOT LEAK"))
        got = self.candidates([row])[0]
        self.assertEqual(got["title"]["source"], "registry:hook.name")
        self.assertEqual(got["name"], row["name"])
        self.assertEqual(got["name_freshness"], "unknown")
        self.assertEqual(got["state"]["value"], "ended")
        self.assertEqual(got["receive"]["value"], "unavailable")

    def test_absolute_paths_and_transcript_prose_are_never_disclosed(self):
        row = self.row()
        path = self.native(row, name="Inspect " + self.root + "/secret.txt")
        with open(path, "a") as stream:
            stream.write(json.dumps({"type": "response_item", "payload": {"type": "message", "role": "user",
                "content": [{"type": "input_text", "text": "PRIVATE_TRANSCRIPT_PROSE"}]}}) + "\n")
        got = json.dumps(self.discover([row]))
        self.assertNotIn(self.root, got)
        self.assertNotIn("PRIVATE_TRANSCRIPT_PROSE", got)
        self.assertNotIn("transcript_path", got)
        self.assertIn("[path]", got)

    def test_budget_exhaustion_is_unknown_and_never_restarts_outer_budget(self):
        with probe.quick(budget=0):
            got = self.discover([self.row()])
        self.assertEqual(got["status"], "unknown")
        self.assertEqual(got["candidates"], [])
        with probe.quick():
            d._settings()
            own = d._endpoint(self.caller)
            self.assertTrue(d._allowed(self.caller, own))
            d.excluded(self.repo)
            d._real(self.repo)  # Empty exclusion policy no longer probes paths.
            d._repo(self.repo)
            with mock.patch.object(probe, "limit", return_value=0):
                got = self.discover([self.row()])
        self.assertEqual(got["status"], "unknown")
        self.assertEqual(len(got["candidates"]), 1)
        self.assertEqual(got["candidates"][0]["summary"]["status"], "unknown")

    def test_source_failure_is_unknown_and_does_not_block_base_communication(self):
        row = self.row()
        with mock.patch.object(d, "_native", side_effect=ValueError("bad source")), \
                mock.patch.object(d, "_title", side_effect=ValueError("bad title")):
            got = self.candidates([row])[0]
        self.assertEqual(got["summary"]["status"], "unknown")
        self.assertEqual(got["title"]["source"], "registry:hook.name")
        self.assertEqual(got["title"]["freshness"], "unknown")
        self.assertEqual(got["receive"]["value"], "available")
        self.assertIsNotNone(config.scope_for(self.caller, row)[0])

    def test_partial_json_truncate_and_mismatched_session_are_unknown(self):
        for suffix in (b'{"type":', b'{bad}\n', b'\xff\n'):
            path = self.native()
            with open(path, "ab") as stream:
                stream.write(suffix)
            self.assertEqual(self.candidates([self.row()])[0]["summary"]["status"], "unknown")
        path = self.native()
        with open(path, "wb") as stream:
            stream.write(b'')
        self.assertEqual(self.candidates([self.row()])[0]["summary"]["status"], "unknown")
        self.native(rows=[{"type": "session_meta", "payload": {"id": "other"}}])
        self.assertEqual(self.candidates([self.row()])[0]["summary"]["status"], "unknown")

    def test_atomic_replace_and_concurrent_truncation_are_unknown(self):
        path = self.native()
        endpoint = d._endpoint(self.row())
        original_fstat = os.fstat
        calls = []

        def replace_after_read(fd):
            info = original_fstat(fd)
            calls.append(fd)
            if len(calls) == 2:
                other = path + ".replacement"
                with open(other, "wb") as stream:
                    stream.write(b'{}\n')
                os.replace(other, path)
            return info

        with mock.patch.object(d.os, "fstat", side_effect=replace_after_read):
            self.assertIsNone(d._snapshot(path, endpoint))
        path = self.native()
        calls.clear()

        def truncate_after_read(fd):
            calls.append(fd)
            if len(calls) == 2:
                with open(path, "wb"):
                    pass
            return original_fstat(fd)

        with mock.patch.object(d.os, "fstat", side_effect=truncate_after_read):
            self.assertIsNone(d._snapshot(path, endpoint))

    def test_large_tail_skips_old_plan_and_partial_first_line(self):
        path = self.native()
        with open(path, "a") as stream:
            stream.write(json.dumps({"type": "event_msg", "payload": {
                "type": "agent_message", "message": "x" * (d.TAIL_BYTES + 100)}}) + "\n")
            stream.write(json.dumps({"type": "event_msg", "timestamp": time.time(),
                                    "payload": {"type": "task_started"}}) + "\n")
        got = self.candidates([self.row()])[0]
        self.assertEqual(got["summary"]["status"], "unknown")
        self.assertEqual(got["activity"]["value"], "busy")

    def test_native_reader_uses_only_bounded_head_and_tail(self):
        path = self.native()
        original_fdopen = os.fdopen
        reads = []

        class Tracked:
            def __init__(self, fd, mode):
                self.stream = original_fdopen(fd, mode)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.stream.close()

            def __getattr__(self, name):
                return getattr(self.stream, name)

            def read(self, size=-1):
                if size < 0:
                    raise AssertionError("unbounded native read")
                reads.append(size)
                return self.stream.read(size)

            def readline(self, size=-1):
                if size < 0:
                    raise AssertionError("unbounded native head")
                reads.append(size)
                return self.stream.readline(size)

        with mock.patch.object(d.os, "fdopen", side_effect=Tracked):
            self.assertIsNotNone(d._snapshot(path, d._endpoint(self.row())))
        self.assertLessEqual(sum(reads), d.HEAD_BYTES + d.TAIL_BYTES + 2)

    def test_receive_capability_is_not_a_successful_delivery_claim(self):
        for state, why, expected in (("ended", "pid_dead", "unavailable"),
                                     ("live", "live_unverified", None),
                                     ("live", "socket_blocked", None),
                                     ("unknown", "no_pid", None)):
            self.state_mock.return_value = state, why
            self.assertEqual(self.candidates([self.row()])[0]["receive"]["value"], expected)

    def test_current_cached_name_fallback_is_labeled_unknown_not_current_native(self):
        got = self.candidates([self.row()])[0]
        self.assertEqual(got["name"], "stale cached name")
        self.assertEqual(got["name_source"], "registry:hook.name")
        self.assertEqual(got["name_freshness"], "unknown")
        self.assertEqual(got["title"]["value"], "stale cached name")
        self.assertEqual(len(self.candidates([self.row()], work="cached")), 1)

    def test_hook_name_fallback_preserves_search_source_and_original_timestamp(self):
        stamp = time.time() - 120
        row = registry.upsert("codex", self.home, "hook-name", os.getpid(), self.repo,
                              name="reviewer from native hook")
        row["updated"] = stamp
        for runtime, home in (("codex", self.home), ("claude", self.claude)):
            for failure in (None, OSError("native title unavailable")):
                with self.subTest(runtime=runtime, failure=failure), mock.patch.object(
                        d, "_title", return_value=None, side_effect=failure):
                    candidate = dict(row, runtime=runtime, home=home)
                    got = self.candidates([candidate], work="reviewer")[0]
                    self.assertEqual(got["name"], row["name"])
                    self.assertEqual(got["title"]["source"], "registry:hook.name")
                    self.assertEqual(got["title"]["timestamp"], stamp)
                    self.assertEqual(got["title"]["freshness"], "unknown")
                    no_name = self.candidates([dict(candidate, name=None)])[0]
                    self.assertIsNone(no_name["name"])
                    self.assertIsNone(no_name["title"]["value"])

    def test_default_discovery_reads_raw_registry_not_global_enrichment(self):
        self.store(self.row(), self.row("private", cwd=self.outside))
        with mock.patch.object(registry, "records", side_effect=AssertionError("global enrichment")):
            got = d.discover(self.caller)
        self.assertEqual(len(got["candidates"]), 1)

    def test_candidate_target_resolves_exact_full_record_even_with_ref_collision(self):
        a, b = self.row("a"), self.row("b")
        self.native(a, name="same")
        self.native(b, name="same")
        self.store(a, b)
        got = self.candidates([a, b])
        for candidate in got:
            self.assertEqual(candidate["target"], "candidate:" + candidate["id"])
            selected = d.resolve_candidate(self.caller, candidate["target"])
            self.assertEqual(selected["session_id"], candidate["handle"]["session_id"])
            self.assertEqual(selected["home"], self.home)
        for invalid in ("abcdef", "same", "candidate:abcdef", "candidate:" + "0" * 64, None):
            self.assertIsNone(d.resolve_candidate(self.caller, invalid))

    def test_candidate_resolution_rechecks_withdrawal_exclusion_home_and_machine(self):
        row = self.row(cwd=self.outside)
        self.publish(row)
        self.store(row)
        key = self.candidates([row])[0]["id"]
        self.assertIsNotNone(d.resolve_candidate(self.caller, key))
        self.publish(row, visible=False)
        self.assertIsNone(d.resolve_candidate(self.caller, key))
        self.publish(row)
        self.cfg(directory_excluded_paths=[self.outside])
        self.assertIsNone(d.resolve_candidate(self.caller, key))
        self.cfg()
        self.store(dict(row, machine="macmini"))
        self.assertIsNone(d.resolve_candidate(self.caller, key))
        self.store(row)
        config.remove_home(self.home)
        self.assertIsNone(d.resolve_candidate(self.caller, key))

    def test_native_identity_replacement_never_resolves_to_old_candidate(self):
        row = self.row()
        path = self.native(row)
        self.store(row)
        key = self.candidates([row])[0]["id"]
        with open(path, "w") as stream:
            stream.write(json.dumps({"type": "session_meta", "payload": {"id": "replacement"}}) + "\n")
        self.assertIsNone(d.resolve_candidate(self.caller, key))
        self.native(row)
        with mock.patch.object(registry, "_enrich", return_value=dict(row, session_id="replaced")):
            self.assertIsNone(d.resolve_candidate(self.caller, key))

    def test_resume_mid_resolution_retries_then_resolves_new_generation(self):
        row = self.row()
        self.store(row)
        key = self.candidates([row])[0]["id"]
        original_enrich = registry._enrich

        def resume(raw):
            self.store(dict(row, pid=999, lstart="new generation"))
            return original_enrich(raw)

        with mock.patch.object(registry, "_enrich", side_effect=resume):
            self.assertIsNone(d.resolve_candidate(self.caller, key))
        self.assertEqual(d.resolve_candidate(self.caller, key)["pid"], 999)

    def test_policy_change_during_resolution_is_rechecked(self):
        row = self.row(cwd=self.outside)
        self.publish(row)
        self.store(row)
        key = self.candidates([row])[0]["id"]
        original_enrich = registry._enrich

        def change_policy(raw):
            self.cfg(directory_excluded_paths=[self.outside])
            return original_enrich(raw)

        with mock.patch.object(registry, "_enrich", side_effect=change_policy):
            self.assertIsNone(d.resolve_candidate(self.caller, key))

    def test_publication_never_expires_by_display_freshness_and_can_revoke_after_exclusion(self):
        row = self.row(cwd=self.outside)
        self.publish(row)
        with mock.patch.object(d.time, "time", return_value=time.time() + 86400 * 365):
            self.assertTrue(d.is_published(row))
        self.cfg(directory_excluded_paths=[self.outside])
        self.publish(row, visible=False)
        self.cfg()
        self.assertFalse(d.is_published(row))

    def test_dedup_prefers_latest_same_conversation_generation(self):
        old = self.row(updated=1, pid=111)
        new = self.row(updated=2, pid=222)
        got = self.candidates([old, new])
        self.assertEqual(len(got), 1)
        self.assertEqual(self.state_mock.call_args.args[0]["pid"], 222)

    def test_unknown_plan_schema_clears_old_summary_and_never_scans_prose(self):
        path = self.native()
        with open(path, "a") as stream:
            stream.write(json.dumps({"type": "response_item", "timestamp": time.time(), "payload": {
                "type": "function_call", "name": "update_plan", "arguments": "not JSON"}}) + "\n")
        self.assertEqual(self.candidates([self.row()])[0]["summary"]["status"], "unknown")

    def test_invalid_filters_and_glob_exclusions_fail_closed(self):
        for filters in ({"machine": []}, {"work": True}, {"branch": ""}):
            self.assertEqual(self.discover([self.row()], **filters)["status"], "unknown")
        self.assertTrue(d.excluded(self.repo, [self.repo + "/*"]))

    def test_display_todo_limit_does_not_misidentify_ninth_active_task(self):
        items = [{"step": "pending " + str(i), "status": "pending"} for i in range(8)]
        items.append({"step": "Actual active work", "status": "in_progress"})
        self.native(rows=[{"type": "response_item", "timestamp": time.time(), "payload": {
            "type": "function_call", "name": "update_plan", "arguments": json.dumps({"plan": items})}}])
        got = self.candidates([self.row()])[0]
        self.assertEqual(got["summary"]["value"], "Actual active work")
        self.assertEqual(len(got["todo"]["value"]), 8)
        self.assertTrue(got["todo"]["truncated"])

    def test_empty_exclusion_config_does_not_add_directory_probe_to_registry(self):
        with mock.patch.object(d, "exclusion_status", side_effect=AssertionError("unexpected default probe")):
            registry.upsert("codex", self.home, "one", os.getpid(), self.repo, inside=None)
            registry.records()

    def test_three_way_exclusion_unknown_and_confirmed_match_precedence(self):
        for policy in (["~typo/private"], [self.repo + "/*"], [None], ["relative"], "bad", False):
            with self.subTest(policy=policy):
                self.assertEqual(d.exclusion_status(self.repo, policy), "unknown")
                self.assertTrue(d.excluded(self.repo, policy))
        self.assertEqual(d.exclusion_status(self.repo, []), "included")
        self.assertEqual(d.exclusion_status(self.repo, [self.outside]), "included")
        for policy in (["~typo/private", self.repo], [self.repo, "~typo/private"],
                       [None, self.repo, self.repo + "/*"]):
            self.assertEqual(d.exclusion_status(self.repo, policy), "excluded")
        with probe.quick(budget=0):
            self.assertEqual(d.exclusion_status(self.repo, [self.repo]), "unknown")
            self.assertTrue(d.excluded(self.repo, [self.repo]))
            self.assertEqual(d.exclusion_status(self.repo, []), "included")

    def test_invalid_exclusion_config_preserves_registration_and_name_lookup(self):
        from xsm import resolve
        policies = (["~typo/private"], [self.repo + "/priv*"], ["relative"], [None],
                    "bad", None, False, 0, {})
        for index, policy in enumerate(policies):
            with self.subTest(policy=policy):
                self.cfg(directory_excluded_paths=policy)
                sid = "invalid-policy-%d" % index
                row = registry.upsert("codex", self.home, sid, os.getpid(), self.repo, name=sid)
                self.assertTrue(row.get("ref"))
                self.assertIsNot(row.get("registered"), False)
                self.assertEqual(row["directory_exclusion_status"], "unknown")
                self.assertEqual(resolve.resolve(sid).record["session_id"], sid)
                self.assertIn(sid, [r["session_id"] for r in registry.records()])
                self.assertIsNotNone(config.scope_for(self.caller, row)[0])
                self.assertTrue(d.excluded(self.repo))
                self.assertEqual(self.candidates([row]), [])

    def test_zero_budget_preserves_existing_and_new_lookup_with_valid_exclusion(self):
        from xsm import resolve
        registry.upsert("codex", self.home, "before-budget", os.getpid(), self.repo, name="before-budget")
        self.cfg(directory_excluded_paths=[self.outside])
        with probe.quick(budget=0):
            row = registry.upsert("codex", self.home, "during-budget", os.getpid(), self.repo,
                                  name="during-budget")
            self.assertTrue(row.get("ref"))
            rows = registry.records()
            self.assertEqual({r["session_id"] for r in rows}, {"before-budget", "during-budget"})
            self.assertTrue(all(r["directory_exclusion_status"] == "unknown" for r in rows))
            self.assertEqual(resolve.resolve("before-budget").record["session_id"], "before-budget")
            self.assertTrue(d.excluded(self.repo, [self.outside]))

    def test_confirmed_match_still_blocks_new_registration_with_other_invalid_root(self):
        self.cfg(directory_excluded_paths=["~typo/private", self.outside])
        row = registry.upsert("codex", self.home, "excluded", os.getpid(), self.outside)
        self.assertTrue(row["excluded"])
        self.assertFalse(os.path.exists(registry._record_path("codex", "excluded")))
        self.assertEqual(registry.raw_records(), [])

    def test_codex_thread_adoption_never_rewrites_excluded_placeholder(self):
        self.cfg(directory_excluded_paths=[self.outside])
        with mock.patch.object(registry, "_hooks_will_register", return_value=True), \
                mock.patch.object(registry, "_codex_thread_row", return_value=("private", self.outside, None)):
            self.assertIsNone(registry.adopt_codex_thread("private", os.getpid(), [self.home]))
        self.assertEqual(os.listdir(paths.path(paths.SESSIONS)), [])
        with mock.patch.object(registry, "_hooks_will_register", return_value=True), \
                mock.patch.object(registry, "_codex_thread_row", return_value=("allowed", self.repo, None)):
            self.assertIsNotNone(registry.adopt_codex_thread("allowed", os.getpid(), [self.home]))
        self.assertEqual([r["session_id"] for r in registry.raw_records()], ["allowed"])

    def test_both_open_codex_adoption_paths_skip_excluded_and_keep_allowed(self):
        from xsm import codex_daemon
        self.cfg(directory_excluded_paths=[self.outside])
        opened = [("open-private", "private", self.outside, None, 0, 0, os.getpid()),
                  ("open-allowed", "allowed", self.repo, None, 0, 0, os.getpid())]
        fresh = [self.row("fresh-private", cwd=self.outside, mcp_pid=os.getpid()),
                 self.row("fresh-allowed", mcp_pid=os.getpid())]
        with mock.patch.object(registry, "_hooks_will_register", return_value=True), \
                mock.patch.object(registry, "_open_codex_threads", return_value=opened), \
                mock.patch.object(registry, "fresh_codex_threads", return_value=fresh), \
                mock.patch.object(registry, "beacon_for", return_value=None), \
                mock.patch.object(codex_daemon, "loaded_threads", return_value=None):
            adopted = registry.adopt_open_codex()
        self.assertEqual({r["session_id"] for r in adopted}, {"open-allowed", "fresh-allowed"})
        self.assertEqual(set(os.listdir(paths.path(paths.SESSIONS))),
                         {"codex-open-allowed.json", "codex-fresh-allowed.json"})

    def test_excluded_child_cannot_inherit_parent_as_authoritative_adoption(self):
        registry.upsert("codex", self.home, "parent", os.getpid(), self.repo)
        self.cfg(directory_excluded_paths=[self.outside])
        with mock.patch.object(registry, "_hooks_will_register", return_value=True), \
                mock.patch.object(registry, "_codex_thread_row", return_value=("private", self.outside, "parent")):
            self.assertIsNone(registry.adopt_codex_thread("private-child", os.getpid(), [self.home]))
        self.assertEqual([r["session_id"] for r in registry.raw_records()], ["parent"])

    def test_all_claude_adoption_entry_points_respect_confirmed_exclusion(self):
        sid, pid = "claude-native", os.getpid()
        native = dict(sessionId=sid, pid=pid, cwd=self.outside, name="native",
                      messagingSocketPath="/tmp/%s.sock" % pid)
        file = os.path.join(self.claude, "sessions", "%s.json" % pid)
        paths.write_json(file, native)
        self.cfg(directory_excluded_paths=[self.outside])
        with mock.patch.object(registry, "self_consent", return_value=None), \
                mock.patch.object(registry, "claude_home_here", return_value=self.claude), \
                mock.patch.object(registry, "claude_homes_here", return_value=[self.claude]), \
                mock.patch.object(registry.identity, "pid_alive", return_value=True), \
                mock.patch.dict(os.environ, {"CLAUDE_CODE_SESSION_ID": sid}):
            self.assertIsNone(registry._adopt_claude(self.claude, sid, pid, self.outside, None))
            self.assertIsNone(registry.adopt_self())
            self.assertIsNone(registry.adopt_claude_process(pid))
            self.assertEqual(os.listdir(paths.path(paths.SESSIONS)), [])
            native["cwd"] = self.repo
            paths.write_json(file, native)
            self.assertIsNotNone(registry.adopt_self())
            self.assertIsNotNone(registry.adopt_claude_process(pid))
        self.assertEqual([r["session_id"] for r in registry.raw_records()], [sid])

    def test_registered_false_alone_is_never_saved_by_any_registry_adoption(self):
        from xsm import codex_daemon
        placeholder = self.row(registered=False)
        with mock.patch.object(registry, "upsert", return_value=placeholder), \
                mock.patch.object(registry, "_hooks_will_register", return_value=True), \
                mock.patch.object(registry, "_codex_thread_row", return_value=("one", self.repo, None)), \
                mock.patch.object(registry, "_open_codex_threads", return_value=[
                    ("one", "one", self.repo, None, 0, 0, os.getpid())]), \
                mock.patch.object(registry, "fresh_codex_threads", return_value=[
                    self.row("fresh", mcp_pid=os.getpid())]), \
                mock.patch.object(registry, "beacon_for", return_value=None), \
                mock.patch.object(codex_daemon, "loaded_threads", return_value=None):
            self.assertIsNone(registry.adopt_codex_thread("one", os.getpid(), [self.home]))
            self.assertEqual(registry.adopt_open_codex(), [])
            self.assertIsNone(registry._adopt_claude(self.claude, "one", os.getpid(), self.repo, None))
        self.assertEqual(os.listdir(paths.path(paths.SESSIONS)), [])

    def test_legacy_rejected_placeholders_never_become_addresses_or_callers(self):
        from xsm import resolve
        for row in (self.row("excluded-legacy", excluded=True, registered=True),
                    self.row("false-legacy", registered=False)):
            self.store(row)
            self.assertIsNone(registry._enrich(row))
            self.assertIsNone(registry.by_session("codex", row["session_id"]))
            self.assertIsNone(registry.me(session_id=row["session_id"]))
            with mock.patch.object(paths, "write_json", side_effect=AssertionError("placeholder rewrite")):
                self.assertIsNone(registry.mark_ended("codex", row["session_id"], "exit"))
            with mock.patch.object(registry, "unregistered", return_value=[]):
                self.assertFalse(resolve.resolve("codex:" + row["session_id"]).ok)
        self.assertEqual(registry.raw_records(), [])
        self.assertEqual(registry.records(), [])
        self.assertEqual(registry.cheap_records(), [])

    def test_missing_policy_uses_defaults_but_broken_existing_file_never_publishes_private(self):
        private = self.row("private-policy", cwd=self.outside)
        self.assertFalse(os.path.exists(paths.path(config.CONFIG)))
        self.assertEqual(d._settings(), config.DEFAULT_CONFIG)
        self.assertFalse(d.excluded(self.repo))
        self.assertEqual(len(self.candidates([self.row(), private])), 1)
        for contents in ('{"directory_excluded_paths":', '[]', 'null', '"not a policy"'):
            with self.subTest(contents=contents):
                with open(paths.path(config.CONFIG), "w") as stream:
                    stream.write(contents)
                with probe.quick(), mock.patch.object(d, "_read_settings", wraps=d._read_settings) as read:
                    self.assertIsNone(d._settings())
                    self.assertIsNone(d._settings())
                    self.assertEqual(read.call_count, 1)
                    self.assertEqual(d.exclusion_status(self.repo), "unknown")
                    self.assertTrue(d.excluded(self.repo))
                    found = self.discover([self.row(), private])
                    self.assertEqual(found["status"], "unknown")
                    self.assertEqual(found["candidates"], [])
                    with self.assertRaises(ValueError):
                        self.publish(private)
                self.assertFalse(os.path.exists(paths.path(d.PUBLICATIONS)))
        # P09: broken existing policy cannot silently reopen same-repo scope.
        with open(paths.path(config.CONFIG), "w") as stream:
            stream.write('{"broken":')
        self.assertFalse(config.load()["same_repo_scope"])
        self.assertFalse(config.policy_health()["can_grant"])


if __name__ == "__main__":
    unittest.main()
