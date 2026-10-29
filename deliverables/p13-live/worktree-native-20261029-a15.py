"""One private-repo/linked-worktree native condition, no product fixes/retries."""
import collections
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
SNAPSHOT = Path('/private/tmp/xsm-p13-postqa-frozen-bukwksw6')
spec = importlib.util.spec_from_file_location('natural_worktree_base', HERE / 'natural-collaboration.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
base.REVIEWER_GOAL = '이곳의 검토 담당 a1입니다. 동료의 산술 제안을 독립 검토하며 실질 검토 세 차례가 끝날 때까지 협업을 유지하세요.'
base.INITIATOR_GOAL = 'a1과 검토 협업해 2+2=5 제안을 독립 검토받고 반례를 고쳐 재검토받으세요. 0+0=0 경계도 독립 검토받아 결과를 보고하세요.'
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
    raw = Path(tempfile.mkdtemp(prefix='p13-worktree-native-', dir='/private/tmp'))
    raw.chmod(0o700)
    state = raw / 'state'; state.mkdir(mode=0o700)
    result = {'scope': 'A15-01 one linked-worktree native condition, not whole-plan completion',
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
        manifest = base.read_json(HERE / 'post-qa-source-manifest.json')
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
        result['git_evidence'] = [git_identity(cwd, log) for cwd in (primary, linked)]
        if result['git_evidence'][0]['common_dir'] != result['git_evidence'][1]['common_dir']:
            raise RuntimeError('private worktrees do not share Git common directory')
        if list(skill_hashes.values())[0] != list(skill_hashes.values())[1]:
            raise RuntimeError('product skill/guide copies differ')
        os.environ['XSM_HOME'] = str(state)
        for name in list(sys.modules):
            if name == 'xsm' or name.startswith('xsm.'):
                del sys.modules[name]
        sys.path.insert(0, str(SNAPSHOT)); sys.dont_write_bytecode = True
        modules = {name: importlib.import_module('xsm.' + name) for name in ('registry', 'paths', 'identity', 'envelope')}
        modules['paths'].HOME = str(state)
        used = set()
        reviewer = Actor('reviewer', Path.home() / '.codex', SNAPSHOT, state, raw, modules, workdir=linked)
        actors.append(reviewer); result['reviewer_invocation'] = reviewer.start()
        deadline = min(started + 560, time.monotonic() + 60)
        while time.monotonic() < deadline and reviewer.peer is None:
            reviewer.refresh(used)
            if reviewer.proc.poll() is not None:
                break
            time.sleep(.1)
        if reviewer.peer is None:
            raise RuntimeError('reviewer actual native registration unavailable; no correction/retry')
        result['setup_registrations'] += 1
        initiator = Actor('initiator', Path.home() / '.codex-3', SNAPSHOT, state, raw, modules, workdir=primary)
        actors.append(initiator); result['initiator_invocation'] = initiator.start()
        result['status'] = 'running'; print(json.dumps({'phase': 'native-started', 'raw_root': str(raw)}), flush=True)
        ended_at = None
        while time.monotonic() < started + 560:
            for actor in actors:
                before = actor.peer is not None
                actor.refresh(used)
                if not before and actor.peer is not None:
                    result['setup_registrations'] += 1
                if actor.cwd_evidence and (actor.cwd_evidence['kernel_process_cwd'] != str(actor.workdir)
                                           or not actor.cwd_evidence['native_generation_alive']):
                    raise RuntimeError('native PID/cwd evidence mismatch; no identity correction')
                if any(c['kind'] == 'file_change' for c in actor.calls.values()):
                    raise RuntimeError('model file change observed; original sample retained')
                if any(c['kind'] == 'mcp_tool_call' and c['item'].get('tool') in base.FORBIDDEN | {'xsm_decide'}
                       for c in actor.calls.values()):
                    raise RuntimeError('extra permission/publication operation attempted; no bypass')
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
        categories = collections.Counter(r['category'] for r in result['reviews'] if r['received_actual_body'])
        result['status'] = ('passed-this-condition' if categories == {'proposal': 1, 'correction': 1, 'boundary': 1, 'handshake': 1}
            and all(a.proc.poll() == 0 for a in actors) else 'not-completed-original-sample')
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
