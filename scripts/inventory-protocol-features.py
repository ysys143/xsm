#!/usr/bin/env python3
"""Inventory CLI leaves and public catalogs without touching user state."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def describe(parser, prefix):
    rows = []
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, child in action.choices.items():
                rows.extend(describe(child, prefix + [name]))
    if rows:
        return rows
    return [{
        'command': ' '.join(prefix),
        'handler': getattr(parser.get_default('func'), '__name__', None),
        'positionals': [{'name': a.dest, 'choices': list(a.choices) if a.choices is not None else None}
                        for a in parser._actions if not a.option_strings
                        and not isinstance(a, argparse._SubParsersAction)],
        'options': [a.option_strings for a in parser._actions if a.option_strings and a.dest != 'help'],
    }]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output already exists; preserve previous evidence')
    with tempfile.TemporaryDirectory(prefix='xsm-inventory-') as temp:
        inherited = {key: os.environ[key] for key in ('PATH', 'LANG', 'TMPDIR') if key in os.environ}
        os.environ.clear()
        os.environ.update(inherited, HOME=temp, XSM_HOME=temp + '/state')
        sys.path.insert(0, str(ROOT))
        from xsm.cli import build_parser
        from xsm.operation_schema import TOOLS
        from xsm.protocol import REQUEST_FIELDS
        result = {
            'cli': describe(build_parser(), ['xsm']),
            'operations': [{'name': tool['name'], 'actions': tool['inputSchema'].get(
                'properties', {}).get('action', {}).get('enum')} for tool in TOOLS],
            'methods': list(REQUEST_FIELDS),
        }
        result['counts'] = {key: len(value) for key, value in result.items()}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result['counts']))


if __name__ == '__main__':
    main()
