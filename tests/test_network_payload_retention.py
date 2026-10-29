"""Attachment retention with new temporary stores, never evaluation originals.

Reuse real SQLite/rollout/registry FILE fixtures. Permissions are explicit unit
fixtures, not a model session, TLS authentication or a new delivery authority.
"""
import base64
import copy
import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from tests import test_network_messages as fixture


class PayloadRetentionTests(unittest.TestCase):
    def setUp(self):
        # Delegate fixture construction, not its test methods or permissions.
        self.fixture = fixture.NetworkMessagesTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        from xsm import files, handoff, network_messages, paths
        self.files, self.handoff, self.messages, self.paths = files, handoff, network_messages, paths
        self.a, self.b, self.ga, self.gb = (getattr(self.fixture, k) for k in ("a", "b", "ga", "gb"))

    def packet(self, message_id="retention-file", size=64 * 1024):
        body = "exact request body\n"
        data = (b"UNMETERED-PAYLOAD-MUST-NOT-REMAIN:" * (size // 32 + 1))[:size]
        manifest = self.files.prepare_inline(self.a, message_id, body,
            [{"name": "payload.bin", "data": data}], limits=self.files.product_limits())
        wire = self.files.export_packet(self.a, manifest["id"], request_id=message_id, body=body)
        packet = self.ga.prepare(self.a, self.fixture.bp, body, request_id=message_id,
                                 attachments=[self.files.reference(manifest)], file_packet=wire)
        return packet, data

    def record(self, gateway, direction, message_id):
        path = gateway.root / direction / (message_id + ".json")
        return path, json.loads(path.read_text())

    def assert_metadata_only(self, gateway, direction, packet, data):
        path, record = self.record(gateway, direction, packet["id"])
        self.assertEqual(record["packet"]["file_packet"], {"manifest": packet["file_packet"]["manifest"]})
        self.assertNotIn(base64.b64encode(data), path.read_bytes())
        self.assertEqual(record["fingerprint"], packet["fingerprint"])
        self.assertEqual(record["packet_sha256"], hashlib.sha256(self.messages._json(record["packet"])).hexdigest())
        return path, record

    def test_wire_bytes_remain_valid_but_both_durable_records_are_metadata_only(self):
        packet, data = self.packet()
        self.assertEqual(self.files._packet(packet["file_packet"], packet["id"], packet["body"],
                                          self.files.product_limits())[1],
                         {packet["file_packet"]["manifest"]["files"][0]["id"]: data})
        self.assert_metadata_only(self.ga, "outbound", packet, data)
        self.gb.receive(fixture.A, packet)
        _, record = self.assert_metadata_only(self.gb, "inbound", packet, data)
        entry = packet["file_packet"]["manifest"]["files"][0]
        self.assertEqual(self.files.read_copy(self.b, record["files"]["storage_id"], entry["id"], incoming=True), data)
        self.assertEqual(self.gb.ingress_record(packet["id"])["packet"], record["packet"])
        # Status reconstruction reads already-authorized private copies only.
        # It must never revalidate/reopen a CLI original as export_packet does.
        with mock.patch.object(self.files, "export_packet", side_effect=AssertionError("reopened input source")), \
                mock.patch.object(self.files, "revalidate", side_effect=AssertionError("revalidated input source")):
            outgoing = self.ga._load("outbound", packet["id"])
            self.assertEqual(self.ga._wire_packet(outgoing), packet)
            self.assertEqual(self.gb._wire_packet(self.gb._load("inbound", packet["id"])), packet)
        for gateway, direction, wrong_owner in ((self.ga, "outbound", self.b), (self.gb, "inbound", self.a)):
            wrong = copy.deepcopy(gateway._load(direction, packet["id"]))
            wrong["local"] = wrong_owner
            with self.assertRaisesRegex(self.messages.GatewayError, "file-payload-unavailable"):
                gateway._wire_packet(wrong)

    def test_quota_rejection_reservation_does_not_cache_large_base64_payload(self):
        packet, data = self.packet("quota-file", size=512 * 1024)
        small = replace(self.files.product_limits(), quota_bytes=1)
        with mock.patch.object(self.files, "product_limits", return_value=small):
            with self.assertRaises(self.messages.GatewayError):
                self.gb.receive(fixture.A, packet)
        _, record = self.assert_metadata_only(self.gb, "inbound", packet, data)
        self.assertEqual(record["phase"], "reserved")
        self.assertNotIn("files", record)
        self.assertEqual(self.handoff.status(self.b, packet["id"])["status"], "not-found")
        self.assertTrue(self.gb.receive(fixture.A, packet)["stored"])

    def test_committed_duplicate_verifies_bytes_and_preserves_original_claim_and_ack(self):
        packet, data = self.packet()
        self.gb.receive(fixture.A, packet)
        before = self.handoff.status(self.b, packet["id"])
        owner, generation = {"type": "native", "id": "fixture-reader"}, "reader-generation"
        claim = self.handoff.claim(self.b, owner, generation, message_id=packet["id"])
        token = claim["claim"]["token"]
        for phase in ("claimed", "acknowledged"):
            if phase == "acknowledged":
                self.handoff.ack(self.b, token, owner, generation)
            for mutation in ("wrong-bytes", "missing-data", "empty-data"):
                with self.subTest(phase=phase, mutation=mutation):
                    bad = copy.deepcopy(packet)
                    if mutation == "wrong-bytes":
                        entry = next(iter(bad["file_packet"]["data"]))
                        bad["file_packet"]["data"][entry] = base64.b64encode(b"x" * len(data)).decode()
                    elif mutation == "missing-data":
                        del bad["file_packet"]["data"]
                    else:
                        bad["file_packet"]["data"] = {}
                    original = self.handoff.status(self.b, packet["id"])
                    with self.assertRaises(self.messages.GatewayError):
                        self.gb.receive(fixture.A, bad)
                    self.assertEqual(self.handoff.status(self.b, packet["id"]), original)
            with mock.patch.object(self.files, "receive", side_effect=AssertionError("duplicate recreated copies")):
                replayed = self.gb.receive(fixture.A, packet)
            self.assertEqual(replayed["acknowledged"], phase == "acknowledged")
            current = self.handoff.status(self.b, packet["id"])
            self.assertEqual(current["message"], before["message"])
            self.assertEqual(current["digest"], before["digest"])
            self.assertEqual(current["claim"]["token"], token)

    def test_ttl_does_not_leave_gateway_payload_and_active_consumption_refuses_expiry(self):
        packet, data = self.packet()
        self.gb.receive(fixture.A, packet)
        _, record = self.assert_metadata_only(self.gb, "inbound", packet, data)
        original = self.handoff.status(self.b, packet["id"])
        expiry = packet["file_packet"]["manifest"]["expires_at"] + 1
        with mock.patch.object(self.files.time, "time", return_value=expiry):
            with self.assertRaises(self.files.FileError) as expired:
                self.files.received_manifest(self.b, record["files"]["storage_id"], request_id=packet["id"],
                    body=packet["body"], expected_reference=packet["attachments"][0])
            self.assertEqual(expired.exception.code, "expired")
            with self.assertRaises(self.messages.GatewayError):
                self.gb.receive(fixture.A, packet)
            with self.assertRaises(self.messages.GatewayError):
                self.gb._wire_packet(self.gb._load("inbound", packet["id"]))
            with self.assertRaises(self.messages.GatewayError):
                self.ga._wire_packet(self.ga._load("outbound", packet["id"]))
        self.assert_metadata_only(self.ga, "outbound", packet, data)
        self.assert_metadata_only(self.gb, "inbound", packet, data)
        self.assertEqual(self.handoff.status(self.b, packet["id"]), original)
        cleaned = self.files.cleanup(now=expiry)
        self.assertTrue(cleaned["removed"])
        self.assert_metadata_only(self.ga, "outbound", packet, data)
        self.assert_metadata_only(self.gb, "inbound", packet, data)

    def test_short_receiver_retention_cannot_be_renewed_by_a_valid_duplicate(self):
        packet, _ = self.packet()
        short = replace(self.files.product_limits(), retention_seconds=1)
        with mock.patch.object(self.files, "product_limits", return_value=short):
            self.gb.receive(fixture.A, packet)
        original = self.handoff.status(self.b, packet["id"])
        # The sender manifest is still live; the receiving copy has expired.
        with mock.patch.object(self.files.time, "time", return_value=self.messages.time.time() + 3):
            with self.assertRaises(self.messages.GatewayError):
                self.gb.receive(fixture.A, packet)
        self.assertEqual(self.handoff.status(self.b, packet["id"]), original)

    def legacy_record(self, gateway, direction, packet):
        path, record = self.record(gateway, direction, packet["id"])
        record["packet"] = copy.deepcopy(packet)
        record["packet_sha256"] = hashlib.sha256(self.messages._json(packet)).hexdigest()
        self.paths.write_json(str(path), record)
        return path, record

    def test_legacy_cache_is_not_used_after_expiry_and_explicit_compaction_preserves_original(self):
        packet, data = self.packet()
        self.gb.receive(fixture.A, packet)
        owner, generation = {"type": "native", "id": "legacy-reader"}, "legacy-generation"
        claim = self.handoff.claim(self.b, owner, generation, message_id=packet["id"])
        self.handoff.ack(self.b, claim["claim"]["token"], owner, generation)
        original = self.handoff.status(self.b, packet["id"])
        for gateway, direction in ((self.ga, "outbound"), (self.gb, "inbound")):
            path, legacy = self.legacy_record(gateway, direction, packet)
            legacy["archived_at"] = 42
            self.paths.write_json(str(path), legacy)
            raw = path.read_bytes()
            loaded = gateway._load(direction, packet["id"])
            self.assertNotIn("data", loaded["packet"]["file_packet"])
            self.assertEqual(path.read_bytes(), raw)  # Audit reads never rewrite old originals.
            with mock.patch.object(self.files.time, "time", return_value=packet["file_packet"]["manifest"]["expires_at"] + 1):
                with self.assertRaises(self.messages.GatewayError):
                    gateway._wire_packet(loaded)
                self.assertEqual(gateway.compact_legacy_payload(direction, packet["id"])["status"], "compacted")
            _, compacted = self.assert_metadata_only(gateway, direction, packet, data)
            self.assertEqual(compacted["archived_at"], 42)
            self.assertEqual(compacted["fingerprint"], legacy["fingerprint"])
        self.assertEqual(self.handoff.status(self.b, packet["id"]), original)
        with self.assertRaisesRegex(self.messages.GatewayError, "request-archived"):
            self.ga.prepare(self.a, self.fixture.bp, packet["body"], request_id=packet["id"],
                attachments=packet["attachments"], file_packet=packet["file_packet"])

    def test_invalid_legacy_payload_is_not_silently_compacted(self):
        packet, _ = self.packet()
        path, record = self.legacy_record(self.ga, "outbound", packet)
        entry = next(iter(record["packet"]["file_packet"]["data"]))
        record["packet"]["file_packet"]["data"][entry] = "invalid base64"
        record["packet_sha256"] = hashlib.sha256(self.messages._json(record["packet"])).hexdigest()
        self.paths.write_json(str(path), record)
        before = path.read_bytes()
        with self.assertRaises(self.messages.GatewayError):
            self.ga.compact_legacy_payload("outbound", packet["id"])
        self.assertEqual(path.read_bytes(), before)

    def test_expired_file_reply_preserves_original_ack_and_reply_metadata_without_dispatch(self):
        request = self.fixture.prepare("original acknowledged task", request_id="acked-before-expiry", kind="task")
        self.gb.receive(fixture.A, request)
        owner, generation = {"type": "native", "id": "expiry-reader"}, "expiry-generation"
        claim = self.handoff.claim(self.b, owner, generation, message_id=request["id"])
        self.handoff.ack(self.b, claim["claim"]["token"], owner, generation)
        original = self.handoff.status(self.b, request["id"])
        body, reply_id = "file reply metadata remains inspectable", "expired-file-reply"
        manifest = self.files.prepare_inline(self.b, reply_id, body,
            [{"name": "answer.bin", "data": b"expired reply bytes"}], limits=self.files.product_limits())
        full = self.files.export_packet(self.b, manifest["id"], request_id=reply_id, body=body)
        self.gb.prepare(self.b, self.fixture.ap, body, request_id=reply_id, kind="reply",
            reply_to=request["id"], outcome="succeeded", attachments=[self.files.reference(manifest)], file_packet=full)
        with mock.patch.object(self.files.time, "time", return_value=manifest["expires_at"] + 1), \
                mock.patch.object(self.files, "receive", side_effect=AssertionError("status dispatched copies")), \
                mock.patch.object(self.handoff, "store", side_effect=AssertionError("status dispatched a body")):
            status = self.gb.status(fixture.A, request["id"], self.fixture.ap)
            self.assertEqual(status["status"], "acknowledged")
            self.assertTrue(status["acknowledged"])
            self.assertEqual([row["id"] for row in status["replies"]], [reply_id])
            self.assertEqual(status["final_reply"]["id"], reply_id)
            self.assertEqual(status["final_reply"]["outcome"], "succeeded")
            self.assertFalse(status["final_reply"]["payload_available"])
            self.assertEqual(status["final_reply"]["payload_error"], "file-payload-unavailable")
            self.assertNotIn("packet", status["final_reply"])
            with self.assertRaises(self.files.FileError):
                self.files.export_frozen(self.b, manifest["id"], reply_id, body)
        self.assertEqual(self.handoff.status(self.b, request["id"]), original)
        self.assertEqual(self.handoff.status(self.a, reply_id)["status"], "not-found")
