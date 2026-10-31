"""Subscription-only S12c runner (copied from deliverables/s12b-hard-sample/run_experiment.py and adapted).

S12c additions: F4 conditions (F4a whole batch, F4b/F4c read F1/F2 output, F4z overhead calibration) with the
main-class model, a STOP check before every call, a `config` stage that records and backs up Codex config hashes,
and a two-phase schedule (F1 || F2, then F3/F4 in one lane).

Kept from S12b:
- raw stdout/stderr are never written; only the fields aggregation needs are kept;
- every record passes through scrub() before it is written;
- codex runs from a scratch directory outside any git repository with --skip-git-repo-check;
- API keys are removed both by `env -u` on the command line and from the child environment.

stages: config | label | evaluate (reconciliation: reconcile.py)
"""
import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / 'runs'
RUNS.mkdir(exist_ok=True)
SCRATCH_BASE = Path(os.environ.get('S12C_SCRATCH', '/private/tmp/claude-501/-Users-jaesolshin-Documents-GitHub-cross-session-messaging/33bf5e13-fa64-4f22-844c-d0a499ae4150/scratchpad/s12c'))
SCRATCH = SCRATCH_BASE / 'codex-cwd'
HOMES = ['.codex', '.codex-2', '.codex-3']
CODEX_HOME = str(Path.home() / '.codex-3')
UNSET = ['env', '-u', 'ANTHROPIC_API_KEY', '-u', 'OPENAI_API_KEY']

UUID = re.compile(r'[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}')
EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
ACCOUNT_KEY = re.compile(r'(account|organi[sz]ation|org_?id|orgid|user_?id|userid|email|uuid)', re.I)


def scrub(x, key=''):
    """Replace account/org/user identifiers and e-mail addresses with <redacted>."""
    if isinstance(x, dict):
        return {k: scrub(v, k) for k, v in x.items()}
    if isinstance(x, list):
        return [scrub(v, key) for v in x]
    if isinstance(x, str):
        if ACCOUNT_KEY.search(key) and (UUID.search(x) or EMAIL.search(x) or key.lower() in ['email']):
            return '<redacted>'
        return EMAIL.sub('<redacted>', x)
    return x


def dump(path, value):
    path.write_text(json.dumps(scrub(value), ensure_ascii=False, indent=2) + '\n')


def child_env(codex=False):
    e = os.environ.copy()
    for k in ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'CLAUDECODE']:
        e.pop(k, None)
    if codex:
        e['CODEX_HOME'] = CODEX_HOME
    return e


def claude_cmd(model):
    return UNSET + ['claude', '-p', '--model', model, '--tools', '', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
                    '--no-session-persistence', '--output-format', 'json']


def codex_cmd(model):
    return UNSET + ['codex', 'exec', '--model', model, '--ephemeral', '--sandbox', 'read-only', '--skip-git-repo-check', '--json',
                    '--color', 'never', '-c', 'mcp_servers.reason-network.enabled=false', '-c', 'model_reasoning_effort="low"', '-']


def parse_json(text):
    text = text.strip()
    if text.startswith('```'):
        text = '\n'.join(text.splitlines()[1:-1])
    return json.loads(text)


def extract_claude(out, meta):
    try:
        obj = json.loads(out)
    except ValueError as ex:
        meta['stdout_parse_error'] = str(ex)
        return ''
    if isinstance(obj, list):  # some versions emit an event array
        obj = next((x for x in reversed(obj) if isinstance(x, dict) and x.get('type') == 'result'), {})
    meta['stdout_top_level_keys'] = sorted(obj.keys())
    meta['is_error'] = obj.get('is_error', False)
    meta['claude_usage'] = {k: v for k, v in (obj.get('usage') or {}).items() if isinstance(v, (int, float))}
    meta['model_usage'] = {m: {k: v for k, v in u.items() if isinstance(v, (int, float))} for m, u in (obj.get('modelUsage') or {}).items()}
    meta['response_models'] = sorted(meta['model_usage'])
    meta['duration_ms'] = obj.get('duration_ms')
    meta['num_turns'] = obj.get('num_turns')
    return obj.get('result') or ''


def extract_codex(out, meta):
    texts, usage, tids, types = [], [], [], set()
    for line in out.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        t = ev.get('type')
        types.add(t)
        item = ev.get('item') or {}
        if t == 'thread.started':
            tids.append(ev.get('thread_id'))
        elif t == 'item.completed' and item.get('type') == 'agent_message':
            texts.append(item.get('text', ''))
        elif t == 'turn.completed':
            usage.append({k: v for k, v in (ev.get('usage') or {}).items() if isinstance(v, (int, float))})
        elif t in ['turn.failed', 'error']:
            meta.setdefault('codex_errors', []).append(str(ev.get('message') or ev.get('error'))[:500])
        if t in ['item.started', 'item.completed'] and item.get('type') in ['command_execution', 'mcp_tool_call', 'web_search', 'file_change']:
            meta['unexpected_tool_use'] = True
    meta['event_types'] = sorted(x for x in types if x)
    meta['thread_ids'] = tids
    meta['codex_usage'] = usage
    return '\n'.join(texts)


PROXY_FIELDS = ['conversationId', 'timestamp', 'requestedModel', 'requestedEffort', 'resolvedModel', 'servedModel', 'provider', 'status',
                'durationMs', 'terminalStatus', 'usage']


def proxy_records(tids):
    wanted = {hashlib.sha256(t.encode()).hexdigest()[:32] for t in tids}
    raw = subprocess.run(['ocx', 'logs', '--limit', '300', '--json'], capture_output=True, text=True, timeout=30)
    rows = []
    for r in json.loads(raw.stdout).get('logs', []):
        if r.get('conversationId') in wanted:
            row = {k: r.get(k) for k in PROXY_FIELDS}
            row['attempts'] = [{k: a.get(k) for k in ['provider', 'model', 'status', 'requestedEffort']} for a in r.get('attempts', [])]
            rows.append(row)
    return rows


def run(name, condition, model, prompt, timeout=300):
    prefix = RUNS / name
    codex = condition in ['F2', 'F3', 'F4a', 'F4b', 'F4c', 'F4z']
    command = codex_cmd(model) if codex else claude_cmd(model)
    (prefix.with_suffix('.prompt.txt')).write_text(prompt)
    meta = dict(name=name, condition=condition, command=command, codex_home=CODEX_HOME if codex else None,
                cwd=str(SCRATCH) if codex else str(ROOT), started_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest())
    t = time.monotonic()
    try:
        r = subprocess.run(command, input=prompt, text=True, capture_output=True, env=child_env(codex),
                           cwd=SCRATCH if codex else ROOT, timeout=timeout)
        out, err = r.stdout, r.stderr
        meta['returncode'] = r.returncode
    except subprocess.TimeoutExpired as ex:
        out = ex.stdout or ''
        err = ex.stderr or ''
        out = out.decode(errors='replace') if isinstance(out, bytes) else out
        err = err.decode(errors='replace') if isinstance(err, bytes) else err
        meta.update(returncode=None, error='timeout')
    meta['elapsed_seconds'] = time.monotonic() - t
    meta['finished_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
    meta['stderr_tail'] = err[-600:] if meta.get('returncode') != 0 else ''
    text = extract_codex(out, meta) if codex else extract_claude(out, meta)
    (prefix.with_suffix('.response.txt')).write_text(EMAIL.sub('<redacted>', text))
    try:
        dump(prefix.with_suffix('.parsed.json'), parse_json(text))
    except Exception as ex:
        meta['parse_error'] = str(ex)
    if codex and meta.get('thread_ids'):
        try:
            rows = proxy_records(meta['thread_ids'])
            dump(prefix.with_suffix('.proxy.json'), rows)
            meta['proxy_requests'] = len(rows)
            meta['response_models'] = sorted({x['servedModel'] for x in rows if x.get('servedModel')})
            meta['requested_models'] = sorted({x['requestedModel'] for x in rows if x.get('requestedModel')})
        except Exception as ex:
            meta['proxy_error'] = str(ex)
            meta['response_models'] = []
    dump(prefix.with_suffix('.meta.json'), meta)
    print(name, json.dumps({k: meta.get(k) for k in ['returncode', 'elapsed_seconds', 'response_models', 'parse_error', 'unexpected_tool_use', 'proxy_requests']}, ensure_ascii=False), flush=True)
    return meta


def label():
    return run('labels-independent', 'L', 'opus', (ROOT / 'label-prompt.txt').read_text(), timeout=1800)


def config():
    """Record config.toml hashes of the three Codex homes and back them up outside the repository."""
    import shutil
    out = dict(recorded_at=dt.datetime.now(dt.timezone.utc).isoformat(), stage='before first codex call',
               backup_location='session scratchpad outside the repository (not committed)', sha256={}, mtime={})
    for h in HOMES:
        f = Path.home() / h / 'config.toml'
        out['sha256'][h] = hashlib.sha256(f.read_bytes()).hexdigest()
        out['mtime'][h] = f.stat().st_mtime
        dest = SCRATCH_BASE / 'config-backup' / h
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest / 'config.toml')
    (ROOT / 'codex-config-hash-before.json').write_text(json.dumps(out, indent=2) + '\n')
    print(json.dumps(out['sha256'], indent=1))


def model_ok(models, condition):
    if not models:
        return False
    if condition == 'F1':
        return all('haiku' in m.lower() for m in models)
    if condition == 'F2':
        return all(m in ['gpt-6-luna', 'openai/gpt-6-luna'] for m in models)
    return all(m == 'gpt-6.1-sol' for m in models)  # F3 and F4*


def validate(meta, condition):
    if not model_ok(meta.get('response_models'), condition):
        dump(ROOT / 'STOP.json', dict(condition=condition, reason='actual model mismatch or no response-model evidence; no substitution permitted', meta=meta))
        raise SystemExit(f'STOP: model evidence {meta.get("response_models")} for {condition}')
    if meta.get('returncode') != 0 or meta.get('is_error') or meta.get('parse_error') or meta.get('unexpected_tool_use'):
        dump(ROOT / 'STOP.json', dict(condition=condition, reason='failed or invalid run; preserved, remaining planned calls not run', meta=meta))
        raise SystemExit(f'STOP: failed or invalid run {meta["name"]}')


MODELS = {'F1': 'haiku', 'F2': 'openai/gpt-6-luna', 'F3': 'gpt-6.1-sol', 'F4a': 'gpt-6.1-sol', 'F4b': 'gpt-6.1-sol',
          'F4c': 'gpt-6.1-sol', 'F4z': 'gpt-6.1-sol'}
F4Z_SESSIONS = ['Heron', 'Wren', 'Godwit']


def plan():
    """Every planned call as (condition, repetition, case) in execution order per lane."""
    fixture = json.loads((ROOT / 'fixture.json').read_text())
    policy = json.loads((ROOT / 'policy.json').read_text())
    cases = [f'{b["id"]}-{s["id"]}' for b in fixture['batches'] for s in fixture['sessions']]
    sub = [x for x in cases if x.split('-')[0] in policy['F3_F4_batches']]
    out = {}
    for c in ['F1', 'F2']:
        out[c] = [(c, 0, x) for x in cases] + [(c, r, x) for r in range(1, policy['extra_repeats'] + 1) for x in policy['repeats']]
    out['F3'] = [('F3', 0, x) for x in sub]
    out['F4z'] = [('F4z', 0, f'zero-{s}') for s in F4Z_SESSIONS]
    for c in ['F4a', 'F4b', 'F4c']:
        out[c] = [(c, 0, x) for x in sub]
    return out


def session_of(case):
    fixture = json.loads((ROOT / 'fixture.json').read_text())
    sid = case.split('-')[-1]
    return next(s for s in fixture['sessions'] if s['id'] == sid)


def filtered_prompt(condition, case):
    """F4b/F4c input: the main-class model reads what F1/F2 returned for the same case in the base run."""
    src = 'F1' if condition == 'F4b' else 'F2'
    items = json.loads((RUNS / f'{src}-r0-{case}.parsed.json').read_text()).get('items', [])
    p = (ROOT / 'f4-prompt.txt').read_text() + (ROOT / 'f4-filtered-note.txt').read_text()
    p += '\n세션:\n' + json.dumps(session_of(case), ensure_ascii=False) + '\n변경 diff:\n'
    for it in items:
        p += f'변경 ID: {it.get("id")}\n## {it.get("title")}\n+ {it.get("quote")}\n필터 이유: {it.get("reason")}\n\n'
    if not items:
        p += '(필터가 고른 변경 없음)\n'
    return p


def prompt_for(condition, case):
    if condition in ['F1', 'F2', 'F3']:
        return (ROOT / 'prompts' / f'{case}.txt').read_text()
    if condition in ['F4a', 'F4z']:
        return (ROOT / 'prompts-f4' / f'{case}.txt').read_text()
    return filtered_prompt(condition, case)


def call(condition, repetition, case):
    if (ROOT / 'STOP.json').exists():
        raise SystemExit('STOP.json present; not starting further calls')
    name = f'{condition}-r{repetition}-{case}'
    p = RUNS / f'{name}.meta.json'
    meta = json.loads(p.read_text()) if p.exists() else run(name, condition, MODELS[condition], prompt_for(condition, case))
    validate(meta, condition)


def lane(conditions):
    schedule = plan()
    for c in conditions:
        for cond, rep, case in schedule[c]:
            call(cond, rep, case)


def evaluate():
    freeze = json.loads((ROOT / 'freeze-evaluation.json').read_text())
    for p, h in freeze['sha256'].items():
        assert hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h, p
    assert (ROOT / 'codex-config-hash-before.json').exists(), 'run the config stage first'
    SCRATCH.mkdir(parents=True, exist_ok=True)
    assert subprocess.run(['git', 'rev-parse'], cwd=SCRATCH, capture_output=True).returncode != 0, 'scratch dir is inside a git repo'
    schedule = plan()
    # Phase 1: the first call of each lane is verified before anything else runs; then F1 || F2.
    for c in ['F1', 'F2']:
        call(*schedule[c][0])
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for f in [pool.submit(lane, [c]) for c in ['F1', 'F2']]:
            f.result()
    print('PHASE 1 DONE', flush=True)
    # Phase 2: main-class model in one lane so F4 timings do not overlap other calls.
    lane(['F3', 'F4z', 'F4a', 'F4b', 'F4c'])
    print('EVALUATE DONE', flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('stage', choices=['config', 'label', 'evaluate'])
    globals()[ap.parse_args().stage]()
