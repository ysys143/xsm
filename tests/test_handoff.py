"""Explicit ownership, recovery and compatibility contracts in temporary state."""
import concurrent.futures
import os
from unittest import mock

from tests import test_xsm


class HandoffTest(test_xsm.TempState):
    def setUp(self):
        super().setUp()
        self.receiver = {'runtime': 'codex', 'home': self.tmp + '/codex', 'session_id': 'receiver'}
        self.sender = {'runtime': 'claude', 'home': self.tmp + '/claude', 'session_id': 'sender'}
        self.message = {'id': 'm1', 'sender': self.sender, 'body': 'work', 'kind': 'task',
                        'scope': 'test', 'reply_to': None}
        self.owner = {'type': 'native', 'id': 'reader'}
        self.generation = 'pid:123-start:456'

    def _store(self, **kwargs):
        from xsm import handoff
        return handoff.store(self.receiver, self.message, **kwargs)

    def _claim(self, **kwargs):
        from xsm import handoff
        return handoff.claim(self.receiver, kwargs.get('owner', self.owner),
                             kwargs.get('generation', self.generation), kwargs.get('lease', 30))

    def test_approved_default_lease_recovers_unconfirmed_and_preserves_original(self):
        from xsm import handoff
        self._store()
        with mock.patch.object(handoff, '_monotonic', return_value=100):
            claimed = handoff.claim(self.receiver, self.owner, self.generation)
        self.assertEqual(claimed['claim']['lease'], 120)
        self.assertEqual(claimed['claim']['deadline_mono'], 220)
        with mock.patch.object(handoff, '_monotonic', return_value=219):
            self.assertEqual(handoff.recover(self.receiver)[0]['status'], 'claimed')
        with mock.patch.object(handoff, '_monotonic', return_value=220):
            recovered = handoff.recover(self.receiver)[0]
        self.assertEqual(recovered['status'], 'pending')
        self.assertEqual(recovered['recovery_reason'], 'lease-expired')
        self.assertEqual(recovered['message'], self.message)
        self.assertIsNone(recovered['retention'])
        self.assertEqual(recovered['expiry'], 'unbounded')

    def test_store_canonical_digest_original_and_duplicate_do_not_reset_claim(self):
        from xsm import envelope, handoff
        self.message['body'] = 'caf\u00e9\r\n'
        stored = self._store()
        self.assertEqual(stored['status'], 'pending')
        self.assertEqual(stored['expiry'], 'unbounded')
        expected = envelope.request_identity('m1', self.sender, self.receiver,
                                             self.message['body'], kind='task', scope='test')
        self.assertEqual(stored['digest'], envelope.request_digest(expected))
        claimed = self._claim()
        equivalent = dict(self.message, body='cafe\u0301\n')
        repeated = handoff.store(self.receiver, equivalent)
        self.assertEqual(repeated['claim'], claimed['claim'])
        self.assertEqual(repeated['message']['body'], 'caf\u00e9\r\n')
        for changed in (dict(self.message, body='different'),
                        dict(self.message, sender=dict(self.sender, home='/other')),
                        dict(self.message, scope='other'), dict(self.message, outcome='failed'),
                        dict(self.message, reply_to='other')):
            with self.assertRaises(ValueError):
                handoff.store(self.receiver, changed)
        self.assertEqual(handoff.status(self.receiver, 'm1')['claim'], claimed['claim'])

    def test_handoff_is_not_ack_release_and_ack_are_explicit_and_idempotent(self):
        from xsm import handoff
        self._store()
        first = self._claim()
        token = first['claim']['token']
        handed = handoff.handoff(self.receiver, token, self.owner, self.generation)
        self.assertEqual(handed['status'], 'handoff-recorded')
        self.assertEqual(self._claim()['status'], 'empty')
        returned = handoff.release(self.receiver, token, self.owner, self.generation)
        self.assertEqual(returned['status'], 'pending')
        second = self._claim()
        new_token = second['claim']['token']
        self.assertNotEqual(token, new_token)
        with self.assertRaises(ValueError):
            handoff.ack(self.receiver, token, self.owner, self.generation)
        acked = handoff.ack(self.receiver, new_token, self.owner, self.generation)
        self.assertEqual(acked['status'], 'acknowledged')
        self.assertFalse(acked['recoverable'])
        self.assertEqual(handoff.ack(self.receiver, new_token, self.owner, self.generation), acked)
        self.assertEqual(self._claim()['status'], 'empty')
        self.assertEqual(handoff.recover(self.receiver, owner_alive=lambda *a: False)[0]['status'],
                         'acknowledged')
        self.assertEqual(handoff.status(self.receiver, 'm1')['message'], self.message)
        with self.assertRaises(ValueError):
            handoff.release(self.receiver, new_token, self.owner, self.generation)

    def test_token_generation_owner_and_full_endpoint_boundaries(self):
        from xsm import handoff
        self._store()
        token = self._claim()['claim']['token']
        for function in (handoff.handoff, handoff.ack, handoff.release):
            for changed in (dict(self.receiver, runtime='claude'),
                            dict(self.receiver, home=self.tmp + '/other'),
                            dict(self.receiver, session_id='new')):
                self.assertEqual(handoff.status(changed, 'm1')['status'], 'not-found')
                with self.assertRaises(ValueError):
                    function(changed, token, self.owner, self.generation)
            for bad_token, owner, generation in (
                    ('wrong', self.owner, self.generation), ('0' * 32, self.owner, self.generation),
                    (token, self.owner, 'new-generation'),
                    (token, dict(self.owner, id='other'), self.generation),
                    (token, dict(self.owner, type='legacy-export'), self.generation)):
                with self.assertRaises(ValueError):
                    function(self.receiver, bad_token, owner, generation)
        self.assertEqual(handoff.status(self.receiver, 'm1')['status'], 'claimed')

    def test_concurrent_claims_are_exclusive_and_one_ack_suppresses_replay(self):
        from xsm import handoff
        self._store()
        def claim(i):
            owner = {'type': 'native', 'id': 'reader%d' % i}
            return handoff.claim(self.receiver, owner, 'generation%d' % i, 30)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(claim, range(24)))
        winners = [r for r in results if r['status'] == 'claimed']
        self.assertEqual(len(winners), 1)
        winner = winners[0]['claim']
        handoff.ack(self.receiver, winner['token'], winner['owner'], winner['generation'])
        self.assertEqual(self._claim()['status'], 'empty')

    def test_concurrent_store_and_ordered_claim_keep_each_original(self):
        from xsm import handoff
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            records = list(pool.map(lambda _: self._store(), range(12)))
        self.assertEqual(len({r['digest'] for r in records}), 1)
        handoff.store(self.receiver, dict(self.message, id='m2'))
        first = self._claim()
        second = self._claim(owner={'type': 'native', 'id': 'second'})
        self.assertEqual([first['id'], second['id']], ['m1', 'm2'])
        self.assertEqual(self._claim()['status'], 'empty')

    def test_explicit_lease_dead_owner_unknown_and_backward_clock_recovery(self):
        from xsm import handoff
        self._store()
        with mock.patch.object(handoff, '_monotonic', return_value=100):
            first = self._claim(lease=5)
        token = first['claim']['token']
        with mock.patch.object(handoff, '_monotonic', return_value=99):
            unknown = handoff.recover(self.receiver, owner_alive=lambda *args: None)[0]
        self.assertEqual(unknown['status'], 'claimed')
        self.assertEqual(unknown['recovery_reason'], 'clock-unknown')
        with mock.patch.object(handoff, '_monotonic', return_value=104):
            live = handoff.recover(self.receiver, owner_alive=lambda *args: True)[0]
        self.assertEqual(live['status'], 'claimed')
        with mock.patch.object(handoff, '_monotonic', return_value=105):
            expired = handoff.recover(self.receiver)[0]
        self.assertEqual(expired['recovery_reason'], 'lease-expired')
        self.assertEqual(expired['status'], 'pending')
        with self.assertRaises(ValueError):
            handoff.ack(self.receiver, token, self.owner, self.generation)
        second = self._claim()
        observed = []
        def dead(owner, generation):
            observed.append((owner, generation))
            return False
        recovered = handoff.recover(self.receiver, owner_alive=dead)[0]
        self.assertEqual(recovered['recovery_reason'], 'owner-dead')
        self.assertEqual(observed, [(self.owner, self.generation)])
        self.assertEqual(recovered['message'], self.message)
        self.assertNotEqual(second['claim']['token'], self._claim()['claim']['token'])

    def test_legacy_export_is_owned_and_export_deletion_does_not_ack_original(self):
        from xsm import handoff
        self._store()
        owner = {'type': 'legacy-export', 'id': 'old-inbox-reader'}
        claimed = self._claim(owner=owner, generation='legacy-generation')
        exported = os.path.join(self.tmp, 'legacy-export.json')
        from xsm import paths
        paths.write_json(exported, claimed['message'])
        handoff.handoff(self.receiver, claimed['claim']['token'], owner, 'legacy-generation')
        os.unlink(exported)  # old reader's destructive read is not consumption evidence
        self.assertEqual(handoff.status(self.receiver, 'm1')['status'], 'handoff-recorded')
        self.assertEqual(self._claim()['status'], 'empty')
        handoff.recover(self.receiver, owner_alive=lambda *args: False)
        restored = self._claim()
        self.assertEqual(restored['id'], 'm1')
        self.assertEqual(restored['message'], self.message)
        with self.assertRaises(ValueError):
            handoff.ack(self.receiver, claimed['claim']['token'], owner, 'legacy-generation')

    def test_expired_or_backward_clock_token_cannot_ack_before_recovery(self):
        from xsm import handoff
        self._store()
        with mock.patch.object(handoff, '_monotonic', return_value=100):
            claimed = self._claim(lease=5)
        token = claimed['claim']['token']
        for clock in (99, 105):
            with mock.patch.object(handoff, '_monotonic', return_value=clock):
                for function in (handoff.ack, handoff.handoff, handoff.release):
                    with self.assertRaises(ValueError):
                        function(self.receiver, token, self.owner, self.generation)
        self.assertEqual(handoff.status(self.receiver, 'm1')['status'], 'claimed')
        handoff.recover(self.receiver, owner_alive=lambda *args: False)
        self.assertEqual(handoff.status(self.receiver, 'm1')['status'], 'pending')

    def test_retention_expiry_delivery_and_outcome_are_separate_and_never_delete(self):
        from xsm import handoff
        with mock.patch.object(handoff.time, 'time', return_value=100):
            self._store(retention=5)
        with mock.patch.object(handoff.time, 'time', return_value=99):
            self.assertEqual(handoff.status(self.receiver, 'm1')['expiry'], 'unknown')
            self.assertEqual(self._claim()['status'], 'empty')
        with mock.patch.object(handoff.time, 'time', return_value=105):
            expired = handoff.recover(self.receiver, retention=5)[0]
            self.assertEqual(expired['expiry'], 'expired')
            self.assertEqual(expired['status'], 'pending')
            self.assertEqual(expired['delivery_state'], 'pending')
            self.assertIsNone(expired['outcome'])
            self.assertEqual(self._claim()['status'], 'empty')
            self.assertEqual(handoff.status(self.receiver, 'm1')['message'], self.message)
        for i, state in enumerate(('held', 'offline', 'unknown', 'refused', 'error')):
            record = handoff.store(self.receiver, dict(self.message, id='gate%d' % i,
                                   delivery_state=state, outcome='failed'))
            self.assertEqual(record['status'], 'pending')
            self.assertEqual(record['delivery_state'], state)
            self.assertEqual(record['outcome'], 'failed')
            self.assertEqual(record['expiry'], 'unbounded')

    def test_no_defaults_invalid_values_and_corrupt_original_never_overwritten(self):
        from xsm import handoff, paths
        for bad in (None, 0, -1, float('inf'), True):
            with self.assertRaises(ValueError):
                self._claim(lease=bad)
        for bad in (-1, float('nan'), True):
            with self.assertRaises(ValueError):
                self._store(retention=bad)
        for bad in ({}, dict(self.message, id='../bad'), dict(self.message, sender={}),
                    dict(self.message, target=dict(self.receiver, home='/other'))):
            with self.assertRaises(ValueError):
                handoff.store(self.receiver, bad)
        self.assertEqual(handoff.status(self.receiver, 'm1')['status'], 'not-found')
        self._store()
        folder = handoff._folder(self.receiver)
        filename = os.path.join(folder, 'm1.json')
        with open(filename, 'w') as stream:
            stream.write('{')
        with self.assertRaises(ValueError):
            self._store()
        with open(filename) as stream:
            self.assertEqual(stream.read(), '{')

    def test_status_is_detached_and_readonly_normalizes_home(self):
        from xsm import handoff
        self._store()
        folder = handoff._folder(self.receiver)
        filename = os.path.join(folder, 'm1.json')
        before = os.stat(filename).st_mtime_ns
        same = dict(self.receiver, home=self.receiver['home'] + '/../codex')
        view = handoff.status(same, 'm1')
        view['message']['body'] = 'changed outside'
        self.assertEqual(handoff.status(self.receiver, 'm1')['message']['body'], 'work')
        self.assertEqual(os.stat(filename).st_mtime_ns, before)
        self.assertEqual(os.stat(filename).st_mode & 0o777, 0o600)
