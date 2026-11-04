#!/usr/bin/env python3
"""Fresh OpenClaw readiness/prewarm, then one actual subscribed native tool turn."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import sys
import time

BASE = Path('/private/tmp/xsm-basic-real')
REPO = Path('/Users/jaesolshin/Documents/GitHub/cross-session-messaging')
sys.path[:0] = [str(BASE), str(REPO), str(REPO / 'scripts'), str(REPO / 'clients/python')]
from probe_native4_once import ObservingOpener, write_json
from native_profiles import configure
from openai_staged_relay import OpenAiSubscriptionRelay


async def run(args, root, report, relay):
    profile, model = configure(args, root, relay)
    env = {k: os.environ[k] for k in ('PATH', 'LANG') if k in os.environ}
    env.update(HOME=str(root / 'home'), XSM_HOME=str(root / 'state'), TMPDIR=str(root / 'tmp') + '/',
        XDG_DATA_HOME=str(root / 'data'), XDG_CACHE_HOME=str(root / 'cache'),
        XSM_PYTHON=sys.executable, PYTHONDONTWRITEBYTECODE='1', OPENCLAW_STATE_DIR=str(profile),
        OPENCLAW_CONFIG_PATH=str(profile / 'openclaw.json'), OPENCLAW_NO_RESPAWN='1',
        XSM_OPENCLAW=str(args.native_cli), XSM_OPENCLAW_NODE=str(args.node))
    os.environ.clear(); os.environ.update(env)
    from xsm import host_install
    from xsm_client import XsmClient
    from probe_owned_observer import OwnedProbeObserver
    observer = client = gateway = None
    gateway_log = None
    service, request_id = 'staged-openclaw', 'one-fresh-native-turn'
    packets = []
    work_deadline = report['_start'] + 160
    relay.absolute_work_deadline = work_deadline
    relay.deadline = work_deadline

    def save():
        report.update(providerRequests=relay.forwarded, nativeHttpArrivals=relay.arrivals,
            responseModelLabels=sorted(relay.response_models), elapsedSeconds=round(time.monotonic() - report['_start'], 3),
            firstProviderRequestAfterSeconds=(round(relay.first_request_monotonic - report['_start'], 3)
                if relay.first_request_monotonic is not None else None))
        write_json(root / 'result.json', {k: v for k, v in report.items() if not k.startswith('_')})

    def check(name, passed):
        if not passed: raise AssertionError(name)
        report['checks'].append(name); save()

    async def measured(name, action):
        started = time.monotonic()
        report['activeStage'] = name; save()
        try:
            result = await action()
        finally:
            report['stages'].append({'name': name, 'startAfterSeconds': round(started - report['_start'], 3),
                'durationSeconds': round(time.monotonic() - started, 3)})
            save()
        return result

    async def native_rpc(method, params):
        command = [str(args.node), str(REPO / 'integrations/openclaw/worker_rpc.mjs'), str(args.native_cli)]
        proc = await asyncio.create_subprocess_exec(*command, cwd=str(root / 'workspace'), env=env,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            start_new_session=True)
        report['prewarmProcessPids'].append(proc.pid)
        payload = json.dumps({'method': method, 'params': params}).encode()
        try:
            out, err = await asyncio.wait_for(proc.communicate(payload), timeout=max(1, min(35, work_deadline - time.monotonic())))
        except BaseException:
            if proc.returncode is None:
                os.killpg(proc.pid, signal.SIGKILL)
                await proc.wait()
            raise
        (root / (method.replace('.', '-') + '.stderr')).write_bytes(err)
        if proc.returncode: raise RuntimeError('native readiness RPC failed: ' + method)
        result = json.loads(out)
        write_json(root / (method.replace('.', '-') + '.json'), result)
        return result

    try:
        async with asyncio.timeout(max(1, work_deadline - time.monotonic())):
            started = time.monotonic()
            installation = host_install.apply('openclaw', str(profile))
            report['runtimeRoot'] = installation['runtime_root']
            report['stages'].append({'name': 'snapshot-install', 'startAfterSeconds': round(started-report['_start'],3),
                'durationSeconds': round(time.monotonic()-started,3)})
            gateway_log = (root / 'gateway.log').open('wb')

            async def gateway_ready():
                nonlocal gateway
                gateway = await asyncio.create_subprocess_exec(str(args.node), str(args.native_cli), 'gateway', 'run',
                    cwd=str(root / 'workspace'), env=env, stdout=gateway_log, stderr=gateway_log, start_new_session=True)
                report['ownedGatewayPid'] = gateway.pid
                port = json.loads((profile / 'openclaw.json').read_text())['gateway']['port']
                while True:
                    if gateway.returncode is not None: raise RuntimeError('fresh gateway exited during readiness')
                    try:
                        _, writer = await asyncio.open_connection('127.0.0.1', port)
                        writer.close(); await writer.wait_closed(); return
                    except OSError: await asyncio.sleep(.1)
            await measured('gateway-listener-readiness', gateway_ready)
            await measured('gateway-health-readiness', lambda: native_rpc('health', {}))
            roster = await measured('agents-list-readiness', lambda: native_rpc('agents.list', {}))
            check('main native agent present in ready roster', any(x.get('id') == 'main' for x in roster.get('agents', [])))
            warm = await measured('non-inference-session-prewarm', lambda: native_rpc('sessions.create', {
                'agentId': 'main', 'cwd': str(root / 'workspace'), 'message': '', 'model': model,
                'idempotencyKey': 'prewarm-' + secrets.token_hex(12)}))
            check('prewarm confirms no native inference was started', warm.get('ok') is True and warm.get('runStarted') is False)
            report['prewarmSessionId'] = warm['sessionId']

            command = [sys.executable, '-B', '-c',
                "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('xsm',run_name='__main__')",
                str(REPO), 'protocol', 'serve', '--stdio']
            client = await XsmClient.connect(command, cwd=str(root / 'workspace'), env=env)
            parent = await client.session_open(runtime='basic-real-reference', profile='user-authorized-staged-test',
                conversation=secrets.token_hex(12), cwd=str(root / 'workspace'), capabilities=['messaging', 'inbox', 'events'])
            report['referenceParticipant'] = parent

            async def op(name, arguments):
                result = await client.operation_call(parent['session'], name, arguments)
                with (root / 'protocol-operations.jsonl').open('a') as stream:
                    stream.write(json.dumps({'operation': name, 'arguments': arguments, 'result': result}, ensure_ascii=False)+'\n')
                if isinstance(result.get('incoming'), dict) and result['incoming'].get('claims'): packets.append(result['incoming'])
                save(); return result

            created = await measured('owned-provider-admission-prewarm', lambda: op('xsm_owned', {
                'action': 'create', 'name': service, 'runtime': 'openclaw', 'home': str(profile), 'model': model}))
            observer = OwnedProbeObserver(root / 'state', parent['ref'], service, created['id'])
            report['nativeProvider'] = observer.worker()['native_provider']
            check('pinned OpenClaw 2026.10.9 admitted', report['nativeProvider']['version'] == '2026.10.9')
            check('readiness and prewarm made zero provider requests', relay.forwarded == 0)
            report['setupSeconds'] = round(time.monotonic()-report['_start'],3)
            report['activeStage'] = 'fresh-native-turn'
            report['nativeSubmissionAfterSeconds'] = round(time.monotonic()-report['_start'],3)
            save()

            nonce = secrets.token_hex(12)
            note, expected = 'XSM_BASIC_REAL_NOTE_' + nonce, 'XSM_BASIC_REAL_DONE_' + nonce
            tool_args = {'target': parent['address'], 'text': note, 'kind': 'note', 'wake': 'never', 'wait': 0}
            prompt = ('This is the user-authorized isolated XSM test. Use the available native xsm_send tool '
                'exactly once with these arguments: '+json.dumps(tool_args)+'. After the tool returns, reply exactly '+expected+
                '. Do not use shell, write files, request approvals, publish, or call other tools.')
            write_json(root / 'requested-turn.json', {'prompt': prompt, 'expectedArguments': tool_args, 'expectedFinal': expected})
            value = await op('xsm_owned', {'action': 'run', 'name': service, 'request_id': request_id,
                'text': prompt, 'work_context': 'one-new-nonce-staged-turn'})
            while value['status'] not in ('sent', 'reply-stored', 'unknown', 'error'):
                if relay.first_request_monotonic is not None and time.monotonic()-relay.first_request_monotonic >= 120:
                    raise TimeoutError('120-second actual provider/native turn budget expired')
                await asyncio.sleep(.15)
                value = await op('xsm_owned', {'action': 'status', 'name': service, 'request_id': request_id})
            report['nativeTurnSeconds'] = round(time.monotonic()-relay.first_request_monotonic,3) if relay.first_request_monotonic else None
            report['nativeSubmissionToResultSeconds'] = round(time.monotonic()-report['_start']-report['nativeSubmissionAfterSeconds'],3)
            report['requestStatus'] = value['status']; write_json(root / 'one-turn-journal.json', value)
            check('actual native answer retained', value['status'] in ('sent', 'reply-stored'))
            check('actual final answer matches new nonce', value['result']['body'] == expected)
            check('actual native session differs from prewarm session', value['result']['native_session_id'] != warm['sessionId'])
            packets.append(await op('xsm_inbox', {}))
            notes, answers = {}, {}
            for packet in packets:
                for claim, body in zip(packet.get('claims', []), packet.get('messages', [])):
                    if note in body: notes[claim['id']] = claim
                    if claim['id'] == value['reply_id'] and expected in body: answers[claim['id']] = claim
            check('actual model xsm_send note received once', len(notes) == 1)
            check('actual native final reply received', len(answers) == 1)
            claims = list(notes.values()) + list(answers.values())
            ack = await op('xsm_ack', {'tokens': [x['token'] for x in claims]})
            check('both actual messages explicitly ACKed', set(ack['acked']) == {x['id'] for x in claims})
            report.update(status='passed', acked=ack['acked'], nativeToolMessageIds=list(notes),
                nativeSessionId=value['result']['native_session_id'], finalReplyId=value['reply_id'])
    except BaseException as error:
        report.update(status='failed', failureType=type(error).__name__, failure=str(error))
    finally:
        cleanup_start = time.monotonic()
        if observer:
            try:
                write_json(root / 'operator-retained-journal.json', observer.request(request_id))
                report['ownedChildrenExited'] = await asyncio.wait_for(asyncio.to_thread(observer.stop_children), timeout=10)
            except Exception as error: report.update(ownedChildrenExited=False, cleanupFailure=type(error).__name__)
        if client:
            try: await asyncio.wait_for(client.close(), timeout=3)
            except Exception as error: report['protocolCloseFailure'] = type(error).__name__
        if gateway:
            if gateway.returncode is None:
                os.killpg(gateway.pid, signal.SIGTERM)
                try: await asyncio.wait_for(gateway.wait(), timeout=3)
                except asyncio.TimeoutError:
                    os.killpg(gateway.pid, signal.SIGKILL); await gateway.wait()
            report['gatewayStopped'] = gateway.returncode is not None
        if gateway_log: gateway_log.close()
        relay.close()
        report.update(cleanupSeconds=round(time.monotonic()-cleanup_start,3), limitFailure=relay.limit_failure,
            nativeArtifacts=[str(p) for p in (root/'state/owned-runs').rglob('*') if p.is_file()])
        save()
    return 0 if report['status']=='passed' and report.get('ownedChildrenExited') and report.get('gatewayStopped') else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-cli', type=Path, required=True)
    parser.add_argument('--node', type=Path, required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); args.runtime = 'openclaw'
    root = args.output.resolve()
    if not root.is_relative_to(BASE) or root.exists(): parser.error('new root under approved temporary directory required')
    started = time.monotonic(); root.mkdir(mode=0o700, parents=True)
    for name in ('home','state','workspace','tmp','data','cache'): (root/name).mkdir(mode=0o700)
    report = {'status':'starting','runtime':'openclaw','requestedModel':args.model,'root':str(root),
        '_start':started,'checks':[],'stages':[],'prewarmProcessPids':[],
        'maxTotalSeconds':180,'controllerWorkDeadlineSeconds':160,'maxNativeTurnSeconds':120,'maxProviderRequests':8,
        'automaticRetry':False,'configurationChange':'readiness/snapshot/non-inference prewarm separated from new native turn; same policy/schema/model arguments',
        'limits':['generic reference receiver; not native-native pair','publish/typed-consent not tested','previous failure root unchanged']}
    write_json(root/'configuration-reason.json', {k:v for k,v in report.items() if not k.startswith('_')})
    write_json(root/'result.json', {k:v for k,v in report.items() if not k.startswith('_')})
    try:
        relay = OpenAiSubscriptionRelay(root, args.model, max_requests=8)
        relay.opener = ObservingOpener(relay.opener, root, report)
        exit_code = asyncio.run(run(args, root, report, relay))
    except BaseException as error:
        report.update(status='failed-preflight',failureType=type(error).__name__,failure=str(error),
            providerRequests=0,elapsedSeconds=round(time.monotonic()-started,3))
        write_json(root/'result.json', {k:v for k,v in report.items() if not k.startswith('_')}); exit_code=1
    print(json.dumps({k:report.get(k) for k in ('status','root','setupSeconds','firstProviderRequestAfterSeconds',
        'nativeTurnSeconds','nativeSubmissionToResultSeconds','providerRequests','responseModelLabels','acked',
        'elapsedSeconds','failureType','failure','ownedChildrenExited','gatewayStopped')},ensure_ascii=False))
    raise SystemExit(exit_code)
