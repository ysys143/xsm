"""One caller, one immutable handle (P01/IC01).

Three entry points resolve the calling session in three different ways: the CLI
walks its own process env and ancestors, the MCP server answers per `tools/call`
and may have to fall back to a neighbour, and a hook is handed the runtime's own
fields. P01 requires that all three hand the *same meaning* onward, that the
result is never mutated once a call starts, and that the resolution actually
used is recorded rather than assumed.

So a call carries a `CallContext`: stable handles (runtime, normalised home,
native conversation id), the execution generation (pid + start time), cwd, the
authenticated machine origin, and -- the part P01 adds -- `basis` and
`certainty`, which say *how* the caller was identified and whether that
identification is solid enough to widen scope or read a file on.

Two rules keep the old accessibility while closing the leak:

- Plain messaging keeps working on a weak identification, but says so
  (`certainty` travels into the ledger and the decision log).
- Widening a permission, reading a file, or binding a message to a target
  requires a solid one (`require_sure`). A neighbour guessed from "the newest
  live record" must never grant, and must never be handed another session's
  files as if it were them.
"""
from __future__ import annotations

import hashlib
import os


# How the caller was identified. Ordered roughly strongest first.
BASIS_HOOK = "hook_input"          # the runtime's own hook fields named it
BASIS_THREAD = "thread_id"         # MCP: params._meta.threadId named the Codex thread
BASIS_SESSION = "session_id"       # the session's own id in env (CLI) or a pointer
BASIS_SOCKET = "socket"            # pid carried by the inbox socket
BASIS_ANCESTOR = "ancestor"        # the nearest agent process above this one
BASIS_ADOPTED = "adopted"          # registered on the spot from its own process/thread
BASIS_NEIGHBOR = "neighbor"        # MCP fallback: the newest live record of the pid
BASIS_CWD = "cwd"                  # one live session shares this folder
BASIS_NONE = "none"                # could not be identified

# Bases that rest on the session's own statement or its own process.
SURE_BASES = (BASIS_HOOK, BASIS_THREAD, BASIS_SESSION, BASIS_SOCKET, BASIS_ANCESTOR,
              BASIS_ADOPTED)
CERTAIN = "certain"
PROVISIONAL = "provisional"


def normalize_home(home: str | None) -> str | None:
    """The one spelling of a home. Two homes are the same when their realpaths
    are: `~/.codex-3` and a symlink to it must not read as two machines, and a
    trailing slash must not either (ADR-0001)."""
    if not home:
        return None
    try:
        return os.path.realpath(os.path.expanduser(home))
    except OSError:
        return os.path.abspath(os.path.expanduser(home))


def generation(pid, lstart: str | None) -> str | None:
    """A pid plus its process start time, so a reused pid is a new generation.
    `claude --resume` keeps the id but gets a new generation; that is the whole
    point of keeping it (A17-03)."""
    if not pid:
        return None
    raw = "%s@%s" % (int(pid), lstart or "")
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:12]


class CallContext:
    """Who is calling, once per call, and how we know.

    Frozen after construction: a server field, an inherited environment
    variable, or the nearest neighbour of a *previous* call must not edit the
    identity of a call already in flight (spec 4.1)."""

    __slots__ = ("runtime", "home", "conversation", "thread", "generation", "cwd",
                 "origin", "basis", "certainty", "evidence", "record", "_frozen")

    def __init__(self, runtime: str | None = None, home: str | None = None,
                 conversation: str | None = None, thread: str | None = None,
                 generation_value: str | None = None, cwd: str | None = None,
                 origin: str | None = None, basis: str = BASIS_NONE,
                 certainty: str | None = None, evidence=None, record=None):
        object.__setattr__(self, "runtime", runtime)
        object.__setattr__(self, "home", normalize_home(home))
        object.__setattr__(self, "conversation", conversation)
        object.__setattr__(self, "thread", thread)
        object.__setattr__(self, "generation", generation_value)
        object.__setattr__(self, "cwd", cwd)
        object.__setattr__(self, "origin", origin)
        object.__setattr__(self, "basis", basis)
        object.__setattr__(self, "certainty", certainty or certainty_of(basis))
        object.__setattr__(self, "evidence", tuple(evidence or ()))
        object.__setattr__(self, "record", record)
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name, value):
        if getattr(self, "_frozen", False):
            raise AttributeError("CallContext is immutable once a call starts")
        object.__setattr__(self, name, value)

    # -- what a caller asks of it -------------------------------------------------
    @property
    def sure(self) -> bool:
        return self.certainty == CERTAIN

    def to_dict(self) -> dict:
        return {"runtime": self.runtime, "home": self.home, "conversation": self.conversation,
                "thread": self.thread, "generation": self.generation, "cwd": self.cwd,
                "origin": self.origin, "basis": self.basis, "certainty": self.certainty,
                "evidence": list(self.evidence)}

    def note(self) -> str:
        """One short phrase for a record or a log line: how sure, and on what."""
        return "%s (%s)" % (self.certainty, self.basis)

    def __repr__(self) -> str:                      # debugging aid only
        return "CallContext(runtime=%r, home=%r, conversation=%r, basis=%r, certainty=%r)" % (
            self.runtime, self.home, self.conversation, self.basis, self.certainty)


def certainty_of(basis: str) -> str:
    """A basis decides its own certainty. An unrecognised basis is treated as
    provisional: the only way to earn `certain` is to name a known solid one."""
    return CERTAIN if basis in SURE_BASES else PROVISIONAL


def of_record(record: dict | None, basis: str = BASIS_NONE, origin: str | None = None,
              evidence=None) -> CallContext:
    """A context from a registry record and the basis that found it.

    The home and generation come from the record; when there is no record the
    context still exists, marked `none`, so a caller can be told why rather than
    silently signed as someone else."""
    rec = record or {}
    return CallContext(
        runtime=rec.get("runtime"), home=rec.get("home"),
        conversation=rec.get("session_id"), thread=rec.get("session_id")
        if rec.get("runtime") == "codex" else None,
        generation_value=generation(rec.get("pid"), rec.get("lstart")),
        cwd=rec.get("cwd") or None, origin=origin, basis=basis if record else BASIS_NONE,
        evidence=evidence, record=record)


def for_hook(runtime: str, session_id: str | None, home: str | None, cwd: str | None,
             basis: str = BASIS_HOOK) -> CallContext:
    """The hook path: the runtime told us its session id, home and folder."""
    return CallContext(runtime=runtime, home=home, conversation=session_id,
                       thread=session_id if runtime == "codex" else None, cwd=cwd,
                       basis=basis if session_id else BASIS_NONE)


def require_sure(ctx: CallContext | None, what: str) -> str | None:
    """Why this action may not run on this context, or None when it may.

    Used for the two things that must never ride on a guessed neighbour:
    widening a permission, and reading a file on behalf of the caller. Plain
    messaging deliberately does not go through here (spec P01 item 2).
    """
    if ctx is None:
        return ("this call did not carry a caller identity, so xsm will not %s: it cannot tell "
                "which session it would be doing it for" % what)
    if ctx.sure:
        return None
    return ("xsm cannot %s for this call: the caller was identified only as %s, and that is a "
            "guess at which session is asking. Run it from the session's own shell (or name the "
            "session) so the identity is exact" % (what, ctx.basis))


