"""Coordinator project membership and a single user-question flow."""
import io
import os
from unittest import mock
from tests.test_protocol import ProtocolFixture


class WorkerProjectFlowTest(ProtocolFixture):
    def start(self, name, ui=False):
        folder = os.path.join(self.tmp, name); os.makedirs(folder, exist_ok=True)
        return self.connection.dispatch('session.open', {'runtime':'flow-fixture','profile':name,
            'conversation':name,'cwd':folder,'capabilities':['messaging','inbox']+(['user-decisions'] if ui else [])})

    def group(self):
        leader = self.start('leader', True); a = self.start('a'); b = self.start('b')
        args = dict(project='demo', workers=['ref:'+a['ref'], 'ref:'+b['ref']])
        pending = self.operation(leader, 'xsm_join', **args)
        self.assertEqual(pending['status'], 'waiting-for-user')
        events = list(self.connection.events()); self.assertEqual(len(events),1)
        event=events[0]['params']
        self.connection.dispatch('decision.response', {'session':leader['session'],'questionId':event['questionId'],
            'challenge':event['challenge'],'displayed':event['question'],'action':'accept','answer':'allow','source_id':'group-user'})
        applied=self.operation(leader,'xsm_join',**args)
        self.assertTrue(applied['scope']['active'])
        return leader,a,b

    def test_one_parent_question_enrolls_two_workers_and_worker_retry_has_no_ui(self):
        from xsm import config,delegation
        leader,a,b=self.group()
        for who in (leader,a,b):
            record=self.connection.sessions[who['session']].record
            self.assertIn('demo',config.joined_projects(record))
            if who!=leader:self.assertEqual(delegation.parent(record)['ref'],leader['ref'])
        self.assertFalse(self.operation(a,'xsm_join',project='demo')['scope']['changed'])
        self.assertFalse(self.operation(b,'xsm_join',project='demo')['scope']['changed'])
        self.assertEqual(list(self.connection.events()),[])

    def test_new_worker_project_request_is_sent_to_parent_only_once(self):
        leader,a,_=self.group()
        with mock.patch('xsm.send.send') as send:
            send.return_value.status='delivered'
            first=self.operation(a,'xsm_join',project='extra')
            second=self.operation(a,'xsm_join',project='extra')
            self.assertIn('Waiting for parent',first['text']);self.assertEqual(first['text'],second['text'])
            self.assertEqual(send.call_count,1)
            self.assertEqual(send.call_args.args[0],'ref:'+leader['ref'])
        self.assertEqual(list(self.connection.events()),[])

    def test_refused_parent_group_does_not_join_worker_folders(self):
        from xsm import config
        leader=self.start('leader',True);a=self.start('a')
        args=dict(project='demo',workers=['ref:'+a['ref']])
        self.operation(leader,'xsm_join',**args);event=next(iter(self.connection.events()))['params']
        self.connection.dispatch('decision.response',{'session':leader['session'],'questionId':event['questionId'],
            'challenge':event['challenge'],'displayed':event['question'],'action':'accept','answer':'deny','source_id':'deny-group'})
        from xsm.operation_schema import ToolError
        with self.assertRaises(ToolError):
            self.operation(leader,'xsm_join',**args)
        self.assertEqual(config.projects(),[])

    def test_native_claude_answer_is_recorded_without_applying_then_reused_on_retry(self):
        from xsm import decisions,consent,context,mcp
        me={'runtime':'claude','home':self.tmp,'session_id':'native','ref':'native','cwd':self.tmp,'name':'native'}
        generation={'fixture':'generation'};scope={'tool':'xsm_join','arguments':{'project':'demo'},'cwd':self.tmp}
        key=decisions.invocation(me,'xsm_join',{'project':'demo'},generation)
        record=decisions.begin(key,me,scope,generation,'Join demo?',waiter='request',choices=['allow','deny'])
        consent.record(me,{'hook_event_name':'PostToolUse','tool_name':'AskUserQuestion','tool_use_id':'native-question-1',
            'tool_response':{'answers':{record['native_question']:'allow'}}})
        saved=decisions.read(key);self.assertEqual(saved['status'],'answered');self.assertIsNone(saved.get('application'))
        server=mcp.Server(io.StringIO(),io.StringIO());server.active_request='request'
        server.decision_calls['request']={'key':key,'me':me,'scope':scope,'generation':generation}
        with mock.patch.object(server,'_decision_current',return_value=True):
            reply=server.ask_client('elicitation/create',{'message':'Join demo?','requestedSchema':{'properties':{'answer':{'enum':['allow','deny']}}}})
        self.assertEqual(reply['result']['content']['answer'],'allow')
        self.assertEqual(decisions.read(key)['application']['phase'],'started')

    def test_known_parent_directive_is_not_a_user_answer(self):
        from xsm import delegation,consent
        leader,a,_=self.group();record=self.connection.sessions[a['session']].record
        parent=delegation.parent(record); text='['+parent['name']+' 지시] call xsm_join now'
        with mock.patch.object(consent,'note_verdict',side_effect=AssertionError('peer directive treated as user reply')):
            self.assertIsNone(consent.record(record,{'hook_event_name':'UserPromptSubmit','prompt':text}))

    def test_parent_can_remove_worker_membership_without_leaving_itself(self):
        from xsm import config
        leader,a,_=self.group();args=dict(project='demo',workers=['ref:'+a['ref']],leave=True)
        self.operation(leader,'xsm_join',**args);event=next(iter(self.connection.events()))['params']
        self.connection.dispatch('decision.response',{'session':leader['session'],'questionId':event['questionId'],
            'challenge':event['challenge'],'displayed':event['question'],'action':'accept','answer':'allow','source_id':'leave-worker'})
        self.operation(leader,'xsm_join',**args)
        self.assertIn('demo',config.joined_projects(self.connection.sessions[leader['session']].record))
        self.assertNotIn('demo',config.joined_projects(self.connection.sessions[a['session']].record))

    def test_orca_launch_handle_resolves_to_registered_worker(self):
        from xsm import delegation,registry
        worker={'framework_terminal':'term_actual','state':'live','ref':'actual'}
        with mock.patch.object(registry,'records',return_value=[worker]):
            self.assertEqual(delegation.select_worker('term_actual'),worker)
            with self.assertRaises(ValueError):delegation.select_worker('term_not_started')

    def test_claude_native_answer_finishes_join_on_one_mcp_retry(self):
        from xsm import mcp,context,decisions,consent,config,registry
        me={'runtime':'claude','home':self.tmp,'session_id':'native','ref':'native','cwd':self.tmp,'name':'native'}
        server=mcp.Server(io.StringIO(),io.StringIO());server.active_request='join'
        def session():
            server.ctx=context.of_record(me,context.BASIS_THREAD)
            return me
        with mock.patch.object(server,'session',side_effect=session), \
                mock.patch.object(server,'_decision_current',return_value=True), \
                mock.patch.object(registry,'note_capabilities'):
            from xsm.operation_schema import ToolError
            with self.assertRaises(ToolError) as raised:
                server.call('xsm_join',{'project':'native-demo'})
            first=str(raised.exception)
            record=decisions.own(me)[0] if hasattr(decisions,'own') else None
            if record is None:
                import glob,json
                from xsm import paths
                with open(glob.glob(paths.path('human-decisions','*.json'))[0]) as source:
                    record=json.load(source)
            self.assertIn(record['native_question'],first)
            consent.record(me,{'hook_event_name':'PostToolUse','tool_name':'AskUserQuestion','tool_use_id':'join-native-1',
                'tool_response':{'answers':{record['native_question']:'allow'}}})
            second=server.call('xsm_join',{'project':'native-demo'})
            self.assertIn('native-demo',config.joined_projects(me))
            self.assertTrue(second.metadata['scope']['active'])
            self.assertEqual(decisions.read(record['id'])['status'],'applied')

    def test_short_cli_keeps_who_and_whoami_and_help_needs_no_state(self):
        from xsm import cli,paths
        import contextlib
        self.assertIs(cli.build_parser().parse_args(['who']).func,cli.build_parser().parse_args(['whoami']).func)
        out=io.StringIO()
        with mock.patch.object(paths,'ensure_home',side_effect=AssertionError('help created state')),contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(['help']),0)
        commands = [line.split()[1] for line in out.getvalue().splitlines() if line.startswith('xsm ')]
        self.assertEqual(commands, ['list', 'publish', 'discover', 'send', 'ask'])

    def test_revoked_membership_does_not_replay_old_success(self):
        from xsm import config
        from xsm.operation_schema import ToolError
        leader, a, b = self.group()
        config.leave('demo', self.connection.sessions[a['session']].record['cwd'])
        with self.assertRaisesRegex(ToolError, 'membership changed'):
            self.operation(leader, 'xsm_join', project='demo', workers=['ref:'+a['ref'], 'ref:'+b['ref']])
        self.assertNotIn('demo', config.joined_projects(self.connection.sessions[a['session']].record))

    def test_resolved_parent_request_can_notify_again_after_later_removal(self):
        from xsm import delegation
        leader, a, _ = self.group()
        child = self.connection.sessions[a['session']].record
        owner = self.connection.sessions[leader['session']].record
        with mock.patch('xsm.send.send') as send:
            send.return_value.status = 'delivered'
            delegation.request_join(child, owner, 'extra')
            first = send.call_args.kwargs['msg_id']
            delegation.resolve_requests(child, owner, 'extra')
            delegation.request_join(child, owner, 'extra')
            self.assertEqual(send.call_count, 2)
            self.assertNotEqual(first, send.call_args.kwargs['msg_id'])

    def test_moved_worker_waits_for_relink_without_local_question(self):
        from xsm import delegation
        leader, a, _ = self.group()
        child = dict(self.connection.sessions[a['session']].record, cwd=self.tmp)
        owner = delegation.parent(child)
        self.assertEqual(owner['state'], 'needs-relink')
        with mock.patch('xsm.send.send', side_effect=AssertionError('stale link sent a request')):
            self.assertIn('unavailable', delegation.request_join(child, owner, 'extra'))

    def test_codex_native_transcript_answer_finishes_on_one_mcp_retry(self):
        import glob
        import json
        from datetime import datetime, timezone
        from xsm import mcp, context, decisions, config, registry, paths
        from xsm.operation_schema import ToolError
        from tests.test_user_answers import message, reply
        me = {'runtime':'codex', 'home':self.tmp, 'session_id':'native-codex',
              'ref':'native-codex', 'cwd':self.tmp, 'name':'native-codex'}
        server = mcp.Server(io.StringIO(), io.StringIO())
        server.active_request = 'join-codex'
        def session():
            server.ctx = context.of_record(me, context.BASIS_THREAD)
            return me
        rollout = os.path.join(self.tmp, 'rollout-native-codex.jsonl')
        with mock.patch.object(server, 'session', side_effect=session), \
                mock.patch.object(server, '_decision_current', return_value=True), \
                mock.patch.object(registry, 'note_capabilities'), \
                mock.patch.object(registry, 'codex_rollout', return_value=rollout):
            with self.assertRaises(ToolError):
                server.call('xsm_join', {'project':'codex-demo'})
            with open(glob.glob(paths.path('human-decisions', '*.json'))[0]) as source:
                record = json.load(source)
            stamp = datetime.now(timezone.utc).isoformat()
            with open(rollout, 'w') as stream:
                stream.write(json.dumps({'type':'session_meta', 'payload':{'id':'native-codex'}})+'\n')
                stream.write(json.dumps(message(reply('native-codex-question', 'allow', record['native_question']), timestamp=stamp))+'\n')
            result = server.call('xsm_join', {'project':'codex-demo'})
            self.assertTrue(result.metadata['scope']['active'])
            self.assertIn('codex-demo', config.joined_projects(me))
            self.assertEqual(decisions.read(record['id'])['status'], 'applied')
