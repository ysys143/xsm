#!/usr/bin/env python3
"""Pinned Hermes injection/queue audit with explicit busy-session fixtures, no model."""
import argparse
import hashlib
import inspect
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import uuid


def require(condition, details):
    if not condition:
        raise AssertionError(details)


def run(args):
    args.output.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='xsm-hermes-injection-'))
    env = {key: os.environ[key] for key in ('PATH', 'LANG', 'TMPDIR') if key in os.environ}
    env.update(HOME=str(temp / 'home'), HERMES_HOME=str(temp / 'allow'), XSM_HOME=str(temp / 'state'),
               PYTHONDONTWRITEBYTECODE='1')
    os.environ.clear()
    os.environ.update(env)
    for name in ('home', 'allow', 'deny'):
        (temp / name).mkdir()
    for name, value in (('allow', 'true'), ('deny', 'false')):
        (temp / name / 'config.yaml').write_text('plugins:\n  enabled: [xsm]\n  entries:\n    xsm:\n      allow_gateway_injection: ' + value + '\n')
    source = args.native_source.resolve()
    tag = subprocess.run(['git', 'describe', '--tags', '--exact-match'], cwd=source,
                         capture_output=True, text=True, check=True).stdout.strip()
    require(tag == 'v0.22.5', tag)
    clean = subprocess.run(['git', 'diff', '--quiet', tag, '--'], cwd=source).returncode == 0
    require(clean, 'tracked native source differs from the pinned tag')
    sys.path.insert(0, str(source))
    from hermes_cli.plugins import PluginManager, PluginContext
    from hermes_cli.plugins_manifest import PluginManifest
    from tui_gateway import plugin_inject, session_auto_continue
    require(Path(plugin_inject.__file__).resolve().is_relative_to(source), plugin_inject.__file__)
    namespace = SimpleNamespace(_sessions={}, _sessions_lock=threading.RLock(),
        time=time, uuid=uuid, threading=threading)
    def no_model(*args):
        raise AssertionError('busy-session fixture must never start a model turn')
    namespace._drain_queued_prompt = no_model
    session_auto_continue.register(namespace)
    plugin_inject.register(namespace)
    namespace._drain_queued_prompt = no_model
    if args.mutation == 'ignore-key':
        body = inspect.getsource(namespace.inject_tui_session_message)
        changed = body.replace('isinstance(session, dict) and session.get("session_key") == session_key',
                               'isinstance(session, dict)')
        require(changed != body, 'native key predicate moved; update explicit mutation')
        scope = dict(vars(namespace))
        exec(compile(changed, '<hermes-injection-key-mutant>', 'exec'), scope)
        namespace.inject_tui_session_message = scope['inject_tui_session_message']
    def row(key, home):
        return dict(session_key=key, profile_home=str(home), history_lock=threading.RLock(), running=True)
    a, b = row('native-a', temp / 'allow'), row('native-b', temp / 'allow')
    namespace._sessions.update({'ui-a': a, 'ui-b': b})
    contexts = {}
    for name in ('allow', 'deny'):
        manager = PluginManager(scope_key=str(temp / name))
        manifest = PluginManifest(name='xsm', version='fixture', source='user', path=str(temp / name / 'plugins/xsm'))
        context = PluginContext(manifest, manager)
        manager.set_tui_message_injector(namespace, namespace.inject_tui_session_message)
        contexts[name] = (manager, context)
    manager, context = contexts['allow']
    if args.mutation == 'ignore-policy':
        contexts['deny'][1]._gateway_injection_allowed = lambda: True
    result = dict(status='running', tag=tag, root=str(temp), mutation=args.mutation, trackedSourceCleanAtTag=clean, checks=[], nativeAgentOrModelTested=False,
                  nativeUiTested=False, nativeFunctionBodies=True, sessionRowsAreFixtures=True,
                  methodNamespaceIsFixture=True, modelCalls=0, sourceSha256={
                      name: hashlib.sha256((source / name).read_bytes()).hexdigest()
                      for name in ('hermes_cli/plugins.py', 'hermes_cli/plugins_manifest.py', 'hermes_cli/config.py',
                                   'hermes_cli/plugins_injection.py', 'tui_gateway/plugin_inject.py',
                                   'tui_gateway/session_auto_continue.py', 'tui_gateway/method_ctx.py')})
    def check(name, condition):
        require(condition, name)
        result['checks'].append(name)
    try:
        check('native profile policy denies injection before queue mutation',
              contexts['deny'][1].inject_message('denied', session_key='native-b') is False and
              'queued_prompt' not in a and 'queued_prompt' not in b)
        b['queued_prompt'] = dict(text='existing user input', transport='fixture-stream')
        check('native keyed busy TUI injection reaches only matching session',
              context.inject_message('peer original 한글 🚀', session_key='native-b') is True and
              'queued_prompt' not in a and b['queued_prompt']['text'] == 'existing user input\n\npeer original 한글 🚀')
        check('native busy queue preserves existing transport and running turn',
              b['queued_prompt']['transport'] == 'fixture-stream' and b['running'] is True)
        check('unknown TUI key without gateway is refused',
              context.inject_message('absent', session_key='missing-key') is False)
        scheduled = []
        def gateway(**payload):
            scheduled.append(payload)
            return True
        manager.set_gateway_message_injector(scheduled, gateway)
        check('unknown TUI key can report gateway scheduling success',
              context.inject_message('scheduled only', session_key='missing-key') is True and
              scheduled[-1]['session_key'] == 'missing-key' and scheduled[-1]['content'] == 'scheduled only')
        check('gateway scheduling did not insert into either TUI queue',
              'queued_prompt' not in a and 'scheduled only' not in b['queued_prompt']['text'])
        manager.clear_gateway_message_injector(scheduled)
        manager._cli_ref = SimpleNamespace(_agent_running=False, _pending_input=queue.Queue(), _interrupt_queue=queue.Queue())
        check('classic CLI accepts an unmatched key into its own REPL queue',
              context.inject_message('unmatched CLI route', session_key='not-this-session') is True and
              manager._cli_ref._pending_input.get_nowait() == 'unmatched CLI route')
        manager._cli_ref = None
        duplicate = row('duplicate', temp / 'allow')
        duplicate['inflight_turn'] = {'user': 'already in flight'}
        namespace._sessions['duplicate-ui'] = duplicate
        check('native true can represent an in-flight duplicate without a new queue entry',
              context.inject_message('already in flight', session_key='duplicate') is True and
              not duplicate.get('queued_prompt'))
        foreign = row('same-route', temp / 'deny')
        local = row('same-route', temp / 'allow')
        namespace._sessions.update({'foreign-first': foreign, 'local-second': local})
        check('native TUI matching selects first shared key without profile disambiguation',
              context.inject_message('shared key probe', session_key='same-route') is True and
              foreign.get('queued_prompt', {}).get('text') == 'shared key probe' and
              not local.get('queued_prompt'))
        result['status'] = 'passed'
    except Exception as error:
        result.update(status='failed', error=repr(error))
        raise
    finally:
        for native_manager, _ in contexts.values():
            native_manager.clear_tui_message_injector(namespace)
        (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'checks': len(result['checks']), 'tag': tag}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mutation', choices=('none', 'ignore-key', 'ignore-policy'), default='none')
    run(parser.parse_args())
