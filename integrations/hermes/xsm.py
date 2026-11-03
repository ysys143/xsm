"""Hermes 0.22.5 pull tools and opt-in native clarify observations."""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import re
import secrets
import subprocess
from pathlib import Path
import sys
import threading


def _sdk(root):
    directory = root / "clients/python"
    name = "_xsm_sdk_" + hashlib.sha256(str(directory.resolve()).encode()).hexdigest()[:24]
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, directory / "__init__.py",
                                                     submodule_search_locations=[str(directory)])
        package = importlib.util.module_from_spec(spec)
        sys.modules[name] = package
        try:
            spec.loader.exec_module(package)
        except BaseException:
            sys.modules.pop(name, None)
            raise
    return __import__(name + ".xsm_host", fromlist=["XsmHost"])


def _component_lease(root, python, env=None):
    root = root.resolve()
    if root.parent.name != "runtime" or not re.fullmatch(r"[0-9a-f]{12}", root.name):
        return lambda: None
    environment = dict(os.environ if env is None else env, XSM_HOME=str(root.parent.parent))
    code = ("import json,sys;sys.path.insert(0,sys.argv[1]);"
            "from xsm.component_leases import hold,release;"
            "record=json.load(sys.stdin);"
            "print(json.dumps(hold('hermes-plugin',int(sys.argv[2])) if record is None "
            "else release(record,int(sys.argv[2]))))")
    def request(record):
        result = subprocess.run([python, "-B", "-c", code, str(root), str(os.getpid())],
            input=json.dumps(record), capture_output=True, text=True, env=environment, timeout=10)
        if result.returncode:
            raise RuntimeError("Hermes component lease failed: " + result.stderr[-2000:])
        return json.loads(result.stdout)
    record = request(None)
    if (record.get("root") != str(root) or record.get("pid") != os.getpid() or
            record.get("component") != "hermes-plugin"):
        raise RuntimeError("Hermes component lease identity differs")
    return lambda: request(record)


class NativeQuestions:
    """Correlate native clarify observations with one live host presentation.

    The native display has a correlation heading and a verbatim canonical body.
    Only the body is attested as `displayed` to the protocol. Choice legends map
    short native UI labels to the original values without truncating those values.
    """
    def __init__(self):
        self.pending = {}
        self.used = set()

    def key(self, sid, host, question_id):
        return sid, host.session['generation'], question_id

    async def present(self, sid, host, event, cancelled):
        params = event['params']
        if params['session'] != host.session['session']:
            raise RuntimeError('native question belongs to another participation')
        schema = params['requestedSchema']
        props = schema.get('properties', {})
        if set(props) != {'answer'} or props['answer'].get('type') != 'string':
            raise RuntimeError('native questions require one string answer')
        choices = props['answer'].get('enum')
        if choices is not None and (not isinstance(choices, list) or not choices or
                any(not isinstance(value, str) for value in choices)):
            raise RuntimeError('invalid native question choices')
        key = self.key(sid, host, params['questionId'])
        future = asyncio.get_running_loop().create_future()
        state = dict(host=host, params=params, cancelled=cancelled, future=future,
                     choices=choices, page=0, nonce=secrets.token_hex(8))
        self.pending[key] = state
        try:
            return await future
        finally:
            if self.pending.get(key) is state:
                self.pending.pop(key, None)

    def render(self, state):
        params = state['params']
        heading = '[XSM question %s / %s]' % (params['questionId'], state['nonce'])
        question = heading + '\n\n' + params['question']
        choices = state['choices']
        if choices is None:
            return {'question': question + '\n\nEnter your answer below.'}, {}
        start = state['page'] * 2
        values = choices[start:start+2]
        labels = {'Value %d' % (start+index+1): value for index,value in enumerate(values)}
        question += '\n\nValues on this page:\n' + '\n'.join(
            '%s: %s' % (label, json.dumps(value, ensure_ascii=False)) for label,value in labels.items())
        offered = list(labels)
        if start:
            offered.append('Previous choices')
        if start + 2 < len(choices):
            offered.append('Next choices')
        return {'question': question, 'choices': offered}, labels

    async def describe(self, sid, host, question_id):
        key = self.key(sid, host, question_id)
        deadline = asyncio.get_running_loop().time() + 10
        while key not in self.pending:
            if host.closed or host.failure or asyncio.get_running_loop().time() >= deadline:
                raise RuntimeError('native question presentation unavailable')
            await asyncio.sleep(.01)
        state = self.pending[key]
        if state['cancelled'].is_set() or state['future'].done():
            raise RuntimeError('native question presentation ended')
        question, _labels = self.render(state)
        return {'tool':'clarify','arguments':{'questions':[question]},
                'after':'After native clarify finishes, retry the original XSM operation with identical arguments.'}

    def observe(self, sid, host, call_id, arguments, result, *, turn_id='', api_request_id=''):
        ids = (call_id, turn_id, api_request_id)
        if (any(not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 32 for c in value) for value in ids)
                or not call_id.strip() or not isinstance(arguments, dict)):
            return []
        try:
            value = json.loads(result) if isinstance(result, str) else result
        except (ValueError, TypeError):
            return []
        questions = arguments.get('questions')
        if not isinstance(value, dict) or not isinstance(questions, list):
            return []
        responses = value.get('responses')
        resolved = []
        for index, raw in enumerate(questions):
            if not isinstance(raw, dict) or raw.get('multi_select', False) is not False:
                continue
            for key, state in list(self.pending.items()):
                if key[0] != sid or state['host'] is not host or state['cancelled'].is_set() or state['future'].done():
                    continue
                expected, labels = self.render(state)
                if raw.get('question') != expected['question'] or raw.get('choices') != expected.get('choices'):
                    continue
                base = (sid, key[1], turn_id, api_request_id, call_id)
                matching = [i for i,q in enumerate(questions) if isinstance(q, dict) and q.get('question') == expected['question']]
                if len(matching) != 1:
                    self.used.update(base + (i,) for i in matching)
                    state['nonce'] = secrets.token_hex(8)
                    continue
                receipt = base + (index,)
                if receipt in self.used:
                    continue
                if value.get('error') is not None:
                    self.used.add(receipt)
                    state['future'].set_exception(RuntimeError('native clarify is unavailable'))
                    resolved.append(key[2]); continue
                response = responses[index] if isinstance(responses, list) and len(responses) == len(questions) else None
                if (not isinstance(response, dict) or response.get('question') != expected['question'] or
                        response.get('choices_offered') != expected.get('choices')):
                    continue
                self.used.add(receipt)
                outcome = value.get('outcome')
                source = 'hermes-clarify-' + hashlib.sha256(json.dumps(receipt).encode()).hexdigest()
                if outcome == 'cancelled':
                    answer = {'displayed':state['params']['question'],'source_id':source,'action':'cancel'}
                elif outcome in ('timed_out','undelivered'):
                    state['future'].set_exception(RuntimeError('native question was not answered'))
                    resolved.append(key[2]); continue
                elif outcome == 'submitted' and response.get('status') in ('skipped','unanswered'):
                    state['future'].set_exception(RuntimeError('native question was not answered'))
                    resolved.append(key[2]); continue
                elif outcome == 'submitted' and response.get('status') == 'answered' and isinstance(response.get('user_response'), str):
                    selected = response['user_response']
                    if (state['choices'] is not None and selected in ('Previous choices','Next choices')
                            and selected in expected['choices']):
                        state['page'] += -1 if selected == 'Previous choices' else 1
                        state['nonce'] = secrets.token_hex(8)
                        continue
                    if state['choices'] is not None:
                        if selected in labels:
                            selected = labels[selected]
                        elif selected not in state['choices']:
                            state['nonce'] = secrets.token_hex(8)
                            continue
                    answer = {'displayed':state['params']['question'],'source_id':source,'answer':selected}
                else:
                    continue
                state['future'].set_result(answer)
                resolved.append(key[2])
        return resolved

    def close_host(self, sid, host):
        for key,state in list(self.pending.items()):
            if key[0] == sid and state['host'] is host:
                state['future'].cancel()


class NativeContext:
    """Stage a natural-turn context; admit only after the native API hook sees it."""
    def __init__(self, render):
        self.render = render
        self.pending = {}

    async def begin(self, sid, host, turn_id):
        if not isinstance(turn_id, str) or not turn_id:
            raise RuntimeError('native turn identity unavailable')
        await self.close_host(sid, host)
        loop = asyncio.get_running_loop()
        key = (sid, id(host))
        state = dict(host=host, turn=turn_id, staged=asyncio.Event(), accepted=loop.create_future(),
                     nonce=secrets.token_hex(16), text=None)
        self.pending[key] = state
        state['task'] = asyncio.create_task(host.natural_boundary())
        staged = asyncio.create_task(state['staged'].wait())
        try:
            done, _ = await asyncio.wait((state['task'], staged), timeout=10,
                                         return_when=asyncio.FIRST_COMPLETED)
            if not done:
                raise RuntimeError('native context staging timed out')
            if state['staged'].is_set():
                return state['text']
            await state['task']
            self.pending.pop(key, None)
            return ''
        except BaseException:
            await self.close_host(sid, host)
            raise
        finally:
            staged.cancel()
            await asyncio.gather(staged, return_exceptions=True)

    async def deliver(self, sid, host, packet, options):
        state = self.pending.get((sid, id(host)))
        if state is None or state['host'] is not host or state['accepted'].done():
            raise RuntimeError('native natural-turn context is not open')
        if options['wake']:
            raise RuntimeError('native context handoff cannot wake a turn')
        state['text'] = '[XSM peer context %s]\n%s' % (state['nonce'], self.render(packet))
        state['staged'].set()
        return await asyncio.wait_for(asyncio.shield(state['accepted']),
                                      max(1, options['lease_seconds'] - 1))

    async def observe(self, sid, host, turn_id, api_request_id, messages):
        state = self.pending.get((sid, id(host)))
        if (state is None or state['host'] is not host or state['turn'] != turn_id
                or not isinstance(api_request_id, str) or not api_request_id or state['accepted'].done()
                or not isinstance(messages, list) or state['text'] is None):
            return False
        observed = False
        for message in messages:
            if not isinstance(message, dict) or message.get('role') != 'user':
                continue
            content = message.get('content')
            texts = [content] if isinstance(content, str) else [part.get('text') for part in content
                if isinstance(part, dict) and part.get('type') in ('text','input_text')] if isinstance(content,list) else []
            if any(isinstance(text, str) and state['text'] in text for text in texts):
                observed = True
                break
        if not observed:
            return False
        state['accepted'].set_result(True)
        try:
            await state['task']
        finally:
            if self.pending.get((sid,id(host))) is state:
                self.pending.pop((sid,id(host)),None)
        return True

    async def close_host(self, sid, host):
        state = self.pending.pop((sid, id(host)), None)
        if state is not None:
            state['accepted'].cancel()
            # Let an in-flight inbox RPC return so the SDK can release exact
            # newly acquired claims instead of orphaning an unseen response.
            try:
                await asyncio.wait_for(asyncio.shield(state['task']), 10)
            except asyncio.TimeoutError:
                state['task'].cancel()
                await asyncio.gather(state['task'], return_exceptions=True)
            except BaseException:
                pass


class NativeGateway:
    """One native conversation and authority generation, never a route alias."""
    def __init__(self, context, profile, sid):
        from gateway.session_authorities import authority_for_home
        from gateway.session_context import get_session_env
        from hermes_cli.plugin_session import session_key
        manager = getattr(context, '_manager', None)
        registered = getattr(manager, '_gateway_message_injector', None)
        if (manager is None or str(Path(manager.home_path).resolve()) != profile or
                not registered or not context._gateway_injection_allowed()):
            raise RuntimeError('native gateway injection is not authorized for this profile')
        self.context, self.profile, self.sid = context, profile, sid
        self.runner, self.route = registered[0], session_key()
        if not self.route or get_session_env('HERMES_SESSION_ID', '') != sid:
            raise RuntimeError('native gateway conversation context is unavailable')
        self.loop = getattr(self.runner, '_gateway_loop', None)
        if self.loop is None or not self.loop.is_running():
            raise RuntimeError('native gateway loop is unavailable')
        self.authority = authority_for_home(self.runner, Path(profile))
        if self.authority is None:
            raise RuntimeError('native profile authority is unavailable')
        self.epoch = self.authority.epoch

    def same_target(self, other):
        return (self.runner is other.runner and self.authority is other.authority and
                (self.profile, self.sid, self.route, self.epoch) ==
                (other.profile, other.sid, other.route, other.epoch))

    def _validate(self):
        from gateway.config import Platform
        from gateway.session_authorities import authority_for_home
        registered = getattr(self.context._manager, '_gateway_message_injector', None)
        if (not registered or registered[0] is not self.runner or
                getattr(self.runner, '_gateway_loop', None) is not self.loop or
                str(Path(self.context._manager.home_path).resolve()) != self.profile or
                not self.context._gateway_injection_allowed() or
                authority_for_home(self.runner, Path(self.profile)) is not self.authority or
                self.authority.epoch != self.epoch or self.authority.retiring or
                getattr(self.authority, 'retired', False) or
                not self.runner._running or self.runner._draining):
            raise RuntimeError('native gateway owner or permission changed')
        entry = self.runner.session_store.lookup_by_session_key(self.route)
        if entry is None or entry.suspended or entry.session_id != self.sid:
            raise RuntimeError('native gateway conversation changed')
        source = self.runner._restored_source(entry)
        if source.platform != Platform.LOCAL:
            raise RuntimeError('native messaging queue delivery is not connected')
        live = self.runner._plugin_local_session(source, self.route,
            plugin_home=Path(self.profile), plugin_id='xsm')
        if live is None:
            raise RuntimeError('native gateway local session is unavailable')
        return live.source, self.runner._adapter_for_source(live.source)

    async def _execute(self, text=None, identity=None):
        from gateway.run import _profile_runtime_scope
        with _profile_runtime_scope(Path(self.profile), hydrate_secrets=False):
            source, adapter = self._validate()
            if text is None:
                return True
            from gateway.platforms.event import MessageEvent, MessageType
            from hermes_state_runtime import get_session_admission
            author = {'id': 'bot:xsm-peer', 'name': 'XSM peer', 'is_bot': True}
            event = MessageEvent(text=text, message_type=MessageType.TEXT, source=source,
                internal=True, allow_gateway_control=False, message_id=identity,
                metadata={'gateway_session_key': self.route, 'gateway_session_id': self.sid,
                          'turn_author': author})
            receipt = await self.authority.admit_automation(adapter, event, identity)
            row = get_session_admission(self.authority.db, admission_id=receipt.admission_id)
            descriptor = row['payload'].get('local_automation_v1', {}) if row else {}
            if (not row or receipt.ref.profile_id != self.authority.profile_id or
                    receipt.authority_epoch != self.epoch or
                    row['target_session_id'] != receipt.ref.session_id or
                    row['principal_id'] != 'automation:' + self.route or row['request_id'] != identity or
                    row['payload']['text'] != text or descriptor.get('target') != self.sid or
                    descriptor.get('turn_author') != author):
                raise RuntimeError('native gateway admission receipt differs')
            return True

    async def prepare(self):
        return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(self._execute(), self.loop))

    async def deliver(self, packet, options, render):
        if options['cancelled'].is_set():
            raise RuntimeError('native gateway participation closed')
        identity = json.dumps(['plugin', 'xsm', self.route,
            hashlib.sha256(json.dumps(sorted((claim['id'], claim['token'])
                for claim in packet['claims'])).encode()).hexdigest()], separators=(',', ':'))
        future = asyncio.wrap_future(asyncio.run_coroutine_threadsafe(
            self._execute(render(packet), identity), self.loop))
        return await asyncio.shield(future)


class HermesBinding:
    def __init__(self, context, *, command=None, env=None):
        from hermes_constants import get_hermes_home
        self.context = context
        self.root = Path(__file__).resolve().parents[2]
        self.profile = str(get_hermes_home().resolve())
        self.profile_current = get_hermes_home
        self.sdk = _sdk(self.root)
        self.command = command or [sys.executable, "-B", "-c",
            "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('xsm',run_name='__main__')",
            str(self.root), "protocol", "serve", "--stdio"]
        self.env = env
        get_config = getattr(context, 'get_config', None)
        native_questions = get_config('native_questions', False) if callable(get_config) else False
        if type(native_questions) is not bool:
            raise ValueError('native_questions must be a boolean')
        self.native_questions = NativeQuestions() if native_questions else None
        native_context = get_config('native_context', False) if callable(get_config) else False
        if type(native_context) is not bool:
            raise ValueError('native_context must be a boolean')
        self.native_context = NativeContext(self.sdk.render_inbox_packet) if native_context else None
        native_wake = get_config('native_wake', False) if callable(get_config) else False
        if type(native_wake) is not bool:
            raise ValueError('native_wake must be a boolean')
        native_permission = getattr(context, '_gateway_injection_allowed', None)
        if native_wake and (not native_context or not callable(native_permission) or native_permission() is not True):
            raise ValueError('native_wake requires native_context and allow_gateway_injection')
        self.native_wake = native_wake
        self.gateway_targets = {}
        self.hosts = {}
        self.host_locks = {}
        self.closed = False
        self.closing = False
        self.finalizing = set()
        self.monitors = {}
        self.states = {}
        self.parents = {}
        self.release_component = None
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, name="xsm-hermes", daemon=True)
        self.thread.start()

    def _run(self, coroutine):
        if self.closed:
            coroutine.close()
            raise RuntimeError("xsm Hermes binding closed")
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result()

    def _identity(self, session_id):
        if str(self.profile_current().resolve()) != self.profile:
            raise RuntimeError('native caller belongs to another Hermes profile')
        sid = str(session_id or "")
        if not sid:
            raise RuntimeError("native dispatcher session identity is missing")
        cwd = self.context.session_cwd()
        if not cwd or not Path(cwd).is_absolute() or not Path(cwd).is_dir():
            raise RuntimeError("native caller has no existing absolute workspace")
        if getattr(self, 'native_wake', False):
            target = NativeGateway(self.context, self.profile, sid)
            previous = self.gateway_targets.get(sid)
            if previous is not None and not previous.same_target(target):
                raise RuntimeError('native gateway target changed; finalize previous participation')
            self.gateway_targets.setdefault(sid, target)
        return sid, str(Path(cwd).resolve())

    def _host_lock(self, sid):
        return self.host_locks.setdefault(sid, asyncio.Lock())

    def _backend_environment(self):
        base = dict(os.environ if self.env is None else self.env)
        if self.env is None:
            from tools.environments.local import served_profile_child_env
            base = served_profile_child_env(base=base, target_home=self.profile, inherit_credentials=False)
        base.pop('XSM_WORKER', None)
        base.pop('XSM_OWNED_CONTROL_FD', None)
        base['HERMES_HOME'] = self.profile
        return base

    async def _host(self, sid, cwd, *, rebind=False):
        async with self._host_lock(sid):
            if self.closed or self.closing or sid in self.finalizing:
                raise RuntimeError("native participation is closing")
            if sid in self.hosts and self.hosts[sid][0] != cwd:
                if not rebind:
                    raise RuntimeError("native workspace changed; wait for the native session-start hook")
                monitor = self.monitors.pop(sid, None)
                if monitor and monitor is not asyncio.current_task():
                    monitor.cancel()
                    await asyncio.gather(monitor, return_exceptions=True)
                _, previous = self.hosts.pop(sid)
                await self._close_host(sid, await previous)
            if sid in self.hosts:
                _, previous = self.hosts[sid]
                existing = await previous
                if getattr(existing, "failure", None) is not None or getattr(existing, "closed", False):
                    # Replace participation without replaying a failed operation.
                    await self._close_host(sid, existing)
                    self.hosts.pop(sid)
            return await self._open_host(sid, cwd)

    async def _open_host(self, sid, cwd):
        if self.closed or self.closing or sid in self.finalizing:
            raise RuntimeError("native participation is closing")
        if sid not in self.hosts:
            async def opened():
                holder = {}
                ui = getattr(self, 'native_questions', None)
                async def present(event, cancelled):
                    return await ui.present(sid, holder['host'], event, cancelled)
                native_context = getattr(self, 'native_context', None)
                gateway = getattr(self, 'gateway_targets', {}).get(sid)
                if gateway is not None:
                    await gateway.prepare()
                async def deliver(packet, options):
                    if gateway is not None and options['wake']:
                        return await gateway.deliver(packet, options, self.sdk.render_inbox_packet)
                    return await native_context.deliver(sid, holder['host'], packet, options)
                delivery = {'deliver': deliver, 'automatic_delivery': gateway is not None} if native_context is not None else {}
                host = await self.sdk.XsmHost.open(runtime="hermes", profile=self.profile,
                    conversation=sid, cwd=cwd, command=self.command, env=self._backend_environment(),
                    parent_conversation=getattr(self, 'parents', {}).get(sid),
                    present=present if ui is not None else None, **delivery)
                holder['host'] = host
                return host
            pending = asyncio.create_task(opened())
            self.hosts[sid] = (cwd, pending)
            try:
                await pending
            except BaseException:
                if self.hosts.get(sid, (None, None))[1] is pending:
                    self.hosts.pop(sid, None)
                raise
        _, pending = self.hosts[sid]
        host = await pending
        if self.closed or self.closing or sid in self.finalizing:
            if self.hosts.get(sid, (None, None))[1] is pending:
                self.hosts.pop(sid, None)
            await self._close_host(sid, host)
            raise RuntimeError("native participation is closing")
        if not self.closing and sid not in self.finalizing and sid not in self.monitors:
            self.monitors[sid] = asyncio.create_task(self._monitor(sid, cwd))
        return host

    async def _close_host(self, sid, host):
        native_context = getattr(self, 'native_context', None)
        if native_context is not None:
            await native_context.close_host(sid, host)
        ui = getattr(self, 'native_questions', None)
        if ui is not None:
            ui.close_host(sid, host)
        await host.close()

    async def _monitor(self, sid, cwd):
        delay = .25
        try:
            while not self.closed and not self.closing and sid not in self.finalizing:
                await asyncio.sleep(delay)
                try:
                    pair = self.hosts.get(sid)
                    if pair:
                        if pair[0] != cwd:
                            return
                        if not pair[1].done():
                            continue
                        host = pair[1].result()
                        failure = getattr(host, "failure", None)
                        if failure is None:
                            delay = .25
                            continue
                        if not isinstance(failure, getattr(self.sdk, "TransportError", ())):
                            return
                    host = await self._host(sid, cwd)
                    await host.update(self.states.get(sid, "idle"))
                    delay = .25
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    print("xsm:", str(error), file=sys.stderr)
                    if not isinstance(error, getattr(self.sdk, "TransportError", ())):
                        return
                    delay = min(delay * 2, 5)
        finally:
            if self.monitors.get(sid) is asyncio.current_task():
                self.monitors.pop(sid, None)

    async def _call(self, sid, cwd, operation, args):
        host = await self._host(sid, cwd)
        ui = getattr(self, 'native_questions', None)
        if ui is None:
            return await host.call(operation, args)
        result = await host.call(operation, args, wait_for_decision=False)
        if result.get('status') == 'waiting-for-user':
            try:
                native = await ui.describe(sid, host, result['question_id'])
            except BaseException:
                try:
                    await host.abandon_deferred(result['question_id'])
                except Exception:
                    pass
                raise
            return dict(result, native_ui=native)
        return result

    def observe_question(self, tool_name='', args=None, result=None, session_id='', tool_call_id='', turn_id='', api_request_id='', **_native):
        if tool_name != 'clarify' or getattr(self, 'native_questions', None) is None or self.closed or self.closing:
            return
        if str(self.profile_current().resolve()) != self.profile:
            return
        async def observe():
            pair = self.hosts.get(session_id)
            if not pair or not pair[1].done() or session_id in self.finalizing:
                return
            host = pair[1].result()
            if host.closed or host.failure:
                return
            resolved = self.native_questions.observe(session_id, host, tool_call_id, args, result,
                turn_id=turn_id, api_request_id=api_request_id)
            for question_id in resolved:
                try:
                    await host.wait_decision(question_id)
                except Exception:
                    pass
        self._run(observe())

    def handler(self, operation):
        def call(args, *, session_id="", **_native):
            sid, cwd = self._identity(session_id)
            return json.dumps(self._run(self._call(sid, cwd, operation, args)), ensure_ascii=False)
        return call

    def before_model(self, session_id='', turn_id='', **_native):
        if getattr(self, 'native_context', None) is None or self.closed or self.closing:
            return None
        sid, cwd = self._identity(session_id)
        async def stage():
            host = await self._host(sid, cwd)
            return await self.native_context.begin(sid, host, turn_id)
        text = self._run(stage())
        return {'context': text} if text else None

    def observe_context(self, session_id='', turn_id='', api_request_id='', request_messages=None, **_native):
        if getattr(self, 'native_context', None) is None or self.closed or self.closing:
            return
        sid, _cwd = self._identity(session_id)
        async def observed():
            pair = self.hosts.get(sid)
            if pair and pair[1].done() and sid not in self.finalizing:
                host = pair[1].result()
                if not host.closed and not host.failure:
                    return await self.native_context.observe(sid, host, turn_id, api_request_id, request_messages)
        self._run(observed())

    def start(self, session_id="", **_native):
        sid, cwd = self._identity(session_id)
        async def update():
            self.states[sid] = "busy"
            await (await self._host(sid, cwd, rebind=True)).update("busy")
        self._run(update())

    def subagent_start(self, parent_session_id='', child_session_id='', **_native):
        if not parent_session_id or not child_session_id or parent_session_id == child_session_id:
            return
        async def remember():
            prior = self.parents.get(child_session_id)
            if prior not in (None, parent_session_id):
                raise RuntimeError('native child changed its parent conversation')
            self.parents[child_session_id] = parent_session_id
        self._run(remember())

    def settled(self, session_id="", **_native):
        async def update():
            if getattr(self,'native_context',None) is not None and session_id in self.hosts:
                await self.native_context.close_host(session_id, await self.hosts[session_id][1])
            if session_id in self.hosts or session_id in self.monitors:
                self.states[session_id] = "idle"
            if session_id in self.hosts:
                await (await self.hosts[session_id][1]).update("idle")
        self._run(update())

    def finalize(self, session_id="", **_native):
        async def close():
            self.finalizing.add(session_id)
            try:
                monitor = self.monitors.pop(session_id, None)
                if monitor:
                    monitor.cancel()
                    await asyncio.gather(monitor, return_exceptions=True)
                async with self._host_lock(session_id):
                    pair = self.hosts.pop(session_id, None)
                    self.states.pop(session_id, None)
                    if pair:
                        await self._close_host(session_id, await pair[1])
            finally:
                getattr(self, 'gateway_targets', {}).pop(session_id, None)
                self.finalizing.discard(session_id)
        self._run(close())

    def reset(self, old_session_id="", new_session_id="", **_native):
        if old_session_id and old_session_id != new_session_id:
            self.finalize(session_id=old_session_id)

    def _release_component(self):
        if self.release_component is not None:
            self.release_component()
            self.release_component = None

    def close(self):
        if self.closed:
            self._release_component()
            return
        async def shutdown():
            self.closing = True
            monitors = list(self.monitors.values())
            self.monitors.clear()
            for monitor in monitors:
                monitor.cancel()
            await asyncio.gather(*monitors, return_exceptions=True)
            for _, pending in list(self.hosts.values()):
                if not pending.done():
                    pending.cancel()
            for lock in list(self.host_locks.values()):
                async with lock:
                    pass
            pairs = list(self.hosts.items())
            self.hosts.clear()
            self.states.clear()
            hosts = await asyncio.gather(*(pair[1] for _sid,pair in pairs), return_exceptions=True)
            await asyncio.gather(*(self._close_host(sid, host) for (sid,_pair),host in zip(pairs,hosts)
                                  if not isinstance(host, BaseException)))
            getattr(self, 'gateway_targets', {}).clear()
        self._run(shutdown())
        self.closed = True
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=3)
        if self.thread.is_alive():
            raise RuntimeError("xsm Hermes coordinator thread did not stop")
        self.loop.close()
        self._release_component()


def register(context, *, command=None, env=None):
    """Register with an optional installer-pinned backend and isolated environment."""
    binding = HermesBinding(context, command=command, env=env)
    try:
        binding.release_component = _component_lease(binding.root, binding.command[0], binding.env)
        context.on_unload(binding.close)
        client_type = binding.sdk.XsmHost.__module__.replace("xsm_host", "xsm_client")
        client_type = __import__(client_type, fromlist=["XsmClient"]).XsmClient
        async def describe():
            async with await client_type.connect(binding.command, cwd=str(binding.root), env=binding.env) as client:
                return (await client.request("operations/list"))["operations"]
        for operation in binding._run(describe()):
            context.register_tool(name=operation["name"], toolset="xsm",
                schema={"name": operation["name"], "description": operation["description"],
                        "parameters": operation["inputSchema"]}, handler=binding.handler(operation["name"]),
                description=operation["description"])
        for name, callback in (("on_session_start", binding.start), ("on_session_end", binding.settled),
                ("subagent_start", binding.subagent_start),
                ("on_session_finalize", binding.finalize), ("on_session_delete", binding.finalize),
                ("on_session_reset", binding.reset)):
            context.register_hook(name, callback)
        context.register_hook('post_tool_call', binding.observe_question)
        context.register_hook('pre_llm_call', binding.before_model)
        context.register_hook('pre_api_request', binding.observe_context)
    except BaseException:
        binding.close()
        raise
    return binding
