#!/usr/bin/env python3
"""Actual installed OpenCode tools with a bounded local scripted provider, no LLM."""
import argparse
import asyncio
import gzip
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'clients/python'))
from xsm_client import XsmClient


class ScriptedTools:
    def __init__(self, output):
        self.lock = threading.Lock()
        self.pending = None
        self.requests = 0
        self.serial = 0
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass

            def do_POST(self):
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size <= 8 * 1048576:
                    self.send_error(413); return
                request = json.loads(self.rfile.read(size))
                available = {t.get('function', {}).get('name') for t in request.get('tools', [])}
                with fixture.lock:
                    fixture.requests += 1
                    if fixture.requests > 200:
                        self.send_error(429); return
                    planned = fixture.pending
                    issue = planned and not planned['issued'] and planned['name'] in available
                    if issue: planned['issued'] = True
                    with gzip.open(output / 'scripted-requests.jsonl.gz', 'at') as stream:
                        stream.write(json.dumps({'request': request, 'issued': planned['id'] if issue else None}) + '\n')
                delta, reason = {'content': 'Explicit local tool fixture; no model inference.'}, 'stop'
                if issue:
                    delta = {'tool_calls': [{'index': 0, 'id': planned['id'], 'type': 'function',
                        'function': {'name': planned['name'], 'arguments': json.dumps(planned['args'])}}]}
                    reason = 'tool_calls'
                packets = [{'id': 'local-fixture', 'object': 'chat.completion.chunk', 'created': 0,
                    'model': 'fixture', 'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]},
                    {'id': 'local-fixture', 'object': 'chat.completion.chunk', 'created': 0,
                    'model': 'fixture', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': reason}]}]
                body = ''.join('data: ' + json.dumps(p) + '\n\n' for p in packets) + 'data: [DONE]\n\n'
                self.send_response(200); self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Content-Length', str(len(body.encode()))); self.end_headers(); self.wfile.write(body.encode())

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()

    def plan(self, name, args):
        with self.lock:
            self.serial += 1
            self.pending = dict(name=name, args=args, id='feature-' + str(self.serial), issued=False)
            return self.pending['id']

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)


async def run(args):
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    root = Path(tempfile.mkdtemp(prefix='xsm-opencode-collaboration-'))
    work, home, profile, state = [root / n for n in ('work', 'home', 'config/opencode', 'state')]
    for path in (work, home, profile): path.mkdir(parents=True)
    subprocess.run(['git', 'init', '-q', str(work)], check=True)
    spec = importlib.util.spec_from_file_location('opencode_probe', ROOT / 'scripts/probe-opencode-protocol.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    fixture = ScriptedTools(out)
    names = ['xsm_team', 'xsm_board', 'xsm_doc', 'xsm_inbox', 'xsm_files', 'xsm_ack', 'xsm_send']
    (profile / 'node_modules').symlink_to(args.native_root.resolve() / 'node_modules', target_is_directory=True)
    for name in ('package.json', 'package-lock.json'):
        source = args.native_root / name
        if source.is_file(): (profile / name).write_bytes(source.read_bytes())
    (profile / 'opencode.json').write_text(json.dumps({'enabled_providers': ['xsm-fixture'], 'model': 'xsm-fixture/fixture',
        'provider': {'xsm-fixture': {'npm': '@ai-sdk/openai-compatible', 'name': 'Explicit local fixture',
        'options': {'baseURL': 'http://127.0.0.1:' + str(fixture.server.server_port) + '/v1'},
        'models': {'fixture': {'name': 'fixture', 'limit': {'context': 262144, 'output': 1000}}}}},
        'permission': {'*': 'deny', **{n: 'allow' for n in names}}}))
    env = {k: os.environ[k] for k in ('PATH', 'LANG', 'TMPDIR') if k in os.environ}
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(root / 'config'), XDG_DATA_HOME=str(root / 'data'),
        XDG_CACHE_HOME=str(root / 'cache'), XSM_HOME=str(state), PYTHONDONTWRITEBYTECODE='1',
        OPENCODE_DISABLE_DEFAULT_PLUGINS='1', OPENCODE_DISABLE_MODELS_FETCH='1')
    command = [sys.executable, '-B', '-c', "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('xsm',run_name='__main__')", str(ROOT)]
    binary = module.native_binary(args.native_root)
    version = subprocess.check_output([str(binary), '--version'], env=env, text=True).strip(); assert version == '1.19.5'
    installed = subprocess.run([*command, 'protocol', 'install', 'opencode', '--home', str(profile)],
        cwd=work, env=env, capture_output=True, text=True, check=True)
    installation = json.loads(installed.stdout)
    if args.mutant:
        loader = Path(installation['file'])
        text = loader.read_text(); assert text.count('export default api => binding(') == 1
        text = text.replace('export default api => binding(', 'const originalBinding = api => binding(')
        text += '''\nexport default async api => {
 const hooks = await originalBinding(api);
 for(const name of ['xsm_board','xsm_doc','xsm_files']) {
  const original=hooks.tool[name].execute;
  hooks.tool[name].execute=async (...args)=>{
   const result=await original(...args), value=JSON.parse(result), input=args[0];
   if(MUTANT==='board-parent'&&name==='xsm_board'&&input.action==='log')
    for(const node of value.nodes??[]) {if(node.body==='Native revision') node.parents=[];}
   if(MUTANT==='doc-candidate'&&name==='xsm_doc'&&input.action==='next') {value.total=0;value.candidates=[];}
   if(MUTANT==='file-content'&&name==='xsm_files'&&input.encoding==='base64') value.content='AAAA';
   return JSON.stringify(value);
  };
 }
 return hooks;
};\n'''.replace('MUTANT', json.dumps(args.mutant))
        loader.write_text(text); (out / 'mutant-loader.mjs').write_text(text)
    with socket.socket() as sock: sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    log = (out / 'native.log').open('w')
    process = subprocess.Popen([str(binary), 'serve', '--port', str(port), '--hostname', '127.0.0.1'],
        cwd=work, env=env, stdout=log, stderr=log, start_new_session=True)
    report = dict(status='running', root=str(root), runtimeVersion=version, installation=installation,
        modelCalls=0, physicalHumanUiTested=False, mutant=args.mutant, checks=[], observations=[],
        scope='actual installed native tools with scripted provider; no real model or human UI')
    save = lambda: (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    def check(name, condition):
        report['activeCheck'] = name
        assert condition, name
        report['checks'].append(name); save()
    async def request(path, body=None):
        def fetch():
            req = urllib.request.Request('http://127.0.0.1:' + str(port) + path,
                json.dumps(body).encode() if body is not None else None, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=30) as response: return json.load(response)
        return await asyncio.to_thread(fetch)
    sender = None
    try:
        for _ in range(200):
            assert process.poll() is None, 'native server stopped'
            try: await request('/global/health'); break
            except OSError: await asyncio.sleep(.05)
        tools = await request('/experimental/tool/ids'); check('native registration exposes22 tools', len([t for t in tools if t.startswith('xsm_')]) == 22)
        native = await request('/session', {'title': 'Explicit native collaboration fixture'})
        report['nativeSession'] = native['id']
        async def call(name, arguments, error=False):
            report['activeOperation'] = dict(name=name, arguments=arguments); save()
            ident = fixture.plan(name, arguments)
            await request('/session/' + native['id'] + '/message', {'parts': [{'type': 'text', 'text': 'Execute the explicit local tool fixture ' + ident}]})
            messages = await request('/session/' + native['id'] + '/message?limit=1000')
            matches = [p for m in messages for p in m['parts'] if p.get('type') == 'tool' and p.get('callID') == ident]
            assert len(matches) == 1, 'exact native tool execution receipt'
            part = matches[0]; assert part['tool'] == name and part['sessionID'] == native['id']
            report['observations'].append(dict(operation=name, arguments=arguments, part=part)); save()
            assert part['state']['status'] == ('error' if error else 'completed'), str(part['state'])[:1000]
            return part if error else json.loads(part['state']['output'])
        team = 'native-collaboration'
        await call('xsm_team', dict(action='create', team=team))
        listed = await call('xsm_team', dict(action='list'))
        check('native team list includes created team', any(t['name'] == team for t in listed['teams']))
        shown = await call('xsm_team', dict(action='show', team=team))
        check('native team member is running', shown['members'][0]['running'] is True)
        async def board(action, **arguments): return await call('xsm_board', dict(action=action, team=team, **arguments))
        check('native empty board', (await board('log'))['nodes'] == [])
        body, item = 'Native contribution: 한글', 'decision: cache'
        await board('set', item=item, text=body); first = (await board('log'))['nodes'][0]
        check('native board first body and root', first['body'] == body and first['parents'] == [])
        await board('set', item=item, text='Native revision'); nodes = (await board('log', item=item))['nodes']
        check('native board links observed predecessor', len(nodes) == 2 and next(n for n in nodes if n['body'] == 'Native revision')['parents'] == [first['id']])
        check('native board item filter', (await board('log', item='absent'))['nodes'] == [])
        async def doc(action, error=False, **arguments): return await call('xsm_doc', dict(action=action, doc='BOARD.md', **arguments), error)
        first = (await doc('add', text='Native report: 한글', tags=['report']))['node']
        check('native document immutable show', (await doc('show', node=first['id']))['node'] == first)
        hypothesis = (await doc('add', text='Native hypothesis', tags=['hypothesis'], parents=[first['id']]))['node']
        check('native document frontier', [n['id'] for n in (await doc('leaves'))['nodes']] == [hypothesis['id']])
        await doc('add', text='Native working declaration', tags=['wip'], parents=[hypothesis['id']])
        candidates = await doc('next')
        check('native wip does not allocate or hide hypothesis', candidates['assigns'] is False and candidates['total'] == 1 and candidates['candidates'][0]['id'] == hypothesis['id'])
        await doc('add', text='Native insight', tags=['insight']); all_candidates = await doc('next'); limited = await doc('next', limit=1)
        check('native document limit preserves total', all_candidates['total'] == limited['total'] == 2 and limited['candidates'] == all_candidates['candidates'][:1])
        refused = await doc('add', error=True, text='orphan', parents=['f' * 12])
        check('native missing parent leaves graph unchanged', 'no node' in refused['state']['error'] and len((await doc('log'))['nodes']) == 4)
        rendered = await doc('render'); check('native render preserves contributions', rendered['nodes'] == 4 and first['body'] in rendered['text'])
        await doc('show', error=True, node='f' * 12)
        check('native unknown node rejected', 'no node' in report['observations'][-1]['part']['state']['error'])
        sender = await XsmClient.connect([*command, 'protocol', 'serve', '--stdio'], cwd=str(work), env=env)
        origin = await sender.session_open(runtime='collaboration-reference', profile=str(root), conversation='sender', cwd=str(work))
        await sender.operation_call(origin['session'], 'xsm_inbox', {})
        records = [json.loads(p.read_text()) for p in (state / 'sessions').glob('*.json')]
        receiver = next(r for r in records if r['runtime'] == 'opencode')
        check('native document author matches conversation', '[' + receiver['ref'] + ']' in first['author'])
        import base64, hashlib
        payload = b'\0\xffA\n'
        sent = await sender.operation_call(origin['session'], 'xsm_send', dict(target='ref:' + receiver['ref'], text='Native attachment',
            request_id='native-file', wake='never', wait=0, attachments=[dict(name='fixture.bin', base64=base64.b64encode(payload).decode())]))
        packet = await call('xsm_inbox', dict(message_ids=[sent['send']['id']]))
        metadata = next(i for i in packet['items'] if i['id'] == sent['send']['id'])['files']; file = metadata['files'][0]
        value = await call('xsm_files', dict(storage_id=metadata['storage_id'], entry_id=file['id'], encoding='base64'))
        check('native binary attachment preserves bytes', base64.b64decode(value['content']) == payload)
        check('native attachment metadata preserves hash', file['size'] == len(payload) and file['sha256'] == hashlib.sha256(payload).hexdigest())
        ack = await call('xsm_ack', dict(tokens=[c['token'] for c in packet['claims'] if c['id'] == sent['send']['id']]))
        check('native attachment explicitly ACKed', ack['acked'] == [sent['send']['id']])
        outgoing = await call('xsm_send', dict(target='ref:' + origin['ref'], text='Native outgoing attachment', request_id='native-outgoing',
            wake='never', wait=0, attachments=[dict(name='owned.txt', text='Native outgoing 한글')]))
        manifest = await call('xsm_files', dict(storage_id=outgoing['materials']['manifest_id'], outgoing=True))
        value = await call('xsm_files', dict(storage_id=outgoing['materials']['manifest_id'], entry_id=manifest['manifest']['files'][0]['id'], outgoing=True))
        check('native outgoing original bytes preserved', value['content'] == 'Native outgoing 한글')
        incoming = await sender.operation_call(origin['session'], 'xsm_inbox', {})
        files = next(i for i in incoming['items'] if i['id'] == outgoing['send']['id'])['files']
        value = await sender.operation_call(origin['session'], 'xsm_files', dict(storage_id=files['storage_id'], entry_id=files['files'][0]['id']))
        check('reference receives actual native sent attachment', value['content'] == 'Native outgoing 한글')
        await call('xsm_files', dict(storage_id=files['storage_id'], entry_id=files['files'][0]['id']), error=True)
        check('native reader rejects another conversation storage', 'owner-mismatch' in report['observations'][-1]['part']['state']['error'])
        await sender.operation_call(origin['session'], 'xsm_ack', dict(tokens=[c['token'] for c in incoming['claims'] if c['id'] == outgoing['send']['id']]))
        report.update(status='passed'); report.pop('activeCheck', None); report.pop('activeOperation', None)
    except BaseException as error: report.update(status='failed', error=repr(error))
    finally:
        if sender: await sender.close()
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try: await asyncio.to_thread(process.wait, timeout=5)
            except subprocess.TimeoutExpired: os.killpg(process.pid, signal.SIGKILL); await asyncio.to_thread(process.wait)
        log.close(); fixture.close(); report.update(nativeStopped=process.poll() is not None, fixtureRequests=fixture.requests); save()
        print(json.dumps({k: report.get(k) for k in ('status', 'error', 'activeCheck', 'nativeStopped', 'fixtureRequests')}))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mutant', choices=['board-parent', 'doc-candidate', 'file-content'])
    raise SystemExit(asyncio.run(asyncio.wait_for(run(parser.parse_args()), timeout=300)))
