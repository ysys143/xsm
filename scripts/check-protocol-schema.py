#!/usr/bin/env python3
"""Validate public request artifacts with jsonschema (development-only dependency)."""
import argparse
import copy
import importlib.metadata
import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def output_contract(trace=None):
    schema = json.loads((ROOT / 'docs/protocol/output.schema.json').read_text())
    examples = json.loads((ROOT / 'docs/protocol/output-examples.json').read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    request_methods = json.loads((ROOT / 'docs/protocol/request.schema.json').read_text())['properties']['method']['enum']
    if set(schema['x-methodResults']) != set(request_methods):
        raise ValueError('output method result map differs from request inventory')
    example_methods = {entry['method'] for entry in examples if 'result' in entry['frame']}
    if example_methods != set(request_methods):
        raise ValueError('output examples omit a method result')
    def validate(observation):
        frame = observation['frame']
        validator.validate(frame)
        if 'result' in frame:
            definition = schema['x-methodResults'][observation['method']]
            Draft202012Validator({'$ref': definition, '$defs': schema['$defs']}).validate(frame['result'])
    for example in examples:
        validate(example)
    error = next(copy.deepcopy(e['frame']) for e in examples if 'error' in e['frame'])
    event = next(copy.deepcopy(e['frame']) for e in examples if e['frame'].get('method') == 'events/available')
    question = next(copy.deepcopy(e['frame']) for e in examples if e['frame'].get('method') == 'decision/request')
    bad_question = copy.deepcopy(question)
    del bad_question['params']['challenge']
    bad_error = copy.deepcopy(error)
    del bad_error['error']['message']
    invalid = [dict(error, result={}), dict(error, id=True), bad_error,
               dict(error, error={'code': 1.5, 'message': 'bad'}), dict(event, id=1),
               dict(event, method='unknown/notification'), bad_question,
               dict(event, params={'session': 's', 'ids': []})]
    for frame in invalid:
        if validator.is_valid(frame):
            raise ValueError('invalid output accepted: ' + repr(frame))
    delivery = Draft202012Validator({'$ref': schema['x-methodResults']['delivery.report'], '$defs': schema['$defs']})
    if delivery.is_valid({'recorded': 'admitted', 'acknowledged': True}):
        raise ValueError('admission incorrectly permits acknowledged=true')
    observations = [] if trace is None else json.loads(trace.read_text())['observations']
    for observation in observations:
        validate(observation)
    return dict(examples=len(examples), rejected=len(invalid) + 1, observed=len(observations),
                observedSuccessfulMethods=sorted({o['method'] for o in observations if 'result' in o['frame']}),
                observedNotifications=sum('method' in o['frame'] for o in observations))


def run(trace=None):
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
                scope='request and output structures; no full operation results or semantic certification',
                output=output_contract(trace))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wire-trace', type=Path)
    args = parser.parse_args()
    result = run(args.wire_trace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
