"""Real stdio server interop; child HOME/XSM_HOME are isolated before imports."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "clients" / "python"))
from xsm_client import RpcError, XsmClient


class RealProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_four_mib_bundle_is_prepared_in_chunks_then_explicitly_sent(self):
        import base64
        import hashlib
        with tempfile.TemporaryDirectory(prefix='xsm-upload-wire-') as temp:
            env = {'PATH': os.environ.get('PATH', os.defpath), 'HOME': temp,
                   'XSM_HOME': temp + '/state', 'PYTHONDONTWRITEBYTECODE': '1'}
            async with await XsmClient.connect(
                    [sys.executable, '-B', '-m', 'xsm', 'protocol', 'serve', '--stdio'],
                    cwd=str(ROOT), env=env) as client:
                a, b = [await client.session_open(runtime='upload-fixture', profile='private',
                         conversation=name, cwd=temp) for name in ('sender', 'receiver')]
                await client.operation_call(b['session'], 'xsm_inbox', {})
                entries = [{'name': 'file%d.bin' % index, 'data': bytes([index]) * 1048576}
                           for index in range(4)]
                prepared = await client.prepare_files(a['session'], target=b['address'],
                    request_id='four-mib', text='four exact copies', entries=entries)
                self.assertFalse(prepared['body_sent'])
                self.assertEqual((await client.operation_call(b['session'], 'xsm_inbox', {}))['items'], [])
                result = await client.operation_call(a['session'], 'xsm_send', {
                    'target': b['address'], 'request_id': 'four-mib', 'text': 'four exact copies',
                    'manifest_id': prepared['manifest_id'], 'wake': 'never', 'wait': 0})
                self.assertNotEqual(result['send']['status'], 'refused')
                pack = await client.operation_call(b['session'], 'xsm_inbox', {})
                copy = pack['items'][0]['files']
                self.assertEqual(len(copy['files']), 4)
                for original, metadata in zip(entries, copy['files']):
                    result = await client.operation_call(b['session'], 'xsm_files', {
                        'storage_id': copy['storage_id'], 'entry_id': metadata['id'], 'encoding': 'base64'})
                    data = base64.b64decode(result['content'], validate=True)
                    self.assertEqual(data, original['data'])
                    self.assertEqual(hashlib.sha256(data).hexdigest(), metadata['sha256'])
                ack = await client.operation_call(b['session'], 'xsm_ack', {
                    'tokens': [claim['token'] for claim in pack['claims']]})
                self.assertEqual(ack['acked'], ['four-mib'])

    async def test_internal_rpc_error_preserves_claim_and_connection(self):
        with tempfile.TemporaryDirectory(prefix='xsm-python-internal-error-') as temp:
            diagnostics = []
            env = {"PATH": os.environ.get("PATH", os.defpath), "HOME": temp,
                "XSM_HOME": temp + '/state', "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": '1'}
            async with await XsmClient.connect([sys.executable, '-B',
                str(ROOT / 'tests/fixtures/protocol_internal_fault.py')], env=env,
                cwd=str(ROOT), on_stderr=diagnostics.append) as client:
                a, b = [await client.session_open(runtime='python-error', profile='fixture',
                    conversation=value, cwd=str(ROOT), capabilities=['messaging', 'inbox', 'events'])
                    for value in ('a', 'b')]
                await client.events_subscribe(b['session'])
                await client.operation_call(a['session'], 'xsm_send', {
                    'target': 'ref:' + b['ref'], 'text': 'retain after internal error', 'wait': 0})
                event = await asyncio.wait_for(client.next_notification(), 3)
                with self.assertRaises(RpcError) as caught:
                    await client.operation_call(b['session'], 'xsm_inbox', {})
                self.assertEqual(caught.exception.code, -32603)
                self.assertEqual(str(caught.exception), 'internal server error')
                pack = await client.operation_call(b['session'], 'xsm_inbox', {'message_ids': event['params']['ids']})
                self.assertEqual([claim['id'] for claim in pack['claims']], event['params']['ids'])
                ack = await client.operation_call(b['session'], 'xsm_ack', {'tokens': [c['token'] for c in pack['claims']]})
                self.assertEqual(ack['acked'], event['params']['ids'])
                self.assertEqual(await client.session_update(b['session'], {'state': 'idle'}), {'state': 'idle'})
            self.assertNotIn('private-post-claim-fixture', ''.join(diagnostics))
            self.assertNotIn('Traceback', ''.join(diagnostics))

    async def test_real_server_two_sessions_send_inbox_ack(self):
        await asyncio.wait_for(self.roundtrip(), 30)

    async def roundtrip(self):
        with tempfile.TemporaryDirectory(prefix="xsm-python-interop-") as temp:
            home, state = Path(temp) / "home", Path(temp) / "state"
            home.mkdir()
            state.mkdir()
            # Do not inherit runtime identities, policy overrides, or credentials.
            env = {"PATH": os.environ.get("PATH", os.defpath), "HOME": str(home),
                   "XSM_HOME": str(state), "PYTHONPATH": str(ROOT),
                   "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"}
            async with await XsmClient.connect(
                [sys.executable, "-m", "xsm", "protocol", "serve", "--stdio"],
                cwd=str(ROOT), env=env,
            ) as client:
                self.assertEqual(client.initialization["protocolVersion"], "1")
                a, b = await asyncio.gather(*[
                    client.session_open(runtime="python-interop", profile="isolated",
                                        conversation=conversation, cwd=str(ROOT), capabilities=[])
                    for conversation in ("sender", "receiver")
                ])
                self.assertNotEqual(a["session"], b["session"])
                self.assertNotEqual(a["ref"], b["ref"])
                records = [json.loads(p.read_text()) for p in (state / "sessions").glob("*.json")]
                self.assertEqual(len(records), 2)
                self.assertTrue(all(r["cwd"] == str(ROOT) for r in records))
                self.assertTrue(all(Path(r["home"]).is_relative_to(state) for r in records))
                self.assertEqual(await client.session_update(a["session"], {"state": "busy"}), {"state": "busy"})
                with self.assertRaises(RpcError) as caught:
                    await client.session_update(a["session"], {"cwd": str(home)})
                self.assertEqual(caught.exception.code, -32602)
                await client.events_subscribe(b["session"])
                sent = await client.operation_call(a["session"], "xsm_send", {
                    "target": "ref:" + b["ref"], "text": "실제 Python 전송", "wait": 0,
                })
                self.assertIn("stored", str(sent))
                event = await client.next_notification()
                self.assertEqual(event["method"], "events/available")
                self.assertEqual(event["params"]["session"], b["session"])
                self.assertEqual(len(event["params"]["ids"]), 1)
                mid = event["params"]["ids"][0]
                originals = list((state / "handoffs").glob("*/" + mid + ".json"))
                self.assertEqual(len(originals), 1)
                for delivery_state in ("queued", "refused", "unknown"):
                    self.assertEqual(await client.delivery_report(b["session"], mid, delivery_state),
                                     {"recorded": delivery_state, "acknowledged": False})
                    self.assertEqual(json.loads(originals[0].read_text())["state"], "pending")
                with self.assertRaises(RpcError) as caught:
                    await client.delivery_report(b["session"], mid, "received")
                self.assertEqual(caught.exception.code, -32602)
                pack = await client.operation_call(b["session"], "xsm_inbox", {"wait": 0})
                self.assertIn("실제 Python 전송", str(pack["messages"]))
                self.assertEqual(len(pack["claims"]), 1)
                claim = pack["claims"][0]
                self.assertEqual(claim["id"], mid)
                self.assertNotEqual(json.loads(originals[0].read_text())["state"], "acknowledged")
                ack = await client.operation_call(b["session"], "xsm_ack", {"tokens": [claim["token"]]})
                self.assertEqual(ack["acked"], [mid])
                self.assertEqual(ack["inbox_pending"], 0)
                self.assertEqual(json.loads(originals[0].read_text())["state"], "acknowledged")
                empty = await client.operation_call(b["session"], "xsm_inbox", {"wait": 0})
                self.assertEqual(empty["messages"], [])
                self.assertEqual(empty["claims"], [])
                for opened in (a, b):
                    self.assertEqual(await client.session_close(opened["session"]), {"closed": True})
            self.assertEqual(client.process.returncode, 0)


if __name__ == "__main__":
    unittest.main()
