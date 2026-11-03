#!/usr/bin/env python3
"""Actual Hermes AIAgent/plugin tool loop; explicit scripted provider, no LLM/UI."""
import argparse
import asyncio
import importlib.util
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'clients/python')]


async def run(args):
    source = args.native_source.resolve()
    commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    assert commit == subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'v0.22.5^{}'], text=True).strip()
    subprocess.run(['git', '-C', str(source), 'diff', '--quiet', 'HEAD'], check=True)
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    root = Path(tempfile.mkdtemp(prefix='xsm-hermes-collaboration-'))
    home, profile, state, work = [root / n for n in ('home', 'hermes', 'state', 'work')]
    for path in (home, profile, state, work): path.mkdir(mode=0o700)
    subprocess.run(['git', 'init', '-q', str(work)], check=True)
    env = {k: os.environ[k] for k in ('PATH', 'LANG', 'TMPDIR') if k in os.environ}
    env.update(HOME=str(home), HERMES_HOME=str(profile), XSM_HOME=str(state), TERMINAL_CWD=str(work),
        XSM_PYTHON=sys.executable, PYTHONDONTWRITEBYTECODE='1')
    os.environ.clear(); os.environ.update(env); os.chdir(work)
    sys.path.insert(0, str(source)); logging.disable(logging.CRITICAL)
    spec = importlib.util.spec_from_file_location('native_tool_fixture', ROOT / 'scripts/probe-opencode-collaboration.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    fixture = module.ScriptedTools(out, lazy=True)
    base = 'http://127.0.0.1:' + str(fixture.server.server_port) + '/v1'
    settings = {'model': {'default': 'fixture', 'provider': 'custom', 'base_url': base,
        'api_key': 'explicit-local-fixture', 'api_mode': 'chat_completions'}, 'fallback_providers': [],
        'agent': {'max_turns': 6, 'skip_context_files': True, 'background_review': {'enabled': False}},
        'memory': {'enabled': False}, 'plugins': {'enabled': ['xsm']}, 'toolsets': ['xsm'],
        'terminal': {'cwd': str(work)}}
    (profile / 'config.yaml').write_text(json.dumps(settings))
    report = dict(status='starting', root=str(root), nativeSourceCommit=commit, runtimeVersion='0.22.5',
        modelCalls=0, physicalHumanUiTested=False, mutant=args.mutant, checks=[], observations=[],
        scope='actual installed Hermes AIAgent and Tool Hub with scripted provider; no model or human UI')
    save = lambda: (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    def check(name, condition):
        report['activeCheck'] = name
        assert condition, name
        report['checks'].append(name); save()
    agent = None
    try:
        from xsm import host_install
        report['installation'] = host_install.apply('hermes', str(profile))
        from run_agent import AIAgent
        agent = AIAgent(model='fixture', provider='custom', base_url=base, api_key='explicit-local-fixture',
            api_mode='chat_completions', enabled_toolsets=['xsm'], max_iterations=6, max_tokens=1000,
            quiet_mode=True, skip_context_files=True, skip_memory=True, skip_background_review=True,
            save_trajectories=False, load_soul_identity=False, cwd=str(work), run_budget_seconds=60)
        from hermes_cli.plugins import get_plugin_manager
        from tools.registry import registry
        manager = get_plugin_manager()
        names = sorted(n for n in manager._plugin_tool_names if n.startswith('xsm_'))
        report['nativeTools'] = names
        check('native registration exposes22 tools', len(names) == 22)
        if args.mutant:
            def wrap(name, original):
                def handler(arguments, **native):
                    result = original(arguments, **native); value = json.loads(result)
                    if args.mutant == 'board-parent' and name == 'xsm_board' and arguments.get('action') == 'log':
                        for node in value.get('nodes', []):
                            if node.get('body') == 'Native revision': node['parents'] = []
                    if args.mutant == 'doc-candidate' and name == 'xsm_doc' and arguments.get('action') == 'next':
                        value.update(total=0, candidates=[])
                    if args.mutant == 'file-content' and name == 'xsm_files' and arguments.get('encoding') == 'base64':
                        value['content'] = 'AAAA'
                    return json.dumps(value)
                return handler
            for name in ('xsm_board', 'xsm_doc', 'xsm_files'):
                entry = registry.get_entry(name, scope=manager.scope_key)
                entry.handler = wrap(name, entry.handler)
        command = [sys.executable, '-B', '-c', "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('xsm',run_name='__main__')", str(ROOT)]
        async def call(name, arguments, error=False):
            report['activeOperation'] = dict(name=name, arguments=arguments); save()
            ident = fixture.plan(name, arguments)
            turn = await asyncio.to_thread(agent.run_conversation, 'Execute the explicit local tool fixture ' + ident)
            (out / ('turn-' + ident + '.json')).write_text(json.dumps(turn, indent=2))
            matches = [m for m in turn.get('messages', []) if m.get('role') == 'tool' and
                m.get('tool_call_id') == ident and m.get('tool_name', m.get('name')) == name]
            assert len(matches) == 1, 'exact native AIAgent tool receipt'
            message = matches[0]; value = json.loads(message['content'])
            report['observations'].append(dict(operation=name, arguments=arguments, message=message, result=value,
                nativeSessionId=agent.session_id)); save()
            assert bool(value.get('error')) is error, str(value)[:1000]
            return value
        from probe_native_collaboration_cases import exercise_collaboration
        await exercise_collaboration(call, check, command=command, env=env, work=work, state=state, root=root,
            runtime='hermes', observations=report['observations'], error_text=lambda row: row.get('result', row).get('error', ''))
        report.update(status='passed', nativeSessionId=agent.session_id)
        report.pop('activeCheck', None); report.pop('activeOperation', None)
    except BaseException as error:
        report.update(status='failed', error=repr(error))
    finally:
        try:
            from hermes_cli.plugins import get_plugin_manager
            manager = get_plugin_manager(); manager.unload('xsm')
            from tools.registry import registry
            report['nativeToolsRemoved'] = all(registry.get_entry(n, scope=manager.scope_key) is None for n in report.get('nativeTools', []))
            records = [json.loads(p.read_text()) for p in (state / 'sessions').glob('*.json')]
            report['nativeParticipationsEnded'] = all(r.get('ended_at') for r in records if r.get('runtime') == 'hermes')
            assert report['nativeToolsRemoved'] and report['nativeParticipationsEnded'], 'native unload did not close tools and participations'
            report['pluginUnloaded'] = True
        except Exception as error:
            report.update(status='failed', unloadFailure=repr(error))
        fixture.close(); report['fixtureRequests'] = fixture.requests; save()
        print(json.dumps({k: report.get(k) for k in ('status', 'error', 'activeCheck', 'pluginUnloaded', 'fixtureRequests')}))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mutant', choices=['board-parent', 'doc-candidate', 'file-content'])
    raise SystemExit(asyncio.run(asyncio.wait_for(run(parser.parse_args()), timeout=300)))
