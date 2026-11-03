#!/usr/bin/env python3
"""Characterize pinned Hermes gateway injection target races; no model/network."""
import argparse
import asyncio
import contextlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mutant', choices=['ignore-stale-sid'])
    args = parser.parse_args()
    source = args.native_source.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    root = Path(tempfile.mkdtemp(prefix='xsm-hermes-target-')).resolve()
    for name in ('home', 'hermes', 'state'):
        (root / name).mkdir(mode=0o700)
    environment = {key: os.environ[key] for key in ('PATH', 'LANG', 'TMPDIR') if key in os.environ}
    environment.update(HOME=str(root / 'home'), HERMES_HOME=str(root / 'hermes'),
                       XSM_HOME=str(root / 'state'), PYTHONDONTWRITEBYTECODE='1')
    os.environ.clear()
    os.environ.update(environment)
    os.chdir(root)
    commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    tag = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'v0.22.5^{}'], text=True).strip()
    if commit != tag:
        raise RuntimeError('native source is not pinned v0.22.5')
    subprocess.run(['git', '-C', str(source), 'diff', '--quiet', 'HEAD'], check=True)
    sys.path.insert(0, str(source))
    from gateway.config import Platform
    from gateway.session import SessionSource
    from gateway.run_plugin_injection import GatewayPluginInjectionMixin
    from gateway.session_automation import _owner
    from hermes_state_runtime import RuntimeStoreError

    if args.mutant:
        import gateway.session_automation as automation
        original = inspect.getsource(_owner)
        changed = original.replace('if expected != entry.session_id:', 'if False:', 1)
        if changed == original:
            raise RuntimeError('native owner guard moved; revise deliberate mutation')
        namespace = dict(automation.__dict__)
        exec(compile(changed, '<deliberate-native-owner-mutation>', 'exec'), namespace)
        _owner = automation._owner = namespace['_owner']

    report = dict(status='starting', nativeSourceCommit=commit, modelCalls=0, mutant=args.mutant,
                  network='none', root=str(root), checks=[], observations={},
                  scope='actual pinned scheduler race with controlled store, followed by real local authority and durable SQLite FIFO; no drain/model/UI')

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        report['checks'].append(name)

    async def exercise():
        route = 'agent:main:telegram:dm:target-probe'
        origin = SessionSource(platform=Platform.TELEGRAM, chat_id='target-probe')
        entry = SimpleNamespace(session_key=route, session_id='original-native-sid', origin=origin, suspended=False)
        events = []

        class Store:
            def lookup_by_session_key(self, key):
                return entry if key == route else None

            def _generate_session_key(self, source):
                return route

        class AsyncStore:
            async def lookup_by_session_key(self, key):
                return store.lookup_by_session_key(key)

        class Runner(GatewayPluginInjectionMixin):
            def _plugin_session_key_admissible(self, *args, **kwargs):
                return True

            def _plugin_messaging_session_owned(self, *args, **kwargs):
                return True

            def _plugin_injection_authorized(self, *args, **kwargs):
                return True

            def _restored_source(self, value):
                return value.origin

            def _delivery_adapter_for(self, source):
                return adapter

            def _plugin_injection_scope(self, *args):
                return contextlib.nullcontext()

        store = Store()
        adapter = object()
        runner = Runner()
        runner.session_store = store
        runner.async_session_store = AsyncStore()
        runner._running = True
        runner._draining = False
        runner._gateway_loop = asyncio.get_running_loop()
        runner._background_tasks = set()

        async def admit(adapter, event, identity):
            events.append(event)
            return SimpleNamespace(outcome='queued')

        authority = SimpleNamespace(admit_automation=admit,
                                    db=SimpleNamespace(get_compression_tip=lambda sid: None))
        with patch('gateway.session_authorities.active_authority', return_value=authority):
            scheduled = runner._schedule_plugin_message_injection(
                content='peer probe', plugin_id='xsm', session_key=route,
                plugin_home=root / 'hermes')
            check('scheduler returns before authority admission', scheduled is True and not events)
            entry.session_id = 'replacement-native-sid'
            await asyncio.gather(*list(runner._background_tasks))
            check('scheduled route resolves replacement SID', len(events) == 1 and
                  events[0].metadata['gateway_session_id'] == 'replacement-native-sid')
            check('native injection remains internal without gateway control',
                  events[0].internal is True and events[0].allow_gateway_control is False)
            report['observations']['scheduledTarget'] = events[0].metadata['gateway_session_id']
            events[0].metadata['gateway_session_id'] = 'original-native-sid'
            try:
                _owner(runner, events[0], authority)
            except RuntimeStoreError as error:
                check('FIFO owner guard rejects stale explicit SID', error.reason == 'admission_conflict')
            else:
                raise AssertionError('FIFO owner guard accepted unrelated replacement')
            events[0].metadata['gateway_session_id'] = entry.session_id
            check('FIFO owner guard accepts current explicit SID', _owner(runner, events[0], authority) is entry)
            authority.db.get_compression_tip = lambda sid: entry.session_id
            events[0].metadata['gateway_session_id'] = 'original-native-sid'
            check('FIFO owner guard permits native compression successor',
                  _owner(runner, events[0], authority) is entry)

        # A separate real authority/store proves the available pinned-SID seam.
        # Keep only drain scheduling disabled: admission, provenance, SQLite writes,
        # profile lookup and native receipt generation are upstream implementations.
        from gateway.config import GatewayConfig
        from gateway.run import GatewayRunner
        from gateway.session_authority import SessionAuthority, initialize_session_authority
        from gateway.session_contract import Principal
        from gateway.session_local import create_local_session
        from hermes_state import SessionDB
        from hermes_state_runtime import list_session_admissions

        live_runner = GatewayRunner(GatewayConfig(sessions_dir=root / 'hermes' / 'sessions'))
        db = SessionDB(root / 'hermes' / 'state.db')
        live_runner.session_store._db = db
        live_runner._session_db = db
        with patch.object(SessionAuthority, '_schedule', lambda self, ref: None):
            try:
                local = await initialize_session_authority(live_runner, profile_id='default',
                                                           instance_id='target-probe', db=db)
                actor = Principal('probe-owner', 'default',
                    frozenset({'session:create', 'session:submit', 'session:read'}), 'fixture')
                ref = create_local_session(local, actor, dict(request_id='local-probe',
                    source='cli', model='scripted-no-drain', toolsets=[]))
                live = local.sessions[ref.session_id]
                local_adapter = live_runner._adapter_for_source(live.source)
                entry = live_runner.session_store.lookup_by_session_key(live.route)
                check('real local source has an exact native transcript', entry is not None and
                      bool(entry.session_id) and local_adapter is not None)
                pinned = entry.session_id
                before = list_session_admissions(db, session_id=ref.session_id, pending_only=False)
                accepted = await live_runner._admit_plugin_injection(local_adapter, live.source,
                    session_key=live.route, session_id=pinned, content='XSM_PINNED_DURABLE', plugin_id='xsm')
                rows = list_session_admissions(db, session_id=ref.session_id, pending_only=False)
                added = [row for row in rows if row['admission_id'] not in
                         {old['admission_id'] for old in before}]
                check('pinned native injection commits exactly one durable queued row',
                      accepted is True and len(added) == 1 and added[0]['status'] == 'queued')
                row = added[0]
                descriptor = row['payload']['local_automation_v1']
                check('durable local row preserves exact peer text and transcript target',
                      row['payload']['text'] == 'XSM_PINNED_DURABLE' and descriptor['target'] == pinned)
                check('durable local row has native producer identity',
                      json.loads(row['request_id'])[:3] == ['plugin', 'xsm', live.route] and
                      row['principal_id'] == 'automation:' + live.route)
                refused = await live_runner._admit_plugin_injection(local_adapter, live.source,
                    session_key=live.route, session_id='unrelated-stale-transcript',
                    content='XSM_MUST_NOT_QUEUE', plugin_id='xsm')
                after = list_session_admissions(db, session_id=ref.session_id, pending_only=False)
                check('stale pinned native injection refuses without another row',
                      refused is False and len(after) == len(rows))
                check('plugin helper does not persist an explicit bot author', 'turn_author' not in descriptor)

                # XSM needs the authority receipt itself and explicit bot provenance,
                # rather than the helper's bool and implicit turn author.
                from gateway.platforms.event import MessageEvent, MessageType
                identity = json.dumps(['plugin', 'xsm', live.route, 'stable-xsm-claim'], separators=(',', ':'))
                event = MessageEvent(text='XSM_BOT_DURABLE', message_type=MessageType.TEXT,
                    source=live.source, internal=True, allow_gateway_control=False, message_id=identity,
                    metadata={'gateway_session_key': live.route, 'gateway_session_id': pinned,
                              'turn_author': {'id': 'bot:xsm-peer', 'name': 'XSM peer', 'is_bot': True}})
                receipt = await local.admit_automation(local_adapter, event, identity)
                rows = list_session_admissions(db, session_id=ref.session_id, pending_only=False)
                committed = next(row for row in rows if row['admission_id'] == receipt.admission_id)
                check('direct authority returns matching queued receipt and epoch',
                      receipt.status == 'queued' and receipt.ref.session_id == ref.session_id and
                      receipt.ref.profile_id == local.profile_id and receipt.authority_epoch == local.epoch)
                check('direct authority persists bot author and full original',
                      committed['payload']['local_automation_v1']['turn_author'] == event.metadata['turn_author']
                      and committed['payload']['text'] == event.text)
                replay = await local.admit_automation(local_adapter, event, identity)
                check('exact producer retry returns same admission without another row',
                      replay.admission_id == receipt.admission_id and
                      len(list_session_admissions(db, session_id=ref.session_id, pending_only=False)) == len(rows))
                event.text = 'XSM_CHANGED_PAYLOAD_MUST_NOT_QUEUE'
                try:
                    await local.admit_automation(local_adapter, event, identity)
                except RuntimeStoreError as error:
                    check('same producer identity with changed text is rejected',
                          error.reason == 'admission_conflict')
                else:
                    raise AssertionError('changed immutable producer payload was admitted')
                check('conflicting retry leaves durable row count unchanged',
                      len(list_session_admissions(db, session_id=ref.session_id, pending_only=False)) == len(rows))
                from hermes_state_runtime import begin_runtime_epoch
                next_epoch = begin_runtime_epoch(db, instance_id='replacement-owner')
                check('replacement authority advances native epoch', next_epoch != local.epoch)
                event.text = 'XSM_OLD_AUTHORITY_MUST_NOT_QUEUE'
                event.message_id = identity = json.dumps(['plugin', 'xsm', live.route, 'old-owner'])
                try:
                    await local.admit_automation(local_adapter, event, identity)
                except RuntimeStoreError as error:
                    check('old authority generation cannot enqueue after replacement', error.reason == 'stale_epoch')
                else:
                    raise AssertionError('old authority enqueued after epoch replacement')
                check('fenced authority leaves durable row count unchanged',
                      len(list_session_admissions(db, session_id=ref.session_id, pending_only=False)) == len(rows))
                report['observations']['durableAdmission'] = {
                    key: row[key] for key in ('admission_id', 'status', 'target_session_id', 'request_id')}
                report['observations']['nativeTranscript'] = pinned
            finally:
                db.close()

    try:
        asyncio.run(exercise())
        report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', failureType=type(error).__name__, failure=str(error))
        raise
    finally:
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({key: report.get(key) for key in ('status', 'checks', 'failure')}))


if __name__ == '__main__':
    main()
