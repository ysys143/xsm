"""Actual broker ingress with FILE actors; native exports are mocked explicitly.

This does not run an LLM or establish idle wake. It checks the boundary before
any native side effect and prevents a parsed header from redirecting replies.
"""
import unittest
from pathlib import Path
from unittest import mock

from tests import test_network_application as application


class NetworkReceiveTests(unittest.TestCase):
    def setUp(self):
        self.case = application.NetworkApplicationTests(
            "test_git_discover_resolve_task_native_file_consume_reverse_reply_and_question_correlation")
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()
        self.case.map_repositories()

    def test_forged_reply_address_cannot_reuse_an_admitted_id_and_body(self):
        from xsm import envelope, network, receive
        case = self.case
        case.send(request_id="header-binding")
        stored, parsed = case.queued(case.b, case.actor_b, "header-binding")
        with case.local(case.b):
            self.assertEqual(receive.check(parsed, case.actor_b)[0], "pass")
            forged = envelope.parse(stored["message"]["content"])
            forged.header["ref"] = forged.header["ref"].replace(case.a.identity, "f" * 64)
            self.assertNotEqual(forged.header["ref"], parsed.header["ref"])
            self.assertIsNone(network.inbound_record(forged, case.actor_b))
            self.assertEqual(receive.check(forged, case.actor_b)[0], "block")

    def test_old_hook_unknown_origin_receipt_cannot_hide_an_admitted_pending_original(self):
        from xsm import handoff, inbox, ledger, paths, receive
        case = self.case
        request_id = "old-hook-p2p-copy"
        case.send(request_id=request_id)
        original, parsed = case.queued(case.b, case.actor_b, request_id)
        reason = "remote message from %s was not received by this machine's xsm" % parsed.header["origin"]
        with case.local(case.b):
            # Exact receipt shape observed from the installed pre-P2P hook.
            # Its separate held copy remains untouched; the admitted canonical
            # original must still pass this version's actual receive gate.
            held_id = receive.hold("codex", reason, {}, case.actor_b, parsed)
            held_path = Path(paths.path(paths.HELD, held_id + ".json"))
            held_bytes = held_path.read_bytes()
            ledger.receipt(request_id, "held", case.actor_b, reason)
            original_receipt = ledger.receipt_of(request_id)
            self.assertIn(request_id, handoff.pending_ids(case.actor_b))
            self.assertEqual(inbox.pending_fields(case.actor_b)["inbox_pending"], 1)
            self.assertEqual(ledger.receipt_of(request_id), original_receipt)
            taken = receive.take_inbox_claims(case.actor_b, message_ids=[request_id])
            self.assertEqual(len(taken["claims"]), 1, taken)
            self.assertIn(parsed.body, taken["messages"][0])
            current = handoff.status(case.actor_b, request_id)
            self.assertEqual(current["message"], original["message"])
            self.assertEqual(current["digest"], original["digest"])
            self.assertNotEqual(current["status"], "acknowledged")
            self.assertEqual(held_path.read_bytes(), held_bytes)
            claim = taken["claims"][0]
            handoff.ack(case.actor_b, claim["token"], claim["owner"], claim["generation"])
            self.assertEqual(handoff.status(case.actor_b, request_id)["status"], "acknowledged")
            self.assertEqual(held_path.read_bytes(), held_bytes)

    def test_old_hook_recheck_preserves_real_holds_and_current_membership_refusal(self):
        from xsm import handoff, ledger, receive
        case = self.case
        ids = ("real-canonical-hold", "bound-refusal", "revoked-after-old-hook")
        messages = {}
        for request_id in ids:
            case.send(request_id=request_id)
            messages[request_id] = case.queued(case.b, case.actor_b, request_id)
        with case.local(case.b):
            for request_id, (_, parsed) in messages.items():
                reason = "remote message from %s was not received by this machine's xsm" % parsed.header["origin"]
                ledger.receipt(request_id, "held", case.actor_b, reason,
                               req_digest=receive._req_digest(parsed) if request_id == ids[1] else None)
            handoff.delivery(case.actor_b, ids[0], "held", route="mcp-inbox")
            bound_receipt = ledger.receipt_of(ids[1])
            taken = receive.take_inbox_claims(case.actor_b, message_ids=list(ids[:2]))
            self.assertEqual(taken["claims"], [])
            self.assertEqual(handoff.status(case.actor_b, ids[0])["delivery_state"], "held")
            self.assertEqual(ledger.receipt_of(ids[1]), bound_receipt)
        case.b.cli("remove", case.a.identity)
        with case.local(case.b):
            taken = receive.take_inbox_claims(case.actor_b, message_ids=[ids[2]])
            self.assertEqual(taken["claims"], [])
            current = handoff.status(case.actor_b, ids[2])
            self.assertNotEqual(current["status"], "acknowledged")
            self.assertEqual(current["message"], messages[ids[2]][0]["message"])
            self.assertIn(current["delivery_state"], ("held", "refused"))

    def test_reply_poll_rechecks_old_copy_receipt_without_consuming_or_ignoring_revocation(self):
        from xsm import handoff, ledger, questions, receive
        case = self.case
        for suffix in ("allowed", "revoked"):
            request_id, reply_id = "poll-old-copy-" + suffix, "old-copy-answer-" + suffix
            with case.local(case.a):
                asked = questions.ask(case.actor_a, case.target(case.b, case.actor_b),
                                      "exact question", request_id=request_id, wait=0, wake="never")
                self.assertFalse(asked["final"])
            case.consume(case.b, case.actor_b, request_id)
            case.send(case.b, case.actor_b, case.target(case.a, case.actor_a), reply_id,
                      kind="reply", reply_to=request_id, outcome="succeeded", body="exact answer")
            original, parsed = case.queued(case.a, case.actor_a, reply_id)
            with case.local(case.a):
                reason = "remote message from %s was not received by this machine's xsm" % parsed.header["origin"]
                ledger.receipt(reply_id, "held", case.actor_a, reason)
                old_receipt = ledger.receipt_of(reply_id)
                if suffix == "revoked":
                    case.a.cli("remove", case.b.identity)
                self.assertEqual(receive.poll_replies(case.actor_a, request_id), 1 if suffix == "allowed" else 0)
                final = questions.status(case.actor_a, request_id)
                self.assertEqual(final["final"], suffix == "allowed")
                if suffix == "allowed":
                    self.assertEqual(final["replies"][0]["body"], "exact answer")
                current = handoff.status(case.actor_a, reply_id)
                self.assertEqual(current["status"], "pending")
                self.assertEqual(current["message"], original["message"])
                self.assertIsNone(current["claim"])
                self.assertEqual(ledger.receipt_of(reply_id), old_receipt)

    def test_conflicting_id_is_refused_without_reading_an_older_messages_delivery(self):
        from xsm import ledger, paths, send
        case = self.case
        with case.local(case.a):
            msg_id = "previous-local-delivered"
            ledger.queued(msg_id, case.actor_a, case.actor_a, "repo:fixture", "task", "old local body")
            ledger.receipt(msg_id, "delivered", case.actor_a, "older local delivery fixture")
            before = {suffix: Path(paths.path(paths.LEDGER, msg_id + suffix)).read_bytes()
                      for suffix in (".json", ".recv.json")}
            result = send.send(case.target(case.b, case.actor_b), "new remote body", sender=case.actor_a,
                               kind="task", msg_id=msg_id, wait=1, wake=False)
            self.assertEqual(result.status, "refused", result.as_dict())
            self.assertEqual(result.reason, "message-id-conflict")
            for suffix, raw in before.items():
                with open(paths.path(paths.LEDGER, msg_id + suffix), "rb") as stream:
                    self.assertEqual(stream.read(), raw)
            direct = case.a.rpc({"op": "send", "caller": case.actor_a,
                                 "target": case.target(case.b, case.actor_b), "id": msg_id,
                                 "body": "new remote body", "kind": "task", "wake": False})
            self.assertEqual(direct, {"ok": False, "code": "message-id-conflict"})
            case.a.stop()
            offline = send.send(case.target(case.b, case.actor_b), "new remote body", sender=case.actor_a,
                                kind="task", msg_id=msg_id, wait=1, wake=False)
            self.assertEqual(offline.status, "refused", offline.as_dict())
            self.assertEqual(offline.reason, "message-id-conflict")
        with case.local(case.b):
            from xsm import handoff
            self.assertEqual(handoff.status(case.actor_b, msg_id)["status"], "not-found")

    def test_reusable_invitation_expiry_and_revocation_run_through_public_cli(self):
        import hashlib
        import json
        import time
        case = self.case
        before = time.time()
        issued = case.a.cli("invite", "--expires", "120")
        ticket = json.loads(Path(issued["ticket_file"]).read_text())
        case.secrets.append(ticket["secret"])
        key = hashlib.sha256(ticket["secret"].encode()).hexdigest()
        status = case.a.cli("status")
        invitation = next(r for r in status["network"]["invites"] if r["invite_hash"] == key)
        self.assertTrue(invitation["reusable"])
        self.assertGreaterEqual(invitation["expires_at"], before + 120)
        self.assertLess(invitation["expires_at"], time.time() + 121)
        self.assertEqual(case.a.cli("revoke-invite", key)["status"], "revoked")
        invitation = next(r for r in case.a.cli("status")["network"]["invites"] if r["invite_hash"] == key)
        self.assertTrue(invitation["revoked"])

    def test_active_members_learn_routes_and_communicate_with_founder_offline(self):
        import json
        import time
        case = self.case
        third = case.node("third")
        invitation = case.a.cli("invite")
        ticket = json.loads(Path(invitation["ticket_file"]).read_text())
        case.secrets.append(ticket["secret"])
        third.cli("join", "--ticket-file", invitation["ticket_file"])
        deadline = time.monotonic() + 7
        while time.monotonic() < deadline:
            if third.identity in case.b.cli("status")["known_peers"] \
                    and case.b.identity in third.cli("status")["known_peers"]:
                break
            time.sleep(.1)
        else:
            self.fail("non-founder members did not learn each other's authenticated-key routes")
        case.a.stop()
        self.assertEqual(case.rpc(case.b, "ping", peer=third.identity)["endpoint_id"], third.identity)
        self.assertEqual(case.rpc(third, "ping", peer=case.b.identity)["endpoint_id"], case.b.identity)

    def test_local_question_and_reply_complete_with_all_network_services_stopped(self):
        from xsm import network, questions, send
        case = self.case
        local_peer = case.actor(case.a, "local-only-reviewer", cwd=case.actor_a["cwd"])
        case.a.stop()
        case.b.stop()
        with case.local(case.a):
            self.assertFalse(network.available())
            asked = questions.ask(case.actor_a, "codex:" + local_peer["session_id"],
                                  "local question while networking is stopped", wait=0,
                                  request_id="local-without-network", wake="never")
            self.assertEqual(asked["status"], "pending", asked)
        case.consume(case.a, local_peer, "local-without-network")
        with case.local(case.a):
            replied = send.send("codex:" + case.actor_a["session_id"], "local final answer",
                                sender=local_peer, kind="reply", reply_to="local-without-network",
                                outcome="succeeded", msg_id="local-without-network-answer", wake=False)
            self.assertEqual(replied.status, "stored", replied.as_dict())
        case.consume(case.a, case.actor_a, "local-without-network-answer")
        with case.local(case.a):
            answer = questions.status(case.actor_a, "local-without-network")
            self.assertTrue(answer["final"])
            self.assertEqual(answer["final_outcome"], "succeeded")
            self.assertEqual(answer["replies"][-1]["body"], "local final answer")
            self.assertFalse(network.available())

    def test_native_hook_service_outage_preserves_original_without_permanent_receipt(self):
        from xsm import handoff, ledger, paths, receive
        case = self.case
        request_id = "hook-temporary-outage"
        case.send(request_id=request_id)
        original, parsed = case.queued(case.b, case.actor_b, request_id)
        case.b.stop()
        with case.local(case.b):
            output = receive._gate({"session_id": case.actor_b["session_id"],
                                    "cwd": case.actor_b["cwd"], "hook_event_name": "UserPromptSubmit"},
                                   "codex", case.actor_b, parsed)
            self.assertIn("temporarily unavailable", str(output))
            self.assertIsNone(ledger.receipt_of(request_id))
            current = handoff.status(case.actor_b, request_id)
            self.assertEqual(current["status"], "pending")
            self.assertEqual(current["message"], original["message"])
            self.assertEqual(current["digest"], original["digest"])
            self.assertFalse(list(Path(paths.path(paths.HELD)).glob("*.json")))
        case.b.start()
        case.consume(case.b, case.actor_b, request_id)

    def test_native_hook_outage_after_initial_check_also_leaves_pending_original(self):
        from xsm import handoff, ledger, receive
        case = self.case
        request_id = "hook-check-claim-race"
        case.send(request_id=request_id)
        original, parsed = case.queued(case.b, case.actor_b, request_id)
        native = receive._native_handoff

        def disappear(me, message):
            case.b.stop()
            return native(me, message)

        with case.local(case.b), mock.patch.object(receive, "_native_handoff", side_effect=disappear):
            output = receive._gate({"session_id": case.actor_b["session_id"],
                                    "cwd": case.actor_b["cwd"], "hook_event_name": "UserPromptSubmit"},
                                   "codex", case.actor_b, parsed)
            self.assertIn("temporarily unavailable", str(output))
            self.assertIsNone(ledger.receipt_of(request_id))
            current = handoff.status(case.actor_b, request_id)
            self.assertEqual(current["status"], "pending")
            self.assertEqual(current["message"], original["message"])
            self.assertEqual(current["delivery_route"], "mcp-inbox")
        case.b.start()
        case.consume(case.b, case.actor_b, request_id)
