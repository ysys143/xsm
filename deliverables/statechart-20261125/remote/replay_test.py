"""Replay of the TLC paths in XsmRemote.tla against xsm's real code.

Two machines in one process, as tests/test_handover.py and tests/test_network_messages.py do:
  M1 holds the sessions A (old), B (successor), C (B's successor) and its own XSM state;
  M2 holds the asking session Q and its own XSM state.
`on(machine)` switches paths.HOME, so every real call (gateway, handover, questions)
reads and writes the state of the machine it runs on.

Mocked, and nothing else:
  * the transport between machines: network.call (hand_over -> service) and Daemon.rpc
    (service -> peer) are replaced by functions that run the receiving side's real code
    (handover.receive_testimony) under the other machine's state, or fail / hold the message;
  * gate decisions: the Gateway permission callbacks (M1 admits the question; M2's own
    permission for a reply is `False`, so only the reverse-reply check can let a reply in).
Run from the repository root:
  python3 <this file> -v Replay.test_x
"""
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from contextlib import closing, contextmanager
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.getcwd())

from xsm import (config, handover, handoff, identity, network, network_directory,  # noqa: E402
                 network_identity, network_messages as messages, paths, questions, registry)

M1, M2, M3 = "1" * 64, "2" * 64, "3" * 64


class Replay(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="xsm-remote-replay-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(os.path.realpath(tmp.name))
        self.states = {M1: str(self.root / "state-m1"), M2: str(self.root / "state-m2")}
        patch = mock.patch.object(paths, "HOME", self.states[M1])
        patch.start()
        self.addCleanup(patch.stop)
        self.start = identity.lstart(os.getpid()) or "native-fixture-start"
        self.cwd = self.root / "work"
        self.cwd.mkdir()
        self.homes = {}
        for machine in (M1, M2):
            with self.on(machine):
                paths.ensure_home()
                home = self.root / ("native-home-" + machine[0])
                home.mkdir()
                config.add_home(str(home), "codex")
                self.homes[machine] = home
        # M1 holds A, B, C; M2 holds Q.
        self.rows = {}
        for name, machine in (("old-a", M1), ("succ-b", M1), ("succ-c", M1), ("asker-q", M2)):
            self.rows[name] = self.session(name, machine)
        self.m2_permission = mock.Mock(name="m2_local_permission_fixture", return_value=False)
        self.g1 = messages.Gateway(self.root / "gateway-m1", M1, mock.Mock(return_value=True))
        self.g2 = messages.Gateway(self.root / "gateway-m2", M2, self.m2_permission)
        self.g1.network_id = self.g2.network_id = "fixture-network"
        self.testimony_log = []

    # ---- machines -----------------------------------------------------------------------
    @contextmanager
    def on(self, machine):
        with mock.patch.object(paths, "HOME", self.states[machine]):
            yield

    def session(self, sid, machine):
        row = {"runtime": "codex", "session_id": sid, "home": str(self.homes[machine]), "cwd": str(self.cwd),
               "pid": os.getpid(), "lstart": self.start, "app_server": False, "ref": "fixture-" + sid,
               "updated": time.time(), "name": sid}
        with self.on(machine):
            paths.write_json(registry._record_path("codex", sid), row)
            home = Path(row["home"])
            rollout = home / (sid + ".jsonl")
            rollout.write_text(json.dumps({"type": "session_meta", "payload": {"id": sid}}) + "\n")
            with closing(sqlite3.connect(home / "state_5.sqlite")) as db, db:
                db.execute("create table if not exists threads (id text primary key, name text, rollout_path text)")
                db.execute("insert or replace into threads values (?, ?, ?)", (sid, "Native fixture", str(rollout)))
        return row

    def record(self, name):
        """The enriched record a live command sees (registry.by_session)."""
        machine = M2 if name == "asker-q" else M1
        with self.on(machine):
            return registry.by_session("codex", name, home=self.rows[name]["home"])

    def public(self, name):
        machine = M2 if name == "asker-q" else M1
        with self.on(machine):
            return network_directory.public_endpoint(self.rows[name], machine)

    def endpoint(self, name):
        """The key a machine uses in testimony and in a question record's target."""
        machine = M2 if name == "asker-q" else M1
        row = self.rows[name]
        return {"machine": machine, "runtime": "codex", "session_id": name,
                "home_id": hashlib.sha256(os.path.realpath(row["home"]).encode()).hexdigest()}

    # ---- the question Q asked A ----------------------------------------------------------
    def ask_a(self, request_id="rq", read=True):
        """Q (on M2) sends A (on M1) a task; M1 stores it for A; M2 keeps the question record.
        read: A's prompt hook shows it and acknowledges it before anything else happens."""
        with self.on(M2):
            packet = self.g2.prepare(self.rows["asker-q"], self.public("old-a"), "who owns the cache?",
                                     request_id=request_id, kind="task")
            paths.write_json(questions._filename(request_id), {
                "id": request_id, "sender": questions._handle(self.record("asker-q")),
                "target": self.endpoint("old-a"), "body": "who owns the cache?", "replies": [],
                "purpose": "question", "created_at": 1.0})
        with self.on(M1):
            self.assertEqual(self.g1.receive(M2, packet)["status"], "queued")
        if read:
            self.assertEqual(self.read_at("old-a", request_id), "acknowledged")
        return packet

    def read_at(self, who, message_id="rq"):
        """The session's prompt hook shows the message and acknowledges it (handoff claim + ack)."""
        owner = {"type": "native", "id": "reader-" + who}
        with self.on(M1):
            rec = self.record(who)
            claimed = handoff.claim(rec, owner, "reader-generation", message_id=message_id)
            handoff.ack(rec, claimed["claim"]["token"], owner, "reader-generation")
            return handoff.status(rec, message_id)["status"]

    # ---- the transport between the machines (mocked) -------------------------------------
    def transport(self, deliver="now"):
        """hand_over -> network.call('handover-publish') -> Daemon.publish_handover -> rpc.
        deliver: 'now' (M2 stores the testimony), 'lose' (rpc fails: machine offline), 'hold'
        (kept in `self.held`, delivered later with release())."""
        self.held = []
        daemon = network.Daemon.__new__(network.Daemon)
        daemon.transport = mock.Mock(endpoint_id=M1)
        daemon.peer_address = lambda key: {"id": key}

        def rpc(peer, request):
            self.testimony_log.append((peer["id"][0], request["old"]["session_id"], request["new"]["session_id"], deliver))
            if peer["id"] == M2:
                if deliver == "lose":
                    raise network.NetworkError("service-unavailable-or-response-unknown")
                if deliver == "hold":
                    self.held.append(request)
                    return {"result": {"status": "stored"}}      # M1 is told it went
                return {"result": self.arrive(request)}
            raise network.NetworkError("peer-refused")
        daemon.rpc = rpc

        def call(request, timeout=15):
            assert request["op"] == "handover-publish"
            with self.on(M1):
                return daemon.publish_handover(request)
        return mock.patch.multiple(network, available=lambda: True, call=call,
                                   message_gateway=lambda permission=None: self.g1)

    def arrive(self, request):
        with self.on(M2):
            return handover.receive_testimony(M1, request["old"], request["new"])

    def release(self):
        return [self.arrive(r) for r in self.held]

    def hand_over(self, old, new, deliver="now"):
        with self.transport(deliver), self.on(M1):
            return handover.hand_over(self.record(old), self.record(new), "summary: the cache question is open", "x")

    # ---- B answers over the P2P gateway ----------------------------------------------------
    def answer(self, who, reply_id, request_id="rq"):
        with self.on(M1):
            return self.g1.prepare(self.rows[who], self.public("asker-q"), "the cache is owned by %s" % who,
                                   request_id=reply_id, kind="reply", reply_to=request_id, outcome="succeeded")

    def deliver(self, packet, allowed=False):
        """M2's gateway receives it. allowed=False: M2's own permission refuses a stranger, so the
        reverse-reply check is the only way in (the refusal then reads local-permission-denied).
        allowed=True: the permission fixture admits it, so the reverse check alone decides
        (the refusal then reads reply-original-unverified)."""
        self.m2_permission.return_value = allowed
        with self.on(M2):
            try:
                return self.g2.receive(M1, packet)
            except messages.GatewayError as exc:
                return {"refused": exc.code}

    def recorded(self, sender, reply_id, request_id="rq"):
        """Stage 2 on M2: the hook indexes the reply into the question record."""
        with self.on(M2):
            header = {"kind": "reply", "reply-to": request_id, "id": reply_id, "outcome": "succeeded"}
            return questions.record_reply(self.record("asker-q"), self.endpoint(sender), header, "body")

    # =========================================================================================
    # Control: a team-member machine hears every hop, so the successor's answer is recorded.
    def test_control_a_machine_that_was_told_records_the_answer(self):
        self.ask_a()
        rec = self.hand_over("old-a", "succ-b")
        print("\n[control] testimony sent:", self.testimony_log, "notes:", rec["notes"])
        self.assertEqual(self.testimony_log, [("2", "old-a", "succ-b", "now")])
        reply = self.answer("succ-b", "ra")
        got = self.deliver(reply)
        print("[control] M2 gateway:", got)
        self.assertEqual(got["status"], "queued")
        self.assertTrue(self.recorded("succ-b", "ra"))

    # =========================================================================================
    # TLC AnswerRecorded, scenario "asked after": 4 steps (ViewsAgree breaks at step 2).
    #  1. the person approves; M1 has no reason to tell R's machine
    #  2. R asks A's old address
    #  3. B answers R
    #  4. R refuses the answer
    def test_asked_after_handover_b_answer_is_refused_on_the_asking_machine(self):
        # step 1: nobody had written to A before: the service has no machine to tell
        rec = self.hand_over("old-a", "succ-b")
        print("\n[after] testimony sent:", self.testimony_log, "notes:", rec["notes"])
        self.assertEqual(self.testimony_log, [])
        # step 2: R (M2) asks A's old address. M1's gate routes it to B (handover.for_handle/follow).
        with self.on(M2):
            packet = self.g2.prepare(self.rows["asker-q"], self.public("old-a"), "who owns the cache?",
                                     request_id="rq", kind="task")
            paths.write_json(questions._filename("rq"), {
                "id": "rq", "sender": questions._handle(self.record("asker-q")),
                "target": self.endpoint("old-a"), "body": "who owns the cache?", "replies": [],
                "purpose": "question", "created_at": 1.0})
        with self.on(M1):
            self.assertEqual(self.g1.receive(M2, packet)["status"], "queued")
            kept_for = self.g1._load("inbound", "rq")["local"]["session_id"]
            routed_status = handoff.status(self.record("succ-b"), "rq")["status"]
        print("[after] M1 kept the question for:", kept_for, "| at B:", routed_status)
        self.assertEqual((kept_for, routed_status), ("succ-b", "pending"))
        # M1's view: B is A's successor; M2's view: it is not.
        with self.on(M1):
            m1_view = handover.endpoint_succeeds(self.endpoint("succ-b"), self.endpoint("old-a"))
        with self.on(M2):
            m2_view = handover.endpoint_succeeds(self.endpoint("succ-b"), self.endpoint("old-a"))
        print("[after] M1 says B succeeds A:", m1_view, "| M2 says B succeeds A:", m2_view)
        self.assertTrue(m1_view)
        self.assertFalse(m2_view)                                    # ViewsAgree breaks
        # step 3: B answers; M1's own check passes (it follows its own handover).
        reply = self.answer("succ-b", "ra")
        # step 4: M2 refuses it.
        got = self.deliver(reply)
        print("[after] M2 gateway on B's answer:", got)
        self.assertIn("refused", got)
        with_permission = self.deliver(reply, allowed=True)
        print("[after] same, M2 permission fixture admitting the sender:", with_permission)
        self.assertEqual(with_permission, {"refused": "reply-original-unverified"})
        with self.on(M2):
            self.assertEqual(questions.status(self.record("asker-q"), "rq")["status"], "pending")
        self.assertFalse(self.recorded("succ-b", "ra"))              # the question record refuses too
        # and no later step of xsm re-sends the testimony: M1's only caller is hand_over/_publish.
        again = self.deliver(reply)                                  # the sender's `--resend`
        print("[after] resend:", again)
        self.assertIn("refused", again)

    # =========================================================================================
    # TLC AnswerRecorded, scenario "asked before, testimony lost": 4 steps.
    #  1. the person approves; M1 tells R's machine (message in flight)
    #  2. B answers R
    #  3. R refuses the answer (the handover news has not arrived)
    #  4. the handover news is lost on the way (no retry)
    def test_testimony_lost_after_the_answer_was_refused_nothing_ever_recovers_it(self):
        self.ask_a()
        rec = self.hand_over("old-a", "succ-b", deliver="hold")                         # step 1
        print("\n[lost] testimony sent:", self.testimony_log, "held:", len(self.held))
        self.assertEqual(len(self.held), 1)
        reply = self.answer("succ-b", "ra")                                             # step 2
        got = self.deliver(reply)                                                       # step 3
        print("[lost] M2 gateway on B's answer (testimony still in flight):", got)
        self.assertIn("refused", got)
        # step 4: the held message is lost. Every other way testimony could be re-sent:
        self.held = []
        with self.on(M2):
            self.assertFalse(handover.endpoint_succeeds(self.endpoint("succ-b"), self.endpoint("old-a")))
        import re
        hits = []
        for n in sorted(os.listdir("xsm")):
            if n.endswith(".py"):
                for number, line in enumerate((Path("xsm") / n).read_text().splitlines(), 1):
                    if re.search(r"handover\._publish\(|_publish\(record|\"handover-publish\"|publish_handover\(", line):
                        hits.append("xsm/%s:%d" % (n, number))
        print("[lost] every place that starts or serves a testimony send:", hits)
        again = self.deliver(reply)                                                     # --resend
        print("[lost] resend after the loss:", again)
        self.assertIn("refused", again)
        self.assertFalse(self.recorded("succ-b", "ra"))

    def test_testimony_failed_at_handover_time_says_so_once(self):
        self.ask_a()
        rec = self.hand_over("old-a", "succ-b", deliver="lose")
        print("\n[offline] notes returned to the person:", rec["notes"], "| log:", self.testimony_log)
        self.assertEqual(len(rec["notes"]), 1)
        self.assertIn("machine", rec["notes"][0])
        reply = self.answer("succ-b", "ra")
        self.assertIn("refused", self.deliver(reply))

    # =========================================================================================
    # Hypothesis (a), the part TLC says holds (scenarioOrdering): the answer first, testimony
    # after, then a resend with the same id: recorded.
    def test_ordering_answer_before_testimony_is_recovered_by_a_resend(self):
        self.ask_a()
        self.hand_over("old-a", "succ-b", deliver="hold")
        reply = self.answer("succ-b", "ra")
        first = self.deliver(reply)
        self.assertIn("refused", first)
        print("\n[order] before the testimony:", first)
        print("[order] testimony arrives:", self.release())
        with self.on(M2):
            kept = self.g2._load("inbound", "ra")
            at_q = handoff.status(self.record("asker-q"), "ra")["status"]
            pending = questions.status(self.record("asker-q"), "rq")["status"]
        print("[order] after the testimony, before any resend: inbound record:", kept, "| at Q:", at_q,
              "| question:", pending)
        self.assertEqual((kept, at_q, pending), (None, "not-found", "pending"))     # nothing re-indexes it
        second = self.deliver(reply)
        print("[order] resend (same id):", second)
        self.assertEqual(second["status"], "queued")
        self.assertTrue(self.recorded("succ-b", "ra"))

    # =========================================================================================
    # TLC AnswerRecorded, scenario "chain": 4 steps.
    #  1. the person approves; M1 tells R's machine (A to B)
    #  2. B hands over to C; M1 has no reason to tell R's machine
    #  3. C answers R
    #  4. R refuses the answer
    def test_chain_second_handover_is_not_told_to_the_machine_that_asked_a(self):
        self.ask_a()
        self.hand_over("old-a", "succ-b")                                               # step 1
        with self.on(M2):
            self.assertTrue(handover.endpoint_succeeds(self.endpoint("succ-b"), self.endpoint("old-a")))
        n = len(self.testimony_log)
        self.hand_over("succ-b", "succ-c")                                              # step 2
        print("\n[chain] testimony sent for B to C:", self.testimony_log[n:])
        self.assertEqual(self.testimony_log[n:], [])
        with self.on(M1):
            print("[chain] origins_for(B):", sorted(m[0] for m in self.g1.origins_for(self.record("succ-b"))),
                  "| origins_for(A):", sorted(m[0] for m in self.g1.origins_for(self.record("old-a"))))
        reply = self.answer("succ-c", "ra")                                             # step 3
        got = self.deliver(reply)                                                       # step 4
        print("[chain] M2 gateway on C's answer:", got)
        self.assertIn("refused", got)
        self.assertFalse(self.recorded("succ-c", "ra"))
        # B's own answer is still accepted: only the second hop is missing.
        with self.on(M2):
            self.assertTrue(handover.endpoint_succeeds(self.endpoint("succ-b"), self.endpoint("old-a")))
            self.assertFalse(handover.endpoint_succeeds(self.endpoint("succ-c"), self.endpoint("old-a")))

    # =========================================================================================
    # New in this lane (TLC scenarioUnread): the question was still unread at A when A handed
    # over. handoff.move_out closes A's original as moved to B, B holds no copy, so the
    # gateway cannot verify the original and B cannot prepare a reply at all.
    def test_unread_question_at_handover_cannot_be_answered_by_the_successor(self):
        self.ask_a(read=False)
        rec = self.hand_over("old-a", "succ-b")
        print("\n[unread] moved messages:", rec["messages"], "| testimony:", self.testimony_log)
        self.assertEqual(rec["messages"], ["rq"])
        with self.on(M1):
            print("[unread] original at A:", handoff.status(self.record("old-a"), "rq")["status"],
                  "moved_to", handoff.status(self.record("old-a"), "rq").get("moved_to", {}).get("session_id"),
                  "| copy at B:", handoff.status(self.record("succ-b"), "rq")["status"])
            with self.assertRaises(messages.GatewayError) as caught:
                self.g1.prepare(self.rows["succ-b"], self.public("asker-q"), "answer", request_id="ra",
                                kind="reply", reply_to="rq", outcome="succeeded")
        print("[unread] B's reply:", caught.exception.code)
        self.assertEqual(caught.exception.code, "reply-original-unverified")
        with self.on(M2):                                    # M2 did get the testimony; it is M1 that cannot reply
            self.assertTrue(handover.endpoint_succeeds(self.endpoint("succ-b"), self.endpoint("old-a")))

    # =========================================================================================
    # What B sees when M2 refuses: Daemon.send_remote with the peer's refusal. Mocked: resolve_remote
    # (target lookup), _grant, repositories, peer_address, and rpc (it raises what the real rpc raises
    # when the peer's body is not ok: NetworkError('peer-refused'), network.py:900-905).
    def test_the_refused_answer_looks_like_an_unknown_delivery_to_its_sender(self):
        from xsm import ledger
        self.ask_a()
        self.hand_over("old-a", "succ-b")
        daemon = network.Daemon.__new__(network.Daemon)
        daemon.transport = mock.Mock(endpoint_id=M1)
        target = dict(self.public("asker-q"), ref="net:fixture")
        daemon.caller = lambda c: c
        daemon.resolve_remote = lambda caller, t: {"target": target, "scope": "network"}
        daemon._grant = lambda caller, t: None
        daemon.repositories = lambda: mock.Mock(for_local=lambda *a: None)
        daemon.peer_address = lambda key: {"id": key}
        daemon.gateway = lambda permission=None: self.g1
        daemon.rpc = mock.Mock(side_effect=network.NetworkError("peer-refused"))
        with self.on(M1), mock.patch.object(network_directory, "public_endpoint", wraps=network_directory.public_endpoint):
            out = daemon.send_remote({"caller": self.record("succ-b"), "target": "net:fixture", "body": "the cache is B's",
                                      "kind": "reply", "reply_to": "rq", "outcome": "succeeded", "id": "ra"})
            row = ledger.status("ra")
        print("\n[sender] send_remote result:", {k: out[k] for k in ("id", "status", "reason")})
        print("[sender] ledger:", {k: row.get(k) for k in ("status", "delivery", "reason") if k in row})
        self.assertEqual(out["status"], "unknown")

    def test_a_stopped_service_at_handover_time_is_silent_when_there_are_no_team_machines(self):
        self.ask_a()
        with mock.patch.object(network, "available", lambda: False), self.on(M1):
            rec = handover.hand_over(self.record("old-a"), self.record("succ-b"), "summary", "x")
        print("\n[silent] notes with the network service stopped:", rec["notes"])
        self.assertEqual(rec["notes"], [])
        self.assertIn("refused", self.deliver(self.answer("succ-b", "ra")))

    # =========================================================================================
    # Rules that hold.
    def test_a_session_outside_the_chain_is_never_recorded(self):
        self.ask_a()
        self.hand_over("old-a", "succ-b")
        # M1 itself will not prepare a reply from a stranger
        with self.on(M1):
            with self.assertRaises(messages.GatewayError) as caught:
                self.g1.prepare(self.rows["succ-c"], self.public("asker-q"), "not mine", request_id="rx",
                                kind="reply", reply_to="rq", outcome="succeeded")
        print("\n[stranger] M1 refuses to prepare it:", caught.exception.code)
        # a forged packet from C that skipped M1's check: M2 refuses it even though M2 knows A -> B
        with self.on(M1):
            good = self.answer("succ-b", "ra")
        forged = json.loads(json.dumps(good))
        forged["sender"] = self.public("succ-c")
        forged["id"] = "rx"
        forged["fingerprint"] = messages.request_fingerprint(forged)
        got = self.deliver(forged)
        print("[stranger] forged packet at M2:", got)
        self.assertIn("refused", got)
        got = self.deliver(forged, allowed=True)
        print("[stranger] forged packet at M2, permission fixture admitting the sender:", got)
        self.assertEqual(got, {"refused": "reply-original-unverified"})
        self.assertFalse(self.recorded("succ-c", "rx"))
        self.assertEqual(self.deliver(good)["status"], "queued")
        self.assertTrue(self.recorded("succ-b", "ra"))

    def test_a_machine_testifies_only_about_its_own_sessions(self):
        old, new = self.endpoint("old-a"), self.endpoint("succ-b")
        with self.on(M2):
            for origin, o, n in ((M3, old, new),                                   # another machine's word
                                 (M1, old, dict(new, machine=M3)),                 # successor on a third machine
                                 (M2, dict(old, machine=M2), dict(new, machine=M2)),  # M2 speaking for M1's A?  (old.machine is M2)
                                 (M1, old, old)):                                  # itself
                if origin == M2:
                    # origin == old.machine == new.machine is a statement about M2's own sessions: allowed,
                    # and says nothing about M1's A.
                    handover.receive_testimony(origin, o, n)
                    continue
                with self.assertRaises(ValueError):
                    handover.receive_testimony(origin, o, n)
            self.assertFalse(handover.endpoint_succeeds(new, old))
            self.assertEqual(handover.receive_testimony(M1, old, new)["status"], "stored")
            other = dict(new, session_id="succ-c")
            self.assertEqual(handover.receive_testimony(M1, old, other)["status"], "conflict")   # first word stands
            self.assertTrue(handover.endpoint_succeeds(new, old))
            self.assertFalse(handover.endpoint_succeeds(other, old))
            print("\n[testimony] forged variants refused; first word stands; chain not backwards:",
                  handover.endpoint_succeeds(old, new))


if __name__ == "__main__":
    unittest.main()
