#!/usr/bin/env python3
"""Repeat isolated actual scope conformance; retain every result and diagnostic."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--runs', type=int, default=20)
args = parser.parse_args()
if not 1 <= args.runs <= 100:
    parser.error('--runs must be between 1 and 100')
root = Path(__file__).resolve().parents[1]
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=False, mode=0o700)
spec = importlib.util.spec_from_file_location('scope_repeat_checker', root / 'scripts/conform-host-protocol.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
command = [sys.executable, '-B', str(root / 'tests/fixtures/protocol_observed_host.py')]
summary = dict(status='running', requested=args.runs, runs=[],
               scope='repeated isolated actual scope protocol; no inference or native UI; non-reproduction does not resolve a prior failure')
started = time.monotonic()
for index in range(args.runs):
    if time.monotonic() - started >= 120:
        break
    before = time.monotonic()
    result = checker.run(command, suite='scopes', capture=True)
    (output / ('run-%02d.json' % (index + 1))).write_text(json.dumps(result, indent=2) + '\n')
    summary['runs'].append(dict(run=index + 1, status=result['status'],
        seconds=round(time.monotonic() - before, 3), activeCheck=result.get('activeCheck'),
        diagnostics=result.get('diagnostics'), error=result.get('error')))
    (output / 'result.json').write_text(json.dumps(summary, indent=2) + '\n')
summary.update(executed=len(summary['runs']), seconds=round(time.monotonic() - started, 3),
               failed=sum(row['status'] != 'passed' for row in summary['runs']))
summary['status'] = ('incomplete' if summary['executed'] != args.runs else
                     'failed' if summary['failed'] else 'passed')
(output / 'result.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps({key: value for key, value in summary.items() if key != 'runs'}))
raise SystemExit(0 if summary['status'] == 'passed' else 1)
