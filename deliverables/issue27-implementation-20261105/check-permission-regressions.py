"""Five deliberate permission/gate faults, injected into temporary copies only."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).resolve().parent
CLASS = 'tests.test_native_permission_recovery.NativePermissionRecoveryTest.'
CASES = [
    ('native-answer-not-imported', 'xsm/decisions.py',
     '    """Record an exact marked question from the native completion hook; do not apply it."""\n',
     '    """Record an exact marked question from the native completion hook; do not apply it."""\n    return False\n',
     CLASS + 'test_allow_join'),
    ('negative-choice-applies', 'xsm/operation_schema.py',
     '    return answer, "they chose %r" % answer\n',
     '    return ("allow" if answer == "deny" else answer), "they chose %r" % answer\n',
     CLASS + 'test_deny_join'),
    ('wrong-question-captured', 'xsm/decisions.py',
     " and r.get('native_question') == question\n", '\n',
     CLASS + 'test_a_different_native_question_cannot_capture_the_pending_choice'),
    ('applied-receipt-not-replayed', 'xsm/operations.py',
     '            if prior and prior["status"] == "applied":\n',
     '            if False and prior and prior["status"] == "applied":\n', CLASS + 'test_allow_join'),
    ('permission-suite-omitted', 'scripts/check-protocol.py',
     '"tests.test_person_decisions", ', '',
     'tests.test_protocol_gate.ProtocolGateTest.test_approval_and_profile_regressions_are_required_gate_members'),
]


def main():
    results = []
    with tempfile.TemporaryDirectory(prefix='xsm-permission-oracles-') as folder:
        scratch = Path(folder)
        env = {key: os.environ[key] for key in ('PATH', 'LANG', 'TMPDIR') if key in os.environ}
        env.update(HOME=str(scratch / 'home'), XSM_HOME=str(scratch / 'state'),
                   CODEX_HOME=str(scratch / 'codex'), CLAUDE_CONFIG_DIR=str(scratch / 'claude'),
                   PYTHONDONTWRITEBYTECODE='1')
        (scratch / 'home').mkdir()
        for name in ('xsm', 'tests', 'integrations', 'scripts'):
            shutil.copytree(ROOT / name, scratch / name, ignore=shutil.ignore_patterns('__pycache__'))
        def run(target):
            return subprocess.run([sys.executable, '-B', '-m', 'unittest', target, '-q'],
                cwd=scratch, env=env, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=20)
        positive = run('tests.test_native_permission_recovery')
        (OUTPUT / 'permission-positive.log').write_text(positive.stdout)
        if positive.returncode:
            raise SystemExit('positive permission tests failed; no mutation success claimed')
        for label, path, old, new, target in CASES:
            filename = scratch / path
            original = filename.read_text()
            if original.count(old) != 1:
                raise AssertionError('mutation anchor is not unique: ' + label)
            try:
                filename.write_text(original.replace(old, new, 1))
                result = run(target)
                (OUTPUT / (label + '-red.log')).write_text(result.stdout)
                detected = result.returncode == 1 and 'AssertionError:' in result.stdout and '\nERROR:' not in result.stdout
                results.append({'case': label, 'source': path, 'test': target,
                                'exit_code': result.returncode, 'detected': detected})
            finally:
                filename.write_text(original)
    files = sorted({case[1] for case in CASES} | {
        'xsm/mcp.py', 'xsm/consent.py', 'tests/test_native_permission_recovery.py',
        'tests/permission_harness.py', 'tests/test_protocol_gate.py'})
    report = {'cases': results, 'source_hashes': {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in files}}
    (OUTPUT / 'permission-regressions.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'positive_exit': 0, 'mutations': results}))
    return 0 if all(case['detected'] for case in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
