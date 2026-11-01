#!/usr/bin/env python3
"""Actual pinned TUI rendering/keypress fixture. No human-response or model claims."""
import argparse
import asyncio
import fcntl
import hashlib
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
    args.output.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='xsm-opencode-tui-'))
    home, profile, work = [temp / name for name in ('home', 'config/opencode', 'work')]
    for path in (home, profile, work):
        path.mkdir(parents=True)
    (profile / 'node_modules').symlink_to(args.native_root.resolve() / 'node_modules', target_is_directory=True)
    subprocess.run(['git', 'init', '-q', str(work)], check=True)
    (profile / 'opencode.json').write_text(json.dumps({
        'enabled_providers': ['xsm-fixture'], 'model': 'xsm-fixture/fixture',
        'provider': {'xsm-fixture': {'npm': '@ai-sdk/openai-compatible', 'name': 'No model fixture',
            'options': {'baseURL': 'http://127.0.0.1:9/v1'},
            'models': {'fixture': {'name': 'fixture', 'limit': {'context': 32000, 'output': 1000}}}}},
    }))
    env = {key: os.environ[key] for key in ('PATH', 'LANG', 'TMPDIR') if key in os.environ}
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(temp / 'config'), XDG_DATA_HOME=str(temp / 'data'),
               XDG_CACHE_HOME=str(temp / 'cache'), XSM_HOME=str(temp / 'state'),
               TERM='xterm-256color', COLORTERM='truecolor',
               OPENCODE_DISABLE_DEFAULT_PLUGINS='1', OPENCODE_DISABLE_MODELS_FETCH='1')
    platform = 'darwin-arm64' if os.uname().sysname == 'Darwin' else 'linux-x64'
    binary = args.native_root.resolve() / ('node_modules/opencode-' + platform + '/bin/opencode')
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
              'sourceSha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
                               ('integrations/opencode/question-ui.mjs', 'scripts/probe-opencode-question-ui.py')}}
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
        for key, value in {'MODULE': (ROOT / 'integrations/opencode/question-ui.mjs').as_uri(),
                           'EVENTS': str(events), 'CONVERSATION': native['id'], 'PARAMS': params}.items():
            script = script.replace(key, json.dumps(value))
        plugin.write_text(script)
        (profile / 'tui.json').write_text(json.dumps({'plugin': [plugin.as_uri()]}))
        tui_pid, master = pty.fork()
        if tui_pid == 0:
            os.chdir(work)
            os.execve(str(binary), [str(binary), 'attach', url, '--dir', str(work), '--session', native['id']], env)
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', 44, 140, 0, 0))
        entered = False
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
            if any(row['type'] == 'failed' for row in records):
                raise RuntimeError(str(records[-1]))
            plain = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', screen.decode(errors='replace'))
            if not entered and 'XSM runtime UI probe' in plain and ('Scope: ' + native['id']) in plain and \
                    any(row['type'] == 'render' for row in records):
                os.write(master, b'\r' if args.action == 'choose' else b'\x1b')
                entered = True
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
                          'nativeRenderObserved': True, 'automatedAnswer': result['answer']['answer']}))
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
        (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        for path in (temp / 'data').rglob('*.log'):
            (args.output / ('runtime-' + path.name)).write_bytes(path.read_bytes())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--action', choices=['choose', 'cancel'], default='choose')
    run(parser.parse_args())
