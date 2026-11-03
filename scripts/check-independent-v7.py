#!/usr/bin/env python3
"""Run the independent result/transport negatives without native models or servers."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'examples/independent-participant'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from verify_v7 import Verification
    with tempfile.TemporaryDirectory(prefix='xsm-independent-v7-local-') as temp:
        verification = Verification({'input': str(args.public_root.resolve())}, Path(temp))
        examples = verification.examples()
        verification.mutants(examples)
        verification.action_fixtures(examples)
        counts = Counter(item['category'] for item in verification.checks if item['passed'])
        failures = [item for item in verification.checks if not item['passed']]
        result = dict(passed=not failures, counts=dict(counts), failures=failures,
            scope='independent public examples and deliberate local wire/result faults; no server, model, UI or network')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
