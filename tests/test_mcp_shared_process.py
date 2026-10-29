"""One real shared MCP process serves two Codex threads of one daemon.

A17-02, A19-02 and A23-03: the process, the stdio wire, the ancestor lookup and
`params._meta.threadId` are real. The native model transport is not started and
no user profile, queue or permission is touched. The daemon is a copy of
/bin/sh named `codex`, so `identity.ancestor_pid` finds it as the session
process and every thread shares its pid, as under a real Codex app-server.
"""
import json
import os
import select
import shutil
import subprocess
import sys
import time
import unittest

from tests.test_xsm import TempState

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def fake_codex(directory):
    """A signed copy of /bin/sh named `codex`, or None where that cannot run."""
    path = os.path.join(directory, "codex")
    try:
        shutil.copy("/bin/sh", path)
        if sys.platform == "darwin":
            subprocess.run(["codesign", "--force", "-s", "-", path], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        probe = subprocess.run([path, "-c", "exit 0"], timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return path if probe.returncode == 0 else None


class SharedMcpProcessTest(TempState):
    def setUp(self):
        super().setUp()
        self.codex = fake_codex(self.tmp)
        if not self.codex:
            self.skipTest("a runnable copy of /bin/sh named codex is unavailable")
        self.pending = bytearray()
        self.errors = open(os.path.join(self.tmp, "mcp.stderr"), "wb")
        self.addCleanup(self.errors.close)
        self.proc = subprocess.Popen(
            [self.codex, "-c", '"$0" "$1"; exit 0', sys.executable,
             os.path.join(ROOT, "hooks", "xsm-mcp.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.errors, bufsize=0,
            env=dict(os.environ, XSM_HOME=self.tmp, HOME=self.user_home,
                     CODEX_HOME=os.path.join(self.tmp, "codex-home"),
                     PYTHONDONTWRITEBYTECODE="1"))
        self.addCleanup(self.stop)
        self.next_id = 0
        self.rpc("initialize", {"capabilities": {}})

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=3)
        for stream in (self.proc.stdin, self.proc.stdout):
            if stream:
                stream.close()

    def stderr_text(self):
        with open(self.errors.name, "rb") as handle:
            return handle.read(2000)

    def send(self, method, params, ident=None):
        ident = self.next_id if ident is None else ident
        self.next_id = max(self.next_id, ident) + 1
        line = json.dumps({"jsonrpc": "2.0", "id": ident, "method": method, "params": params})
        self.proc.stdin.write((line + "\n").encode())
        self.proc.stdin.flush()
        return ident

    def read(self, timeout=10):
        deadline = time.monotonic() + timeout
        while b"\n" not in self.pending:
            left = deadline - time.monotonic()
            self.assertGreater(left, 0, "MCP response timed out")
            ready, _, _ = select.select([self.proc.stdout], [], [], left)
            self.assertTrue(ready, "MCP reader did not dispatch a response")
            chunk = os.read(self.proc.stdout.fileno(), 65536)
            self.assertTrue(chunk, "MCP process exited early: %r" % self.stderr_text())
            self.pending.extend(chunk)
        line, _, rest = self.pending.partition(b"\n")
        self.pending[:] = rest
        return json.loads(line)

    def rpc(self, method, params):
        ident = self.send(method, params)
        reply = self.read()
        self.assertEqual(reply["id"], ident)
        return reply

    def tool(self, thread, name, arguments=None):
        """One tools/call naming the calling thread; the decoded text or the error."""
        reply = self.rpc("tools/call", {"name": name, "arguments": arguments or {},
                                        "_meta": {"threadId": thread}})
        if "error" in reply:
            return reply["error"]["message"]
        result = reply["result"]
        text = result["content"][0]["text"]
        return text if result.get("isError") else text

    def register(self, thread, folder, name):
        from xsm import registry
        home = os.path.join(self.tmp, "codex-home")
        os.makedirs(folder, exist_ok=True)
        record = registry.upsert("codex", home, thread, self.proc.pid, folder, name=name)
        self.assertTrue(registry.note_capabilities(
            record, {"files": {"status": "observed", "version": 1}}, reader_pid=os.getpid()))
        return record

    def link(self, one, other):
        """The person linked two folders, so messages between them are in scope."""
        from xsm import config
        config.add_link(config.project_root(one["cwd"]), config.project_root(other["cwd"]), "tester")

    def test_two_threads_of_one_process_keep_their_own_inbox_and_copies(self):
        from xsm import handoff
        a = self.register("thread-a", os.path.join(self.tmp, "proj-a"), "a")
        b = self.register("thread-b", os.path.join(self.tmp, "proj-b"), "b")
        sender = self.register("thread-s", os.path.join(self.tmp, "proj-s"), "s")
        for who, text in ((a, "only a may read this"), (b, "only b may read this")):
            self.link(sender, who)
            # The sender is a third thread of the same process, so the send is a real call.
            answer = self.tool("thread-s", "xsm_send", {
                "target": "ref:" + who["ref"], "text": "body-" + who["name"].upper() + "-ONLY", "kind": "task",
                "request_id": "msg-" + who["name"], "wake": "never", "wait": 0,
                "attachments": [{"name": who["name"] + ".txt", "text": text}]})
            self.assertIn("stored", answer)

        # Alternate A, B, A, B: the thread named in each call decides the caller.
        seen = {}
        for turn, thread in enumerate(("thread-a", "thread-b", "thread-a", "thread-b")):
            pack = json.loads(self.tool(thread, "xsm_inbox"))
            bodies = json.dumps(pack["messages"])
            mine = "a" if thread == "thread-a" else "b"
            other = "b" if mine == "a" else "a"
            if turn < 2:
                # A claimed message is not shown again until it is acknowledged.
                self.assertIn("body-%s-ONLY" % mine.upper(), bodies, "turn %d" % turn)
            self.assertNotIn("body-%s-ONLY" % other.upper(), bodies, "turn %d" % turn)
            seen.setdefault(thread, pack)

        storage = {}
        for who in (a, b):
            storage[who["name"]] = handoff.status(who, "msg-" + who["name"])["message"]["file_storage"]
        for thread, mine, other in (("thread-a", "a", "b"), ("thread-b", "b", "a")):
            manifest = json.loads(self.tool(thread, "xsm_files", {"storage_id": storage[mine]}))["manifest"]
            entry = manifest["files"][0]["id"]
            content = json.loads(self.tool(thread, "xsm_files", {
                "storage_id": storage[mine], "entry_id": entry}))["content"]
            self.assertEqual(content, "only %s may read this" % mine)
            # The other thread's copy is refused for this caller, not read as theirs.
            refused = self.tool(thread, "xsm_files", {"storage_id": storage[other]})
            self.assertNotIn("may read this", refused)
            self.assertNotIn(other + ".txt", refused)

    def test_a_call_naming_no_thread_among_several_is_not_signed_as_the_newest(self):
        a = self.register("thread-a", os.path.join(self.tmp, "proj-a"), "a")
        self.register("thread-b", os.path.join(self.tmp, "proj-b"), "b")
        sender = self.register("thread-s", os.path.join(self.tmp, "proj-s"), "s")
        self.link(sender, a)
        self.assertIn("stored", self.tool("thread-s", "xsm_send", {
            "target": "ref:" + a["ref"], "text": "PRIVATE-TO-A", "kind": "task",
            "request_id": "only-a", "wake": "never", "wait": 0}))
        reply = self.rpc("tools/call", {"name": "xsm_inbox", "arguments": {}})
        text = json.dumps(reply)
        self.assertNotIn("PRIVATE-TO-A", text)


if __name__ == "__main__":
    unittest.main()
