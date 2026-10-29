"""ADR-0021 file-store tests, separate from transport and physical-machine tests.

Fixture signatures below deliberately use a PUBLIC, forgeable hash function.
They test callback wiring and graph validation, not cryptographic security.
Real Ed25519 verification uses the built Rust sidecar on every Python version;
the native binary is required, and its absence fails rather than skips tests.
Native processes use temporary state and relay=off. No test reads a key file,
starts an installed service, or edits global configuration.
"""
import copy
import hashlib
import json
import multiprocessing
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from xsm import network_membership as nm


def key(name):
    return hashlib.sha256(name.encode()).hexdigest()


A, B, C, D = [key(name) for name in ("a", "b", "c", "d")]


def fixture_signature(public_key, data):
    return hashlib.sha512(b"INSECURE UNIT FIXTURE:" + public_key.encode() + data).hexdigest()


def fixture_verify(public_key, data, signature):
    return signature == fixture_signature(public_key, data)


def fixture_store(root, node=A, clock=lambda: 1000):
    return nm.MembershipStore(root, node, lambda data: fixture_signature(node, data),
                              fixture_verify, clock)


def resign(record, issuer=None):
    if issuer:
        record["issuer"] = issuer
    record["signature"] = fixture_signature(record["issuer"], nm._json(nm._unsigned(record)))
    return record


def concurrent_worker(root, secret, endpoint, barrier, results, issue=False):
    """Spawned processes each open their own instance and actual file lock."""
    store = fixture_store(root)
    try:
        barrier.wait(timeout=15)
        if issue:
            value = store.issue_invite(lifetime_seconds=60)["invite"]["invite_hash"]
        else:
            value = store.redeem(secret, endpoint, "same display name")["admission"]
        results.put(("ok", value))
    except Exception as exc:
        results.put(("error", str(exc)))


class MembershipFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = 1000
        self.a = self.store("a", A)
        self.a.initialize("team", "founder")

    def store(self, name, node):
        return fixture_store(self.root / name, node, lambda: self.now)

    def join(self, node=B, name="b", issuer=None, reusable=True):
        issuer = issuer or self.a
        invite = issuer.issue_invite(reusable=reusable, lifetime_seconds=60)
        result = issuer.redeem(invite["secret"], node, name)
        store = self.store(name, node)
        store.adopt(result["state"])
        return store, invite, result

    def assert_code(self, code, call, *args, **kwargs):
        with self.assertRaises(nm.MembershipError) as raised:
            call(*args, **kwargs)
        self.assertEqual(raised.exception.code, code)

    def test_initialize_restart_and_private_files(self):
        restarted = self.store("a", A)
        self.assertEqual(restarted.snapshot(), self.a.snapshot())
        self.assertTrue(restarted.is_active(A))
        self.assertFalse(restarted.is_active("founder"))
        for path in (self.a.root, self.a.path, self.a.root / "membership.lock"):
            expected = 0o700 if path.is_dir() else 0o600
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), expected)
        self.assert_code("already_initialized", self.a.initialize, "other", "other")

    def test_root_bound_network_id_and_readonly_founder_survive_adopt_and_removal(self):
        network_id = self.a.snapshot()["network_id"]
        self.assertEqual(network_id.split(":")[0], A)
        self.assertEqual(self.a.network_id, network_id)
        self.assertEqual(self.a.founder, A)
        self.assertEqual(self.a.founder_public_key, A)
        b, _, _ = self.join()
        b.remove(A)
        restarted = self.store("b", B)
        self.assertEqual(restarted.network_id, network_id)
        self.assertEqual(restarted.snapshot()["network_id"], network_id)
        self.assertEqual(restarted.founder, A)
        self.assertFalse(restarted.is_active(A))
        for name in ("network_id", "founder", "founder_public_key"):
            with self.assertRaises(AttributeError):
                setattr(restarted, name, B)

    def test_genesis_root_and_nonce_cannot_change_under_same_network_id(self):
        original = self.a.snapshot()
        before = self.a.path.read_bytes()
        for field, value in (("issuer", B), ("nonce", "0" * 64), ("name", "other team")):
            bad = copy.deepcopy(original)
            bad["records"][0][field] = value
            # Even a valid signature for a substituted root is insufficient.
            resign(bad["records"][0])
            self.assert_code("invalid_genesis", self.a.adopt, bad)
            self.assertEqual(before, self.a.path.read_bytes())
        other = self.store("same-founder", A)
        other.initialize("team", "founder")
        self.assertNotEqual(self.a.network_id, other.network_id)
        self.assertEqual(self.a.founder, other.founder)

    def test_empty_store_and_bootstrap_require_verified_self_admission(self):
        b = self.store("b", B)
        self.assertEqual(b.public_state(), {})
        self.assertEqual(b.snapshot(), {})
        self.assertFalse(b.is_active(B))
        self.assertIsNone(b.network_id)
        self.assertIsNone(b.founder)
        self.assert_code("not_admitted", b.adopt, self.a.snapshot())
        self.assertFalse(b.path.exists())
        forged = self.a.snapshot()
        forged["records"][0]["signature"] = "00" * 64
        self.assert_code("invalid_signature", b.adopt, forged)
        self.assertFalse(b.path.exists())

    def test_public_lists_and_all_files_contain_no_invite_secret(self):
        invite = self.a.issue_invite(lifetime_seconds=71)
        result = self.a.redeem(invite["secret"], B, "peer")
        for value in (self.a.public_state(), self.a.members(), self.a.snapshot(), result):
            rendered = json.dumps(value)
            self.assertNotIn(invite["secret"], rendered)
            self.assertNotIn('"secret"', rendered)
            self.assertNotIn("private_key", rendered)
        for path in self.a.root.iterdir():
            self.assertNotIn(invite["secret"].encode(), path.read_bytes())
        self.assertNotIn("signature", json.dumps(self.a.public_state()))

    def test_every_active_member_can_invite_remove_founder_and_revoke(self):
        b, _, _ = self.join()
        c, invite, _ = self.join(C, "c", b)
        # A is never called again: the founder can be offline.
        c.remove(A)
        b.merge(c.snapshot())
        b.revoke_invite(invite["invite"]["invite_hash"])
        b.remove(C)
        b.issue_invite(lifetime_seconds=9)
        self.assertFalse(b.is_active(A))
        self.assertFalse(b.is_active(C))
        self.assertTrue(b.is_active(B))

    def test_reusable_link_works_at_another_active_member(self):
        b, _, _ = self.join()
        invite = self.a.issue_invite()
        b.merge(self.a.snapshot())
        b.redeem(invite["secret"], C, "c")
        b.redeem(invite["secret"], D, "d")
        self.assertTrue(b.is_active(C))
        self.assertTrue(b.is_active(D))

    def test_caller_specifies_ttl_and_exact_expiry_is_refused(self):
        for value in (None, 0, -1, True, float("inf"), float("nan"), "60"):
            self.assert_code("invalid_lifetime", self.a.issue_invite,
                             reusable=False, lifetime_seconds=value)
        invite = self.a.issue_invite(reusable=False, lifetime_seconds=7.25)
        self.assertEqual(invite["invite"]["expires_at"], 1007.25)
        self.now = 1007.25
        before = self.a.path.read_bytes()
        self.assert_code("expired_invite", self.a.redeem, invite["secret"], B, "b")
        self.assertEqual(before, self.a.path.read_bytes())
        self.assertEqual(self.a.issue_invite()["invite"]["expires_at"], None)

    def test_sign_callback_gets_final_canonical_bytes_once_and_verify_gets_public_key(self):
        self.a.sign = mock.Mock(side_effect=lambda data: fixture_signature(A, data))
        self.a.verify = mock.Mock(side_effect=fixture_verify)
        invite = self.a.issue_invite(reusable=False, lifetime_seconds=12)
        self.a.sign.assert_called_once()
        payload = self.a.sign.call_args[0][0]
        self.assertIsInstance(payload, bytes)
        record = json.loads(payload)
        self.assertNotIn("signature", record)
        self.assertEqual(record["expires_at"], 1012)
        self.assertEqual(record["network_id"], self.a.network_id)
        self.assertEqual(record["domain"], nm.DOMAIN)
        self.a.verify.assert_any_call(A, payload, invite["invite"]["signature"])

    def test_one_time_requires_issuer_even_if_that_issuer_is_offline(self):
        b, _, _ = self.join()
        invite = self.a.issue_invite(reusable=False, lifetime_seconds=60)
        b.merge(self.a.snapshot())
        self.assert_code("issuer_required", b.redeem, invite["secret"], C, "c")
        self.assertFalse(b.is_active(C))

    def test_lost_response_restart_returns_identical_admission(self):
        invite = self.a.issue_invite(reusable=False, lifetime_seconds=3)
        first = self.a.redeem(invite["secret"], B, "b")
        durable = self.a.path.read_bytes()
        self.now += 5  # An accepted admission outlives invite expiration.
        retried = self.store("a", A).redeem(invite["secret"], B, "different name")
        self.assertEqual(first, retried)
        self.assertEqual(durable, self.a.path.read_bytes())
        self.assert_code("invite_consumed", self.a.redeem, invite["secret"], C, "c")

    def test_crash_after_replace_recovers_consumption_without_second_admission(self):
        invite = self.a.issue_invite(reusable=False, lifetime_seconds=5)
        original = nm.os.replace

        def replace_then_lose_response(source, target):
            original(source, target)
            raise OSError("simulated response loss after commit")

        with mock.patch.object(nm.os, "replace", side_effect=replace_then_lose_response):
            with self.assertRaises(OSError):
                self.a.redeem(invite["secret"], B, "b")
        retry = self.store("a", A).redeem(invite["secret"], B, "b")
        self.assertTrue(self.a.is_active(B))
        self.assertEqual(sum(r["op"] == "admit" for r in retry["state"]["records"]), 1)

    def test_removed_device_cannot_reuse_consumed_code_or_mutate(self):
        b, invite, _ = self.join(reusable=False)
        self.a.remove(B)
        b.merge(self.a.snapshot())
        self.assertFalse(b.is_active(B))
        self.assert_code("invite_consumed", self.a.redeem, invite["secret"], B, "b")
        self.assert_code("inactive_issuer", b.issue_invite)
        self.assert_code("inactive_issuer", b.remove, A)
        fresh = self.a.issue_invite(reusable=False, lifetime_seconds=12)
        result = self.a.redeem(fresh["secret"], B, "b again")
        b.adopt(result["state"])
        self.assertTrue(b.is_active(B))
        # A fresh rejoin cannot resurrect retry eligibility of the old admission.
        self.assert_code("invite_consumed", self.a.redeem, invite["secret"], B, "b")

    def test_removal_revokes_old_reusable_links_and_new_invite_allows_explicit_rejoin(self):
        b, invite, first = self.join()
        c, other_invite, _ = self.join(C, "c")
        b.merge(self.a.snapshot())
        b_invite = b.issue_invite()
        c.merge(b.snapshot())
        c.remove(B)  # Any active member can remove and rotate existing links.
        self.a.merge(c.snapshot())
        for old in (invite, other_invite, b_invite):
            for store in (self.a, c):
                with self.subTest(issuer=store.node_id, old_hash=old["invite"]["invite_hash"]):
                    with self.assertRaises(nm.MembershipError):
                        store.redeem(old["secret"], B, "b with old ticket")
        self.assertFalse(c.is_active(B))
        fresh = c.issue_invite(lifetime_seconds=30)
        second = c.redeem(fresh["secret"], B, "b explicitly rejoined")
        self.assertNotEqual(first["admission"], second["admission"])
        b.adopt(second["state"])
        self.assertTrue(b.is_active(B))
        # A lost successful response is recovered from the new admission.
        self.assertEqual(second, self.store("c", C).redeem(fresh["secret"], B, "ignored"))
        self.assert_code("revoked_invite", c.redeem, invite["secret"], B, "old ticket after rejoin")

    def test_remove_and_leave_revoke_links_under_one_lock_and_one_commit(self):
        for action in ("remove", "leave"):
            with self.subTest(action=action):
                actor = self.store(action, A)
                actor.initialize("atomic removal", "a")
                first = actor.issue_invite()
                state = actor.redeem(first["secret"], B, "b")["state"]
                peer = self.store(action + "-peer", B)
                peer.adopt(state)
                second = peer.issue_invite(lifetime_seconds=30)
                actor.merge(peer.snapshot())
                once = actor.issue_invite(reusable=False, lifetime_seconds=30)
                before = actor.path.read_bytes()
                original_sign = actor.sign

                def sign_while_original_is_intact(data):
                    self.assertEqual(before, actor.path.read_bytes())
                    return original_sign(data)

                with mock.patch.object(actor, "_locked", wraps=actor._locked) as locked, \
                        mock.patch.object(actor, "_write", wraps=actor._write) as commit, \
                        mock.patch.object(actor, "sign", side_effect=sign_while_original_is_intact):
                    result = actor.remove(B) if action == "remove" else actor.leave()
                locked.assert_called_once()
                commit.assert_called_once()
                self.assertEqual(result, fixture_store(actor.root, A).snapshot())
                rows = {r["invite_hash"]: r for r in actor.public_state()["invites"]}
                self.assertTrue(rows[first["invite"]["invite_hash"]]["revoked"])
                self.assertTrue(rows[second["invite"]["invite_hash"]]["revoked"])
                self.assertFalse(rows[once["invite"]["invite_hash"]]["revoked"])
                removed = B if action == "remove" else A
                self.assertFalse(actor.is_active(removed))
                survivor = actor if action == "remove" else peer
                if action == "leave":
                    peer.merge(result)
                fresh = survivor.issue_invite(lifetime_seconds=20)
                survivor.redeem(fresh["secret"], removed, "explicitly rejoined")
                self.assertTrue(survivor.is_active(removed))

    def test_remove_and_leave_failures_preserve_member_and_original_links(self):
        for action in ("remove", "leave"):
            for failure in ("sign", "verify", "fsync", "replace"):
                with self.subTest(action=action, failure=failure):
                    actor = self.store(action + "-" + failure, A)
                    actor.initialize("preserve original", "a")
                    first = actor.issue_invite()
                    actor.redeem(first["secret"], B, "b")
                    second = actor.issue_invite()
                    before = actor.path.read_bytes()
                    original_sign, original_verify = actor.sign, actor.verify
                    signed = []

                    def failing_sign(data):
                        signed.append(json.loads(data))
                        if failure == "sign" and len(signed) == 2:
                            raise OSError("second staged signature failed")
                        return original_sign(data)

                    def failing_verify(public, data, signature):
                        record = json.loads(data)
                        if failure == "verify" and record["op"] == "remove":
                            return False
                        return original_verify(public, data, signature)

                    target = "fsync" if failure == "fsync" else "replace"
                    patch_io = (mock.patch.object(nm.os, target, side_effect=OSError("commit failed"))
                                if failure in ("fsync", "replace") else mock.patch.object(actor, "verify", side_effect=failing_verify))
                    with mock.patch.object(actor, "sign", side_effect=failing_sign), patch_io:
                        with self.assertRaises((OSError, nm.MembershipError)):
                            actor.remove(B) if action == "remove" else actor.leave()
                    self.assertEqual(before, actor.path.read_bytes())
                    restarted = fixture_store(actor.root, A)
                    self.assertTrue(restarted.is_active(A))
                    self.assertTrue(restarted.is_active(B))
                    self.assertTrue(all(not row["revoked"] for row in restarted.public_state()["invites"]))
                    restarted.redeem(second["secret"], C, "still valid after failed removal")

    def test_removal_response_loss_preserves_rotation_and_fresh_join_retry(self):
        for action in ("remove", "leave"):
            with self.subTest(action=action):
                actor = self.store(action + "-response-loss", A)
                actor.initialize("lost response", "a")
                first = actor.issue_invite()
                peer = self.store(action + "-response-peer", B)
                peer.adopt(actor.redeem(first["secret"], B, "b")["state"])
                peer_link = peer.issue_invite()
                actor.merge(peer.snapshot())
                original_replace = nm.os.replace

                def replace_then_lose_response(source, target):
                    original_replace(source, target)
                    raise OSError("response lost after atomic commit")

                with mock.patch.object(nm.os, "replace", side_effect=replace_then_lose_response):
                    with self.assertRaises(OSError):
                        actor.remove(B) if action == "remove" else actor.leave()
                restored = fixture_store(actor.root, A)
                removed = B if action == "remove" else A
                self.assertFalse(restored.is_active(removed))
                self.assertTrue(all(row["revoked"] for row in restored.public_state()["invites"]))
                survivor = restored if action == "remove" else peer
                if action == "leave":
                    peer.merge(restored.snapshot())
                old = first if action == "remove" else peer_link
                self.assert_code("revoked_invite", survivor.redeem, old["secret"], removed, "old ticket")
                fresh = survivor.issue_invite(lifetime_seconds=20)
                with mock.patch.object(nm.os, "replace", side_effect=replace_then_lose_response):
                    with self.assertRaises(OSError):
                        survivor.redeem(fresh["secret"], removed, "explicit rejoin")
                # Reopening retrieves the one committed admission after its lost response.
                survivor = fixture_store(survivor.root, survivor.node_id)
                durable = survivor.path.read_bytes()
                retry = survivor.redeem(fresh["secret"], removed, "retry")
                self.assertTrue(survivor.is_active(removed))
                self.assertEqual(durable, survivor.path.read_bytes())
                self.assertEqual(sum(r["op"] == "admit" and r["invite_hash"] == fresh["invite"]["invite_hash"]
                                     for r in retry["state"]["records"]), 1)

    def test_revoked_invite_rejects_fresh_and_cached_retry(self):
        _, invite, _ = self.join()
        self.a.revoke_invite(invite["invite"]["invite_hash"])
        for endpoint in (B, C):
            self.assert_code("revoked_invite", self.a.redeem, invite["secret"], endpoint, "peer")
        self.assertTrue(self.a.is_active(B))  # Revocation does not expel existing members.

    def test_removed_invite_issuer_cannot_lend_authority(self):
        b, _, _ = self.join()
        invite = self.a.issue_invite()
        b.merge(self.a.snapshot())
        b.remove(A)
        self.assert_code("inactive_issuer", b.redeem, invite["secret"], C, "c")

    def test_wrong_network_unknown_and_malformed_secret(self):
        other = self.store("other", D)
        other.initialize("team", "founder")  # Same names are irrelevant.
        secret = self.a.issue_invite()["secret"]
        self.assert_code("unknown_invite", other.redeem, secret, C, "c")
        self.assert_code("wrong_network", self.a.merge, other.snapshot())
        self.assert_code("invalid_redemption", self.a.redeem, "short", C, "c")

    def test_operation_domain_network_and_signature_tampering(self):
        self.a.issue_invite(lifetime_seconds=30)
        original = self.a.snapshot()
        for field, value, code in (("domain", "other/protocol", "invalid_record"),
                                   ("network_id", "0" * 64, "invalid_record"),
                                   ("signature", "0" * 128, "invalid_signature"),
                                   ("reusable", False, "invalid_signature")):
            bad = copy.deepcopy(original)
            bad["records"][-1][field] = value
            self.assert_code(code, self.a.merge, bad)
        bad = copy.deepcopy(original)
        bad["records"][-1]["domain"] = "native/member"
        resign(bad["records"][-1])
        self.assert_code("invalid_record", self.a.merge, bad)

    def test_valid_signature_is_not_an_admission_chain(self):
        self.a.issue_invite(lifetime_seconds=30)
        bad = self.a.snapshot()
        # Correct fixture signature, but signer B has no admission.
        resign(bad["records"][-1], B)
        self.assert_code("inactive_issuer", self.a.merge, bad)
        # Correct signer, but a claimed admission references no valid invite.
        bad = self.a.snapshot()
        r = bad["records"][-1]
        r.update(op="admit", endpoint_id=B, machine_name="founder", invite_hash="0" * 64)
        del r["reusable"], r["expires_at"]
        resign(r)
        self.assert_code("unknown_invite", self.a.merge, bad)

    def test_admission_endpoint_and_machine_name_are_signed(self):
        _, _, result = self.join()
        for field, value in (("endpoint_id", C), ("machine_name", "founder")):
            bad = copy.deepcopy(result["state"])
            bad["records"][-1][field] = value
            self.assert_code("invalid_signature", self.a.merge, bad)

    def test_unsigned_native_members_and_names_never_become_authority(self):
        for bad in ({"network_id": self.a.snapshot()["network_id"], "members": [{"name": "founder", "key": B}]},
                    dict(self.a.snapshot(), members=[{"endpoint_id": B, "role": "founder"}])):
            self.assert_code("invalid_state", self.a.merge, bad)
        bad = self.a.snapshot()
        bad["records"][0]["role"] = "administrator"
        resign(bad["records"][0])
        self.assert_code("invalid_record", self.a.merge, bad)
        self.assertFalse(self.a.is_active("founder"))
        self.assert_code("invalid_identity", self.a.remove, "founder")

    def test_merge_is_order_independent_and_keeps_removal_and_revocation(self):
        b, invite, _ = self.join()
        old = b.snapshot()
        self.a.remove(B)
        b.revoke_invite(invite["invite"]["invite_hash"])
        left, right = self.a.snapshot(), b.snapshot()
        self.a.merge(right)
        b.merge(left)
        self.assertEqual(self.a.snapshot(), b.snapshot())
        self.a.merge(old)
        self.assertFalse(self.a.is_active(B))
        self.assert_code("revoked_invite", self.a.redeem, invite["secret"], C, "c")
        self.assertEqual(self.a.snapshot(), b.snapshot())

    def test_removed_issuer_descendant_is_rejected(self):
        b, _, _ = self.join()
        self.a.remove(B)
        b.merge(self.a.snapshot())
        # Deliberately bypass public checks, including a valid fixture signature.
        bad = b.snapshot()
        bad["records"].append(b._record("invite", nm._Graph(bad, fixture_verify),
            invite_hash="e" * 64, reusable=True, expires_at=None))
        self.assert_code("inactive_issuer", self.a.merge, bad)

    def test_adopt_new_network_validates_before_commit_and_old_survives_failure(self):
        old = self.a.path.read_bytes()
        other = self.store("other", D)
        other.initialize("second", "d")
        invite = other.issue_invite(lifetime_seconds=30)
        result = other.redeem(invite["secret"], A, "a")
        bad = copy.deepcopy(result["state"])
        bad["records"][-1]["signature"] = "0" * 128
        self.assert_code("invalid_signature", self.a.adopt, bad)
        self.assertEqual(old, self.a.path.read_bytes())
        with mock.patch.object(nm.os, "replace", side_effect=OSError("commit failed")):
            with self.assertRaises(OSError):
                self.a.adopt(result["state"])
        self.assertEqual(old, self.a.path.read_bytes())
        self.assertEqual(self.store("a", A).public_state()["name"], "team")
        self.a.adopt(result["state"])
        self.assertEqual(self.store("a", A).snapshot()["network_id"], other.snapshot()["network_id"])
        self.assertEqual(list(self.a.root.glob(".membership-*")), [])

    def test_same_network_adopt_cannot_rollback_removal(self):
        b, _, _ = self.join()
        old = b.snapshot()
        self.a.remove(B)
        b.merge(self.a.snapshot())
        before = b.path.read_bytes()
        self.assert_code("not_admitted", b.adopt, old)
        self.assertEqual(before, b.path.read_bytes())

    def test_failed_write_does_not_consume_invite_and_fsync_precedes_replace(self):
        invite = self.a.issue_invite(reusable=False, lifetime_seconds=30)
        before = self.a.path.read_bytes()
        with mock.patch.object(nm.os, "fsync", side_effect=OSError("disk failed")):
            with self.assertRaises(OSError):
                self.a.redeem(invite["secret"], B, "b")
        self.assertEqual(before, self.a.path.read_bytes())
        result = self.a.redeem(invite["secret"], B, "b")
        self.assertEqual(result["admission"]["endpoint_id"], B)
        calls = []
        real_fsync, real_replace = nm.os.fsync, nm.os.replace

        def fsync(fd):
            calls.append("fsync")
            return real_fsync(fd)

        def replace(source, target):
            calls.append("replace")
            return real_replace(source, target)

        with mock.patch.object(nm.os, "fsync", side_effect=fsync), mock.patch.object(nm.os, "replace", side_effect=replace):
            self.a.issue_invite()
        self.assertEqual(calls, ["fsync", "replace", "fsync"])

    def test_corrupt_persistent_state_fails_closed(self):
        for contents in (b"{", b"null", b"\xff", b"x" * (nm.MAX_STATE_BYTES + 1)):
            self.a.path.write_bytes(contents)
            with self.assertRaises(nm.MembershipError):
                self.store("a", A).is_active(A)

    def test_input_bounds_and_missing_or_duplicate_parents(self):
        self.a.issue_invite()
        good = self.a.snapshot()
        for parent in (["0" * 64], [nm._hash(good["records"][-1])], [nm._hash(good["records"][0])] * 2):
            bad = copy.deepcopy(good)
            bad["records"][-1]["parents"] = parent
            resign(bad["records"][-1])
            with self.assertRaises(nm.MembershipError):
                self.a.merge(bad)
        with mock.patch.object(nm, "MAX_RECORDS", 1):
            self.assert_code("invalid_state", self.a.merge, good)
        with mock.patch.object(nm, "MAX_STATE_BYTES", 10):
            self.assert_code("state_too_large", self.a.snapshot)

    def test_deep_untrusted_input_is_rejected_before_copy_or_commit(self):
        bad = self.a.snapshot()
        nested = []
        for _ in range(2000):
            nested = [nested]
        bad["records"][0]["name"] = nested
        before = self.a.path.read_bytes()
        with self.assertRaises(nm.MembershipError):
            self.a.merge(bad)
        with self.assertRaises(nm.MembershipError):
            self.a.adopt(bad)
        self.assertEqual(before, self.a.path.read_bytes())

    def test_one_time_double_spend_forks_rejected_even_with_valid_signatures(self):
        invite = self.a.issue_invite(reusable=False, lifetime_seconds=20)
        branch = self.a.snapshot()
        first = self.a.redeem(invite["secret"], B, "b")["state"]
        # Reproduce a copied/rolled-back issuer store, not the normal flock path.
        alternate = fixture_store(self.root / "copied-issuer")
        alternate.adopt(branch)
        second = alternate.redeem(invite["secret"], C, "c")["state"]
        before = self.a.path.read_bytes()
        self.assert_code("conflicting_consumption", self.a.merge, second)
        self.assertEqual(before, self.a.path.read_bytes())
        self.assertTrue(self.a.is_active(B))
        self.assertFalse(self.a.is_active(C))
        self.assertEqual(first, self.a.snapshot())

    def test_return_values_are_detached_and_callback_failure_fails_closed(self):
        result = self.a.snapshot()
        result["records"][0]["name"] = "mutated"
        self.assertEqual(self.a.public_state()["name"], "team")
        before = self.a.path.read_bytes()
        self.a.sign = lambda data: "00" * 64
        self.assert_code("invalid_signature", self.a.issue_invite)
        self.assertEqual(before, self.a.path.read_bytes())
        self.a.verify = mock.Mock(side_effect=OSError("verifier unavailable"))
        self.assert_code("invalid_signature", self.a.snapshot)

    def test_leave_is_signed_removal_and_blocks_later_operations(self):
        state = self.a.leave()
        self.assertEqual(state["records"][-1]["op"], "remove")
        self.assertFalse(self.store("a", A).is_active(A))
        self.assert_code("inactive_issuer", self.a.issue_invite)

    def race(self, endpoints, issue=False):
        invite = self.a.issue_invite(reusable=False, lifetime_seconds=30)
        ctx = multiprocessing.get_context("spawn")
        barrier, results = ctx.Barrier(len(endpoints)), ctx.Queue()
        processes = [ctx.Process(target=concurrent_worker,
            args=(str(self.a.root), invite["secret"], endpoint, barrier, results, issue))
            for endpoint in endpoints]
        try:
            for process in processes:
                process.start()
            output = [results.get(timeout=20) for _ in processes]
            for process in processes:
                process.join(timeout=10)
                self.assertEqual(process.exitcode, 0)
            return output
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
            results.close()
            results.join_thread()

    def test_concurrent_processes_serialize_one_time_consumption(self):
        output = self.race([B, C])
        self.assertEqual(sorted(row[0] for row in output), ["error", "ok"])
        self.assertEqual([row[1] for row in output if row[0] == "error"], ["invite_consumed"])
        self.assertEqual(sum(self.a.is_active(endpoint) for endpoint in (B, C)), 1)

    def test_concurrent_same_device_retry_returns_same_admission(self):
        output = self.race([B, B])
        self.assertEqual([row[0] for row in output], ["ok", "ok"])
        self.assertEqual(output[0][1], output[1][1])
        self.assertEqual(sum(r["op"] == "admit" for r in self.a.snapshot()["records"]), 1)

    def test_concurrent_invite_writers_do_not_lose_records(self):
        output = self.race([B, C, D, A], issue=True)
        self.assertTrue(all(row[0] == "ok" for row in output))
        self.assertEqual(len({row[1] for row in output}), 4)
        self.assertEqual(len(self.store("a", A).public_state()["invites"]), 5)


class RealEd25519MembershipTests(unittest.TestCase):
    def test_real_signatures_admission_chain_restart_and_forgery(self):
        """Real Rust Ed25519 IPC verifies admission and rejects a wrong signer.

        The sidecar alone owns temporary private keys. This retains the former
        optional Python-cryptography case, including a reopened membership file,
        without relying on that Python package or forgeable fixture callbacks.
        """
        from xsm.network_transport import Sidecar

        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            a_node = Sidecar(root / "native-a", relay="off")
            b_node = Sidecar(root / "native-b", relay="off")
            try:
                a_node.start(timeout=15)
                b_node.start(timeout=15)
                a_id, b_id = a_node.endpoint_id, b_node.endpoint_id
                a = nm.MembershipStore(root / "a", a_id, a_node.sign, a_node.verify)
                a.initialize("real crypto", "a")
                invite = a.issue_invite(reusable=False, lifetime_seconds=45)
                result = a.redeem(invite["secret"], b_id, "b")
                b = nm.MembershipStore(root / "b", b_id, b_node.sign, b_node.verify)
                b.adopt(result["state"])
                b.remove(a_id)
                restarted = nm.MembershipStore(b.root, b_id, b_node.sign, b_node.verify)
                self.assertFalse(restarted.is_active(a_id))
                self.assertTrue(restarted.is_active(b_id))
                # A real B signature is valid for B, but not for claimed issuer A.
                bad = copy.deepcopy(result["state"])
                bad["records"][-1]["endpoint_id"] = a_id
                payload = nm._json(nm._unsigned(bad["records"][-1]))
                signature = b_node.sign(payload)
                self.assertTrue(a_node.verify(b_id, payload, signature))
                self.assertFalse(b_node.verify(a_id, payload, signature))
                bad["records"][-1]["signature"] = signature
                before = restarted.path.read_bytes()
                with self.assertRaisesRegex(nm.MembershipError, "invalid_signature"):
                    restarted.merge(bad)
                self.assertEqual(before, restarted.path.read_bytes())
            finally:
                b_node.close()
                a_node.close()


class NativeSignatureMembershipTests(unittest.TestCase):
    def test_actual_rust_callbacks_durable_admission_and_identity_restart(self):
        """Use real Rust-node public keys; no fixture signatures or key-file reads.

        These are transient processes on this host with relay disabled, not
        evidence of physical-machine transport, NAT traversal or deployment.
        """
        from xsm.network_transport import Sidecar

        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            a_node = Sidecar(root / "native-a", relay="off")
            b_node = Sidecar(root / "native-b", relay="off")
            restarted_node = None
            try:
                a_node.start(timeout=15)
                b_node.start(timeout=15)
                a = nm.MembershipStore(root / "membership-a", a_node.endpoint_id, a_node.sign, a_node.verify)
                b = nm.MembershipStore(root / "membership-b", b_node.endpoint_id, b_node.sign, b_node.verify)
                a.initialize("native callbacks", "a")
                invite = a.issue_invite(reusable=False, lifetime_seconds=40)
                result = a.redeem(invite["secret"], b_node.endpoint_id, "b")
                b.adopt(result["state"])
                self.assertEqual(a.network_id, b.network_id)
                self.assertEqual(a.founder, b.founder)
                self.assertTrue(b.is_active(b_node.endpoint_id))
                original_id = b_node.endpoint_id
                old_link = b.issue_invite()
                b.remove(a_node.endpoint_id)
                with self.assertRaisesRegex(nm.MembershipError, "revoked_invite"):
                    b.redeem(old_link["secret"], a_node.endpoint_id, "a with old ticket")
                before = b.path.read_bytes()
                bad = copy.deepcopy(result["state"])
                bad["records"][-1]["machine_name"] = "forged"
                # A valid signature by B must fail on a record claiming A.
                bad["records"][-1]["signature"] = b_node.sign(nm._json(nm._unsigned(bad["records"][-1])))
                with self.assertRaisesRegex(nm.MembershipError, "invalid_signature"):
                    b.merge(bad)
                self.assertEqual(before, b.path.read_bytes())
                b_node.close()
                restarted_node = Sidecar(root / "native-b", relay="off")
                restarted_node.start(timeout=15)
                self.assertEqual(original_id, restarted_node.endpoint_id)
                restored = nm.MembershipStore(b.root, restarted_node.endpoint_id,
                                             restarted_node.sign, restarted_node.verify)
                self.assertTrue(restored.is_active(original_id))
                self.assertFalse(restored.is_active(a_node.endpoint_id))
                self.assertEqual(restored.network_id, a.network_id)
                self.assertEqual(restored.founder, a_node.endpoint_id)
                fresh = restored.issue_invite(lifetime_seconds=30)
                rejoined = restored.redeem(fresh["secret"], a_node.endpoint_id, "a explicitly rejoined")
                self.assertTrue(restored.is_active(a_node.endpoint_id))
                self.assertEqual(rejoined, restored.redeem(fresh["secret"], a_node.endpoint_id, "retry"))
            finally:
                if restarted_node:
                    restarted_node.close()
                b_node.close()
                a_node.close()


if __name__ == "__main__":
    unittest.main()
