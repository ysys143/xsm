"""Check exact-home regression oracles against temporary pre-fix source only."""
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
BASELINE = '66a263c'
CASES = [
    ('registry-overwrite', ['registry.py', 'workers.py'],
     'test_repeated_registration_keeps_both_homes_and_their_refs'),
    ('mcp-copy-preference', ['mcp.py'],
     'test_mcp_thread_lookup_checks_its_own_home_before_adopting_a_copy'),
]


def main():
    results = []
    with tempfile.TemporaryDirectory(prefix='xsm-identity-oracles-') as folder:
        scratch = Path(folder)
        env = {key: os.environ[key] for key in ('PATH', 'LANG', 'TMPDIR') if key in os.environ}
        env.update(HOME=str(scratch / 'home'), XSM_HOME=str(scratch / 'state'),
                   CODEX_HOME=str(scratch / 'codex'), CLAUDE_CONFIG_DIR=str(scratch / 'claude'),
                   PYTHONDONTWRITEBYTECODE='1')
        (scratch / 'home').mkdir()
        for name in ('xsm', 'tests', 'integrations'):
            shutil.copytree(ROOT / name, scratch / name, ignore=shutil.ignore_patterns('__pycache__'))
        positive = subprocess.run([sys.executable, '-B', '-m', 'unittest',
            'tests.test_registry_profiles', '-q'], cwd=scratch, env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
        (OUTPUT / 'identity-positive.log').write_text(positive.stdout)
        if positive.returncode:
            raise SystemExit('current identity tests failed; no RED result claimed')
        for label, files, method in CASES:
            originals = {name: (scratch / 'xsm' / name).read_bytes() for name in files}
            try:
                for name in files:
                    old = subprocess.check_output(['git', 'show', BASELINE + ':xsm/' + name], cwd=ROOT)
                    (scratch / 'xsm' / name).write_bytes(old)
                result = subprocess.run([sys.executable, '-B', '-m', 'unittest',
                    'tests.test_registry_profiles.RegistryProfilesTest.' + method, '-q'],
                    cwd=scratch, env=env, text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, timeout=20)
                (OUTPUT / (label + '-red.log')).write_text(result.stdout)
                detected = result.returncode == 1 and 'AssertionError:' in result.stdout and '\nERROR:' not in result.stdout
                results.append({'case': label, 'baseline': BASELINE, 'files': files,
                                'test': method, 'exit_code': result.returncode, 'detected': detected})
            finally:
                for name, content in originals.items():
                    (scratch / 'xsm' / name).write_bytes(content)
    report = {'cases': results, 'source_hashes': {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [ROOT / 'xsm' / name for name in ('registry.py', 'mcp.py', 'workers.py')]
        + [ROOT / 'tests/test_registry_profiles.py']}}
    (OUTPUT / 'identity-regressions.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'positive_exit': 0, 'regressions': results}))
    return 0 if all(case['detected'] for case in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
