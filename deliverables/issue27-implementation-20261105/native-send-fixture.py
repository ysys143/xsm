"""A model0 SDK peer sends to the old address; actual Claude consumes it."""
import asyncio
import json
import os
from pathlib import Path
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path.insert(0, str(ROOT / 'clients/python'))
from xsm_client import XsmHostClient


async def main():
    info = json.loads((OUT / 'native-preflight.json').read_text())
    root = Path(info['root'])
    env = {key: os.environ[key] for key in ('PATH', 'LANG', 'TMPDIR') if key in os.environ}
    env.update(HOME=str(root / 'fixture-user'), XSM_HOME=str(root / 'state'), PYTHONDONTWRITEBYTECODE='1')
    Path(env['HOME']).mkdir(exist_ok=True)
    async with await XsmHostClient.connect([sys.executable, '-B', '-m', 'xsm', 'protocol', 'serve', '--stdio'],
                                           cwd=str(ROOT), env=env) as client:
        peer = await client.session_open(runtime='migration-probe', profile='sender', conversation='sender', cwd=str(root/'work'))
        result = await client.operation_call(peer['session'], 'xsm_send',
            {'target':'ref:a1a8a3', 'text':'XSM_NATIVE_OLD_ADDRESS_FORWARDED_20261105',
             'wake':'never', 'wait':0, 'request_id':'native-old-address-probe'})
        (OUT/'native-peer-send.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result))


asyncio.run(main())
