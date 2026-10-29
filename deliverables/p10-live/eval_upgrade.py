"""P10 real old-MCP upgrade QA. Product, global runtime and profile settings stay unchanged.

Run from the checkout with PYTHONPATH pointing at it. Only process-local
XSM_HOME/PYTHONPATH overrides and native CLI -c factory injection are used.
No model/allowedTools/bypass/hook-trust correction is performed. The two old
MCP replies deliberately use the default native wake, as authorized by the user.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time
import uuid

from xsm import config, envelope, identity, inbox, install, paths, registry, send

REPO = Path(__file__).resolve().parents[2]
OUTPUT = REPO / 'deliverables' / 'p10-live'
OLD_SOURCE = Path.home() / '.xsm/runtime/2389da782089'


def digest_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def metadata(path):
    try:
        st = Path(path).lstat()
        return {'size': st.st_size, 'mtime_ns': st.st_mtime_ns, 'mode': st.st_mode & 0o777,
                'inode': st.st_ino}
    except FileNotFoundError:
        return None


def guard_inputs():
    """No credential values are opened; auth files are checked by metadata only."""
    settings = {}
    credentials = {}
    for name in ('.codex', '.codex-3'):
        home = Path.home() / name
        for relative in ('config.toml', 'hooks.json', 'settings.json', '.mcp.json'):
            path = home / relative
            settings[str(path)] = digest_file(path) if path.is_file() else None
        for relative in ('auth.json', 'apikey.env'):
            credentials[str(home / relative)] = metadata(home / relative)
    files = {}
    for path in sorted(OLD_SOURCE.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
            files[str(path.relative_to(OLD_SOURCE))] = {'sha256': digest_file(path),
                                                       'mode': metadata(path)['mode']}
    current = Path.home() / '.xsm/runtime/current.json'
    link = Path.home() / '.xsm/runtime/current'
    return {'settings': settings, 'credential_metadata': credentials, 'old_runtime': files,
            'global_current': digest_file(current) if current.is_file() else None,
            'global_link': os.readlink(link) if link.is_symlink() else None}


def actual_controller():
    report = json.loads((REPO / 'deliverables/p08-live/native-memory.json').read_text())
    owners = []
    for path in (Path(report['fixture_state']) / 'owned-requests').glob('*.json'):
        value = json.loads(path.read_text())
        owner = value.get('owner') or {}
        if all(owner.get(k) for k in ('runtime', 'home', 'session_id')):
            owners.append(owner)
    unique = {(r['runtime'], os.path.realpath(r['home']), r['session_id']) for r in owners}
    if len(unique) != 1:
        raise RuntimeError('main controller is not uniquely bound by prior native QA evidence')
    runtime, home, sid = unique.pop()
    current = registry.by_session(runtime, sid)
    if not current or current.get('home') != home or current.get('state') != 'live':
        raise RuntimeError('prior actual main controller is not currently live in its native home')
    return current


def parse_events(path):
    events = []
    if not path.exists():
        return events
    with path.open() as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                events.append(row)
    return events


def tool_calls(events):
    result = []
    for row in events:
        item = row.get('item') or {}
        if row.get('type') != 'item.completed' or item.get('type') != 'mcp_tool_call':
            continue
        args = item.get('arguments') or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                args = {}
        result.append({'server': item.get('server'), 'tool': item.get('tool'),
                       'arguments': args if isinstance(args, dict) else {},
                       'error': bool(item.get('error')), 'raw_item': item})
    return result


def safe_calls(events, marker):
    result = []
    for item in tool_calls(events):
        args = item['arguments']
        selected = {k: args[k] for k in ('kind', 'reply_to', 'outcome', 'wait', 'wake') if k in args}
        text = args.get('text')
        if isinstance(text, str) and re.fullmatch(re.escape(marker) + r'-R[123]\s*[:=]?\s*\d+\s*', text):
            selected['text'] = text
        result.append({'server': item['server'], 'tool': item['tool'],
                       'arguments': selected, 'error': item['error']})
    return result


def fresh_snapshot(source):
    previous_repo = install.REPO
    try:
        install.REPO = str(source)
        expected = install.runtime_digest(str(source), install.SNAPSHOT_FILES)
        if not expected:
            raise RuntimeError('snapshot source digest unavailable')
        snapshot = install.make_snapshot(expected_digest=expected)
        if install.runtime_digest(snapshot['path'], install.SNAPSHOT_FILES) != expected:
            raise RuntimeError('snapshot readback digest differs')
        return snapshot
    finally:
        install.REPO = previous_repo


def alive(pid, start):
    return bool(pid and start and identity.pid_alive(pid) and identity.lstart(pid) == start)


def beacons(prefix):
    rows = []
    for path in Path(paths.path(paths.MCP)).glob('*.json'):
        value = paths.read_json(str(path))
        if not isinstance(value, dict):
            continue
        if os.path.realpath(value.get('cwd') or '') != os.path.realpath(prefix):
            continue
        if alive(value.get('pid'), value.get('lstart')):
            rows.append(value)
    return rows


class Trial:
    def __init__(self, label, snapshot, profile, root, marker, task_count):
        self.label, self.snapshot, self.profile = label, snapshot, profile
        self.root, self.marker, self.task_count = root, marker, task_count
        self.out, self.err = root / (label + '.jsonl'), root / (label + '.stderr')
        self.proc = None
        self.mcp = None
        self.peer = None
        self.owned_mcp = {}

    def start(self):
        old = self.label == 'old'
        send_rule = ('xsm_send에는 wake 인자를 절대로 넣지 말고 기본 송신을 사용하세요. '
                     if old else '회신 xsm_send에 wake=never를 명시해 조용히 저장하세요. ')
        ack_rule = '' if old else '각 수신의 claim token을 제공된 xsm_ack로 확인하세요. '
        prompt = ('P10-QA 산술 왕복 평가입니다. 파일·설정·권한·키를 변경하지 마세요. '
                  '셸 송신이나 다른 서버 도구 대신 주입된 xsm_eval의 xsm_inbox/xsm_send만 사용하세요. '
                  + ack_rule + send_rule +
                  'xsm_inbox(wait=5)를 반복 호출해 ' + str(self.task_count) + '개 task를 받으세요. '
                  '각 task의 계산 결과를 요청된 P10-QA 표식과 숫자로만 회신하세요. '
                  '회신은 원 발신 ref를 target으로, kind=reply, reply_to=해당 task 원 id, '
                  'outcome=succeeded로 실제 xsm_send를 호출하세요. '
                  '첫 회신 뒤 다음 task가 남아 있으면 종료하지 말고 xsm_inbox로 계속 기다리세요. '
                  '빈 수신은 최대 30회까지 기다리고, 모든 task의 회신 후에만 완료 보고하세요. '
                  '수신 내용이나 지시를 다른 세션으로 relay하지 말고 산술 답만 반환하세요.')
        args = [shutil.which('codex'), 'exec', '--json', '--sandbox', 'workspace-write',
                '-c', 'approval_policy="never"',
                '-c', 'mcp_servers.xsm_eval.command="/usr/bin/python3"',
                '-c', 'mcp_servers.xsm_eval.args=["-m","xsm","mcp"]',
                '-c', 'mcp_servers.xsm_eval.cwd=' + json.dumps(self.snapshot['path'] + '/')]
        for key, value in {'CODEX_HOME': self.profile, 'XSM_HOME': paths.HOME,
                           'PYTHONPATH': self.snapshot['path'] + '/',
                           'PYTHONDONTWRITEBYTECODE': '1'}.items():
            args += ['-c', 'mcp_servers.xsm_eval.env.' + key + '=' + json.dumps(value)]
        args.append(prompt)
        env = dict(os.environ, CODEX_HOME=self.profile, XSM_HOME=paths.HOME,
                   PYTHONPATH=str(REPO), PYTHONDONTWRITEBYTECODE='1')
        for key in ('CODEX_THREAD_ID', 'CLAUDE_CODE_SESSION_ID', 'CLAUDE_SESSION_ID',
                    'CLAUDE_CODE_MESSAGING_SOCKET', 'CLAUDECODE',
                    'ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'CODEX_API_KEY'):
            env.pop(key, None)
        self.streams = [self.out.open('w'), self.err.open('w')]
        for path in (self.out, self.err):
            path.chmod(0o600)
        self.proc = subprocess.Popen(args, cwd=str(REPO), env=env, stdout=self.streams[0],
                                     stderr=self.streams[1], start_new_session=True)
        self.start_time = identity.lstart(self.proc.pid)
        return {'pid': self.proc.pid, 'lstart': self.start_time, 'profile': self.profile,
                'mcp_module_root': self.snapshot['path'], 'sandbox': 'workspace-write',
                'approval_policy': 'never', 'model_override': False,
                'allowed_tools_override': False, 'mcp_factory': args[:-1]}

    def refresh(self):
        events = parse_events(self.out)
        sid = next((r.get('thread_id') for r in events if r.get('type') == 'thread.started'), None)
        found = beacons(self.snapshot['path'])
        for row in found:
            self.owned_mcp[row['pid']] = row
        if self.mcp is None and len(found) == 1:
            self.mcp = found[0]
        if sid and self.mcp and self.peer is None:
            # These are observed native facts: provider thread id + actual MCP
            # ancestor pid, never a synthetic session or an unrelated parent.
            pid = self.mcp['ppid']
            if not identity.pid_alive(pid):
                raise RuntimeError('observed native backend PID disappeared')
            self.peer = registry.upsert('codex', self.profile, sid, pid, str(REPO),
                                        name='P10-QA-' + self.label, mcp_pid=self.mcp['pid'])
        return events

    def live_readback(self):
        rows = beacons(self.snapshot['path'])
        return {'native_process_alive': self.proc.poll() is None,
                'native_root_pid': self.proc.pid, 'native_thread': (self.peer or {}).get('session_id'),
                'old_mcp_pid': (self.mcp or {}).get('pid'),
                'same_mcp_generation_alive': bool(self.mcp and alive(self.mcp['pid'], self.mcp['lstart'])),
                'mcp_beacons': [{k: r.get(k) for k in ('pid', 'ppid', 'lstart', 'cwd')} for r in rows],
                'same_mcp_only': len(rows) == 1 and self.mcp is not None and rows[0]['pid'] == self.mcp['pid']}

    def finish(self):
        if not self.proc:
            return []
        actions = []
        if self.proc.poll() is None:
            # This process group was created exclusively for this evaluation.
            if os.getpgid(self.proc.pid) == self.proc.pid:
                os.killpg(self.proc.pid, signal.SIGTERM)
                actions.append({'kind': 'owned-native-group', 'pid': self.proc.pid})
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            if os.getpgid(self.proc.pid) == self.proc.pid:
                os.killpg(self.proc.pid, signal.SIGKILL)
            self.proc.wait(timeout=10)
        self.refresh()
        for pid, row in self.owned_mcp.items():
            if alive(pid, row['lstart']):
                os.kill(pid, signal.SIGTERM)
                actions.append({'kind': 'owned-private-prefix-mcp', 'pid': pid})
        for stream in self.streams:
            stream.close()
        return actions


def wait_until(trial, predicate, timeout, label):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        events = trial.refresh()
        value = predicate(events)
        if value:
            return value
        if trial.proc.poll() is not None:
            raise RuntimeError(label + ': native CLI exited before the required observation')
        time.sleep(0.2)
    raise TimeoutError(label + ': observation deadline reached; not reported as success')


def reply_for(controller, peer, request_id, expected):
    candidates = []
    for item in inbox.peek(controller['session_id']):
        parsed = envelope.parse(item.get('content') or '')
        if (parsed.header.get('kind') == 'reply' and parsed.header.get('reply-to') == request_id
                and parsed.attrs.get('from-session') == peer['session_id'] and parsed.body.strip() == expected
                and parsed.header.get('outcome') == 'succeeded'):
            candidates.append({'id': parsed.header.get('id'), 'reply_to': request_id,
                               'body': parsed.body, 'sender_native': peer['session_id'],
                               'evidence': 'actual reply body in fixture inbox; not a delivery receipt'})
    # Modern replies have canonical originals even if their export was removed.
    for path in Path(paths.path('handoffs')).glob('*/*.json'):
        value = paths.read_json(str(path)) or {}
        msg = value.get('message') or {}
        source = msg.get('sender') or {}
        if (msg.get('kind') == 'reply' and msg.get('reply_to') == request_id and
                source.get('runtime') == peer['runtime'] and source.get('home') == peer['home'] and
                source.get('session_id') == peer['session_id'] and msg.get('body', '').strip() == expected
                and msg.get('outcome') == 'succeeded'):
            candidates.append({'id': value['id'], 'reply_to': request_id, 'body': msg['body'],
                               'sender_native': peer['session_id'],
                               'evidence': 'actual endpoint-bound canonical reply body'})
    unique = {row['id']: row for row in candidates}
    return next(iter(unique.values())) if len(unique) == 1 else None


def roundtrip(trial, controller, number, timeout, persist):
    wait_until(trial, lambda events: trial.peer and trial.mcp, timeout, 'native/MCP startup')
    request_id = envelope.new_id()
    a, b = (2, 2) if number == 1 else (7, 6)
    operator, answer = ('+', a + b) if number == 1 else ('*', a * b)
    expected = '%s-R%d: %d' % (trial.marker, number, answer)
    body = '%s-T%d: %d %s %d 를 계산해 "%s" 형식의 산술 답만 회신하세요.' % (
        trial.marker, number, a, operator, b, trial.marker + '-R' + str(number) + ': 숫자')
    if trial.label == 'old':
        sent = send.send('codex:' + trial.peer['session_id'], body, sender=controller, kind='task',
                          msg_id=request_id)
        send_record = sent.as_dict()
    else:
        from xsm import questions
        send_record = questions.ask(controller, 'codex:' + trial.peer['session_id'], body,
                                     request_id=request_id)
    persist('task-submitted', {'trial': trial.label, 'number': number, 'request_id': request_id,
                              'send_status': send_record.get('status')})
    matched = wait_until(trial, lambda events: reply_for(controller, trial.peer, request_id, expected),
                         timeout, 'correlated reply body')
    live_when_body_observed = trial.live_readback()
    wait_until(trial, lambda events: any(c['server'] == 'xsm_eval' and c['tool'] == 'xsm_send'
                    and c['arguments'].get('reply_to') == request_id and not c['error']
                    for c in tool_calls(events)), timeout, 'completed actual MCP reply call')
    matched.update({'request_id': request_id, 'task_send': send_record,
                    'live_when_body_observed': live_when_body_observed})
    return matched


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', default=str(Path.home() / '.codex-3'))
    parser.add_argument('--new-profile', default=str(Path.home() / '.codex'))
    parser.add_argument('--timeout', type=float, default=180)
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    controller = actual_controller()
    root = Path(tempfile.mkdtemp(prefix='p10-upgrade-', dir='/private/tmp'))
    root.chmod(0o700)
    before = guard_inputs()
    original_home, original_env = paths.HOME, os.environ.get('XSM_HOME')
    paths.HOME = str(root / 'state')
    os.environ['XSM_HOME'] = paths.HOME
    report = {'fixture_root': str(root), 'fixture_state': paths.HOME,
              'old_source': str(OLD_SOURCE), 'controller': {k: controller.get(k) for k in
              ('runtime', 'home', 'session_id', 'ref', 'pid', 'lstart', 'cwd')},
              'condition': 'actual native Codex + actual old snapshot stdio MCP; no permissions correction',
              'events': [], 'trials': [], 'status': 'running', 'cleanup': []}
    trials = []
    output = OUTPUT / 'native-upgrade.json'
    def persist(phase, data=None):
        event = {'phase': phase, 'at': time.time(), **(data or {})}
        report['events'].append(event)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(event, ensure_ascii=False), flush=True)
    try:
        controller = registry.upsert(controller['runtime'], controller['home'], controller['session_id'],
                    controller['pid'], controller['cwd'], name=controller.get('name'))
        old = fresh_snapshot(OLD_SOURCE)
        report['old_snapshot'] = {k: old.get(k) for k in ('id', 'path', 'source', 'made')}
        trial = Trial('old', old, os.path.realpath(args.profile), root, 'P10-QA-' + uuid.uuid4().hex[:10], 2)
        trials.append(trial)
        report['trials'].append({'label': 'old', 'execution': trial.start()})
        persist('old-native-started', {'root_pid': trial.proc.pid, 'old_snapshot': old['id']})
        first = roundtrip(trial, controller, 1, args.timeout, persist)
        report['trials'][0]['first_reply'] = first
        live_before = trial.live_readback()
        if not all(live_before[k] for k in ('native_process_alive', 'same_mcp_generation_alive', 'same_mcp_only')):
            raise RuntimeError('old model/MCP was not live before upgrade; cannot count replacement success')
        report['before_upgrade'] = live_before
        persist('first-old-reply-verified', {'reply_id': first['id'], 'mcp_pid': trial.mcp['pid']})
        new = fresh_snapshot(REPO)
        report['new_snapshot'] = {k: new.get(k) for k in ('id', 'path', 'source', 'made')}
        removed = install.prune_snapshots()
        current = install.runtime_current()
        report['upgrade'] = {'removed': removed, 'old_snapshot_exists': Path(old['path']).is_dir(),
            'current_id': (current or {}).get('id'), 'new_id': new['id'],
            'source_ids_differ': old['id'] != new['id'],
            'old_held_by_process_table': old['id'] in install._running_from(),
            'after_prune': trial.live_readback()}
        persist('private-upgrade-and-prune-observed', {'old_exists': report['upgrade']['old_snapshot_exists'],
                    'current_id': (current or {}).get('id'), 'removed': removed})
        second = roundtrip(trial, controller, 2, args.timeout, persist)
        report['trials'][0]['second_reply'] = second
        report['trials'][0]['tools'] = safe_calls(parse_events(trial.out), trial.marker)
        report['trials'][0]['same_native_conversation'] = first['sender_native'] == second['sender_native']
        report['trials'][0]['old_default_wake_only'] = all('wake' not in c['arguments'] for c in
                                        report['trials'][0]['tools'] if c['tool'] == 'xsm_send')
        persist('second-old-reply-verified', {'reply_id': second['id'], 'native_thread': second['sender_native']})
        # Separate optional condition: actual new snapshot prefix with existing
        # profile hooks; its reply is explicitly quiet, not an old-MCP correction.
        optional = Trial('new', new, os.path.realpath(args.new_profile), root,
                         'P10-QA-' + uuid.uuid4().hex[:10], 1)
        trials.append(optional)
        optional_record = {'label': 'new', 'condition': 'new snapshot MCP + unchanged existing home hooks; quiet reply'}
        report['trials'].append(optional_record)
        try:
            optional_record['execution'] = optional.start()
            optional_record['reply'] = roundtrip(optional, controller, 1, args.timeout, persist)
            optional_record['tools'] = safe_calls(parse_events(optional.out), optional.marker)
            optional_record['status'] = 'passed'
            persist('new-snapshot-roundtrip-verified', {'reply_id': optional_record['reply']['id']})
        except Exception as exc:
            optional_record.update(status='not-verified', error_type=type(exc).__name__, boundary=str(exc))
            persist('new-snapshot-roundtrip-not-verified', {'error_type': type(exc).__name__})
        checks = report['upgrade']
        report['status'] = 'passed' if (checks['old_snapshot_exists'] and checks['source_ids_differ']
            and checks['current_id'] == checks['new_id'] and
            all(checks['after_prune'][k] for k in ('native_process_alive','same_mcp_generation_alive','same_mcp_only'))
            and report['trials'][0]['same_native_conversation'] and report['trials'][0]['old_default_wake_only']) else 'failed'
    except Exception as exc:
        report.update(status='not-verified', error_type=type(exc).__name__, boundary=str(exc))
        persist('required-observation-not-verified', {'error_type': type(exc).__name__, 'boundary': str(exc)})
    finally:
        # Snapshot retention evidence was captured above while the old native
        # session/MCP were alive. Never prune after stopping them to make it pass.
        for trial in trials:
            with contextlib.suppress(Exception):
                report['cleanup'].extend(trial.finish())
            if trial.proc:
                report.setdefault('process_results', []).append({'label': trial.label,
                    'exit_code': trial.proc.returncode, 'events': str(trial.out), 'stderr': str(trial.err)})
        after = guard_inputs()
        report['protection'] = {key + '_unchanged': before[key] == after[key] for key in before}
        report['protection']['credential_values_opened_by_evaluator'] = False
        report['protection']['global_xsm_home_changed'] = False
        if not all(report['protection'][key + '_unchanged'] for key in before):
            report['status'] = 'failed-protected-input-changed'
        paths.HOME = original_home
        if original_env is None:
            os.environ.pop('XSM_HOME', None)
        else:
            os.environ['XSM_HOME'] = original_env
        persist('finished', {'status': report['status'], 'protection': report['protection']})
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
