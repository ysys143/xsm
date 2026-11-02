#!/usr/bin/env python3
"""Regenerate structural public operation schemas and validation-only examples."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from xsm.protocol_contract import operation_schema
from xsm.operation_schema import TOOLS


def sample(schema):
    if 'enum' in schema:
        return next((value for value in ('status', 'show') if value in schema['enum']), schema['enum'][0])
    if 'const' in schema:
        return schema['const']
    kind = schema.get('type')
    if kind == 'string':
        return '' if schema.get('maxLength') == 0 else 'structural-fixture'
    if kind in ('number', 'integer'):
        return schema.get('minimum', 0)
    if kind == 'boolean':
        return False
    if kind == 'array':
        return [sample(schema['items']) for _ in range(schema.get('minItems', 0))]
    if kind == 'object':
        return {key: sample(schema['properties'][key]) for key in schema.get('required', [])}
    raise ValueError('unsupported schema for example generation: ' + repr(schema))


if __name__ == '__main__':
    schema = operation_schema()
    examples = [dict(session='opaque-session', operation=name, arguments=sample(arguments))
                for name, arguments in schema['$defs'].items()]
    for name, value in (('operations.schema.json', schema), ('operation-examples.json', examples)):
        (ROOT / 'docs/protocol' / name).write_text(json.dumps(value, indent=2) + '\n')
    (ROOT / 'integrations/openclaw/tools.mjs').write_text(
        '// Generated from xsm.operation_schema.TOOLS; checked by tests.test_openclaw_schema.\n'
        + 'export default ' + json.dumps(TOOLS, indent=2) + ';\n')
