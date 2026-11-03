"""Read-only export of this installation's public experimental protocol artifacts."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys

PATTERNS = ('docs/protocol/*.json', 'docs/protocol/*.md', 'scripts/conform-host-protocol.py', 'scripts/check-protocol-schema.py')
REQUIRED = ('docs/protocol/README.md', 'docs/protocol/request.schema.json',
            'docs/protocol/request-examples.json', 'docs/protocol/output.schema.json',
            'docs/protocol/output-examples.json', 'docs/protocol/inbox-result.schema.json',
            'docs/protocol/file-result.schema.json', 'docs/protocol/ack-result.schema.json', 'docs/protocol/operations.schema.json',
            'docs/protocol/handover-result.schema.json', 'docs/protocol/handover-result-examples.json',
            'docs/protocol/endorsement-result.schema.json', 'docs/protocol/endorsement-result-examples.json',
            'docs/protocol/scope-result.schema.json', 'docs/protocol/scope-result-examples.json',
            'docs/protocol/decision-result.schema.json', 'docs/protocol/decision-result-examples.json',
            'docs/protocol/approval-result.schema.json', 'docs/protocol/approval-result-examples.json',
            'docs/protocol/grant-result.schema.json', 'docs/protocol/grant-result-examples.json',
            'docs/protocol/decision-status-result.schema.json', 'docs/protocol/decision-status-result-examples.json',
            'docs/protocol/publication-result.schema.json', 'docs/protocol/publication-result-examples.json',
            'docs/protocol/question-results.md', 'docs/protocol/question-result.schema.json', 'docs/protocol/question-result-examples.json',
            'docs/protocol/send-result.schema.json', 'docs/protocol/send-result-examples.json',
            'docs/protocol/doc-result.schema.json', 'docs/protocol/doc-result-examples.json',
            'docs/protocol/board-result.schema.json', 'docs/protocol/board-result-examples.json',
            'docs/protocol/team-result.schema.json', 'docs/protocol/team-result-examples.json',
            'docs/protocol/discovery-result.schema.json', 'docs/protocol/discovery-result-examples.json',
            'docs/protocol/operation-examples.json', 'scripts/conform-host-protocol.py', 'scripts/check-protocol-schema.py')


def operation_schema():
    """Structural operation.call parameters, including this transport's restrictions."""
    from .operation_schema import TOOLS
    definitions, choices = {}, []
    def closed(schema):
        value = copy.deepcopy(schema)
        if value.get('type') == 'object':
            value['additionalProperties'] = False
        if 'properties' in value:
            value['properties'] = {key: closed(item) for key, item in value['properties'].items()}
        if 'items' in value:
            value['items'] = closed(value['items'])
        return value
    for tool in TOOLS:
        name = tool['name']
        arguments = closed(tool['inputSchema'])
        arguments['description'] = tool['description']
        for key in ('wait', 'wait_secs'):
            if key in arguments['properties']:
                arguments['properties'][key].update(const=0, default=0)
        if 'answer_request' in arguments['properties']:
            arguments['properties']['answer_request']['maxLength'] = 0
        definitions[name] = arguments
        branch = {'properties': {'operation': {'const': name}, 'arguments': {'$ref': '#/$defs/' + name}}}
        if arguments.get('required'):
            branch['required'] = ['arguments']
        choices.append(branch)
    return {'$schema': 'https://json-schema.org/draft/2020-12/schema',
        '$id': 'urn:xsm:host-protocol:1:operation-parameters',
        'title': 'Experimental operation.call structural parameters',
        'type': 'object', 'required': ['session', 'operation'], 'additionalProperties': False,
        'properties': {'session': {'type': 'string', 'minLength': 1},
                       'operation': {'enum': [tool['name'] for tool in TOOLS]},
                       'arguments': {'type': 'object'}},
        'oneOf': choices, '$defs': definitions,
        '$comment': 'Structural inputs only. A schema-valid operation is not proof of runtime support, authorization or effect.'}


def bundle(root=None):
    from .operation_schema import TOOLS
    from .protocol import REQUEST_FIELDS, VERSION
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    root = root.resolve()
    missing = [name for name in REQUIRED if not (root / name).is_file()]
    if missing:
        raise ValueError('public protocol artifacts missing; update xsm: ' + ', '.join(missing))
    artifacts = {}
    for pattern in PATTERNS:
        for filename in sorted(root.glob(pattern)):
            if filename.is_symlink() or not filename.resolve().is_relative_to(root):
                raise ValueError("public protocol artifact symlink or outside installation: " + str(filename.relative_to(root)))
            content = filename.read_bytes()
            artifacts[filename.relative_to(root).as_posix()] = {
                'sha256': hashlib.sha256(content).hexdigest(), 'text': content.decode('utf-8')}
    if json.loads(artifacts['docs/protocol/operations.schema.json']['text']) != operation_schema():
        raise ValueError('public operation schema differs from this installation; update xsm with matching artifacts')
    return {'protocolVersion': VERSION, 'experimental': True, 'methods': sorted(REQUEST_FIELDS),
            'operations': TOOLS, 'artifacts': artifacts,
            'coverage': 'experimental structures and partial conformance; full operation results and native certification remain incomplete'}


def command(_args):
    try:
        print(json.dumps(bundle(), ensure_ascii=False))
        return 0
    except (OSError, ValueError) as error:
        print('xsm protocol contract: ' + str(error), file=sys.stderr)
        return 4
