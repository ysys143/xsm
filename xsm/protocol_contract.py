"""Read-only export of this installation's public experimental protocol artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

PATTERNS = ('docs/protocol/*.json', 'docs/protocol/*.md', 'scripts/conform-host-protocol.py', 'scripts/check-protocol-schema.py')
REQUIRED = ('docs/protocol/README.md', 'docs/protocol/request.schema.json',
            'docs/protocol/request-examples.json', 'docs/protocol/output.schema.json',
            'docs/protocol/output-examples.json', 'scripts/conform-host-protocol.py', 'scripts/check-protocol-schema.py')


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
