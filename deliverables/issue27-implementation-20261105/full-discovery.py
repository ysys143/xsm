"""Run the complete discovered unittest inventory in isolated module groups.

No test exclusions. Existing protocol gate remains the product gate. The ordinary
serial discovery is preserved separately; this runner records every case/skip.
"""
import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path.insert(0, str(ROOT))


def leaves(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from leaves(item)
        else:
            yield item


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--group':
        class Result(unittest.TextTestResult):
            def startTest(self, test):
                self.stream.write('\nCASE ' + test.id() + '\n')
                super().startTest(test)
        result = unittest.TextTestRunner(verbosity=1, resultclass=Result).run(
            unittest.defaultTestLoader.loadTestsFromNames(sys.argv[3:]))
        Path(sys.argv[2]).write_text(json.dumps({
            'ran': result.testsRun, 'failures': [test.id() for test, _ in result.failures],
            'errors': [test.id() for test, _ in result.errors],
            'skipped': [{'test': test.id(), 'reason': reason} for test, reason in result.skipped],
            'success': result.wasSuccessful()}, indent=2) + '\n')
        raise SystemExit(0 if result.wasSuccessful() else 1)

    started = time.monotonic()
    suite = unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    cases = list(leaves(suite))
    counts = {}
    for test in cases:
        module = test.id().rsplit('.', 2)[0]
        counts[module] = counts.get(module, 0) + 1
    groups = [[] for _ in range(8)]
    weights = [0] * len(groups)
    for module in sorted(counts, key=lambda name: (-counts[name], name)):
        index = min(range(len(groups)), key=lambda number: weights[number])
        groups[index].append(module)
        weights[index] += counts[module]
    spec = importlib.util.find_spec('jsonschema')
    dependency = str(Path(spec.origin).resolve().parent.parent) if spec and spec.origin else ''
    inventory = {'python': sys.version.split()[0], 'expected': len(cases),
                 'modules': counts, 'groups': groups, 'weights': weights,
                 'scope': 'all unittest discovery cases, parallel module groups, model0'}
    (OUT/'discovery-inventory.json').write_text(json.dumps(inventory, indent=2)+'\n')

    with tempfile.TemporaryDirectory(prefix='xsm-full-discovery-') as folder:
        def run(index):
            home = Path(folder)/str(index)
            home.mkdir()
            env = {key: os.environ[key] for key in ('PATH','LANG','TMPDIR') if key in os.environ}
            env.update(HOME=str(home), XSM_HOME=str(home/'state'), CODEX_HOME=str(home/'codex'),
                       CLAUDE_CONFIG_DIR=str(home/'claude'), PYTHONDONTWRITEBYTECODE='1',
                       PYTHON=sys.executable, PYTHONPATH=os.pathsep.join(filter(None, (str(ROOT/'tests'), str(ROOT), dependency))))
            report = OUT/('discovery-group-%d.json' % index)
            with (OUT/('discovery-group-%d.log' % index)).open('w') as stream:
                proc = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()),
                    '--group', str(report), *groups[index]], cwd=ROOT, env=env,
                    stdout=stream, stderr=subprocess.STDOUT)
            value = json.loads(report.read_text()) if report.exists() else {'ran':0,'success':False,'runner_error':True}
            return dict(value, group=index, exit=proc.returncode)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(run, range(len(groups))))
    ran = sum(result['ran'] for result in results)
    result = {'expected':len(cases), 'ran':ran, 'complete_inventory':ran == len(cases),
              'passed':ran == len(cases) and all(r['success'] for r in results),
              'seconds':round(time.monotonic()-started,3), 'python':sys.version.split()[0], 'groups':results}
    (OUT/'discovery-final.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
