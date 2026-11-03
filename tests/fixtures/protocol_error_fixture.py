"""Real protocol error boundary after an actual document write; no model."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from xsm import operations, protocol
from xsm.operation_schema import TOOLS
for tool in TOOLS:
    if tool['name']=='xsm_doc':tool['description']+=' XSM_CONFORMANCE_ERROR_FIXTURE'
original=operations.OperationService._call

def call(self,name,args,me):
    value=original(self,name,args,me)
    if name=='xsm_doc' and args.get('action')=='add' and args.get('doc')=='ERROR-FIXTURE.md':
        raise RuntimeError('private-error-fixture-detail')
    return value

operations.OperationService._call=call
protocol.serve()
