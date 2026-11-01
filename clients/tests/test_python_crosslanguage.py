"""Two SDK implementations and two real servers exchange a request and reply."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "clients/python"))
from xsm_client import XsmClient


class CrossLanguageTest(unittest.IsolatedAsyncioTestCase):
    async def test_python_node_request_reply_with_explicit_ack(self):
        await asyncio.wait_for(self.exchange(), 30)

    async def exchange(self):
        with tempfile.TemporaryDirectory(prefix="xsm-cross-language-") as temp:
            env = {"PATH": os.environ.get("PATH", os.defpath), "HOME": temp,
                   "XSM_HOME": temp + "/state", "PYTHON": sys.executable,
                   "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT)}
            client = await XsmClient.connect(
                [sys.executable, "-B", "-m", "xsm", "protocol", "serve", "--stdio"],
                cwd=str(ROOT), env=env)
            peer = None
            try:
                sender = await client.session_open(runtime="python-cross", profile="isolated",
                    conversation="sender", cwd=str(ROOT), capabilities=["messaging", "events", "inbox"])
                await client.events_subscribe(sender["session"])
                peer = await asyncio.create_subprocess_exec("node",
                    str(ROOT / "clients/tests/cross_language_peer.mjs"), sender["ref"],
                    cwd=str(ROOT), env=env, stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                ready = json.loads(await peer.stdout.readline())
                sent = await client.operation_call(sender["session"], "xsm_send", {
                    "target": "ref:" + ready["ref"], "text": "Python → Node 요청",
                    "kind": "task", "wait": 0})
                self.assertIn("stored", str(sent))
                report = json.loads(await peer.stdout.readline())
                self.assertEqual(len(report["acked"]), 1)
                self.assertIn("stored", str(report["sent"]))
                event = await client.next_notification()
                reply = await client.operation_call(sender["session"], "xsm_inbox", {})
                self.assertEqual(len(reply["claims"]), 1, reply)
                self.assertIn("Node → Python 회신", str(reply["messages"]))
                claim = reply["claims"][0]
                self.assertEqual(event["params"]["ids"], [claim["id"]])
                ack = await client.operation_call(sender["session"], "xsm_ack", {"tokens": [claim["token"]]})
                self.assertEqual(ack["acked"], [claim["id"]])
                records = [json.loads(p.read_text()) for p in Path(env["XSM_HOME"]).glob("handoffs/*/*.json")]
                self.assertEqual(len(records), 2)
                self.assertTrue(all(r["state"] == "acknowledged" for r in records))
                peer.stdin.write(b"finished\n")
                await peer.stdin.drain()
                await asyncio.wait_for(peer.wait(), 5)
                self.assertEqual(peer.returncode, 0, (await peer.stderr.read()).decode())
            finally:
                if peer and peer.returncode is None:
                    peer.kill()
                    await peer.wait()
                await client.close()
