#!/usr/bin/env python3
"""One real subscribed native tool turn; no fixtures or consent overrides."""
import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import sys
import threading
import time
import urllib.error

REPO = Path('/Users/jaesolshin/Documents/GitHub/cross-session-messaging')
BASE = Path('/private/tmp/xsm-basic-real')
sys.path[:0] = [str(REPO), str(REPO / 'scripts'), str(REPO / 'clients/python')]
from probe_subscription_relay import SubscriptionRelay


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    path.chmod(0o600)


class ObservingOpener:
    """Record unmodified upstream response bytes; never create an answer."""
    def __init__(self, original, root, report):
        self.original, self.root, self.report = original, root, report
        self.serial, self.lock = 0, threading.Lock()

    def open(self, request, **kwargs):
        try:
            response = self.original.open(request, **kwargs)
        except urllib.error.HTTPError as error:
            response = error
        with self.lock:
            self.serial += 1
            serial = self.serial
        owner = self

        class Response:
            code, headers = response.code, response.headers

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                response.close()

            def read(self, size=-1):
                payload = response.read(size)
                filename = owner.root / ('upstream-%02d.body' % serial)
                filename.write_bytes(payload)
                filename.chmod(0o600)
                observation = {'request': serial, 'httpStatus': response.code,
                               'rawBody': str(filename), 'responseBytes': len(payload)}
                if response.code >= 400:
                    try:
                        error = json.loads(payload).get('error', {})
                        if not isinstance(error, dict):
                            error = {'message': str(error)}
                        observation['error'] = {k: error[k] for k in ('type', 'code', 'message') if k in error}
                    except (ValueError, AttributeError):
                        observation['errorBodyNotJson'] = True
                    observation['quota400'] = response.code == 400 and bool(re.search(
                        r'extra.?usage|quota|usage.?limit|credit|insufficient|out.of',
                        payload.decode('utf-8', errors='replace'), re.I))
                with owner.lock:
                    owner.report.setdefault('upstreamResponses', []).append(observation)
                    write_json(owner.root / 'upstream-observations.json', owner.report['upstreamResponses'])
                return payload

        return Response()


def options():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', choices=('pi', 'opencode'), required=True)
    parser.add_argument('--native-cli', type=Path, required=True)
    parser.add_argument('--native-deps-root', type=Path)
    parser.add_argument('--model', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.output.is_absolute() or not args.output.is_relative_to(BASE):
        parser.error('output must be under /private/tmp/xsm-basic-real')
    if args.output.exists() or not args.native_cli.is_absolute() or not args.native_cli.is_file():
        parser.error('new output and existing absolute native CLI required')
    args.native_tools = True
    return args


async def run(args, root, report, relay):
    spec = importlib.util.spec_from_file_location('existing_subscription_profile', REPO / 'scripts/probe-owned-subscription.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    profile, model = helper.profile_config(args, root, relay)
    env = {k: os.environ[k] for k in ('PATH', 'LANG') if k in os.environ}
    env.update(HOME=str(root / 'home'), XSM_HOME=str(root / 'state'),
               TMPDIR=str(root / 'tmp') + '/', XDG_DATA_HOME=str(root / 'data'),
               XDG_CACHE_HOME=str(root / 'cache'), XSM_PYTHON=sys.executable,
               PYTHONDONTWRITEBYTECODE='1')
    if args.runtime == 'pi':
        env.update(PI_CODING_AGENT_DIR=str(profile), XSM_PI=str(args.native_cli))
    else:
        env.update(OPENCODE_CONFIG_DIR=str(profile), XSM_OPENCODE=str(args.native_cli),
                   OPENCODE_DISABLE_DEFAULT_PLUGINS='1', OPENCODE_DISABLE_MODELS_FETCH='1')
    os.environ.clear()
    os.environ.update(env)
    from xsm import host_install
    from xsm_client import XsmClient
    from probe_owned_observer import OwnedProbeObserver
    client = observer = None
    service, request_id = 'basic-' + args.runtime, 'one-native-turn'
    packets = []

    def save():
        report.update(providerRequests=relay.forwarded, responseModelLabels=sorted(relay.response_models),
                      elapsedSeconds=round(time.monotonic() - report['_monotonic'], 3))
        write_json(root / 'result.json', {k: v for k, v in report.items() if not k.startswith('_')})

    def check(name, value):
        if not value:
            raise AssertionError(name)
        report['checks'].append(name)
        save()

    try:
        async with asyncio.timeout(92):
            installation = host_install.apply(args.runtime, str(profile))
            report['runtimeRoot'] = installation['runtime_root']
            command = [sys.executable, '-B', '-c',
                "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('xsm',run_name='__main__')",
                str(REPO), 'protocol', 'serve', '--stdio']
            client = await XsmClient.connect(command, cwd=str(root / 'workspace'), env=env)
            parent = await client.session_open(runtime='basic-real-reference', profile='user-authorized-isolated-test',
                conversation=secrets.token_hex(8), cwd=str(root / 'workspace'), capabilities=['messaging', 'inbox', 'events'])
            report['referenceParticipant'] = parent

            async def op(name, arguments):
                value = await client.operation_call(parent['session'], name, arguments)
                with (root / 'protocol-operations.jsonl').open('a') as stream:
                    stream.write(json.dumps({'operation': name, 'arguments': arguments, 'result': value}, ensure_ascii=False) + '\n')
                if isinstance(value.get('incoming'), dict) and value['incoming'].get('claims'):
                    packets.append(value['incoming'])
                save()
                return value

            created = await op('xsm_owned', {'action': 'create', 'name': service, 'runtime': args.runtime,
                'home': str(profile), 'model': model})
            check('owned native service admitted', created.get('owned') is True)
            observer = OwnedProbeObserver(root / 'state', parent['ref'], service, created['id'])
            report['nativeProvider'] = observer.worker()['native_provider']
            check('pinned native provider version', report['nativeProvider']['version'] ==
                  ('1.4.0' if args.runtime == 'pi' else '1.19.5'))
            nonce = secrets.token_hex(12)
            note, expected = 'XSM_BASIC_REAL_NOTE_' + nonce, 'XSM_BASIC_REAL_DONE_' + nonce
            tool_args = {'target': parent['address'], 'text': note, 'kind': 'note', 'wake': 'never', 'wait': 0}
            prompt = ('This is the user-authorized isolated XSM test. Use the available native xsm_send tool '
                      'exactly once with these arguments: ' + json.dumps(tool_args) +
                      '. After the tool returns, reply exactly ' + expected +
                      '. Do not use shell, write files, request approvals, publish, or call other tools.')
            write_json(root / 'requested-turn.json', {'prompt': prompt, 'expectedTool': 'xsm_send',
                       'expectedArguments': tool_args, 'expectedFinal': expected})
            value = await op('xsm_owned', {'action': 'run', 'name': service, 'request_id': request_id,
                'text': prompt, 'work_context': 'one-real-basic-turn'})
            while value['status'] not in ('sent', 'reply-stored', 'unknown', 'error'):
                await asyncio.sleep(.1)
                value = await op('xsm_owned', {'action': 'status', 'name': service, 'request_id': request_id})
            write_json(root / 'one-turn-journal.json', value)
            report['requestStatus'] = value['status']
            check('actual model answer saved', value['status'] in ('sent', 'reply-stored'))
            check('actual final reply matches nonce', value['result']['body'] == expected)
            check('native completion did not manufacture task outcome', value['result']['outcome'] is None)
            packets.append(await op('xsm_inbox', {}))
            notes, answers = {}, {}
            for packet in packets:
                for claim, body in zip(packet.get('claims', []), packet.get('messages', [])):
                    if note in body:
                        notes[claim['id']] = claim
                    if claim['id'] == value['reply_id'] and expected in body:
                        answers[claim['id']] = claim
            check('native model tool sent one actual canonical note', len(notes) == 1)
            check('actual native final reply read in protocol inbox', len(answers) == 1)
            claims = list(notes.values()) + list(answers.values())
            ack = await op('xsm_ack', {'tokens': [c['token'] for c in claims]})
            check('tool note and final reply explicitly ACKed', set(ack['acked']) == {c['id'] for c in claims})
            report.update(nativeToolMessageIds=list(notes), finalReplyId=value['reply_id'], acked=ack['acked'],
                          nativeSessionId=value['result']['native_session_id'], status='passed')
    except BaseException as error:
        report.update(status='failed', failureType=type(error).__name__, failure=str(error))
    finally:
        if observer:
            try:
                write_json(root / 'operator-retained-journal.json', observer.request(request_id))
                report['ownedChildrenExited'] = await asyncio.wait_for(asyncio.to_thread(observer.stop_children), timeout=12)
            except Exception as error:
                report.update(ownedChildrenExited=False, cleanupFailure=type(error).__name__)
        if client:
            try:
                await asyncio.wait_for(client.close(), timeout=6)
            except Exception as error:
                report['protocolCloseFailure'] = type(error).__name__
        relay.close()
        report['quota400'] = any(r.get('quota400') for r in report.get('upstreamResponses', []))
        report['nativeArtifacts'] = [str(p) for p in (root / 'state' / 'owned-runs').rglob('*') if p.is_file()]
        save()
    return 0 if report['status'] == 'passed' and report.get('ownedChildrenExited') else 1


if __name__ == '__main__':
    args = options()
    started = time.monotonic()
    root = args.output.resolve()
    root.mkdir(parents=True, mode=0o700)
    root.chmod(0o700)
    for name in ('home', 'state', 'workspace', 'tmp', 'data', 'cache'):
        (root / name).mkdir(mode=0o700)
    report = {'status': 'starting', 'runtime': args.runtime, 'root': str(root), 'checks': [],
        '_monotonic': started, 'requestedModel': args.model, 'subscriptionAuthMode': 'oauth',
        'maxProviderRequests': 8, 'maxRuntimeSeconds': 120, 'automaticRetry': False,
        'scope': 'one actual native model tool turn, generic reference receiver, real protocol inbox and ACK',
        'limits': ['generic reference parent; not two native participants', 'publish consent not exercised',
                   'Claude/Codex user sessions not touched', 'no fixtures, approval synthesis, or API keys']}
    report['sourceSha256'] = {name: hashlib.sha256((REPO / name).read_bytes()).hexdigest() for name in (
        'scripts/probe-owned-subscription.py', 'scripts/probe_subscription_relay.py',
        'integrations/pi/xsm.mjs', 'xsm/operations.py', 'xsm/operation_schema.py')}
    write_json(root / 'result.json', {k: v for k, v in report.items() if not k.startswith('_')})
    relay = SubscriptionRelay(root, args.model, max_requests=8)
    relay.server.daemon_threads = True
    relay.opener = ObservingOpener(relay.opener, root, report)
    exit_code = asyncio.run(run(args, root, report, relay))
    print(json.dumps({k: report.get(k) for k in ('status', 'runtime', 'root', 'providerRequests',
        'responseModelLabels', 'quota400', 'requestStatus', 'failureType', 'failure',
        'ownedChildrenExited', 'elapsedSeconds')}, ensure_ascii=False))
    raise SystemExit(exit_code)
