"""Approved permission recovery contract: same-MCP retry, exact effect, once."""
import os
from pathlib import Path
from unittest import mock

from tests.test_xsm import TempState
from tests import permission_harness as harness


class NativePermissionRecoveryTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import identity
        self.me = {'runtime': 'claude', 'home': self.tmp + '/native-home',
                   'session_id': 'permission-owner', 'ref': 'abc123', 'cwd': self.tmp,
                   'pid': os.getpid(), 'lstart': identity.lstart(os.getpid()),
                   'name': 'owner', 'alias': 'fixture'}
        Path(self.me['home']).mkdir()

    def scenario(self, kind):
        from xsm import config, doc, paths, workers
        other = os.path.join(self.tmp, 'other-' + kind)
        os.makedirs(other, exist_ok=True)
        if kind == 'link':
            return 'xsm_link', {'dir': other}, lambda: config.links(), 'allow', 'deny'
        if kind in ('join', 'leave'):
            project = 'project-' + kind
            if kind == 'leave':
                config.join(project, self.tmp)
            return ('xsm_join', {'project': project, 'leave': kind == 'leave'},
                    lambda: project in config.joined_projects(self.me), 'allow', 'deny')
        if kind == 'reach':
            return 'xsm_reach', {'dir': other}, lambda: config.reaches(), 'allow', 'deny'
        if kind == 'approve':
            workers.save({'name': 'worker', 'runtime': 'claude', 'mode': 'background',
                          'parent_ref': self.me['ref'], 'cwd': self.tmp, 'created': 0})
            paths.write_json(workers._approval_path('request'),
                             {'id': 'request', 'worker': 'worker', 'status': 'pending',
                              'summary': 'Bash: build', 'tool': 'Bash', 't': 0})
            return ('xsm_approve', {'id': 'request'},
                    lambda: paths.read_json(workers._approval_path('request'))['status'], 'allow', 'deny')
        if kind in ('grant', 'outside-grant', 'remote-grant'):
            remote = kind == 'remote-grant'
            arguments = {'runtime': 'remote:box' if remote else 'codex',
                         'options': ['remote'] if remote else ['full_access'],
                         'reason': 'fixture permission',
                         'dir': other if kind != 'grant' else self.tmp}
            return ('xsm_grant', arguments,
                    lambda: sorted(Path(paths.path(workers.GRANTS)).glob('*.json')), 'allow once', 'deny')
        document = os.path.join(self.tmp, 'report.md')
        node = doc.add(document, {'kind': 'agent', 'name': 'author', 'ref': 'def456'},
                       'Report text', ['report'], [])
        return ('xsm_doc_endorse', {'doc': document, 'node': node['id']},
                lambda: [n for n in doc.read(document) if 'endorsed' in n.get('tags', [])],
                'endorse', 'not now')

    def exercise(self, kind, allowed):
        from xsm import decisions
        name, arguments, effect, yes, no = self.scenario(kind)
        before = effect()
        result, frames = harness.invoke(self.me, name, arguments)
        first = result['content'][0]['text']
        self.assertIn('retry this same MCP tool', first)
        self.assertNotIn('Shell equivalent:', first)
        self.assertEqual(effect(), before, 'asking is not permission')
        record = harness.pending(self.me, first)
        harness.answer(self.me, record, yes if allowed else no)
        self.assertEqual(effect(), before, 'recording a choice is not application')
        result, frames = harness.invoke(self.me, name, arguments)
        applied = decisions.read(record['id'])
        if allowed:
            self.assertFalse(result.get('isError'), result)
            self.assertNotEqual(effect(), before, 'permission must reach the domain operation')
            self.assertEqual(applied['status'], 'applied')
        else:
            self.assertEqual(effect(), 'denied' if kind == 'approve' else before,
                             'a refusal must not grant permission')
            self.assertEqual(applied['status'], 'denied')
        after = effect()
        again, frames = harness.invoke(self.me, name, arguments)
        self.assertEqual(effect(), after, 'retry must not apply again')
        if allowed:
            self.assertEqual(again, result, 'retry returns the original applied receipt')
        self.assertFalse(any(row.get('method') == 'elicitation/create' for row in frames))

    def test_allow_link(self): self.exercise('link', True)
    def test_deny_link(self): self.exercise('link', False)
    def test_allow_join(self): self.exercise('join', True)
    def test_deny_join(self): self.exercise('join', False)
    def test_allow_leave(self): self.exercise('leave', True)
    def test_deny_leave(self): self.exercise('leave', False)
    def test_allow_reach(self): self.exercise('reach', True)
    def test_deny_reach(self): self.exercise('reach', False)
    def test_allow_worker_request(self): self.exercise('approve', True)
    def test_deny_worker_request(self): self.exercise('approve', False)
    def test_allow_grant(self): self.exercise('grant', True)
    def test_deny_grant(self): self.exercise('grant', False)
    def test_allow_outside_grant(self): self.exercise('outside-grant', True)
    def test_deny_outside_grant(self): self.exercise('outside-grant', False)
    def test_allow_remote_grant(self): self.exercise('remote-grant', True)
    def test_deny_remote_grant(self): self.exercise('remote-grant', False)
    def test_allow_endorsement(self): self.exercise('endorse', True)
    def test_deny_endorsement(self): self.exercise('endorse', False)

    def test_dismissed_claude_form_can_recover_from_a_fresh_native_answer(self):
        from xsm import config, decisions
        args = {'project': 'cancel-recovery'}
        result, _ = harness.invoke(self.me, 'xsm_join', args, {'result': {'action': 'cancel'}})
        record = harness.pending(self.me, result['content'][0]['text'])
        self.assertEqual(record['status'], 'dismissed')
        harness.answer(self.me, record, 'allow')
        result, _ = harness.invoke(self.me, 'xsm_join', args)
        self.assertFalse(result.get('isError'), result)
        self.assertIn(args['project'], config.joined_projects(self.me))
        self.assertEqual(decisions.read(record['id'])['status'], 'applied')

    def test_dismissed_codex_form_recovers_from_its_actual_native_record_format(self):
        from xsm import config, decisions
        self.me['runtime'] = 'codex'
        args = {'project': 'codex-cancel-recovery'}
        result, _ = harness.invoke(self.me, 'xsm_join', args, {'result': {'action': 'cancel'}})
        record = harness.pending(self.me, result['content'][0]['text'])
        harness.answer(self.me, record, 'allow')
        result, _ = harness.invoke(self.me, 'xsm_join', args)
        self.assertFalse(result.get('isError'), result)
        self.assertIn(args['project'], config.joined_projects(self.me))
        self.assertEqual(decisions.read(record['id'])['status'], 'applied')

    def test_an_unshown_decline_recovers_only_after_a_fresh_native_choice(self):
        from xsm import config, decisions
        args = {'project': 'unshown-recovery'}
        result, _ = harness.invoke(self.me, 'xsm_join', args, {'result': {'action': 'decline'}})
        record = harness.pending(self.me, result['content'][0]['text'])
        self.assertEqual(record['status'], 'unshown-or-declined')
        self.assertNotIn(args['project'], config.joined_projects(self.me))
        harness.answer(self.me, record, 'allow')
        result, _ = harness.invoke(self.me, 'xsm_join', args)
        self.assertFalse(result.get('isError'), result)
        self.assertIn(args['project'], config.joined_projects(self.me))
        saved = decisions.read(record['id'])
        self.assertEqual(saved['answer_history'][0]['reply']['result']['action'], 'decline')

    def test_an_automatic_reviewer_is_not_permission_but_a_new_native_choice_is(self):
        from xsm import config, decisions
        args = {'project': 'automatic-reviewer-recovery'}
        result, _ = harness.invoke(self.me, 'xsm_join', args, {'result': {'action': 'accept',
            'content': {'answer': 'allow'}, '_meta': {'approvals_reviewer': 'auto_review'}}})
        record = harness.pending(self.me, result['content'][0]['text'])
        self.assertEqual(record['status'], 'unknown')
        self.assertNotIn(args['project'], config.joined_projects(self.me))
        harness.answer(self.me, record, 'allow')
        result, _ = harness.invoke(self.me, 'xsm_join', args)
        self.assertFalse(result.get('isError'), result)
        self.assertIn(args['project'], config.joined_projects(self.me))
        self.assertEqual(decisions.read(record['id'])['answer']['source'], 'native-user')

    def test_a_native_answer_before_dismissal_cannot_revive_that_permission(self):
        from datetime import datetime, timezone
        from xsm import config, decisions
        self.me['runtime'] = 'codex'
        args = {'project': 'obsolete-answer'}
        result, _ = harness.invoke(self.me, 'xsm_join', args, {'result': {'action': 'cancel'}})
        record = harness.pending(self.me, result['content'][0]['text'])
        old = datetime.fromtimestamp(record['created_at'], timezone.utc).isoformat()
        harness.answer(self.me, record, 'allow', timestamp=old)
        harness.invoke(self.me, 'xsm_join', args)
        self.assertNotIn(args['project'], config.joined_projects(self.me))
        self.assertEqual(decisions.read(record['id'])['status'], 'dismissed')

    def test_an_explicit_decline_cannot_be_reopened_by_a_native_answer(self):
        from xsm import config, decisions
        args = {'project': 'real-decline'}
        result, _ = harness.invoke(self.me, 'xsm_join', args, {'result': {'action': 'decline'}},
                                   client='claude-code')
        records = decisions.public_status(self.me)['decisions']
        self.assertEqual(len(records), 1)
        record = decisions.read(records[0]['id'])
        self.assertEqual(record['status'], 'denied')
        harness.answer(self.me, record, 'allow')
        harness.invoke(self.me, 'xsm_join', args)
        self.assertEqual(decisions.read(record['id'])['status'], 'denied')
        self.assertNotIn(args['project'], config.joined_projects(self.me))

    def test_a_different_native_question_cannot_capture_the_pending_choice(self):
        from xsm import config, decisions
        args = {'project': 'exact-question'}
        result, _ = harness.invoke(self.me, 'xsm_join', args)
        record = harness.pending(self.me, result['content'][0]['text'])
        different = dict(record, native_question=record['native_question'] + ' A different request.')
        harness.answer(self.me, different, 'allow')
        self.assertIsNone(decisions.read(record['id'])['answer'])
        harness.invoke(self.me, 'xsm_join', args)
        self.assertNotIn(args['project'], config.joined_projects(self.me))

    def test_a_decline_during_native_capture_wins_before_application(self):
        from xsm import config, decisions
        args = {'project': 'concurrent-decline'}
        result, _ = harness.invoke(self.me, 'xsm_join', args)
        record = harness.pending(self.me, result['content'][0]['text'])
        claim = decisions.claim_native

        def decline_before_response(*arguments):
            claim(*arguments)
            decisions.response(record['id'], {'result': {'action': 'accept',
                'content': {'answer': 'deny'}, '_meta': {'approvals_reviewer': 'user'}}},
                'mcp-elicitation', source_id='fixture-concurrent-denial')

        with mock.patch.object(decisions, 'claim_native', side_effect=decline_before_response):
            harness.answer(self.me, record, 'allow')
        harness.invoke(self.me, 'xsm_join', args)
        self.assertEqual(decisions.read(record['id'])['status'], 'denied')
        self.assertNotIn(args['project'], config.joined_projects(self.me))

    def test_an_outside_scope_grant_covers_the_worker_that_was_approved(self):
        from xsm import paths, workers
        name, arguments, _, yes, _ = self.scenario('outside-grant')
        result, _ = harness.invoke(self.me, name, arguments)
        record = harness.pending(self.me, result['content'][0]['text'])
        harness.answer(self.me, record, yes)
        result, _ = harness.invoke(self.me, name, arguments)
        self.assertFalse(result.get('isError'), result)
        records = list(Path(paths.path(workers.GRANTS)).glob('*.json'))
        self.assertEqual(len(records), 1)
        granted = paths.read_json(str(records[0]))
        self.assertIn('outside_scope', granted['options'])
        self.assertIn('OUTSIDE', record['question'])
        used = workers.use_grant(granted['id'], self.me, 'codex', arguments['dir'],
                                 ['full_access', 'outside_scope'])
        self.assertEqual(used['id'], granted['id'])
        with self.assertRaises(workers.WorkerError):
            workers.use_grant(granted['id'], self.me, 'codex', arguments['dir'],
                              ['full_access', 'outside_scope'])
