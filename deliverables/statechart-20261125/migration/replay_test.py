"""Replay TLC's paths for XsmHeldDeliver and XsmTransfer against xsm's real code.

A = self.a ("old" profile), B = self.b ("new" profile), P = self.peer (sender).
Run from the repository root:
  python3 <this file> -v Replay.test_x
Mocked: gate decisions (receive.check), the person's yes (cli._person_or_refuse
returning None) and registry.me() for `held deliver`; adapters.to_codex (the
only transport) is not called because messages are sent with wake=False.
Everything else (handoff, ledger, migration, receive.take_inbox_claims,
receive._gate, cli._held_deliver) is the real code.
"""
import io
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

sys.path.insert(0, os.getcwd())
from tests.test_profile_migration import ProfileMigrationTest  # noqa: E402

BLOCK = ('block', 'out of scope (replay)')
OWNER_A = {'type': 'native', 'id': 'reader-a'}
OWNER_B = {'type': 'native', 'id': 'reader-b'}


class Replay(ProfileMigrationTest):
    # ---- helpers: one real call each ----
    def dm(self, body):
        from xsm import send
        r = send.send('ref:' + self.a['ref'], body, sender=self.peer, wake=False)
        return r.msg_id

    def hook_gate(self, me, mid, verdict):
        """receive._gate on the queue copy of the DM, with check() mocked."""
        from xsm import envelope, handoff, receive
        parsed = envelope.parse(handoff.status(me, mid)['message']['content'])
        with mock.patch.object(receive, 'check', return_value=verdict):
            return receive._gate({}, 'codex', me, parsed)

    def inbox(self, me, owner=OWNER_A, generation='gen-a', verdict=None, **kw):
        from xsm import receive
        if verdict is None:
            return receive.take_inbox_claims(me, owner=owner, generation=generation, **kw)
        with mock.patch.object(receive, 'check', return_value=verdict):
            return receive.take_inbox_claims(me, owner=owner, generation=generation, **kw)

    def held_deliver(self, me, name):
        from xsm import cli
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(cli.registry, 'me', return_value=me), \
             mock.patch.object(cli, '_person_or_refuse', return_value=None), \
             mock.patch.object(cli, '_verdict', 'yes', create=True), \
             redirect_stdout(out), redirect_stderr(err):
            code = cli._held_deliver(mock.Mock(id=name))
        return code, out.getvalue(), err.getvalue()

    def held_names(self):
        from xsm import paths
        folder = paths.path(paths.HELD)
        return sorted(n[:-5] for n in os.listdir(folder)) if os.path.isdir(folder) else []

    def snap(self, label, me, mid):
        from xsm import handoff, ledger
        h = handoff.status(me, mid)
        r = ledger.receipt_of(mid)
        print('  [%s] original=%s delivery_state=%s receipt=%s held-files=%d' % (
            label, h.get('status'), h.get('delivery_state'), r and r['decision'], len(self.held_names())))

    # ---- XsmHeldDeliver: YesIsFinal ----
    def test_held_deliver_then_inbox_holds_again(self):
        """hook holds -> person says yes -> held deliver -> A's inbox holds again."""
        mid = self.dm('SECRET-1')
        print('\n[yes-final/hold-again]')
        self.hook_gate(self.a, mid, BLOCK)                       # 1 A's hook holds DM1
        self.snap('after hook hold', self.a, mid)
        first = self.held_names()
        self.assertEqual(len(first), 1)
        code, out, err = self.held_deliver(self.a, first[0])     # 2 person says yes
        print('  held deliver exit', code, 'body shown:', 'SECRET-1' in out)
        self.assertEqual(code, 0)
        self.snap('after held deliver', self.a, mid)
        pack = self.inbox(self.a, verdict=BLOCK)                 # 3 A's inbox, gate still refuses
        print('  inbox said:', pack['messages'])
        self.snap('after inbox', self.a, mid)
        again = self.held_names()
        print('  held entries now:', again)
        # YesIsFinal breaks: a NEW held entry exists after the yes (the person is asked again)
        self.assertEqual(len(again), 1)
        self.assertNotEqual(again[0], first[0])

    def test_held_deliver_then_inbox_shows_again(self):
        """same, but the person linked the sessions meanwhile (GateOpens): shown twice."""
        mid = self.dm('SECRET-2')
        print('\n[yes-final/shown-twice]')
        self.hook_gate(self.a, mid, BLOCK)
        name = self.held_names()[0]
        code, out, _ = self.held_deliver(self.a, name)
        self.assertIn('SECRET-2', out)
        pack = self.inbox(self.a)                                # real check(): passes
        print('  inbox shows it again:', any('SECRET-2' in m for m in pack['messages']))
        self.assertTrue(any('SECRET-2' in m for m in pack['messages']))   # YesIsFinal breaks: shown again

    def test_held_deliver_then_transfer_then_b_shows_again(self):
        """across the move: held deliver at A, migrate, B's reader shows it again."""
        mid = self.dm('SECRET-3')
        print('\n[yes-final/after-move]')
        self.hook_gate(self.a, mid, BLOCK)
        code, out, _ = self.held_deliver(self.a, self.held_names()[0])
        self.assertIn('SECRET-3', out)
        self.migrate()
        pack = self.inbox(self.b, OWNER_B, 'gen-b')
        print('  B shows it again:', any('SECRET-3' in m for m in pack['messages']))
        self.assertTrue(any('SECRET-3' in m for m in pack['messages']))   # YesIsFinal breaks: shown again at B

    # ---- XsmTransfer: DeliveredMeansShown ----
    def test_delivered_receipt_written_then_fence_refuses_the_handoff(self):
        from xsm import handoff, ledger, migration, receive
        mid = self.dm('NEVER-SHOWN-AT-A')
        print('\n[delivered-means-shown]')
        real = ledger.receipt
        fired = []

        def receipt_then_migrate(msg_id, decision, *a, **k):
            real(msg_id, decision, *a, **k)
            if msg_id == mid and decision == 'delivered' and not fired:
                fired.append(1)
                self.migrate()                                    # fence..commit right after the receipt
        raised = None
        with mock.patch.object(ledger, 'receipt', side_effect=receipt_then_migrate):
            try:
                self.inbox(self.a)                                # 1 claim 2 fence 3 receipt 4 handoff refused
            except migration.MigrationError as exc:
                raised = exc
        print('  A reader raised:', type(raised).__name__ if raised else None, '-', str(raised)[:80] if raised else '')
        self.assertIsNotNone(raised)
        st = ledger.status(mid)
        print('  ledger status seen by the sender:', st.get('status'))
        self.snap('A', self.a, mid)
        self.snap('B', self.b, mid)
        # B has not read it yet, A's model never saw it, yet the ledger says delivered
        self.assertEqual(handoff.status(self.b, mid)['status'], 'pending')
        self.assertEqual(st.get('status'), 'delivered')           # DeliveredMeansShown breaks: nobody has seen it

    # ---- XsmTransfer: HeldFollowsOwner ----
    def test_in_flight_gate_hold_after_the_move_stays_bound_to_a(self):
        from xsm import handoff, ledger, migration, paths
        mid = self.dm('HELD-ACROSS-MOVE')
        print('\n[held-follows-owner]')
        fired = []

        def check_runs_migration(parsed, me, cfg=None):
            if not fired:
                fired.append(1)
                self.migrate()                                    # whole move happens while A's check() runs
            return BLOCK
        raised = None
        from xsm import receive
        with mock.patch.object(receive, 'check', side_effect=check_runs_migration):
            try:
                receive.take_inbox_claims(self.a, owner=OWNER_A, generation='gen-a')
            except migration.MigrationError as exc:
                raised = exc
        print('  A reader raised:', type(raised).__name__ if raised else None)
        self.assertIsNotNone(raised)
        names = self.held_names()
        entry = paths.read_json(paths.path(paths.HELD, names[0] + '.json'))
        print('  held entry bound to ref:', entry['receiver_ref'], '(A=%s, B=%s)' % (self.a['ref'], self.b['ref']))
        self.snap('B', self.b, mid)
        code, out, err = self.held_deliver(self.b, names[0])
        print('  B agent runs held deliver -> exit', code, err.strip()[:110])
        self.assertEqual(entry['receiver_ref'], self.a['ref'])    # HeldFollowsOwner breaks: bound to retired A
        self.assertEqual(code, 2)

    # ---- controls: rules that hold ----
    def test_control_old_claim_cannot_ack_or_release_and_target_acks_once(self):
        from xsm import handoff, migration, receive
        mid = self.dm('LIVE-CLAIM')
        print('\n[control: live claim across the move]')
        pack = self.inbox(self.a)
        self.assertEqual([c['id'] for c in pack['claims']], [mid])
        token = pack['claims'][0]['token']
        self.migrate()
        for what, call in (('ack', handoff.ack), ('release', handoff.release)):
            with self.assertRaises(ValueError) as ctx:
                call(self.a, token, OWNER_A, 'gen-a')
            print('  A %s refused: %s' % (what, str(ctx.exception)[:70]))
        with self.assertRaises(ValueError):
            receive.ack_inbox(self.a, [token], owner=OWNER_A, generation='gen-a')
        pack_b = self.inbox(self.b, OWNER_B, 'gen-b')
        print('  B shows it:', pack_b['messages'][0].splitlines()[0][:90])
        done = receive.ack_inbox(self.b, [pack_b['claims'][0]['token']], owner=OWNER_B, generation='gen-b')
        acked = [handoff.status(s, mid)['status'] for s in (self.a, self.b)]
        print('  statuses A,B:', acked, 'acked ids:', done['acked'])
        self.assertEqual(acked, ['pending', 'acknowledged'])      # A never acknowledged

    def test_control_ack_before_the_move_leaves_no_copy(self):
        from xsm import handoff, receive
        mid = self.dm('ACKED-EARLY')
        pack = self.inbox(self.a)
        receive.ack_inbox(self.a, [pack['claims'][0]['token']], owner=OWNER_A, generation='gen-a')
        self.migrate()
        print('\n[control: ack before move] B copy:', handoff.status(self.b, mid)['status'])
        self.assertEqual(handoff.status(self.b, mid)['status'], 'not-found')

    def test_control_hook_held_dm_stays_held_at_b_and_entry_follows(self):
        from xsm import handoff, paths
        mid = self.dm('HELD-BEFORE-MOVE')
        self.hook_gate(self.a, mid, BLOCK)
        self.migrate()
        print('\n[control: held then moved]')
        pack = self.inbox(self.b, OWNER_B, 'gen-b')
        self.snap('B', self.b, mid)
        entry = paths.read_json(paths.path(paths.HELD, self.held_names()[0] + '.json'))
        print('  B reader returned:', pack['messages'], '| entry bound to B:', entry['receiver_ref'] == self.b['ref'])
        self.assertEqual(pack['messages'], [])
        self.assertEqual(entry['receiver_ref'], self.b['ref'])
        code, out, _ = self.held_deliver(self.b, self.held_names()[0])
        self.assertIn('HELD-BEFORE-MOVE', out)

    # ---- (d) two DMs, batch limit and exception ----
    def test_control_two_dms_batch_limit_releases_the_rest(self):
        from xsm import handoff
        m1, m2 = self.dm('ONE'), self.dm('TWO')
        print('\n[control: two DMs, limit=1]')
        pack = self.inbox(self.a, limit=1)
        print('  returned:', len(pack['messages']), 'claims:', [c['id'] == m1 for c in pack['claims']], 'batch_limited:', pack['batch_limited'])
        s1, s2 = handoff.status(self.a, m1), handoff.status(self.a, m2)
        print('  m1', s1['status'], 'm2', s2['status'], 'claim2:', s2['claim'])
        self.assertEqual((s1['status'], s2['status'], s2['claim']), ('handoff-recorded', 'pending', None))

    def test_control_two_dms_max_bytes_releases_the_one_that_does_not_fit(self):
        from xsm import handoff
        m1, m2 = self.dm('ONE'), self.dm('T' * 5000)
        print('\n[control: two DMs, max_bytes]')
        pack = self.inbox(self.a, max_bytes=3000)
        s1, s2 = handoff.status(self.a, m1), handoff.status(self.a, m2)
        print('  returned:', len(pack['messages']), 'm1', s1['status'], 'm2', s2['status'], 'claim2:', s2['claim'])
        self.assertEqual((s1['status'], s2['status'], s2['claim']), ('handoff-recorded', 'pending', None))

    def test_control_two_dms_exception_in_second_releases_both(self):
        from xsm import handoff
        m1, m2 = self.dm('ONE'), self.dm('TWO')
        real = handoff.handoff
        calls = []

        def second_fails(*a, **k):
            calls.append(1)
            if len(calls) == 2:
                raise OSError('output failed (replay)')
            return real(*a, **k)
        print('\n[control: two DMs, exception on the second]')
        with mock.patch.object(handoff, 'handoff', side_effect=second_fails):
            with self.assertRaises(OSError):
                self.inbox(self.a)
        s1, s2 = handoff.status(self.a, m1), handoff.status(self.a, m2)
        print('  m1', s1['status'], 'm2', s2['status'])
        self.assertEqual((s1['status'], s2['status']), ('pending', 'pending'))

    def test_control_two_dms_both_move_and_nothing_is_lost(self):
        from xsm import handoff
        m1, m2 = self.dm('ONE'), self.dm('TWO')
        self.inbox(self.a, limit=1)                              # m1 handoff-recorded at A
        self.migrate()
        print('\n[control: two DMs across the move]')
        for m in (m1, m2):
            print('  ', m[:6], 'A:', handoff.status(self.a, m)['status'], 'B:', handoff.status(self.b, m)['status'])
        self.assertEqual([handoff.status(self.b, m)['status'] for m in (m1, m2)], ['pending', 'pending'])


if __name__ == '__main__':
    unittest.main()
