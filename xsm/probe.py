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

Outside `quick` nothing is remembered (the MCP server runs for days, and a folder
that stalled once may answer later), and the deadlines are the ordinary ones.
"""
from __future__ import annotations

import contextlib
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


def _gave_up(folder) -> None:
    if _quick is not None and folder is not None:
        _stalled.add(folder)


def bounded(fn, *args, folder: str | None = None, timeout: float | None = None, default=None):
    """`fn(*args)`, or `default` when it raises or takes longer than the deadline. A
    read in a stalled folder cannot be interrupted, so it runs in a daemon thread that
    is left behind. `folder` names what is being asked about: one that did not answer
    inside `quick` is not asked again."""
    if folder is not None and folder in _stalled:
        return default
    wait = limit(READ_TIMEOUT if timeout is None else timeout)
    if wait <= 0:
        return default
    box: list = []

    def work():
        try:
            box.append(fn(*args))
        except Exception:               # noqa: BLE001 - what cannot be read is unknown
            box.append(default)

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    thread.join(wait)
    if thread.is_alive() or not box:
        _gave_up(folder)
        return default
    return box[0]


def command(argv: list, timeout: float = GIT_TIMEOUT, folder: str | None = None) -> str | None:
    """Read-only subprocess output, bounded by the shared lookup budget.

    Never wait for a killed child: lsof can be stuck in a filesystem read too.
    """
    if folder in _stalled:
        return None
    wait = limit(timeout)
    if wait <= 0:
        return None
    try:
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True)
    except OSError:
        return None
    try:
        out, _ = proc.communicate(timeout=wait)
    except subprocess.TimeoutExpired:
        proc.kill()                     # and not waited for: it may never leave the folder
        proc.stdout.close()
        _gave_up(folder)
        return None
    except (OSError, subprocess.SubprocessError):
        return None
    return out if proc.returncode == 0 else None


def git(folder: str, *args: str, timeout: float | None = None) -> str | None:
    """stdout of git, or None when the folder cannot answer in time."""
    return command(["git", "-C", folder] + list(args),
                   GIT_TIMEOUT if timeout is None else timeout, folder=folder)
