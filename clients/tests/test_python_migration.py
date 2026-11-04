"""Profile migration through the actual Python SDK and stdio server; model0 UI."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'clients/python'))
from xsm_client import XsmHostClient, RpcError


class ProfileMigrationInteropTest(unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_profile_copy_fencing_forwarding_and_claim(self):
        with tempfile.TemporaryDirectory(prefix='xsm-python-profile-migration-') as temp:
            env = {key: os.environ[key] for key in ('PATH', 'LANG', 'TMPDIR') if key in os.environ}
            env.update(HOME=temp, XSM_HOME=temp + '/state', PYTHONDONTWRITEBYTECODE='1')
            async with await XsmHostClient.connect([sys.executable, '-B', '-m', 'xsm',
                    'protocol', 'serve', '--stdio'], cwd=str(ROOT), env=env) as client:
                a = await client.session_open(runtime='python-migration', profile='a', conversation='copied',
                                               cwd=temp, capabilities=['user-decisions'])
                b = await client.session_open(runtime='python-migration', profile='b', conversation='copied',
                                               cwd=temp, capabilities=['user-decisions'])
                peer = await client.session_open(runtime='python-migration', profile='peer', conversation='peer', cwd=temp)
                await client.operation_call(peer['session'], 'xsm_send', {'target': a['address'],
                    'text': 'before transfer', 'wake': 'never', 'wait': 0, 'request_id': 'python-before-migration'})
                args = {'source': a['address']}
                pending = await client.operation_call(b['session'], 'xsm_migrate', args)
                self.assertEqual(pending['status'], 'waiting-for-user')
                event = await asyncio.wait_for(client.next_notification(), 3)
                self.assertEqual(event['method'], 'decision/request')
                await client.respond_to_decision(event, displayed=event['params']['question'],
                                                  source_id='python-migration-user', answer='allow')
                receipt = await client.operation_call(b['session'], 'xsm_migrate', args)
                self.assertEqual(receipt['status'], 'committed')
                self.assertEqual(receipt['forward_until'] - receipt['committed_at'], 86400)
                replay = await client.operation_call(b['session'], 'xsm_migrate', args)
                self.assertEqual(replay['id'], receipt['id'])
                self.assertEqual(replay['committed_at'], receipt['committed_at'])
                with self.assertRaises(RpcError):
                    await client.operation_call(a['session'], 'xsm_inbox', {})
                await client.operation_call(peer['session'], 'xsm_send', {'target': a['address'],
                    'text': 'after transfer via old address', 'wake': 'never', 'wait': 0,
                    'request_id': 'python-after-migration'})
                catchup = await client.operation_call(b['session'], 'xsm_migrate', {})
                bodies = [item['body'] for item in catchup['migrations'][0]['messages']]
                self.assertIn('before transfer', bodies)
                self.assertIn('after transfer via old address', bodies)
                pack = await client.operation_call(b['session'], 'xsm_inbox', {})
                self.assertEqual({claim['id'] for claim in pack['claims']},
                                 {'python-before-migration', 'python-after-migration'})
                ack = await client.operation_call(b['session'], 'xsm_ack', {'tokens': [c['token'] for c in pack['claims']]})
                self.assertEqual(set(ack['acked']), {'python-before-migration', 'python-after-migration'})


if __name__ == '__main__':
    unittest.main()
