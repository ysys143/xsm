"""Looking at a project folder without being held by it.

A session's folder is not xsm's: it can sit under ~/Documents, which macOS guards,
or on a mount that does not answer. An open() or an opendir() there blocks in the
kernel and cannot be interrupted, and `subprocess.run(timeout=)` waits for the child
it killed, which never leaves that read. `xsm list` asked about each session's folder
(its settings files, `git rev-parse`; 42 git calls for 8 folders, measured
2026-10-02) and one stalled folder froze it for good on the Mac mini. A listing that
a person is waiting on must not wait for a folder.

- `bounded` reads with a deadline, in a thread that is left behind when time runs out;
  a timeout is "unknown", never an error.
- `git` is `git -C <folder>` with the same deadline, and a child that does not answer
  is killed and let go, not waited for.
- `quick` gives interactive lookups a shared three-second probe budget. Every
  probe gets at most a second, answers are reused (`remember`), and a folder
  that did not answer is not asked again.
- A probe that timed out, or was not started because the budget was spent or its
  folder had stalled, is counted by kind (`missed`, `unanswered`): a list that
  skipped a probe says so instead of passing for complete (#17).

Outside `quick` nothing is remembered (the MCP server runs for days, and a folder
that stalled once may answer later), and the deadlines are the ordinary ones.
"""
from __future__ import annotations

import contextlib
import contextvars
import os
import subprocess
import threading
import time

GIT_TIMEOUT = 5.0           # what a git call has always been allowed
READ_TIMEOUT = 2.0          # a file read is microseconds when the folder answers
QUICK_TIMEOUT = 1.0
QUICK_BUDGET = 3.0          # shared by every probe in one interactive lookup

_quick = None               # the deadline in force inside `quick`, else None
_deadline = None
_memo: dict = {}
_stalled: set = set()
_unanswered: dict = {}      # kind of probe -> how many did not answer in this command
_observers = contextvars.ContextVar("xsm_probe_observers", default=())


@contextlib.contextmanager
def observe_unavailable():
    """Observe unknown reads in this call without changing probe defaults.

    Admission uses this to distinguish an explicit policy refusal from an
    evaluation that could not finish. Context-local observers do not borrow
    another service request's counters or change ordinary discovery behavior.
    """
    observed = {"unavailable": False}
    token = _observers.set(_observers.get() + (observed,))
    try:
        yield observed
    finally:
        _observers.reset(token)


def _note_unavailable():
    for observed in _observers.get():
        observed["unavailable"] = True


@contextlib.contextmanager
def quick(timeout: float | None = None, budget: float | None = None):
    """Per-probe timeout and one total budget, with answers reused until exit.

    Nested lookups share the outer budget instead of starting another deadline.
    """
    global _quick, _deadline
    if _quick is not None:
        yield
        return
    _quick = QUICK_TIMEOUT if timeout is None else timeout
    _deadline = time.monotonic() + (QUICK_BUDGET if budget is None else budget)
    _memo.clear()
    _stalled.clear()
    _unanswered.clear()                 # and kept after exit: the caller reads it then
    try:
        yield
    finally:
        _quick = None
        _deadline = None
        _memo.clear()
        _stalled.clear()


def limit(timeout: float) -> float:
    return timeout if _quick is None else min(timeout, _quick,
                                             max(0.0, _deadline - time.monotonic()))


def remember(key, compute):
    """`compute()`, once per `key` inside `quick`, every time outside it."""
    if _quick is None:
        return compute()
    if key not in _memo:
        _memo[key] = compute()
    return _memo[key]


def missed(kind: str, how: str) -> None:
    """Count one probe of this `kind` that did not answer; `how` is "timeout" or
    "skipped", and goes on the command's span as xsm.probe.<kind>.<how>."""
    _note_unavailable()
    _unanswered[kind] = _unanswered.get(kind, 0) + 1
    try:
        from . import telemetry
        telemetry.bump("xsm.probe.%s.%s" % (kind, how))
    except ImportError:
        pass


def unanswered() -> dict:
    """{kind: count} of the probes of the current command that did not answer. Reset
    when the outermost `quick` is entered, so it can be read after that block exits."""
    return dict(_unanswered)


def _gave_up(folder) -> None:
    if _quick is not None and folder is not None:
        _stalled.add(folder)


def bounded(fn, *args, folder: str | None = None, timeout: float | None = None, default=None):
    """`fn(*args)`, or `default` when it raises or takes longer than the deadline. A
    read in a stalled folder cannot be interrupted, so it runs in a daemon thread that
    is left behind. `folder` names what is being asked about: one that did not answer
    inside `quick` is not asked again."""
    if folder is not None and folder in _stalled:
        missed("read", "skipped")
        return default
    wait = limit(READ_TIMEOUT if timeout is None else timeout)
    if wait <= 0:
        missed("read", "skipped")
        return default
    box: list = []

    def work():
        try:
            box.append(fn(*args))
        except FileNotFoundError:
            # A missing optional record is a known absence, not evidence that
            # the filesystem could not answer. Callers retain their default.
            box.append(default)
        except Exception:               # noqa: BLE001 - what cannot be read is unknown
            _note_unavailable()
            box.append(default)

    if _observers.get():
        context = contextvars.copy_context()
        thread = threading.Thread(target=context.run, args=(work,), daemon=True)
    else:
        thread = threading.Thread(target=work, daemon=True)
    thread.start()
    thread.join(wait)
    if thread.is_alive() or not box:
        missed("read", "timeout")
        _gave_up(folder)
        return default
    return box[0]


def command(argv: list, timeout: float = GIT_TIMEOUT, folder: str | None = None,
            any_exit: bool = False) -> str | None:
    """Read-only subprocess output, bounded by the shared lookup budget.

    Never wait for a killed child: lsof can be stuck in a filesystem read too.
    `any_exit` returns stdout whatever the exit code, for a tool that prints what it
    found and still exits 1 (lsof, when one of the pids it was given is gone); a
    timeout or a command that does not start is None either way.
    """
    kind = os.path.basename(argv[0])
    if folder in _stalled:
        missed(kind, "skipped")
        return None
    wait = limit(timeout)
    if wait <= 0:
        missed(kind, "skipped")
        return None
    try:
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True)
    except OSError:
        _note_unavailable()
        return None
    try:
        out, _ = proc.communicate(timeout=wait)
    except subprocess.TimeoutExpired:
        proc.kill()                     # and not waited for: it may never leave the folder
        proc.stdout.close()
        missed(kind, "timeout")
        _gave_up(folder)
        return None
    except (OSError, subprocess.SubprocessError):
        _note_unavailable()
        return None
    return out if any_exit or proc.returncode == 0 else None


def git(folder: str, *args: str, timeout: float | None = None) -> str | None:
    """stdout of git, or None when the folder cannot answer in time."""
    return command(["git", "-C", folder] + list(args),
                   GIT_TIMEOUT if timeout is None else timeout, folder=folder)
