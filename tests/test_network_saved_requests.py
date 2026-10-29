"""Recovery of saved outgoing data with networking off and after team changes."""
import hashlib
import json
from pathlib import Path
import stat
import unittest
from unittest import mock

from tests import test_network_application as application


class SavedNetworkRequestTests(unittest.TestCase):
    def setUp(self):
        self.case = application.NetworkApplicationTests(
            "test_git_discover_resolve_task_native_file_consume_reverse_reply_and_question_correlation")
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()
        self.case.map_repositories()

    def test_export_and_archive_remain_owner_bound_without_a_running_service(self):
        from xsm import network, network_messages, network_recovery
        case = self.case
        request_id = "saved-outgoing"
        case.send(request_id=request_id, body="immutable outgoing original\n")
        case.a.stop()
        case.b.stop()
        with case.local(case.a), mock.patch.object(network, "call", side_effect=AssertionError("no network RPC")):
            rows = network_recovery.requests(case.actor_a)
            self.assertEqual([r["id"] for r in rows], [request_id])
            other = case.actor(case.a, "another-local-owner", cwd=case.actor_a["cwd"])
            self.assertEqual(network_recovery.requests(other), [])
            with self.assertRaises(ValueError):
                network_recovery.export(other, request_id, case.root / "wrong-owner.json")
            output = case.root / "frozen-export.json"
            exported = network_recovery.export(case.actor_a, request_id, output)
            raw = output.read_bytes()
            packet = json.loads(raw)["packet"]
            self.assertEqual(packet["body"], "immutable outgoing original\n")
            self.assertEqual(exported["sha256"], hashlib.sha256(raw).hexdigest())
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.assertNotIn(case.actor_a["home"], raw.decode())
            with self.assertRaises(FileExistsError):
                network_recovery.export(case.actor_a, request_id, output)
            self.assertEqual(output.read_bytes(), raw)
            self.assertFalse(network_recovery.archive(case.actor_a, request_id)["remote_execution_cancelled"])
            self.assertEqual(network_recovery.requests(case.actor_a), [])
            self.assertEqual([r["id"] for r in network_recovery.requests(case.actor_a, True)], [request_id])
            gateway, record = network_recovery._original(case.actor_a, request_id)
            self.assertEqual(record["packet"], packet)
            with self.assertRaisesRegex(network_messages.GatewayError, "request-archived"):
                gateway.prepare(case.actor_a, record["packet"]["receiver"], record["packet"]["body"],
                                request_id=request_id, kind="task", wake=False)

    def test_old_team_original_can_be_exported_after_a_real_network_switch(self):
        from xsm import network_recovery
        case = self.case
        request_id = "old-network-original"
        case.send(request_id=request_id, body="original from the previous team")
        founder = case.node("new-team")
        fresh = founder.cli("init", "new-team")
        invitation = founder.cli("invite")
        ticket = json.loads(Path(invitation["ticket_file"]).read_text())
        case.secrets.append(ticket["secret"])
        switched = case.a.cli("join", "--ticket-file", invitation["ticket_file"])
        self.assertEqual(switched["network"]["network_id"], fresh["network"]["network_id"])
        self.assertNotEqual(switched["network"]["network_id"], case.network_id)
        case.a.stop()
        with case.local(case.a):
            rows = network_recovery.requests(case.actor_a)
            self.assertEqual(rows[0]["network_id"], case.network_id)
            output = case.root / "old-team-export.json"
            network_recovery.export(case.actor_a, request_id, output)
            self.assertEqual(json.loads(output.read_text())["packet"]["network_id"], case.network_id)

    def test_archiving_does_not_cancel_or_discard_an_exact_late_reply(self):
        from xsm import network_recovery
        case = self.case
        request_id = "archived-with-late-reply"
        case.send(request_id=request_id)
        with case.local(case.a):
            network_recovery.archive(case.actor_a, request_id)
        case.consume(case.b, case.actor_b, request_id)
        reverse = case.target(case.a, case.actor_a)
        reply = case.send(case.b, case.actor_b, reverse, "late-archived-answer", kind="reply",
                          reply_to=request_id, outcome="succeeded", body="actual late result")
        self.assertTrue(reply["delivery"]["stored"])
        case.consume(case.a, case.actor_a, "late-archived-answer")
        with case.local(case.a):
            gateway, original = network_recovery._original(case.actor_a, request_id)
            self.assertIsNotNone(original["archived_at"])
            result = gateway.status(case.a.identity, request_id, original["packet"]["sender"])
            self.assertEqual(result["final_reply"]["packet"]["body"], "actual late result")
            self.assertEqual(network_recovery.requests(case.actor_a), [r for r in
                network_recovery.requests(case.actor_a, True) if r["id"] != request_id])

    def test_public_cli_uses_sure_caller_and_never_starts_service_for_recovery(self):
        from xsm import cli, context, network, registry
        import contextlib
        import io
        case = self.case
        request_id = "cli-saved-original"
        case.send(request_id=request_id)
        case.a.stop()
        exact = context.of_record(case.actor_a, context.BASIS_SESSION)
        with case.local(case.a), mock.patch.object(registry, "me_context", return_value=(case.actor_a, exact)), \
                mock.patch.object(network, "start", side_effect=AssertionError("no service startup")):
            for args in (["network", "requests"], ["network", "export", request_id, "--output", str(case.root / "cli-export.json")],
                         ["network", "archive", request_id]):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(cli.main(args), 0)
                value = json.loads(output.getvalue())
                self.assertNotIn("body", value)
        provisional = context.of_record(case.actor_a, context.BASIS_NEIGHBOR)
        with case.local(case.a), mock.patch.object(registry, "me_context", return_value=(case.actor_a, provisional)):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(cli.main(["network", "requests"]), 4)
            self.assertEqual(json.loads(output.getvalue())["code"], "caller-unverified")
