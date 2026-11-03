"""Hermes coordinator lifecycle and isolated backend recovery, without a model."""
import asyncio
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace, ModuleType
import unittest


spec = importlib.util.spec_from_file_location(
    "xsm_hermes_binding", Path(__file__).resolve().parents[1] / "integrations/hermes/xsm.py")
module = importlib.util.module_from_spec(spec)
if os.environ.get('XSM_HERMES_MONITOR_MUTANT') == 'disabled':
    code = Path(spec.origin).read_text()
    changed = code.replace('    async def _monitor(self, sid, cwd):', '    async def _monitor(self, sid, cwd):\n        return')
    if changed == code:
        raise RuntimeError('monitor entry moved; update intentional mutation')
    exec(compile(changed, spec.origin, 'exec'), module.__dict__)
else:
    spec.loader.exec_module(module)


class HermesLifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def test_native_subagent_hook_supplies_parent_when_child_opens(self):
        binding = module.HermesBinding.__new__(module.HermesBinding)
        binding.parents, binding.hosts = {}, {}
        binding.monitors = {'native-child': None}
        binding.closed, binding.closing, binding.finalizing = False, False, set()
        binding.profile, binding.command, binding.env = 'isolated', [], {}
        calls, scheduled = [], []
        async def open_host(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace()
        binding.sdk = SimpleNamespace(XsmHost=SimpleNamespace(open=open_host))
        binding._run = lambda coroutine: scheduled.append(asyncio.create_task(coroutine))
        binding.subagent_start(parent_session_id='native-root', child_session_id='native-child')
        await asyncio.gather(*scheduled)
        await binding._open_host('native-child', '/workspace')
        self.assertEqual(calls[0]['parent_conversation'], 'native-root')
        self.assertEqual(calls[0]['conversation'], 'native-child')
        binding.subagent_start(parent_session_id='unrelated', child_session_id='native-child')
        with self.assertRaisesRegex(RuntimeError, 'changed its parent'):
            await scheduled[-1]
        self.assertEqual(binding.parents['native-child'], 'native-root')

    async def test_default_backend_uses_native_profile_secret_scoping_without_ambient_worker(self):
        binding=module.HermesBinding.__new__(module.HermesBinding)
        binding.env=None;binding.profile='/native/profile-b'
        native=ModuleType('tools.environments.local')
        native.served_profile_child_env=mock.Mock(side_effect=lambda **kwargs:
            {key:value for key,value in kwargs['base'].items() if key!='FIXTURE_API_KEY'})
        source={'HOME':'/fixture-home','XSM_HOME':'/fixture-state','XSM_WORKER':'different-worker',
                'XSM_OWNED_CONTROL_FD':'9','HERMES_HOME':'/native/profile-a','FIXTURE_API_KEY':'fixture'}
        with mock.patch.dict(sys.modules,{'tools.environments.local':native}),mock.patch.object(module.os,'environ',source):
            environment=binding._backend_environment()
        self.assertEqual(environment['HERMES_HOME'],'/native/profile-b')
        self.assertEqual(environment['XSM_HOME'],'/fixture-state')
        self.assertNotIn('XSM_WORKER',environment)
        self.assertNotIn('XSM_OWNED_CONTROL_FD',environment)
        self.assertNotIn('FIXTURE_API_KEY',environment)
        self.assertEqual(native.served_profile_child_env.call_args.kwargs['target_home'],'/native/profile-b')
        self.assertIs(native.served_profile_child_env.call_args.kwargs['inherit_credentials'],False)

    async def test_explicit_backend_environment_is_copied_and_profile_bound(self):
        binding=module.HermesBinding.__new__(module.HermesBinding)
        binding.env={'XSM_WORKER':'other','HERMES_HOME':'/wrong','XSM_HOME':'/state'}
        binding.profile='/native/own-profile'
        environment=binding._backend_environment()
        self.assertEqual(environment,{'HERMES_HOME':'/native/own-profile','XSM_HOME':'/state'})
        self.assertEqual(binding.env['XSM_WORKER'],'other')
    async def test_finalize_waits_for_inflight_open_before_removing_participation(self):
        entered, release = asyncio.Event(), asyncio.Event()
        closed = []

        async def close():
            closed.append(True)

        host = SimpleNamespace(close=close)

        async def open_host(**kwargs):
            entered.set()
            await release.wait()
            return host

        binding = module.HermesBinding.__new__(module.HermesBinding)
        binding.hosts, binding.host_locks = {}, {}
        binding.closed, binding.closing, binding.finalizing, binding.monitors, binding.states = False, False, set(), {}, {}
        binding.profile, binding.command, binding.env = "isolated", [], {}
        binding.sdk = SimpleNamespace(XsmHost=SimpleNamespace(open=open_host))
        scheduled = []
        binding._run = lambda coroutine: scheduled.append(asyncio.create_task(coroutine))
        opening = asyncio.create_task(binding._host("native", "/workspace"))
        await entered.wait()
        binding.finalize(session_id="native")
        await asyncio.sleep(0)
        release.set()
        results = await asyncio.gather(opening, *scheduled, return_exceptions=True)
        self.assertIsInstance(results[0], RuntimeError, repr(results))
        self.assertIn("closing", str(results[0]))
        self.assertIsNone(results[1], repr(results))
        self.assertEqual(closed, [True])
        self.assertEqual(binding.hosts, {})


    async def test_failed_operation_is_not_replayed_when_next_invocation_recovers(self):
        calls, opens = [], []
        async def close():
            old.closed = True
        async def failed(operation, arguments):
            calls.append(operation)
            old.failure = RuntimeError("outcome unknown")
            raise old.failure
        async def successful(operation, arguments):
            calls.append(operation)
            return {"recovered": True}
        old = SimpleNamespace(failure=None, closed=False, call=failed, close=close)
        new = SimpleNamespace(failure=None, closed=False, call=successful)
        async def open_host(**kwargs):
            opens.append(kwargs)
            return new
        existing = asyncio.get_running_loop().create_future()
        existing.set_result(old)
        binding = module.HermesBinding.__new__(module.HermesBinding)
        binding.hosts, binding.host_locks = {"native": ("/workspace", existing)}, {}
        binding.closed, binding.closing, binding.finalizing, binding.monitors, binding.states = False, False, set(), {}, {}
        binding.profile, binding.command, binding.env = "isolated", [], {}
        binding.sdk = SimpleNamespace(XsmHost=SimpleNamespace(open=open_host))
        with self.assertRaisesRegex(RuntimeError, "outcome unknown"):
            await binding._call("native", "/workspace", "xsm_send", {})
        self.assertEqual(calls, ["xsm_send"])
        self.assertEqual(opens, [])
        result = await binding._call("native", "/workspace", "xsm_inbox", {})
        self.assertEqual(result, {"recovered": True})
        self.assertEqual(calls, ["xsm_send", "xsm_inbox"])
        self.assertEqual(len(opens), 1)
        self.assertTrue(old.closed)


    async def test_monitor_backs_off_transient_failures_and_restores_activity(self):
        attempts, ready = [], asyncio.Event()
        async def close():
            pass
        async def update(state):
            self.assertEqual(state, "busy")
            ready.set()
        old = SimpleNamespace(failure=RuntimeError("lost transport"), closed=False, close=close)
        new = SimpleNamespace(failure=None, closed=False, update=update, close=close)
        async def open_host(**kwargs):
            attempts.append(asyncio.get_running_loop().time())
            if len(attempts) < 3:
                raise RuntimeError("temporary transport failure")
            return new
        pending = asyncio.get_running_loop().create_future()
        pending.set_result(old)
        binding = module.HermesBinding.__new__(module.HermesBinding)
        binding.hosts, binding.host_locks = {"native": ("/workspace", pending)}, {}
        binding.closed, binding.closing, binding.finalizing, binding.monitors = False, False, set(), {}
        binding.states = {"native": "busy"}
        binding.profile, binding.command, binding.env = "isolated", [], {}
        binding.sdk = SimpleNamespace(TransportError=RuntimeError, XsmHost=SimpleNamespace(open=open_host))
        task = asyncio.create_task(binding._monitor("native", "/workspace"))
        binding.monitors["native"] = task
        try:
            await asyncio.wait_for(ready.wait(), 4)
            self.assertEqual(len(attempts), 3)
            self.assertGreaterEqual(attempts[1] - attempts[0], .45)
            self.assertGreaterEqual(attempts[2] - attempts[1], .95)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


    async def test_slow_registration_does_not_block_another_native_conversation(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def close():
            pass
        async def open_host(**kwargs):
            if kwargs['conversation'] == 'slow':
                entered.set()
                await release.wait()
            return SimpleNamespace(close=close)
        binding = module.HermesBinding.__new__(module.HermesBinding)
        binding.hosts, binding.host_locks = {}, {}
        binding.closed, binding.closing, binding.finalizing, binding.monitors, binding.states = False, False, set(), {}, {}
        binding.profile, binding.command, binding.env = 'isolated', [], {}
        binding.sdk = SimpleNamespace(XsmHost=SimpleNamespace(open=open_host))
        existing = await binding._host('fast', '/workspace')
        slow = asyncio.create_task(binding._host('slow', '/workspace'))
        await entered.wait()
        fast = asyncio.create_task(binding._host('fast', '/workspace'))
        try:
            self.assertIs(await asyncio.wait_for(asyncio.shield(fast), .2), existing)
            await asyncio.wait_for(binding._host('another', '/workspace'), .2)
            self.assertFalse(slow.done())
        finally:
            release.set()
            await asyncio.gather(slow, fast, return_exceptions=True)
            tasks = list(binding.monitors.values())
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


from tests.test_xsm import TempState
from unittest import mock
import json
import os
import sys


class HermesRegistrationTest(TempState):
    def test_native_wake_requires_explicit_context_and_native_permission(self):
        constants = SimpleNamespace(get_hermes_home=lambda: Path(self.user_home, 'hermes'))
        for config in ({'native_wake': True},
                       {'native_wake': True, 'native_context': True},
                       {'native_wake': True, 'native_context': True, 'allow_gateway_injection': True},
                       {'native_wake': True, 'allow_gateway_injection': True},
                       {'native_wake': 'true'}):
            with self.subTest(config=config), mock.patch.dict(sys.modules, hermes_constants=constants):
                context = self.context()
                context.get_config = lambda name, default=None: config.get(name, default)
                with self.assertRaises(ValueError):
                    module.HermesBinding(context)

    def test_native_wake_uses_native_permission_outside_plugin_settings(self):
        constants = SimpleNamespace(get_hermes_home=lambda: Path(self.user_home, 'hermes'))
        context = self.context()
        context.get_config = lambda name, default=None: True if name in ('native_context', 'native_wake') else default
        context._gateway_injection_allowed = lambda: True
        with mock.patch.dict(sys.modules, hermes_constants=constants):
            binding = module.HermesBinding(context)
        try:
            self.assertTrue(binding.native_wake)
            self.assertIsNotNone(binding.native_context)
        finally:
            binding.close()

    def context(self):
        self.tools, self.hooks, self.unload = {}, {}, []
        return SimpleNamespace(
            on_unload=self.unload.append,
            register_tool=lambda **tool: self.tools.__setitem__(tool["name"], tool),
            register_hook=lambda name, callback: self.hooks.__setitem__(name, callback),
            session_cwd=lambda: self.user_home)

    def test_pinned_command_and_environment_reach_describe_and_tool_processes(self):
        marker = Path(self.tmp, "backend-starts")
        root = Path(__file__).resolve().parents[1]
        boot = ("import os,pathlib,runpy,sys;"
                "p=pathlib.Path(os.environ['XSM_HERMES_TEST_MARKER']);"
                "p.open('a').write('start\\n');"
                "sys.path.insert(0,sys.argv.pop(1));"
                "runpy.run_module('xsm',run_name='__main__')")
        command = [sys.executable, "-B", "-c", boot, str(root), "protocol", "serve", "--stdio"]
        env = {key: os.environ[key] for key in ("PATH", "LANG", "TMPDIR") if key in os.environ}
        env.update(HOME=self.user_home, XSM_HOME=self.tmp, XSM_HERMES_TEST_MARKER=str(marker))
        constants = SimpleNamespace(get_hermes_home=lambda: Path(self.user_home, "hermes"))
        with mock.patch.dict(sys.modules, hermes_constants=constants):
            binding = module.register(self.context(), command=command, env=env)
        try:
            self.assertEqual(len(self.tools), 22)
            self.assertEqual(len(self.hooks), 9)
            self.assertIn('pre_llm_call', self.hooks)
            self.assertIn('pre_api_request', self.hooks)
            self.assertEqual(marker.read_text().splitlines(), ["start"])
            result = json.loads(self.tools["xsm_inbox"]["handler"]({}, session_id="pinned-native"))
            self.assertIsInstance(result, dict)
            self.assertEqual(marker.read_text().splitlines(), ["start", "start"])
            self.assertEqual(binding.command, command)
            self.assertEqual(len(binding.hosts), 1)
        finally:
            binding.close()
        self.assertFalse(binding.thread.is_alive())

    def test_registration_failure_stops_coordinator(self):
        constants = SimpleNamespace(get_hermes_home=lambda: Path(self.user_home, "hermes"))
        with mock.patch.dict(sys.modules, hermes_constants=constants):
            with self.assertRaisesRegex(Exception, "peer closed stdout"):
                module.register(self.context(), command=[sys.executable, "-c", "raise SystemExit(7)"])
        self.assertEqual(len(self.unload), 1)
        binding = self.unload[0].__self__
        self.assertTrue(binding.closed)
        self.assertFalse(binding.thread.is_alive())

    def test_next_native_call_recovers_dead_backend_without_inheriting_claim(self):
        constants = SimpleNamespace(get_hermes_home=lambda: Path(self.user_home, 'hermes'))
        with mock.patch.dict(sys.modules, hermes_constants=constants):
            binding = module.register(self.context(), env={key: os.environ[key] for key in
                ('PATH', 'LANG', 'TMPDIR', 'HOME', 'XSM_HOME') if key in os.environ})
        def invoke(sid, operation, arguments=None):
            return json.loads(self.tools[operation]['handler'](arguments or {}, session_id=sid))
        async def host(sid):
            return await binding.hosts[sid][1]
        async def crash(value):
            value.client.process.kill()
            await value.client.process.wait()
            for _ in range(100):
                if value.failure is not None:
                    return
                await asyncio.sleep(.01)
            raise AssertionError('SDK did not observe dead backend')
        try:
            invoke('sender', 'xsm_inbox')
            invoke('receiver', 'xsm_inbox')
            before = binding._run(host('receiver'))
            invoke('sender', 'xsm_send', {'target': 'ref:' + before.session['ref'], 'text': 'survive backend death', 'wait': 0})
            original = invoke('receiver', 'xsm_inbox')['claims'][0]
            binding._run(crash(before))
            recovered = invoke('receiver', 'xsm_inbox')
            after = binding._run(host('receiver'))
            self.assertIsNot(after, before)
            self.assertEqual(after.session['ref'], before.session['ref'])
            self.assertNotEqual(after.session['generation'], before.session['generation'])
            self.assertNotEqual(after.client.process.pid, before.client.process.pid)
            self.assertEqual(recovered['claims'][0]['id'], original['id'])
            self.assertNotEqual(recovered['claims'][0]['token'], original['token'])
            with self.assertRaises(Exception) as refused:
                invoke('receiver', 'xsm_ack', {'tokens': [original['token']]})
            self.assertEqual(refused.exception.code, -32602)
            self.assertEqual(invoke('receiver', 'xsm_ack', {'tokens': [recovered['claims'][0]['token']]})['acked'], [original['id']])
        finally:
            binding.close()
        self.assertFalse(binding.thread.is_alive())

    def test_registered_backend_reconnects_without_native_call_and_restores_state(self):
        constants = SimpleNamespace(get_hermes_home=lambda: Path(self.user_home, 'hermes'))
        with mock.patch.dict(sys.modules, hermes_constants=constants):
            binding = module.register(self.context(), env={key: os.environ[key] for key in
                ('PATH', 'LANG', 'TMPDIR', 'HOME', 'XSM_HOME') if key in os.environ})
        async def crash_and_wait():
            before = await binding.hosts['automatic'][1]
            before.client.process.kill()
            await before.client.process.wait()
            for _ in range(300):
                pair = binding.hosts.get('automatic')
                if pair and pair[1].done():
                    current = pair[1].result()
                    rows = [json.loads(path.read_text()) for path in Path(self.tmp, 'sessions').glob('*.json')]
                    busy = any(row.get('pid') == current.client.process.pid and row.get('activity') == 'busy' for row in rows)
                    if current is not before and busy:
                        return before, current
                await asyncio.sleep(.01)
            raise AssertionError('no automatic registration')
        try:
            binding.start(session_id='automatic')
            before, after = binding._run(crash_and_wait())
            self.assertEqual(before.session['ref'], after.session['ref'])
            self.assertNotEqual(before.session['generation'], after.session['generation'])
            self.assertNotEqual(before.client.process.pid, after.client.process.pid)
            binding.finalize(session_id='automatic')
            async def wait():
                await asyncio.sleep(.4)
                return list(binding.hosts), list(binding.monitors)
            self.assertEqual(binding._run(wait()), ([], []))
        finally:
            binding.close()
        self.assertFalse(binding.thread.is_alive())


    def test_unload_cancels_backend_open_before_stopping_loop(self):
        import concurrent.futures
        import threading
        constants = SimpleNamespace(get_hermes_home=lambda: Path(self.user_home, 'hermes'))
        with mock.patch.dict(sys.modules, hermes_constants=constants):
            binding = module.HermesBinding(self.context(), env={key: os.environ[key] for key in
                ('PATH', 'LANG', 'TMPDIR', 'HOME', 'XSM_HOME') if key in os.environ})
        entered = threading.Event()
        release = binding._run(self.make_event())
        async def close():
            pass
        async def blocked(**kwargs):
            entered.set()
            await release.wait()
            return SimpleNamespace(close=close)
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        stopping = None
        try:
            with mock.patch.object(binding.sdk.XsmHost, 'open', new=blocked):
                opening = asyncio.run_coroutine_threadsafe(binding._host('pending', self.user_home), binding.loop)
                self.assertTrue(entered.wait(2))
                stopping = pool.submit(binding.close)
                try:
                    stopping.result(timeout=2)
                finally:
                    if not binding.loop.is_closed():
                        binding.loop.call_soon_threadsafe(release.set)
                    stopping.result(timeout=3)
                self.assertTrue(opening.cancelled())
                self.assertFalse(binding.thread.is_alive())
        finally:
            if not binding.loop.is_closed():
                binding.loop.call_soon_threadsafe(release.set)
                binding.close()
            pool.shutdown(wait=True)

    async def make_event(self):
        return asyncio.Event()


class HermesNativeQuestionsTest(TempState):
    def setUp(self):
        super().setUp()
        context = HermesRegistrationTest.context(self)
        context.get_config = lambda key, default=None: True if key == 'native_questions' else default
        constants = SimpleNamespace(get_hermes_home=lambda: Path(self.user_home, 'hermes'))
        environment = {key: os.environ[key] for key in ('PATH','LANG','TMPDIR','HOME','XSM_HOME') if key in os.environ}
        with mock.patch.dict(sys.modules, hermes_constants=constants):
            self.binding = module.register(context, env=environment)
        self.args = {'question':'Choose','options':['blue','green']}

    def tearDown(self):
        self.binding.close()
        super().tearDown()

    def invoke(self, operation='xsm_decide', arguments=None, sid='native-ui-a'):
        return json.loads(self.tools[operation]['handler'](self.args if arguments is None else arguments, session_id=sid))

    def native_reply(self, pending, selected='Value 1', sid='native-ui-a', call_id='native-clarify-1', outcome='submitted', rewrite=None, turn_id='turn-fixture', api_request_id='request-fixture'):
        question = json.loads(json.dumps(pending['native_ui']['arguments']['questions'][0]))
        if rewrite:
            rewrite(question)
        response = {'question':question['question'],'choices_offered':question.get('choices'),
                    'status':'answered' if selected is not None else 'unanswered','user_response':selected}
        self.hooks['post_tool_call'](tool_name='clarify', args={'questions':[question]},
            result=json.dumps({'outcome':outcome,'responses':[response]}), session_id=sid, tool_call_id=call_id,
            turn_id=turn_id, api_request_id=api_request_id)

    def status(self, pending, sid='native-ui-a'):
        return self.invoke('xsm_decision_status', {'id':pending['decision_id']}, sid=sid)

    def test_native_hook_answer_requires_original_operation_retry(self):
        pending = self.invoke()
        self.assertEqual(pending['status'], 'waiting-for-user')
        self.assertEqual(set(pending['native_ui']), {'tool','arguments','after'})
        self.assertEqual(self.status(pending)['status'], 'pending')
        self.native_reply(pending)
        self.assertEqual(self.status(pending)['status'], 'answered')
        self.assertIn('your user answered: blue', self.invoke()['text'])

    def test_other_session_or_changed_native_form_cannot_answer(self):
        pending = self.invoke()
        self.native_reply(pending, sid='native-ui-b')
        self.assertNotIn('native-ui-b', self.binding.hosts)
        self.invoke(sid='native-ui-b')
        self.native_reply(pending, sid='native-ui-b', call_id='foreign-active-session')
        self.native_reply(pending, call_id='rewritten-body', rewrite=lambda q:q.update(question=q['question']+' changed'))
        self.native_reply(pending, call_id='rewritten-choices', rewrite=lambda q:q.update(choices=list(reversed(q['choices']))))
        self.assertIsNone(self.status(pending)['answer'])
        self.native_reply(pending, call_id='genuine')
        self.assertEqual(self.status(pending)['status'], 'answered')

    def test_reset_fences_late_answer_even_for_identical_question(self):
        old = self.invoke()
        self.binding.finalize(session_id='native-ui-a')
        fresh = self.invoke()
        self.assertNotEqual(fresh['question_id'], old['question_id'])
        self.native_reply(old, call_id='late-old')
        self.assertIsNone(self.status(fresh)['answer'])
        self.native_reply(fresh, call_id='fresh')
        self.assertEqual(self.status(fresh)['status'], 'answered')

    def test_native_occurrence_cannot_answer_a_second_question(self):
        first = self.invoke()
        self.native_reply(first, call_id='single-use')
        self.invoke()
        changed = dict(self.args, decision_key='second-distinct-question')
        second = self.invoke(arguments=changed)
        self.native_reply(second, call_id='single-use')
        self.assertIsNone(self.status(second)['answer'])
        self.native_reply(second, call_id='second-occurrence')
        self.assertEqual(self.status(second)['status'], 'answered')

    def test_native_pages_preserve_all_canonical_values(self):
        values = ['first','second','third','fourth','  '+('long value '*1000)+'  ']
        canonical = [value.strip() for value in values]
        arguments = {'question':'Paged choice','options':values}
        pending = self.invoke(arguments=arguments)
        views = [pending['native_ui']['arguments']['questions'][0]['question']]
        self.native_reply(pending, selected='Next choices', call_id='page-next-1')
        pending = self.invoke(arguments=arguments)
        views.append(pending['native_ui']['arguments']['questions'][0]['question'])
        self.native_reply(pending, selected='Next choices', call_id='page-next-2')
        pending = self.invoke(arguments=arguments)
        views.append(pending['native_ui']['arguments']['questions'][0]['question'])
        for value in canonical:
            self.assertIn(json.dumps(value, ensure_ascii=False), '\n'.join(views))
        self.native_reply(pending, selected='Value 5', call_id='final-value')
        applied = self.invoke(arguments=arguments)
        self.assertIn(canonical[-1], applied['text'])

    def test_native_cancel_does_not_become_an_approval(self):
        pending = self.invoke()
        self.native_reply(pending, selected=None, outcome='cancelled')
        status = self.status(pending)
        self.assertNotEqual(status['status'], 'answered')
        self.assertNotIn('blue', json.dumps(status.get('answer')))

    def test_native_free_text_uses_actual_observed_value(self):
        arguments = {'question':'Free text  \n '}
        pending = self.invoke(arguments=arguments)
        self.assertNotIn('choices', pending['native_ui']['arguments']['questions'][0])
        self.native_reply(pending, selected='actual free answer')
        self.assertIn('your user answered: actual free answer', self.invoke(arguments=arguments)['text'])

    def test_duplicate_native_questions_do_not_select_one_conflicting_answer(self):
        pending = self.invoke()
        question = pending['native_ui']['arguments']['questions'][0]
        responses = [{'question':question['question'],'choices_offered':question['choices'],
                      'status':'answered','user_response':value} for value in ('Value 1','Value 2')]
        self.hooks['post_tool_call'](tool_name='clarify', args={'questions':[question,question]},
            result=json.dumps({'outcome':'submitted','responses':responses}), session_id='native-ui-a',
            tool_call_id='duplicated-native-question', turn_id='turn-fixture', api_request_id='request-fixture')
        self.assertIsNone(self.status(pending)['answer'])
        fresh = self.invoke()
        self.assertNotEqual(fresh['native_ui'], pending['native_ui'])
        self.native_reply(fresh, call_id='fresh-single-question')
        self.assertEqual(self.status(fresh)['status'], 'answered')

    def test_distinct_native_turn_disambiguates_reused_provider_call_id(self):
        first = self.invoke()
        self.native_reply(first, call_id='provider-call-id')
        self.invoke()
        second = self.invoke(arguments=dict(self.args, decision_key='later-turn'))
        self.native_reply(second, call_id='provider-call-id', turn_id='later-native-turn', api_request_id='later-request')
        self.assertEqual(self.status(second)['status'], 'answered')

    def test_native_profile_context_cannot_answer_another_profile_question(self):
        pending = self.invoke()
        current = self.binding.profile_current
        self.binding.profile_current = lambda: Path(self.user_home, 'other-hermes-profile')
        try:
            self.native_reply(pending, call_id='foreign-profile-native')
        finally:
            self.binding.profile_current = current
        self.assertIsNone(self.status(pending)['answer'])
        self.native_reply(pending, call_id='genuine-profile-native')
        self.assertEqual(self.status(pending)['status'], 'answered')

    def test_native_unavailable_is_not_a_user_answer(self):
        pending = self.invoke()
        self.hooks['post_tool_call'](tool_name='clarify', args=pending['native_ui']['arguments'],
            result=json.dumps({'error':'Native UI callback unavailable'}), session_id='native-ui-a',
            tool_call_id='unavailable-native')
        self.assertIsNone(self.status(pending)['answer'])

    def test_native_typed_canonical_value_is_valid_but_other_text_is_not(self):
        pending = self.invoke()
        self.native_reply(pending, selected='not-an-option', call_id='invalid-typed-value')
        self.assertIsNone(self.status(pending)['answer'])
        fresh = self.invoke()
        self.native_reply(fresh, selected='green', call_id='typed-canonical-value')
        self.assertIn('your user answered: green', self.invoke()['text'])
        literal = {'question':'A literal navigation name','options':['Next choices']}
        pending = self.invoke(arguments=literal)
        self.native_reply(pending, selected='Next choices', call_id='literal-navigation-value')
        self.assertIn('your user answered: Next choices', self.invoke(arguments=literal)['text'])
