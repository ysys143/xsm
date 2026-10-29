"""Exact conversation permission boundaries, independent of discovery."""
import os
import tempfile
import unittest
from unittest.mock import patch

from xsm import collaboration, paths


class CollaborationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = patch.object(paths, "HOME", self.temp.name)
        self.home.start()
        self.addCleanup(self.home.stop)
        self.a = dict(runtime="codex", home=self.temp.name + "/codex",
                      session_id="a", name="same", cwd="/repo/a", ref="aaaaaa")
        self.b = dict(runtime="claude", home=self.temp.name + "/claude",
                      session_id="b", name="same", cwd="/repo/b", ref="bbbbbb")

    def test_proposal_does_not_grant_or_write(self):
        proposal = collaboration.propose(self.a, self.b)
        self.assertEqual(proposal, collaboration.propose(self.b, self.a))
        self.assertIsNone(collaboration.scope_for(self.a, self.b))
        self.assertEqual(os.listdir(self.temp.name), [])

    def test_create_persists_bidirectional_verbatim_evidence(self):
        verdict = " a1이랑 붙어서 일하자\n"
        record = collaboration.create(self.a, self.b, verdict)
        self.assertEqual(record["verdict"], verdict)
        self.assertEqual(collaboration.scope_for(self.a, self.b), record)
        self.assertEqual(collaboration.scope_for(self.b, self.a), record)
        self.assertEqual(paths.read_json(paths.path(
            collaboration.DIRECTORY, record["id"] + ".json")), record)
        self.assertEqual(os.stat(paths.path(collaboration.DIRECTORY,
                                           record["id"] + ".json")).st_mode & 0o777, 0o600)
        self.assertEqual(collaboration.create(self.b, self.a, "later"), record)

    def test_same_name_new_conversation_other_home_and_runtime_are_denied(self):
        collaboration.create(self.a, self.b, "selected b")
        for field, value in (("session_id", "new"), ("home", "/different-home"),
                             ("runtime", "codex")):
            with self.subTest(field=field):
                other = dict(self.b, **{field: value})
                self.assertIsNone(collaboration.scope_for(self.a, other))
                self.assertIsNone(collaboration.scope_for(other, self.a))
        self.assertIsNone(collaboration.scope_for(dict(self.a, session_id="new"), self.b))

    def test_resume_ignores_execution_and_display_fields(self):
        record = collaboration.create(self.a, self.b, "selected")
        resumed = dict(self.b, pid=999, start=123, name="renamed", ref="ffffff",
                       cwd="/different-folder", home=self.b["home"] + "/../claude")
        self.assertEqual(collaboration.scope_for(self.a, resumed), record)

    def test_drop_both_directions_preserves_other_pairs_and_evidence(self):
        c = dict(self.b, session_id="c")
        record = collaboration.create(self.a, self.b, "selected b")
        other = collaboration.create(self.a, c, "selected c")
        self.assertTrue(collaboration.drop(self.b, self.a))
        self.assertFalse(collaboration.drop(self.a, self.b))
        self.assertIsNone(collaboration.scope_for(self.a, self.b))
        self.assertIsNone(collaboration.scope_for(self.b, self.a))
        self.assertEqual(collaboration.scope_for(self.a, c), other)
        revoked = paths.read_json(paths.path(collaboration.DIRECTORY, record["id"] + ".json"))
        self.assertFalse(revoked["active"])
        self.assertEqual(revoked["verdict"], "selected b")
        self.assertIn("revoked_at", revoked)
        self.assertEqual(collaboration.create(self.a, self.b, "fresh selection")["verdict"],
                         "fresh selection")

    def test_discovery_and_permission_are_independent(self):
        public = dict(self.b, published=True, discovery_basis=["explicit", "same_repository"],
                      parent_session_id="a")
        self.assertIsNone(collaboration.scope_for(self.a, public))
        record = collaboration.create(self.a, public, "selected")
        private = dict(public, published=False, discovery_basis=[])
        self.assertEqual(collaboration.scope_for(self.a, private), record)
        sibling = dict(public, session_id="sibling")
        self.assertIsNone(collaboration.scope_for(self.a, sibling))
        self.assertTrue(collaboration.drop(self.a, public))
        self.assertTrue(public["published"])
        self.assertIsNone(collaboration.scope_for(self.a, public))

    def test_missing_identity_and_empty_verdict_fail_closed(self):
        for field in ("runtime", "home", "session_id"):
            for value in (None, "", 42):
                bad = dict(self.b, **{field: value})
                self.assertIsNone(collaboration.scope_for(self.a, bad))
                with self.assertRaises(ValueError):
                    collaboration.create(self.a, bad, "selected")
        for verdict in (None, "", "  ", True):
            with self.assertRaises(ValueError):
                collaboration.create(self.a, self.b, verdict)
        with self.assertRaises(ValueError):
            collaboration.create(self.a, self.a, "selected")
        self.assertEqual(os.listdir(self.temp.name), [])

    def test_corrupt_or_mismatched_record_cannot_grant(self):
        record = collaboration.create(self.a, self.b, "selected")
        filename = paths.path(collaboration.DIRECTORY, record["id"] + ".json")
        for change in ({"endpoints": []}, {"verdict": ""}, {"active": "true"},
                       {"id": "other"}, {"kind": "discovery"}):
            paths.write_json(filename, dict(record, **change))
            self.assertIsNone(collaboration.scope_for(self.a, self.b))
        with open(filename, "w") as fh:
            fh.write("{")
        self.assertIsNone(collaboration.scope_for(self.a, self.b))


if __name__ == "__main__":
    unittest.main()
