"""P00 crash-control fixtures: a real process dies at a named boundary, and the
next run is observed.

[execution.md G00](../../docs/plan/reason-inspired-adrs/execution.md) and
[spec.md P00.4](../../docs/plan/reason-inspired-adrs/spec.md) ask for fixtures
that die at a boundary and then run again. Two boundaries are covered.

1. **After the connection is applied, before the message goes.** The person
   already said yes; `connect.run` made the link; the process dies before the
   send. What is on disk afterwards, and what does the same command do next?
2. **Between the inbox claim and the ack.** `inbox.take` renames a waiting
   copy to `.taking` and then unlinks it. The process dies between those two
   steps.

The fixtures record what the code does today. Whether recovery is complete is
for G02/G04 to judge; P00 only makes each boundary reproducible. Each fixture
is driven through the real CLI as a subprocess, so the death is a real process
death (SIGKILL) and not a mock.
"""
import os
import json
import signal
import subprocess
import sys
import tempfile
import unittest

# The suite runs on 3.9 too (docs/xsm/TESTPLAN.md requires 3.9+): no PEP 604
# unions in signatures, no match statements. Keep this file 3.9-readable.

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests import test_xsm  # noqa: E402
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TempState = test_xsm.TempState


def _killer_sitecustomize(probe_dir, when):
    """A sitecustomize.py that SIGKILLs this process at the boundary named by
    `when`. `when` is python source placed inside `_arm()`; it patches what
    it needs and calls `_kill()`. `_kill` writes `<probe_dir>/boundary-reached`
    first, so a test can tell "the boundary was reached" from "died earlier"."""
    body = '\n'.join([
        "import os, signal, sys",
        "_BOUNDARY_DIR = %r" % probe_dir,
        "",
        "def _touch():",
        "    try:",
        "        with open(os.path.join(_BOUNDARY_DIR, 'boundary-reached'), 'w') as fh:",
        "            fh.write('reached')",
        "    except OSError:",
        "        pass",
        "",
        "def _kill():",
        "    import traceback",
        "    try:",
        "        with open(os.path.join(_BOUNDARY_DIR, 'boundary-stack'), 'w') as fh:",
        "            traceback.print_stack(file=fh)",
        "    except OSError:",
        "        pass",
        "    _touch()",
        "    os.kill(os.getpid(), signal.SIGKILL)",
        "",
        "def _arm():",
        when,
        "",
        "try:",
        "    _arm()",
        "except Exception:",
        "    pass",
        "",
    ])
    path = os.path.join(probe_dir, "sitecustomize.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return path


class _Harness(TempState):
    """A Claude session in folder A and a Codex session in folder B, two
    repositories nobody linked."""

    def setUp(self):
        super().setUp()
        from xsm import registry
        self.a = os.path.realpath(os.path.join(self.tmp, "proj-a"))
        self.b = os.path.realpath(os.path.join(self.tmp, "proj-b"))
        for folder in (self.a, self.b):
            os.makedirs(folder, exist_ok=True)
        registry.upsert("claude", os.path.join(self.tmp, "homes", "claude"), "s-sender",
                        os.getpid(), self.a, name="sender")
        registry.upsert("codex", os.path.join(self.tmp, "homes", "codex"), "s-target",
                        os.getpid(), self.b, name="target")
        self.me = registry.by_session("claude", "s-sender")
        self.you = registry.by_session("codex", "s-target")
        self.target = "ref:%s" % self.you["ref"]
        self.probe = os.path.join(self.tmp, "boundary-" + self._testMethodName)
        os.makedirs(self.probe, exist_ok=True)

    def _base_env(self, runtime="claude", **extra):
        """A shell that knows its runtime, without the session's own process
        markers: the point is that the CLI picks a registered session."""
        env = {k: v for k, v in os.environ.items()
               if k in ("LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "USER")}
        env.update(PATH=os.environ.get("PATH", "/usr/bin:/bin"), HOME=self.user_home,
                   XSM_HOME=self.tmp, PYTHONPATH=REPO,
                   XSM_CODEX=self._fake_codex(),
                   XSM_NO_CODEX_WAKE="1")
        if runtime == "claude":
            env["CLAUDE_CODE_SESSION_ID"] = "s-sender"
        else:
            env["CODEX_THREAD_ID"] = "s-target"
        env.pop("CODEX_HOME", None)
        env.pop("CLAUDE_CONFIG_DIR", None)
        env.pop("CLAUDE_CODE_MESSAGING_SOCKET", None)
        env.update(extra)
        return env

    def _fake_codex(self):
        """A `codex` that answers as an installed one does, so the send under
        test does not open a real Codex home's state database."""
        path = os.path.join(self.tmp, "fake-codex")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("#!%s\n" % sys.executable)
                fh.write("import sys\n"
                         "args = sys.argv[1:]\n"
                         "thread = args[args.index('--thread') + 1] if '--thread' in args else '?'\n"
                         "print('Queued message 0123456789abcdef for thread %s.' % thread)\n")
            os.chmod(path, 0o755)
        return path

    def _cli(self, *argv, **extra):
        probe = extra.pop("probe", None)
        runtime = extra.pop("_runtime", "claude")
        env = self._base_env(runtime, **extra)
        if probe:
            env["PYTHONPATH"] = probe + os.pathsep + REPO
        proc = subprocess.run([sys.executable, "-m", "xsm", *argv],
                              cwd=self.a, env=env, capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def _reached(self):
        return os.path.exists(os.path.join(self.probe, "boundary-reached"))

    def _reply(self, text):
        from xsm import consent
        consent.record(self.me, {"hook_event_name": "UserPromptSubmit", "prompt": text})

    def _waited(self):
        from xsm import consent, paths
        files = consent.pending_files(self.me["ref"])
        if not files:
            return
        entry = paths.read_json(files[0])
        entry["shown_t"] -= consent.SHOW_DELAY + 1
        paths.write_json(files[0], entry)


class ConnectionThenCrashTest(_Harness):
    """Boundary 1: the connection was applied, the message was not sent."""

    def _arm_after_add_link(self):
        _killer_sitecustomize(self.probe, '\n'.join([
            "    from xsm import config",
            "    _real = config.add_link",
            "    def _wrapped(*a, **kw):",
            "        out = _real(*a, **kw)",
            "        _kill()",
            "    config.add_link = _wrapped",
        ]))

    def _refuse_then_yes(self):
        """One send is refused and holds the message; the person's yes is left
        on record and shown, so the next send takes the connect-and-send path."""
        code, out, err = self._cli("send", self.target, "--text", "hello b")
        self.assertEqual(code, 2, out + err)
        self.assertIn("out of scope", out + err)
        self._reply("응, 그 저장소 연결해서 보내줘")
        code, shown, err = self._cli("send", self.target, "--text", "hello b")
        self.assertEqual(code, 2, shown + err)
        self.assertIn("your user replied", shown)
        self._waited()

    def test_the_link_survives_and_the_message_is_still_held(self):
        from xsm import config, outbox
        self._refuse_then_yes()
        self.assertEqual(config.links(), [], "nothing is connected yet")
        held_before = outbox._records()
        self.assertEqual([h["body"] for h in held_before], ["hello b"])

        self._arm_after_add_link()
        code, out, err = self._cli("send", self.target, "--text", "hello b",
                                   probe=self.probe)

        self.assertEqual(code, -signal.SIGKILL,
                         "the process must die at the boundary\n%s\n%s" % (out, err))
        self.assertTrue(self._reached(), "the kill must come from the add_link wrapper")
        self.assertEqual(len(config.links()), 1,
                         "the connection was applied before the process died")
        after = outbox._records()
        self.assertEqual([h["id"] for h in after], [held_before[0]["id"]],
                         "the held message is still the one that never went")

    def test_the_retry_after_the_crash_sends_without_a_new_question(self):
        from xsm import config, consent, ledger, outbox
        self._refuse_then_yes()
        held_before = outbox._records()[0]["id"]
        self._arm_after_add_link()
        self._cli("send", self.target, "--text", "hello b", probe=self.probe)
        pending_before = sorted(os.listdir(
            consent.paths.path(consent.ASKED))) if os.path.isdir(
                consent.paths.path(consent.ASKED)) else []

        code, out, err = self._cli("send", self.target, "--text", "hello b")

        self.assertEqual(code, 3, "sent-unconfirmed, as any send\n%s\n%s" % (out, err))
        pending_after = sorted(os.listdir(consent.paths.path(consent.ASKED)))
        self.assertEqual(len(pending_after), len(pending_before),
                         "a retry must not open a new question")
        rows = ledger.recent()
        self.assertEqual(len(config.links()), 1, "no second link")
        # P02 item 5: the retry must send under the id the crashed run held, so
        # one yes and one message keep one identity across the crash. Before the
        # fix the retry minted a new id and left the held copy behind (recorded
        # in G00 as "the retry sends under a NEW id").
        self.assertEqual([r["id"] for r in rows], [held_before],
                         "the retry sends under the held id")
        self.assertEqual(outbox._records(), [],
                         "the held copy went with the send, not left for TTL")


class InboxClaimThenCrashTest(_Harness):
    """P04: durable native claim survives reader SIGKILL before handoff/ack."""

    def _arm_after_claim(self):
        _killer_sitecustomize(self.probe, '\n'.join([
            "    from xsm import handoff",
            "    _real = handoff._write",
            "    def _wrapped(p, record):",
            "        _real(p, record)",
            "        if record.get('state') == 'claimed' and record['receiver']['session_id'] == %r:" % self.you['session_id'],
            "            _kill()",
            "    handoff._write = _wrapped",
        ]))

    def _waiting(self, msg_id, body):
        from xsm import config, envelope, inbox
        config.add_link(self.a,self.b,'fixture approval')
        content = envelope.build(body, msg_id=msg_id, sender=self.me,
                                 scope=config.scope_for(self.me,self.you)[0], kind="task")
        inbox.keep(str(self.you["session_id"]), msg_id, content,receiver=self.you)
        return os.path.join(inbox._dir(str(self.you["session_id"])), "%s.json" % msg_id)

    def _inbox_dir(self):
        from xsm import inbox
        return inbox._dir(str(self.you["session_id"]))

    def _stack(self):
        p = os.path.join(self.probe, "boundary-stack")
        if not os.path.exists(p):
            return ""
        with open(p, encoding="utf-8") as fh:
            return fh.read()

    def test_the_claim_dies_between_the_rename_and_the_ack(self):
        msg_id = "0" * 15 + "1"
        waiting = self._waiting(msg_id, "a task for b")
        self.assertTrue(os.path.exists(waiting))

        self._arm_after_claim()
        env = self._base_env("codex", PYTHONPATH=self.probe + os.pathsep + REPO)
        proc = subprocess.run([sys.executable, "-m", "xsm", "inbox"],
                              cwd=self.b, env=env, capture_output=True, text=True)

        self.assertEqual(proc.returncode, -signal.SIGKILL,
                         "the claim must die at the ack\n%s\n%s" % (proc.stdout, proc.stderr))
        self.assertTrue(self._reached())
        self.assertIn("xsm/handoff.py", self._stack(),
                      "the kill must come from the canonical claim\n%s" % self._stack()[-600:])
        self.assertNotIn("xsm/bounce.py", self._stack())
        from xsm import handoff
        record=handoff.status(self.you,msg_id)
        self.assertEqual(record['status'],'claimed')
        self.assertEqual(record['message']['body'],'a task for b')

    def test_a_later_inbox_run_recovers_the_original_after_lease_expiry(self):
        from xsm import handoff,housekeeping,receive
        msg_id = "0" * 15 + "2"
        self._waiting(msg_id, "another task for b")
        self._arm_after_claim()
        env = self._base_env("codex", PYTHONPATH=self.probe + os.pathsep + REPO)
        crashed=subprocess.run([sys.executable, "-m", "xsm", "inbox"],
                       cwd=self.b, env=env, capture_output=True, text=True)
        self.assertEqual(crashed.returncode,-signal.SIGKILL)
        before=handoff.status(self.you,msg_id)
        clock=before['claim']['deadline_mono']+1
        resume=os.path.join(self.tmp,'resume-clock');os.makedirs(resume)
        with open(os.path.join(resume,'sitecustomize.py'),'w') as stream:
            stream.write('from xsm import handoff\nhandoff._monotonic=lambda: %r\n' % clock)
        code,out,err=self._cli('inbox','--json',_runtime='codex',probe=resume)
        self.assertEqual(code,0,err)
        pack=json.loads(out)
        self.assertIn('another task for b',pack['messages'][0])
        self.assertNotEqual(pack['claims'][0]['token'],before['claim']['token'])
        with mock.patch.object(handoff,'_monotonic',return_value=clock):
            receive.ack_inbox(self.you,[c['token'] for c in pack['claims']])
        self.assertEqual(handoff.status(self.you,msg_id)['status'],'acknowledged')
        housekeeping.prune()
        self.assertEqual(handoff.status(self.you,msg_id)['message']['body'],'another task for b')


class FixtureSelfTest(unittest.TestCase):
    """The sitecustomize must actually kill, and only at the boundary."""

    def test_it_kills_at_the_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            _killer_sitecustomize(folder, "    pass\n    _kill()")
            env = {**os.environ,
                   "PYTHONPATH": folder + os.pathsep + os.environ.get("PYTHONPATH", "")}
            proc = subprocess.run([sys.executable, "-c", "pass"], env=env,
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, -signal.SIGKILL)
            self.assertTrue(os.path.exists(os.path.join(folder, "boundary-reached")))

    def test_no_marker_when_the_boundary_is_not_reached(self):
        with tempfile.TemporaryDirectory() as folder:
            _killer_sitecustomize(folder, "    pass")
            env = {**os.environ,
                   "PYTHONPATH": folder + os.pathsep + os.environ.get("PYTHONPATH", "")}
            subprocess.run([sys.executable, "-c", "pass"], env=env,
                           capture_output=True, text=True)
            self.assertFalse(os.path.exists(os.path.join(folder, "boundary-reached")))


if __name__ == "__main__":
    unittest.main()
