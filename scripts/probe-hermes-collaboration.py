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
    fixture = module.ScriptedTools(out, lazy=True, native_ui=args.native_ui)
    base = 'http://127.0.0.1:' + str(fixture.server.server_port) + '/v1'
    settings = {'model': {'default': 'fixture', 'provider': 'custom', 'base_url': base,
        'api_key': 'explicit-local-fixture', 'api_mode': 'chat_completions'}, 'fallback_providers': [],
        'agent': {'max_turns': 6, 'skip_context_files': True, 'background_review': {'enabled': False}},
        'memory': {'enabled': False}, 'plugins': {'enabled': ['xsm']}, 'toolsets': ['xsm'],
        'terminal': {'cwd': str(work)}}
    if args.native_ui:
        settings['plugins']['entries'] = {'xsm': {'settings': {'native_questions': True}}}
        settings['toolsets'] = ['xsm', 'clarify']
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
    ui_questions, ui_choice = [], {'index': 0}
    def ui_callback(questions):
        ui_questions.extend(questions)
        return {'answers': {'q0': questions[0]['choices'][ui_choice['index']]}, 'outcome': 'submitted'}
    report['uiReceiptSnapshots'] = []
    def before_ui_retry(planned, waiting, _receipt):
        # Operator-only readback at the actual native boundary, before issuing retry.
        from xsm import board, doc
        decision = json.loads((state / 'human-decisions' / (waiting['decision_id'] + '.json')).read_text())
        snapshot = dict(operation=planned['name'], decisionId=waiting['decision_id'], status=decision['status'],
            answerSource=decision.get('answer', {}).get('source'))
        if planned['name'] == 'xsm_decide':
            snapshot['effects'] = len(board.decisions(planned['args']['team']))
        else:
            document = (work / planned['args']['doc']).resolve(); assert document.is_relative_to(work.resolve())
            nodes = doc.read(str(document)); snapshot['nodes'] = len(nodes)
            snapshot['effects'] = sum(n['author_kind'] == 'human' and planned['args']['node'] in n['parents'] for n in nodes)
        report['uiReceiptSnapshots'].append(snapshot); save()
    if args.native_ui: fixture.before_ui_retry = before_ui_retry
    try:
        from xsm import host_install
        report['installation'] = host_install.apply('hermes', str(profile))
        from run_agent import AIAgent
        agent = AIAgent(model='fixture', provider='custom', base_url=base, api_key='explicit-local-fixture',
            api_mode='chat_completions', enabled_toolsets=['xsm', 'clarify'] if args.native_ui else ['xsm'], max_iterations=6, max_tokens=1000,
            quiet_mode=True, skip_context_files=True, skip_memory=True, skip_background_review=True,
            save_trajectories=False, load_soul_identity=False, cwd=str(work), run_budget_seconds=60,
            **({'clarify_callback': ui_callback} if args.native_ui else {}))
        from hermes_cli.plugins import get_plugin_manager
        from tools.registry import registry
        manager = get_plugin_manager()
        names = sorted(n for n in manager._plugin_tool_names if n.startswith('xsm_'))
        report['nativeTools'] = names
        check('native registration exposes23 tools', len(names) == 23)
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
                    if args.mutant == 'endorsement-via' and name == 'xsm_doc_endorse' and value.get('endorsement'):
                        value['endorsement']['via'] = 'model'
                    return json.dumps(value)
                return handler
            for name in ('xsm_board', 'xsm_doc', 'xsm_files', 'xsm_doc_endorse'):
                entry = registry.get_entry(name, scope=manager.scope_key)
                entry.handler = wrap(name, entry.handler)
        command = [sys.executable, '-B', '-c', "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('xsm',run_name='__main__')", str(ROOT)]
        async def call(name, arguments, error=False):
            report['activeOperation'] = dict(name=name, arguments=arguments); save()
            ident = fixture.plan(name, arguments)
            turn = await asyncio.to_thread(agent.run_conversation, 'Execute the explicit local tool fixture ' + ident)
            (out / ('turn-' + ident + '.json')).write_text(json.dumps(turn, indent=2))
            final_id = fixture.pending.get('final_id', ident)
            matches = [m for m in turn.get('messages', []) if m.get('role') == 'tool' and
                m.get('tool_call_id') == final_id and m.get('tool_name', m.get('name')) == name]
            assert len(matches) == 1, 'exact native AIAgent tool receipt'
            message = matches[0]; value = json.loads(message['content'])
            report['observations'].append(dict(operation=name, arguments=arguments, message=message, result=value,
                turnId=ident, nativeSessionId=agent.session_id)); save()
            assert bool(value.get('error')) is error, str(value)[:1000]
            return value
        from probe_native_collaboration_cases import exercise_collaboration
        await exercise_collaboration(call, check, command=command, env=env, work=work, state=state, root=root,
            runtime='hermes', observations=report['observations'], error_text=lambda row: row.get('result', row).get('error', ''))
        if args.native_ui:
            team, item = 'native-collaboration', 'decision: cache'
            decided = await call('xsm_decide', dict(question='Native Hermes cache strategy', options=['bounded', 'none'], team=team, item=item))
            records = (await call('xsm_board', dict(action='decisions', team=team)))['decisions']
            check('synthetic native UI decision persisted once', len(records) == 1 and records[0]['answer'] == 'bounded'
                and records[0]['via'] == 'host-user' and decided['decision']['recorded'] is True)
            nodes = (await call('xsm_board', dict(action='log', team=team, item=item)))['nodes']
            check('native decision references human board node', len([n for n in nodes if n.get('decision') == records[0]['id'] and n['author_kind'] == 'human']) == 1)
            document = 'BOARD.md'
            nodes = (await call('xsm_doc', dict(action='log', doc=document)))['nodes']
            first = next(n for n in nodes if n['body'] == 'Native report: 한글')
            endorsement_args = dict(doc=document, node=first['id'])
            endorsed = await call('xsm_doc_endorse', endorsement_args)
            human = (await call('xsm_doc', dict(action='show', doc=document, node=endorsed['endorsement']['node'])))['node']
            check('native endorsement creates exact human child', endorsed['endorsement']['via'] == 'host-user'
                and human['parents'] == [first['id']] and human['author_kind'] == 'human'
                and human['tags'] == ['endorsed'] and human['body'] == first['body'])
            shown_before = len(ui_questions)
            replay = await call('xsm_doc_endorse', endorsement_args)
            nodes = (await call('xsm_doc', dict(action='log', doc=document)))['nodes']
            check('native endorsement replay adds neither UI nor node', replay == endorsed and len(nodes) == 5 and len(ui_questions) == shown_before)
            rendered = await call('xsm_doc', dict(action='render', doc=document))
            check('native endorsed body renders', first['body'] in rendered['text'])
            denied_node = (await call('xsm_doc', dict(action='add', doc=document, text='Denied native candidate', tags=['report'])))['node']
            ui_choice['index'] = 1
            denied = await call('xsm_doc_endorse', dict(doc=document, node=denied_node['id']), error=True)
            ui_choice['index'] = 0
            nodes = (await call('xsm_doc', dict(action='log', doc=document)))['nodes']
            check('native denial leaves graph without endorsement', bool(denied.get('error')) and len(nodes) == 6
                and not any(n['parents'] == [denied_node['id']] and n['author_kind'] == 'human' for n in nodes))
            check('three actual synthetic UI callbacks observed', len(ui_questions) == 3)
            snapshots = report['uiReceiptSnapshots']
            check('native UI answer receipt alone applies no effect', len(snapshots) == 3 and
                [s['status'] for s in snapshots] == ['answered', 'answered', 'denied'] and
                all(s['answerSource'] == 'host-user' and s['effects'] == 0 for s in snapshots))
            denied_decision = json.loads((state / 'human-decisions' / (snapshots[-1]['decisionId'] + '.json')).read_text())
            check('native rejected endorsement has actual denied receipt', denied_decision['status'] == 'denied' and
                denied_decision['answer']['reply']['result']['content']['answer'] == 'not now')
            report['uiQuestions'] = ui_questions
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
        if fixture.observer_error:
            report.update(status='failed', fixtureObserverError=fixture.observer_error); save()
        print(json.dumps({k: report.get(k) for k in ('status', 'error', 'activeCheck', 'pluginUnloaded', 'fixtureRequests')}))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mutant', choices=['board-parent', 'doc-candidate', 'file-content', 'endorsement-via'])
    parser.add_argument('--native-ui', action='store_true', help='Actual native clarify/bridge with explicitly synthetic UI callbacks')
    options = parser.parse_args()
    if options.mutant == 'endorsement-via' and not options.native_ui:
        parser.error('endorsement mutation requires --native-ui')
    raise SystemExit(asyncio.run(asyncio.wait_for(run(options), timeout=300)))
