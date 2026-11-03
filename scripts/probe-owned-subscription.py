#!/usr/bin/env python3
"""Actual Pi/OpenCode subscribed turns through public owned operations.

Uses fresh profiles and the existing direct Anthropic OAuth proxy, never an
assistant fixture. The controller is a generic reference participant.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'clients/python')]
from probe_subscription_relay import SubscriptionRelay


def options():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', choices=('pi', 'opencode'), required=True)
    parser.add_argument('--native-cli', type=Path, required=True)
    parser.add_argument('--native-deps-root', type=Path)
    parser.add_argument('--model', required=True, help='Exact live direct Anthropic OAuth model')
    parser.add_argument('--native-tools', action='store_true', help='Also verify one native model xsm_send call')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.native_cli.is_absolute() or not args.native_cli.is_file():
        parser.error('an existing absolute native CLI is required')
    if args.runtime == 'opencode' and (args.native_deps_root is None or not
            (args.native_deps_root / 'node_modules/@opencode-ai/plugin/package.json').is_file()):
        parser.error('OpenCode requires its pinned private dependency root')
    if args.output.exists():
        parser.error('output must be new; preserve previous evidence')
    return args


def profile_config(args, root, relay):
    profile = root / args.runtime
    profile.mkdir(mode=0o700)
    base = 'http://127.0.0.1:' + str(relay.server.server_port) + '/v1'
    model = 'xsm-subscription/' + args.model
    if args.runtime == 'pi':
        config = {'providers': {'xsm-subscription': {'baseUrl': base,
            'api': 'openai-completions', 'apiKey': 'local-proxy-placeholder', 'models': [{
                'id': args.model, 'name': args.model, 'reasoning': False, 'input': ['text'],
                'contextWindow': 32000, 'maxTokens': 1000}]}}}
        (profile / 'models.json').write_text(json.dumps(config))
        (profile / 'settings.json').write_text(json.dumps({'defaultProvider': 'xsm-subscription',
            'defaultModel': args.model, 'compaction': {'enabled': False}, 'retry': {'enabled': False}}))
    else:
        native = args.native_deps_root.resolve()
        (profile / 'node_modules').symlink_to(native / 'node_modules', target_is_directory=True)
        for name in ('package.json', 'package-lock.json'):
            if (native / name).is_file():
                shutil.copyfile(native / name, profile / name)
        permission = {'*': 'deny'}
        if args.native_tools:
            permission['xsm_send'] = 'allow'
        (profile / 'opencode.json').write_text(json.dumps({'enabled_providers': ['xsm-subscription'],
            'model': model, 'provider': {'xsm-subscription': {'npm': '@ai-sdk/openai-compatible',
            'name': 'Existing OAuth subscription', 'options': {'baseURL': base,
            'apiKey': 'local-proxy-placeholder'}, 'models': {args.model: {'name': args.model,
            'limit': {'context': 32000, 'output': 1000}}}}}, 'permission': permission}))
    return profile, model


async def run(args, root, out, relay, report):
    profile, model = profile_config(args, root, relay)
    env = {key: os.environ[key] for key in ('PATH', 'LANG', 'TMPDIR') if key in os.environ}
    env.update(HOME=str(root / 'home'), XSM_HOME=str(root / 'state'),
        XDG_DATA_HOME=str(root / 'data'), XDG_CACHE_HOME=str(root / 'cache'),
        XSM_PYTHON=sys.executable, PYTHONDONTWRITEBYTECODE='1')
    if args.runtime == 'pi':
        env.update(PI_CODING_AGENT_DIR=str(profile), XSM_PI=str(args.native_cli))
    else:
        env.update(OPENCODE_CONFIG_DIR=str(profile), XSM_OPENCODE=str(args.native_cli),
            OPENCODE_DISABLE_DEFAULT_PLUGINS='1', OPENCODE_DISABLE_MODELS_FETCH='1')
    os.environ.clear(); os.environ.update(env)
    from xsm import host_install, identity, workers
    from xsm_client import XsmClient
    def save():
        report.update(providerRequests=relay.forwarded, responseModelLabels=sorted(relay.response_models))
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        report['checks'].append(name); save()
    client = None
    children = {}
    try:
        installation = host_install.apply(args.runtime, str(profile))
        report['runtimeRoot'] = installation['runtime_root']
        command = [sys.executable, '-B', '-c',
            "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('xsm',run_name='__main__')",
            str(ROOT), 'protocol', 'serve', '--stdio']
        client = await XsmClient.connect(command, cwd=str(root / 'workspace'), env=env)
        parent = await client.session_open(runtime='owned-reference', profile='subscription-probe',
            conversation=secrets.token_hex(8), cwd=str(root / 'workspace'), capabilities=['messaging','inbox','events'])
        packets = []
        async def op(name, arguments):
            value = await client.operation_call(parent['session'], name, arguments)
            if isinstance(value.get('incoming'), dict) and value['incoming'].get('claims'):
                packets.append(value['incoming'])
            child = value.get('child') or {}
            if type(child.get('pid')) is int and child.get('lstart'):
                children[child['pid']] = child['lstart']
            return value
        service = 'native-' + args.runtime
        created = await op('xsm_owned', {'action':'create','name':service,'runtime':args.runtime,
            'home':str(profile),'model':model})
        check('public operation admits pinned native provider', created['native_provider']['version'] ==
              ('1.4.0' if args.runtime == 'pi' else '1.19.5'))
        report['nativeProvider'] = created['native_provider']; save()
        async def turn(request, text, work='shared'):
            value = await op('xsm_owned', {'action':'run','name':service,'request_id':request,
                'text':text,'work_context':work})
            deadline = time.monotonic() + 180
            while value['status'] not in ('sent','reply-stored','unknown','error'):
                if time.monotonic() > deadline:
                    raise TimeoutError('native subscribed turn')
                await asyncio.sleep(.1)
                value = await op('xsm_owned', {'action':'status','name':service,'request_id':request})
            (out / (request + '-journal.json')).write_text(json.dumps(value, indent=2) + '\n')
            check('actual native answer stored ' + request, value['status'] in ('sent','reply-stored'))
            check('native completion did not manufacture task success ' + request, value['result']['outcome'] is None)
            return value
        async def read_reply(value, expected):
            packet = next((p for p in packets if any(c['id'] == value['reply_id'] for c in p['claims'])), None)
            if packet is None:
                packet = await op('xsm_inbox', {'message_ids':[value['reply_id']]})
            claims = [c for c in packet['claims'] if c['id'] == value['reply_id']]
            check('actual original claimed ' + value['id'], len(claims) == 1 and
                  any(expected in text for text in packet['messages']))
            ack = await op('xsm_ack', {'tokens':[claims[0]['token']]})
            check('actual original ACKed ' + value['id'], ack['acked'] == [value['reply_id']])
        nonce = secrets.token_hex(12)
        first_text = 'Remember private token '+nonce+'. Reply exactly XSM_FIRST_'+nonce+'. Do not use tools.'
        first = await turn('first', first_text)
        check('first actual model answer exact', first['result']['body'] == 'XSM_FIRST_' + nonce)
        await read_reply(first, 'XSM_FIRST_' + nonce)
        second = await turn('recall', 'Return only the private token from the previous user turn. Do not use tools.')
        check('native conversation reused and previous token recalled',
            second['result']['native_session_id'] == first['result']['native_session_id'] and second['result']['body'] == nonce)
        await read_reply(second, nonce)
        separate = await turn('separate', 'Reply exactly XSM_SEPARATE_'+nonce+'. Do not use tools.', 'independent')
        check('independent native conversation and exact answer',
            separate['result']['native_session_id'] != first['result']['native_session_id'] and separate['result']['body'] == 'XSM_SEPARATE_' + nonce)
        await read_reply(separate, 'XSM_SEPARATE_' + nonce)
        before = relay.forwarded
        replay = await turn('first', first_text)
        check('same request returns same reply without inference', replay['reply_id'] == first['reply_id'] and relay.forwarded == before)
        if args.native_tools:
            note = 'XSM_NATIVE_TOOL_NOTE_' + nonce
            arguments = {'target':parent['address'],'text':note,'kind':'note','wake':'never','wait':0}
            expected = 'XSM_TOOL_DONE_' + nonce
            task = 'Call xsm_send exactly once with '+json.dumps(arguments)+'. Then reply exactly '+expected+'. Do not use other tools.'
            result = await turn('native-tools', task, 'tools')
            check('native model tool turn answer exact', result['result']['body'] == expected)
            fresh = await op('xsm_inbox', {})
            notes = {c['id']:c for p in packets+[fresh] for c,text in zip(p.get('claims',[]),p.get('messages',[])) if note in text}
            check('model native tool produced one canonical note', len(notes) == 1)
            note_id, claim = next(iter(notes.items()))
            ack = await op('xsm_ack', {'tokens':[claim['token']]})
            check('native model tool note explicitly ACKed', ack['acked'] == [note_id])
            await read_reply(result, expected)
            report['nativeModelToolMessageId'] = note_id
        report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', failureType=type(error).__name__, failure=str(error))
    finally:
        for pid, birth in children.items():
            if identity.pid_alive(pid) and identity.lstart(pid) == birth:
                workers._terminate(pid, birth)
        report['ownedChildrenExited'] = all(not identity.pid_alive(pid) or identity.lstart(pid) != birth
                                            for pid,birth in children.items())
        if not report['ownedChildrenExited']:
            report.update(status='failed', cleanupFailure='owned child remains live')
        if client:
            try:
                await client.close()
            except Exception as error:
                report.update(status='failed', cleanupFailure=type(error).__name__)
        relay.close()
        save()
    return 0 if report['status'] == 'passed' and report['ownedChildrenExited'] else 1


if __name__ == '__main__':
    args = options()
    out = args.output.absolute(); out.mkdir(parents=True)
    root = Path(tempfile.mkdtemp(prefix='xsm-owned-subscription-')).resolve(); root.chmod(0o700)
    for name in ('home','workspace','state'):
        (root / name).mkdir(mode=0o700)
    relay = SubscriptionRelay(out, args.model)
    # Set roots before importing xsm modules, even in the controller process.
    for key,value in {'HOME':root/'home','XSM_HOME':root/'state'}.items():
        os.environ[key] = str(value)
    report = {'status':'starting','runtime':args.runtime,'root':str(root),'checks':[],
        'scope':'actual subscribed native owned turns and optional native model tool; generic reference parent; no native UI/messenger',
        'requestedModel':args.model,'subscriptionAuthMode':'oauth',
        'probeSourceSha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
            ('scripts/probe-owned-subscription.py','scripts/probe_subscription_relay.py')}}
    exit_code = asyncio.run(run(args, root, out, relay, report))
    print(json.dumps({key:report.get(key) for key in ('status','runtime','checks','providerRequests','ownedChildrenExited','failure')}))
    raise SystemExit(exit_code)
