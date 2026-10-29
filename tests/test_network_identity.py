import unittest
from tests.test_xsm import TempState


class NetworkIdentityTest(TempState):
    def endpoint(self, **changes):
        return dict(dict(machine="a"*64, home_id="b"*64, runtime="codex", session_id="thread-1"), **changes)

    def test_remote_machine_and_home_are_both_part_of_canonical_identity(self):
        from xsm import envelope
        receiver = dict(runtime="codex", home=self.tmp, session_id="receiver")
        def digest(sender):
            return envelope.request_digest(envelope.request_identity("r1", sender, receiver, "same"))
        original = digest(self.endpoint())
        self.assertNotEqual(original, digest(self.endpoint(machine="c"*64)))
        self.assertNotEqual(original, digest(self.endpoint(home_id="c"*64)))
        self.assertEqual(original, digest(self.endpoint(name="renamed")))

    def test_remote_sender_original_can_be_claimed_without_a_fabricated_local_home(self):
        from xsm import handoff
        receiver = dict(runtime="codex", home=self.tmp, session_id="receiver")
        saved = handoff.store(receiver, {"id":"remote-r1", "sender":self.endpoint(), "body":"original"})
        self.assertNotIn("home", saved["message"]["sender"])
        self.assertEqual(handoff._identity(saved["message"]["sender"]), self.endpoint())
        with self.assertRaises(ValueError):
            handoff.store(receiver, {"id":"remote-r1", "sender":self.endpoint(home_id="c"*64), "body":"original"})

    def test_opaque_targets_roundtrip_and_private_home_or_missing_machine_is_rejected(self):
        from xsm.network_identity import endpoint, target, parse_target
        self.assertEqual(parse_target(target(self.endpoint())), self.endpoint())
        for bad in (self.endpoint(home=self.tmp), self.endpoint(machine="claimed-name"), self.endpoint(home_id="")):
            with self.assertRaises(ValueError):
                endpoint(bad)

    def test_local_identity_shape_is_unchanged(self):
        from xsm import envelope, handoff
        record = dict(runtime="codex", home=self.tmp, session_id="receiver")
        self.assertEqual(set(handoff._identity(record)), {"runtime", "home", "session_id"})
        self.assertEqual(set(envelope._handle_for_digest(envelope._canon_handle(record))),
                         {"ref", "runtime", "home", "conversation"})
