"""State-model fixes, held / migration slice (docs/plan/state-model-fixes/spec.md).

SM-F11  after `held deliver` the same message is not held again and not shown again.
SM-F12  a hold made around a move stays deliverable by the session that now owns it.
SM-F13  a `delivered` receipt means somebody was shown the message.

Reproduction source: deliverables/statechart-20261125/migration/replay_test.py. Only
external transport (adapters.to_codex is never reached: wake=False or mocked), the gate
decision (receive.check, where a test says so), the person's yes (cli._person_or_refuse)
and registry.me() for `held deliver` are mocked. Interleavings wrap the real function and
call it. Everything else is the real code.

RED tests carry @unittest.expectedFailure and `# RED until P<n> (SM-<ID>)`; remove the
decorator when the phase lands. test_control_* tests pass today and must keep passing.
"""
import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from tests.test_xsm import TempState

BLOCK = ('block', 'out of scope (state-model test)')
OWNER_A = {'type': 'native', 'id': 'reader-a'}
OWNER_B = {'type': 'native', 'id': 'reader-b'}


class _Helpers:
    """One real call each; `self.a` is the old session, `self.b` the new one, `self.peer` the sender."""

    def dm(self, body):
        from xsm import send
        r = send.send('ref:' + self.a['ref'], body, sender=self.peer, wake=False)
        self.assertEqual(r.status, 'stored', r.lines())
        return r.msg_id

    def hook_gate(self, me, mid, verdict):
        """receive._gate (the prompt hook's gate) on the queue copy of the DM, with check() mocked."""
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
        """`xsm held deliver <name>` as the agent of `me` runs it, the person having said yes."""
        from xsm import cli
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(cli.registry, 'me', return_value=me), \
             mock.patch.object(cli, '_person_or_refuse', return_value=None), \
             mock.patch.object(cli, '_verdict', 'yes', create=True), \
             mock.patch('xsm.workers.human_terminal', return_value=False), \
             redirect_stdout(out), redirect_stderr(err):
            code = cli._held_deliver(mock.Mock(id=name))
        return code, out.getvalue(), err.getvalue()

    def held_names(self):
        from xsm import paths
        folder = paths.path(paths.HELD)
        return sorted(n[:-5] for n in os.listdir(folder)) if os.path.isdir(folder) else []

    def hold_at_a(self, body):
        """A DM held by A's hook gate, then released by the person's yes. Returns the id."""
        mid = self.dm(body)
        self.hook_gate(self.a, mid, BLOCK)
        names = self.held_names()
        self.assertEqual(len(names), 1, names)
        code, out, err = self.held_deliver(self.a, names[0])
        self.assertEqual(code, 0, err)
        self.assertIn(body, out)
        self.assertEqual(self.held_names(), [])
        return mid


class _MigrationBase(_Helpers, TempState):
    """The profile-migration fixture of tests/test_profile_migration.py (same setUp and migrate())."""

    def setUp(self):
        super().setUp()
        from xsm import registry
        self.a = registry.upsert('codex', self.tmp + '/a', 'copied-id', os.getpid(), self.tmp, name='old')
        self.b = registry.upsert('codex', self.tmp + '/b', 'copied-id', os.getpid(), self.tmp, name='new')
        self.peer = registry.upsert('codex', self.tmp + '/peer', 'peer', os.getpid(), self.tmp, name='peer')

    def migrate(self, authorize=None, **kwargs):
        from xsm import migration
        plan = migration.prepare(self.b, 'ref:' + self.a['ref'])
        return migration.execute(plan, authorize=authorize or (lambda _: 'fixture user approval'), **kwargs)


class _HandoverBase(_Helpers, TempState):
    """P (sender) and A share the team `core`; each session has its own folder, so the team is
    the only scope between them. A hands its place over to B (tests/test_handover.py fixture)."""

    def setUp(self):
        super().setUp()
        from xsm import registry, teams
        home = self.tmp + '/codex'
        os.makedirs(home)
        for sid, name in (('p', 'peer'), ('a', 'olda'), ('b', 'newb')):
            os.makedirs(self.tmp + '/cwd-' + sid)
            registry.upsert('codex', home, sid, os.getpid(), self.tmp + '/cwd-' + sid, name=name)
        self.peer, self.a, self.b = (registry.by_session('codex', s) for s in ('p', 'a', 'b'))
        teams.create(self.peer, 'core')
        teams.add(self.peer, 'core', self.a, 'x')
        patcher = mock.patch('xsm.workers.human_terminal', return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def hand_over(self):
        from xsm import handover
        return handover.hand_over(self.a, self.b, 'summary: keep going', 'x')


# ---------------------------------------------------------------------------------------------
# SM-F11: a message the person said yes to is not held again and not shown again
# ---------------------------------------------------------------------------------------------

class HeldDeliverIsFinal(_MigrationBase):
    # Fixed in P4 (SM-F11). Before the fix: `held deliver` rewrites only the receipt (cli.py:1551) and leaves
    # the original pending, so A's inbox, with the gate still closed, holds it again under a new
    # name and asks the person a second time.
    def test_SM_F11_a_inbox_with_scope_closed_does_not_hold_again(self):
        mid = self.hold_at_a('SECRET-1')
        pack = self.inbox(self.a, verdict=BLOCK)
        self.assertEqual(self.held_names(), [], 'the person said yes; a new held entry asks again')
        self.assertEqual(pack['messages'], [], pack)
        self.assertNotIn(mid, json.dumps(pack))

    # Fixed in P4 (SM-F11). Before the fix: same cause; once the person links the folders the gate passes and
    # the still-pending original is shown by `xsm inbox` after `held deliver` already showed it.
    def test_SM_F11_a_inbox_after_link_does_not_show_again(self):
        self.hold_at_a('SECRET-2')
        pack = self.inbox(self.a)                                 # real check(): passes
        self.assertEqual(pack['messages'], [], 'shown a second time')
        self.assertEqual(pack['claims'], [])

    # Fixed in P4 (SM-F11). Before the fix: the migration copies the still-pending original to B, whose inbox
    # shows it a second time.
    def test_SM_F11_b_migration_then_b_inbox_does_not_show_again(self):
        self.hold_at_a('SECRET-3')
        self.migrate()
        pack = self.inbox(self.b, OWNER_B, 'gen-b')
        self.assertEqual(pack['messages'], [], 'shown a second time at B')
        self.assertEqual(pack['claims'], [])

    # Fixed in P4 (SM-F11). Before the fix: as above with B's gate closed: B holds it again.
    def test_SM_F11_b_migration_then_b_inbox_with_scope_closed_does_not_hold_again(self):
        self.hold_at_a('SECRET-4')
        self.migrate()
        pack = self.inbox(self.b, OWNER_B, 'gen-b', verdict=BLOCK)
        self.assertEqual(self.held_names(), [], 'a new held entry at B asks the person again')
        self.assertEqual(pack['messages'], [], pack)


class HeldDeliverIsFinalAcrossHandover(_HandoverBase):
    # SM-F11 (fixed in P4): held deliver acknowledges the original, so the handover neither moves
    # it nor writes it into the letter.
    def test_SM_F11_c_handover_then_b_inbox_and_letter_do_not_show_again(self):
        from xsm import receive
        self.hold_at_a('SECRET-5')
        rec = self.hand_over()
        pack = self.inbox(self.b, OWNER_B, 'gen-b')
        out = receive._with_bounces('codex', self.b, None)
        letter = rec['letter'] + json.dumps(out, ensure_ascii=False)
        self.assertNotIn('SECRET-5', json.dumps(pack), 'B inbox shows it again')
        self.assertNotIn('SECRET-5', letter, "B's handover letter shows it again")
        self.assertEqual(self.held_names(), [], 'held again for B')


# ---------------------------------------------------------------------------------------------
# SM-F12: holds made around a move stay deliverable
# ---------------------------------------------------------------------------------------------

class HeldFollowsOwner(_MigrationBase):
    def test_SM_F12_a_gate_hold_right_after_migration_is_deliverable_by_b(self):
        from xsm import migration, receive
        self.dm('HELD-ACROSS-MOVE')
        fired = []

        def check_runs_migration(parsed, me, cfg=None):
            if not fired:
                fired.append(1)
                self.migrate()                                    # the whole move lands inside A's check()
            return BLOCK
        with mock.patch.object(receive, 'check', side_effect=check_runs_migration):
            try:
                receive.take_inbox_claims(self.a, owner=OWNER_A, generation='gen-a')
            except migration.MigrationError:
                pass                                              # A's reader may or may not stop here
        names = self.held_names()
        self.assertEqual(len(names), 1, 'the gate hold was not kept at all: %s' % names)
        code, out, err = self.held_deliver(self.b, names[0])
        self.assertEqual(code, 0, 'B cannot deliver the hold: %s' % err.strip())
        self.assertIn('HELD-ACROSS-MOVE', out)


class NativeCopyAfterHandover(_HandoverBase):
    # Q1 (spec section 10), measured on 2a858d3+: it DOES create a new held entry. After the
    # handover A is out of team `core`, so A's real gate says "out of scope" to the queued copy
    # of the DM that moved to B, and receive.hold keeps it as a new held entry bound to A: a
    # message B already owns would be asked about again, at a session that has handed over.
    # Fixed in P2 (SM-F12)
    def test_SM_F12_native_copy_after_handover(self):
        from xsm import adapters, handoff, receive, send
        with mock.patch.object(adapters, 'to_codex', return_value='Queued message q for thread a.') as transport:
            sent = send.send('ref:' + self.a['ref'], 'NATIVE-COPY', sender=self.peer)
        self.assertIn(sent.status, ('sent-unconfirmed', 'stored', 'delivered'), sent.lines())
        wire = transport.call_args.args[2]                        # the copy in the runtime's own queue
        rec = self.hand_over()
        self.assertEqual(rec['messages'], [sent.msg_id])          # it moved with the handover
        self.assertEqual(self.held_names(), [])
        with mock.patch.object(receive, 'register', return_value=self.a):
            receive.handle({'hook_event_name': 'UserPromptSubmit', 'session_id': 'a', 'turn_id': 'native',
                            'cwd': self.tmp + '/cwd-a', 'prompt': wire})
        self.assertEqual(self.held_names(), [], 'A holds a copy of a DM that already moved to B')
        self.assertEqual(handoff.status(self.a, sent.msg_id)['status'], 'acknowledged')   # still closed as moved


# ---------------------------------------------------------------------------------------------
# SM-F13: `delivered` means shown
# ---------------------------------------------------------------------------------------------

class DeliveredMeansShown(_MigrationBase):
    # SM-F13 (fixed in P4): the `delivered` receipt is written only after handoff.handoff stood.
    # The first version of this test fenced right after ledger.receipt; with the fixed order that
    # point lies after the handoff, so it no longer describes the defect and was replaced by this one.
    def test_SM_F13_fence_before_handoff_leaves_no_delivered_receipt(self):
        """Same assertions, fence injected where the handoff is refused: right before handoff.handoff."""
        from xsm import handoff, ledger, migration
        mid = self.dm('NEVER-SHOWN-AT-A-2')
        real = handoff.handoff
        fired = []

        def migrate_then_handoff(*a, **k):
            if not fired:
                fired.append(1)
                self.migrate()                                    # fence..commit just before the handoff
            return real(*a, **k)
        with mock.patch.object(handoff, 'handoff', side_effect=migrate_then_handoff):
            try:
                self.inbox(self.a)
            except migration.MigrationError:
                pass
        self.assertEqual(handoff.status(self.b, mid)['status'], 'pending')   # B has not been shown it either
        self.assertNotEqual(ledger.status(mid).get('status'), 'delivered')


# ---------------------------------------------------------------------------------------------
# Controls: pass today, must keep passing
# ---------------------------------------------------------------------------------------------

class Controls(_MigrationBase):
    def test_control_old_claim_cannot_ack_or_release_and_target_acks_once(self):
        from xsm import handoff, receive
        mid = self.dm('LIVE-CLAIM')
        pack = self.inbox(self.a)
        self.assertEqual([c['id'] for c in pack['claims']], [mid])
        token = pack['claims'][0]['token']
        self.migrate()
        for call in (handoff.ack, handoff.release):
            with self.assertRaises(ValueError):
                call(self.a, token, OWNER_A, 'gen-a')
        with self.assertRaises(ValueError):
            receive.ack_inbox(self.a, [token], owner=OWNER_A, generation='gen-a')
        pack_b = self.inbox(self.b, OWNER_B, 'gen-b')
        self.assertIn('LIVE-CLAIM', pack_b['messages'][0])
        receive.ack_inbox(self.b, [pack_b['claims'][0]['token']], owner=OWNER_B, generation='gen-b')
        self.assertEqual([handoff.status(s, mid)['status'] for s in (self.a, self.b)],
                         ['pending', 'acknowledged'])             # A never acknowledged

    def test_control_ack_before_the_move_leaves_no_copy(self):
        from xsm import handoff, receive
        mid = self.dm('ACKED-EARLY')
        pack = self.inbox(self.a)
        receive.ack_inbox(self.a, [pack['claims'][0]['token']], owner=OWNER_A, generation='gen-a')
        self.migrate()
        self.assertEqual(handoff.status(self.b, mid)['status'], 'not-found')

    def test_control_hook_held_dm_stays_held_at_b_and_entry_follows(self):
        from xsm import paths
        self.dm('HELD-BEFORE-MOVE')
        mid = self.dm('HELD-BEFORE-MOVE-2')
        self.hook_gate(self.a, mid, BLOCK)
        self.migrate()
        pack = self.inbox(self.b, OWNER_B, 'gen-b')
        names = self.held_names()
        self.assertEqual(len(names), 1)
        entry = paths.read_json(paths.path(paths.HELD, names[0] + '.json'))
        self.assertEqual(entry['receiver_ref'], self.b['ref'])
        self.assertNotIn('HELD-BEFORE-MOVE-2', json.dumps(pack))  # the held one is not shown without a yes
        code, out, _ = self.held_deliver(self.b, names[0])
        self.assertEqual(code, 0)
        self.assertIn('HELD-BEFORE-MOVE-2', out)

    def test_control_two_dms_batch_limit_releases_the_rest(self):
        from xsm import handoff
        m1, m2 = self.dm('ONE'), self.dm('TWO')
        pack = self.inbox(self.a, limit=1)
        self.assertTrue(pack['batch_limited'])
        s1, s2 = handoff.status(self.a, m1), handoff.status(self.a, m2)
        self.assertEqual((s1['status'], s2['status'], s2['claim']), ('handoff-recorded', 'pending', None))

    def test_control_two_dms_max_bytes_releases_the_one_that_does_not_fit(self):
        from xsm import handoff
        m1, m2 = self.dm('ONE'), self.dm('T' * 5000)
        self.inbox(self.a, max_bytes=3000)
        s1, s2 = handoff.status(self.a, m1), handoff.status(self.a, m2)
        self.assertEqual((s1['status'], s2['status'], s2['claim']), ('handoff-recorded', 'pending', None))

    def test_control_two_dms_exception_in_second_releases_both(self):
        from xsm import handoff
        m1, m2 = self.dm('ONE'), self.dm('TWO')
        real = handoff.handoff
        calls = []

        def second_fails(*a, **k):
            calls.append(1)
            if len(calls) == 2:
                raise OSError('output failed (state-model test)')
            return real(*a, **k)
        with mock.patch.object(handoff, 'handoff', side_effect=second_fails):
            with self.assertRaises(OSError):
                self.inbox(self.a)
        s1, s2 = handoff.status(self.a, m1), handoff.status(self.a, m2)
        self.assertEqual((s1['status'], s2['status']), ('pending', 'pending'))

    def test_control_two_dms_both_move_and_nothing_is_lost(self):
        from xsm import handoff
        m1, m2 = self.dm('ONE'), self.dm('TWO')
        self.inbox(self.a, limit=1)                               # m1 handoff-recorded at A
        self.migrate()
        self.assertEqual([handoff.status(self.b, m)['status'] for m in (m1, m2)], ['pending', 'pending'])


if __name__ == '__main__':
    unittest.main()
