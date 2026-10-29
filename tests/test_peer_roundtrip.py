"""G02 fixture evidence: linked-folder peers need no direct parent/child edge.

Two topologies, each with both peers initiating a message/reply round trip.
The approved link is seeded through config.add_link, not a simulated human
approval UI. Only the runtime queue adapter is mocked; registry, scope checks,
send, envelope, inbox and receive execute their existing service paths.
This is isolated fixture evidence, not a real harness or full G02 verdict.
"""
import os
import unittest
from unittest import mock

from tests.test_xsm import TempState


class PeerRoundtripTest(TempState):
    def _session(self, name, folder):
        from xsm import registry
        cwd = os.path.join(self.tmp, folder)
        os.makedirs(cwd, exist_ok=True)
        home = os.path.join(self.tmp, "runtime-home")
        os.makedirs(home, exist_ok=True)
        rec = registry.upsert("codex", home, name, os.getpid(), cwd, name=name)
        self.assertEqual(registry.by_session("codex", name)["ref"], rec["ref"])
        return rec

    def _pair(self, siblings):
        from xsm import workers
        parent_a = self._session("parent-a", "parent-a-folder")
        parent_b = parent_a if siblings else self._session("parent-b", "parent-b-folder")
        a = self._session("peer-a", "project-a")
        b = self._session("peer-b", "project-b")
        for child, parent in ((a, parent_a), (b, parent_b)):
            workers.save({"name": child["name"], "ref": child["ref"],
                          "parent_ref": parent["ref"], "session_id": child["session_id"],
                          "runtime": child["runtime"], "home": child["home"]})
        rows = {w["ref"]: w for w in workers.all_workers()}
        self.assertEqual(rows[a["ref"]]["parent_ref"] == rows[b["ref"]]["parent_ref"],
                         siblings)
        self.assertNotIn(rows[a["ref"]]["parent_ref"], (a["ref"], b["ref"]))
        self.assertNotIn(rows[b["ref"]]["parent_ref"], (a["ref"], b["ref"]))
        return a, b

    def _handover(self, sender, recipient, body, *, reply_to=None):
        from xsm import envelope, inbox, ledger, receive, send
        result = send.send("ref:" + recipient["ref"], body, sender=sender,
                           kind="reply" if reply_to else "task", reply_to=reply_to,
                           outcome="succeeded" if reply_to else None)
        self.assertEqual(result.status, "sent-unconfirmed", result.reason)
        self.assertIsNotNone(result.msg_id)
        self.assertIsNone(ledger.receipt_of(result.msg_id))
        self.assertEqual(inbox.count(sender["session_id"]), 0)
        self.assertEqual(inbox.count(recipient["session_id"]), 1)
        home, sid, wire = self.transport.call_args.args
        self.assertEqual((home, sid), (recipient["home"], recipient["session_id"]))
        parsed = envelope.parse(wire)
        self.assertEqual(parsed.body, body)
        self.assertEqual(parsed.header["id"], result.msg_id)
        self.assertEqual(parsed.header["ref"], sender["ref"])
        self.assertEqual(parsed.header["scope"], self.scope)
        self.assertEqual(parsed.header.get("reply-to"), reply_to)
        self.assertEqual(parsed.header["kind"], "reply" if reply_to else "task")
        texts = receive.take_inbox(recipient)
        self.assertEqual(len(texts), 1, texts)
        self.assertTrue(texts[0].endswith("\n\n" + body), texts)
        receipt = ledger.receipt_of(result.msg_id)
        self.assertEqual(receipt["decision"], "delivered", receipt)
        self.assertEqual(receipt["receiver"]["ref"], recipient["ref"])
        self.assertEqual(receipt["from_ref"], sender["ref"])
        state = ledger.status(result.msg_id)
        self.assertEqual(state["status"], "delivered")
        self.assertEqual((state["from"]["ref"], state["to"]["ref"]),
                         (sender["ref"], recipient["ref"]))
        self.assertEqual(state.get("reply_to"), reply_to)
        self.assertEqual(receive.take_inbox(recipient), [], "no duplicate handover")
        return result.msg_id

    def _exercise(self, siblings):
        from xsm import adapters, config, ledger
        a, b = self._pair(siblings)
        # Sibling ancestry alone grants nothing between the separate folders;
        # nor does merely having different registered parents.
        self.assertIsNone(config.scope_for(a, b)[0])
        self.assertIsNone(config.scope_for(b, a)[0])
        approved, added = config.add_link(a["cwd"], b["cwd"],
                                          "fixture: user approved these two folders")
        self.assertTrue(added)
        self.assertIn(approved, config.links())
        self.scope = config.link_id(a["cwd"], b["cwd"])
        for sender, recipient in ((a, b), (b, a)):
            scope, reason = config.scope_for(sender, recipient)
            self.assertEqual(scope, self.scope)
            self.assertEqual(reason, "two folders your user linked")
        with mock.patch.object(adapters, "to_codex", return_value=None) as transport:
            self.transport = transport
            ids = []
            for sender, recipient in ((a, b), (b, a)):
                with self.subTest(initiator=sender["name"]):
                    request = self._handover(sender, recipient, "question from " + sender["name"])
                    self.assertNotIn("outcome", ledger.status(request))
                    reply = self._handover(recipient, sender, "answer from " + recipient["name"],
                                           reply_to=request)
                    closed = ledger.status(request)
                    self.assertEqual(closed["outcome"], "succeeded")
                    self.assertEqual(closed["closed_by"]["ref"], recipient["ref"])
                    self.assertEqual(ledger.status(reply)["reply_to"], request)
                    ids.extend((request, reply))
            self.assertEqual(transport.call_count, 4)
            self.assertEqual(len(set(ids)), 4)
        # Keep ancestry intact: removing folder authority removes scope.
        self.assertTrue(config.drop_link(a["cwd"], b["cwd"]))
        self.assertIsNone(config.scope_for(a, b)[0])
        self.assertIsNone(config.scope_for(b, a)[0])

    def test_siblings_roundtrip_both_ways_under_approved_folder_link(self):
        self._exercise(siblings=True)

    def test_different_parents_roundtrip_both_ways_under_approved_folder_link(self):
        self._exercise(siblings=False)


if __name__ == "__main__":
    unittest.main()
