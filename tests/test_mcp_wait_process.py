"""A real stdio MCP client cancels a wait and recovers its late reply.

The process and wire are real. Only the native model transport is replaced;
no user profile, runtime queue, permission or actual model is modified.
"""
import json
import os
import select
import subprocess
import sys
import time
from unittest import mock
from tests.test_xsm import TempState


class McpWaitProcessTest(TempState):
    def test_ping_cancel_lost_auto_id_and_late_reply_keep_inbox_and_request(self):
        from xsm import adapters, config, envelope, inbox, registry, send
        home = os.path.join(self.tmp, "codex")
        os.makedirs(home)
        me = registry.upsert("codex", home, "me", os.getpid(), self.tmp, name="me")
        peer = registry.upsert("codex", home, "peer", os.getpid(), self.tmp, name="peer")
        scope, _ = config.scope_for(peer, me)
        inbox.keep("me", "unrelated", envelope.build("unrelated", msg_id="unrelated",
                   sender=peer, scope=scope))
        script = ('from xsm import mcp,registry,adapters\n'
                  'adapters.to_codex=lambda *a,**k: None\n'
                  's=mcp.Server()\n'
                  's.session=lambda: registry.by_session("codex","me")\n'
                  'raise SystemExit(s.serve())\n')
        proc = subprocess.Popen([sys.executable, "-u", "-c", script], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        def cleanup():
            if proc.poll() is None:
                proc.terminate()
                try:proc.wait(timeout=3)
                except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=3)
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream:stream.close()
        self.addCleanup(cleanup)
        pending = bytearray()
        def write(obj):
            proc.stdin.write((json.dumps(dict(jsonrpc="2.0", **obj)) + "\n").encode())
            proc.stdin.flush()
        def read(timeout=5):
            deadline = time.monotonic() + timeout
            while b"\n" not in pending:
                left = deadline - time.monotonic()
                self.assertGreater(left, 0, "MCP response timed out")
                ready, _, _ = select.select([proc.stdout], [], [], left)
                self.assertTrue(ready, "MCP reader did not dispatch a response")
                chunk = os.read(proc.stdout.fileno(), 65536)
                self.assertTrue(chunk, "MCP process exited early")
                pending.extend(chunk)
            line, _, rest = pending.partition(b"\n")
            pending[:] = rest
            return json.loads(line)
        write({"id": 0, "method": "initialize", "params": {"capabilities": {}}})
        self.assertEqual(read()["id"], 0)
        write({"id": 1, "method": "tools/call", "params": {"name": "xsm_ask", "arguments": {
            "target": "ref:" + peer["ref"], "text": "question", "wait": 60}}})
        write({"id": 2, "method": "ping"})
        self.assertEqual(read()["id"], 2, "ping must be answered before the waiting ask")
        write({"method": "notifications/cancelled", "params": {"requestId": 1}})
        cancelled = read()
        self.assertEqual(cancelled["id"], 1)
        # A real client discards the cancelled response, including its auto ID.
        # Do not read its result: recover only through a subsequent public call.
        write({"id": 3, "method": "tools/call", "params": {
            "name": "xsm_question_status", "arguments": {}}})
        listing = read()
        self.assertEqual(listing["id"], 3)
        own = json.loads(listing["result"]["content"][0]["text"])["requests"]
        self.assertEqual(len(own), 1)
        self.assertEqual(own[0]["preview"], "question")
        recovered_id = own[0]["id"]
        self.assertEqual(inbox.count("me"), 1)
        with mock.patch.object(adapters, "to_codex", return_value=None):
            sent = send.send("ref:" + me["ref"], "late-reply", sender=peer, kind="reply",
                             reply_to=recovered_id, outcome="succeeded")
        self.assertEqual(sent.status, "sent-unconfirmed")
        write({"id": 4, "method": "tools/call", "params": {"name": "xsm_question_status",
               "arguments": {"id": recovered_id}}})
        got = read()
        self.assertEqual(got["id"], 4)
        recovered = json.loads(got["result"]["content"][0]["text"])
        self.assertEqual(recovered["replies"][0]["body"], "late-reply")
        self.assertTrue(recovered["final"])
        self.assertEqual([c['id'] for c in recovered['claims']], [sent.msg_id])
        self.assertEqual(inbox.count("me"), 1, "only the exact returned reply copy is handed off")
        write({'id': 5, 'method': 'tools/call', 'params': {'name': 'xsm_ack',
               'arguments': {'tokens': [c['token'] for c in recovered['claims']]}}})
        acknowledged = read()
        self.assertEqual(json.loads(acknowledged['result']['content'][0]['text'])['acked'], [sent.msg_id])
        write({'id': 6, 'method': 'tools/call', 'params': {'name': 'xsm_question_status',
               'arguments': {'id': recovered_id}}})
        repeated = json.loads(read()['result']['content'][0]['text'])
        self.assertEqual(repeated['replies'], recovered['replies'])
        self.assertEqual(repeated['claims'], [])
        self.assertEqual(inbox.count('me'), 1, 'ACK must leave unrelated unread text untouched')
        self.assertEqual(inbox.count("peer"), 1, "no repeated task after wait cancellation")
        proc.stdin.close()
        self.assertEqual(proc.wait(timeout=5), 0)
