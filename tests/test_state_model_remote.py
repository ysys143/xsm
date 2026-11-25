"""State-model regression tests, remote lane: SM-F9 and SM-F10 (docs/plan/state-model-fixes/spec.md).

Two machines in one process, driving xsm's real code (the fixture is the replay in
deliverables/statechart-20261125/remote/replay_test.py):
  M1 holds the sessions A ("old-a"), B ("succ-b"), C ("succ-c") and its own XSM state;
  M2 holds the asking session R ("asker-q") and its own XSM state.
`on(machine)` switches paths.HOME, so every real call reads and writes the state of the
machine it runs on.

Mocked, and nothing else:
  * machine-to-machine transport.
      - network.call("handover-publish") runs M1's real Daemon.publish_handover; Daemon.rpc
        is replaced by a function that runs M2's real handover.receive_testimony, or fails
        (machine offline), or holds the message for release().
      - network.call("succession") is the planned P6 pull query (spec section 3.4 F9:
        request `succession {old, new}`, answered with the whole chain). It does not exist
        yet, so today nothing calls it. The mock answers from M1's real handover records
        as {"chain": [{"old": endpoint, "new": endpoint}, ...]}, or raises
        network.NetworkError when M1 is made unreachable. The wire shape is an assumption
        taken from the spec; P6 may need to adapt this one function.
  * gate permission callbacks: M1's admits the question; M2's own permission for a reply is
    `False` by default, so only the reverse-reply check (or the planned succession pull) can
    let a reply in.

Run from the repository root:
  python3 -m unittest tests.test_state_model_remote -v
"""
import hashlib
import json
import os
import sqlite3
import time
import unittest
from contextlib import closing, contextmanager
from pathlib import Path
from unittest import mock
import tempfile

from xsm import (config, handover, handoff, identity, network, network_directory,
                 network_identity, network_messages as messages, paths, questions, registry)

M1, M2, M3 = "1" * 64, "2" * 64, "3" * 64


_NAMES = {"config": "config", "handover": "handover", "handoff": "handoff", "identity": "identity",
          "network": "network", "network_directory": "network_directory",
          "network_identity": "network_identity", "messages": "network_messages", "paths": "paths",
          "questions": "questions", "registry": "registry"}


def _fresh_xsm():
    """Bind this module's xsm names to the modules the code under test uses.
    TempState (tests/test_xsm.py) drops every xsm module from sys.modules and
    imports them again, so names bound at import time can point at stale
    copies whose paths.HOME no longer reaches the real calls."""
    import importlib
    for name, module in _NAMES.items():
        globals()[name] = importlib.import_module("xsm." + module)


class RemoteFixture(unittest.TestCase):
    def setUp(self):
        _fresh_xsm()
        tmp = tempfile.TemporaryDirectory(prefix="xsm-remote-sm-")
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
        self.rows = {}
        for name, machine in (("old-a", M1), ("succ-b", M1), ("succ-c", M1), ("asker-q", M2)):
            self.rows[name] = self.session(name, machine)
        self.m2_permission = mock.Mock(name="m2_local_permission_fixture", return_value=False)
        self.g1 = messages.Gateway(self.root / "gateway-m1", M1, mock.Mock(return_value=True))
        self.g2 = messages.Gateway(self.root / "gateway-m2", M2, self.m2_permission)
        self.g1.network_id = self.g2.network_id = "fixture-network"
        self.testimony_log = []
        self.pull_log = []
        self.held = []
        self.m1_reachable = True        # False: M1 cannot be reached for the succession pull

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

    # ---- the question R (on M2) asked A (on M1) ------------------------------------------
    def ask_a(self, request_id="rq", read=True):
        """R sends A's address a task; M1 stores it for whoever holds A's place; M2 keeps the
        question record. read: A's prompt hook shows it and acknowledges it. Called after a
        handover, M1's gate routes it to the successor (handover.follow)."""
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
        owner = {"type": "native", "id": "reader-" + who}
        with self.on(M1):
            rec = self.record(who)
            claimed = handoff.claim(rec, owner, "reader-generation", message_id=message_id)
            handoff.ack(rec, claimed["claim"]["token"], owner, "reader-generation")
            return handoff.status(rec, message_id)["status"]

    # ---- the transport between the machines (mocked) -------------------------------------
    def _chain_on_m1(self, old, new):
        """M1's answer to the succession pull: its real handover records, hop by hop, from `old`
        until `new` (or the end of the chain)."""
        hops, current = [], handover._key(old)
        for _ in range(handover.CHAIN):
            with self.on(M1):
                nxt = next((rec["to_identity"] for rec in handover._records()
                            if handover._names(rec.get("from_identity") or {}, current)), None)
                if nxt is None:
                    break
                nxt_endpoint = handover.local_endpoint(nxt, M1)
            hops.append({"old": current, "new": nxt_endpoint})
            current = nxt_endpoint
            if current == handover._key(new):
                break
        return {"chain": hops}

    def net(self, deliver="now"):
        """network.call for both machine-to-machine ops.
        deliver (for "handover-publish"): 'now' (M2 stores the testimony), 'lose' (rpc fails:
        machine offline), 'hold' (kept in self.held, delivered later with release()).
        "succession" (the planned pull): answered from M1's records, or NetworkError when
        self.m1_reachable is False."""
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
            if request["op"] == "handover-publish":
                with self.on(M1):
                    return daemon.publish_handover(request)
            if request["op"] == "succession":
                self.pull_log.append(request)
                if not self.m1_reachable:
                    raise network.NetworkError("peer-unreachable")
                return self._chain_on_m1(request["old"], request["new"])
            raise AssertionError("unexpected network op: %r" % request["op"])
        return mock.patch.multiple(network, available=lambda: True, call=call,
                                   message_gateway=lambda permission=None: self.g1)

    def arrive(self, request):
        with self.on(M2):
            return handover.receive_testimony(M1, request["old"], request["new"])

    def tell_m2(self, old, new):
        """M1's testimony that session `old` handed over to `new` reaches M2."""
        return self.arrive({"old": self.endpoint(old), "new": self.endpoint(new)})

    def release(self):
        held, self.held = self.held, []
        return [self.arrive(r) for r in held]

    def hand_over(self, old, new, deliver="now"):
        self.held = []
        with self.net(deliver), self.on(M1):
            return handover.hand_over(self.record(old), self.record(new), "summary: the cache question is open", "x")

    # ---- the answer, from M1 to M2 ---------------------------------------------------------
    def answer(self, who, reply_id, request_id="rq"):
        with self.on(M1):
            return self.g1.prepare(self.rows[who], self.public("asker-q"), "the cache is owned by %s" % who,
                                   request_id=reply_id, kind="reply", reply_to=request_id, outcome="succeeded")

    def deliver(self, packet, allowed=False, origin=M1):
        """M2's gateway receives it (stage 1). allowed=False: M2's own permission refuses a
        stranger, so only the reverse-reply check (or the succession pull) lets it in."""
        self.m2_permission.return_value = allowed
        with self.net(), self.on(M2):
            try:
                return self.g2.receive(origin, packet)
            except messages.GatewayError as exc:
                return {"refused": exc.code}

    def recorded(self, sender_endpoint, reply_id, request_id="rq"):
        """Stage 2 on M2: the hook indexes the reply into the question record."""
        with self.net(), self.on(M2):
            header = {"kind": "reply", "reply-to": request_id, "id": reply_id, "outcome": "succeeded"}
            return questions.record_reply(self.record("asker-q"), sender_endpoint, header, "body")

    def replies(self, request_id="rq"):
        with self.on(M2):
            return questions.status(self.record("asker-q"), request_id).get("replies") or []

    def assert_recorded_without_resend(self, who, reply_id="ra"):
        """The sender sends once. R's gateway takes it and R's question record keeps it."""
        reply = self.answer(who, reply_id)
        got = self.deliver(reply)
        self.assertNotIn("refused", got, "R's machine refused %s's answer (never resent): %r" % (who, got))
        self.assertEqual(got.get("status"), "queued")
        self.assertTrue(self.recorded(self.endpoint(who), reply_id),
                        "the question record did not take %s's answer" % who)
        rows = self.replies()
        self.assertEqual([r["id"] for r in rows], [reply_id])
        return rows


class SM_F9_RemoteTestimony(RemoteFixture):
    # ---- SM-F9: the successor's answer ends up in the question record ----------------------

    # RED until P6 (SM-F9)
    # Today: the handover news was lost (offline); R's machine has no testimony, so
    # Gateway.receive refuses with local-permission-denied and record_reply returns False.
    # Nothing re-sends the testimony and nothing pulls it (spec section 2, F9).
    @unittest.expectedFailure
    def test_SM_F9_testimony_lost(self):
        self.ask_a()
        rec = self.hand_over("old-a", "succ-b", deliver="lose")
        self.assertEqual(len(rec["notes"]), 1)               # the person was told once; R's machine was not
        with self.on(M2):
            self.assertFalse(handover.endpoint_succeeds(self.endpoint("succ-b"), self.endpoint("old-a")))
        rows = self.assert_recorded_without_resend("succ-b")
        self.assertNotEqual(rows[0].get("succession"), "unconfirmed")    # the pull confirmed it

    # RED until P6 (SM-F9)
    # Today: R asks A's old address after the handover. M1 routes the question to B, but
    # M1 told nobody (A had no earlier correspondent), so B's answer is refused on M2
    # (local-permission-denied; reply-original-unverified when M2's permission admits it).
    @unittest.expectedFailure
    def test_SM_F9_asked_after_handover(self):
        self.hand_over("old-a", "succ-b")
        self.assertEqual(self.testimony_log, [])             # nobody was told
        self.ask_a(read=False)
        with self.on(M1):
            self.assertEqual(handoff.status(self.record("succ-b"), "rq")["status"], "pending")   # routed to B
        rows = self.assert_recorded_without_resend("succ-b")
        self.assertNotEqual(rows[0].get("succession"), "unconfirmed")

    # RED until P6 (SM-F9)
    # Today: A -> B was told to M2, B -> C was not (nobody asked B anything, so origins_for(B)
    # is empty). endpoint_succeeds(C, A) on M2 stops at B, so C's answer is refused.
    @unittest.expectedFailure
    def test_SM_F9_chain(self):
        self.ask_a()
        self.hand_over("old-a", "succ-b")
        n = len(self.testimony_log)
        self.hand_over("succ-b", "succ-c")
        self.assertEqual(self.testimony_log[n:], [])         # M2 was not told about B -> C
        rows = self.assert_recorded_without_resend("succ-c")
        self.assertNotEqual(rows[0].get("succession"), "unconfirmed")

    # RED until P6 (SM-F9)
    # Today: with M1 unreachable for the pull (and the testimony still in flight), M2 refuses
    # B's answer. Target: it is recorded with succession "unconfirmed" on the reply entry (P*,
    # spec 3.4: same machine as A, and the reply carries the question's reply_to); when the
    # testimony arrives later the mark becomes "confirmed". The answer is never dropped.
    @unittest.expectedFailure
    def test_SM_F9_unconfirmed_then_confirmed_when_testimony_arrives(self):
        self.ask_a()
        self.hand_over("old-a", "succ-b", deliver="hold")
        self.assertEqual(len(self.held), 1)
        self.m1_reachable = False
        rows = self.assert_recorded_without_resend("succ-b")
        self.assertEqual(rows[0].get("succession"), "unconfirmed")
        self.assertEqual(len(rows), 1)
        self.release()                                       # the in-flight testimony lands
        self.assertEqual(self.replies()[0].get("succession"), "confirmed")
        self.assertEqual(len(self.replies()), 1)

    # RED until P6 (SM-F9)
    # Same, for a question asked after the handover and never testified to R's machine; the
    # testimony later reaches R's machine by any route (here: M1 sends it).
    @unittest.expectedFailure
    def test_SM_F9_unconfirmed_when_asked_after_handover_then_confirmed(self):
        self.hand_over("old-a", "succ-b")
        self.ask_a(read=False)
        self.m1_reachable = False
        rows = self.assert_recorded_without_resend("succ-b")
        self.assertEqual(rows[0].get("succession"), "unconfirmed")
        self.tell_m2("old-a", "succ-b")
        self.assertEqual(self.replies()[0].get("succession"), "confirmed")

    # ---- controls: pass today and must keep passing ----------------------------------------

    def test_control_SM_F9_a_machine_that_was_told_records_the_answer(self):
        self.ask_a()
        self.hand_over("old-a", "succ-b")
        self.assertEqual(self.testimony_log, [("2", "old-a", "succ-b", "now")])
        rows = self.assert_recorded_without_resend("succ-b")
        self.assertNotEqual(rows[0].get("succession"), "unconfirmed")

    # Q2: in the chain A -> B -> C, when both testimonies (A -> B, B -> C) have reached R's
    # machine, today's endpoint_succeeds walks the two hops, so C's answer is recorded. M1 is
    # made unreachable so only the stored testimony decides, never the pull.
    # Answer: yes. The F9 chain failure is only "the second testimony never goes".
    def test_control_SM_F9_chain_with_both_testimonies(self):
        self.ask_a()
        self.hand_over("old-a", "succ-b")
        self.hand_over("succ-b", "succ-c")
        self.tell_m2("succ-b", "succ-c")
        self.m1_reachable = False
        with self.on(M2):
            self.assertTrue(handover.endpoint_succeeds(self.endpoint("succ-c"), self.endpoint("old-a")))
        rows = self.assert_recorded_without_resend("succ-c")
        self.assertIn(rows[0].get("succession"), (None, "confirmed"))

    def test_control_SM_F9_a_machine_testifies_only_about_its_own_sessions(self):
        old, new = self.endpoint("old-a"), self.endpoint("succ-b")
        with self.on(M2):
            for origin, o, n in ((M3, old, new),                                      # another machine's word
                                 (M1, old, dict(new, machine=M3)),                    # successor on a third machine
                                 (M1, old, old)):                                     # itself
                with self.assertRaises(ValueError):
                    handover.receive_testimony(origin, o, n)
            self.assertFalse(handover.endpoint_succeeds(new, old))
            self.assertEqual(handover.receive_testimony(M1, old, new)["status"], "stored")
            other = dict(new, session_id="succ-c")
            self.assertEqual(handover.receive_testimony(M1, old, other)["status"], "conflict")  # first word stands
            self.assertTrue(handover.endpoint_succeeds(new, old))
            self.assertFalse(handover.endpoint_succeeds(other, old))

    # An answer from a session on a different machine than A is never recorded, with or without
    # a pull, with M2's own permission refusing or admitting the sender. The packet is B's real
    # answer re-issued from a session on a third machine (M3).
    def test_control_SM_F9_an_answer_from_a_different_machine_is_never_recorded(self):
        self.ask_a()
        self.hand_over("old-a", "succ-b", deliver="lose")
        good = self.answer("succ-b", "ra")
        forged = json.loads(json.dumps(good))
        forged["sender"] = dict(self.public("succ-b"), machine=M3)
        forged["id"] = "rx"
        forged["fingerprint"] = messages.request_fingerprint(forged)
        for allowed in (False, True):
            got = self.deliver(forged, allowed=allowed, origin=M3)
            self.assertIn("refused", got)
        stranger = dict(self.endpoint("succ-b"), machine=M3)
        self.assertFalse(self.recorded(stranger, "rx"))
        self.assertEqual(self.replies(), [])


class SM_F10_UnreadQuestionAtHandover(RemoteFixture):
    # RED until P2 (SM-F10)
    # Today: A had not read R's question when it handed over. handoff.move_out closes A's
    # original as moved and B holds no copy, so Gateway.prepare for B raises
    # reply-original-unverified (its _ingress cannot find the original). Target: B prepares,
    # sends, and R records the answer. M2 was told about A -> B (it had written to A), so only
    # the missing original at B is in the way.
    @unittest.expectedFailure
    def test_SM_F10_successor_can_answer_a_question_the_old_session_never_read(self):
        self.ask_a(read=False)
        rec = self.hand_over("old-a", "succ-b")
        self.assertEqual(rec["messages"], ["rq"])
        try:
            reply = self.answer("succ-b", "ra")
        except messages.GatewayError as exc:
            self.fail("B cannot prepare a reply to the question A never read: %s" % exc.code)
        got = self.deliver(reply)
        self.assertEqual(got.get("status"), "queued", got)
        self.assertTrue(self.recorded(self.endpoint("succ-b"), "ra"))
        self.assertEqual([r["id"] for r in self.replies()], ["ra"])


if __name__ == "__main__":
    unittest.main()
