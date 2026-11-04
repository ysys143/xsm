"""Hook -> CLI/service round trips; native identity and transport are fixtures."""
import contextlib
import io
import json
import os
import subprocess
from pathlib import Path
from unittest import mock

from tests.test_xsm import TempState


class PublicCommandFlowTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import config, registry
        self.rows = []
        for runtime, name, repo in [('claude', 'import-data', 'jstack'),
                                    ('codex', 'wdl-coordinator', 'wdl')]:
            folder = Path(self.tmp, repo); folder.mkdir()
            subprocess.run(['git', 'init', '-q', str(folder)], check=True)
            home = Path(self.tmp, runtime); home.mkdir()
            config.add_home(str(home), runtime)
            row = registry.upsert(runtime, str(home), runtime, os.getpid(), str(folder), name=name)
            self.rows.append(dict(row, state='live', registered=True,
                                  **({'socket': '/fixture/native.sock'} if runtime == 'claude' else {})))
        self.a, self.b = self.rows
        p = mock.patch.object(registry, 'records', return_value=self.rows)
        p.start(); self.addCleanup(p.stop)
        p = mock.patch.object(registry, '_enrich', side_effect=lambda row: next(
            (r for r in self.rows if r['runtime'] == row.get('runtime') and
             r['home'] == row.get('home') and r['session_id'] == row.get('session_id')), row))
        p.start(); self.addCleanup(p.stop)

    def user_command(self, who, command):
        from xsm import consent
        event = ({'hook_event_name': 'UserPromptExpansion', 'expansion_type': 'slash_command',
                  'command_name': 'xsm', 'command_args': command} if who['runtime'] == 'claude' else
                 {'hook_event_name': 'UserPromptSubmit', 'prompt': '$xsm '+command})
        return consent.record(who, event)

    def cli(self, who, *args):
        from xsm import cli, context, registry
        out = io.StringIO()
        with mock.patch.object(registry, 'me', return_value=who), \
                mock.patch.object(registry, 'last_identity', return_value=context.of_record(who, context.BASIS_SESSION)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(list(args))
        return code, out.getvalue()

    def test_each_native_publish_command_publishes_on_first_cli_call_without_an_ask(self):
        from xsm import config, consent, directory
        for who in self.rows:
            with self.subTest(runtime=who['runtime']):
                before = config.load()
                self.assertIsNotNone(self.user_command(who, 'publish'))
                code, text = self.cli(who, 'publish')
                self.assertEqual(code, 0, text)
                self.assertEqual(json.loads(text)['status'], 'published')
                self.assertTrue(directory.is_published(who))
                self.assertEqual(consent.pending_files(who['ref']), [])
                self.assertEqual(config.load(), before)
                self.assertEqual(self.cli(who, 'publish', '--off')[0], 0)

    def test_a_pasted_claude_command_or_peer_message_does_not_publish(self):
        from xsm import consent, directory
        for text in ('/xsm publish', '[xsm v1 id=peer kind=task]\npublish'):
            consent.record(self.a, {'hook_event_name': 'UserPromptSubmit', 'prompt': text})
            self.assertFalse(directory.is_published(self.a))
        code, _ = self.cli(self.a, 'publish')
        self.assertEqual(code, 2)

    def test_publication_command_is_bound_to_home_and_conversation(self):
        from xsm import connect, consent, directory
        self.user_command(self.a, 'publish')
        binding = {'conversation': {k:self.a[k] for k in ('runtime','home','session_id')}}
        for changed in (dict(self.a, session_id='other'), dict(self.a, home=self.tmp+'/other')):
            self.assertIsNone(consent.take_selection_command(changed, 'publish', binding))
        self.assertEqual(connect.publication(self.a)['status'], 'published')
        self.assertTrue(directory.is_published(self.a))

    def test_noop_publish_and_withdrawal_do_not_leave_an_old_publish_permission(self):
        from xsm import consent
        self.user_command(self.a, 'publish'); self.assertEqual(self.cli(self.a, 'publish')[0], 0)
        self.user_command(self.a, 'publish'); self.assertEqual(self.cli(self.a, 'publish')[0], 0)
        self.assertEqual(self.cli(self.a, 'publish', '--off')[0], 0)
        self.assertEqual(self.cli(self.a, 'publish')[0], 2)

    def test_later_native_user_turn_supersedes_an_unconsumed_command(self):
        from xsm import config, connect, consent
        for who in self.rows:
            with self.subTest(runtime=who['runtime']):
                self.user_command(who, 'publish')
                consent.record(who, {'hook_event_name': 'UserPromptSubmit', 'prompt': '취소. 공개하지 마.'})
                self.assertEqual(self.cli(who, 'publish')[0], 2)
        self.user_command(self.b, 'connect ref:'+self.a['ref'])
        consent.record(self.b, {'hook_event_name': 'UserPromptSubmit', 'prompt': '취소. 연결하지 마.'})
        self.assertEqual(connect.select(self.b, self.a)['status'], 'selection-required')
        self.assertIsNone(config.scope_for(self.a, self.b)[0])

    def test_contact_does_not_select_a_different_named_person_or_a_question(self):
        from xsm import collaboration, consent, directory
        self.user_command(self.a, 'publish'); self.assertEqual(self.cli(self.a, 'publish')[0], 0)
        binding = {'pair': collaboration.propose(self.b, self.a)['endpoints']}
        for text in ('jstack의 bob에게 연락해줘', 'jstack의 bob 세션에 연락해줘',
                     'jstack에 연락해도 되는지 설명해줘', 'jstack 세션에 연락할까?',
                     'jstack 세션에 연락해줘. 취소. 연락하지 마.'):
            with self.subTest(text=text):
                consent.record(self.b, {'hook_event_name': 'UserPromptSubmit', 'prompt': text})
                with mock.patch.object(directory, '_liveness', return_value=('live', 'live')):
                    self.assertIsNone(consent.take_contact_selection(self.b, binding))

    def test_partial_discovery_never_establishes_a_unique_contact_selection(self):
        from xsm import collaboration, consent, directory
        self.user_command(self.a, 'publish'); self.assertEqual(self.cli(self.a, 'publish')[0], 0)
        consent.record(self.b, {'hook_event_name': 'UserPromptSubmit', 'prompt': 'jstack 세션에 연락해줘.'})
        binding = {'pair': collaboration.propose(self.b, self.a)['endpoints']}
        with mock.patch.object(directory, '_liveness', return_value=('live', 'live')):
            complete = directory.discover(self.b)
        self.assertEqual([r['ref'] for r in complete['candidates'] if not r['is_self']], [self.a['ref']])
        with mock.patch.object(directory, 'discover', return_value=dict(
                complete, status='unknown', reason='probe_incomplete', unanswered={'home': 'timeout'})):
            self.assertIsNone(consent.take_contact_selection(self.b, binding))

    def test_clear_contact_instruction_selects_only_the_unique_repository_peer(self):
        from xsm import config, connect, consent, directory
        self.user_command(self.a, 'publish'); self.assertEqual(self.cli(self.a, 'publish')[0], 0)
        consent.record(self.b, {'hook_event_name': 'UserPromptSubmit',
                               'prompt': 'jstack에서 일하는 세션에 끝나면 알려달라고 해.'})
        before = config.load()
        with mock.patch.object(directory, '_liveness', return_value=('live', 'live')):
            result = connect.select(self.b, self.a)
        self.assertEqual(result['status'], 'permitted', result)
        self.assertEqual(config.load(), before)
        self.assertTrue(config.scope_for(self.a, self.b)[0])
        self.assertEqual(consent.pending_files(self.b['ref']), [])

    def test_original_deferred_notification_request_is_a_repository_selection(self):
        from xsm import collaboration, consent, directory
        self.user_command(self.a, 'publish'); self.assertEqual(self.cli(self.a, 'publish')[0], 0)
        text = 'jstack에서 뭔가 하고 있는데 끝나면 알려달라고 해. 끝나면 너가 또 받아서 반입하고 릴리즈까지 진행해.'
        consent.record(self.b, {'hook_event_name': 'UserPromptSubmit', 'prompt': text})
        with mock.patch.object(directory, '_liveness', return_value=('live', 'live')):
            self.assertEqual(consent.take_contact_selection(self.b, {
                'pair': collaboration.propose(self.b, self.a)['endpoints']}), text)

    def test_ambiguous_repository_or_later_cancellation_does_not_auto_connect(self):
        from xsm import config, connect, consent, directory, registry
        self.user_command(self.a, 'publish'); self.assertEqual(self.cli(self.a, 'publish')[0], 0)
        consent.record(self.b, {'hook_event_name': 'UserPromptSubmit', 'prompt': 'jstack 세션에 연락해줘.'})
        other = registry.upsert('claude', self.a['home'], 'other', os.getpid(), self.a['cwd'], name='other')
        directory.publish(other, user_source='explicit fixture publication')
        with mock.patch.object(directory, '_liveness', return_value=('live', 'live')):
            result = connect.select(self.b, self.a)
        self.assertEqual(result['status'], 'selection-required')
        self.assertIsNone(config.scope_for(self.a, self.b)[0])
        consent.record(self.b, {'hook_event_name': 'UserPromptSubmit', 'prompt': '취소. 연락하지 마.'})
        self.assertIsNone(consent.take_contact_selection(self.b, {'pair': __import__('xsm.collaboration', fromlist=['propose']).propose(self.b,self.a)['endpoints']}))

    def test_repository_query_and_table_find_published_peer_without_reach(self):
        from xsm import config, directory
        self.user_command(self.a, 'publish'); self.assertEqual(self.cli(self.a, 'publish')[0], 0)
        before = config.load()
        with mock.patch.object(directory, '_native', return_value={}), \
                mock.patch.object(directory, '_title', return_value=directory._observation()):
            code, text = self.cli(self.b, 'discover', 'jstack', '--table')
            self.assertEqual(code, 0)
            self.assertIn('import-data', text)
            code, text = self.cli(self.b, 'discover', 'jstack')
            result = json.loads(text)
        self.assertEqual([r['ref'] for r in result['candidates']], [self.a['ref']])
        self.assertEqual(config.load(), before)
        self.assertIsNone(config.scope_for(self.a, self.b)[0])

    def test_explicit_connect_command_selects_only_its_exact_peer_without_an_ask(self):
        from xsm import config, connect, consent
        before = config.load()
        self.assertIsNotNone(self.user_command(self.b, 'connect ref:'+self.a['ref']))
        result = connect.select(self.b, self.a)
        self.assertEqual(result['status'], 'permitted', result)
        self.assertTrue(config.scope_for(self.a, self.b)[0])
        self.assertEqual(config.load(), before)
        self.assertEqual(consent.pending_files(self.b['ref']), [])

    def test_cli_and_mcp_repository_query_return_the_same_exact_candidate(self):
        from xsm import mcp
        self.user_command(self.a, 'publish'); self.assertEqual(self.cli(self.a, 'publish')[0], 0)
        code, text = self.cli(self.b, 'discover', 'jstack')
        self.assertEqual(code, 0)
        server = mcp.Server(io.StringIO(), io.StringIO())
        server.session = lambda: self.b
        value = json.loads(server.call('xsm_discover', {'query': 'jstack'}))
        self.assertEqual([x['target'] for x in value['candidates']],
                         [x['target'] for x in json.loads(text)['candidates']])

    def test_publish_discover_select_ask_and_late_reply_keep_the_original_request(self):
        from xsm import adapters, config, context, question_service, receive, send
        before = config.load()
        self.user_command(self.a, 'publish'); self.assertEqual(self.cli(self.a, 'publish')[0], 0)
        code, text = self.cli(self.b, 'discover', 'jstack')
        self.assertEqual(code, 0)
        target = json.loads(text)['candidates'][0]['target']
        self.user_command(self.b, 'connect '+target)
        # Only the native transport is replaced. Hook, selection, storage,
        # correlation, claims and ACK use the ordinary production services.
        with mock.patch.object(adapters, 'to_claude', return_value=None), \
                mock.patch.object(adapters, 'to_codex', return_value=None):
            code, text = self.cli(self.b, 'connect', target)
            handshake = json.loads(text)
            self.assertEqual(handshake['handshake'], 'pending', handshake)
            self.assertEqual(code, 3)
            code, text = self.cli(self.b, 'ask', target, '--text', 'notify me when finished')
            pending = json.loads(text)
            self.assertEqual(code, 3, pending)
            for encoded in (json.dumps(pending), json.dumps(pending, indent=2)):
                decoded = json.loads(encoded)
                self.assertEqual(decoded['status'], 'pending')
                self.assertEqual(decoded['replies'], [])
                self.assertFalse(decoded['final'])
            inbox = receive.take_inbox_claims(self.a)
            claims = inbox['claims']
            self.assertEqual({c['id'] for c in claims}, {handshake['id'], pending['id']})
            receive.ack_inbox(self.a, [c['token'] for c in claims])
            reply = send.send('ref:'+self.b['ref'], 'finished abc123', sender=self.a,
                              kind='reply', reply_to=pending['id'], outcome='succeeded')
            result = question_service.status(self.b, pending['id'])['result']
            self.assertEqual(result['id'], pending['id'])
            self.assertTrue(result['final'])
            self.assertEqual(result['replies'][0]['body'], 'finished abc123')
            claimed = receive.claim_question_replies(self.b, result)
            self.assertEqual([c['id'] for c in claimed['claims']], [reply.msg_id])
            receive.ack_inbox(self.b, [c['token'] for c in claimed['claims']])
            retained = question_service.status(self.b, pending['id'])['result']
            self.assertEqual(retained['replies'][0]['body'], 'finished abc123')
            self.assertEqual(config.load(), before)
