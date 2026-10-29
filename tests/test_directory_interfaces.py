"""Publication is explicit; CLI/MCP discovery targets remain exact and scoped."""
import contextlib
import io
import json
import os
from unittest import mock
from tests.test_xsm import TempState


class DirectoryInterfacesTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import context, registry
        home = os.path.join(self.tmp, "codex")
        os.makedirs(home)
        self.home = home
        self.rows = []
        for sid in ("a1", "a2", "a3"):
            folder = os.path.join(self.tmp, sid)
            os.makedirs(folder)
            self.rows.append(registry.upsert("codex", home, sid, os.getpid(), folder, name=sid))
        self.viewer, self.me, self.neighbor = self.rows
        self.identity = context.of_record(self.me, context.BASIS_SESSION)
        for patch in (mock.patch.object(registry, "me", return_value=self.me),
                      mock.patch.object(registry, "last_identity", return_value=self.identity)):
            patch.start();self.addCleanup(patch.stop)

    def cli(self, *args):
        from xsm import cli
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(args))
        return code, json.loads(out.getvalue())

    def publish_through_user_instruction(self):
        from xsm import consent, paths
        consent.record(self.me, {"hook_event_name": "UserPromptSubmit",
                                "prompt": "이 세션은 xsm에서 찾을 수 있게 공개해놔"})
        code, shown = self.cli("publish")
        self.assertEqual(code, 2)
        self.assertEqual(shown["status"], "selection-required")
        filename = consent.pending_files(self.me["ref"])[0]
        entry = paths.read_json(filename)
        entry["shown_t"] -= consent.SHOW_DELAY + 1
        paths.write_json(filename, entry)
        code, published = self.cli("publish")
        self.assertEqual(code, 0)
        self.assertTrue(published["visible"])

    def test_publication_discovery_and_withdrawal_do_not_grant_folder_communication(self):
        from xsm import config, directory, resolve
        self.assertEqual(directory.discover(self.viewer)["candidates"], [])
        before = config.load()
        self.publish_through_user_instruction()
        found = directory.discover(self.viewer)["candidates"]
        self.assertEqual(len(found), 1)
        self.assertIn("published", found[0]["discovery_basis"])
        self.assertEqual(config.load(), before)
        self.assertIsNone(config.scope_for(self.viewer, self.me)[0])
        exact = resolve.resolve(found[0]["target"], caller=self.viewer)
        self.assertTrue(exact.ok, exact.reason)
        self.assertEqual(exact.record["session_id"], self.me["session_id"])
        self.assertEqual(self.cli("publish", "--off")[0], 0)
        self.assertEqual(directory.discover(self.viewer)["candidates"], [])
        self.assertFalse(resolve.resolve(found[0]["target"], caller=self.viewer).ok)
        self.assertEqual(config.load(), before)

    def test_mcp_discovery_contract_uses_the_same_candidates_and_no_absolute_home(self):
        from xsm import directory, mcp
        self.publish_through_user_instruction()
        server = mcp.Server(io.StringIO(), io.StringIO())
        server.session = lambda: self.viewer
        result = json.loads(server.call("xsm_discover", {}))
        expected = directory.discover(self.viewer)["candidates"]
        self.assertEqual([r["id"] for r in result["candidates"]], [r["id"] for r in expected])
        self.assertNotIn(os.path.realpath(self.home), json.dumps(result))
        self.assertEqual(result["candidates"][0]["handle"]["session_id"], self.me["session_id"])
        self.assertFalse(result["candidates"][0]["is_self"])
        own = directory.discover(self.me)["candidates"]
        self.assertTrue(next(r for r in own if r["handle"]["session_id"] == self.me["session_id"])["is_self"])
