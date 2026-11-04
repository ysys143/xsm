#!/usr/bin/env python3
"""Owned OpenCode install/upgrade/resume/uninstall and live UI snapshot trials."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pty
import re
import select
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import termios
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BOOT = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('xsm',run_name='__main__')"


class Server:
    def __init__(self, binary, port, work, env, output):
        self.url = 'http://127.0.0.1:' + str(port)
        self.log = output.open('w')
        self.process = subprocess.Popen([str(binary), 'serve', '--port', str(port), '--hostname', '127.0.0.1'],
            cwd=work, env=env, stdout=self.log, stderr=self.log, start_new_session=True)
        self.timeouts = []
        output.with_suffix('.process.json').write_text(json.dumps({'pid': self.process.pid, 'url': self.url,
                                                                  'cwd': str(work)}))
        try:
            until(lambda: self.request('/global/health'), 'native server health')
            until(lambda: self.request('/experimental/tool/ids'), 'native project bootstrap', timeout=25)
        except BaseException:
            self.stop()
            raise

    def request(self, path, body=None):
        request = urllib.request.Request(self.url + path, headers={'Content-Type': 'application/json'},
            data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                data = response.read()
        except TimeoutError:
            self.timeouts.append(path)
            raise
        return json.loads(data) if data else None

    def stop(self):
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=3)
        self.log.close()


class Tui:
    def __init__(self, binary, server, conversation, work, env, output, events):
        self.output = output
        self.events = events
        self.raw = b''
        self.pid, self.master = pty.fork()
        if self.pid == 0:
            os.chdir(work)
            os.execve(str(binary), [str(binary), 'attach', server.url, '--dir', str(work), '--session', conversation], env)
        self.closed = False
        fcntl.ioctl(self.master, termios.TIOCSWINSZ, struct.pack('HHHH', 44, 140, 0, 0))
        output.with_suffix('.process.json').write_text(json.dumps({'pid': self.pid, 'conversation': conversation,
                                                                  'cwd': str(work), 'url': server.url}))
        try:
            until(lambda: self.ready(conversation), 'native TUI conversation', timeout=20)
        except BaseException:
            self.stop()
            raise

    def drain(self):
        ready, _, _ = select.select([self.master], [], [], .025)
        if ready:
            try:
                self.raw += os.read(self.master, 65536)
            except OSError:
                pass
            self.output.write_bytes(self.raw)

    def alive(self):
        if self.closed:
            return False
        pid, status = os.waitpid(self.pid, os.WNOHANG)
        if pid:
            self.closed = True
            self.exit = os.waitstatus_to_exitcode(status)
        return not self.closed

    def ready(self, conversation):
        self.drain()
        if not self.alive():
            raise RuntimeError('native TUI stopped before ready: ' + str(self.exit))
        rows = [json.loads(line) for line in self.events.read_text().splitlines()] if self.events.exists() else []
        return any(row.get('conversation') == conversation and row.get('pid') == self.pid for row in rows)

    def stop(self):
        if self.alive():
            os.write(self.master, b'\x03')
            end = time.monotonic() + 5
            repeated = False
            while self.alive() and time.monotonic() < end:
                self.drain()
                if not repeated and time.monotonic() > end - 3:
                    os.write(self.master, b'\x03')
                    repeated = True
            if self.alive():
                os.kill(self.pid, signal.SIGTERM)
                end = time.monotonic() + 1
                while self.alive() and time.monotonic() < end:
                    self.drain()
            if self.alive():
                os.kill(self.pid, signal.SIGKILL)
                _, status = os.waitpid(self.pid, 0)
                self.exit = os.waitstatus_to_exitcode(status)
                self.closed = True
        self.drain()
        os.close(self.master)
        return self.exit


def until(predicate, label, timeout=12):
    end = time.monotonic() + timeout
    error = None
    while time.monotonic() < end:
        try:
            result = predicate()
            if result:
                return result
        except (OSError, ValueError) as caught:
            error = caught
        time.sleep(.025)
    raise TimeoutError(label + ': ' + str(error))


def run(args):
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='xsm-opencode-lifecycle-'))
    home, profile, work, state = [temp / name for name in ('home', 'config/opencode', 'work', 'state')]
    for path in (home, profile, work):
        path.mkdir(parents=True)
    subprocess.run(['git', 'init', '-q', str(work)], check=True)
    (profile / 'node_modules').symlink_to(args.native_root.resolve() / 'node_modules', target_is_directory=True)
    # An existing native profile already has a complete SDK dependency install.
    # Reuse the authentic pinned manifests too, so native background repair does
    # not turn process-lifetime trials into registry/download timing trials.
    for filename in ('package.json', 'package-lock.json'):
        shutil.copy2(args.native_root.resolve() / filename, profile / filename)
    native_config = profile / 'opencode.json'
    native_config.write_text(json.dumps({'enabled_providers': ['xsm-fixture'], 'model': 'xsm-fixture/fixture',
        'provider': {'xsm-fixture': {'npm': '@ai-sdk/openai-compatible', 'name': 'No model fixture',
            'options': {'baseURL': 'http://127.0.0.1:9/v1'},
            'models': {'fixture': {'name': 'fixture', 'limit': {'context': 32000, 'output': 1000}}}}}}))
    before_native = native_config.read_bytes()
    events = args.output / 'tui-events.jsonl'
    observer = temp / 'observer.mjs'
    observer.write_text('''import { appendFileSync } from 'node:fs';
export default {id:'xsm-lifetime-observer', tui:async api => {
  const timer=setInterval(()=>{
    if(api.route.current.name!=='session' || !api.state.session.get(api.route.current.params.sessionID))return;
    clearInterval(timer);
    appendFileSync(EVENTS,JSON.stringify({pid:process.pid,conversation:api.route.current.params.sessionID})+'\\n');
  },50);
  api.lifecycle.onDispose(()=>clearInterval(timer));
}};
'''.replace('EVENTS', json.dumps(str(events))))
    tui_config = profile / 'tui.jsonc'
    before_tui = ('{// retain user comment\r\n"plugin":[' + json.dumps(observer.as_uri()) + ',],}\r\n').encode()
    tui_config.write_bytes(before_tui)
    tui_config.chmod(0o640)
    env = {key: os.environ[key] for key in ('PATH', 'LANG', 'TMPDIR') if key in os.environ}
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(temp / 'config'), XDG_DATA_HOME=str(temp / 'data'),
        XDG_CACHE_HOME=str(temp / 'cache'), XSM_HOME=str(state), PYTHONDONTWRITEBYTECODE='1',
        TERM='xterm-256color', COLORTERM='truecolor', OPENCODE_DISABLE_DEFAULT_PLUGINS='1',
        OPENCODE_DISABLE_MODELS_FETCH='1')
    system, machine = os.uname().sysname, os.uname().machine
    platform = ('darwin' if system == 'Darwin' else 'linux') + '-' + ('arm64' if machine in ('arm64', 'aarch64') else 'x64')
    binary = args.native_root.resolve() / ('node_modules/opencode-' + platform + '/bin/opencode')
    version = subprocess.run([str(binary), '--version'], env=env, capture_output=True, text=True, check=True).stdout.strip()
    assert version == '1.19.5', version
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    result = {'status': 'running', 'root': str(temp), 'version': version, 'python': sys.version.split()[0],
        'platform': sys.platform, 'nativeInputFixture': True, 'modelInferenceTested': False,
        'physicalHumanInputTested': False, 'phases': [], 'installations': [],
        'userEdits': args.user_edit,
        'sourceSha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
            ('scripts/probe-opencode-install-lifecycle.py', 'xsm/host_install.py', 'xsm/host_ui_config.py',
             'xsm/component_leases.py', 'xsm/install.py', 'integrations/opencode/tui.mjs',
             'integrations/opencode/component-lease.mjs')}}
    server, tui = None, None
    number = 0

    def checkpoint():
        (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')

    def phase(name, **evidence):
        result['phases'].append({'name': name, **evidence})
        checkpoint()
        print(name, flush=True)

    def start_server():
        nonlocal number
        number += 1
        started = Server(binary, port, work, env, args.output / ('server-%d.log' % number))
        result.setdefault('serverBoots', []).append({'pid': started.process.pid, 'timeouts': started.timeouts})
        return started

    def start_tui():
        nonlocal number
        number += 1
        return Tui(binary, server, conversation, work, env, args.output / ('tui-%d.raw' % number), events)

    def setup(source, action):
        done = subprocess.run([sys.executable, '-B', '-c', BOOT, str(source), 'protocol', action,
                               'opencode', '--home', str(profile)], env=env, cwd=work, capture_output=True, text=True)
        (args.output / ('setup-%d-%s.log' % (len(result['installations']), action))).write_text(done.stdout + done.stderr)
        done.check_returncode()
        value = json.loads(done.stdout)
        result['installations'].append(value)
        return value

    def record():
        values = [json.loads(path.read_text()) for path in (state / 'sessions').glob('*.json')]
        return next(item for item in values if item['runtime'] == 'opencode')

    def ui_lease(root):
        values = [json.loads(path.read_text()) for path in (state / 'component-leases').glob('*.json')]
        return next((item for item in values if item['pid'] == tui.pid and item['component'] == 'opencode-tui'
                     and item['root'] == os.path.realpath(root)), None)

    def context():
        info = server.request('/session/' + conversation)
        assert info['id'] == conversation
        messages = server.request('/session/' + conversation + '/message?limit=1000')
        assert any('retained-opencode-context' in part.get('text', '') for message in messages for part in message['parts'])
        return messages

    def boundary(marker):
        server.request('/session/' + conversation + '/message',
                       {'noReply': True, 'parts': [{'type': 'text', 'text': marker}]})
        return context()

    def prune():
        # Only this trial's registered sidecar PIDs are inspected, never a global argv scan.
        code = '''import sys,json
sys.path.insert(0,sys.argv[1])
from pathlib import Path
import os,subprocess,time
from xsm import install,registry,identity,component_leases
from unittest import mock
install._running_from=lambda:{Path(r['protocol_root']).name for r in registry.raw_records()
 if r.get('protocol_root') and identity.state_of(r)=='live'}
with mock.patch.object(component_leases,'configured_roots',return_value=[]):
 other=sorted(install._configured_for())
folder=Path(component_leases.paths.path('component-leases'))
def lease_files():return [json.loads(p.read_text()) for p in folder.glob('*.json')]
before=lease_files();registered={r['pid'] for r in before};samples=[];original_run=subprocess.run
def observe(command,*args,**kwargs):
 result=original_run(command,*args,**kwargs)
 if isinstance(command,list) and command[:3]==['ps','-o','lstart='] and int(command[-1]) in registered:
  pid=int(command[-1]);kernel=None
  try:kernel=Path('/proc/%d/stat'%pid).read_text().rsplit(')',1)[1].split()[19]
  except (OSError,IndexError):pass
  btime=None
  try:btime=next(line.split()[1] for line in Path('/proc/stat').read_text().splitlines() if line.startswith('btime '))
  except (OSError,StopIteration):pass
  samples.append(dict(pid=pid,observed=result.stdout.strip(),returncode=result.returncode,kernelStartTicks=kernel,bootWallSeconds=btime,monotonic=time.monotonic(),wall=time.time(),pidAlive=identity.pid_alive(pid)))
 return result
subprocess.run=observe
for pid in registered:
 observe(['ps','-o','lstart=','-p',str(pid)],env={**os.environ,'LC_ALL':'C','TZ':'UTC'},capture_output=True,text=True,timeout=2)
active=component_leases.active_records()
if sys.argv[2]=='omit-ui':
 component_leases.configured_roots=lambda:[r['root'] for r in component_leases.active_records()
  if r['component']!='opencode-tui']
print(json.dumps({'removed':install.prune_snapshots(),'configured':sorted(install._configured_for()),
 'withoutComponents':other,'activeComponents':active,'leaseFilesBefore':before,
 'leaseFilesAfter':lease_files(),'pidSamples':samples}))
'''
        done = subprocess.run([sys.executable, '-B', '-c', code, str(ROOT),
                               'omit-ui' if args.mutate_omit_ui else 'normal'], env=env, cwd=work,
                              capture_output=True, text=True, check=True, timeout=12)
        value = json.loads(done.stdout)
        observations = result.setdefault('pruneObservations', [])
        observations.append(value)
        (args.output / ('prune-%d.json' % len(observations))).write_text(json.dumps(value, indent=2))
        checkpoint()
        return value

    checkpoint()
    try:
        server = start_server()
        tools = server.request('/experimental/tool/ids')
        assert not any(name.startswith('xsm_') for name in tools)
        conversation = server.request('/session', {'title': 'existing native xsm lifecycle conversation'})['id']
        boundary('retained-opencode-context')
        tui = start_tui()
        observed = native_config.read_bytes()
        expected = dict(json.loads(before_native), **{'$schema': 'https://opencode.ai/config.json'})
        assert json.loads(observed) == expected, 'native bootstrap changed more than its own schema field'
        result['nativeOnlyNormalization'] = {
            'beforeXsmInstall': True, 'addedFields': ['$schema'],
            'inputSha256': hashlib.sha256(before_native).hexdigest(),
            'installBaselineSha256': hashlib.sha256(observed).hexdigest()}
        before_native = observed  # Baseline immediately before xsm's first mutation.
        assert tui_config.read_bytes() == before_tui
        first = setup(args.baseline_source.resolve() if args.baseline_source else ROOT, 'install')
        assert first['requires_reload']
        assert not any(name.startswith('xsm_') for name in server.request('/experimental/tool/ids'))
        phase('existing native conversation survives install; backend reload is required', conversation=conversation)
        code = tui.stop()
        assert code == 0, ('initial TUI did not exit normally', code)
        tui = None
        server.stop()
        server = start_server()
        assert len([name for name in server.request('/experimental/tool/ids') if name.startswith('xsm_')]) == 22
        boundary('resume installed context')
        old = record()
        assert old['protocol_root'] == os.path.realpath(first['runtime_root'])
        tui = start_tui()
        lease = until(lambda: ui_lease(first['runtime_root']), 'installed UI lifetime')
        phase('same native conversation and context resume with installed server and UI', backend=old, ui=lease)

        if args.user_edit:
            extra = temp / 'user-added.mjs'
            extra.write_text("import{appendFileSync}from'node:fs';\nexport default{id:'user-added-plugin',tui:async()=>{"
                "appendFileSync(" + json.dumps(str(events)) + ",JSON.stringify({pid:process.pid,userAddedLoaded:true})+'\\n');}};\n")
            original_uri = json.dumps(observer.as_uri())
            addition = original_uri + ', ' + json.dumps(extra.as_uri())
            tui_config.write_bytes(tui_config.read_bytes().decode().replace(original_uri, addition, 1).encode())
            before_tui = before_tui.decode().replace(original_uri, addition, 1).encode()
            loader = Path(first['file'])
            original_loader = loader.read_bytes()
            loader.write_bytes(original_loader + b'// deliberate user-edit fixture\n')
            before_conflict = tui_config.read_bytes()
            conflict = subprocess.run([sys.executable, '-B', '-c', BOOT, str(ROOT), 'protocol', 'install',
                                      'opencode', '--home', str(profile)], env=env, cwd=work,
                                     capture_output=True, text=True)
            (args.output / 'expected-user-conflict.log').write_text(conflict.stdout + conflict.stderr)
            assert conflict.returncode == 4 and 'edited native loader preserved' in conflict.stderr
            assert loader.read_bytes() == original_loader + b'// deliberate user-edit fixture\n'
            assert tui_config.read_bytes() == before_conflict and tui.alive()
            context()
            result['activeUserConflictRejected'] = True
            loader.write_bytes(original_loader)  # Remove only this harness's injected edit.

        clone = temp / 'upgrade-source'
        for name in ('xsm', 'hooks', 'skills', 'bin', 'clients', 'integrations', '.claude-plugin', '.codex-plugin'):
            shutil.copytree(ROOT / name, clone / name, ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy2(ROOT / 'LICENSE', clone / 'LICENSE')
        with (clone / 'xsm/paths.py').open('a') as stream:
            stream.write('\n# isolated native UI lifetime revision\n')
        second = setup(clone, 'install')
        assert second['runtime_root'] != first['runtime_root']
        assert tui.alive() and ui_lease(first['runtime_root'])
        assert record()['protocol_root'] == old['protocol_root']
        kept = prune()
        assert Path(first['runtime_root']).name not in kept['removed']
        phase('upgrade keeps running old server and UI source', pruning=kept)

        # Legacy process birth strings have one-second precision. Make the new
        # backend observably newer than retirement, so blanket legacy retention
        # cannot mask the UI-only component check or its fault injection.
        next_second = int(time.time()) + 1
        until(lambda: time.time() >= next_second, 'new backend birth epoch', timeout=2)
        server.stop()
        server = start_server()
        boundary('resume after isolated upgrade')
        updated = record()
        assert updated['protocol_root'] == os.path.realpath(second['runtime_root'])
        assert updated['ref'] == old['ref'] and updated['protocol_generation'] != old['protocol_generation']
        assert tui.alive() and ui_lease(first['runtime_root'])
        kept = prune()
        assert Path(first['runtime_root']).name not in kept['removed'], ('old UI source pruned', kept)
        active_old = [item for item in kept['activeComponents']
                      if item['root'] == os.path.realpath(first['runtime_root'])]
        assert [(item['component'], item['pid']) for item in active_old] == [('opencode-tui', tui.pid)], active_old
        assert Path(first['runtime_root']).name not in kept['withoutComponents'], kept
        phase('old UI alone retains its snapshot after backend restart', backend=updated,
              ui=ui_lease(first['runtime_root']), pruning=kept)

        code = tui.stop()
        assert code == 0, ('old TUI did not exit normally', code)
        tui = None
        removed = prune()
        assert Path(first['runtime_root']).name in removed['removed'], removed
        phase('normal UI shutdown releases the previous snapshot for actual pruning', pruning=removed)
        tui = start_tui()
        lease = until(lambda: ui_lease(second['runtime_root']), 'updated UI lifetime')
        context()
        phase('updated UI resumes the same native context', ui=lease)

        uninstalled = setup(ROOT, 'uninstall')
        assert uninstalled['status'] == 'removed'
        assert tui.alive()
        assert len([name for name in server.request('/experimental/tool/ids') if name.startswith('xsm_')]) == 22
        assert native_config.read_bytes() == before_native
        if args.user_edit:
            text = tui_config.read_bytes().decode()
            assert '// retain user comment\r\n' in text
            # This fixture contains only the known comment and URI strings.
            plain = re.sub(r',\s*([}\]])', r'\1', text.replace('// retain user comment\r\n', ''))
            assert json.loads(plain) == {'plugin': [observer.as_uri(), extra.as_uri()]}
        else:
            assert tui_config.read_bytes() == before_tui
        assert (tui_config.stat().st_mode & 0o777) == 0o640
        boundary('uninstalled process still retains existing context')
        phase('uninstall preserves running processes, original JSONC bytes, mode and native settings')
        code = tui.stop()
        assert code == 0, ('updated TUI did not exit normally', code)
        tui = None
        server.stop()
        server = start_server()
        assert not any(name.startswith('xsm_') for name in server.request('/experimental/tool/ids'))
        context()
        tui = start_tui()
        assert not ui_lease(second['runtime_root'])
        if args.user_edit:
            assert any(row.get('pid') == tui.pid and row.get('userAddedLoaded')
                       for row in (json.loads(line) for line in events.read_text().splitlines()))
        phase('uninstalled native restart preserves the conversation without xsm server or UI')
        result['status'] = 'passed'
    except BaseException as error:
        result.update(status='failed', error=repr(error))
        raise
    finally:
        if tui:
            result['finalUiExit'] = tui.stop()
        if server:
            server.stop()
        checkpoint()
        for path in (temp / 'data').rglob('*.log'):
            (args.output / ('runtime-' + path.name)).write_bytes(path.read_bytes())
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mutate-omit-ui', action='store_true', help='deliberately omit UI pins in this isolated trial')
    parser.add_argument('--user-edit', action='store_true', help='add a user plugin and reject an active loader conflict')
    parser.add_argument('--baseline-source', type=Path, help='install an older isolated source first, then upgrade to this checkout')
    raise SystemExit(run(parser.parse_args()))
