"""Application broker over two real private services and Rust QUIC.

Actors are FAKE NATIVE FILE fixtures: real temporary SQLite threads, rollout
files and registry pointers naming this test process, not running LLM sessions.
Git repositories, service IPC, TLS/QUIC, signatures, policy, receive.check,
inbox claims/ACK and question correlation use their actual implementations.
Only local fixture state/sockets are selected through paths.HOME/socket_path;
no broker response, permission callback, receive gate or network is mocked.
The direct wake-helper case mocks both native adapters to prevent model effects.
These tests do not establish live model-session or physical-machine success.
"""
import copy
from contextlib import closing, contextmanager
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from tests import test_network_service as services
from xsm import (adapters, collaboration, config, directory, envelope, handoff, identity, ledger,
                 inbox, network, network_directory, network_identity, paths,
                 probe, questions, receive, registry)
from xsm.network_transport import find_binary


class NetworkApplicationTests(unittest.TestCase):
    def setUp(self):
        # TempState in earlier suite modules deletes/reimports xsm.*. Rebind
        # fixtures to that current graph, not objects retained at discovery.
        global adapters, collaboration, config, directory, envelope, handoff, identity, ledger
        global inbox, network, network_directory, network_identity, paths, probe, questions, receive, registry, find_binary
        from xsm import (adapters, collaboration, config, directory, envelope, handoff, identity, ledger,
                         inbox, network, network_directory, network_identity, paths,
                         probe, questions, receive, registry)
        from xsm.network_transport import find_binary
        self.binary = find_binary()  # An absent prebuilt engine fails; never skip/build.
        self.temporary = tempfile.TemporaryDirectory(prefix="xapp-", dir="/tmp")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(os.path.realpath(self.temporary.name))
        self.temp_dir = self.root / "tmp"
        self.temp_dir.mkdir(mode=0o700)
        self.outputs, self.secrets = [], [services.CANARY]
        self.a, self.b = self.node("a"), self.node("b")
        self.actor_a = self.actor(self.a, "fixture-a")
        self.actor_b = self.actor(self.b, "fixture-b")
        self.network_id = self.a.cli("init", "application-fixture-network")["network"]["network_id"]
        invitation = self.a.cli("invite")
        ticket = json.loads(Path(invitation["ticket_file"]).read_text())
        self.secrets.append(ticket["secret"])
        joined = self.b.cli("join", "--ticket-file", invitation["ticket_file"])
        self.assertEqual(joined["network"]["network_id"], self.network_id)
        self.repository_id = "application-explicit-repository"

    def assert_no_secrets(self, text):
        for value in self.secrets:
            self.assertNotIn(value, text)

    def node(self, name):
        node = services.ServiceNode(self, name)
        self.addCleanup(node.cleanup)
        return node.start()

    @contextmanager
    def local(self, node):
        # These patches select the real private service socket and fixture state;
        # network.call still performs actual Unix RPC and Rust QUIC downstream.
        with mock.patch.object(paths, "HOME", str(node.home)), \
                mock.patch.object(network, "socket_path", return_value=node.socket):
            yield

    def actor(self, node, sid, cwd=None):
        native_home = node.home / (sid + "-native-home")
        native_home.mkdir(mode=0o700)
        cwd = Path(cwd or node.home / (sid + "-git"))
        if not cwd.exists():
            cwd.mkdir(mode=0o700)
            result = subprocess.run(["git", "init", "-q", "-b", "main", str(cwd)],
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
        row = {"runtime": "codex", "session_id": sid, "home": str(native_home),
               "cwd": str(cwd), "pid": os.getpid(), "lstart": identity.lstart(os.getpid()),
               "app_server": False, "ref": "ref-" + sid, "name": "FAKE native FILE actor",
               "updated": time.time()}
        self.assertTrue(row["lstart"])
        rollout = native_home / (sid + ".jsonl")
        rollout.write_text(json.dumps({"type": "session_meta", "payload": {"id": sid}}) + "\n")
        with closing(sqlite3.connect(native_home / "state_5.sqlite")) as db, db:
            db.execute("create table threads (id text primary key, name text, rollout_path text)")
            db.execute("insert into threads values (?, ?, ?)", (sid, "FAKE native FILE actor", str(rollout)))
        with self.local(node):
            paths.ensure_home()
            config.add_home(str(native_home), "codex")
            paths.write_json(registry._record_path("codex", sid), row)
        return row

    def handle(self, node, actor):
        return network_directory.public_endpoint(actor, node.identity)

    def target(self, node, actor):
        return network_identity.target(self.handle(node, actor))

    def rpc(self, node, op, **kwargs):
        answer = node.rpc(dict(op=op, **kwargs))
        self.assertTrue(answer["ok"], "%s: %s" % (op, answer.get("code")))
        return answer["result"]

    def map_repositories(self):
        for own, actor, peer in ((self.a, self.actor_a, self.b), (self.b, self.actor_b, self.a)):
            self.rpc(own, "map-repository", path=actor["cwd"], repository_id=self.repository_id,
                     peer_keys=[peer.identity])

    def discovered(self):
        answer = self.rpc(self.a, "discover", caller=self.actor_a)
        self.assertEqual(answer["status"], "ok")
        return answer["candidates"]

    def send(self, sender=None, actor=None, target=None, request_id="application-task", **kwargs):
        return self.rpc(sender or self.a, "send", caller=actor or self.actor_a,
                        target=target or self.target(self.b, self.actor_b),
                        id=request_id, body=kwargs.pop("body", "task body 한글\nexact trailing newline\n"),
                        kind=kwargs.pop("kind", "task"), wake=False, **kwargs)

    def queued(self, node, actor, request_id):
        with self.local(node):
            stored = handoff.status(actor, request_id)
            self.assertNotEqual(stored["status"], "not-found")
            parsed = envelope.parse(stored["message"]["content"])
        return stored, parsed

    def consume(self, node, actor, request_id):
        with self.local(node):
            stored = handoff.status(actor, request_id)
            self.assertNotEqual(stored["status"], "not-found", "no canonical inbox message for " + request_id)
            parsed = envelope.parse(stored["message"]["content"])
            decision, reason = receive.check(parsed, actor)
            if decision != "pass":
                admission = node.rpc({"op": "admission", "caller": actor, "id": request_id})
                self.fail("receive.check=%s (%s); service admission ok=%s allowed=%s code=%s" % (
                    decision, reason, admission.get("ok"), admission.get("result", {}).get("allowed"),
                    admission.get("code")))
            taken = receive.take_inbox_claims(actor, message_ids=[request_id])
            self.assertEqual([r["id"] for r in taken["claims"]], [request_id])
            self.assertEqual(len(taken["messages"]), 1)
            claim = taken["claims"][0]
            handoff.ack(actor, claim["token"], claim["owner"], claim["generation"])
            self.assertEqual(handoff.status(actor, request_id)["status"], "acknowledged")
        return parsed

    def select_published(self):
        with self.local(self.b):
            directory.publish(self.actor_b, user_source="test operator publication fixture, not an LLM decision")
        remote = self.handle(self.b, self.actor_b)
        with self.local(self.a):
            collaboration.create(self.actor_a, remote,
                                 "test operator consent fixture for this exact pair; no live user/model interaction")
        selected = self.rpc(self.a, "selection", caller=self.actor_a, target=self.target(self.b, self.actor_b))
        self.assertEqual(selected["status"], "selected")

    def assert_late_consume_refused(self, request_id):
        with self.local(self.b):
            original = handoff.status(self.actor_b, request_id)
            parsed = envelope.parse(original["message"]["content"])
            self.assertEqual(receive.check(parsed, self.actor_b)[0], "block")
            taken = receive.take_inbox_claims(self.actor_b, message_ids=[request_id])
            self.assertEqual(taken["claims"], [])
            after = handoff.status(self.actor_b, request_id)
            self.assertEqual(after["message"]["body"], original["message"]["body"])
            self.assertNotEqual(after["status"], "acknowledged")

    def test_git_discover_resolve_task_native_file_consume_reverse_reply_and_question_correlation(self):
        self.map_repositories()
        candidates = self.discovered()
        self.assertEqual([r["handle"]["session_id"] for r in candidates], [self.actor_b["session_id"]])
        target = candidates[0]["target"]
        self.assertEqual(candidates[0]["repository_id"], self.repository_id)
        resolved = self.rpc(self.a, "resolve", caller=self.actor_a, target=target)
        self.assertEqual(resolved["scope_basis"], "same-repository")
        caps = self.rpc(self.a, "capabilities", caller=self.actor_a, target=target)
        self.assertIn("status", caps["capabilities"])
        sent = self.send(target=target)
        self.assertTrue(sent["delivery"]["stored"])
        self.assertFalse(sent["delivery"]["acknowledged"])
        policy = self.b.home / "network" / "ingress-policy" / "application-task.json"
        self.assertEqual(stat.S_IMODE(policy.stat().st_mode), 0o600)
        self.assertEqual(json.loads(policy.read_text())["repository_id"], self.repository_id)
        parsed = self.consume(self.b, self.actor_b, "application-task")
        self.assertEqual(parsed.header["origin"], "p2p:" + self.a.identity)
        self.assertEqual(parsed.body, "task body 한글\nexact trailing newline\n")
        delivered = self.rpc(self.a, "message-status", caller=self.actor_a, target=target, id="application-task")
        self.assertTrue(delivered["acknowledged"])
        reverse = self.target(self.a, self.actor_a)
        reply = self.send(self.b, self.actor_b, reverse, "application-reply", kind="reply",
                          reply_to="application-task", outcome="succeeded", body="native FILE fixture reply")
        self.assertTrue(reply["delivery"]["stored"])
        self.assertEqual(self.consume(self.a, self.actor_a, "application-reply").header["reply-to"], "application-task")
        with self.local(self.a):
            asked = questions.ask(self.actor_a, target, "correlated fixture question?",
                                  request_id="application-question", wait=0, wake="never")
            self.assertFalse(asked["final"])
            self.assertEqual(asked["replies"], [])
            self.assertNotIn(asked["status"], ("refused", "error", "selection-required"))
            self.assertIn(asked["send_evidence"]["status"], ("sent-unconfirmed", "delivered"),
                          "question dispatch evidence: " + str(asked["send_evidence"]))
        self.consume(self.b, self.actor_b, "application-question")
        self.send(self.b, self.actor_b, reverse, "question-answer", kind="reply",
                  reply_to="application-question", outcome="succeeded", body="exact correlated answer")
        with self.local(self.a):
            # Merely receiving/storing the reply is not native consumption.
            self.assertEqual(questions.status(self.actor_a, "application-question")["replies"], [])
        self.consume(self.a, self.actor_a, "question-answer")
        with self.local(self.a):
            final = questions.status(self.actor_a, "application-question")
            self.assertTrue(final["final"])
            self.assertEqual(final["final_outcome"], "succeeded")
            self.assertEqual([(r["id"], r["body"]) for r in final["replies"]],
                             [("question-answer", "exact correlated answer")])
            self.assertEqual(questions.status(self.actor_a, "application-task")["status"], "not-found")

    def test_invitation_only_neither_reveals_hidden_candidate_nor_allows_send(self):
        self.assertEqual(self.discovered(), [])
        result = self.a.rpc({"op": "send", "caller": self.actor_a,
                             "target": self.target(self.b, self.actor_b), "id": "hidden-task",
                             "body": "membership is not session permission", "kind": "task", "wake": False})
        self.assertFalse(result["ok"])
        with self.local(self.b):
            self.assertEqual(handoff.status(self.actor_b, "hidden-task")["status"], "not-found")
        self.assertFalse((self.b.home / "network" / "ingress-policy" / "hidden-task.json").exists())

    def test_native_handoff_claims_existing_p2p_original_and_ack_suppresses_duplicate(self):
        self.map_repositories()
        request_id = "native-existing-p2p"
        self.assertTrue(self.send(request_id=request_id)["delivery"]["stored"])
        with self.local(self.b):
            original = handoff.status(self.actor_b, request_id)
            self.assertEqual(original["status"], "pending")
            parsed = envelope.parse(original["message"]["content"])
            self.assertEqual(parsed.header["origin"], "p2p:" + self.a.identity)
            self.assertEqual(receive.check(parsed, self.actor_b)[0], "pass")
            ingress_path = self.b.home / "network" / "messages" / "inbound" / (request_id + ".json")
            ingress_bytes = ingress_path.read_bytes()
            owner, generation = receive.consumer_for(self.actor_b)
            claimed = receive._native_handoff(self.actor_b, parsed)
            self.assertIsInstance(claimed, dict)
            self.assertEqual(claimed["id"], request_id)
            self.assertTrue(claimed["token"])
            self.assertEqual(claimed["owner"], owner)
            self.assertEqual(claimed["generation"], generation)
            current = handoff.status(self.actor_b, request_id)
            self.assertEqual(current["status"], "handoff-recorded")
            self.assertEqual(current["claim"]["token"], claimed["token"])
            self.assertEqual(current["claim"]["owner"], owner)
            self.assertEqual(current["claim"]["generation"], generation)
            self.assertEqual(current["message"], original["message"])
            self.assertEqual(current["digest"], original["digest"])
            self.assertEqual(claimed["digest"], original["digest"])
            self.assertEqual(ingress_path.read_bytes(), ingress_bytes)
            handoff.ack(self.actor_b, claimed["token"], owner, generation)
            self.assertIs(receive._native_handoff(self.actor_b, parsed), False)
            acknowledged = handoff.status(self.actor_b, request_id)
            self.assertEqual(acknowledged["status"], "acknowledged")
            self.assertEqual(acknowledged["message"], original["message"])
            self.assertEqual(acknowledged["digest"], original["digest"])
            self.assertEqual(ingress_path.read_bytes(), ingress_bytes)
        remote = self.rpc(self.a, "message-status", caller=self.actor_a,
                          target=self.target(self.b, self.actor_b), id=request_id)
        self.assertTrue(remote["acknowledged"])

    def test_wake_helper_requires_executed_reader_marker_for_same_generation(self):
        """Actual stored P2P message; controlled wake intent, adapters mocked.

        The service receives wake=False and is stopped before adding markers.
        The direct helper's wake=True input is a fixture, not a second network
        admission or evidence of native hooks/LLM sessions executing.
        """
        self.map_repositories()
        request_id = "native-reader-marker"
        self.assertTrue(self.send(request_id=request_id)["delivery"]["stored"])
        self.b.stop()
        with self.local(self.b), mock.patch.object(adapters, "to_codex") as codex, \
                mock.patch.object(adapters, "to_claude") as claude:
            original = handoff.status(self.actor_b, request_id)
            packet = copy.deepcopy(network.message_gateway().ingress_record(request_id)["packet"])
            packet["wake"] = True  # Direct helper intent only; not sent on QUIC.
            daemon = network.Daemon(SimpleNamespace(endpoint_id=self.b.identity))
            self.assertFalse(network.native_reader_ready(self.actor_b))
            daemon.wake_native(packet)
            codex.assert_not_called()
            claude.assert_not_called()
            self.assertEqual(handoff.status(self.actor_b, request_id), original)
            self.assertTrue(network.note_native_reader(self.actor_b))
            self.assertTrue(network.native_reader_ready(self.actor_b))
            daemon.wake_native(packet)
            codex.assert_called_once_with(self.actor_b["home"], self.actor_b["session_id"],
                                          original["message"]["content"])
            claude.assert_not_called()
            self.assertEqual(handoff.status(self.actor_b, request_id)["message"], original["message"])
            codex.reset_mock()
            changed = dict(self.actor_b, native_start="FAKE FILE reader generation changed")
            paths.write_json(registry._record_path("codex", changed["session_id"]), changed)
            self.assertFalse(network.native_reader_ready(changed))
            daemon.wake_native(packet)
            codex.assert_not_called()
            claude.assert_not_called()

    def test_publication_needs_selection_and_malformed_saved_grant_cannot_authorize_send(self):
        with self.local(self.b):
            directory.publish(self.actor_b, user_source="explicit test publication fixture")
        self.assertEqual(len(self.discovered()), 1)
        target = self.target(self.b, self.actor_b)
        denied = self.a.rpc({"op": "send", "caller": self.actor_a, "target": target,
                             "id": "unselected-task", "body": "published is not selected", "kind": "task", "wake": False})
        self.assertEqual(denied, {"ok": False, "code": "selection-required"})
        self.select_published()
        grants = list((self.b.home / "network" / "selections").glob("*.json"))
        self.assertEqual(len(grants), 1)
        original = json.loads(grants[0].read_text())
        for label, mutate in (("signature", lambda g: g.update(signature={"trusted": True})),
                              ("statement", lambda g: g["statement"].update(selection_id=True))):
            with self.subTest(malformed=label):
                bad = copy.deepcopy(original)
                mutate(bad)
                paths.write_json(str(grants[0]), bad)
                answer = self.a.rpc({"op": "send", "caller": self.actor_a, "target": target,
                                     "id": "malformed-" + label, "body": "must not authorize",
                                     "kind": "task", "wake": False})
                self.assertFalse(answer["ok"])
                with self.local(self.b):
                    self.assertEqual(handoff.status(self.actor_b, "malformed-" + label)["status"], "not-found")
        paths.write_json(str(grants[0]), original)
        self.assertTrue(self.send(request_id="valid-selection")["delivery"]["stored"])
        self.consume(self.b, self.actor_b, "valid-selection")

    def test_resolve_refreshes_generation_and_stale_local_caller_is_rejected(self):
        self.map_repositories()
        old = self.rpc(self.a, "resolve", caller=self.actor_a, target=self.target(self.b, self.actor_b))["target"]
        self.actor_b = dict(self.actor_b, native_start="FAKE FILE fixture generation two")
        with self.local(self.b):
            paths.write_json(registry._record_path("codex", self.actor_b["session_id"]), self.actor_b)
        fresh = self.rpc(self.a, "resolve", caller=self.actor_a, target=old["target"])["target"]
        self.assertEqual(fresh["target"], old["target"])
        self.assertNotEqual(fresh["generation"], old["generation"])
        self.assertTrue(self.send(target=old["target"], request_id="fresh-generation")["delivery"]["stored"])
        with self.local(self.b):
            ingress = network.message_gateway().ingress_record("fresh-generation")
            self.assertEqual(ingress["packet"]["receiver"]["generation"], fresh["generation"])
        stale = copy.deepcopy(self.actor_a)
        self.actor_a = dict(self.actor_a, native_start="FAKE sender FILE generation two")
        with self.local(self.a):
            paths.write_json(registry._record_path("codex", self.actor_a["session_id"]), self.actor_a)
        result = self.a.rpc({"op": "send", "caller": stale, "target": old["target"],
                             "id": "stale-caller", "body": "deny stale generation", "kind": "task", "wake": False})
        self.assertEqual(result, {"ok": False, "code": "caller-unverified"})

    def test_member_removal_after_delivery_denies_late_native_file_consume(self):
        self.map_repositories()
        self.assertTrue(self.send(request_id="late-membership")["delivery"]["stored"])
        self.b.cli("remove", self.a.identity)
        self.assert_late_consume_refused("late-membership")

    def test_repository_map_change_after_delivery_denies_late_consume(self):
        self.map_repositories()
        self.assertTrue(self.send(request_id="late-repository")["delivery"]["stored"])
        self.rpc(self.b, "map-repository", path=self.actor_b["cwd"], repository_id="different-repository",
                 peer_keys=[self.a.identity])
        self.assert_late_consume_refused("late-repository")

    def test_local_collaboration_revocation_after_delivery_denies_late_consume(self):
        target_a = self.handle(self.a, self.actor_a)
        with self.local(self.b):
            collaboration.create(self.actor_b, target_a, "local test operator fixture consent")
        # Issue this side's local selection so its own revocation is authoritative.
        with self.local(self.a):
            directory.publish(self.actor_a, user_source="test reverse selection publication fixture")
        self.rpc(self.b, "selection", caller=self.actor_b, target=self.target(self.a, self.actor_a))
        self.assertTrue(self.send(request_id="late-selection")["delivery"]["stored"])
        with self.local(self.b):
            self.assertTrue(collaboration.drop(self.actor_b, target_a))
        self.assert_late_consume_refused("late-selection")

    def test_service_down_preserves_remote_queue_and_local_consume_stays_independent(self):
        self.map_repositories()
        self.assertTrue(self.send(request_id="down-remote")["delivery"]["stored"])
        local_sender = self.actor(self.b, "fixture-local-neighbor", cwd=self.actor_b["cwd"])
        self.b.stop()
        with self.local(self.b):
            original = handoff.status(self.actor_b, "down-remote")
            parsed = envelope.parse(original["message"]["content"])
            self.assertEqual(receive.check(parsed, self.actor_b)[0], "block")
            self.assertEqual(handoff.status(self.actor_b, "down-remote"), original)
            collaboration.create(local_sender, self.actor_b, "explicit local fixture collaboration")
            scope, _ = config.scope_for(local_sender, self.actor_b)
            self.assertTrue(scope)
            body = "local storage and consume without P2P service"
            content = envelope.build(body, msg_id="local-independent", sender=local_sender, scope=scope)
            handoff.store(self.actor_b, {"id": "local-independent", "sender": local_sender,
                "target": self.actor_b, "body": body, "kind": "note", "reply_to": None, "outcome": None,
                "scope": scope, "content": content, "priority": "next", "wake": False})
            handoff.delivery(self.actor_b, "local-independent", "pending", route="mcp-inbox")
            inbox.keep(self.actor_b["session_id"], "local-independent", content, receiver=self.actor_b)
        self.consume(self.b, self.actor_b, "local-independent")
        self.b.start()
        self.consume(self.b, self.actor_b, "down-remote")

    def test_service_unavailable_inbox_take_keeps_pending_without_hold_receipt_or_ack(self):
        """F2: exercise the actual consumer, not only a read-only check call."""
        self.map_repositories()
        request_id = "temporarily-unavailable-consume"
        self.assertTrue(self.send(request_id=request_id)["delivery"]["stored"])
        self.b.stop()
        with self.local(self.b):
            original = handoff.status(self.actor_b, request_id)
            self.assertEqual(original["status"], "pending")
            receipt = ledger.receipt_of(request_id)
            self.assertIsNone(receipt)
            held = self.b.home / paths.HELD
            held_before = {str(p.relative_to(held)): p.read_bytes() for p in held.rglob("*.json")}
            taken = receive.take_inbox_claims(self.actor_b, message_ids=[request_id])
            self.assertEqual(taken["claims"], [])
            current = handoff.status(self.actor_b, request_id)
            self.assertEqual(current["status"], "pending", "temporary service loss must not become held")
            self.assertEqual(current["delivery_state"], original["delivery_state"])
            self.assertEqual(current["delivery_route"], original["delivery_route"])
            self.assertEqual(current["message"], original["message"])
            self.assertEqual(current["digest"], original["digest"])
            self.assertEqual(ledger.receipt_of(request_id), receipt)
            self.assertEqual({str(p.relative_to(held)): p.read_bytes() for p in held.rglob("*.json")}, held_before)
            self.assertNotIn(original["message"]["body"], "\n".join(taken["messages"]))
        self.b.start()
        parsed = self.consume(self.b, self.actor_b, request_id)
        self.assertEqual(parsed.body, original["message"]["body"])
        with self.local(self.b):
            after = handoff.status(self.actor_b, request_id)
            self.assertEqual(after["message"], original["message"])
            self.assertEqual(after["digest"], original["digest"])

    def test_current_same_cid_generation_consumes_original_but_old_and_other_callers_fail(self):
        """F3: the original packet stays old; actual current caller is revalidated."""
        self.map_repositories()
        request_id = "current-generation-consume"
        self.assertTrue(self.send(request_id=request_id)["delivery"]["stored"])
        old_caller = copy.deepcopy(self.actor_b)
        with self.local(self.b):
            original = handoff.status(self.actor_b, request_id)
            self.assertEqual(original["status"], "pending")
            packet_before = network.message_gateway().ingress_record(request_id)["packet"]
            original_generation = packet_before["receiver"]["generation"]
            self.actor_b = dict(self.actor_b, native_start="FAKE FILE current resumed generation")
            paths.write_json(registry._record_path("codex", self.actor_b["session_id"]), self.actor_b)
            self.assertNotEqual(self.handle(self.b, self.actor_b)["generation"], original_generation)
            self.assertEqual(handoff.status(self.actor_b, request_id)["message"], original["message"])
        stale = self.b.rpc({"op": "admission", "caller": old_caller, "id": request_id})
        self.assertIn(stale, ({"ok": False, "code": "caller-unverified"},
                              {"ok": True, "result": {"allowed": False}}))
        other = self.actor(self.b, "fixture-other-reader", cwd=self.actor_b["cwd"])
        self.assertEqual(self.rpc(self.b, "admission", caller=other, id=request_id), {"allowed": False})
        self.assertEqual(self.rpc(self.b, "admission", caller=self.actor_b, id=request_id), {"allowed": True})
        with self.local(self.b):
            self.assertEqual(handoff.status(self.actor_b, request_id)["status"], "pending")
            self.assertIsNone(ledger.receipt_of(request_id))
        parsed = self.consume(self.b, self.actor_b, request_id)
        self.assertEqual(parsed.body, original["message"]["body"])
        with self.local(self.b):
            after = handoff.status(self.actor_b, request_id)
            self.assertEqual(after["message"], original["message"])
            self.assertEqual(after["digest"], original["digest"])
            self.assertEqual(network.message_gateway().ingress_record(request_id)["packet"], packet_before)

    def test_live_service_slow_git_probe_is_unavailable_and_pending_message_consumes_after_path_restore(self):
        """R1: real service-side probe timeout, not a two-second RPC timeout."""
        self.map_repositories()
        request_id = "live-slow-git-consume"
        self.assertTrue(self.send(request_id=request_id)["delivery"]["stored"])
        self.assertEqual(self.rpc(self.b, "admission", caller=self.actor_b, id=request_id), {"allowed": True})
        original_env = self.b.env.copy()
        original_path = original_env.get("PATH", os.defpath)
        parent_path, other_path = os.environ.get("PATH"), self.a.env.get("PATH")
        real_git = shutil.which("git", path=original_path)
        self.assertIsNotNone(real_git)
        shim_dir = self.root / "private-slow-git"
        shim_dir.mkdir(mode=0o700)
        marker = shim_dir / "calls"
        delay = probe.QUICK_TIMEOUT + .5
        shim = shim_dir / "git"
        shim.write_text("#!%s\nimport os, sys, time\n" % sys.executable +
                        "fd = os.open(%r, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)\n" % str(marker) +
                        "os.write(fd, b'probe\\n')\nos.close(fd)\n" +
                        "time.sleep(%r)\n" % delay +
                        "os.execv(%r, [%r] + sys.argv[1:])\n" % (real_git, real_git))
        shim.chmod(0o700)
        map_path = self.b.home / "network" / "repositories" / "repositories.json"
        original_map = map_path.read_bytes()
        with self.local(self.b):
            original = handoff.status(self.actor_b, request_id)
            self.assertEqual(original["status"], "pending")
        self.b.stop()
        self.b.env["PATH"] = str(shim_dir) + os.pathsep + original_path
        try:
            self.b.start()
            self.assertIsNone(self.b.process.poll())
            self.assertTrue(self.b.rpc({"op": "status"})["ok"])
            # ServiceNode.rpc has a five-second transport timeout. A concrete
            # error response here must precede inbound_record's two-second RPC
            # deadline and follow the one-second internal QUICK_TIMEOUT.
            started = time.monotonic()
            admission = self.b.rpc({"op": "admission", "caller": self.actor_b, "id": request_id})
            elapsed = time.monotonic() - started
            self.slow_git_observation = {"direct_admission": admission, "elapsed_seconds": elapsed,
                "quick_timeout_seconds": probe.QUICK_TIMEOUT, "shim_delay_seconds": delay,
                "service_alive": self.b.process.poll() is None,
                "shim_calls": marker.read_text().count("probe\n") if marker.exists() else 0}
            self.assertEqual(admission, {"ok": False, "code": "admission-unavailable"})
            self.assertGreaterEqual(self.slow_git_observation["shim_calls"], 1)
            self.assertGreaterEqual(elapsed, probe.QUICK_TIMEOUT * .7)
            self.assertLess(elapsed, 2.0, "must observe the service's internal probe failure, not RPC expiry")
            self.assertIsNone(self.b.process.poll())
            with self.local(self.b):
                held = self.b.home / paths.HELD
                held_before = {str(p.relative_to(held)): p.read_bytes() for p in held.rglob("*.json")}
                self.assertIsNone(ledger.receipt_of(request_id))
                taken = receive.take_inbox_claims(self.actor_b, message_ids=[request_id])
                self.assertEqual(taken["claims"], [])
                current = handoff.status(self.actor_b, request_id)
                self.assertEqual(current["status"], "pending")
                self.assertEqual(current["delivery_state"], "pending")
                self.assertEqual(current["delivery_route"], original["delivery_route"])
                self.assertEqual(current["message"], original["message"])
                self.assertEqual(current["digest"], original["digest"])
                self.assertIsNone(ledger.receipt_of(request_id))
                self.assertEqual({str(p.relative_to(held)): p.read_bytes() for p in held.rglob("*.json")}, held_before)
                self.assertNotIn(original["message"]["body"], "\n".join(taken["messages"]))
                self.slow_git_observation.update(pending_preserved=True, held_copies=0, receipt_created=False,
                                                 acknowledged=False)
            self.assertEqual(map_path.read_bytes(), original_map)
        finally:
            self.b.stop()
            self.b.env.clear()
            self.b.env.update(original_env)
            self.b.start()
        self.assertEqual(os.environ.get("PATH"), parent_path)
        self.assertEqual(self.a.env.get("PATH"), other_path)
        self.assertEqual(map_path.read_bytes(), original_map)
        self.assertEqual(self.rpc(self.b, "admission", caller=self.actor_b, id=request_id), {"allowed": True})
        parsed = self.consume(self.b, self.actor_b, request_id)
        self.assertEqual(parsed.body, original["message"]["body"])
        with self.local(self.b):
            consumed = handoff.status(self.actor_b, request_id)
            self.assertEqual(consumed["message"], original["message"])
            self.assertEqual(consumed["digest"], original["digest"])
        self.slow_git_observation.update(restored_same_id_consumed=True, parent_and_other_path_unchanged=True)

    def test_absent_receiver_map_and_changed_signed_selection_is_terminal_refusal_not_unavailable(self):
        """R2: missing map is known absence; grant mismatch is a real denial."""
        request_id = "absent-map-known-refusal"
        receiver_map = self.b.home / "network" / "repositories"
        self.assertFalse(receiver_map.exists())
        # A advertises a repository ID, while B has never created any map.
        self.rpc(self.a, "map-repository", path=self.actor_a["cwd"],
                 repository_id=self.repository_id, peer_keys=[self.b.identity])
        self.select_published()
        self.assertFalse(receiver_map.exists())
        self.assertTrue(self.send(request_id=request_id)["delivery"]["stored"])
        self.assertEqual(self.rpc(self.b, "admission", caller=self.actor_b, id=request_id), {"allowed": True})
        grant_files = list((self.b.home / "network" / "selections").glob("*.json"))
        self.assertEqual(len(grant_files), 1)
        first_grant = json.loads(grant_files[0].read_text())
        ingress_file = self.b.home / "network" / "messages" / "inbound" / (request_id + ".json")
        ingress_bytes = ingress_file.read_bytes()
        with self.local(self.b):
            original = handoff.status(self.actor_b, request_id)
            self.assertEqual(original["delivery_state"], "pending")
        # Replace B's retained grant via another genuine signed selection over
        # QUIC. Do not forge a signature or rewrite the original ingress policy.
        with self.local(self.a):
            remote = self.handle(self.b, self.actor_b)
            self.assertTrue(collaboration.drop(self.actor_a, remote))
            collaboration.create(self.actor_a, remote, "replacement exact-pair test consent fixture")
        self.assertEqual(self.rpc(self.a, "selection", caller=self.actor_a,
                                  target=self.target(self.b, self.actor_b))["status"], "selected")
        replacement_grant = json.loads(grant_files[0].read_text())
        self.assertNotEqual(replacement_grant, first_grant)
        self.assertNotEqual(replacement_grant["statement"]["evidence_sha256"],
                            first_grant["statement"]["evidence_sha256"])
        policy = json.loads((self.b.home / "network" / "ingress-policy" / (request_id + ".json")).read_text())
        self.assertEqual(policy["authorization"], first_grant)
        self.assertFalse(receiver_map.exists())
        admission = self.b.rpc({"op": "admission", "caller": self.actor_b, "id": request_id})
        self.absent_map_observation = {"direct_admission": admission,
            "receiver_map_root_exists": receiver_map.exists(), "replacement_signed_grant_changed": True,
            "service_alive": self.b.process.poll() is None}
        self.assertEqual(admission, {"ok": True, "result": {"allowed": False}})
        with self.local(self.b):
            taken = receive.take_inbox_claims(self.actor_b, message_ids=[request_id])
            self.assertEqual(taken["claims"], [])
            current = handoff.status(self.actor_b, request_id)
            self.assertIn(current["delivery_state"], ("held", "refused"))
            self.assertEqual(current["message"], original["message"])
            self.assertEqual(current["digest"], original["digest"])
            receipt = ledger.receipt_of(request_id)
            self.assertIn(receipt["decision"], ("held", "blocked"))
            self.assertEqual(ingress_file.read_bytes(), ingress_bytes)
            self.absent_map_observation.update(delivery_state=current["delivery_state"],
                                               receipt_decision=receipt["decision"], original_preserved=True)
        delivery = self.rpc(self.a, "message-status", caller=self.actor_a,
                            target=self.target(self.b, self.actor_b), id=request_id)
        self.assertIn(delivery["status"], ("held", "refused"))
        self.assertFalse(delivery["acknowledged"])
        self.assertFalse(receiver_map.exists())
        self.absent_map_observation.update(public_delivery_status=delivery["status"], acknowledged=False)


if __name__ == "__main__":
    unittest.main()
