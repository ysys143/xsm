#!/usr/bin/env python3
"""배포 ask-worker의 상태·재사용·복구를 대체 자식 프로세스로 검증한다. LLM 호출은 없다."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix='reason-worker-cases-', dir='/private/tmp'))
    actor = Path(__file__).with_name('probe_worker_actor.mjs')
    results = []

    def item(id, sender='fixture/alice', delay=5):
        return dict(id=id, **{'from': sender}, body=f'CASE:{id};', delay=delay)

    def run(name, catalog, *, agent='claude', batches=None, home=None, expected=1, crash=None, fail_sends=0, stop_attempts=None, expected_exit=0):
        folder = root / name
        folder.mkdir()
        plan = dict(home=str(home or folder / 'home'), cwd=str(folder / 'work'), catalog=catalog, agent=agent,
                    batches=batches if batches is not None else [dict(ids=[m['id'] for m in catalog])], expectedReplies=expected,
                    crashAt=crash, failSends=fail_sends, stopAfterAttempts=stop_attempts)
        path = folder / 'plan.json'
        path.write_text(json.dumps(plan))
        with (folder / 'events.jsonl').open('w') as stdout, (folder / 'stderr').open('w') as stderr:
            p = subprocess.run(['node', '--experimental-vm-modules', str(actor), str(args.module), str(path)], stdout=stdout, stderr=stderr, timeout=30)
        events = [json.loads(l) for l in (folder / 'events.jsonl').read_text().splitlines() if l]
        if p.returncode != expected_exit:
            raise AssertionError(f'{name}: actor exit {p.returncode}, expected {expected_exit}; inspect {folder}')
        if not any(e['type'] == 'module_loaded' for e in events):
            raise AssertionError(f'{name}: no actual module evaluation')
        return plan, events

    def check(name, condition, detail=None, classification='verified-control-flow'):
        results.append(dict(name=name, passed=bool(condition), classification=classification, detail=detail))
        if not condition:
            raise AssertionError(name)

    def events_of(events, kind):
        return [e for e in events if e['type'] == kind]

    def journal(home):
        return json.loads((Path(home) / '.reason/ask-workers/worker.json').read_text())

    try:
        catalog = [item('a1', delay=80), item('b1', 'fixture/bob'), item('a2')]
        plan, events = run('claude-reuse', catalog, expected=3)
        starts = {e['id']: e for e in events_of(events, 'ask_start')}
        ends = {e['id']: e for e in events_of(events, 'ask_end')}
        check('same-sender-reuses-child', starts['a1']['child'] == starts['a2']['child'] and starts['a2']['prior'] == 'a1')
        check('different-senders-use-distinct-children', starts['a1']['child'] != starts['b1']['child'])
        check('same-sender-serial-and-other-sender-parallel', starts['a2']['at'] >= ends['a1']['at'] and starts['b1']['at'] < ends['a1']['at'])
        check('successful-replies-remove-journal-entries', journal(plan['home']) == [])
        argv = events_of(events, 'spawn')[0]['argv']
        check('claude-default-has-strict-mcp-and-hooks-disabled', '--strict-mcp-config' in argv and any('disableAllHooks' in str(x) for x in argv))

        _, events = run('normalized-ask-senders', [item('n1', 'fixture/ask-abcdef'), item('n2', 'fixture/ask-123456')], expected=2)
        starts = events_of(events, 'ask_start')
        check('ephemeral-ask-addresses-of-one-person-share-context', starts[0]['child'] == starts[1]['child'])

        _, events = run('codex-fresh', [item('c1'), item('c2')], agent='codex', expected=2)
        spawns = events_of(events, 'spawn')
        check('codex-spawns-per-request-without-resume', len(spawns) == 2 and all(e['command'] == 'codex' and e['argv'][0] == 'exec' and 'resume' not in e['argv'] for e in spawns))

        catalog = [item(f'pool{i}', f'fixture/sender{i}', 120) for i in range(7)]
        _, events = run('all-six-busy', catalog, expected=7)
        replies = events_of(events, 'reply')
        failed = [e for e in replies if "isn't running" in str(e['body'])]
        check('seventh-sender-can-receive-worker-stopped-answer', len(replies) == 7 and len(failed) == 1 and len(events_of(events, 'ask_start')) == 6,
              dict(replies=len(replies), not_executed=len(failed), failed_request=failed[0]['replyTo'] if failed else None), 'observed-admission-defect')

        catalog = [item('before_ack')]
        plan, events = run('crash-before-ack', catalog, crash='ack', expected_exit=77)
        kept = journal(plan['home'])
        check('requests-persist-before-network-ack', len(kept) == 1 and kept[0]['request']['id'] == 'before_ack' and not events_of(events, 'ask_start'))
        _, recovered = run('recover-before-ack', catalog, home=plan['home'], batches=[], expected=1)
        check('restart-recovers-unanswered-request', len(events_of(recovered, 'ask_start')) == 1 and len(events_of(recovered, 'reply')) == 1 and journal(plan['home']) == [])

        catalog = [item('saved_answer')]
        plan, events = run('crash-after-answer', catalog, crash='send', expected_exit=78)
        kept = journal(plan['home'])
        check('answer-persists-before-reply-send', len(kept) == 1 and kept[0].get('reply', '').startswith('fixture-answer:saved_answer'))
        _, recovered = run('recover-saved-answer', catalog, home=plan['home'], batches=[], expected=1)
        check('saved-answer-retries-without-new-work', not events_of(recovered, 'ask_start') and len(events_of(recovered, 'reply')) == 1 and journal(plan['home']) == [])

        catalog = [item('send_retry')]
        plan, events = run('send-fails-three-times', catalog, expected=99, fail_sends=3, stop_attempts=3)
        check('reply-failure-retains-answer-after-three-attempts', len(events_of(events, 'send_attempt')) == 3 and len(journal(plan['home'])) == 1)
        _, recovered = run('recover-send-failure', catalog, home=plan['home'], batches=[], expected=1)
        check('reply-failure-recovery-does-not-repeat-work', not events_of(recovered, 'ask_start') and len(events_of(recovered, 'reply')) == 1)

        catalog = [item('effect_gap')]
        plan, events = run('crash-after-effect-before-answer', catalog, crash='after_work', expected_exit=81)
        _, recovered = run('recover-effect-gap', catalog, home=plan['home'], batches=[], expected=1)
        effects = [json.loads(l) for l in (Path(plan['home']) / 'simulated-effects.jsonl').read_text().splitlines()]
        check('effect-before-answer-crash-can-repeat-work', len(effects) == 2 and len(events_of(recovered, 'ask_start')) == 1,
              dict(simulated_effects=len(effects)), 'observed-at-least-once-gap')
    except Exception as exc:
        results.append(dict(name='fixture-exception', passed=False, detail=f'{type(exc).__name__}: {exc}'))
    payload = dict(module_sha256=hashlib.sha256(args.module.read_bytes()).hexdigest(), actor_sha256=hashlib.sha256(actor.read_bytes()).hexdigest(),
                   fixture_root=str(root), native_llm_calls=0, scope='수정하지 않은 배포 ask-worker JS. 자식 CLI·모델 결과·네트워크·표시 helper는 fixture 대체. 실제 전체 CLI/모델 통합 검증과 구별.',
                   results=results, passed=all(r['passed'] for r in results))
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(passed=payload['passed'], checks=len(results), observed_defects=[r['name'] for r in results if r.get('classification','').startswith('observed-')]), ensure_ascii=False))
    return 0 if payload['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
