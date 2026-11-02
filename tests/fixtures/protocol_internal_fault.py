"""Real stdio server with one deliberate post-claim failure; isolated by its caller."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from xsm.operations import OperationService
from xsm.protocol import serve

original = OperationService.call
failed = False


def after_claim(self, name, args):
    global failed
    result = original(self, name, args)
    if name == 'xsm_inbox' and not failed:
        failed = True
        raise RuntimeError('private-post-claim-fixture')
    return result


OperationService.call = after_claim
raise SystemExit(serve())
