#!/usr/bin/env python3
"""Actual pinned TUI rendering/keypress fixture. No human-response or model claims."""
import argparse
import asyncio
import fcntl
import hashlib
import gzip
import io
import importlib.util
import json
import os
from pathlib import Path
import pty
import queue
import re
import select
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import termios
import time
import threading
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'clients/python'))
from xsm_client import XsmHostClient


def workflow_fixture(assistant, workflow, question):
    """Script native setup/UI/readback calls; never supplies an approval answer."""
    team, document = 'native-ui-team', 'ENDORSE.md'
    state = {'step': 'setup', 'results': {}, 'workflow': workflow}
    if workflow == 'board': assistant.plan('xsm_team', {'action': 'create', 'team': team})
    else: assistant.plan('xsm_doc', {'action': 'add', 'doc': document, 'text': question, 'tags': ['report']})
    original = assistant.server.RequestHandlerClass.do_POST
    def post(handler):
        size = int(handler.headers.get('Content-Length', 0))
        if not 0 < size <= 8 * 1048576: return original(handler)
        data = handler.rfile.read(size); request = json.loads(data)
        pending = assistant.pending
        receipts = [m for m in request.get('messages', []) if m.get('role') == 'tool' and m.get('tool_call_id') == pending['id']]
        if request.get('tools') and pending['issued'] and receipts:
            try: value = json.loads(receipts[-1]['content'])
            except ValueError: value = {'nativeError': receipts[-1]['content']}
            state['results'][state['step']] = value
            if state['step'] == 'setup':
                if workflow == 'board':
                    assistant.plan('xsm_decide', {'question': question, 'options': ['blue', 'green'], 'team': team, 'item': 'decision: cache'})
                else:
                    state['node'] = value['node']
                    assistant.plan('xsm_doc_endorse', {'doc': document, 'node': value['node']['id']})
                state['step'] = 'question'
            elif state['step'] == 'question':
                assistant.plan('xsm_board' if workflow == 'board' else 'xsm_doc',
                    {'action': 'log', **({'team': team, 'item': 'decision: cache'} if workflow == 'board' else {'doc': document})})
                state['step'] = 'log'
            elif state['step'] == 'log':
                assistant.plan('xsm_board' if workflow == 'board' else 'xsm_doc',
                    {'action': 'decisions', 'team': team} if workflow == 'board' else {'action': 'render', 'doc': document})
                state['step'] = 'readback'
            elif state['step'] == 'readback': state['step'] = 'done'
        handler.rfile = io.BytesIO(data)
        result = original(handler)
        if assistant.pending['name'] in ('xsm_decide', 'xsm_doc_endorse') and assistant.pending['issued']:
            assistant.question_issued = True
        return result
    assistant.server.RequestHandlerClass.do_POST = post
    return state


class ProtocolQuestion:
    """Harness relay only; native server/TUI production IPC is a separate requirement."""
    def __init__(self, env, work, profile, conversation, question):
        self.events, self.answers, self.results = [queue.Queue() for _ in range(3)]

        async def exchange():
            command = [sys.executable, '-B', '-c',
                       "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('xsm',run_name='__main__')",
                       str(ROOT), 'protocol', 'serve', '--stdio']
            async with await XsmHostClient.connect(command, cwd=str(work), env=env) as host:
                session = await host.session_open(runtime='opencode', profile=os.path.realpath(profile),
                    conversation=conversation, cwd=str(work), capabilities=['user-decisions'])
                args = {'question': question, 'options': ['blue', 'green']}
                pending = await host.operation_call(session['session'], 'xsm_decide', args)
                assert pending['status'] == 'waiting-for-user', pending
                event = await host.next_notification()
                assert event['method'] == 'decision/request', event
                self.events.put(event)
                answer = await asyncio.to_thread(self.answers.get, True, 50)
                if answer is None:
                    await host.abandon_decision(event)
                    return
                stored = await host.respond_to_decision(event, displayed=answer['displayed'],
                    source_id=answer['sourceId'], action=answer['action'], answer=answer['answer'])
                before = await host.operation_call(session['session'], 'xsm_decision_status',
                                                    {'id': pending['decision_id']})
                expected = 'answered' if answer['action'] == 'accept' else 'dismissed'
                assert stored['status'] == expected and before['status'] == expected, before
                assert before['answer']['source'] == 'host-user', before
                applied = await host.operation_call(session['session'], 'xsm_decide', args)
                status = await host.operation_call(session['session'], 'xsm_decision_status',
                                                   {'id': pending['decision_id']})
                if answer['action'] == 'accept':
                    assert status['status'] == 'applied' and 'your user answered: blue' in str(applied), status
                else:
                    assert status['status'] == 'dismissed' and not status.get('application'), status
                self.results.put({'session': session, 'beforeRetry': before, 'afterRetry': status, 'operation': applied})

        def worker():
            try:
                asyncio.run(asyncio.wait_for(exchange(), 55))
            except BaseException as error:
                self.events.put(error)
                self.results.put(error)

        self.thread = threading.Thread(target=worker, daemon=True)
        self.thread.start()

    def question(self):
        event = self.events.get(timeout=10)
        if isinstance(event, BaseException):
            raise event
        return event

    def respond(self, answer):
        self.answers.put(answer)
        result = self.results.get(timeout=10)
        if isinstance(result, BaseException):
            raise result
        return result

    def close(self):
        self.answers.put(None)
        self.thread.join(timeout=3)
        if self.thread.is_alive():
            raise RuntimeError('owned protocol harness did not stop')


def run(args):
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    temp = Path(tempfile.mkdtemp(prefix='xsm-opencode-tui-'))
    home, profile, work = [temp / name for name in ('home', 'config/opencode', 'work')]
    for path in (home, profile, work):
        path.mkdir(parents=True)
    (profile / 'node_modules').symlink_to(args.native_root.resolve() / 'node_modules', target_is_directory=True)
    for name in ('package.json', 'package-lock.json'):
        source = args.native_root / name
        if source.is_file(): (profile / name).write_bytes(source.read_bytes())
    subprocess.run(['git', 'init', '-q', str(work)], check=True)
    assistant = None
    fixture_url = 'http://127.0.0.1:9/v1'
    spec = importlib.util.spec_from_file_location('xsm_native_fixture', ROOT / 'scripts/probe-opencode-protocol.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if args.native_bridge:
        if args.workflow:
            workflow_spec = importlib.util.spec_from_file_location('xsm_workflow_fixture', ROOT / 'scripts/probe-opencode-collaboration.py')
            workflow_module = importlib.util.module_from_spec(workflow_spec); workflow_spec.loader.exec_module(workflow_module)
            assistant = workflow_module.ScriptedTools(args.output); assistant.question_issued = False
        else: assistant = module.AssistantFixture(args.output)
        fixture_url = 'http://127.0.0.1:' + str(assistant.server.server_port) + '/v1'
        plugins = profile / 'plugins'
        command = [sys.executable, '-B', '-c',
                   "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('xsm',run_name='__main__')",
                   str(ROOT), 'protocol', 'serve', '--stdio']
        if not args.installed:
            plugins.mkdir()
            (plugins / 'xsm.js').write_text('import { tool } from "@opencode-ai/plugin";\nimport binding from ' +
                json.dumps((ROOT / 'integrations/opencode/xsm.mjs').as_uri()) +
                ';\nexport default api => binding(api, { schema: tool.schema, nativeUi: true, command: ' +
                json.dumps(command) + ' });\n')
    (profile / 'opencode.json').write_text(json.dumps({
        'enabled_providers': ['xsm-fixture'], 'model': 'xsm-fixture/fixture',
        'provider': {'xsm-fixture': {'npm': '@ai-sdk/openai-compatible', 'name': 'No model fixture',
            'options': {'baseURL': fixture_url},
            'models': {'fixture': {'name': 'fixture', 'limit': {'context': 32000, 'output': 1000}}}}},
        'permission': {'*': 'deny', **{name: 'allow' for name in (
            ['xsm_decide', 'xsm_team', 'xsm_board', 'xsm_doc', 'xsm_doc_endorse'] if args.workflow else ['xsm_decide'])}},
    }))
    env = {key: os.environ[key] for key in ('PATH', 'LANG', 'TMPDIR') if key in os.environ}
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(temp / 'config'), XDG_DATA_HOME=str(temp / 'data'),
               XDG_CACHE_HOME=str(temp / 'cache'), XSM_HOME=str(temp / 'state'),
               TERM='xterm-256color', COLORTERM='truecolor',
               OPENCODE_DISABLE_DEFAULT_PLUGINS='1', OPENCODE_DISABLE_MODELS_FETCH='1')
    installation = None
    if args.installed:
        done = subprocess.run([*command[:5], 'protocol', 'install', 'opencode', '--home', str(profile)],
                              cwd=work, env=env, capture_output=True, text=True)
        (args.output / 'installation.stdout').write_text(done.stdout)
        (args.output / 'installation.stderr').write_text(done.stderr)
        done.check_returncode()
        installation = json.loads(done.stdout)
        if args.workflow_mutant:
            loader = Path(installation['file']); text = loader.read_text()
            assert text.count('export default api => binding(') == 1
            text = text.replace('export default api => binding(', 'const originalBinding = api => binding(')
            text += '''\nexport default async api => {
 const hooks=await originalBinding(api), name=TARGET, execute=hooks.tool[name].execute;
 hooks.tool[name].execute=async(...args)=>{
  const value=JSON.parse(await execute(...args));
  if(value.decision?.record) value.decision.record.via='model';
  if(value.endorsement) value.endorsement.via='model';
  return JSON.stringify(value);
 };
 return hooks;
};\n'''.replace('TARGET', json.dumps('xsm_doc_endorse' if args.workflow == 'endorsement' else 'xsm_decide'))
            loader.write_text(text); (args.output / 'mutant-loader.mjs').write_text(text)
    binary = module.native_binary(args.native_root.resolve())
    version = subprocess.run([str(binary), '--version'], env=env, capture_output=True,
                             text=True, check=True).stdout.strip()
    assert version == '1.19.5', version
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = 'http://127.0.0.1:' + str(port)
    server_log = (args.output / 'server.log').open('w')
    server = subprocess.Popen([str(binary), 'serve', '--port', str(port), '--hostname', '127.0.0.1'],
                              cwd=work, env=env, stdout=server_log, stderr=server_log, start_new_session=True)
    result = {'status': 'running', 'root': str(temp), 'runtimeVersion': version,
              'modelInferenceTested': False, 'physicalHumanInputTested': False,
              'automatedKeypressFixture': True, 'protocolDecisionApplied': False,
              'nativeServerTuiBridge': args.native_bridge,
              'installation': installation,
              'sourceSha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
                               ('integrations/opencode/question-ui.mjs', 'scripts/probe-opencode-question-ui.py')}}
    if args.native_bridge:
        for name in ('integrations/opencode/ui-channel.mjs', 'integrations/opencode/xsm.mjs',
                     'integrations/opencode/tui.mjs', 'scripts/probe-opencode-protocol.py'):
            result['sourceSha256'][name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    if installation:
        for name in ('integrations/opencode/component-lease.mjs', 'xsm/component_leases.py',
                     'xsm/host_install.py', 'xsm/host_ui_config.py', 'xsm/jsonc_edit.py'):
            result['sourceSha256'][name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    tui_pid = None
    master = None
    protocol = None
    screen = b''
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(url + '/global/health', timeout=1) as response:
                    json.load(response)
                break
            except OSError:
                time.sleep(.05)
        request = urllib.request.Request(url + '/session', data=b'{"title":"xsm native UI probe"}',
                                         headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=10) as response:
            native = json.load(response)
        events = args.output / 'ui-events.jsonl'
        question = 'XSM runtime UI probe: choose a color\nScope: ' + native['id']
        if args.native_bridge:
            if args.workflow: result['workflow'] = workflow_fixture(assistant, args.workflow, question)
            else: assistant.question = question
            params = None
        else:
            protocol = ProtocolQuestion(env, work, profile, native['id'], question)
            decision_event = protocol.question()
            params = decision_event['params']
        plugin = temp / 'question-probe.mjs'
        script = '''import { appendFileSync } from 'node:fs';
import { presentQuestion } from MODULE;
const record = event => appendFileSync(EVENTS, JSON.stringify(event) + '\\n');
export default { id: 'xsm-native-question-probe', tui: async api => {
  record({ type: 'plugin-loaded', version: api.app.version });
  let ticks = 0;
  const timer = setInterval(async () => {
    if (ticks++ % 20 === 0) record({ type: 'wait-state', ready: api.state.ready,
      route: api.route.current, nativeSessionPresent: !!api.state.session.get(CONVERSATION) });
    if (api.route.current.name !== 'session' || !api.state.session.get(CONVERSATION)) return;
    clearInterval(timer);
    record({ type: 'native-context', conversation: api.route.current.params.sessionID,
      directory: api.state.path.directory });
    const nativeSelect = api.ui.DialogSelect;
    const ui = { ...api.ui, DialogSelect: props => {
      record({ type: 'render', title: props.title, options: props.options });
      return nativeSelect(props);
    } };
    try {
      const answer = await presentQuestion({ ...api, ui }, CONVERSATION, { params: PARAMS },
        { signal: api.lifecycle.signal });
      record({ type: 'answer', ...answer });
    } catch (error) { record({ type: 'failed', error: error.message }); }
  }, 50);
  api.lifecycle.onDispose(() => clearInterval(timer));
} };
'''
        if args.native_bridge:
            script = '''import { appendFileSync } from 'node:fs';
import companion from MODULE;
const record = event => appendFileSync(EVENTS, JSON.stringify(event) + '\\n');
export default { id: 'xsm-native-bridge-probe', tui: async api => {
  const nativeSelect = api.ui.DialogSelect;
  const ui = { ...api.ui, DialogSelect: props => {
    record({ type: 'render', title: props.title, options: props.options });
    return nativeSelect(props);
  } };
  await companion.tui({ ...api, ui });
  record({ type: 'plugin-loaded', version: api.app.version });
  const timer = setInterval(() => {
    if (api.route.current.name !== 'session' || !api.state.session.get(CONVERSATION)) return;
    clearInterval(timer);
    record({ type: 'native-ready', conversation: api.route.current.params.sessionID });
  }, 50);
  api.lifecycle.onDispose(() => clearInterval(timer));
} };
'''
        for key, value in {'MODULE': (ROOT / ('integrations/opencode/tui.mjs' if args.native_bridge
                                            else 'integrations/opencode/question-ui.mjs')).as_uri(),
                           'EVENTS': str(events), 'CONVERSATION': native['id'], 'PARAMS': params}.items():
            script = script.replace(key, json.dumps(value))
        if installation:
            script = '''import { appendFileSync } from 'node:fs';
const record = event => appendFileSync(EVENTS, JSON.stringify(event) + '\\n');
export default { id: 'xsm-readonly-ui-observer', tui: async api => {
  const off = api.event.on('message.part.updated', event => {
    const frame = event.properties.part.metadata?.xsmUi;
    if (frame?.type === 'displayed') record({ type: 'native-render-reported', displayed: frame.displayed });
  });
  const timer = setInterval(() => {
    if (api.route.current.name !== 'session' || !api.state.session.get(CONVERSATION)) return;
    clearInterval(timer);
    record({ type: 'native-ready', conversation: api.route.current.params.sessionID });
  }, 50);
  api.lifecycle.onDispose(() => { off(); clearInterval(timer); });
} };
'''.replace('EVENTS', json.dumps(str(events))).replace('CONVERSATION', json.dumps(native['id']))
        plugin.write_text(script)
        if installation:
            config_file = Path(installation['ui']['file'])
            value = json.loads(config_file.read_text())
            assert value['plugin'] == [installation['ui']['uri']], value
            value['plugin'].append(plugin.as_uri())  # A separate read-only observer; never renders or answers.
            config_file.write_text(json.dumps(value))
        else:
            (profile / 'tui.json').write_text(json.dumps({'plugin': [plugin.as_uri()]}))
        tui_pid, master = pty.fork()
        if tui_pid == 0:
            os.chdir(work)
            os.execve(str(binary), [str(binary), 'attach', url, '--dir', str(work), '--session', native['id']], env)
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', 44, 140, 0, 0))
        entered = False
        triggered = False
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master], [], [], .05)
            if ready:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    chunk = b''
                screen += chunk
                (args.output / 'terminal.raw').write_bytes(screen)
            records = [json.loads(line) for line in events.read_text().splitlines()] if events.exists() else []
            if args.native_bridge and not triggered and any(row['type'] == 'native-ready' for row in records):
                req = urllib.request.Request(url + '/session/' + native['id'] + '/prompt_async',
                    data=json.dumps({'parts': [{'type': 'text', 'text': 'Run the explicit xsm UI fixture'}]}).encode(),
                    headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=5) as response:
                    assert response.status == 204
                triggered = True
            if any(row['type'] == 'failed' for row in records):
                raise RuntimeError(str(records[-1]))
            plain = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', screen.decode(errors='replace'))
            if not entered and 'XSM runtime UI probe' in plain and ('Scope: ' + native['id']) in plain and \
                    any(row['type'] in ('render', 'native-render-reported') for row in records):
                if installation:
                    leases = [json.loads(path.read_text()) for path in (temp / 'state/component-leases').glob('*.json')]
                    lease = next(item for item in leases if item['pid'] == tui_pid)
                    assert lease['root'] == os.path.realpath(installation['runtime_root']), lease
                    assert lease['clock'] == 'utc-c', lease
                    result['activeUiLease'] = lease
                os.write(master, b'\r' if args.action == 'choose' else b'\x1b')
                entered = True
            if args.native_bridge and entered:
                decisions = [json.loads(path.read_text()) for path in (temp / 'state/human-decisions').glob('*.json')]
                decision = next((item for item in decisions if question in item['question']), None)
                expected = 'applied' if args.action == 'choose' else 'dismissed'
                if decision and decision['status'] == expected:
                    with urllib.request.urlopen(url + '/session/' + native['id'] + '/message?limit=1000', timeout=5) as response:
                        messages = json.load(response)
                    operation = 'xsm_doc_endorse' if args.workflow == 'endorsement' else 'xsm_decide'
                    completed = [part for message in messages for part in message['parts']
                                 if part.get('tool') == operation and part.get('state', {}).get('status') in
                                 (('completed', 'error') if args.action == 'cancel' else ('completed',))]
                    if completed:
                        if args.workflow:
                            state = result['workflow']
                            if state['step'] != 'done': continue
                            nodes = state['results']['log']['nodes']
                            if args.workflow == 'board':
                                recorded = state['results']['readback']['decisions']
                                assert len(recorded) == (1 if args.action == 'choose' else 0)
                                assert len(nodes) == (1 if args.action == 'choose' else 0)
                                if args.action == 'choose':
                                    assert recorded[0]['answer'] == 'blue' and recorded[0]['via'] == 'host-user'
                                    assert nodes[0]['author_kind'] == 'human' and nodes[0]['decision'] == recorded[0]['id']
                                    assert state['results']['question']['decision']['record'] == recorded[0], 'native board receipt matches persisted user decision'
                            else:
                                assert len(nodes) == (2 if args.action == 'choose' else 1)
                                children = [n for n in nodes if state['node']['id'] in n['parents']]
                                assert len(children) == (1 if args.action == 'choose' else 0)
                                if args.action == 'choose':
                                    assert children[0]['author_kind'] == 'human' and children[0]['body'] == question
                                    assert children[0]['tags'] == ['endorsed']
                                    assert state['results']['question']['endorsement']['via'] == 'host-user', 'native endorsement receipt is host-user'
                                assert question in state['results']['readback']['text']
                        assert decision['answer']['source'] == 'host-user'
                        assert decision['display']['complete']
                        control = [part for message in messages for part in message['parts']
                                   if part.get('metadata', {}).get('xsmUi')]
                        assert len(control) >= 4, control
                        assert all(part['ignored'] and part['synthetic'] and not part['text'] for part in control)
                        if args.workflow:
                            with gzip.open(args.output / 'scripted-requests.jsonl.gz', 'rt') as stream: model_requests = stream.read()
                        else: model_requests = (args.output / 'assistant-fixture.jsonl').read_text()
                        observed_requests = [json.loads(line)['request'] for line in model_requests.splitlines()]
                        if not any(message.get('role') == 'tool' for req in observed_requests
                                   for message in req.get('messages', [])):
                            continue  # Inspect a post-tool inference request, after all UI frames were stored.
                        assert 'xsmUi' not in model_requests
                        for part in control:
                            assert part['metadata']['xsmUi']['nonce'] not in model_requests
                        result.update(status='passed', nativeSession=native['id'], nativeRenderObserved=True,
                            terminalTitleObserved=True, terminalScopeObserved=True,
                            protocolDecisionApplied=expected == 'applied', decision=decision,
                            nativeToolOutput=completed[-1]['state'].get('output', completed[-1]['state'].get('error')), controlFrames=len(control),
                            uiFramesExcludedFromModelInput=True, assistantFixtureQuestionIssued=assistant.question_issued)
                        if installation:
                            actual = [json.loads(path.read_text()) for path in (temp / 'state/sessions').glob('*.json')]
                            backend = next(item for item in actual if item['runtime'] == 'opencode')
                            assert backend['protocol_root'] == os.path.realpath(installation['runtime_root']), backend
                            result['backendOrigin'] = backend['protocol_root']
                        (args.output / 'native-messages.json').write_text(json.dumps(messages, indent=2))
                        break
            answer = next((row for row in records if row['type'] == 'answer'), None)
            if answer:
                expected_action = 'accept' if args.action == 'choose' else 'cancel'
                assert answer['displayed'] == question and answer['action'] == expected_action, answer
                assert answer['answer'] == ('blue' if args.action == 'choose' else None), answer
                application = protocol.respond(answer)
                result.update(status='passed', nativeSession=native['id'], answer=answer,
                              nativeRenderObserved=True, terminalTitleObserved=entered,
                              terminalScopeObserved=True,
                              protocolDecisionApplied=application['afterRetry']['status'] == 'applied',
                              protocolApplication=application)
                break
            finished, status = os.waitpid(tui_pid, os.WNOHANG)
            if finished:
                tui_pid = None
                raise RuntimeError('native TUI stopped before answer: ' + str(status))
        else:
            raise TimeoutError('native question render/answer was not observed')
        print(json.dumps({'status': result['status'], 'runtimeVersion': version,
                          'nativeRenderObserved': True, 'nativeBridge': args.native_bridge,
                          'protocolDecisionApplied': result['protocolDecisionApplied']}))
    except BaseException as error:
        result.update(status='failed', error=repr(error))
        raise
    finally:
        if tui_pid:
            try:
                os.kill(tui_pid, signal.SIGTERM)
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    finished, _ = os.waitpid(tui_pid, os.WNOHANG)
                    if finished:
                        break
                    time.sleep(.025)
                else:
                    os.kill(tui_pid, signal.SIGKILL)
                    os.waitpid(tui_pid, 0)
            except ProcessLookupError:
                pass
        if master is not None:
            os.close(master)
        if server.poll() is None:
            os.killpg(server.pid, signal.SIGTERM)
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(server.pid, signal.SIGKILL)
                server.wait()
        server_log.close()
        if protocol:
            protocol.close()
        if assistant:
            assistant.close()
        (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        for path in (temp / 'data').rglob('*.log'):
            (args.output / ('runtime-' + path.name)).write_bytes(path.read_bytes())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--action', choices=['choose', 'cancel'], default='choose')
    parser.add_argument('--native-bridge', action='store_true')
    parser.add_argument('--installed', action='store_true')
    parser.add_argument('--workflow', choices=['board', 'endorsement'])
    parser.add_argument('--workflow-mutant', choices=['receipt-via'])
    args = parser.parse_args()
    if args.installed and not args.native_bridge:
        parser.error('--installed requires --native-bridge')
    if args.workflow and not (args.native_bridge and args.installed):
        parser.error('--workflow requires --native-bridge --installed')
    if args.workflow_mutant and (not args.workflow or args.action != 'choose'):
        parser.error('--workflow-mutant requires a choose workflow')
    run(args)
