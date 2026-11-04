"""Five planned migration faults in temporary copies, without models or real homes."""
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
CLASS = 'tests.test_profile_migration.ProfileMigrationTest.'
CASES = [
    ('migration-home-key-omitted', 'xsm/registry.py',
     '[runtime, _home(home), session_id]', '[runtime, session_id]',
     'tests.test_registry_profiles.RegistryProfilesTest.test_repeated_registration_keeps_both_homes_and_their_refs'),
    ('migration-source-fence-omitted', 'xsm/migration.py',
     '    if retired:\n        owner = current_owner(record)\n',
     '    if False and retired:\n        owner = current_owner(record)\n',
     CLASS + 'test_source_cannot_reclaim_registration_or_send_after_transfer'),
    ('migration-lease-check-omitted', 'xsm/migration.py',
     'def _check_lease(transfer, now):\n', 'def _check_lease(transfer, now):\n    return\n',
     CLASS + 'test_forwarding_expires_at_24_hours_but_retirement_does_not'),
    ('migration-old-allow-retained', 'xsm/migration_state.py',
     "            decisions.supersede(item['id'])\n", '            pass\n',
     CLASS + 'test_pending_user_permission_moves_as_a_request_not_an_old_allow'),
    ('migration-missing-transfer-falsely-completes', 'xsm/migration.py',
     '            migration_state.verify(record)\n', '            pass\n',
     CLASS + 'test_missing_successor_copy_is_not_reported_as_a_completed_transfer'),
]


def main():
    results = []
    with tempfile.TemporaryDirectory(prefix='xsm-migration-oracles-') as folder:
        scratch = Path(folder)
        env = {key: os.environ[key] for key in ('PATH', 'LANG', 'TMPDIR') if key in os.environ}
        env.update(HOME=str(scratch / 'home'), XSM_HOME=str(scratch / 'state'),
                   CODEX_HOME=str(scratch / 'codex'), CLAUDE_CONFIG_DIR=str(scratch / 'claude'),
                   PYTHONDONTWRITEBYTECODE='1')
        (scratch / 'home').mkdir()
        for name in ('xsm', 'tests', 'integrations', 'scripts'):
            shutil.copytree(ROOT / name, scratch / name, ignore=shutil.ignore_patterns('__pycache__'))

        def run(*targets):
            return subprocess.run([sys.executable, '-B', '-m', 'unittest', *targets, '-q'],
                cwd=scratch, env=env, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, timeout=30)

        positive = run('tests.test_profile_migration', 'tests.test_registry_profiles',
                       'tests.test_migration_diagnostics', 'tests.test_migration_network')
        (OUTPUT / 'migration-positive.log').write_text(positive.stdout)
        if positive.returncode:
            raise SystemExit('positive migration tests failed; no mutation result claimed')
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
    files = {case[1] for case in CASES} | {
        'xsm/handoff.py', 'xsm/send.py', 'xsm/mcp.py', 'xsm/operations.py',
        'tests/test_profile_migration.py', 'tests/test_registry_profiles.py',
        'tests/test_migration_diagnostics.py', 'tests/test_migration_network.py'}
    report = {'python': sys.version.split()[0], 'positive_exit': 0, 'cases': results,
              'source_hashes': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in sorted(files)}}
    (OUTPUT / 'migration-regressions.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'positive_exit': 0, 'mutations': results}))
    return 0 if all(case['detected'] for case in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
