"""Gateway product API with real local registry/native FILE fixtures.

Permission callbacks below are explicit unit fixtures, not live model-session
authorization. No native send/queue/wake or external accounts are used.
"""
import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest import mock

from xsm import envelope, files, handoff, network_directory, network_identity, network_messages as messages, paths

A = "a" * 64
B = "b" * 64
C = "c" * 64


def _crash_gateway(state, root, packet, phase):
    from xsm import files as child_files, network_messages as child_messages, paths as child_paths
    child_paths.HOME = state
    gateway = child_messages.Gateway(root, B, lambda *args: True)  # Explicit unit permission fixture.
    gateway.network_id = "fixture-network"
    if phase == "handoff":
        write = child_messages._write
        def crash(path, value):
            if value.get("phase") == "stored": os._exit(71)
            return write(path, value)
        child_messages._write = crash
    else:
        receive = child_files.receive
        def crash(*args, **kwargs):
            receive(*args, **kwargs)
            os._exit(72)
        child_files.receive = crash
    gateway.receive(A, packet)
    os._exit(99)


class NetworkMessagesTest(unittest.TestCase):
    def setUp(self):
        global envelope, files, handoff, network_directory, network_identity, messages, paths
        from xsm import envelope, files, handoff, network_directory, network_identity, network_messages as messages, paths
        from xsm import config, identity
        temporary = tempfile.TemporaryDirectory(prefix="xsm-network-messages-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(os.path.realpath(temporary.name))
        patch = mock.patch.object(paths, "HOME", str(self.root / "state"))
        patch.start()
        self.addCleanup(patch.stop)
        paths.ensure_home()
        self.home = self.root / "first-native-home"
        self.home.mkdir()
        config.add_home(str(self.home), "codex")
        self.cwd = self.root / "work"
        self.cwd.mkdir()
        self.start = identity.lstart(os.getpid()) or "native-fixture-start"
        second = self.root / "second-native-home"
        second.mkdir()
        config.add_home(str(second), "codex")
        self.a = self.row("sender-a")
        self.b = self.row("receiver-b", home=str(second))
        self.store(self.a, self.b)
        self.native(self.a)
        self.native(self.b)
        self.allowed = mock.Mock(name="unit_fixture_local_permission", return_value=True)
        self.denied = mock.Mock(name="unit_fixture_local_denial", return_value=False)
        self.ga = messages.Gateway(self.root / "gateway-a", A, self.denied)
        self.gb = messages.Gateway(self.root / "gateway-b", B, self.allowed)
        self.ga.network_id = self.gb.network_id = "fixture-network"
        self.ap = network_directory.public_endpoint(self.a, A)
        self.bp = network_directory.public_endpoint(self.b, B)

    def row(self, sid, **fields):
        record = {"runtime":"codex", "session_id":sid, "home":str(self.home), "cwd":str(self.cwd),
                  "pid":os.getpid(), "lstart":self.start, "app_server":False,
                  "ref":"fixture-"+sid, "updated":time.time(), "name":"fixture title"}
        record.update(fields)
        return record

    def store(self, *rows):
        from xsm import registry
        for row in rows:
            paths.write_json(registry._record_path(row["runtime"], row["session_id"]), row)

    def native(self, row):
        home = Path(row["home"])
        rollout = home / (row["session_id"] + ".jsonl")
        rollout.write_text(json.dumps({"type":"session_meta", "payload":{"id":row["session_id"]}}) + "\n")
        with closing(sqlite3.connect(home / "state_5.sqlite")) as db, db:
            db.execute("create table if not exists threads (id text primary key, name text, rollout_path text)")
            db.execute("insert or replace into threads values (?, ?, ?)", (row["session_id"], "Native fixture title", str(rollout)))

    def publish(self, row):
        from xsm import directory
        return directory.publish(row, user_source="unit fixture operator publication")

    def prepare(self, body="원문\nPRIVATE CONTENT", **kwargs):
        return self.ga.prepare(self.a, self.bp, body, request_id=kwargs.pop("request_id", "request-1"), **kwargs)

    def test_text_request_reverse_reply_and_exact_status_pair(self):
        packet = self.prepare(kind="task")
        self.assertNotIn(str(self.root), json.dumps(packet))
        self.assertEqual(self.gb.receive(A, packet)["status"], "queued")
        self.assertGreaterEqual(self.allowed.call_count, 1)
        current = handoff.status(self.b, packet["id"])
        self.assertEqual(current["status"], "pending")
        self.assertEqual(current["delivery_route"], "mcp-inbox")
        self.assertEqual(current["message"]["body"], packet["body"])
        self.assertNotIn("home", current["message"]["sender"])
        parsed = envelope.parse(current["message"]["content"])
        self.assertEqual(parsed.header["origin"], "p2p:" + A)
        self.assertEqual(parsed.header["scope"], "network:fixture-network")
        self.assertNotIn("from-mode", parsed.attrs)
        reply = self.gb.prepare(self.b, self.ap, "실제 회신", request_id="reply-1", kind="reply",
                                reply_to=packet["id"], outcome="succeeded")
        self.assertEqual(self.ga.receive(B, reply)["status"], "queued")
        self.assertGreaterEqual(self.denied.call_count, 1)  # Exact reverse request grants reply binding only.
        status = self.ga.status(A, packet["id"], self.ap)
        self.assertEqual(status["status"], "prepared")
        self.assertFalse(status["acknowledged"])
        self.assertEqual(status["final_reply"]["packet"]["body"], "실제 회신")
        self.assertEqual(self.gb.status(A, packet["id"], self.ap)["final_reply"]["packet"], reply)
        self.assertEqual(self.gb.status(A, packet["id"]), {"status":"not-found"})
        self.assertEqual(self.gb.status(C, packet["id"], self.ap), {"status":"not-found"})
        self.assertEqual(self.gb.status(A, packet["id"], dict(self.ap, session_id="other")), {"status":"not-found"})
        self.assertTrue(self.gb.ingress_record(packet["id"])["verified"])

    def _handed_over(self, old, new):
        from xsm import handover
        self.store(new)
        self.native(new)
        paths.write_json(handover._file(handoff._identity(old)), {
            "t": time.time(), "from_identity": handoff._identity(old),
            "to_identity": handoff._identity(new), "letter": "", "shown": True})

    def test_a_message_for_a_handed_over_session_is_stored_for_its_successor(self):
        b2 = self.row("receiver-b2", home=self.b["home"])
        self._handed_over(self.b, b2)
        packet = self.prepare(kind="task")
        self.assertEqual(self.gb.receive(A, packet)["status"], "queued")
        self.assertEqual(handoff.status(b2, packet["id"])["status"], "pending")
        self.assertEqual(handoff.status(self.b, packet["id"])["status"], "not-found")
        # The receive gate reads it back: measured on two machines, 2026-10-31.
        self.assertEqual(self.gb.ingress_record(packet["id"])["target_local"]["session_id"], "receiver-b2")

    def test_a_reply_to_a_handed_over_question_reaches_the_successor(self):
        packet = self.prepare(kind="task")
        self.gb.receive(A, packet)
        a2 = self.row("sender-a2")
        self._handed_over(self.a, a2)
        reply = self.gb.prepare(self.b, self.ap, "늦은 답", request_id="reply-late", kind="reply",
                                reply_to=packet["id"], outcome="succeeded")
        self.assertEqual(self.ga.receive(B, reply)["status"], "queued")
        self.assertEqual(handoff.status(a2, "reply-late")["status"], "pending")
        self.assertEqual(self.ga.ingress_record("reply-late")["target_local"]["session_id"], "sender-a2")

    def test_a_kept_record_for_a_session_that_is_no_successor_is_refused(self):
        packet = self.prepare(kind="task")
        self.gb.receive(A, packet)
        path = self.gb._path("inbound", packet["id"])
        record = json.loads(Path(path).read_text())
        record["local"]["session_id"] = "someone-else"
        Path(path).write_text(json.dumps(record))
        with self.assertRaises(messages.GatewayError):
            self.gb.ingress_record(packet["id"])

    def test_the_successor_answers_a_question_the_old_session_was_asked_from_another_machine(self):
        packet = self.prepare(kind="task")
        self.gb.receive(A, packet)
        b2 = self.row("receiver-b2", home=self.b["home"])
        self._handed_over(self.b, b2)
        b2p = network_directory.public_endpoint(b2, B)
        reply = self.gb.prepare(b2, self.ap, "후임의 답", request_id="reply-successor", kind="reply",
                                reply_to=packet["id"], outcome="succeeded")
        self.assertEqual(network_identity.endpoint(reply["sender"]), network_identity.endpoint(b2p))
        # Both gateways share this test's state, so the asking side reads the
        # handover record itself; across machines it reads B's testimony.
        self.assertEqual(self.ga.receive(B, reply)["status"], "queued")
        stranger = self.row("someone-else", home=self.b["home"])
        self.store(stranger)
        self.native(stranger)
        with self.assertRaises(messages.GatewayError):
            self.gb.prepare(stranger, self.ap, "남의 답", request_id="reply-stranger", kind="reply",
                            reply_to=packet["id"], outcome="succeeded")

    def test_duplicate_preserves_claim_ack_and_original_raw_body(self):
        packet = self.prepare(wake=False)
        self.gb.receive(A, packet)
        owner = {"type":"native", "id":"unit-native-reader"}
        claimed = handoff.claim(self.b, owner, "reader-generation", message_id=packet["id"])
        token = claimed["claim"]["token"]
        self.assertEqual(self.gb.receive(A, packet)["handoff_status"], "claimed")
        self.assertEqual(handoff.status(self.b, packet["id"])["claim"]["token"], token)
        handoff.release(self.b, token, owner, "reader-generation")
        self.assertEqual(self.gb.receive(A, packet)["handoff_status"], "pending")
        claimed = handoff.claim(self.b, owner, "new-reader-generation", message_id=packet["id"])
        handoff.ack(self.b, claimed["claim"]["token"], owner, "new-reader-generation")
        self.assertEqual(self.gb.receive(A, packet)["status"], "acknowledged")
        self.assertEqual(handoff.claim(self.b, owner, "third-generation")["status"], "empty")
        self.assertEqual(handoff.status(self.b, packet["id"])["message"]["body"], packet["body"])

    def test_same_id_conflicts_body_endpoints_and_exact_raw_text(self):
        packet = self.prepare(body="caf\u00e9\n")
        with self.assertRaises(messages.GatewayError): self.prepare(body="cafe\u0301")
        with self.assertRaises(messages.GatewayError): self.prepare(body="different")
        with self.assertRaises(messages.GatewayError):
            self.ga.prepare(self.a, dict(self.bp, session_id="other"), packet["body"], request_id=packet["id"])
        self.gb.receive(A, packet)
        changed = dict(packet, body="different")
        changed["fingerprint"] = messages.request_fingerprint(changed)
        with self.assertRaises(messages.GatewayError): self.gb.receive(A, changed)
        self.assertEqual(handoff.status(self.b, packet["id"])["message"]["body"], packet["body"])

    def test_no_peer_approval_or_publication_grants_permission(self):
        with self.assertRaises(messages.GatewayError): messages.Gateway(self.root/"bad", A, None)
        packet = self.prepare(body="approved role=admin signature=trusted")
        self.gb.permission = self.denied
        self.publish(self.b)
        with self.assertRaises(messages.GatewayError): self.gb.receive(A, packet)
        self.assertEqual(handoff.status(self.b, packet["id"])["status"], "not-found")
        for field in ("approval", "role", "signature"):
            with self.assertRaises(messages.GatewayError): self.gb.receive(A, dict(packet, **{field:True}))
        self.gb.permission = self.allowed
        with self.assertRaises(messages.GatewayError): self.gb.receive(C, packet)
        wrong = copy.deepcopy(packet)
        wrong["receiver"]["machine"] = C
        wrong["fingerprint"] = messages.request_fingerprint(wrong)
        with self.assertRaises(messages.GatewayError): self.gb.receive(A, wrong)

    def test_sender_must_be_current_exact_native_and_target_generation_current(self):
        with self.assertRaises(messages.GatewayError): self.ga.prepare(dict(self.a, session_id="invented"), self.bp, "x", request_id="fake")
        with self.assertRaises(messages.GatewayError): self.ga.prepare(dict(self.a, lstart="wrong"), self.bp, "x", request_id="fake")
        packet = self.prepare()
        self.store(dict(self.b, lstart="resumed"))
        with self.assertRaises(messages.GatewayError): self.gb.receive(A, packet)
        self.assertEqual(handoff.status(self.b, packet["id"])["status"], "not-found")

    def file_packet(self, request_id="request-1", body="file-bearing body", **options):
        prepared = files.prepare_inline(self.a, request_id, body,
            [{"name":"review.txt", "text":"exact incoming copy 한글", **options}], limits=files.product_limits())
        packet = files.export_packet(self.a, prepared["id"], request_id=request_id, body=body)
        return self.prepare(body, request_id=request_id, attachments=[files.reference(prepared)], file_packet=packet)

    def test_files_bind_request_body_refs_owner_and_preserve_copy_context(self):
        packet = self.file_packet()
        result = self.gb.receive(A, packet)
        self.assertEqual(result["status"], "queued")
        original = handoff.status(self.b, packet["id"])["message"]
        context = original["receivedfile_context"]
        self.assertEqual(context["storage_id"], original["file_storage"])
        self.assertEqual(original["attachments"], packet["attachments"])
        entry = packet["file_packet"]["manifest"]["files"][0]
        self.assertEqual(files.read_copy(self.b, context["storage_id"], entry["id"], incoming=True),
                         "exact incoming copy 한글".encode())
        self.assertEqual(self.gb.ingress_record(packet["id"])["files"]["storage_id"], context["storage_id"])
        self.assertEqual(set(self.gb.ingress_record(packet["id"])["packet"]["file_packet"]), {"manifest"})
        self.assertIn("data", packet["file_packet"])  # The caller's valid wire packet is untouched.
        with mock.patch.object(files, "receive", side_effect=AssertionError("duplicate recreated files")), \
                mock.patch.object(handoff, "store", side_effect=AssertionError("duplicate reset canonical original")):
            self.assertEqual(self.gb.receive(A, packet)["status"], "queued")

    def test_file_packet_tamper_body_owner_reference_and_bytes_are_rejected(self):
        packet = self.file_packet()
        changes = []
        wrong = copy.deepcopy(packet); wrong["body"] = "rebound body"; changes.append(wrong)
        wrong = copy.deepcopy(packet); wrong["attachments"][0]["sha256"] = "0"*64; changes.append(wrong)
        wrong = copy.deepcopy(packet)
        wrong["file_packet"]["manifest"]["owner"]["session_id"] = "another"
        wrong["file_packet"]["manifest"]["sha256"] = files._manifest_digest(wrong["file_packet"]["manifest"])
        wrong["attachments"] = [files.reference(wrong["file_packet"]["manifest"])]
        changes.append(wrong)
        wrong = copy.deepcopy(packet)
        first_id = next(iter(wrong["file_packet"]["data"]))
        wrong["file_packet"]["data"][first_id] = "eA=="
        changes.append(wrong)
        for wrong in changes:
            wrong["fingerprint"] = messages.request_fingerprint(wrong)
            with mock.patch.object(handoff, "store") as stored, self.assertRaises(messages.GatewayError):
                self.gb.receive(A, wrong)
            stored.assert_not_called()
        self.assertEqual(handoff.status(self.b, packet["id"])["status"], "not-found")

    def test_file_metadata_cannot_export_private_paths_or_permission_evidence(self):
        for descriptor in ("/private/source", "~/.private/source", "C:\\Users\\private", "v1 /private/source"):
            with self.assertRaises(messages.GatewayError):
                self.file_packet(request_id="descriptor-"+str(len(str(descriptor))), source_version=descriptor)

    def test_denial_precedes_incoming_file_side_effects(self):
        packet = self.file_packet()
        self.gb.permission = self.denied
        with mock.patch.object(files, "receive") as copied, mock.patch.object(handoff, "store") as stored:
            with self.assertRaises(messages.GatewayError): self.gb.receive(A, packet)
        copied.assert_not_called(); stored.assert_not_called()
        self.assertIsNone(self.gb.ingress_record(packet["id"]))

    def test_restart_after_reserved_original_recovers_without_losing_raw_body(self):
        packet = self.prepare()
        with mock.patch.object(handoff, "store", side_effect=OSError("injected")):
            with self.assertRaises(messages.GatewayError): self.gb.receive(A, packet)
        restarted = messages.Gateway(self.gb.root, B, self.allowed)
        restarted.network_id = self.gb.network_id
        self.assertEqual(restarted.receive(A, packet)["status"], "queued")
        self.assertEqual(handoff.status(self.b, packet["id"])["message"]["body"], packet["body"])

    def test_restart_after_handoff_commit_preserves_claim_without_store_or_copy(self):
        packet = self.prepare()
        write = messages._write
        def fail_after_handoff(path, value):
            if value.get("phase") == "stored": raise OSError("lost completion")
            return write(path, value)
        with mock.patch.object(messages, "_write", side_effect=fail_after_handoff):
            with self.assertRaises(messages.GatewayError): self.gb.receive(A, packet)
        owner = {"type":"native", "id":"reader"}
        claimed = handoff.claim(self.b, owner, "generation", message_id=packet["id"])
        with mock.patch.object(handoff, "store", side_effect=AssertionError("re-stored")), \
                mock.patch.object(files, "receive", side_effect=AssertionError("re-copied")):
            self.assertEqual(self.gb.receive(A, packet)["handoff_status"], "claimed")
        self.assertEqual(handoff.status(self.b, packet["id"])["claim"], claimed["claim"])

    def test_file_commit_response_loss_reads_back_same_copy(self):
        packet = self.file_packet()
        receive = files.receive
        def lost_return(*args, **kwargs):
            receive(*args, **kwargs)
            raise OSError("post-commit response lost")
        with mock.patch.object(files, "receive", side_effect=lost_return):
            with self.assertRaises(messages.GatewayError): self.gb.receive(A, packet)
        folder = Path(paths.path(files.DIRECTORY, "incoming"))
        first = sorted(p.name for p in folder.iterdir())
        self.assertEqual(self.gb.receive(A, packet)["status"], "queued")
        self.assertEqual(sorted(p.name for p in folder.iterdir()), first)
        self.assertEqual(self.gb.ingress_record(packet["id"])["files"]["replayed"], True)

    def test_global_canonical_id_collision_on_another_local_endpoint_is_refused(self):
        packet = self.prepare()
        handoff.store(self.a, {"id":packet["id"], "sender":self.b, "body":"existing local original"})
        with self.assertRaises(messages.GatewayError): self.gb.receive(A, packet)
        self.assertEqual(handoff.status(self.b, packet["id"])["status"], "not-found")
        self.assertEqual(handoff.status(self.a, packet["id"])["message"]["body"], "existing local original")

    def test_body_binding_and_digest_are_required_even_when_callback_permits_reply(self):
        packet = self.prepare()
        self.gb.receive(A, packet)
        reply = self.gb.prepare(self.b, self.ap, "bound reply", request_id="reply-1", kind="reply", reply_to=packet["id"])
        self.ga.permission = self.allowed
        for change in ("digest", "endpoint", "request"):
            wrong = copy.deepcopy(reply)
            if change == "digest": wrong["reply_binding"]["fingerprint"] = "0"*64
            elif change == "endpoint": wrong["sender"]["session_id"] = "another-sender"
            else:
                wrong["reply_to"] = "invented-request"
                wrong["reply_binding"]["id"] = "invented-request"
            wrong["fingerprint"] = messages.request_fingerprint(wrong)
            with self.assertRaises(messages.GatewayError): self.ga.receive(B, wrong)
        self.assertEqual(self.ga.receive(B, reply)["status"], "queued")

    def test_verified_ingress_rejects_tampered_canonical_message(self):
        packet = self.prepare()
        self.gb.receive(A, packet)
        canonical = Path(handoff._folder(self.b)) / (packet["id"] + ".json")
        value = json.loads(canonical.read_text())
        value["message"]["wake"] = False
        paths.write_json(str(canonical), value)
        self.assertIsNone(self.gb.ingress_record(packet["id"]))

    def test_missing_network_bad_ids_permissions_and_errors_are_closed(self):
        self.ga.network_id = None
        with self.assertRaises(messages.GatewayError): self.prepare()
        self.ga.network_id = "fixture-network"
        for bad in ("../private", "x/y", "ticket-secret\n", "", None):
            with self.assertRaises(messages.GatewayError) as error: self.prepare(request_id=bad)
            self.assertNotIn("ticket-secret", str(error.exception))
        packet = self.prepare()
        for folder in (self.ga.root, self.ga.root/"outbound", self.gb.root/"inbound"):
            self.assertEqual(folder.stat().st_mode & 0o777, 0o700)
        for path in self.ga.root.rglob("*"):
            if path.is_file(): self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        original = self.ga.root / "outbound" / (packet["id"] + ".json")
        original.chmod(0o644)
        with self.assertRaises(messages.GatewayError): self.ga.status(A, packet["id"], self.ap)

    def test_actual_inbox_consumer_receipt_handoff_ack_do_not_break_duplicate(self):
        from xsm import receive
        packet = self.prepare()
        self.gb.receive(A, packet)
        # Only the local gate decision is a fixture; claim, receipt and ACK use
        # the real consumer/handoff APIs. No running model runtime is implied.
        with mock.patch.object(receive, "check", return_value=("pass", "unit local gate fixture")):
            taken = receive.take_inbox_claims(self.b, owner={"type":"native", "id":"fixture-consumer"},
                                             generation="consumer-generation", message_ids=[packet["id"]])
        self.assertEqual(len(taken["claims"]), 1)
        result = self.gb.receive(A, packet)
        self.assertEqual(result["status"], "queued")
        self.assertEqual(result["handoff_status"], "handoff-recorded")
        self.assertFalse(result["acknowledged"])
        claim = taken["claims"][0]
        handoff.ack(self.b, claim["token"], claim["owner"], claim["generation"])
        self.assertEqual(self.gb.receive(A, packet)["status"], "acknowledged")

    def test_legacy_held_receipt_requires_full_native_reservation_and_never_becomes_read(self):
        from xsm import ledger
        packet = self.prepare()
        self.gb.receive(A, packet)
        ledger.handoff_step(packet["id"], "stored", self.b)
        ledger.receipt(packet["id"], "held", self.b, "unit fixture local deferral")
        handoff.delivery(self.b, packet["id"], "held", route="mcp-inbox")
        result = self.gb.receive(A, packet)
        self.assertEqual(result["status"], "held")
        self.assertFalse(result["acknowledged"])
        self.assertEqual(handoff.status(self.b, packet["id"])["delivery_state"], "held")

    def test_crash_before_route_commit_repairs_route_without_resetting_claim(self):
        packet = self.prepare()
        with mock.patch.object(self.gb, "_route", side_effect=OSError("lost route commit")):
            with self.assertRaises(messages.GatewayError): self.gb.receive(A, packet)
        self.assertNotIn("delivery_route", handoff.status(self.b, packet["id"]))
        owner = {"type":"native", "id":"reader"}
        claimed = handoff.claim(self.b, owner, "generation", message_id=packet["id"])
        self.assertEqual(self.gb.receive(A, packet)["route"], "mcp-inbox")
        self.assertEqual(handoff.status(self.b, packet["id"])["claim"], claimed["claim"])

    def test_route_repair_racing_held_release_never_reopens_delivery(self):
        packet = self.prepare()
        with mock.patch.object(self.gb, "_route", side_effect=OSError("lost route commit")):
            with self.assertRaises(messages.GatewayError): self.gb.receive(A, packet)
        owner = {"type":"native", "id":"reader"}
        claim = handoff.claim(self.b, owner, "generation", message_id=packet["id"])["claim"]
        route = self.gb._route
        def release_then_route(local, message_id):
            handoff.release(self.b, claim["token"], owner, "generation", delivery_state="held")
            return route(local, message_id)
        with mock.patch.object(self.gb, "_route", side_effect=release_then_route):
            self.assertEqual(self.gb.receive(A, packet)["status"], "held")
        current = handoff.status(self.b, packet["id"])
        self.assertEqual(current["delivery_route"], "mcp-inbox")
        self.assertEqual(current["delivery_state"], "held")
        self.assertIsNone(current["claim"])

    def test_real_process_exit_after_handoff_commit_keeps_original_and_lock_recoverable(self):
        packet = self.prepare()
        process = multiprocessing.get_context("spawn").Process(target=_crash_gateway,
            args=(paths.HOME, str(self.gb.root), packet, "handoff"))
        process.start()
        try:
            process.join(10)
            self.assertEqual(process.exitcode, 71)
        finally:
            if process.is_alive(): process.kill(); process.join(5)
        owner = {"type":"native", "id":"post-crash-consumer"}
        claimed = handoff.claim(self.b, owner, "consumer-generation", message_id=packet["id"])
        self.assertEqual(self.gb.receive(A, packet)["handoff_status"], "claimed")
        self.assertEqual(handoff.status(self.b, packet["id"])["claim"], claimed["claim"])
        self.assertEqual(handoff.status(self.b, packet["id"])["message"]["body"], packet["body"])

    def test_real_process_exit_after_file_commit_recovers_one_existing_bundle(self):
        packet = self.file_packet()
        process = multiprocessing.get_context("spawn").Process(target=_crash_gateway,
            args=(paths.HOME, str(self.gb.root), packet, "files"))
        process.start()
        try:
            process.join(10)
            self.assertEqual(process.exitcode, 72)
        finally:
            if process.is_alive(): process.kill(); process.join(5)
        folder = Path(paths.path(files.DIRECTORY, "incoming"))
        copies = sorted(path.name for path in folder.iterdir())
        self.assertEqual(len(copies), 1)
        self.assertEqual(self.gb.receive(A, packet)["status"], "queued")
        self.assertEqual(sorted(path.name for path in folder.iterdir()), copies)

    def test_concurrent_receive_stores_only_one_canonical_original(self):
        packet = self.prepare()
        with mock.patch.object(handoff, "store", wraps=handoff.store) as store:
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda _: self.gb.receive(A, packet), range(8)))
        self.assertTrue(all(result["status"] == "queued" for result in results))
        self.assertEqual(store.call_count, 1)

    def test_four_mib_file_bundle_uses_incoming_copies_without_inline_rewrite(self):
        body = "Four MiB immutable bundle"
        prepared = files.prepare_inline(self.a, "bundle-4m", body,
            [{"name":"part-%d.bin" % number, "data":bytes([number])*1024*1024} for number in range(4)],
            limits=files.product_limits())
        file_packet = files.export_packet(self.a, prepared["id"], request_id="bundle-4m", body=body)
        packet = self.prepare(body, request_id="bundle-4m", attachments=[files.reference(prepared)], file_packet=file_packet)
        self.assertEqual(self.gb.receive(A, packet)["status"], "queued")
        message = handoff.status(self.b, "bundle-4m")["message"]
        self.assertEqual(message["body"], body)
        self.assertEqual(len(message["receivedfile_context"]["files"]), 4)
        for number, entry in enumerate(prepared["files"]):
            self.assertEqual(files.read_copy(self.b, message["file_storage"], entry["id"], incoming=True), bytes([number])*1024*1024)

    def test_semantic_identity_excludes_generation_but_original_packet_stays_frozen(self):
        packet = self.prepare()
        changed = self.ga.prepare(dict(self.a, name="renamed display"), dict(self.bp, generation="0"*64), packet["body"], request_id=packet["id"])
        self.assertEqual(changed["fingerprint"], packet["fingerprint"])
        self.assertNotEqual(changed["receiver"]["generation"], packet["receiver"]["generation"])
        original = self.ga._load("outbound", packet["id"])
        self.assertEqual(original["packet"], packet)
        with self.assertRaises(messages.GatewayError): self.gb.receive(A, changed)

    def test_foreign_receipt_digest_cannot_override_own_canonical_ack(self):
        from xsm import ledger
        packet = self.prepare()
        self.gb.receive(A, packet)
        ledger.receipt(packet["id"], "delivered", self.b, from_ref="wrong", body_sha="0"*16, req_digest="0"*64)
        self.assertFalse(self.gb.status(A, packet["id"], self.ap)["acknowledged"])
        with self.assertRaises(messages.GatewayError): self.gb.receive(A, packet)
        self.assertEqual(handoff.status(self.b, packet["id"])["status"], "pending")

    def test_status_never_exposes_reply_for_different_reverse_endpoint(self):
        packet = self.prepare()
        self.gb.receive(A, packet)
        reply = self.gb.prepare(self.b, self.ap, "private bound reply", request_id="reply-1", kind="reply", reply_to=packet["id"])
        filename = self.gb.root / "outbound" / "reply-1.json"
        record = json.loads(filename.read_text())
        record["packet"]["receiver"]["session_id"] = "unrelated-owner"
        record["packet"]["fingerprint"] = messages.request_fingerprint(record["packet"])
        record["fingerprint"] = record["packet"]["fingerprint"]
        record["packet_sha256"] = messages.hashlib.sha256(messages._json(record["packet"])).hexdigest()
        paths.write_json(str(filename), record)
        status = self.gb.status(A, packet["id"], self.ap)
        self.assertIsNone(status["final_reply"])
        self.assertEqual(status["replies"], [])

    def test_large_file_reply_status_carries_one_packet_within_quic_frame_bound(self):
        packet = self.prepare()
        self.gb.receive(A, packet)
        body = "Exact reverse file reply"
        prepared = files.prepare_inline(self.b, "reply-with-file", body,
            [{"name":"reply-%d.bin" % number, "data":b"r"*1024*1024} for number in range(4)], limits=files.product_limits())
        file_packet = files.export_packet(self.b, prepared["id"], request_id="reply-with-file", body=body)
        reply = self.gb.prepare(self.b, self.ap, body, request_id="reply-with-file", kind="reply", reply_to=packet["id"],
                                attachments=[files.reference(prepared)], file_packet=file_packet)
        source_status = self.gb.status(A, packet["id"], self.ap)
        self.assertEqual(source_status["final_reply"]["packet"], reply)
        self.assertNotIn("packet", source_status["replies"][0])
        self.assertLess(len(messages._json(source_status)), messages.MAX_PACKET)
        self.assertEqual(self.ga.receive(B, reply)["status"], "queued")
        destination_status = self.ga.status(A, packet["id"], self.ap)
        self.assertLess(len(messages._json(destination_status)), messages.MAX_PACKET)
        self.assertEqual(destination_status["final_reply"]["packet"]["body"], body)

    def test_permission_revoked_during_copy_cannot_queue_body(self):
        packet = self.file_packet()
        receive = files.receive
        def revoke_after_copy(*args, **kwargs):
            receipt = receive(*args, **kwargs)
            self.allowed.return_value = False
            return receipt
        with mock.patch.object(files, "receive", side_effect=revoke_after_copy):
            with self.assertRaises(messages.GatewayError): self.gb.receive(A, packet)
        self.assertEqual(handoff.status(self.b, packet["id"])["status"], "not-found")
        self.assertIsNone(self.gb.ingress_record(packet["id"]))
        self.allowed.return_value = True
        with mock.patch.object(files, "receive", side_effect=AssertionError("copy recreated")):
            self.assertEqual(self.gb.receive(A, packet)["status"], "queued")

    def test_corrupt_symlink_and_nonprivate_gateway_state_fail_closed(self):
        packet = self.prepare()
        filename = self.ga.root / "outbound" / (packet["id"] + ".json")
        saved = filename.with_suffix(".saved")
        filename.rename(saved)
        filename.symlink_to(saved)
        with self.assertRaises(messages.GatewayError): self.ga.status(A, packet["id"], self.ap)
        filename.unlink()
        saved.rename(filename)
        filename.write_text("{")
        with self.assertRaises(messages.GatewayError): self.ga.status(A, packet["id"], self.ap)
        self.gb.root.chmod(0o755)
        with self.assertRaises(messages.GatewayError): self.gb.status(A, packet["id"], self.ap)
        self.gb.root.chmod(0o700)

    def test_gateway_never_calls_native_send_queue_or_wake(self):
        from xsm import adapters
        packet = self.prepare()
        with mock.patch.object(adapters, "to_codex", side_effect=AssertionError("native codex send")) as codex, \
                mock.patch.object(adapters, "to_claude", side_effect=AssertionError("native claude send")) as claude, \
                mock.patch.object(adapters, "wake_codex", side_effect=AssertionError("native wake")) as wake:
            self.assertEqual(self.gb.receive(A, packet)["status"], "queued")
        codex.assert_not_called(); claude.assert_not_called(); wake.assert_not_called()

    def test_permission_receives_exact_public_sender_actual_target_and_isolated_packet(self):
        packet = self.prepare()
        def inspect(origin, sender, target, supplied):
            self.assertEqual(origin, A)
            self.assertEqual(sender, packet["sender"])
            self.assertEqual(target["home"], self.b["home"])
            self.assertEqual(target["session_id"], self.b["session_id"])
            self.assertEqual(supplied, packet)
            sender["session_id"] = "mutated"
            target["home"] = "/untrusted/mutation"
            supplied["body"] = "mutated"
            return True
        self.gb.permission = inspect
        self.assertEqual(self.gb.receive(A, packet)["status"], "queued")
        self.assertEqual(handoff.status(self.b, packet["id"])["message"]["body"], packet["body"])

    def test_truthy_permission_and_callback_error_never_grant_or_expose_payload(self):
        packet = self.prepare()
        self.gb.permission = lambda *args: {"approval":True, "role":"administrator"}
        with self.assertRaises(messages.GatewayError): self.gb.receive(A, packet)
        self.gb.permission = mock.Mock(side_effect=RuntimeError("PRIVATE BODY TICKET KEY"))
        with self.assertRaises(messages.GatewayError) as error: self.gb.receive(A, packet)
        self.assertEqual(str(error.exception), "local-permission-unavailable")
        self.assertNotIn("PRIVATE BODY", str(error.exception))

    def test_cli_snapshot_gateway_never_reopens_paths_and_only_creates_incoming_copy(self):
        source = self.cwd / "operator-source.txt"
        source.write_bytes(b"original source copy")
        body = "Caller supplied CLI snapshot"
        prepared = files.prepare_cli(self.a, "cli-copy", body, [str(source)], limits=files.product_limits())
        exported = files.export_packet(self.a, prepared["id"], request_id="cli-copy", body=body)
        with mock.patch.object(files, "_snapshot_cli", side_effect=AssertionError("gateway source path read")):
            packet = self.prepare(body, request_id="cli-copy", attachments=[files.reference(prepared)], file_packet=exported)
            self.assertNotIn(str(source), json.dumps(packet))
            self.assertEqual(self.gb.receive(A, packet)["status"], "queued")
        self.assertEqual(source.read_bytes(), b"original source copy")
        original = handoff.status(self.b, "cli-copy")["message"]
        self.assertEqual(files.read_copy(self.b, original["file_storage"], prepared["files"][0]["id"], incoming=True), source.read_bytes())

    def test_matching_core_ledger_digest_is_not_read_evidence_or_a_resend_conflict(self):
        packet = self.prepare()
        self.gb.receive(A, packet)
        filename = paths.path(paths.LEDGER, packet["id"] + ".json")
        paths.write_json(filename, {"id":packet["id"], "req_version":envelope.CANON_VERSION,
                                    "digest":packet["fingerprint"], "status":"delivered"})
        result = self.gb.receive(A, packet)
        self.assertEqual(result["status"], "queued")
        self.assertFalse(result["acknowledged"])
        paths.write_json(filename, {"id":packet["id"], "req_version":envelope.CANON_VERSION, "digest":"0"*64})
        with self.assertRaises(messages.GatewayError): self.gb.receive(A, packet)

    def test_copy_time_cwd_change_is_authorized_against_the_new_actual_record(self):
        packet = self.file_packet()
        other = self.root / "other-repository"
        other.mkdir()
        before = self.b["cwd"]
        checked = []
        def permission(origin, sender, target, supplied):
            checked.append(target["cwd"])
            return target["cwd"] == before
        self.gb.permission = permission
        receive = files.receive
        def move_after_copy(*args, **kwargs):
            result = receive(*args, **kwargs)
            self.store(dict(self.b, cwd=str(other)))
            return result
        with mock.patch.object(files, "receive", side_effect=move_after_copy):
            with self.assertRaises(messages.GatewayError): self.gb.receive(A, packet)
        self.assertIn(str(other), checked)
        self.assertEqual(handoff.status(self.b, packet["id"])["status"], "not-found")

    def test_cwd_change_during_permission_callback_is_detected_even_when_not_excluded(self):
        packet = self.prepare()
        other = self.root / "other-repository"
        other.mkdir()
        def moving_permission(*args):
            self.store(dict(self.b, cwd=str(other)))
            return True
        self.gb.permission = moving_permission
        with self.assertRaises(messages.GatewayError): self.gb.receive(A, packet)
        self.assertEqual(handoff.status(self.b, packet["id"])["status"], "not-found")

    def queued_intent(self, request_id, body="prepared question", **updates):
        from xsm import ledger, network_identity
        return ledger.queued(request_id, updates.get("sender", self.a),
            updates.get("target", network_identity.endpoint(self.bp)),
            updates.get("scope", "network:fixture-network"), updates.get("kind", "task"), updates.get("body", body),
            priority=updates.get("priority", "next"), attachments=updates.get("attachments"))

    def test_prepared_intent_accepts_only_exact_local_to_opaque_canonical_row(self):
        body = "prepared question"
        queued = self.queued_intent("prepared-1", body)
        before = Path(paths.path(paths.LEDGER, "prepared-1.json")).read_bytes()
        with self.assertRaises(messages.GatewayError): self.prepare(body, request_id="prepared-1", kind="task")
        packet = self.prepare(body, request_id="prepared-1", kind="task", prepared_intent=True)
        self.assertNotEqual(packet["fingerprint"], queued["digest"])
        self.assertEqual(packet["scope"], "network:fixture-network")
        self.assertEqual(Path(paths.path(paths.LEDGER, "prepared-1.json")).read_bytes(), before)
        self.assertEqual(self.ga._load("outbound", "prepared-1")["packet"], packet)

    def test_prepared_intent_wrong_native_target_body_scope_kind_priority_version_refuse(self):
        from xsm import network_identity
        cases = [
            {"sender":dict(self.a, session_id="wrong-sender")},
            {"sender":dict(self.a, home=self.b["home"])},
            {"target":dict(network_identity.endpoint(self.bp), session_id="wrong-target")},
            {"target":dict(network_identity.endpoint(self.bp), machine=C)},
            {"body":"other body"}, {"scope":"network:another-network"}, {"kind":"note"}, {"priority":"now"},
        ]
        for number, update in enumerate(cases):
            request_id = "bad-intent-" + str(number)
            self.queued_intent(request_id, **update)
            with self.assertRaises(messages.GatewayError):
                self.prepare("prepared question", request_id=request_id, kind="task", prepared_intent=True)
            self.assertIsNone(self.ga._load("outbound", request_id))
        for number, update in enumerate(({"req_version":0}, {"req_version":True}, {"status":"delivered"})):
            request_id = "bad-intent-meta-" + str(number)
            row = self.queued_intent(request_id)
            row.update(update)
            paths.write_json(paths.path(paths.LEDGER, request_id + ".json"), row)
            with self.assertRaises(messages.GatewayError):
                self.prepare("prepared question", request_id=request_id, kind="task", prepared_intent=True)
        with self.assertRaises(messages.GatewayError):
            self.prepare("prepared question", request_id="missing-intent", kind="task", prepared_intent=True)

    def test_prepared_intent_never_allows_other_canonical_global_reservations(self):
        self.queued_intent("occupied-intent")
        handoff.store(self.a, {"id":"occupied-intent", "sender":self.b, "body":"existing original"})
        with self.assertRaises(messages.GatewayError):
            self.prepare("prepared question", request_id="occupied-intent", kind="task", prepared_intent=True)
        self.assertEqual(handoff.status(self.a, "occupied-intent")["message"]["body"], "existing original")

    def test_prepared_intent_ref_must_be_absent_or_exact_opaque_net_address(self):
        from xsm import network_identity
        for number, ref in enumerate(("display-name", "https://example.invalid/repository", network_identity.target(dict(self.bp, machine=C)))):
            request_id = "bad-intent-ref-" + str(number)
            self.queued_intent(request_id, target=dict(self.bp, ref=ref))
            with self.assertRaises(messages.GatewayError):
                self.prepare("prepared question", request_id=request_id, kind="task", prepared_intent=True)

    def test_prepared_outbound_intent_never_grants_inbound_permission(self):
        self.queued_intent("prepared-denied")
        packet = self.prepare("prepared question", request_id="prepared-denied", kind="task", prepared_intent=True)
        self.gb.permission = self.denied
        with self.assertRaises(messages.GatewayError) as error: self.gb.receive(A, packet)
        self.assertEqual(error.exception.code, "local-permission-denied")
        self.assertEqual(handoff.status(self.b, packet["id"])["status"], "not-found")

    def test_private_binding_retains_native_generation_for_broker_revalidation(self):
        self.b = dict(self.b, mcp_pid=os.getpid(), mcp_lstart=self.start)
        self.store(self.b)
        self.bp = network_directory.public_endpoint(self.b, B)
        packet = self.prepare()
        self.gb.receive(A, packet)
        binding = self.gb.ingress_record(packet["id"])
        self.assertEqual(network_directory.public_endpoint(binding["target_local"], B), packet["receiver"])
        outbound = self.ga._load("outbound", packet["id"])
        self.assertEqual(network_directory.public_endpoint(outbound["local"], A), packet["sender"])

    def test_real_questions_ask_prequeued_intent_enters_gateway_with_uniform_network_scope(self):
        from xsm import config, network_identity, questions, resolve, send
        body = "Question through existing ask API"
        address = network_identity.target(self.bp)
        remote = dict(self.bp, handle=self.bp, ref=address, target=address, remote=True, registered=True, alias=B)
        dispatched = []
        def dispatch(address, text, **options):
            packet = self.ga.prepare(options["sender"], self.bp, text, request_id=options["msg_id"],
                kind=options["kind"], priority=options["priority"], wake=options["wake"],
                attachments=options.get("attachments") or (), file_packet=options.get("file_packet"), prepared_intent=True)
            dispatched.append(packet)
            return send.SendResult("sent-unconfirmed", "unit broker dispatch fixture", packet["id"])
        with mock.patch.object(resolve, "resolve", return_value=resolve.Resolution("resolved", remote,
                    scope="network:fixture-network", scope_basis="selected")), \
                mock.patch.object(config, "scope_for", side_effect=AssertionError("remote scope must come from broker")), \
                mock.patch.object(send, "send", side_effect=dispatch):
            result = questions.ask(self.a, address, body, request_id="actual-question-intent", wait=0)
        self.assertEqual(result["status"], "pending", result)
        self.assertEqual(len(dispatched), 1)
        self.assertEqual(dispatched[0]["scope"], "network:fixture-network")
        self.assertEqual(dispatched[0]["kind"], "task")
        self.assertEqual(self.ga._load("outbound", "actual-question-intent")["packet"]["body"], body)

    def test_target_privacy_changed_inside_permission_callback_is_rechecked(self):
        from xsm import config
        packet = self.prepare()
        def revoke(*args):
            paths.write_json(paths.path(config.CONFIG), {"directory_excluded_paths":[self.b["cwd"]]})
            return True
        self.gb.permission = revoke
        with self.assertRaises(messages.GatewayError): self.gb.receive(A, packet)
        self.assertEqual(handoff.status(self.b, packet["id"])["status"], "not-found")


if __name__ == "__main__":
    unittest.main()
