"""Canonical pending lookup never claims, acknowledges, recovers or writes."""
import os
from pathlib import Path
from unittest import mock

from tests import test_xsm


class PendingIDsTest(test_xsm.TempState):
    def setUp(self):
        super().setUp()
        self.receiver = {'runtime': 'codex', 'home': self.tmp+'/codex', 'session_id': 'receiver'}
        self.sender = {'runtime': 'claude', 'home': self.tmp+'/claude', 'session_id': 'sender'}
        self.message = {'id': 'm1', 'sender': self.sender, 'body': 'work', 'kind': 'task',
                        'scope': 'test', 'reply_to': None}
        self.owner = {'type': 'native', 'id': 'reader'}
        self.generation = 'pid:123-start:456'

    def _store(self, **kwargs):
        from xsm import handoff
        return handoff.store(self.receiver, self.message, **kwargs)

    def _claim(self, **kwargs):
        from xsm import handoff
        return handoff.claim(self.receiver, self.owner, self.generation, kwargs.get('lease', 30))

    def _snapshot(self):
        return {str(p): (p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_ino)
                for p in Path(self.tmp).rglob('*') if p.is_file()}

    def test_missing_endpoint_read_creates_no_folder_or_lock(self):
        from xsm import handoff
        before = self._snapshot()
        self.assertEqual(handoff.pending_ids(self.receiver), [])
        self.assertEqual(self._snapshot(), before)
        self.assertFalse(os.path.exists(handoff._folder(self.receiver)))

    def test_only_pending_delivered_routes_are_counted_without_writes(self):
        from xsm import handoff
        self._store()
        for index, state in enumerate(handoff.DELIVERY_STATES):
            mid = 'state%d' % index
            handoff.store(self.receiver, dict(self.message, id=mid))
            handoff.delivery(self.receiver, mid, state, route='native')
        before = self._snapshot()
        with mock.patch.object(handoff, '_write', side_effect=AssertionError('read-only')):
            ids = handoff.pending_ids(self.receiver)
        self.assertEqual(set(ids), {'m1', 'state0', 'state1'})
        self.assertEqual(self._snapshot(), before)
        self.assertEqual(handoff.pending_ids(dict(self.receiver, home=self.tmp+'/other')), [])

    def test_route_is_top_level_and_ack_is_never_resurrected(self):
        from xsm import handoff
        original = self._store()
        routed = handoff.delivery(self.receiver, 'm1', 'pending', route='mcp-inbox')
        self.assertEqual(routed['message'], original['message'])
        self.assertEqual(routed['identity'], original['identity'])
        self.assertEqual(routed['digest'], original['digest'])
        claim = self._claim()
        handoff.ack(self.receiver, claim['claim']['token'], self.owner, self.generation)
        after = self._snapshot()
        current = handoff.delivery(self.receiver, 'm1', 'pending', route='native')
        self.assertEqual(current['status'], 'acknowledged')
        self.assertEqual(current['delivery_route'], 'mcp-inbox')
        self.assertEqual(handoff.pending_ids(self.receiver, owner_alive=lambda *args: False), [])
        self.assertEqual(self._snapshot(), after)

    def test_expired_and_dead_claims_are_reported_but_not_recovered(self):
        from xsm import handoff
        self._store()
        with mock.patch.object(handoff, '_monotonic', return_value=100):
            self._claim(lease=10)
        before = self._snapshot()
        for now, alive, expected in ((105, True, []), (105, None, []),
                                     (99, None, []), (110, True, ['m1']),
                                     (99, False, ['m1'])):
            with self.subTest(now=now, alive=alive), \
                    mock.patch.object(handoff, '_monotonic', return_value=now):
                self.assertEqual(handoff.pending_ids(self.receiver, owner_alive=lambda *args: alive), expected)
        self.assertEqual(self._snapshot(), before)
        self.assertEqual(handoff.status(self.receiver, 'm1')['status'], 'claimed')

    def test_callback_receives_a_copy_and_expiry_remains_authoritative(self):
        from xsm import handoff
        self._store(retention=0)
        self.assertEqual(handoff.pending_ids(self.receiver), [])
        handoff.store(self.receiver, dict(self.message, id='active'))
        self._claim()
        before = self._snapshot()
        def dead(owner, generation):
            owner['id'] = 'do-not-persist'
            return False
        self.assertEqual(handoff.pending_ids(self.receiver, owner_alive=dead), ['active'])
        self.assertEqual(self._snapshot(), before)

    def test_invalid_state_or_io_failure_never_opens_or_deletes_originals(self):
        from xsm import handoff
        self._store()
        path = Path(handoff._folder(self.receiver))/'m1.json'
        path.write_text('{broken')
        before = self._snapshot()
        with self.assertRaises(ValueError):
            handoff.pending_ids(self.receiver)
        self.assertEqual(self._snapshot(), before)
        with mock.patch.object(handoff, '_records', side_effect=PermissionError('private state')):
            with self.assertRaises(PermissionError):handoff.pending_ids(self.receiver)
        self.assertEqual(self._snapshot(), before)

    def test_receipt_filter_only_reopens_pending_traffic_retries(self):
        from xsm import handoff, ledger
        for decision in ('held', 'blocked'):
            for state in ('pending', 'delivered', 'error'):
                mid = decision+'-'+state
                handoff.store(self.receiver, dict(self.message, id=mid))
                handoff.delivery(self.receiver, mid, state)
                ledger.receipt(mid, decision, self.receiver, 'traffic retry_after=0')
        before = self._snapshot()
        self.assertEqual(set(handoff.pending_ids(self.receiver)),
                         {'held-pending', 'blocked-pending'})
        self.assertEqual(self._snapshot(), before)
