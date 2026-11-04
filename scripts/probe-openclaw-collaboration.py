#!/usr/bin/env python3
"""Actual OpenClaw gateway/agent/Tool Hub collaboration with local scripted provider."""
import argparse
import asyncio
import gzip
import importlib.util
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'clients/python')]
from integrations.openclaw import worker_session
from xsm_client import XsmClient


async def run(args):
    assert args.native_cli.is_absolute() and args.node.is_absolute()
    assert json.loads((args.native_cli.parent / 'package.json').read_text())['version'] == '2026.10.9'
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    root = Path(tempfile.mkdtemp(prefix='xsm-openclaw-collaboration-')).resolve()
    home, profile, state, work = [root / n for n in ('home', 'openclaw', 'xsm', 'work')]
    for path in (home, profile, state, work): path.mkdir(mode=0o700)
    subprocess.run(['git', 'init', '-q', str(work)], check=True)
    env = {k: os.environ[k] for k in ('PATH', 'LANG', 'TMPDIR') if k in os.environ}
    env.update(HOME=str(home), XSM_HOME=str(state), PYTHONDONTWRITEBYTECODE='1')
    os.environ.clear(); os.environ.update(env)
    spec = importlib.util.spec_from_file_location('native_tool_fixture', ROOT / 'scripts/probe-opencode-collaboration.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    fixture = module.ScriptedTools(out, lazy=True, native_dialect='openclaw')
    with socket.socket() as sock: sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    config = {'gateway': {'mode': 'local', 'bind': 'loopback', 'port': port,
        'auth': {'mode': 'token', 'token': secrets.token_hex(32)}},
        'agents': {'defaults': {'workspace': str(work), 'heartbeat': {'every': '0m'},
            'model': {'primary': 'xsm-fixture/fixture', 'fallbacks': []}}}, 'cron': {'enabled': False},
        'models': {'providers': {'xsm-fixture': {'api': 'openai-completions',
            'baseUrl': 'http://127.0.0.1:' + str(fixture.server.server_port) + '/v1', 'apiKey': 'explicit-local-fixture',
            'agentRuntime': {'id': 'openclaw'}, 'models': [{'id': 'fixture', 'name': 'fixture', 'reasoning': False,
                'input': ['text'], 'contextWindow': 262144, 'maxTokens': 1000,
                'cost': {'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0}}]}}},
        'plugins': {'enabled': True, 'allow': ['xsm'], 'entries': {'xsm': {'enabled': True,
            'config': {'nativeWake': True}, 'hooks': {'allowConversationAccess': True, 'allowPromptInjection': True}}}}}
    config_path = profile / 'openclaw.json'; config_path.write_text(json.dumps(config)); config_path.chmod(0o600)
    env.update(OPENCLAW_STATE_DIR=str(profile), OPENCLAW_CONFIG_PATH=str(config_path), OPENCLAW_NO_RESPAWN='1')
    from xsm import host_install
    installation = host_install.apply('openclaw', str(profile))
    if args.mutant:
        entry = profile / 'extensions/xsm/index.mjs'
        code = entry.read_text(); assert code.count('binding.register(api,') == 1
        observer = '''
function mutatedApi(api) {
 const wrap = tool => {
  if(!tool) return tool;
  const execute=tool.execute;
  return {...tool,execute:async(...args)=>{
   const result=await execute.apply(tool,args), input=args[1], value=result.details;
   if(MUTANT==='board-parent'&&tool.name==='xsm_board'&&input.action==='log')
    for(const node of value.nodes??[]) {if(node.body==='Native revision') node.parents=[];}
   if(MUTANT==='doc-candidate'&&tool.name==='xsm_doc'&&input.action==='next') {value.total=0;value.candidates=[];}
   if(MUTANT==='file-content'&&tool.name==='xsm_files'&&input.encoding==='base64') value.content='AAAA';
   return {...result,details:value,content:[{type:'text',text:JSON.stringify(value)}]};
  }};
 };
 const registerTool=(factory,options)=>api.registerTool(typeof factory==='function' ? ctx=>wrap(factory(ctx)) : wrap(factory),options);
 return new Proxy(api,{get:(target,key)=>key==='registerTool'?registerTool:Reflect.get(target,key,target)});
}
'''.replace('MUTANT', json.dumps(args.mutant))
        entry.write_text(observer + code.replace('binding.register(api,', 'binding.register(mutatedApi(api),', 1))
        (out / 'mutant-loader.mjs').write_text(entry.read_text())
    report = dict(status='starting', root=str(root), runtimeVersion='2026.10.9', installation=installation,
        modelCalls=0, physicalHumanUiTested=False, mutant=args.mutant, checks=[], observations=[], catalogReceipts=[],
        scope='actual installed native gateway/agent/Tool Hub with scripted provider; no real model or human UI')
    save = lambda: (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    def check(name, condition):
        report['activeCheck'] = name
        assert condition, name
        report['checks'].append(name); save()
    def rpc(method, params):
        result = subprocess.run([str(args.node), str(ROOT / 'integrations/openclaw/worker_rpc.mjs'), str(args.native_cli)],
            input=json.dumps(dict(method=method, params=params)), cwd=work, env=env, capture_output=True, text=True, timeout=50)
        number = report.get('rpcCount', 0); report['rpcCount'] = number + 1
        (out / ('rpc-' + str(number) + '.stdout')).write_text(result.stdout)
        (out / ('rpc-' + str(number) + '.stderr')).write_text(result.stderr)
        assert result.returncode == 0, 'actual native RPC refused ' + method
        return worker_session.decode_reply(result.stdout)
    def provider_rows():
        path = out / 'scripted-requests.jsonl.gz'
        if not path.exists(): return []
        with gzip.open(path, 'rt') as stream: return [json.loads(line) for line in stream]
    log = (out / 'gateway.log').open('w'); process = None
    try:
        process = subprocess.Popen([str(args.node), str(args.native_cli), 'gateway', 'run'], cwd=work,
            env=env, stdout=log, stderr=log, start_new_session=True)
        deadline = time.monotonic() + 45
        while True:
            assert process.poll() is None, 'native gateway exited'
            with socket.socket() as test:
                if test.connect_ex(('127.0.0.1', port)) == 0: break
            assert time.monotonic() < deadline, 'native gateway startup deadline'
            await asyncio.sleep(.1)
        await asyncio.to_thread(rpc, 'health', {})
        created = await asyncio.to_thread(rpc, 'sessions.create', worker_session.creation_params('main', str(work)))
        locator = worker_session.created_locator(created, 'main', str(work)); report['locator'] = locator
        async def call(name, arguments, error=False, catalog=False):
            report['activeOperation'] = dict(name=name, arguments=arguments); save()
            ident = fixture.plan(name, arguments); first_row = len(provider_rows())
            params = worker_session.agent_params(locator, 'Execute the explicit local tool fixture ' + ident, 'run-' + ident)
            admitted = await asyncio.to_thread(rpc, 'agent', params)
            worker_session.accepted_run(admitted, locator, params['idempotencyKey'])
            terminal = await asyncio.to_thread(rpc, 'agent.wait', dict(runId=params['idempotencyKey'], timeoutMs=15000))
            worker_session.completed_run(terminal, locator, params['idempotencyKey'])
            matches = {}
            for row in provider_rows()[first_row:]:
                for message in row['request'].get('messages', []):
                    if message.get('role') == 'tool' and message.get('tool_call_id') == ident:
                        matches[message['content']] = message
            assert len(matches) == 1, 'exact native Tool Hub receipt'
            message = next(iter(matches.values())); content = message['content']
            try: envelope = json.loads(content)
            except ValueError: envelope = None
            if catalog:
                report['catalogReceipts'].append(dict(message=message, result=envelope)); save(); return envelope
            if error:
                assert isinstance(content, str) and ('error' in content.lower() or 'no node' in content.lower()), 'actual native error receipt'
                observed = dict(operation=name, arguments=arguments, message=message, envelope=envelope, errorText=content)
                report['observations'].append(observed); save(); return observed
            assert envelope.get('tool', {}).get('name') == name, 'native receipt tool name'
            value = envelope['result']['details']; assert isinstance(value, dict)
            report['observations'].append(dict(operation=name, arguments=arguments, message=message, envelope=envelope, result=value)); save()
            return value
        command = [sys.executable, '-B', '-c', "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('xsm',run_name='__main__')", str(ROOT)]
        async with await XsmClient.connect([*command, 'protocol', 'serve', '--stdio'], cwd=str(work), env=env) as describe:
            names = [o['name'] for o in (await describe.request('operations/list'))['operations']]
        candidates = []; truncated_queries = []
        for offset in range(0, len(names), 16):
            result = await call('tool_search', {'queries': [{'query': n, 'limit': 1} for n in names[offset:offset + 16]]}, catalog=True)
            candidates.extend(c for row in result['results'] for c in row.get('candidates', []))
            truncated_queries.extend(row['query'] for row in result['results'] if row.get('truncated'))
        for query in truncated_queries:
            result = await call('tool_search', {'query': query, 'limit': 1}, catalog=True)
            assert isinstance(result, list), 'single native search returns candidate list'
            candidates.extend(result)
        check('native registration exposes23 tools', len(names) == 23 and {c['name'] for c in candidates} == set(names))
        from probe_native_collaboration_cases import exercise_collaboration
        await exercise_collaboration(call, check, command=command, env=env, work=work, state=state, root=root,
            runtime='openclaw', observations=report['observations'], error_text=lambda row: row.get('errorText', ''))
        report.update(status='passed'); report.pop('activeCheck', None); report.pop('activeOperation', None)
    except BaseException as error:
        report.update(status='failed', error=repr(error))
    finally:
        if process and process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try: await asyncio.to_thread(process.wait, timeout=10)
            except subprocess.TimeoutExpired: os.killpg(process.pid, signal.SIGKILL); await asyncio.to_thread(process.wait)
        fixture.close(); log.close()
        records = [json.loads(p.read_text()) for p in (state / 'sessions').glob('*.json')]
        report.update(gatewayStopped=process is not None and process.poll() is not None,
            nativeParticipationsEnded=all(r.get('ended_at') for r in records if r.get('runtime') == 'openclaw'),
            fixtureRequests=fixture.requests)
        if not report['gatewayStopped'] or not report['nativeParticipationsEnded']: report['status'] = 'failed'
        save(); print(json.dumps({k: report.get(k) for k in ('status', 'error', 'activeCheck', 'gatewayStopped', 'nativeParticipationsEnded', 'fixtureRequests')}))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-cli', type=Path, required=True)
    parser.add_argument('--node', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mutant', choices=['board-parent', 'doc-candidate', 'file-content'])
    raise SystemExit(asyncio.run(asyncio.wait_for(run(parser.parse_args()), timeout=480)))
