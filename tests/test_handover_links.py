"""Handover P3 (docs/plan/state-model-fixes/spec.md): the connections a handover copies
(D1), a target that handed over itself, and a transfer that must not overlap a handover.

The sessions are the real registry records of tests.test_handover.HandoverTest; the
scope checks (config.scope_for), the reach and pair-team writers, the service that
shows the plan to the approval and the handover itself are the real code.
"""
import json
import os
import shutil
import tempfile
import threading
import unittest

from tests import test_handover


class HandoverLinksTest(test_handover.HandoverTest):
    def _sess(self, sid, cwd=None):
        from xsm import registry
        if cwd is None:
            cwd = tempfile.mkdtemp(prefix='xsm-links-')
            self.addCleanup(shutil.rmtree, cwd, True)
        os.makedirs(cwd, exist_ok=True)
        registry.upsert('codex', self.home, sid, os.getpid(), cwd, name=sid)
        return registry.by_session('codex', sid)

    def _real(self, path):
        return os.path.realpath(path)

    # ---- the plan --------------------------------------------------------------------
    def test_the_plan_lists_each_kind_and_writes_nothing(self):
        from xsm import config, handover, handover_links, workers
        far = self._sess('far')
        peer, linked, reached = self._sess('peer'), self._sess('linked'), self._sess('reached')
        config.add_link(linked['cwd'], self.lead['cwd'], 't')
        config.add_reach(self.lead['ref'], reached['cwd'], 't', self.lead)
        workers.save({'name': 'h', 'ref': peer['ref'], 'parent_ref': self.lead['ref']})
        before = (config.reaches(), config.links())
        plan = handover.plan_links(self.lead, far)
        got = {(row['kind'], row['what']) for row in plan['links']}
        self.assertEqual(got, {('reach', self._real(reached['cwd'])), ('folder', self._real(self.lead['cwd'])),
                               ('link', self._real(linked['cwd'])), ('worker', peer['ref'])})
        self.assertEqual((config.reaches(), config.links()), before)         # nothing written
        json.dumps(plan)                                                      # it is stored in the record
        self.assertEqual(len(handover_links.describe(plan)), 4)

    def test_a_successor_inside_the_folder_gets_no_folder_reach(self):
        from xsm import handover
        plan = handover.plan_links(self.lead, self.new)       # lead and next share the folder
        self.assertEqual(plan['links'], [])

    def test_a_connection_the_successor_already_has_is_not_planned(self):
        from xsm import config, handover
        far, reached = self._sess('far'), self._sess('reached')
        config.add_reach(self.lead['ref'], reached['cwd'], 't', self.lead)
        config.add_reach(far['ref'], reached['cwd'], 't', far)
        kinds = {(r['kind'], r['what']) for r in handover.plan_links(self.lead, far)['links']}
        self.assertNotIn(('reach', self._real(reached['cwd'])), kinds)

    # ---- the copy --------------------------------------------------------------------
    def test_the_worker_stays_As_and_joins_B_in_a_pair_team(self):
        from xsm import config, teams, workers
        far, peer = self._sess('far'), self._sess('peer')
        workers.save({'name': 'h', 'ref': peer['ref'], 'parent_ref': self.lead['ref']})
        rec = self._call_to(far)
        self.assertEqual(workers.load('h')['parent_ref'], self.lead['ref'])      # the parent is not changed
        rows = [r for r in rec['links'] if r['kind'] == 'worker']
        self.assertEqual([(r['what'], r['ok']) for r in rows], [(peer['ref'], True)])
        self.assertTrue(rows[0]['team'].startswith('pair-'))
        self.assertTrue(teams.is_member(teams.require(rows[0]['team']), far))
        self.assertTrue(teams.is_member(teams.require(rows[0]['team']), peer))
        self.assertTrue(config.scope_for(peer, far)[0].startswith('team:pair-'))
        self.assertIsNotNone(config.scope_for(peer, self.lead)[0])                # A keeps its own

    def test_a_parent_of_A_joins_B_too(self):
        from xsm import config, workers
        far, boss = self._sess('far'), self._sess('boss')
        workers.save({'name': 'h', 'ref': self.lead['ref'], 'parent_ref': boss['ref']})
        rec = self._call_to(far)
        self.assertEqual([(r['kind'], r['what'], r['ok']) for r in rec['links'] if r['kind'] != 'folder'],
                         [('parent', boss['ref'], True)])
        self.assertIsNotNone(config.scope_for(boss, far)[0])

    def test_a_reach_to_a_folder_is_given_to_B_bound_to_its_run(self):
        from xsm import config
        far, reached = self._sess('far'), self._sess('reached')
        config.add_reach(self.lead['ref'], reached['cwd'], 't', self.lead)
        self._call_to(far)
        mine = [r for r in config.reaches() if r['ref'] == far['ref'] and r['root'] == self._real(reached['cwd'])]
        self.assertEqual([(r['session_id'], r['pid'], r['lstart']) for r in mine],
                         [('far', far['pid'], far['lstart'])])
        self.assertTrue(config.reach_holds(mine[0], far))
        self.assertIsNotNone(config.scope_for(reached, far)[0])

    def test_B_gets_no_more_than_A_had(self):
        from xsm import config
        far, reached, stranger = self._sess('far'), self._sess('reached'), self._sess('stranger')
        config.add_reach(self.lead['ref'], reached['cwd'], 't', self.lead)
        self._call_to(far)
        self.assertIsNone(config.scope_for(stranger, self.lead)[0])
        self.assertIsNone(config.scope_for(stranger, far)[0])
        self.assertEqual(sorted(r['root'] for r in config.reaches() if r['ref'] == far['ref']),
                         sorted([self._real(reached['cwd']), self._real(self.lead['cwd'])]))   # A's reach and A's folder, no more

    def test_a_copy_that_fails_is_listed_the_rest_go_on_and_the_record_keeps_them(self):
        from xsm import config, handover, workers
        far, reached, peer = self._sess('far'), self._sess('reached'), self._sess('peer')
        gone = tempfile.mkdtemp(prefix='xsm-links-gone-')
        config.add_reach(self.lead['ref'], gone, 't', self.lead)
        shutil.rmtree(gone)
        config.add_reach(self.lead['ref'], reached['cwd'], 't', self.lead)
        workers.save({'name': 'h', 'ref': peer['ref'], 'parent_ref': self.lead['ref']})
        rec = self._call_to(far)
        bad = [r for r in rec['links'] if not r['ok']]
        self.assertEqual([os.path.basename(r['what']) for r in bad], [os.path.basename(gone)])
        self.assertTrue(bad[0]['why'])
        self.assertGreaterEqual(len([r for r in rec['links'] if r['ok']]), 3)
        self.assertEqual(handover.load(self.lead)['links'], rec['links'])
        self.assertIn('Not copied', handover.summary_line(rec))
        self.assertIn('not copied: reach', handover.notice(far))

    def test_the_letter_lists_the_copies(self):
        from xsm import config, handover
        far, reached = self._sess('far'), self._sess('reached')
        config.add_reach(self.lead['ref'], reached['cwd'], 't', self.lead)
        self._call_to(far)
        letter = handover.notice(far)
        self.assertIn('copied: reach ' + self._real(reached['cwd']), letter)

    def test_the_approved_plan_is_what_is_applied_even_when_the_world_changed(self):
        from xsm import config, handover
        far, reached, later = self._sess('far'), self._sess('reached'), self._sess('later')
        config.add_reach(self.lead['ref'], reached['cwd'], 't', self.lead)
        plan = handover.plan_links(self.lead, far)
        config.add_reach(self.lead['ref'], later['cwd'], 't', self.lead)       # after the approval
        rec = handover.hand_over(self.lead, far, 's', 'x', plan)
        self.assertNotIn(self._real(later['cwd']), json.dumps(rec['links']))
        self.assertIsNone(config.scope_for(later, far)[0])

    def test_a_plan_made_for_another_successor_is_made_again(self):
        from xsm import config, handover
        far, other, reached = self._sess('far'), self._sess('other'), self._sess('reached')
        config.add_reach(self.lead['ref'], reached['cwd'], 't', self.lead)
        plan = handover.plan_links(self.lead, other)
        handover.hand_over(self.lead, far, 's', 'x', plan)
        self.assertIsNotNone(config.scope_for(reached, far)[0])

    def _call_to(self, target):
        from xsm import handover
        return handover.hand_over(self.lead, target, 'goal: x', 'x')

    # ---- the approval shows the plan ---------------------------------------------------
    def test_the_service_shows_the_plan_to_the_approval_and_applies_it(self):
        from xsm import config, handover_service
        far, reached = self._sess('far'), self._sess('reached')
        config.add_reach(self.lead['ref'], reached['cwd'], 't', self.lead)
        seen = []

        def approve(target, plan=None):
            seen.append((target['session_id'], plan))
            return 'the person said yes'
        result = handover_service.execute(self.lead, {'target': 'ref:' + far['ref'], 'summary': 's'}, authorize=approve)
        self.assertEqual(seen[0][0], 'far')
        self.assertIn(('reach', self._real(reached['cwd'])), {(r['kind'], r['what']) for r in seen[0][1]['links']})
        self.assertEqual([r['what'] for r in result['record']['links'] if r['kind'] == 'reach'],
                         [self._real(reached['cwd'])])

    def test_an_approval_that_takes_only_the_target_still_works(self):
        from xsm import handover_service
        far = self._sess('far')
        result = handover_service.execute(self.lead, {'target': 'ref:' + far['ref'], 'summary': 's'},
                                          authorize=lambda target: 'yes')
        self.assertEqual(result['record']['to']['session_id'], 'far')

    def test_the_form_text_lists_the_connections(self):
        from xsm import config, handover, handover_links
        far, reached = self._sess('far'), self._sess('reached')
        config.add_reach(self.lead['ref'], reached['cwd'], 't', self.lead)
        text = '\n'.join(handover_links.describe(handover.plan_links(self.lead, far)))
        self.assertIn(self._real(reached['cwd']), text)

    # ---- a target that handed over itself --------------------------------------------------
    def test_a_target_that_handed_over_gets_the_end_of_its_chain_and_the_result_says_so(self):
        from xsm import handover
        handover.hand_over(self.new, self.out, 's', 'x')
        rec = handover.hand_over(self.bee, self.new, 's', 'x')
        self.assertEqual(rec['to']['session_id'], 'out')
        self.assertTrue(any('handed its place over' in n for n in rec['notes']), rec['notes'])
        self.assertIn('handed over to out', handover.summary_line(rec))

    def test_a_target_whose_handover_is_still_moving_is_followed_too(self):
        from xsm import handover
        handover._begin(self.new, self.out, 's', 'x')                   # next -> out began and did not finish
        rec = handover.hand_over(self.bee, self.new, 's', 'x')
        self.assertEqual(rec['to']['session_id'], 'out')

    def test_the_service_asks_about_the_end_of_the_chain(self):
        from xsm import handover, handover_service
        handover.hand_over(self.new, self.out, 's', 'x')
        seen = []

        def approve(target, plan=None):
            seen.append((target['session_id'], (plan or {}).get('redirected_from')))
            return 'yes'
        result = handover_service.execute(self.bee, {'target': 'ref:' + self.new['ref'], 'summary': 's'}, authorize=approve)
        self.assertEqual(seen[0][0], 'out')
        self.assertIn('handed its place over', seen[0][1])
        self.assertEqual(result['record']['to']['session_id'], 'out')

    def test_double_handover_and_a_loop_are_still_refused_with_the_next_action(self):
        from xsm import handover
        handover.hand_over(self.lead, self.new, 's', 'x')
        with self.assertRaises(handover.HandoverError) as double:
            handover.hand_over(self.lead, self.out, 's', 'x')
        self.assertIn('xsm handover', str(double.exception))
        with self.assertRaises(handover.HandoverError) as loop:
            handover.hand_over(self.new, self.lead, 's', 'x')
        self.assertIn('loop', str(loop.exception))
        self.assertIn('xsm handover', str(loop.exception))

    def test_a_chain_end_that_is_not_running_is_refused_with_a_next_action(self):
        from xsm import handover, registry
        handover.hand_over(self.new, self.out, 's', 'x')
        registry.mark_ended('codex', 'out', 'worker-stopped', home=self.home)
        with self.assertRaises(handover.HandoverError) as refused:
            handover.hand_over(self.bee, self.new, 's', 'x')
        self.assertIn('not running', str(refused.exception))
        self.assertIsNone(handover.load(self.bee))

    # ---- question groups -----------------------------------------------------------------------
    def test_every_child_of_a_moved_group_moves_with_its_origin_recorded(self):
        from xsm import paths, question_groups, questions
        for ident, target in (('g1-0', self.bee), ('g1-1', self.out)):
            self._question(ident, self.lead, target)
        paths.write_json(paths.path(questions.DIRECTORY, 'g1-0.json'),
                         dict(paths.read_json(questions._filename('g1-0')),
                              replies=[{'id': 'r', 'outcome': 'succeeded', 'body': 'x'}]))
        paths.write_json(paths.path(question_groups.DIRECTORY, 'g1.json'),
                         {'id': 'g1', 'sender': questions._native(self.lead), 'created_at': 1.0,
                          'recipients': [{'spec': 'a', 'label': 'a', 'id': 'g1-0'},
                                         {'spec': 'b', 'label': 'b', 'id': 'g1-1'}], 'notes': []})
        self._question('stand-alone', self.lead, self.bee)
        paths.write_json(questions._filename('stand-alone'),
                         dict(paths.read_json(questions._filename('stand-alone')),
                              replies=[{'id': 'r2', 'outcome': 'succeeded', 'body': 'x'}]))
        self._hand_over()
        for child in ('g1-0', 'g1-1'):
            record = paths.read_json(questions._filename(child))
            self.assertEqual(record['sender']['session_id'], 'next', child)
            self.assertEqual(record['handed_over_from']['session_id'], 'lead', child)
        self.assertEqual(paths.read_json(questions._filename('stand-alone'))['sender']['session_id'], 'lead')

    # ---- a transfer does not overlap a handover -----------------------------------------------
    def _copies(self):
        from xsm import registry
        a = registry.upsert('codex', self.tmp + '/a', 'copied-id', os.getpid(), self.tmp, name='old')
        b = registry.upsert('codex', self.tmp + '/b', 'copied-id', os.getpid(), self.tmp, name='new')
        return a, b

    def test_a_transfer_is_refused_while_a_handover_of_the_source_is_unfinished(self):
        from xsm import handover, migration
        a, b = self._copies()
        handover._begin(a, self.out, 's', 'x')                        # moving: it did not finish
        with self.assertRaises(migration.MigrationError) as refused:
            migration.prepare(b, 'ref:' + a['ref'])
        self.assertIn('finish it first', str(refused.exception))

    def test_a_handover_that_begins_after_the_plan_stops_the_transfer(self):
        from xsm import handover, migration
        a, b = self._copies()
        plan = migration.prepare(b, 'ref:' + a['ref'])
        handover._begin(a, self.out, 's', 'x')
        with self.assertRaises(migration.MigrationError) as refused:
            migration.execute(plan, authorize=lambda _: 'yes')
        self.assertIn('handover', str(refused.exception))
        self.assertIsNone(migration.retirement(a))                    # nothing was fenced

    def test_a_transfer_waits_for_a_running_handover_and_then_asks_to_run_again(self):
        from unittest import mock
        from xsm import handover, migration
        a, b = self._copies()
        plan = migration.prepare(b, 'ref:' + a['ref'])
        held, release = threading.Event(), threading.Event()

        def holder():
            with handover._handover_lock():
                held.set()
                release.wait(10)
        thread = threading.Thread(target=holder, daemon=True)
        thread.start()
        self.assertTrue(held.wait(5))
        try:
            with mock.patch.object(migration, 'HANDOVER_WAIT', 0.3), self.assertRaises(migration.MigrationError) as refused:
                migration.execute(plan, authorize=lambda _: 'yes')
            self.assertIn('again', str(refused.exception))
            self.assertIsNone(migration.retirement(a))
        finally:
            release.set()
            thread.join(5)
        self.assertEqual(migration.execute(plan, authorize=lambda _: 'yes')['status'], 'committed')


# The fixture's own tests stay in test_handover; only this file's tests run here.
for _name in dir(test_handover.HandoverTest):
    if _name.startswith('test_'):
        setattr(HandoverLinksTest, _name, None)


if __name__ == '__main__':
    unittest.main()
