"""Actual stdio with an explicitly synthetic runtime; no model or native process."""
from pathlib import Path
import os
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from xsm import protocol, workers, owned_service

from xsm.operation_schema import TOOLS
for tool in TOOLS:
    if tool['name'] == 'xsm_owned': tool['description'] += ' XSM_CONFORMANCE_MODEL0_ONLY'

require_native = workers._require_owned_native
workers._require_owned_native = lambda runtime: None if runtime == 'codex' else require_native(runtime)
workers._check_installed = lambda *args: None
workers._execute_owned = lambda worker, context, body, request: {
    'body': 'fixture owned result', 'outcome': 'succeeded',
    'native_session_id': str(uuid.uuid4()), 'execution': {'pid': os.getpid(), 'private': True}}
workers._reply_owned = lambda worker, request: {'id': request['reply_id'], 'status': 'stored'}
limit = workers._limit

def fixture_limit(key, variable, default):
    if key == 'max_workers':
        marker = Path(os.environ['XSM_HOME']) / 'owned-fixture-capacity'
        return int(marker.read_text()) if marker.exists() else 0
    return limit(key, variable, default)

workers._limit = fixture_limit
original_projection = owned_service.public_result

def projection(value):
    result = original_projection(value)
    if len(sys.argv)>1 and sys.argv[1]=='private-leak': result['home']='/private-fixture-profile'
    if len(sys.argv)>1 and sys.argv[1]=='missing-result-body' and isinstance(result.get('result'),dict):
        result['result'].pop('body',None)
    return result

owned_service.public_result = projection
protocol.serve()
