#!/usr/bin/env python3
"""Validate public request artifacts with jsonschema (development-only dependency)."""
import argparse
import copy
import importlib.metadata
import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def run():
    schema = json.loads((ROOT / 'docs/protocol/request.schema.json').read_text())
    examples = json.loads((ROOT / 'docs/protocol/request-examples.json').read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    methods = schema['properties']['method']['enum']
    if len(methods) != len(set(methods)) or set(methods) != {value['method'] for value in examples}:
        raise ValueError('examples must cover every declared method exactly once')
    if len(examples) != len(methods):
        raise ValueError('duplicate or missing method examples')
    accepted = rejected = 0
    for example in examples:
        validator.validate(example)
        accepted += 1
        bad = copy.deepcopy(example)
        bad['params']['unrecognized'] = True
        if validator.is_valid(bad):
            raise ValueError('unknown field accepted for ' + example['method'])
        rejected += 1
        binding = next(item['then'] for item in schema['allOf']
                       if item['if']['properties']['method']['const'] == example['method'])
        definition = schema['$defs'][binding['properties']['params']['$ref'].split('/')[-1]]
        for required in definition['required']:
            bad = copy.deepcopy(example)
            del bad['params'][required]
            if validator.is_valid(bad):
                raise ValueError('missing required field accepted: ' + example['method'] + '/' + required)
            rejected += 1
    for changes in ({'id': True}, {'params': []}, {'method': 'unknown.method'}, {'extra': True}):
        bad = dict(examples[0], **changes)
        if validator.is_valid(bad):
            raise ValueError('invalid envelope accepted: ' + repr(changes))
        rejected += 1
    bad = next(copy.deepcopy(e) for e in examples if e['method'] == 'delivery.report')
    del bad['params']['token']
    if validator.is_valid(bad):
        raise ValueError('admitted report without claim token accepted')
    rejected += 1
    return dict(passed=True, methods=len(methods), accepted=accepted, rejected=rejected,
                validator='jsonschema', validatorVersion=importlib.metadata.version('jsonschema'),
                scope='request envelopes only; no semantic, operation-result or response certification')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
