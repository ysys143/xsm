"""The succession pull (docs/plan/state-model-fixes/spec.md 3.4 F9, PROTOCOL 5.15) beyond the SM-F9 tests:
what the asked machine answers and to whom, the ten-minute negative cache, and how an answer recorded
without testimony ends up marked once testimony arrives. Same two-machine fixture as
tests/test_state_model_remote.py.

Run from the repository root:
  python3 -m unittest tests.test_state_model_remote_succession -v
"""
import importlib
import unittest
from unittest import mock

from tests import test_state_model_remote as remote


class SuccessionServer(remote.RemoteFixture):
    def daemon(self):
        daemon = remote.network.Daemon.__new__(remote.network.Daemon)
        daemon.transport = mock.Mock(endpoint_id=remote.M1)
        daemon.gateway = lambda permission=None: self.g1
        return daemon

    def test_the_chain_is_read_from_the_handover_records(self):
        self.ask_a()
        self.hand_over("old-a", "succ-b", deliver="lose")
        self.hand_over("succ-b", "succ-c", deliver="lose")
        old = self.endpoint("old-a")
        with self.on(remote.M1):
            full = remote.handover.succession_chain(old, remote.M1)
            to_b = remote.handover.succession_chain(old, remote.M1, stop=self.endpoint("succ-b"))
        self.assertEqual([h["new"]["session_id"] for h in full], ["succ-b", "succ-c"])
        self.assertEqual([h["old"]["session_id"] for h in full], ["old-a", "succ-b"])
        self.assertEqual([h["new"]["session_id"] for h in to_b], ["succ-b"])

    def test_only_a_machine_that_wrote_to_the_old_session_is_told(self):
        self.ask_a()
        self.hand_over("old-a", "succ-b", deliver="lose")
        request = {"old": self.endpoint("old-a"), "new": self.endpoint("succ-b")}
        with self.on(remote.M1):
            told = self.daemon().answer_succession(remote.M2, request)
            stranger = self.daemon().answer_succession(remote.M3, request)
        self.assertEqual([h["new"]["session_id"] for h in told["chain"]], ["succ-b"])
        self.assertEqual(stranger, {"chain": []})

    def test_the_service_answers_a_member_machine_over_the_peer_request(self):
        self.ask_a()
        self.hand_over("old-a", "succ-b", deliver="lose")
        daemon = self.daemon()
        daemon._lock = mock.MagicMock()
        store = mock.Mock(network_id="n")
        store.is_active.return_value = True
        daemon.store = lambda: store
        daemon._learn_contacts = lambda *a: None
        request = {"network_id": "n", "op": "succession", "old": self.endpoint("old-a"), "new": self.endpoint("succ-c")}
        with self.on(remote.M1):
            out = daemon.incoming(remote.M2, request)
            refused = daemon.incoming(remote.M2, dict(request, old=self.endpoint("asker-q")))
        self.assertTrue(out["ok"])
        self.assertEqual([h["new"]["session_id"] for h in out["result"]["chain"]], ["succ-b"])
        self.assertEqual(refused["result"], {"chain": []})

    def test_a_machine_is_asked_only_about_its_own_sessions(self):
        request = {"old": self.endpoint("asker-q"), "new": self.endpoint("succ-b")}      # M2's session, asked of M1
        with self.on(remote.M1):
            self.assertEqual(self.daemon().answer_succession(remote.M2, request), {"chain": []})


class SuccessionPull(remote.RemoteFixture):
    def test_an_unreachable_machine_is_asked_once_in_ten_minutes(self):
        self.ask_a()
        self.hand_over("old-a", "succ-b", deliver="lose")
        self.m1_reachable = False
        for reply_id in ("ra", "rb"):
            got = self.deliver(self.answer("succ-b", reply_id))
            self.assertEqual(got.get("status"), "queued")
        self.assertEqual(len(self.pull_log), 1)

    def test_a_chain_without_the_sender_is_a_refusal_not_an_unconfirmed_answer(self):
        self.ask_a()
        self.hand_over("old-a", "succ-b", deliver="lose")
        reply = self.answer("succ-b", "ra")
        # M1 answers the pull, but the chain it holds does not reach the sender it was asked about.
        with mock.patch.object(self, "_chain_on_m1", return_value={"chain": []}):
            got = self.deliver(reply)
        self.assertIn("refused", got)
        self.assertEqual(self.replies(), [])

    def test_the_mark_follows_the_testimonies_of_a_chain(self):
        self.ask_a()
        self.hand_over("old-a", "succ-b", deliver="lose")
        self.hand_over("succ-b", "succ-c", deliver="lose")
        self.m1_reachable = False
        self.assert_recorded_without_resend("succ-c")
        self.assertEqual(self.replies()[0]["succession"], "unconfirmed")
        self.tell_m2("old-a", "succ-b")          # the chain known so far ends at B: C's answer is disputed
        self.assertEqual(self.replies()[0]["succession"], "disputed")
        bounce = importlib.import_module("xsm.bounce")
        with self.on(remote.M2):
            self.assertIn("disputed", bounce.notice("asker-q"))
            self.assertEqual(bounce.notice("asker-q"), "")           # shown once
        self.tell_m2("succ-b", "succ-c")         # the second hop arrives: confirmed, the answer was never dropped
        rows = self.replies()
        self.assertEqual([(r["id"], r["succession"]) for r in rows], [("ra", "confirmed")])

    def test_an_answer_recorded_without_the_gateway_admitting_it_is_refused(self):
        self.ask_a()
        self.hand_over("old-a", "succ-b", deliver="lose")
        self.assertFalse(self.recorded(self.endpoint("succ-b"), "ra"))
        self.assertEqual(self.replies(), [])


if __name__ == "__main__":
    unittest.main()
