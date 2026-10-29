"""P2P integration at the broker boundary; no service, native wake or real peer.

Consent, immutable files, question indexing and canonical ledgers run normally.
The RPC mock stands for an authenticated broker, never for a user verdict.
"""
import copy
import contextlib
import hashlib
import io
import json
import os
from unittest import mock

from tests.test_xsm import TempState


class NetworkInterfacesTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import context, network_identity, registry
        os.mkdir(self.tmp + "/profile")
        self.sender = registry.upsert("codex", self.tmp + "/profile", "sender",
                                      os.getpid(), self.tmp, name="sender")
        self.call = context.of_record(self.sender, context.BASIS_SESSION)
        self.handle = dict(machine="a" * 64, runtime="codex", home_id="b" * 64,
                           session_id="remote-thread", generation="c" * 64)
        self.address = network_identity.target(self.handle)
        self.target = dict(self.handle, handle=dict(self.handle), name="peer",
                           machine_name="remote-device", alias="remote-device",
                           ref=self.address, target=self.address, remote=True,
                           registered=True, state="live")
        self.scope = "network:fixture-network"
        self.candidate_id = hashlib.sha256(json.dumps(self.handle, sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()
        self.candidate = "candidate:" + self.candidate_id

    def resolved(self, scope=None, basis=None):
        return {"target": copy.deepcopy(self.target), "scope": scope, "scope_basis": basis}

    def test_resolve_keeps_opaque_identity_generation_and_broker_scope(self):
        from xsm import network, registry, resolve
        with mock.patch.object(network, "call", return_value=self.resolved(self.scope, "same-repository")) as rpc, \
                mock.patch.object(registry, "me", side_effect=AssertionError("explicit caller lost")), \
                mock.patch.object(registry, "records", side_effect=AssertionError("remote is not local")):
            found = resolve.resolve(self.address, caller=self.sender)
        self.assertTrue(found.ok, found.reason)
        self.assertEqual(found.scope, self.scope)
        self.assertEqual(found.scope_basis, "same-repository")
        self.assertEqual(found.record["handle"], self.handle)
        self.assertEqual(found.record["generation"], self.handle["generation"])
        self.assertEqual(found.record["ref"], self.address)
        self.assertNotIn("home", found.record)
        rpc.assert_called_once_with({"op": "resolve", "caller": self.sender, "target": self.address})

    def test_resolve_without_explicit_caller_uses_actual_local_record(self):
        from xsm import network, registry, resolve
        with mock.patch.object(registry, "me", return_value=self.sender), \
                mock.patch.object(network, "call", return_value=self.resolved()) as rpc:
            self.assertTrue(resolve.resolve(self.address).ok)
        self.assertEqual(rpc.call_args.args[0]["caller"], self.sender)

    def test_malformed_network_addresses_never_fall_through_to_ssh_or_local_names(self):
        from xsm import network, remote, resolve, send
        with mock.patch.object(network, "call") as rpc, \
                mock.patch.object(remote, "split_target", side_effect=AssertionError("SSH fallback")):
            for address in ("net:bad", self.address + "@ssh-peer", self.address + ":extra",
                            self.address.replace("a" * 64, "A" * 64)):
                with self.subTest(address=address):
                    self.assertFalse(resolve.resolve(address, caller=self.sender).ok)
                    self.assertEqual(send.send(address, "body", sender=self.sender).status, "refused")
        rpc.assert_not_called()

    def test_resolution_rejects_mixed_homes_wrong_endpoints_and_stale_handle_shapes(self):
        from xsm import network, resolve
        changes = [dict(home=self.tmp), dict(machine="d" * 64), dict(generation=None),
                   dict(handle=dict(self.handle, home=self.tmp)),
                   dict(handle=dict(self.handle, generation="d" * 64))]
        for change in changes:
            with self.subTest(change=change), mock.patch.object(network, "call", return_value={
                    "target": dict(self.target, **change), "scope": self.scope}):
                self.assertFalse(resolve.resolve(self.address, caller=self.sender).ok)
        for answer in (None, {"target": self.target, "scope": "repo:claimed"},
                       {"target": self.target, "scope": self.scope, "scope_basis": "claimed"}):
            with self.subTest(answer=answer), mock.patch.object(network, "call", return_value=answer):
                self.assertFalse(resolve.resolve(self.address, caller=self.sender).ok)

    def test_network_failure_and_unregistered_caller_do_not_create_local_fallbacks(self):
        from xsm import network, registry, resolve
        with mock.patch.object(network, "call", side_effect=network.NetworkError("target-unavailable")):
            found = resolve.resolve(self.address, caller=self.sender)
            self.assertFalse(found.ok)
            self.assertEqual(found.reason, "target-unavailable")
        with mock.patch.object(registry, "me", return_value=None), mock.patch.object(network, "call") as rpc:
            self.assertFalse(resolve.resolve(self.address).ok)
        rpc.assert_not_called()

    def test_collaboration_remote_pair_is_exact_bidirectional_and_resume_stable(self):
        from xsm import collaboration
        record = collaboration.create(self.sender, self.target, "peer이랑 붙어서 일하자")
        self.assertEqual(collaboration.scope_for(self.target, self.sender), record)
        resumed = dict(self.target, generation="d" * 64, name="renamed")
        self.assertEqual(collaboration.scope_for(self.sender, resumed), record)
        for field, value in (("machine", "d" * 64), ("home_id", "d" * 64),
                             ("session_id", "other"), ("runtime", "claude")):
            self.assertIsNone(collaboration.scope_for(self.sender, dict(self.target, **{field: value})))
        for change in (dict(home=self.tmp), dict(home_id="invalid"), dict(machine=None)):
            self.assertIsNone(collaboration.scope_for(self.sender, dict(self.target, **change)))
        self.assertNotIn("home", collaboration._identity(self.target))
        self.assertEqual(set(collaboration._identity(self.sender)), {"home", "runtime", "session_id"})

    def test_send_uses_broker_before_ssh_and_does_not_consult_local_remote_scope(self):
        from xsm import adapters, config, network, remote, send
        with mock.patch.object(network, "call", return_value={
                "status": "queued", "id": "net-send", "target": self.target, "reason": "stored remotely"}) as rpc, \
                mock.patch.object(config, "scope_for", side_effect=AssertionError("local scope on remote")), \
                mock.patch.object(remote, "split_target", side_effect=AssertionError("SSH split")), \
                mock.patch.object(adapters, "to_codex", side_effect=AssertionError("local native queue")), \
                mock.patch.object(network, "start", side_effect=AssertionError("implicit service start")):
            result = send.send(self.address, "exact body", sender=self.sender, kind="reply",
                               reply_to="question", outcome="succeeded", msg_id="net-send", wake=False)
        self.assertEqual(result.status, "sent-unconfirmed")
        self.assertEqual(result.msg_id, "net-send")
        rpc.assert_called_once_with({"op": "send", "caller": self.sender, "target": self.address,
                                    "body": "exact body", "id": "net-send", "kind": "reply",
                                    "reply_to": "question", "outcome": "succeeded", "priority": "next",
                                    "wake": False, "attachments": [], "file_packet": None})

    def test_send_response_loss_keeps_request_id_and_does_not_replay(self):
        from xsm import network, send
        with mock.patch.object(network, "call", side_effect=network.NetworkError(
                "service-unavailable-or-response-unknown")) as rpc:
            result = send.send(self.address, "body", sender=self.sender)
        self.assertEqual(result.status, "unknown")
        self.assertTrue(result.msg_id)
        self.assertEqual(result.msg_id, rpc.call_args.args[0]["id"])
        self.assertEqual(rpc.call_count, 1)
        with mock.patch.object(network, "call", side_effect=network.NetworkError("selection-required")):
            refused = send.send(self.address, "body", sender=self.sender)
        self.assertEqual(refused.status, "refused")

    def test_remote_resend_requires_same_existing_sender_target_and_canonical_request(self):
        from xsm import ledger, network, send
        with mock.patch.object(network, "call") as rpc:
            self.assertEqual(send.send(self.address, "body", sender=self.sender,
                                       msg_id="unknown-resend", resend=True).status, "refused")
        rpc.assert_not_called()
        ledger.queued("known-resend", self.sender, self.target, self.scope, "task", "body")
        with mock.patch.object(network, "call", return_value={"status": "sent-unconfirmed", "id": "known-resend"}) as rpc:
            result = send.send(self.address, "body", sender=self.sender, kind="task",
                               msg_id="known-resend", resend=True)
        self.assertEqual(result.status, "sent-unconfirmed", result.reason)
        self.assertEqual(rpc.call_count, 1)
        with mock.patch.object(network, "call") as rpc:
            self.assertEqual(send.send(self.address, "changed", sender=self.sender, kind="task",
                                       msg_id="known-resend", resend=True).status, "refused")
        rpc.assert_not_called()

    def test_remote_materials_negotiate_observed_files_and_send_the_same_frozen_packet(self):
        from xsm import materials, network, registry, send
        calls = []
        def broker(request):
            calls.append(request)
            self.assertEqual(request["caller"], self.sender)
            self.assertEqual(request["target"], self.address)
            if request["op"] == "resolve":
                return self.resolved(self.scope, "selected")
            if request["op"] == "capabilities":
                return {"capabilities": {"status": "observed", "version": 1}}
            return {"status": "sent-unconfirmed", "id": request["id"], "target": self.target}
        with mock.patch.object(network, "call", side_effect=broker), \
                mock.patch.object(registry, "file_capability", side_effect=AssertionError("local file observation")):
            prepared = materials.prepare(self.sender, self.address, "body", "file-request",
                                         [{"name": "design.md", "text": "frozen copy"}], call=self.call)
            result = send.send(self.address, prepared["body"], sender=self.sender,
                               msg_id="file-request", wake=False, call=self.call,
                               attachments=prepared["attachments"], file_packet=prepared["file_packet"],
                               file_limits=prepared["file_limits"])
        self.assertEqual(prepared["mode"], "files")
        self.assertEqual(result.status, "sent-unconfirmed")
        self.assertEqual([c["op"] for c in calls], ["resolve", "capabilities", "send"])
        self.assertEqual(calls[-1]["file_packet"], prepared["file_packet"])
        self.assertEqual(calls[-1]["attachments"], prepared["attachments"])

    def test_unknown_declared_or_disconnected_files_never_silently_claim_support(self):
        from xsm import files, materials, network
        for index, capability in enumerate(({"status": "unknown", "version": None},
                                             {"status": "declared", "version": 1},
                                             {"status": "observed", "version": 2}, None, "disconnected")):
            request_id = "unknown-files-%d" % index
            def broker(request):
                if request["op"] == "resolve":
                    return self.resolved()
                if capability == "disconnected":
                    raise network.NetworkError("service-unavailable-or-response-unknown")
                return {"capabilities": capability}
            with self.subTest(capability=capability), mock.patch.object(network, "call", side_effect=broker):
                with self.assertRaises(files.FileError) as caught:
                    materials.prepare(self.sender, self.address, "body", request_id,
                                      [{"name": "note.txt", "text": "saved copy"}], call=self.call)
                failure = materials.failure(caught.exception)
                self.assertEqual(failure["code"], "files-unsupported-or-unknown")
                self.assertTrue(failure["manifest_id"])
                self.assertFalse(failure["body_sent"])
                fallback = materials.prepare(self.sender, self.address, "body", request_id,
                                             manifest_id=failure["manifest_id"], fallback="inline", call=self.call)
                self.assertEqual(fallback["mode"], "inline")
                self.assertEqual(fallback["attachments"], [])
                self.assertIn("saved copy", fallback["body"])

    def test_provisional_identity_cannot_select_publish_prepare_or_dispatch_files(self):
        from xsm import connect, context, files, materials, network, send
        weak = context.of_record(self.sender, context.BASIS_NEIGHBOR)
        with mock.patch.object(network, "call") as rpc:
            self.assertEqual(connect.select(self.sender, self.target, call=weak)["status"], "refused")
            self.assertEqual(connect.publication(self.sender, call=weak)["status"], "refused")
            with self.assertRaises(files.FileError):
                materials.prepare(self.sender, self.address, "body", "weak-file",
                                  [{"name": "a", "text": "copy"}], call=weak)
            prepared = files.prepare_inline(self.sender, "weak-file", "body", [{"name": "a", "text": "copy"}],
                                            limits=files.product_limits())
            result = send.send(self.address, "body", sender=self.sender, call=weak, msg_id="weak-file",
                               attachments=[files.reference(prepared)], file_packet={"manifest": prepared})
            self.assertEqual(result.status, "refused")
            self.assertIn("exact caller", result.reason)
        rpc.assert_not_called()

    def _record_selection(self):
        from xsm import consent
        consent.record(self.sender, {"hook_event_name": "UserPromptSubmit", "prompt": "peer이랑 붙어서 일하자"})

    def _age_selection(self):
        from xsm import consent, paths
        pending = consent.pending_files(self.sender["ref"])
        self.assertEqual(len(pending), 1, pending)
        entry = paths.read_json(pending[0])
        entry["shown_t"] -= consent.SHOW_DELAY + 1
        paths.write_json(pending[0], entry)
        return entry

    def test_remote_selection_uses_real_consent_and_pair_before_broker_attestation(self):
        from xsm import collaboration, config, connect, consent, network, registry
        selected = []
        def broker(request):
            self.assertEqual(request["caller"], self.sender)
            if request["op"] == "resolve":
                return self.resolved(self.scope if selected else None, "selected" if selected else None)
            self.assertEqual(request["op"], "selection")
            self.assertIsNotNone(collaboration.scope_for(self.sender, self.target))
            selected.append(request)
            return {"status": "selected", "target": self.target}
        before = config.load()
        self._record_selection()
        with mock.patch.object(network, "call", side_effect=broker), \
                mock.patch.object(registry, "records", side_effect=AssertionError("local target lookup")), \
                mock.patch.object(config, "scope_for", side_effect=AssertionError("local remote scope")):
            shown = connect.select(self.sender, self.target, call=self.call)
            self.assertEqual(shown["status"], "selection-required", shown)
            self.assertIn("peer이랑 붙어서 일하자", shown["reason"])
            self.assertEqual(selected, [])
            self.assertIsNone(collaboration.scope_for(self.sender, self.target))
            entry = self._age_selection()
            self.assertEqual(entry["binding"]["generation"], self.handle["generation"])
            permitted = connect.select(self.sender, self.target, call=self.call)
            self.assertEqual(permitted["status"], "permitted", permitted)
            self.assertEqual(permitted["scope"], self.scope)
            self.assertEqual(permitted["handshake"], "not-started")
            self.assertEqual(connect.select(self.sender, self.target, call=self.call)["scope"], self.scope)
        self.assertEqual(len(selected), 1)
        self.assertEqual(collaboration.scope_for(self.sender, self.target)["verdict"], "peer이랑 붙어서 일하자")
        self.assertEqual(consent.pending_files(self.sender["ref"]), [])
        self.assertEqual(config.load(), before)

    def test_changed_generation_during_consent_never_creates_pair_or_selection(self):
        from xsm import collaboration, connect, network
        self._record_selection()
        with mock.patch.object(network, "call", return_value=self.resolved()):
            self.assertEqual(connect.select(self.sender, self.target, call=self.call)["status"], "selection-required")
        self._age_selection()
        changed = self.resolved()
        changed["target"]["generation"] = "d" * 64
        changed["target"]["handle"]["generation"] = "d" * 64
        with mock.patch.object(network, "call", side_effect=[self.resolved(), changed]) as rpc:
            result = connect.select(self.sender, self.target, call=self.call)
        self.assertEqual(result["status"], "refused", result)
        self.assertIn("generation changed", result["reason"])
        self.assertIsNone(collaboration.scope_for(self.sender, self.target))
        self.assertEqual([c.args[0]["op"] for c in rpc.call_args_list], ["resolve", "resolve"])

    def test_remote_selection_rejects_stopped_observation_before_consent(self):
        from xsm import collaboration, connect, consent, network
        for state in ("ended", {"value": "stale", "source": "registry:liveness", "observed_at": 0}):
            answer = self.resolved()
            answer["target"]["state"] = state
            with self.subTest(state=state), mock.patch.object(network, "call", return_value=answer):
                result = connect.select(self.sender, self.target, call=self.call)
            self.assertEqual(result["status"], "refused", result)
            self.assertIsNone(collaboration.scope_for(self.sender, self.target))
            self.assertEqual(consent.pending_files(self.sender["ref"]), [])

    def test_consent_pair_can_resume_selection_after_broker_response_loss(self):
        from xsm import collaboration, connect, network
        collaboration.create(self.sender, self.target, "peer이랑 붙어서 일하자")
        with mock.patch.object(network, "call", side_effect=[self.resolved(),
                network.NetworkError("service-unavailable-or-response-unknown")]):
            first = connect.select(self.sender, self.target, call=self.call)
        self.assertEqual(first["status"], "refused")
        with mock.patch.object(network, "call", side_effect=[self.resolved(),
                {"status": "selected", "target": self.target}, self.resolved(self.scope, "selected")]):
            resumed = connect.select(self.sender, self.target, call=self.call)
        self.assertEqual(resumed["status"], "permitted", resumed)
        self.assertEqual(resumed["scope"], self.scope)

    def test_remote_ask_keeps_caller_address_and_canonical_ledger_then_correlates_reply(self):
        from xsm import config, envelope, ledger, network, paths, questions, remote
        sends = []
        def broker(request):
            self.assertEqual(request["caller"], self.sender)
            self.assertEqual(request["target"], self.address)
            if request["op"] == "resolve":
                return self.resolved(self.scope, "selected")
            self.assertEqual(request["op"], "send")
            sends.append(request)
            expected = envelope.request_identity(request["id"], self.sender, self.target, request["body"],
                kind="task", scope=self.scope, priority="next")
            self.assertEqual(ledger.status(request["id"])["digest"], envelope.request_digest(expected))
            return {"status": "sent-unconfirmed", "id": request["id"], "target": self.target}
        with mock.patch.object(network, "call", side_effect=broker), \
                mock.patch.object(config, "scope_for", side_effect=AssertionError("local question scope")), \
                mock.patch.object(remote, "split_target", side_effect=AssertionError("SSH question target")):
            result = questions.ask(self.sender, self.address, "검토해 주세요", request_id="remote-question", purpose="handshake")
            self.assertEqual(result["status"], "pending", result)
            self.assertEqual(result["send_evidence"]["status"], "sent-unconfirmed", result)
            self.assertEqual(questions.ask(self.sender, self.address, "검토해 주세요",
                                         request_id="remote-question", purpose="handshake")["status"], "pending")
            changed = questions.ask(self.sender, self.address, "different body", request_id="remote-question", purpose="handshake")
        self.assertEqual(changed["status"], "refused")
        self.assertEqual(len(sends), 1)
        saved = paths.read_json(paths.path("questions", "remote-question.json"))
        self.assertNotIn("home", saved["target"])
        self.assertEqual(saved["sender"]["home"], self.sender["home"])
        self.assertEqual(saved["target"]["machine"], self.handle["machine"])
        listed = questions.list_requests(self.sender)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["target"]["machine"], self.handle["machine"])
        self.assertFalse(questions.record_reply(self.sender, dict(self.target, machine="d" * 64),
            {"kind": "reply", "id": "wrong-reply", "reply-to": "remote-question"}, "forged"))
        self.assertTrue(questions.record_reply(self.sender, self.target,
            {"kind": "reply", "id": "remote-reply", "reply-to": "remote-question", "outcome": "succeeded"}, "검토 완료"))
        final = questions.status(self.sender, "remote-question")
        self.assertEqual(final["handshake"], "completed")
        self.assertEqual(final["replies"][0]["body"], "검토 완료")
        self.assertNotIn(self.sender["home"], json.dumps(final))

    def test_remote_ask_without_broker_scope_does_not_claim_send_or_use_local_grants(self):
        from xsm import config, ledger, network, questions
        with mock.patch.object(network, "call", return_value=self.resolved()) as rpc, \
                mock.patch.object(config, "scope_for", side_effect=AssertionError("local grant")):
            result = questions.ask(self.sender, self.address, "body", request_id="not-selected")
        self.assertEqual(result["status"], "selection-required", result)
        self.assertEqual(ledger.status("not-selected"), {})
        self.assertEqual(rpc.call_count, 1)

    def test_local_and_ssh_send_and_local_resolution_do_not_contact_network(self):
        from xsm import adapters, network, registry, remote, resolve, send
        local = registry.upsert("codex", self.sender["home"], "neighbor", os.getpid(), self.tmp, name="neighbor")
        with mock.patch.object(network, "call", side_effect=AssertionError("local depends on network")), \
                mock.patch.object(network, "start", side_effect=AssertionError("service started")), \
                mock.patch.object(adapters, "to_codex", return_value=None), \
                mock.patch.object(remote, "send", return_value={"status": "queued", "id": "ssh-send"}) as ssh, \
                mock.patch.object(remote, "split_target", wraps=remote.split_target) as split:
            self.assertTrue(resolve.resolve("codex:neighbor").ok)
            self.assertEqual(send.send("codex:neighbor", "local", sender=self.sender).status, "sent-unconfirmed")
            with mock.patch.object(remote, "split_target", return_value=("codex:ssh-peer", "legacy-machine")):
                self.assertEqual(send.send("codex:ssh-peer@legacy-machine", "ssh", sender=self.sender).status, "sent-unconfirmed")
            self.assertEqual(ssh.call_count, 1)
            self.assertEqual(split.call_count, 1)
        self.assertEqual(local["home"], self.sender["home"])

    def test_cli_network_status_recovers_only_actual_consumer_ack(self):
        from xsm import cli, ledger, network, registry, remote
        ledger.queued("network-status", self.sender, self.target, self.scope, "note", "body")
        for acknowledged in (False, True):
            delivery = {"status": "acknowledged" if acknowledged else "stored",
                        "stored": True, "acknowledged": acknowledged}
            out = io.StringIO()
            with self.subTest(acknowledged=acknowledged), \
                    mock.patch.object(registry, "me", return_value=self.sender), \
                    mock.patch.object(network, "call", return_value=delivery) as rpc, \
                    mock.patch.object(network, "start", side_effect=AssertionError("implicit service start")), \
                    mock.patch.object(remote, "reconcile", side_effect=AssertionError("SSH status")), \
                    contextlib.redirect_stdout(out):
                code = cli.main(["status", "network-status", "--json"])
            self.assertEqual(code, 0 if acknowledged else 3, out.getvalue())
            state = json.loads(out.getvalue())
            self.assertEqual(state["network_delivery"], delivery)
            self.assertEqual(rpc.call_args.args[0], {"op": "message-status", "caller": self.sender,
                                                    "target": self.address, "id": "network-status"})
            self.assertEqual(ledger.evidence_of("network-status")["steps"].get("hook_taken", {}).get("ok") is True,
                             acknowledged)

    def test_mcp_question_status_recovers_remote_delivery_without_inventing_a_reply(self):
        from xsm import ledger, mcp, network, questions
        with mock.patch.object(network, "call", side_effect=[self.resolved(self.scope, "selected"),
                {"status": "sent-unconfirmed", "id": "mcp-question", "target": self.target}]):
            self.assertEqual(questions.ask(self.sender, self.address, "body", request_id="mcp-question")["status"], "pending")
        server = mcp.Server(io.StringIO(), io.StringIO())
        server.session = lambda: self.sender
        delivery = {"status": "acknowledged", "stored": True, "acknowledged": True}
        with mock.patch.object(network, "call", return_value=delivery) as rpc:
            result = json.loads(server.call("xsm_question_status", {"id": "mcp-question", "wait": 0}))
        self.assertEqual(result["status"], "pending", result)
        self.assertEqual(result["replies"], [])
        self.assertEqual(result["network_delivery"], delivery)
        self.assertEqual(ledger.status("mcp-question")["status"], "delivered")
        self.assertEqual(rpc.call_args.args[0]["caller"], self.sender)
        self.assertEqual(rpc.call_args.args[0]["op"], "message-status")

    def test_send_wait_retrieves_delivery_under_same_id_without_resending(self):
        from xsm import ledger, network, send
        calls = []
        def broker(request, **kwargs):
            calls.append(request)
            if request["op"] == "send":
                ledger.queued(request["id"], self.sender, self.target, self.scope, "note", "body")
                return {"status": "sent-unconfirmed", "id": request["id"], "target": self.target}
            self.assertEqual(request["op"], "message-status")
            return {"status": "acknowledged", "stored": True, "acknowledged": True}
        with mock.patch.object(network, "call", side_effect=broker):
            result = send.send(self.address, "body", sender=self.sender, msg_id="waited-send", wait=2)
        self.assertEqual(result.status, "delivered", result.reason)
        self.assertEqual([c["op"] for c in calls], ["send", "message-status"])
        self.assertEqual([c["id"] for c in calls], ["waited-send", "waited-send"])

    def test_cli_local_and_ssh_status_do_not_reconcile_network(self):
        from xsm import cli, ledger, network, remote
        with mock.patch.object(network, "reconcile", side_effect=AssertionError("network status fallback")):
            for request_id, scope in (("local-status", "repo:local"), ("ssh-status", "remote:legacy")):
                ledger.queued(request_id, self.sender, self.sender, scope, "note", "body")
                with mock.patch.object(remote, "reconcile", return_value=ledger.status(request_id)) as ssh, \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(cli.main(["status", request_id, "--json"]), 3)
                self.assertEqual(ssh.call_count, 1 if scope.startswith("remote:") else 0)

    def test_network_ledger_target_is_not_marked_stopped_by_local_registry(self):
        from xsm import cli, ledger
        ledger.queued("network-ledger", self.sender, self.target, self.scope, "note", "body")
        rows = cli._mark_undelivered([ledger.status("network-ledger")])
        self.assertEqual(rows[0]["status"], "queued")
        self.assertIn("xsm status network-ledger", rows[0]["note"])

    def test_remote_candidate_resolves_current_full_handle_and_retains_network_scope(self):
        from xsm import directory, network, resolve
        candidate = dict(self.target, id=self.candidate_id)
        def broker(request, **kwargs):
            self.assertEqual(request["caller"], self.sender)
            if request["op"] == "discover":
                return {"status": "ok", "candidates": [candidate]}
            self.assertEqual(request["op"], "resolve")
            return self.resolved(self.scope, "same-repository")
        with mock.patch.object(network, "available", return_value=True), \
                mock.patch.object(network, "call", side_effect=broker) as rpc:
            found = resolve.resolve(self.candidate, caller=self.sender)
        self.assertTrue(found.ok, found.reason)
        self.assertEqual(found.scope, self.scope)
        self.assertEqual(found.scope_basis, "same-repository")
        self.assertEqual(found.record["handle"], self.handle)
        self.assertEqual([c.args[0]["op"] for c in rpc.call_args_list], ["discover", "resolve"])
        self.assertEqual(found.record["target"], self.address)

    def test_remote_candidate_rejects_stale_generation_duplicate_or_missing_discovery(self):
        from xsm import directory, network, resolve
        candidate = dict(self.target, id=self.candidate_id)
        changed = self.resolved(self.scope, "selected")
        changed["target"]["generation"] = changed["target"]["handle"]["generation"] = "d" * 64
        for candidates, resolved in (([candidate], changed), ([candidate, candidate], self.resolved()),
                                     ([], self.resolved())):
            def broker(request, **kwargs):
                return {"status": "ok", "candidates": candidates} if request["op"] == "discover" else resolved
            with self.subTest(candidates=len(candidates)), \
                    mock.patch.object(network, "available", return_value=True), \
                    mock.patch.object(network, "call", side_effect=broker):
                self.assertFalse(resolve.resolve(self.candidate, caller=self.sender).ok)
        with mock.patch.object(network, "available", return_value=False), mock.patch.object(network, "call") as rpc:
            self.assertIsNone(directory.resolve_candidate(self.sender, self.candidate_id))
        rpc.assert_not_called()

    def test_local_candidate_does_not_query_network_when_service_is_available(self):
        from xsm import directory, network, resolve
        directory.publish(self.sender, user_source="unit fixture publication")
        key = directory._key(directory._endpoint(self.sender))
        with mock.patch.object(network, "available", return_value=True), \
                mock.patch.object(network, "call", side_effect=AssertionError("local candidate queried network")):
            found = resolve.resolve("candidate:" + key, caller=self.sender)
        self.assertTrue(found.ok, found.reason)
        self.assertEqual(found.record["session_id"], self.sender["session_id"])
        self.assertIsNone(found.scope)

    def test_candidate_ask_and_files_redelegate_to_broker_without_local_scope(self):
        from xsm import config, materials, network, questions
        candidate = dict(self.target, id=self.candidate_id)
        calls = []
        def broker(request, **kwargs):
            calls.append(request)
            self.assertEqual(request["caller"], self.sender)
            if request["op"] == "discover":
                return {"status": "ok", "candidates": [candidate]}
            self.assertEqual(request["target"], self.address)
            if request["op"] == "resolve":
                return self.resolved(self.scope, "selected")
            if request["op"] == "capabilities":
                return {"capabilities": {"status": "observed", "version": 1}}
            return {"status": "sent-unconfirmed", "id": request["id"], "target": self.target}
        with mock.patch.object(network, "available", return_value=True), \
                mock.patch.object(network, "call", side_effect=broker), \
                mock.patch.object(config, "scope_for", side_effect=AssertionError("candidate used local scope")):
            prepared = materials.prepare(self.sender, self.candidate, "body", "candidate-question",
                                         [{"name": "spec.md", "text": "copy"}], call=self.call)
            result = questions.ask(self.sender, self.candidate, prepared["body"], request_id="candidate-question",
                                   attachments=prepared["attachments"], file_packet=prepared["file_packet"],
                                   file_limits=prepared["file_limits"], wake="never")
        self.assertEqual(result["send_evidence"]["status"], "sent-unconfirmed", result)
        self.assertEqual(result["status"], "pending", result)
        sends = [c for c in calls if c["op"] == "send"]
        self.assertEqual(len(sends), 1)
        self.assertEqual(sends[0]["target"], self.address)
        self.assertEqual(sends[0]["file_packet"], prepared["file_packet"])

    def test_mcp_candidate_discover_select_handshake_runs_through_real_services(self):
        from xsm import collaboration, mcp, network, questions
        candidate = dict(self.target, id=self.candidate_id)
        selected, sent = [], []
        def broker(request, **kwargs):
            self.assertEqual(request["caller"], self.sender)
            if request["op"] == "discover":
                return {"status": "ok", "candidates": [candidate]}
            if request["op"] == "resolve":
                return self.resolved(self.scope if selected else None, "selected" if selected else None)
            if request["op"] == "selection":
                self.assertIsNotNone(collaboration.scope_for(self.sender, self.target))
                selected.append(request)
                return {"status": "selected", "target": self.target}
            self.assertEqual(request["op"], "send")
            sent.append(request)
            return {"status": "sent-unconfirmed", "id": request["id"], "target": self.target}
        server = mcp.Server(io.StringIO(), io.StringIO())
        server.session = lambda: self.sender
        self._record_selection()
        with mock.patch.object(network, "available", return_value=True), \
                mock.patch.object(network, "call", side_effect=broker):
            discovery = json.loads(server.call("xsm_discover", {}))
            self.assertTrue(any(row["id"] == self.candidate_id for row in discovery["candidates"]))
            shown = json.loads(server.call("xsm_connect", {"target": self.candidate, "wait": 0}))
            self.assertEqual(shown["status"], "selection-required", shown)
            self._age_selection()
            pending = json.loads(server.call("xsm_connect", {"target": self.candidate, "wait": 0}))
            self.assertEqual(pending["handshake"], "pending", pending)
        self.assertEqual(len(selected), 1)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["target"], self.address)
        self.assertEqual(sent[0]["kind"], "task")
        self.assertTrue(questions.record_reply(self.sender, self.target,
            {"kind": "reply", "id": "candidate-handshake-reply", "reply-to": pending["id"], "outcome": "succeeded"}, "준비 완료"))
        self.assertEqual(questions.status(self.sender, pending["id"])["handshake"], "completed")

    def test_selection_response_loss_consumes_approved_consent_and_retains_pair_for_retry(self):
        from xsm import collaboration, connect, consent, network
        self._record_selection()
        with mock.patch.object(network, "call", return_value=self.resolved()):
            self.assertEqual(connect.select(self.sender, self.target, call=self.call)["status"], "selection-required")
        self._age_selection()
        with mock.patch.object(network, "call", side_effect=[self.resolved(), self.resolved(),
                network.NetworkError("service-unavailable-or-response-unknown")]):
            failed = connect.select(self.sender, self.target, call=self.call)
        self.assertEqual(failed["status"], "refused")
        self.assertIsNotNone(collaboration.scope_for(self.sender, self.target))
        self.assertEqual(consent.pending_files(self.sender["ref"]), [])
