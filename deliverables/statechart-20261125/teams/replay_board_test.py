"""Replay of the XsmHandoverBoard.tla paths against xsm's real code.

A = self.lead ('lead'), B = self.new ('next'), M = self.bee ('bee').
Nothing is mocked except transport (network is simply not running: board_sync and
team_sync publish see no remote members). The racing writes are made by the real
board.set_item of M, injected at the point of the path where TLC puts them, by a
pass-through wrapper around the real board function A is about to call.

Run from the repository root:
  python3 <this file> -v Replay.test_x
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.getcwd())
from tests.test_handover import HandoverTest  # noqa: E402


def trace_board(calls):
    """Pass-through wrappers that only record which real board function A calls."""
    from xsm import board
    orig = {n: getattr(board, n) for n in ('show', 'current', 'set_item')}

    def wrap(name):
        def inner(*a, **k):
            who = a[0].get('name') if a and isinstance(a[0], dict) else '-'
            item = a[2] if name == 'set_item' else ''
            calls.append('%s(%s%s)' % (name, who, (', ' + item) if item else ''))
            return orig[name](*a, **k)
        return inner
    return orig, wrap


class Replay(HandoverTest):
    def _heads(self, item):
        from xsm import board
        return [h['body'].split('\n')[0] for h in board.current('core').get(item, [])]

    def test_a_two_version_item_is_skipped_and_nothing_says_so(self):
        """Path EveryOwnerItemClosed: read board -> list items [one in conflict] ->
        leave it alone -> write handover/A."""
        from xsm import board, handover
        board.set_item(self.lead, 'core', 'owner/lead', 'plan v1')              # node 1 (A)
        board.set_item(self.bee, 'core', 'owner/lead', 'bee notes')             # M never read it: second head
        print('\n[skip] before:', self._heads('owner/lead'))
        calls = []
        orig, wrap = trace_board(calls)
        with mock.patch.object(board, 'show', wrap('show')), mock.patch.object(board, 'current', wrap('current')), \
                mock.patch.object(board, 'set_item', wrap('set_item')):
            rec = self._hand_over()
        print('[skip] real board calls made by hand_over:', calls)
        print('[skip] items moved reported to B:', rec['items'])
        print('[skip] owner/lead heads after:', self._heads('owner/lead'))
        print('[skip] owner/next present:', 'owner/next' in board.current('core'))
        note = board.current('core')['handover/lead'][0]['body']
        print('[skip] handover/lead item:', note)
        letter = rec['letter']
        print('[skip] letter mentions owner/lead:', 'owner/lead' in letter)
        self.assertEqual(len(board.current('core')['owner/lead']), 2)          # rule EveryOwnerItemClosed breaks
        self.assertNotIn('owner/next', board.current('core'))
        self.assertNotIn('owner/lead', note)
        self.assertNotIn('owner/lead', letter)

    def test_a_write_after_the_copy_leaves_a_head_nobody_carried(self):
        """Path MovedItemIsClosed / NoContentLeftBehind (TLC's 6-step path): read board ->
        list items -> copy owner/A into owner/B -> a member writes owner/A -> A overwrites
        owner/A with 'handed over' -> A writes handover/A."""
        from xsm import board
        board.set_item(self.lead, 'core', 'owner/lead', 'plan v1')
        real = board.set_item
        done = []

        def racing(me, team, item, text, *a, **k):
            if me['name'] == 'lead' and item == 'owner/lead' and not done:
                done.append(1)
                real(self.bee, team, 'owner/lead', 'bee LATE EDIT')            # M's real write
            return real(me, team, item, text, *a, **k)
        with mock.patch.object(board, 'set_item', side_effect=racing):
            rec = self._hand_over()
        old = board.current('core')['owner/lead']
        new = board.current('core')['owner/next']
        print('\n[late] reported to B:', rec['items'])
        print('[late] owner/lead heads:', [h['body'].split('\n')[0] for h in old], 'count', len(old))
        print('[late] owner/next heads:', [h['body'].split('\n')[0] for h in new])
        self.assertEqual(len(old), 2)                                           # note beside a content head
        self.assertTrue(any('bee LATE EDIT' in h['body'] for h in old))
        self.assertFalse(any('bee LATE EDIT' in h['body'] for h in new))        # never carried
        self.assertEqual(rec['items']['core'], ['owner/lead'])                  # and B is told it was moved

    def test_a_write_between_reading_and_listing_is_carried_but_the_old_item_is_left_in_conflict(self):
        """Same rule, earlier window: read board -> a member writes -> list items -> ..."""
        from xsm import board
        board.set_item(self.lead, 'core', 'owner/lead', 'plan v1')
        board.show(self.bee, 'core')                                            # M has read node 1
        real_show, real_current = board.show, board.current
        state = {'shown': False, 'done': False}

        def show(*a, **k):
            out = real_show(*a, **k)
            if a[0]['name'] == 'lead':
                state['shown'] = True
            return out

        def current(*a, **k):
            if state['shown'] and not state['done']:
                state['done'] = True
                board.set_item(self.bee, 'core', 'owner/lead', 'bee MID EDIT')  # M's real write
            return real_current(*a, **k)
        with mock.patch.object(board, 'show', side_effect=show), mock.patch.object(board, 'current', side_effect=current):
            rec = self._hand_over()
        old = board.current('core')['owner/lead']
        new = board.current('core')['owner/next']
        print('\n[mid] owner/lead heads:', [h['body'].split('\n')[0] for h in old], 'count', len(old))
        print('[mid] owner/next heads:', [h['body'].split('\n')[0] for h in new])
        self.assertEqual(len(old), 2)
        self.assertTrue(any('bee MID EDIT' in h['body'] for h in new))          # carried, but...

    def test_control_when_nobody_writes_the_old_item_ends_with_the_note_only(self):
        from xsm import board
        board.set_item(self.lead, 'core', 'owner/lead', 'plan v1')
        self._hand_over()
        self.assertEqual(len(board.current('core')['owner/lead']), 1)

    def test_observation_an_existing_owner_item_of_the_successor_is_displaced(self):
        """Not one of the model's rules: B is already a member and already has owner/next."""
        from xsm import board, teams
        teams.add(self.lead, 'core', self.new, 'x')
        board.set_item(self.new, 'core', 'owner/next', "B's own work")
        board.set_item(self.lead, 'core', 'owner/lead', "A's plan")
        self._hand_over()
        heads = board.current('core')['owner/next']
        print('\n[collision] owner/next heads:', [h['body'].replace(chr(10), ' | ') for h in heads])
        self.assertEqual(len(heads), 1)
        self.assertNotIn("B's own work", heads[0]['body'])

    def test_observation_a_moved_item_loses_its_decision_mark(self):
        """Not one of the model's rules: owner/lead was settled by a person's decision record."""
        from xsm import board
        rec = board.record_decision(self.lead, 'core', 'who owns docs?', 'lead', via='terminal', item='owner/lead')
        before = board.render_text('core')
        self.assertIn('decided', before)
        self._hand_over()
        after = board.render_text('core')
        new_section = after.split('## owner/next')[1].split('## ')[0]
        print('\n[decision] owner/next section:', new_section.strip().replace(chr(10), ' | '))
        print('[decision] decision records on core:', [d['id'] for d in board.decisions('core')], 'item', [d['item'] for d in board.decisions('core')])
        self.assertNotIn('decided', new_section)


if __name__ == '__main__':
    unittest.main()
