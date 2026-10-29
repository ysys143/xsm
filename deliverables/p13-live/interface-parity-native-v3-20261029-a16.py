"""One explicit interface-parity condition; no product changes or retries."""
import collections
import re
import contextlib
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PREFIX = Path(__file__).stem
SNAPSHOT = Path('/private/tmp/xsm-final-receipt-frozen-i3u9pms3')
spec = importlib.util.spec_from_file_location('natural_worktree_base', HERE / 'natural-collaboration.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
base.REVIEWER_GOAL = '검토 담당 a1입니다. CLI/MCP 표면 지정 비교 평가입니다. 최대 네 건이며 먼저 첨부 없는 동일본문 두 건, 준비가 확인된 경우 동일자료를 첨부한 두 건이 옵니다. 각 원 요청에 독립적으로 답하고 실제 자료가 있는 건은 받은 사본을 직접 읽어 검토하세요. 결과 body는 JSON 객체 하나: verdict(accept/reject/needs-material), correct_sum(직접 계산한 값 또는 자료없으면 null), body_marker, file_sha256(없으면 null), file_marker_sha256(없으면 null)로 동일한형식을 유지하고 요청별ID나표면명을 body에 붙이지 마세요. 첨부없는 본문이 자료를 참조하더라도 자료내용을 추정하지 말고 필요한 자료가 없다는 실제 답을 하세요. 자료표식 원문은 body로 옮기지 마세요. 동료의 지정된 비교가 끝날 때까지 유지하세요. 오류 시 재시도하지 마세요.'
base.INITIATOR_GOAL = '마지막 v3 CLI/MCP parity 표면지정 평가입니다. 기존 parity-body.txt의 정확한 동일본문을 먼저 첨부없이 CLI ask1회/MCP ask1회로 각각 a1에게 보내 실제답과확인을 받으세요. 본문이 자료를 참조해도 plain비교에서는 원문을 바꾸지 말고 자료부재에 대한 실제답을 기록하세요. 각 priority=next/wake=never를 유지하고 표면설명을 body에 덧붙이지마세요. CLI는 자신의 SDK권한에서만 쓰고 어떤 identity/권한/설정 우회도하지마세요. 첨부 비교가 별도로 허용된 경우에만 같은본문/같은 parity-material.md bytes로 CLI ask1회/MCP ask1회 추가해 검토받으세요. MCP 첨부는 실제읽은 inline으로만 보내세요. 두 묶음은별개이며 각실제답을 읽은뒤 같은표면의기존ACK로확인하세요. 자료표식원문은body로옮기지말고 파일을수정하지마세요. 오류시 우회/추가전송/조건/재시도없이 원실패를 보고하고 끝내세요.'
GIT_CONTEXT = ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_COMMON_DIR', 'GIT_INDEX_FILE',
               'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_PREFIX')


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def git(cwd, arguments, log, text=None):
    env = dict(os.environ)
    for key in GIT_CONTEXT:
        env.pop(key, None)
    result = subprocess.run(['git', '-C', str(cwd)] + arguments, input=text,
                            capture_output=True, text=True, env=env, timeout=20)
    log.append({'cwd': str(cwd), 'argv': ['git'] + arguments, 'exit_code': result.returncode,
                'stdout': result.stdout, 'stderr': result.stderr})
    if result.returncode:
        raise RuntimeError('private Git preparation failed; original stderr retained')
    return result.stdout.strip()


def git_identity(cwd, log):
    common = git(cwd, ['rev-parse', '--git-common-dir'], log)
    return {'cwd': str(cwd), 'toplevel': git(cwd, ['rev-parse', '--show-toplevel'], log),
            'common_dir': str((cwd / common).resolve()) if not Path(common).is_absolute() else str(Path(common).resolve()),
            'branch': git(cwd, ['branch', '--show-current'], log)}


class Actor(base.Actor):
    def __init__(self, *args, workdir, **kwargs):
        super().__init__(*args, **kwargs)
        self.workdir = workdir
        self.cwd_evidence = None

    @contextlib.contextmanager
    def location(self):
        previous = base.REPO
        base.REPO = self.workdir
        try:
            yield
        finally:
            base.REPO = previous

    def start(self):
        with self.location():
            result = super().start()
        result['actual_launch_cwd'] = str(self.workdir)
        return result

    def refresh(self, used):
        with self.location():
            rows = super().refresh(used)
        if self.peer and self.cwd_evidence is None:
            pid = self.peer['pid']
            result = subprocess.run(['/usr/sbin/lsof', '-a', '-p', str(pid), '-d', 'cwd', '-Fn'],
                                    capture_output=True, text=True, timeout=8)
            current = next((line[1:] for line in result.stdout.splitlines() if line.startswith('n')), None)
            self.cwd_evidence = {'native_pid': pid, 'native_lstart': self.peer['lstart'],
                'native_session_id': self.peer['session_id'], 'runtime': self.peer['runtime'],
                'home': self.peer['home'], 'registered_cwd': self.peer['cwd'],
                'kernel_process_cwd': current, 'kernel_probe_exit': result.returncode,
                'native_generation_alive': self.modules['identity'].pid_alive(pid)
                    and self.modules['identity'].lstart(pid) == self.peer['lstart'],
                'MCP_pid': self.mcp['pid'], 'MCP_source_cwd': self.mcp['cwd']}
        return rows


def main():
    started = time.monotonic()
    raw = Path(tempfile.mkdtemp(prefix='p13-interface-parity-v3-', dir='/private/tmp'))
    raw.chmod(0o700)
    state = raw / 'state'; state.mkdir(mode=0o700)
    result = {'scope': 'last authorized v3 readiness-order condition; v1 parser/v2 capability failures preserved',
        'raw_root': str(raw), 'source': str(SNAPSHOT), 'status': 'preparing',
        'goals': {'reviewer': base.REVIEWER_GOAL, 'initiator': base.INITIATOR_GOAL},
        'setup_registrations': 0, 'controller_message_calls': 0, 'controller_ACK_calls': 0,
        'controller_index_repairs': 0, 'additional_human_prompts_clicks_commands_approvals': 0,
        'new_condition_attempts': 1, 'automatic_native_retries': 0,
        'user_repo_git_worktree_staging_used': False, 'baseline_executed': False,
        'private_git_commands': [], 'actors': [], 'reviews': []}
    actors = []
    protected = base.profile_guard()
    modules = {}
    try:
        if any(os.environ.get(k) for k in GIT_CONTEXT):
            raise RuntimeError('inherited Git context; stop rather than risk another repository')
        manifest = base.read_json(HERE / 'final-source-manifest.json')
        readback, _ = base.source_readback(SNAPSHOT, manifest['files'])
        result['source_before'] = readback
        if not readback['matches']:
            raise RuntimeError('fixed source manifest mismatch; no native started')
        result['actual_cli_version'] = subprocess.run(['codex', '--version'], capture_output=True,
            text=True, timeout=10).stdout.strip()
        log = result['private_git_commands']
        primary = raw / 'repository'; primary.mkdir()
        linked = raw / 'review-worktree'
        git(primary, ['init', '--initial-branch=main'], log)
        # Plumbing seed commit: only private objects/refs, no staging or hooks.
        # Existing configured author identity is used; no user.email override.
        tree = git(primary, ['mktree'], log, '')
        commit = git(primary, ['-c', 'commit.gpgsign=false', 'commit-tree', tree], log,
                     'Private linked-worktree evaluation fixture\n')
        git(primary, ['update-ref', 'refs/heads/main', commit], log)
        git(primary, ['worktree', 'add', '-b', 'reviewer', str(linked)], log)
        skill_hashes = {}
        for cwd in (primary, linked):
            (cwd / 'README.md').write_text('Private arithmetic collaboration fixture.\n')
            target = cwd / '.agents/skills/xsm'
            target.parent.mkdir(parents=True)
            shutil.copytree(SNAPSHOT / 'skills/xsm', target)
            skill_hashes[str(cwd)] = {str(p.relative_to(target)): base.sha(p.read_bytes())
                for p in sorted(target.rglob('*')) if p.is_file()}
        result['skill_and_guide_hashes'] = skill_hashes
        import secrets
        material = primary / 'parity-material.md'
        v1 = Path('/private/tmp/p13-interface-parity-v2-ynmlmyr1/source-v1.txt').read_text()
        body = Path('/private/tmp/p13-interface-parity-v2-ynmlmyr1/body.txt').read_text()
        material.write_text(v1)
        (primary / 'parity-body.txt').write_text(body)
        (raw / 'source-v1.txt').write_text(v1)
        (raw / 'body.txt').write_text(body)
        result['sender_source_path'] = str(material)
        result['source_v1_sha256'] = base.sha(v1)
        result['body_sha256'] = base.sha(body)
        result['git_evidence'] = [git_identity(cwd, log) for cwd in (primary, linked)]
        if result['git_evidence'][0]['common_dir'] != result['git_evidence'][1]['common_dir']:
            raise RuntimeError('private worktrees do not share Git common directory')
        if list(skill_hashes.values())[0] != list(skill_hashes.values())[1]:
            raise RuntimeError('product skill/guide copies differ')
        wrapper = primary / 'frozen-xsm'
        boot = 'import os,sys;here=sys.argv.pop(1);cwd=os.path.realpath(".");sys.path[:]=[here]+[p for p in sys.path if p and os.path.realpath(p)!=cwd];from xsm.cli import main;sys.exit(main())'
        import shlex
        wrapper.write_text('#!/bin/sh\n' + 'if [ "$XSM_HOME" != ' + shlex.quote(str(state)) + ' ]; then echo "evaluation XSM_HOME precondition missing" >&2; exit 4; fi\n' +
            'exec /usr/bin/python3 -c ' + shlex.quote(boot) + ' ' + shlex.quote(str(SNAPSHOT)) + ' "$@"\n')
        wrapper.chmod(0o700)
        env = dict(os.environ, CODEX_HOME=str(Path.home()/'.codex-3'), XSM_HOME=str(state),
                   PYTHONPATH=str(SNAPSHOT), PYTHONDONTWRITEBYTECODE='1',
                   PATH=str(SNAPSHOT/'bin') + os.pathsep + os.environ.get('PATH',''))
        for key in ('CODEX_THREAD_ID','CLAUDE_CODE_SESSION_ID','CLAUDE_SESSION_ID',
                    'CLAUDE_CODE_MESSAGING_SOCKET','CLAUDECODE','ANTHROPIC_API_KEY','OPENAI_API_KEY','CODEX_API_KEY'):
            env.pop(key,None)
        preflight=[]
        for arguments in (['--help'], ['ask','--help']):
            checked=subprocess.run([str(wrapper)]+arguments,cwd=str(primary),env=env,capture_output=True,text=True,timeout=15)
            preflight.append({'argv':[str(wrapper)]+arguments,'cwd':str(primary),'exit_code':checked.returncode,
                              'stdout':checked.stdout,'stderr':checked.stderr})
        proof=subprocess.run(['/usr/bin/python3','-c','import sys;sys.path.insert(0,sys.argv[1]);import xsm.cli;print(xsm.cli.__file__)',str(SNAPSHOT)],
                             cwd=str(primary),env=env,capture_output=True,text=True,timeout=15)
        result['CLI_preflight']={'checks':preflight,'module_source':proof.stdout.strip(),'module_probe_exit':proof.returncode,
            'source_cli_SHA':base.sha((SNAPSHOT/'xsm/cli.py').read_bytes()),'wrapper':str(wrapper),'wrapper_SHA':base.sha(wrapper.read_bytes()),
            'scope':'same actor process env/cwd and absolute entry before model; actual SDK sandbox authority only tested by native ask',
            'credentials_or_profile_values_queried':False}
        if any(r['exit_code'] for r in preflight) or proof.returncode or proof.stdout.strip()!=str(SNAPSHOT/'xsm/cli.py'):
            raise RuntimeError('v2 frozen CLI preflight failed; zero model starts')
        if not all(flag in preflight[1]['stdout'] for flag in ('--attachment','--wake','--wait','--priority','--text')):
            raise RuntimeError('v2 required parser flags missing; zero model starts')
        base.INITIATOR_GOAL += ' v3도유지하는CLI source 선결조건: CLI는 전역 xsm 대신 절대경로 '+str(wrapper)+' 를 사용하세요. 이 wrapper는 /usr/bin/python3와 고정본 CLI를 실행하며 기존 SDK sandbox 권한을 바꾸지 않습니다. 이 새 조건에서도 실패하면 또 조건을 추가하거나 실행경로/identity/권한을 고쳐 재시도하지 마세요.'
        result['goals']['initiator']=base.INITIATOR_GOAL
        result['precondition_correction']='original v1 parser and v2 capability refusal preserved; final separately authorized readiness-order condition; no additional condition'
        os.environ['XSM_HOME'] = str(state)
        for name in list(sys.modules):
            if name == 'xsm' or name.startswith('xsm.'):
                del sys.modules[name]
        sys.path.insert(0, str(SNAPSHOT)); sys.dont_write_bytecode = True
        modules = {name: importlib.import_module('xsm.' + name) for name in ('registry', 'paths', 'identity', 'envelope')}
        modules['paths'].HOME = str(state)
        used = set()
        reviewer = Actor('reviewer', Path.home() / '.codex-3', SNAPSHOT, state, raw, modules, workdir=linked)
        actors.append(reviewer); result['reviewer_invocation'] = reviewer.start()
        deadline = min(started + 780, time.monotonic() + 60)
        while time.monotonic() < deadline and reviewer.peer is None:
            reviewer.refresh(used)
            if reviewer.proc.poll() is not None:
                break
            time.sleep(.1)
        if reviewer.peer is None:
            raise RuntimeError('reviewer actual native registration unavailable; no correction/retry')
        result['setup_registrations'] += 1
        readiness_start=time.monotonic()
        readiness_deadline=readiness_start+15
        ready=False; observations=[]; first_raw_call=None
        while time.monotonic()<readiness_deadline:
            reviewer.refresh(used)
            actual=[c for c in reviewer.calls.values() if c['kind']=='mcp_tool_call']
            if actual and first_raw_call is None:
                first_raw_call={'tool':actual[0]['item'].get('tool'),'item_id':actual[0]['item'].get('id'),
                                'raw_path':str(reviewer.out),'observed_seconds':round(time.monotonic()-readiness_start,3)}
            capability=modules['registry'].file_capability(reviewer.peer)
            records=[]
            for p in (state/'capability-observations').glob('*.json'):
                row=base.read_json(p)
                if isinstance(row,dict) and (row.get('endpoint')or{}).get('session_id')==reviewer.peer['session_id']:
                    records.append({'path':str(p),'sha256':base.sha(p.read_bytes()),'record':row})
            observations.append({'seconds':round(time.monotonic()-readiness_start,3),'capability':capability,'records':records})
            if first_raw_call and capability.get('status')=='observed' and any(
                r['record'].get('reader_pid')==reviewer.mcp['pid'] and
                r['record'].get('files',{}).get('status')=='observed' for r in records):
                ready=True;break
            if reviewer.proc.poll() is not None:break
            time.sleep(.1)
        result['files_readiness']={'budget_seconds':15,'ready':ready,'first_actual_MCP_call':first_raw_call,
            'elapsed':round(time.monotonic()-readiness_start,3),'observations':observations,
            'method':'read-only raw MCP event plus exact current endpoint/reader observation; no capability write/injection'}
        write(raw/'files-readiness.json',result['files_readiness'])
        base.INITIATOR_GOAL += (' 첨부pair허용: 실제reviewer firstMCP와observed files광고를선결확인했으니 plain2건후 첨부2건까지총4건을진행하세요.' if ready else
                               ' 첨부pair금지: 15초선결 files준비가미확인이라 plain2건만진행하고 자료전송은시도하지마세요. files는partial로보고하세요.')
        result['goals']['initiator']=base.INITIATOR_GOAL
        result['allowed_business_question_count']=4 if ready else 2
        initiator = Actor('initiator', Path.home() / '.codex-3', SNAPSHOT, state, raw, modules, workdir=primary)
        actors.append(initiator); result['initiator_invocation'] = initiator.start()
        result['status'] = 'running'; print(json.dumps({'phase': 'native-started', 'raw_root': str(raw)}), flush=True)
        ended_at = None
        while time.monotonic() < started + 780:
            for actor in actors:
                before = actor.peer is not None
                actor.refresh(used)
                if not before and actor.peer is not None:
                    result['setup_registrations'] += 1
                if actor.cwd_evidence and (actor.cwd_evidence['kernel_process_cwd'] != str(actor.workdir)
                                           or not actor.cwd_evidence['native_generation_alive']):
                    raise RuntimeError('native PID/cwd evidence mismatch; no identity correction')
                for call in actor.calls.values():
                    if call['kind'] == 'file_change':
                        for change in call['item'].get('changes', []):
                            changed = Path(change['path'])
                            if not changed.is_absolute(): changed = actor.workdir / changed
                            if changed.resolve() == material.resolve():
                                raise RuntimeError('immutable parity material changed')
                if any(c['kind'] == 'mcp_tool_call' and c['item'].get('tool') in base.FORBIDDEN | {'xsm_decide'}
                       for c in actor.calls.values()):
                    raise RuntimeError('extra permission/publication operation attempted; no bypass')
            for actor in actors:
                for call in actor.calls.values():
                    item = call['item']
                    if not call['complete']: continue
                    if call['kind'] == 'mcp_tool_call' and base.error_kind(item):
                        raise RuntimeError('actual MCP error before parity completion: ' + str(base.error_kind(item)))
                    if call['kind'] == 'command_execution' and 'ask' in (item.get('command') or '') and (item.get('exit_code') not in (None, 0) or ('CLI_EXIT_CODE=' in (item.get('aggregated_output') or '') and re.search(r'CLI_EXIT_CODE=(?!0(?:\s|$))\d+',item.get('aggregated_output') or ''))):
                        raise RuntimeError('actual caller CLI ask failed; no bypass/retry')
            config = base.read_json(state / 'config.json') or {}
            if any(config.get(k) for k in ('links', 'reaches', 'projects', 'scopes')):
                raise RuntimeError('extra fixture collaboration scope detected')
            if initiator.proc.poll() is not None:
                ended_at = ended_at or time.monotonic()
                if reviewer.proc.poll() is not None or time.monotonic() - ended_at > 20:
                    break
            if reviewer.proc.poll() not in (None, 0):
                raise RuntimeError('reviewer native host exit; no retry')
            time.sleep(.2)
        messages, replies = base.product_messages(state, actors, modules)
        received = base.received_reply_ids(initiator, replies)
        for reply in replies:
            request = messages[reply['reply_to']]
            question = base.read_json(state / 'questions' / (request['id'] + '.json')) or {}
            result['reviews'].append({'category': 'handshake' if question.get('purpose') == 'handshake'
                else base.math_kind(request['body']), 'request_id': request['id'], 'reply_id': reply['id'],
                'reply_to': reply['reply_to'], 'request_body': request['body'], 'reply_body': reply['body'],
                'received_actual_body': reply['id'] in received, 'outcome': reply['outcome'],
                'canonical_state': (base.read_json(next((state / 'handoffs').glob('*/' + reply['id'] + '.json'))) or {}).get('state')})
        final_source = material.read_bytes()
        (raw / 'source-final.txt').write_bytes(final_source)
        (raw / 'source-final.txt').chmod(0o600)
        result['source_final_sha256'] = base.sha(final_source)
        result['status'] = 'collected-needs-parity-readback' if all(a.proc.poll() == 0 for a in actors) else 'not-completed-original-sample'
    except Exception as exc:
        result.update(status='original-failure-preserved-no-retry', failure_type=type(exc).__name__, failure=str(exc))
    finally:
        result['actors'] = [dict(a.summary(), native_cwd_evidence=a.cwd_evidence) for a in actors]
        result['cleanup'] = []
        for actor in actors:
            try:
                result['cleanup'] += actor.finish()
            except Exception as exc:
                result['cleanup'].append({'role': actor.role, 'error': type(exc).__name__})
        result['owned_alive_after'] = [{'role': a.role, 'native_alive': a.proc.poll() is None,
            'MCP_same_generation_alive': bool(a.mcp and modules['identity'].pid_alive(a.mcp['pid'])
                and modules['identity'].lstart(a.mcp['pid']) == a.mcp['lstart'])} for a in actors]
        result['source_after'] = base.source_readback(SNAPSHOT, manifest['files'])[0] if 'manifest' in locals() else None
        result['source_unchanged'] = result.get('source_before') == result['source_after']
        result['profile_guard_unchanged'] = protected == base.profile_guard()
        result['seconds'] = round(time.monotonic() - started, 3)
        result['native_CLI_invocations'] = len(actors)
        write(HERE / (PREFIX + '.json'), result)
        evidence = {'scope': 'private worktree single-condition evidence; no attestation/permission grant',
            'script_sha256': base.sha(Path(__file__).read_bytes()), 'raw_root': str(raw),
            'files': {str(p.relative_to(raw)): base.sha(p.read_bytes()) for p in sorted(raw.rglob('*'))
                if p.is_file() and '.git' not in p.parts and '__pycache__' not in p.parts}}
        write(HERE / (PREFIX + '.manifest.json'), evidence)
        print(json.dumps({'status': result['status'], 'seconds': result['seconds'],
            'native_CLI_invocations': len(actors), 'raw_root': str(raw)}), flush=True)


if __name__ == '__main__':
    main()
