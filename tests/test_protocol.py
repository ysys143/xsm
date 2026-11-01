"""Public protocol behavior, using real canonical storage and isolated homes."""
import io
import json
import os
import sys
import time
from unittest import mock

from tests.test_xsm import TempState


class ProtocolFixture(TempState):
    def setUp(self):
        super().setUp()
        from xsm.protocol import Connection
        self.connection = Connection()
        self.addCleanup(self.connection.close)
        self.connection.dispatch("initialize", {"protocolVersion": "1"})

    def tearDown(self):
        self.connection.close()
        super().tearDown()

    def open(self, conversation="a", profile="p", runtime="fixture"):
        return self.connection.dispatch("session.open", {
            "runtime": runtime, "profile": profile,
            "conversation": conversation, "cwd": self.tmp,
            "capabilities": ["messaging", "inbox", "events"]})

    def operation(self, session, name, **args):
        return self.connection.dispatch("operation.call", {
            "session": session["session"], "operation": name, "arguments": args})


class ProtocolTest(ProtocolFixture):
    def test_open_separates_profiles_and_opaque_handles(self):
        a, b = self.open(), self.open(profile="second")
        self.assertNotEqual(a["session"], b["session"])
        self.assertNotEqual(a["ref"], b["ref"])
        self.assertNotIn(self.tmp, json.dumps(a))

    def test_connection_handle_cannot_select_another_connection(self):
        from xsm.protocol import Connection, ProtocolError
        other = Connection()
        other.dispatch("initialize", {"protocolVersion": "1"})
        with self.assertRaises(ProtocolError):
            other.dispatch("session.update", {"session": self.open()["session"], "state": "busy"})

    def test_generic_host_uses_shared_service_without_mcp_transport(self):
        from xsm.operations import OperationService
        self.assertNotIn("xsm.mcp", sys.modules)
        opened = self.open()
        host = self.connection.sessions[opened["session"]]
        self.assertIsInstance(host, OperationService)
        self.assertEqual(host._invoke_operation.__func__.__module__, "xsm.operations")

    def test_native_impersonation_and_identity_replacement_rejected(self):
        from xsm.protocol import ProtocolError
        for runtime in ("claude", "codex", "../bad", "remote:foo"):
            with self.assertRaises(ProtocolError):
                self.open(runtime=runtime)
        a = self.open()
        with self.assertRaises(ProtocolError):
            self.connection.dispatch("session.update", {"session": a["session"], "cwd": "/"})

    def test_live_duplicate_refused_close_reopens_same_address(self):
        from xsm.protocol import ProtocolError
        a = self.open()
        with self.assertRaises(ProtocolError):
            self.open()
        record = self.connection.sessions[a["session"]].record
        self.connection.dispatch("session.close", {"session": a["session"]})
        from xsm import registry
        self.assertEqual(registry.by_session("fixture", record["session_id"])["state"], "ended")
        b = self.open()
        self.assertEqual(a["ref"], b["ref"])
        self.assertNotEqual(a["session"], b["session"])
        self.assertNotEqual(a["generation"], b["generation"])

    def test_user_answer_cannot_be_fabricated(self):
        from xsm.protocol import ProtocolError
        a = self.open()
        with self.assertRaises(ProtocolError) as caught:
            self.connection.dispatch("decision.response", {"session": a["session"], "answer": "yes"})
        self.assertEqual(caught.exception.code, -32004)

    def test_unknown_operation_and_arguments_rejected(self):
        from xsm.protocol import ProtocolError
        a = self.open()
        for name, args in [("shell", {}), ("xsm_send", {"sender": "someone"}),
                           ("xsm_send", {"wake": "always"}), ("xsm_inbox", {"wait": True})]:
            with self.assertRaises(ProtocolError):
                self.operation(a, name, **args)

    def test_protocol_send_does_not_call_codex_and_roundtrips_ack(self):
        from xsm import adapters, handoff
        a, b = self.open(), self.open("b")
        with mock.patch.object(adapters, "to_codex", side_effect=AssertionError("wrong runtime")):
            result = self.operation(a, "xsm_send", target="ref:" + b["ref"], text="hello", wait=0)
        self.assertIn("stored", str(result))
        pack = self.operation(b, "xsm_inbox")
        self.assertEqual(len(pack["claims"]), 1, pack)
        self.assertIn("hello", str(pack["messages"]))
        claim = pack["claims"][0]
        rec = self.connection.sessions[b["session"]].record
        self.assertNotEqual(handoff.status(rec, claim["id"])["status"], "acknowledged")
        self.operation(b, "xsm_ack", tokens=[claim["token"]])
        self.assertEqual(handoff.status(rec, claim["id"])["status"], "acknowledged")

    def test_fyi_never_emits_event_but_can_be_consumed(self):
        a, b = self.open(), self.open("b")
        self.connection.dispatch("events.subscribe", {"session": b["session"]})
        self.operation(a, "xsm_send", target="ref:" + b["ref"], text="later", wake="never", wait=0)
        self.assertEqual(list(self.connection.events()), [])
        pack = self.operation(b, "xsm_inbox")
        self.assertIn("later", str(pack["messages"]))
        self.assertEqual(len(pack["claims"]), 1)

    def test_notification_does_not_claim_and_delivery_report_does_not_ack(self):
        from xsm import handoff
        a, b = self.open(), self.open("b")
        self.connection.dispatch("events.subscribe", {"session": b["session"]})
        self.operation(a, "xsm_send", target="ref:" + b["ref"], text="now", wait=0)
        events = list(self.connection.events())
        self.assertEqual(len(events), 1)
        mid = events[0]["params"]["ids"][0]
        record = self.connection.sessions[b["session"]].record
        self.assertEqual(handoff.status(record, mid)["status"], "pending")
        report = self.connection.dispatch("delivery.report", {"session": b["session"], "id": mid, "state": "queued"})
        self.assertFalse(report["acknowledged"])
        self.assertEqual(handoff.status(record, mid)["status"], "pending")
        self.assertEqual(list(self.connection.events()), [])

    def test_fetch_release_and_queue_report_never_forge_native_consumption(self):
        from xsm import ledger
        a, b = self.open(), self.open("b")
        self.operation(a, "xsm_send", target="ref:" + b["ref"], text="native admission may fail", wait=0)
        pack = self.operation(b, "xsm_inbox")
        mid = pack["claims"][0]["id"]
        self.assertFalse(ledger.evidence_of(mid)["runtime_reached"])
        self.assertIsNone(ledger.receipt_of(mid))
        self.connection.dispatch("inbox.release", {"session": b["session"], "tokens": [pack["claims"][0]["token"]]})
        self.assertFalse(ledger.evidence_of(mid)["runtime_reached"])
        self.connection.dispatch("delivery.report", {"session": b["session"], "id": mid, "state": "queued"})
        self.assertFalse(ledger.evidence_of(mid)["runtime_reached"])
        current = self.operation(b, "xsm_inbox")
        self.operation(b, "xsm_ack", tokens=[current["claims"][0]["token"]])
        self.assertTrue(ledger.evidence_of(mid)["runtime_reached"])
        self.assertEqual(ledger.receipt_of(mid)["decision"], "delivered")

    def test_native_admission_requires_own_claim_and_is_separate_from_consumption(self):
        from xsm import ledger, handoff
        from xsm.protocol import ProtocolError
        a, b = self.open(), self.open("b")
        self.operation(a, "xsm_send", target="ref:" + b["ref"], text="native admitted", wait=0)
        claim = self.operation(b, "xsm_inbox")["claims"][0]
        for token in (None, "wrong"):
            with self.assertRaises(ProtocolError):
                self.connection.dispatch("delivery.report", {"session": b["session"], "id": claim["id"],
                    "state": "admitted", "token": token})
        self.assertFalse(ledger.evidence_of(claim["id"])["runtime_reached"])
        self.connection.dispatch("delivery.report", {"session": b["session"], "id": claim["id"],
            "state": "admitted", "token": claim["token"]})
        self.assertTrue(ledger.evidence_of(claim["id"])["runtime_reached"])
        receiver = self.connection.sessions[b["session"]].record
        self.assertNotEqual(handoff.status(receiver, claim["id"])["status"], "acknowledged")

    def test_committed_consumption_survives_receipt_mirror_failure(self):
        from xsm import receive, ledger
        a, b = self.open(), self.open("b")
        self.operation(a, "xsm_send", target="ref:" + b["ref"], text="committed read", wait=0)
        claim = self.operation(b, "xsm_inbox")["claims"][0]
        with mock.patch.object(receive, "protocol_receipt", side_effect=OSError("mirror interrupted")):
            with self.assertRaises(OSError):
                self.operation(b, "xsm_ack", tokens=[claim["token"]])
        self.assertIsNone(ledger.receipt_of(claim["id"]))
        with mock.patch.object(ledger.time, "sleep", side_effect=AssertionError("committed ACK must not wait")):
            self.assertTrue(ledger.wait_for(claim["id"], 1)["delivery"]["acknowledged"])
        self.assertEqual(self.operation(b, "xsm_inbox")["claims"], [])

    def test_closed_connection_preserves_unacknowledged_original(self):
        from xsm import handoff
        a, b = self.open(), self.open("b")
        self.operation(a, "xsm_send", target="ref:" + b["ref"], text="retain", wait=0)
        record = dict(self.connection.sessions[b["session"]].record)
        self.connection.close()
        self.assertTrue(handoff.pending_ids(record))

    def test_uninitialized_and_unsupported_version(self):
        from xsm.protocol import Connection, ProtocolError
        c = Connection()
        for method, args in [("operations/list", {}), ("initialize", {"protocolVersion": "999"})]:
            with self.assertRaises(ProtocolError):
                c.dispatch(method, args)

    def test_omitted_wait_cannot_inherit_legacy_blocking_default(self):
        a = self.open()
        host = self.connection.sessions[a["session"]]
        with mock.patch.object(host, "call", return_value="{}") as call:
            self.operation(a, "xsm_send", target="ref:123456", text="hello")
        self.assertEqual(call.call_args[0][1]["wait"], 0)

    def test_continuous_requests_do_not_starve_event_polling(self):
        from xsm.protocol import serve, Connection
        ticks = iter([i * 0.3 for i in range(200)])
        request = json.dumps({"jsonrpc": "2.0", "id": 1,
                              "method": "initialize", "params": {"protocolVersion": "1"}})
        out = io.StringIO()
        with mock.patch("xsm.protocol.time.monotonic", side_effect=lambda: next(ticks)), \
                mock.patch.object(Connection, "events", return_value=iter(())) as events:
            serve(io.StringIO((request + "\n") * 12), out)
        self.assertGreater(events.call_count, 1)

    def test_stdio_recovers_after_bad_json_and_unknown_method(self):
        from xsm.protocol import serve
        inp = io.StringIO('broken\n' + json.dumps({"jsonrpc": "2.0", "id": 1,
            "method": "initialize", "params": {"protocolVersion": "1"}}) + '\n')
        out = io.StringIO()
        self.assertEqual(serve(inp, out), 0)
        results = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual(results[0]["error"]["code"], -32700)
        self.assertEqual(results[1]["result"]["protocolVersion"], "1")
