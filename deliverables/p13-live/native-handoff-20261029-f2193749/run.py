"""One native interruption specimen. The controller never writes product state."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
SOURCE = Path('/private/tmp/xsm-p13-local-frozen-dn7tom1y')
PROFILE = Path('/Users/jaesolshin/.codex-3')
CLI = '/opt/homebrew/bin/codex'
DEADLINE = datetime.datetime.fromisoformat('2026-10-28T20:04:35+00:00').timestamp()
RECEIVER_GOAL = ('이 작업공간의 검토 담당입니다. 동료로부터 들어오는 짧은 산술 점검 요청을 받아 '
                 '독립적으로 검토하고 결과를 동료에게 돌려주세요. 아직 요청이 없으면 잠시 기다려주세요. '
                 '읽어 처리한 요청은 확인 표시하고, 끝낸 일이 다시 남아 있지 않은지도 살펴본 뒤 결과를 보고하세요.')
SENDER_GOAL = ('이 작업공간의 검토 담당 동료를 찾아 2+2=5라는 주장을 검토받으세요. '
               '반례와 올바른 합을 실제 동료의 답으로 확인한 뒤 보고하세요. '
               '한 번 맡긴 요청은 답을 기다리거나 회수하고 새 요청으로 중복시키지 마세요. '
               '다른 대화나 폴더의 권한을 바꾸지는 마세요.')
RESUME_GOAL = ('중단된 검토 업무를 이어서 마무리하세요. 아직 처리하지 못한 동료 요청을 회수해 '
               '독립 검토하고 결과를 원래 동료에게 돌려주세요. 읽어 처리한 요청은 확인 표시하고, '
               '끝낸 일이 다시 남아 있지 않은지도 살펴본 뒤 결과를 보고하세요.')
actors = []
out = {'scope': 'A18-02/J05 single real native consumer interruption specimen',
       'root': str(ROOT), 'source': str(SOURCE), 'status': 'in-progress',
       'native_invocations': [], 'coordinator_resume_calls': 0,
       'additional_human_inputs': 0, 'automatic_retry_runs': 0,
       'controller_product_state_writes': 0, 'proxy_synthetic_results': 0}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(name, value):
    target = ROOT / name
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    target.chmod(0o600)


def read(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def start(pid):
    return subprocess.run(['ps', '-o', 'lstart=', '-p', str(pid)],
                          capture_output=True, text=True).stdout.strip() or None


def events(path):
    try:
        lines = Path(path).read_text().splitlines()
    except OSError:
        return []
    result = []
    for line in lines:
        try:
            result.append(json.loads(line))
        except ValueError:
            pass
    return result


def guard():
    return {name: sha((PROFILE / name).read_bytes()) if (PROFILE / name).is_file() else None
            for name in ('config.toml', 'hooks.json', 'settings.json')}


def snapshot():
    return {str(p.relative_to(SOURCE)): sha(p.read_bytes()) for parent in ('xsm', 'hooks', 'skills')
            for p in sorted((SOURCE / parent).rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}


def launch(role, goal, cid=None):
    folder = ROOT / role
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(('CLAUDE', 'XSM', 'CODEX_')) or key in ('OPENAI_API_KEY', 'OPENAI_BASE_URL', 'ANTHROPIC_API_KEY'):
            env.pop(key, None)
    env.update(CODEX_HOME=str(PROFILE), XSM_HOME=str(ROOT / 'state'),
               PYTHONPATH=str(SOURCE), PYTHONDONTWRITEBYTECODE='1')
    argv = [CLI, 'exec', '--ignore-user-config', '--ignore-rules', '--json',
            '--sandbox', 'read-only', '--skip-git-repo-check']
    for feature in ('hooks', 'plugins', 'apps', 'shell_tool', 'shell_snapshot', 'remote_plugin'):
        argv += ['--disable', feature]
    cfg = {'approval_policy': 'never', 'sandbox_mode': 'read-only', 'project_doc_max_bytes': 0,
           'model_instructions_file': str(ROOT / 'product-instructions.md'),
           'log_dir': str(folder / 'logs'), 'mcp_servers.xsm.command': '/usr/bin/python3',
           'mcp_servers.xsm.args': [str(ROOT / 'proxy.py'), str(folder), str(SOURCE),
                                    'fault' if role == 'receiver-initial' else 'pass'],
           'mcp_servers.xsm.cwd': str(SOURCE), 'mcp_servers.xsm.startup_timeout_sec': 20,
           'mcp_servers.xsm.tool_timeout_sec': 180}
    for key in ('CODEX_HOME', 'XSM_HOME', 'PYTHONPATH', 'PYTHONDONTWRITEBYTECODE'):
        cfg['mcp_servers.xsm.env.' + key] = env[key]
    for key, value in cfg.items():
        argv += ['-c', key + '=' + json.dumps(value, ensure_ascii=False)]
    argv += ['--output-last-message', str(folder / 'last-message.txt')]
    if cid:
        argv += ['resume', cid, '-']
    else:
        argv += ['-']
    streams = [(folder / 'native.jsonl').open('w'), (folder / 'native.stderr').open('w')]
    proc = subprocess.Popen(argv, cwd=str(ROOT / 'work'), env=env, stdin=subprocess.PIPE,
                            stdout=streams[0], stderr=streams[1], text=True, start_new_session=True)
    proc.stdin.write(goal)
    proc.stdin.close()
    entry = {'role': role, 'pid': proc.pid, 'lstart': start(proc.pid),
             'alive_after_start': proc.poll() is None, 'argv': argv, 'goal': goal,
             'goal_sha256': sha(goal.encode()), 'resume_requested_cid': cid}
    actor = {'proc': proc, 'streams': streams, 'entry': entry, 'folder': folder}
    actors.append(actor)
    out['native_invocations'].append(entry)
    save('result.json', out)
    return actor


def cid(actor):
    return next((r.get('thread_id') for r in events(actor['folder'] / 'native.jsonl')
                 if r.get('type') == 'thread.started'), None)


def pointer(actor):
    value = cid(actor)
    for path in (ROOT / 'state/sessions').glob('*.json'):
        row = read(path)
        if row and row.get('session_id') == value and row.get('home') == str(PROFILE):
            return row
    return None


def until(fn, timeout, label):
    end = min(time.time() + timeout, DEADLINE - 45)
    while time.time() < end:
        value = fn()
        if value:
            return value
        time.sleep(.1)
    raise RuntimeError(label)


def kill_exact(pid, expected, label):
    actual = start(pid)
    result = {'pid': pid, 'recorded_lstart': expected, 'observed_lstart': actual, 'label': label}
    if actual is None:
        result['already_exited'] = True
    elif actual == expected:
        os.kill(pid, signal.SIGKILL)
        result['signal'] = 'SIGKILL'
    else:
        raise RuntimeError('refuse to signal changed PID ' + label)
    return result


try:
    out['started_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    out['profile_guard_before'] = guard()
    source_files = snapshot()
    save('source-manifest.json', source_files)
    out['source_manifest_sha256'] = sha(json.dumps(source_files, sort_keys=True).encode())
    receiver = launch('receiver-initial', RECEIVER_GOAL)
    def receiver_registered():
        value = pointer(receiver)
        if receiver['proc'].poll() is not None:
            raise RuntimeError('receiver exited before natural native registration; no controller repair')
        return value
    initial = until(receiver_registered, 100, 'native receiver identity was not registered naturally')
    out['receiver_initial_identity'] = initial
    save('result.json', out)
    sender = launch('sender', SENDER_GOAL)
    fault = until(lambda: read(receiver['folder'] / 'fault-observed.json'), 180,
                  'no actual xsm_inbox claim reached the single fault boundary')
    out['fault'] = fault
    original_id = fault['claims'][0]['id']
    original_file = until(lambda: next((p for p in (ROOT / 'state/handoffs').glob('*/*.json')
                                       if (read(p) or {}).get('id') == original_id), None),
                          5, 'canonical original not found after actual claim')
    before = read(original_file)
    out['before_interruption'] = before
    out['original_file'] = str(original_file)
    out['sender_identity'] = pointer(sender)
    assert before['state'] == 'handoff-recorded'
    assert before['receiver']['session_id'] == cid(receiver)
    assert not any(row.get('id') == fault['actual_request'].get('id')
                   for row in events(receiver['folder'] / 'forwarded.jsonl'))
    handles = read(receiver['folder'] / 'handles.json')
    out['fault_cleanup'] = [kill_exact(receiver['proc'].pid, receiver['entry']['lstart'], 'own interrupted native CLI')]
    for role in ('server', 'proxy'):
        out['fault_cleanup'].append(kill_exact(handles[role + '_pid'], handles[role + '_lstart'], 'own interrupted ' + role))
    receiver['proc'].wait(timeout=10)
    out['after_kill_before_resume'] = read(original_file)
    out['receiver_native_cid'] = cid(receiver)
    out['coordinator_resume_calls'] = 1
    save('result.json', out)
    resumed = launch('receiver-resume', RESUME_GOAL, cid=out['receiver_native_cid'])
    until(lambda: resumed['proc'].poll() is not None and sender['proc'].poll() is not None,
          240, 'resumed receiver/sender did not finish in bounded specimen')
    out['receiver_resume_cid'] = cid(resumed)
    out['same_native_conversation'] = out['receiver_native_cid'] == cid(resumed)
    out['receiver_resume_identity'] = pointer(resumed)
    out['after_native_work'] = read(original_file)
    out['question_record'] = read(ROOT / 'state/questions' / (original_id + '.json'))
    out['status'] = 'executed; evaluate original evidence'
except BaseException as exc:
    out['status'] = 'failed-original-specimen; no automatic retry'
    out['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
finally:
    cleanup = []
    for actor in actors:
        proc, entry = actor['proc'], actor['entry']
        if proc.poll() is None:
            try:
                cleanup.append(kill_exact(proc.pid, entry['lstart'], 'bounded own CLI cleanup'))
                proc.wait(timeout=10)
            except Exception as exc:
                cleanup.append({'error': str(exc), 'pid': proc.pid})
        entry['exit_code'] = proc.poll()
        entry['observed_cid'] = cid(actor)
        h = read(actor['folder'] / 'handles.json') or {}
        for role in ('server', 'proxy'):
            if h.get(role + '_pid') and start(h[role + '_pid']):
                try:
                    cleanup.append(kill_exact(h[role + '_pid'], h[role + '_lstart'], 'bounded own MCP cleanup'))
                except Exception as exc:
                    cleanup.append({'error': str(exc)})
        for stream in actor['streams']:
            stream.close()
    out['cleanup'] = cleanup
    out['profile_guard_after'] = guard()
    out['profile_configuration_unchanged'] = out['profile_guard_before'] == out['profile_guard_after']
    out['frozen_source_unchanged'] = source_files == snapshot()
    out['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save('result.json', out)
    print(json.dumps({'status': out['status'], 'failure': out.get('failure'),
                      'native_invocations': len(actors), 'root': str(ROOT)}, ensure_ascii=False), flush=True)
