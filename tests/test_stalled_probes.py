"""Issue #17/#18: a command must not wait for a probe that never answers.

`xsm list`, `who`, `doctor` and `send` took 60-180 s on a real machine. On that
machine every `lsof` hung, and the Codex scan ran one per Codex window and per
Codex home, five seconds each. These tests rebuild that machine for real (real
processes, a real `lsof` that sleeps, wall-clock time) and run `bin/xsm` on it:

- LAT-1: the display commands finish while `lsof` hangs.
- LAT-2: a send to a live session by address delivers while `lsof` hangs, from
  the shell and from the MCP server.
- LAT-3: with nothing hanging, 350 unrelated pointers cost about what 10 do.
- OBS-1: and what did not answer is said so: `list` and `doctor` name the probe,
  the command's span counts it, and with nothing hanging `list` says nothing.

Nothing here touches the real ~/.xsm or the real home: every command runs on a
temporary XSM_HOME and HOME.
"""
import glob
import importlib
import io
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from tests import test_xsm

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER = os.path.join(REPO, "bin", "xsm")

BUDGET = 15.0           # seconds a command may take while lsof hangs
HARD_TIMEOUT = 120.0    # a regression fails here instead of hanging the suite
POINTERS = 350
FOLDERS = 60
WINDOWS = 4
EXTRA = 2.0             # what 340 more pointers may add (LAT-3)

MINE = "mine-thread"
CLAUDE_SID = "claude-target-sid"
CODEX_SID = "codex-target-thread"


def dead_pid() -> int:
    """The pid of a child that has already been reaped: certainly not running."""
    for _ in range(5):
        child = subprocess.Popen(["true"])
        child.wait()
        try:
            os.kill(child.pid, 0)
        except ProcessLookupError:
            return child.pid
    raise RuntimeError("could not find a dead pid")


class Inbox:
    """A Claude session's inbox socket: keeps the JSON line each delivery writes.

    xsm connects to it twice, once to ask if it is alive (that writes nothing)
    and once to deliver, so a connection without data is not a message.
    """

    def __init__(self, path: str):
        self.path = path
        self.frames = []
        self.connections = 0
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(path)
        self._sock.listen(32)
        self._sock.settimeout(0.2)
        self._thread = threading.Thread(target=self._accept, daemon=True)
        self._thread.start()

    def _accept(self):
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with self._lock:
                self.connections += 1
            threading.Thread(target=self._read, args=(conn,), daemon=True).start()

    def _read(self, conn):
        data = b""
        with conn:
            conn.settimeout(5)
            try:
                while True:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    data += chunk
            except OSError:
                pass
        for line in data.splitlines():
            if line.strip():
                with self._lock:
                    self.frames.append(json.loads(line))

    def wait(self, count: int, seconds: float = 5.0) -> list:
        """The frames received, once there are `count` of them or time is up."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            with self._lock:
                if len(self.frames) >= count:
                    break
            time.sleep(0.05)
        with self._lock:
            return list(self.frames)

    def close(self):
        self._stop.set()
        self._thread.join(2)
        self._sock.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass


class Machine(test_xsm.TempState):
    """A temporary machine: three trusted Codex homes, one Claude home, a work
    tree of folders, hundreds of pointers, and two live sessions to talk to.

    Anything that holds a unix socket lives under a short /tmp path: the temp
    folder macOS gives a process is too long for a socket path.
    """

    def setUp(self):
        super().setUp()
        from xsm import config, paths, registry
        # TempState removes its folder in tearDown, which does not run when this
        # setUp fails half way.
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="xsm-sp-", dir="/tmp"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.path = os.environ["PATH"]
        self.dead = dead_pid()
        self.filler = 0

        self.folders = []
        for n in range(FOLDERS):
            folder = os.path.join(self.root, "work", "f%02d" % n)
            os.makedirs(folder)
            self.folders.append(folder)

        self.codex_homes = [self.trusted_codex_home(name)
                            for name in ("codex-a", "codex-b", "codex-c")]
        self.claude_home = os.path.join(self.root, "claude-home")
        os.makedirs(os.path.join(self.claude_home, "sessions"))
        for home in self.codex_homes:
            self.assertTrue(registry._hooks_will_register(home), home)
        listed = [h["path"] for h in config.homes() if h.get("runtime") == "codex"]
        self.assertEqual(sorted(listed), sorted(self.codex_homes))

        # The calling session, and the two it can reach, all in one folder that
        # is not a git repository (two sessions in one plain folder share a scope).
        here = self.folders[0]
        self.mine = registry.upsert("codex", self.codex_homes[0], MINE, os.getpid(), here,
                                    name="mine")
        self.inbox = Inbox(os.path.join(self.root, "%d.sock" % os.getpid()))
        self.addCleanup(self.inbox.close)
        self.claude_target = registry.upsert("claude", self.claude_home, CLAUDE_SID, os.getpid(),
                                             here, name="claude-target", socket=self.inbox.path)
        # Claude's own record of the session is where its name and socket come from.
        paths.write_json(os.path.join(self.claude_home, "sessions", "%d.json" % os.getpid()),
                         {"pid": os.getpid(), "sessionId": CLAUDE_SID, "name": "claude-target",
                          "nameSource": "user", "messagingSocketPath": self.inbox.path,
                          "cwd": here})
        self.codex_target = registry.upsert("codex", self.codex_homes[1], CODEX_SID, os.getpid(),
                                            here, name="codex-target")

    def trusted_codex_home(self, name: str) -> str:
        """A Codex home xsm is installed in and whose hooks Codex trusts."""
        from xsm import config, install, paths
        home = os.path.join(self.root, name)
        os.makedirs(home)
        paths.write_json(os.path.join(home, "hooks.json"), {"hooks": {}}, mode=0o644)
        install.apply(home, "codex")
        with open(os.path.join(home, "config.toml"), "w") as fh:
            fh.write(test_xsm._trusted_config(home))
        config.add_home(home, "codex")
        return os.path.realpath(home)

    def fill_to(self, total: int) -> None:
        """Pointers of sessions that ended long ago, in all the folders, until the
        registry holds `total` of them. Written directly: registering each would
        be hundreds of real `ps` calls."""
        from xsm import config, identity, paths, registry
        have = len(glob.glob(paths.path(paths.SESSIONS, "*.json")))
        for _ in range(total - have):
            n, self.filler = self.filler, self.filler + 1
            runtime = "claude" if n % 2 else "codex"
            home = self.claude_home if runtime == "claude" else self.codex_homes[n % 3]
            sid = "elsewhere-%d" % n
            row = {"runtime": runtime, "home": home, "alias": config.alias_of(home),
                   "session_id": sid, "pid": self.dead, "lstart": None,
                   "cwd": self.folders[n % FOLDERS], "name": sid, "updated": time.time() - n,
                   "ref": identity.ref_of(runtime, home, sid)}
            if runtime == "claude":
                row["socket"] = os.path.join(self.root, "gone", "%d.sock" % self.dead)
            else:
                row["app_server"] = False
            paths.write_json(registry._record_path(runtime, sid), row)

    def stand_in_codex(self) -> tuple:
        """A `codex` that writes down its arguments and answers like `codex queue`
        (0.158): (the script, the file it appends one JSON list per call to)."""
        calls = os.path.join(self.root, "queue-calls.jsonl")
        script = os.path.join(self.root, "codex-stand-in")
        with open(script, "w") as fh:
            fh.write("#!%s\n"
                     "import json, sys\n"
                     "with open(%r, 'a') as out:\n"
                     "    out.write(json.dumps(sys.argv[1:]) + '\\n')\n"
                     "print('Queued message q-1 for thread %%s.' %% "
                     "sys.argv[sys.argv.index('--thread') + 1])\n" % (sys.executable, calls))
        os.chmod(script, 0o755)
        return script, calls

    def xsm(self, *args, thread=MINE, **env) -> tuple:
        """`bin/xsm args` as a subprocess on this machine, as the session `thread`
        (none for a shell that carries no thread id):
        (exit code, stdout, stderr, seconds). Past HARD_TIMEOUT it is killed with
        everything it started and the code is None."""
        environ = {key: os.environ[key] for key in ("LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "USER")
                   if key in os.environ}
        environ.update(PATH=self.path, HOME=self.user_home, XSM_HOME=self.tmp)
        if thread:
            environ["CODEX_THREAD_ID"] = thread
        environ.update(env)
        start = time.monotonic()
        proc = subprocess.Popen([LAUNCHER, *args], cwd=self.folders[0], env=environ, text=True,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, start_new_session=True)
        try:
            out, err = proc.communicate(timeout=HARD_TIMEOUT)
            code = proc.returncode
        except subprocess.TimeoutExpired:
            self.kill_group(proc)
            out, err = proc.communicate()
            code = None
        finally:
            self.kill_group(proc)       # a probe it left behind goes with it
        return code, out, err, time.monotonic() - start

    @staticmethod
    def kill_group(proc) -> None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    def done(self, ran: tuple, codes=(0,)) -> tuple:
        """The command finished in time, with one of `codes` and no traceback."""
        code, out, err, seconds = ran
        self.assertLess(seconds, BUDGET, "took %.1f s\nstdout: %s\nstderr: %s"
                        % (seconds, out[-400:], err[-400:]))
        self.assertIn(code, codes, "stdout: %s\nstderr: %s" % (out[-400:], err[-400:]))
        self.assertNotIn("Traceback", err)
        return ran


class Blocked(Machine):
    """The machine of the bug report: four Codex windows are open and `lsof`,
    the only way to learn a process's folder, never answers.

    The windows are `sleep` processes started as `codex` (`exec -a`), which is
    how the process scan sees them; a copy of /bin/sleep named codex is killed
    on sight by this macOS. The fake `lsof` goes first on the PATH of the
    commands under test, and `ps` and `git` stay the real ones.
    """

    def setUp(self):
        super().setUp()
        bindir = os.path.join(self.root, "bin")
        os.makedirs(bindir)
        lsof = os.path.join(bindir, "lsof")
        with open(lsof, "w") as fh:
            fh.write("#!/bin/sh\nexec sleep 30\n")
        os.chmod(lsof, 0o755)
        self.path = bindir + os.pathsep + self.path
        self.assertEqual(shutil.which("lsof", path=self.path), lsof)

        windows = []
        for n in range(WINDOWS):
            proc = subprocess.Popen(["bash", "-c", "exec -a codex /bin/sleep 120"],
                                    cwd=self.folders[n], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.addCleanup(self.close_window, proc)
            windows.append(proc)
        self.wait_for_windows([w.pid for w in windows])
        self.fill_to(POINTERS)

    @staticmethod
    def close_window(proc):
        proc.kill()
        proc.wait()

    def wait_for_windows(self, pids: list) -> None:
        """The scan reads `ps`, so the windows count once `ps` shows them as codex."""
        deadline = time.monotonic() + 10
        while True:
            table = subprocess.run(["ps", "-axo", "pid=,args="], capture_output=True,
                                   text=True).stdout.splitlines()
            shown = [pid for pid in pids if any(line.split() == [str(pid), "codex", "120"]
                                                for line in table)]
            if shown == pids:
                return
            self.assertLess(time.monotonic(), deadline, "windows not in ps: %s"
                            % sorted(set(pids) - set(shown)))
            time.sleep(0.1)


class BlockedDisplayTest(Blocked):
    """LAT-1: looking at sessions does not wait for the processes' folders."""

    def test_list(self):
        """LAT-1: `xsm list` finishes while lsof hangs."""
        self.done(self.xsm("list"))

    def test_list_all(self):
        """LAT-1: `xsm list -a` finishes while lsof hangs."""
        self.done(self.xsm("list", "-a"))

    def test_doctor(self):
        """LAT-1: `xsm doctor` finishes while lsof hangs."""
        self.done(self.xsm("doctor"))

    def test_list_says_once_which_probe_did_not_answer(self):
        """OBS-1: `xsm list` exits 0 and, on stderr, says in one line that lsof did not
        answer and the list may be incomplete; `--json` keeps its stdout clean."""
        for argv in (["list"], ["list", "--json"]):
            code, out, err, _ = self.done(self.xsm(*argv))
            notice = [line for line in err.splitlines() if "did not answer" in line]
            self.assertEqual(len(notice), 1, err)
            self.assertIn("lsof", notice[0])
            self.assertIn("incomplete", notice[0])
            self.assertIn("xsm doctor", notice[0])
            if "--json" in argv:
                self.assertIsInstance(json.loads(out), list)

    def test_list_counts_the_lsof_timeout_on_its_span(self):
        """OBS-1: the command's span carries xsm.probe.lsof.timeout."""
        self.done(self.xsm("list"))
        with open(os.path.join(self.tmp, "otel-spans.jsonl")) as fh:
            spans = [json.loads(line) for line in fh if line.strip()]
        (span,) = [row for row in spans if row["name"] == "xsm.cli.list"]
        self.assertGreaterEqual(span["attributes"].get("xsm.probe.lsof.timeout", 0), 1, span)

    def test_doctor_names_the_probe_that_did_not_answer(self):
        """OBS-1: `xsm doctor` has one `probes` line, and it names lsof."""
        out = self.done(self.xsm("doctor"))[1]
        lines = [line for line in out.splitlines() if line.startswith("probes ")]
        self.assertEqual(len(lines), 1, out)
        self.assertIn("lsof", lines[0])

    def test_who_of_a_thread_nothing_registered(self):
        """LAT-1: `xsm who` from a Codex thread with no pointer cannot be adopted
        here, so "not registered" (2) is a right answer, but not a slow one."""
        self.done(self.xsm("who", thread="no-pointer-thread"), codes=(0, 2))


class BlockedSendTest(Blocked):
    """LAT-2: a message to a live session, addressed exactly, goes out at once."""

    def assert_ledgered(self, result: dict, target: dict) -> None:
        from xsm import ledger
        entry = ledger.status(result["id"])
        self.assertEqual(entry.get("status"), "queued", entry)
        self.assertEqual((entry.get("from") or {}).get("ref"), self.mine["ref"])
        self.assertEqual((entry.get("to") or {}).get("ref"), target["ref"])

    def test_send_to_a_live_claude_session(self):
        """LAT-2: `xsm send ref:<claude> --text hello` writes the frame to the
        session's socket and the ledger while lsof hangs."""
        out = self.done(
            self.xsm("send", "ref:" + self.claude_target["ref"], "--text", "hello", "--json"),
            codes=(3,))[1]
        result = json.loads(out)
        self.assertEqual(result["status"], "sent-unconfirmed", result)
        frames = self.inbox.wait(1)
        self.assertEqual(len(frames), 1, frames)
        self.assertIn("hello", frames[0]["message"]["content"])
        self.assertEqual(frames[0]["msg_id"], result["id"])
        self.assert_ledgered(result, self.claude_target)

    def test_send_to_a_live_codex_session(self):
        """LAT-2: `xsm send ref:<codex> --text hello` hands the message to
        `codex queue` while lsof hangs."""
        script, calls = self.stand_in_codex()
        out = self.done(
            self.xsm("send", "ref:" + self.codex_target["ref"], "--text", "hello", "--json",
                     XSM_CODEX=script),
            codes=(3,))[1]
        result = json.loads(out)
        self.assertEqual(result["status"], "sent-unconfirmed", result)
        with open(calls) as fh:
            queued = [json.loads(line) for line in fh]
        self.assertEqual(len(queued), 1, queued)
        argv = queued[0]
        self.assertEqual(argv[0], "queue")
        self.assertEqual(argv[argv.index("--thread") + 1], CODEX_SID)
        self.assertIn("hello", argv[argv.index("--message") + 1])
        self.assert_ledgered(result, self.codex_target)

    def test_mcp_send_to_a_live_claude_session(self):
        """LAT-2: the `xsm_send` MCP tool, which a sandboxed Codex has to use, is
        as quick. It runs in this process, so the scan must be the real one (the
        TempState stub is undone) and the fake lsof first on this PATH."""
        from xsm import mcp, registry
        importlib.reload(registry)
        with mock.patch.dict(os.environ, {"PATH": self.path, "CODEX_THREAD_ID": MINE}), \
                mock.patch.object(mcp.identity, "ancestor_pid", return_value=os.getpid()):
            server = mcp.Server(io.StringIO(), io.StringIO())
            server.call_thread = MINE
            start = time.monotonic()
            text = server.call("xsm_send", {"target": "ref:" + self.claude_target["ref"],
                                            "text": "hello", "wait": 0})
            seconds = time.monotonic() - start
        self.assertLess(seconds, BUDGET, "took %.1f s: %s" % (seconds, text))
        self.assertIn("sent-unconfirmed", text)
        frames = self.inbox.wait(1)
        self.assertEqual(len(frames), 1, frames)
        self.assertIn("hello", frames[0]["message"]["content"])


class ScaleTest(Machine):
    """LAT-3: nothing is blocked, and 340 more pointers of sessions elsewhere add
    next to nothing. Each command runs once to warm up (imports, file cache),
    then twice at each size; the faster run of the two is compared, so a busy
    moment on this machine does not decide it."""

    def timed(self, argv: list, codes=(0,)) -> float:
        seconds = []
        for _ in range(2):
            code, out, err, took = self.xsm(*argv)
            self.assertIn(code, codes, "stdout: %s\nstderr: %s" % (out[-400:], err[-400:]))
            self.assertNotIn("Traceback", err)
            seconds.append(took)
        return min(seconds)

    def assert_scales(self, argv: list, codes=(0,), deliveries: int = 0) -> None:
        self.fill_to(10)
        self.xsm(*argv)
        small = self.timed(argv, codes)
        self.fill_to(POINTERS)
        large = self.timed(argv, codes)
        self.assertLessEqual(large, small + EXTRA, "10 pointers: %.2f s, %d pointers: %.2f s"
                             % (small, POINTERS, large))
        if deliveries:
            # A refusal is quick too, so what was timed must have been a delivery.
            self.assertEqual(len(self.inbox.wait(deliveries * 5)), deliveries * 5)

    def test_who(self):
        """LAT-3: `xsm who` costs the same with 350 pointers as with 10."""
        self.assert_scales(["who"])

    def test_list(self):
        """LAT-3: `xsm list` costs the same with 350 pointers as with 10."""
        self.assert_scales(["list"])

    def test_list_prints_no_notice(self):
        """OBS-1: when every probe answers, `xsm list` says nothing on stderr."""
        self.fill_to(POINTERS)
        code, out, err, _ = self.xsm("list")
        self.assertEqual(code, 0, err)
        self.assertNotIn("did not answer", err)

    def test_send_by_ref(self):
        """LAT-3: `xsm send ref:<claude> --text x` costs the same with 350 pointers."""
        self.assert_scales(["send", "ref:" + self.claude_target["ref"], "--text", "x"],
                           codes=(3,), deliveries=1)

    def test_send_by_name(self):
        """LAT-3: `xsm send <name> --text x` has to look at every pointer to find
        the name, and still costs the same with 350 of them."""
        self.assert_scales(["send", "claude-target", "--text", "x"], codes=(3,), deliveries=1)


if __name__ == "__main__":
    unittest.main()
