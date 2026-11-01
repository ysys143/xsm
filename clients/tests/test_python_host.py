"""Trusted UI callbacks against a real server; no native UI certification."""
import asyncio
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "clients/python"))
from xsm_client import XsmHostClient, RpcError


class HostClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_real_scoped_question_answer_and_retry(self):
        await asyncio.wait_for(self.roundtrip(), 20)

    async def roundtrip(self):
        with tempfile.TemporaryDirectory(prefix="xsm-host-client-") as temp:
            env = {"PATH": os.environ.get("PATH", os.defpath), "HOME": temp,
                   "XSM_HOME": temp + "/state", "PYTHONPATH": str(ROOT),
                   "PYTHONDONTWRITEBYTECODE": "1"}
            async with await XsmHostClient.connect([sys.executable, "-B", "-m", "xsm",
                    "protocol", "serve", "--stdio"], cwd=str(ROOT), env=env) as host:
                session = await host.session_open(runtime="python-ui", profile="isolated",
                    conversation="a", cwd=str(ROOT), capabilities=["user-decisions"])
                arguments = {"question": "Choose a color", "options": ["blue", "green"]}
                pending = await host.operation_call(session["session"], "xsm_decide", arguments)
                self.assertEqual(pending["status"], "waiting-for-user")
                event = await host.next_notification()
                self.assertEqual(event["method"], "decision/request")
                self.assertEqual(event["params"]["question"], arguments["question"])
                with self.assertRaises(PermissionError):
                    await host.request("decision.response", {})
                with self.assertRaises(RpcError):
                    await host.respond_to_decision(event, displayed="wrong display", source_id="ui1", answer="blue")
                answer = await host.respond_to_decision(event, displayed=arguments["question"],
                    source_id="ui1", answer="blue")
                self.assertEqual(answer["status"], "answered")
                # A host callback stores the answer, but never self-applies the operation.
                result = await host.operation_call(session["session"], "xsm_decide", arguments)
                self.assertIn("your user answered: blue", str(result))
                status = await host.operation_call(session["session"], "xsm_decision_status", {"id": pending["decision_id"]})
                self.assertEqual(status["status"], "applied")
