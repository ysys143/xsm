"""The xsm MCP server: xsm's tools for a session, over stdio.

Started by the session (Claude Code or Codex) and ending with it, so it is not
a resident process (ADR-0003). It exists for two reasons (ADR-0005, ADR-0026):

- A decision recorded from a session must be the person's. `xsm_decide` asks
  them through MCP elicitation, and their answer comes back from the client to
  this server without passing through the model (measured on both runtimes,
  2026-09-22). The answer and the question are stored with the decision,
  beside a team's board. Verified native-user readback is a separate supported source;
  it must match the exact conversation, question and unconsumed native answer.
- A sandboxed Codex cannot write `~/.xsm` from its shell, but the MCP servers it
  starts run outside the sandbox (measured), so messaging and reading go through
  here too.

The session is identified by this process's ancestry: the nearest `claude` or
`codex` ancestor is the session, and its registry record is the caller. Codex
threads of one CODEX_HOME share one ancestor (the app-server daemon), so a
Codex call names its thread in `params._meta.threadId` and that decides; with
several live threads and no such id, the call is refused (Server.session).
"""
from __future__ import annotations

import json
import copy
import base64
import math
import os
import queue
import threading
import shlex
import signal
import sys
import time

from . import consent, context, identity, paths, probe, registry, workers
from .instructions import HANDSHAKE_TEXT, MESSAGING_GUIDE

PROTOCOL = "2025-06-18"


def plugin_home(path: str | None = None) -> str | None:
    """The CODEX_HOME this server was installed in, from its own path
    (<home>/plugins/cache/...). Codex hands an MCP server a filtered environment
    with no CODEX_HOME, so a plugin server in any home but ~/.codex took ~/.codex
    for its own and refused its own thread (measured with Codex 0.165, 2026-10-31)."""
    here = os.path.realpath(path or __file__)
    home, marker, _ = here.partition(os.sep + os.path.join("plugins", "cache") + os.sep)
    return home if marker else None


from .operations import OperationService
from .operation_schema import (ToolError, TOOLS, READ_ONLY, MESSAGING, WIDENING, FILE_READING,
    CODEX_CLIENT, ACTIONS, DECLINED, person_answer, unanswered, who_answered)


class Server(OperationService):
    def __init__(self, inp=sys.stdin, out=sys.stdout):
        self.inp, self.out = inp, out
        self.initialize_service()
        self._input = queue.Queue()
        self._reader = None
        self._closed = False

    # -- transport ----------------------------------------------------------------
    def send(self, obj: dict) -> None:
        obj.setdefault("jsonrpc", "2.0")
        self.out.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.out.flush()

    def _start_reader(self):
        if self._reader is not None:
            return

        def read_lines():
            # Exactly one reader owns stdin. It only parses/queues input;
            # service calls and all mutable call context stay on this thread.
            try:
                while True:
                    line = self.inp.readline()
                    if not line:
                        break
                    self._input.put(json.loads(line))
            except Exception as exc:
                self._input.put(exc)
            finally:
                self._input.put(None)

        self._reader = threading.Thread(target=read_lines, daemon=True,
                                        name="xsm-mcp-input")
        self._reader.start()

    def read(self, timeout=None) -> dict | None:
        self._start_reader()
        if self._closed:
            return None
        msg = self._input.get(timeout=timeout)
        if msg is None:
            self._closed = True
        if isinstance(msg, Exception):
            raise msg
        return msg

    def pump(self):
        """Dispatch pending input during a service wait, without another reader."""
        try:
            msg = self.read(timeout=0)
        except queue.Empty:
            return True
        if msg is not None:
            self.dispatch(msg)
        return not self._closed

    def ask_client(self, method: str, params: dict) -> dict:
        self.next_id += 1
        rid = "xsm-%d" % self.next_id
        owner = self.active_request
        self.pending_client[rid] = owner
        decision = self.decision_calls.get(owner) if method == "elicitation/create" else None
        if decision:
            from . import decisions
            record = decisions.begin(decision["key"], decision["me"], decision["scope"],
                                     decision["generation"], params.get("message", ""),
                                     waiter=owner,
                                     choices=(((params.get("requestedSchema") or {}).get("properties") or {}).get("answer") or {}).get("enum"))
            record = decisions.recover_display(record["id"])
            if not decision.get('native_request') and decisions.native_recoverable(record):
                from . import user_answers
                original = record.get('native_question', record['question'])
                evidence = user_answers.read_answer(decision['me'], since=decisions.native_since(record),
                    latest_only=True, question=original, tail_bytes=user_answers.MAX_TAIL_BYTES)
                if evidence and evidence.get('question') == original:
                    decision['native_request'] = evidence['questionItemId']
                    decision['native_question'] = original
            if decision.get("native_request"):
                if (not decisions.native_recoverable(record) or
                        (record.get("answer") and self.answer(record["answer"]["reply"], record.get("choices"))[1] == DECLINED) or
                        time.time() > record["expires_at"] or not self._decision_current(decision)):
                    self.pending_client.pop(rid, None)
                    return {"id": rid, "error": {"code": -32000, "message": "decision is closed or expired; native answer not imported"}}
                from . import user_answers
                evidence = user_answers.read_answer(decision["me"], request=decision["native_request"],
                            since=max(decisions.native_since(record), time.time() - consent.TTL), latest_only=True,
                            question=decision.get("native_question"),
                            tail_bytes=user_answers.MAX_TAIL_BYTES)
                original = decision.get("native_question")
                if not evidence or evidence["question"] != original or original != record.get("native_question", record["question"]):
                    self.pending_client.pop(rid, None)
                    return {"id": rid, "error": {"code": -32000,
                            "message": "native answer or original displayed question could not be verified"}}
                decisions.claim_native(decision["me"], evidence["questionItemId"], record["id"])
                if record["display"]["status"] == "not-requested":
                    decisions.display(record["id"], owner, evidence["question"], "native-user")
                reply = {"id": rid, "result": {"action": "accept",
                         "content": {"answer": evidence["answer"]},
                         "_meta": {"approvals_reviewer": "user"}}}
                record = decisions.response(record["id"], reply, "native-user",
                         source_id=evidence["questionItemId"], displayed=evidence["question"])
            if record.get("answer"):
                self.pending_client.pop(rid, None)
                if record["status"] == "unknown" and self.answer(record["answer"]["reply"], record.get("choices"))[0] is None:
                    # Preserve the specific malformed/automatic-reviewer reason
                    # from the existing answer adapter, which cannot apply it.
                    return record["answer"]["reply"]
                if record["status"] in ("answered", "denied", "dismissed", "unshown-or-declined"):
                    if not self._decision_current(decision):
                        return {"id": rid, "error": {"code": -32000, "message": "decision caller or scope changed"}}
                    if record["status"] == "answered":
                        decisions.start_application(record["id"], decision["generation"], decision["scope"], reader=self.reader_identity)
                    return record["answer"]["reply"]
                return {"id": rid, "error": {"code": -32000, "message": "decision is not applicable: " + record["status"] +
                        "; inspect xsm_decision_status; a renewed user request uses a new decision_key"}}
            if "elicitation" not in (self.client_caps or {}):
                self.pending_client.pop(rid, None)
                return {"id": rid, "error": {"code": -32000, "message": "client cannot show a form (no elicitation support); pending question retained for verified native recovery"}}
            if not decisions.display(record["id"], owner, params.get("message", ""), "mcp-elicitation", reader=self.reader_identity):
                self.pending_client.pop(rid, None)
                return {"id": rid, "error": {"code": -32000,
                        "message": "joined pending human question " + record["id"] +
                        "; inspect xsm_decision_status; cancelled/expired questions require a renewed user request and new decision_key"}}
            from . import attention
            try:
                attention.notify(record["id"], "xsm: 확인 요청", params.get("message", ""),
                                 enabled=decision.get("notify", False))
            except OSError:
                # An optional OS notification cannot orphan the real question.
                pass
            self.decision_routes[rid] = record["id"]
        if method == "elicitation/create" and "elicitation" not in (self.client_caps or {}):
            self.pending_client.pop(rid, None)
            return {"id": rid, "error": {"code": -32000, "message": "client has no elicitation support"}}
        try:
            self.send({"id": rid, "method": method, "params": params})
            while True:
                if rid in self.client_replies:
                    reply = self.client_replies.pop(rid)
                    if decision:
                        record = decisions.read(decision["key"])
                        if record["status"] not in ("answered", "denied", "dismissed", "unshown-or-declined"):
                            if record["status"] == "unknown" and self.answer(reply, record.get("choices"))[0] is None:
                                return reply
                            return {"id": rid, "error": {"code": -32000, "message": "decision is " + record["status"]}}
                        if not self._decision_current(decision):
                            return {"id": rid, "error": {"code": -32000, "message": "decision caller or scope changed"}}
                        if record["status"] == "answered":
                            decisions.start_application(record["id"], decision["generation"], decision["scope"], reader=self.reader_identity)
                    return reply
                if owner in self.cancelled:
                    if decision:
                        decisions.cancel_waiter(decision["key"], owner)
                    return {"id": rid, "error": {"code": -32800,
                            "message": "request cancelled; no decision applied"}}
                msg = self.read()
                if msg is None:
                    raise EOFError("client went away")
                self.dispatch(msg)
        except (EOFError, OSError):
            if decision:
                decisions.abandon_display(decision["key"], self.instance_id)
            raise
        finally:
            self.pending_client.pop(rid, None)



    def answer(self, reply, allowed) -> tuple:
        return person_answer(reply, allowed, self.client_name)

    # -- the session ---------------------------------------------------------------
    def session(self) -> dict | None:
        """The caller's registry record. `self.ctx` is set alongside with how it
        was found, so a tool knows whether the identity is exact or a guess
        (P01 items 1 and 2)."""
        rec, basis, evidence = self._resolve()
        self.ctx = context.of_record(rec, basis, evidence=evidence)
        return rec

    def _resolve(self):
        """(record | None, basis, evidence) for the caller of this call.

        Each rule says how it found the session, never that it did: `neighbor`
        (the newest live record under the pid) is a guess and is marked as one
        even though it still answers, because a shared-daemon neighbour is
        exactly what must not widen a permission or read another session's file.

        A pointer is keyed on runtime and session id alone, so a thread id that
        exists in two CODEX_HOMEs (a copied home, another profile) names one
        record whose `home` may be the *other* one. Signing as it would send a
        message as a session in a home this server is not running in (A23-03),
        so a record from a different known home is not taken: the thread is
        registered for this server's own home instead.

        The home is this *server's own*: the variable of the runtime this server
        serves, or that runtime's default. Reading whichever home variable is
        set is what let a default-home server adopt another home's record, and
        what made a Codex started from a Claude shell (CLAUDE_CONFIG_DIR
        inherited, spec P01.1) refuse its own home's record.

        When the call names no thread id, one live record under this pid is this
        server's own session -- Claude is one session per process, and a Codex
        daemon with a single live thread has that thread calling. Several
        candidates is the shared-daemon case, and the newest of those is only a
        guess, which is what `neighbor` says (P01 item 2).
        """
        pid = identity.ancestor_pid({"claude", "codex"})
        if not pid:
            return None, context.BASIS_NONE, ("no session process above this server",)
        # Runs on every tool call: only the pointers that carry the caller's pid are
        # enriched. Every pointer was (ps, socket and sqlite each) and a registry of
        # hundreds cost seconds before the tool began (#17).
        mine = [registry._enrich(r) for r in registry.raw_records() if r.get("pid") == pid]
        rows = [r for r in mine if r.get("state") == "live" or r.get('retired')]
        codex = [r for r in rows if r.get("runtime") == "codex"]
        own_runtime = self.own_runtime(pid, rows)
        own_home = self.own_home(own_runtime)

        def in_this_home(rec: dict) -> bool:
            """Whether a record belongs to the home this server runs in. A record
            with no home, or a server with no home that can be told, cannot be
            told apart: it is left to the rules below."""
            rec_home = context.normalize_home(rec.get("home"))
            return not (own_home and rec_home and rec_home != own_home)

        # The live pointers under this pid that belong to this server's home. A
        # record from another known home is a different session (A23-03).
        here = [r for r in rows if in_this_home(r)]
        if self.call_thread and (codex or not rows):
            # Codex 0.158 names the calling thread in every tools/call
            # (`params._meta.threadId`; measured 2026-09-29 with two TUIs on one
            # daemon: one MCP server process per thread, all children of the
            # daemon, so the pid alone names all of them).
            for r in sorted(codex, key=lambda item: not in_this_home(item)):
                if r.get("session_id") == self.call_thread:
                    if in_this_home(r):
                        return r, context.BASIS_THREAD, (
                            "the call named thread %s" % self.call_thread,)
                    # Same id, another home: a different session. Do not sign as it.
                    other = context.normalize_home(r.get("home"))
                    evidence = ("thread %s lives in %s, not in %s"
                                % (self.call_thread, other, own_home),)
                    adopted = registry.adopt_codex_thread(
                        self.call_thread, pid, self.adoptable_homes(own_home, codex),
                        mcp_pid=os.getpid())
                    if adopted:
                        return adopted, context.BASIS_ADOPTED, evidence + (
                            "registered it for this home from its own state DB",)
                    return None, context.BASIS_NONE, evidence
            # No live record: a sub-agent's thread, or one whose hook has not
            # run. Connect it rather than refuse (user decision, 2026-09-30:
            # "prefer easy connection; accidental connection failures must not
            # happen"). Adoption needs the same consent as `xsm list`'s: xsm
            # installed in that home with trusted hooks; without it, fall
            # through to the most recent record below.
            adopted = registry.adopt_codex_thread(
                self.call_thread, pid, self.adoptable_homes(own_home, codex),
                mcp_pid=os.getpid())
            if adopted:
                return adopted, context.BASIS_ADOPTED, (
                    "registered thread %s from its own state DB" % self.call_thread,)
        # No thread id in the call, and one live record under this pid: that is
        # the session this server belongs to -- Claude is one session per
        # process, and a daemon with a single live thread has that thread
        # calling -- so it is exact, not a guess (G01 review, O-F1: reading it
        # as a neighbour refused every Claude session its own permission
        # tools). **Only when the call named no thread**: a call that named a
        # thread which matched nothing (a sub-agent's thread, a home whose hook
        # has not run) must not be signed as a *different* session just because
        # that session is the only one here -- that was G01 review R2-1, a
        # regression of the O-F1 fix.
        if not self.call_thread and len(here) == 1 and \
                (own_runtime is None or here[0].get("runtime") == own_runtime):
            return here[0], context.BASIS_ANCESTOR, (
                "the only live record under pid %s is this server's own session" % pid,)
        # Several records, or a named thread that matched none: the newest live
        # record is a guess, as before 0840ee3 (user decision, 2026-09-30: a
        # possibly wrong neighbour is better than a refusal).
        if here:
            newest = max(here, key=lambda r: r.get("updated", 0))
            why = ("thread %s has no record under pid %s; the newest live record is a guess"
                   % (self.call_thread, pid)) if self.call_thread else \
                ("no thread id in the call; the newest live record under pid %s" % pid)
            return newest, context.BASIS_NEIGHBOR, (why,)
        if rows:
            return None, context.BASIS_NONE, (
                "every live record under pid %s lives in another home, not in %s"
                % (pid, own_home),)
        # A Claude session whose hooks never ran (started before xsm, or before
        # its plugin was enabled) has no record at all: its own process is this
        # server's parent, and Claude's record of it names the session (audit,
        # 2026-10-01: such a session could not use any xsm tool). By pid, never by
        # an environment variable: a Codex started from a Claude shell inherits
        # that session's id.
        adopted = registry.adopt_claude_process(pid)
        return adopted, (context.BASIS_ADOPTED if adopted else context.BASIS_NONE), (
            "registered this process's own Claude session" if adopted
            else "no record carries this pid",)

    @staticmethod
    def own_runtime(pid, rows: list):
        """Which runtime this server serves: the session process above it.

        The environment cannot say -- a Codex started from a Claude shell carries
        CLAUDE_CONFIG_DIR and CLAUDE_CODE_SESSION_ID, a Claude started from Codex
        carries CODEX_HOME -- so the pointers under the pid decide when they agree
        (one process serves one runtime), and the process table is asked only when
        there are none to agree, which is the adoption path. That keeps the common
        call free of an extra `ps` (#17)."""
        seen = {r.get("runtime") for r in rows if r.get("runtime")}
        if len(seen) == 1:
            return seen.pop()
        runtime = identity.comm(pid)
        return runtime if runtime in ("claude", "codex") else None

    @staticmethod
    def own_home(runtime: str | None) -> str | None:
        """This server's home, from *its own* runtime's variable only, with that
        runtime's default when it is unset. Reading the other harness's variable
        would refuse this server's own records (P01 item 1)."""
        if runtime == "claude":
            return context.normalize_home(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude")
        if runtime == "codex":
            return context.normalize_home(os.environ.get("CODEX_HOME") or plugin_home() or "~/.codex")
        return None

    @staticmethod
    def adoptable_homes(own_home: str | None, codex_rows: list) -> list:
        """Candidate CODEX_HOMEs for a thread with no record. A daemon serves the
        threads of one home, so when this server's home is known that is the only
        one to look in: a thread found in another home's state DB belongs to
        another server (A23-03). Without it, the old list is kept."""
        if own_home:
            return [own_home]
        return registry.codex_homes(codex_rows)

    @staticmethod
    def codex_homes(codex_rows: list) -> list:
        """Candidate CODEX_HOMEs for a thread with no record, likeliest first:
        this server's own env, the homes of records sharing the daemon, the
        declared Codex homes, then the default. The caller keeps the first one
        whose state DB knows the thread."""
        return registry.codex_homes(codex_rows)

    # -- tools --------------------------------------------------------------------

























    # -- loop -------------------------------------------------------------------------
    def dispatch(self, msg):
        method, mid = msg.get("method"), msg.get("id")
        if not method:
            if mid in self.decision_routes:
                from . import decisions
                decisions.response(self.decision_routes[mid], msg, "mcp-elicitation", source_id=str(mid))
            if mid in self.pending_client:
                self.client_replies[mid] = msg
            return
        params = msg.get("params") or {}
        if method == "notifications/cancelled":
            cancelled = params.get("requestId")
            if cancelled in self.pending_requests:
                self.cancelled.add(cancelled)
            return
        if method == "initialize":
            self.client_caps = params.get("capabilities") or {}
            info = params.get("clientInfo")
            name = info.get("name") if isinstance(info, dict) else None
            self.client_name = name if isinstance(name, str) else None
            self.send({"id": mid, "result": {
                "protocolVersion": params.get("protocolVersion") or PROTOCOL,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "xsm", "version": "1"}}})
        elif method == "tools/list":
            self.send({"id": mid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            if mid in self.pending_requests:
                self.send({"id": mid, "error": {"code": -32600,
                           "message": "duplicate in-flight request id"}})
                return
            saved = self.ctx, self.call_thread, self.active_request
            # Re-entrant tool dispatch can interrupt a form or a wait. Keep
            # consent's reporting globals local to that call as well.
            saved_consent = consent.supplied, consent.used_via, consent.answer_request, consent.question_text
            consent.supplied = consent.used_via = consent.answer_request = consent.question_text = None
            meta = params.get("_meta")
            thread = meta.get("threadId") if isinstance(meta, dict) else None
            self.call_thread = thread if isinstance(thread, str) and thread else None
            self.ctx, self.active_request = None, mid
            self.pending_requests[mid] = params
            try:
                try:
                    text, error = self.call(params.get("name"), params.get("arguments") or {}), False
                except (ToolError, EOFError) as exc:
                    text, error = str(exc), True
                except OSError as exc:
                    text, error = (paths.sandbox_blocked(exc) if paths.blocked_write(exc)
                                   else "xsm failed: %s: %s" % (type(exc).__name__, exc)), True
                except Exception as exc:
                    text, error = "xsm failed: %s: %s" % (type(exc).__name__, exc), True
                    gone = removed_version_note(exc, params.get("name"))
                    if gone:
                        text += "\n" + gone
                try:
                    if mid in self.cancelled and self.handoff_calls.get(mid):
                        from . import receive
                        for me, pack, owner, generation in self.handoff_calls.pop(mid, []):
                            receive.release_inbox(me, [c["token"] for c in pack["claims"]], owner=owner, generation=generation)
                        text, error = "request cancelled; unconfirmed inbox claims released", True
                    self.send({"id": mid, "result": {"content": [{"type": "text", "text": text}],
                                                     "isError": error}})
                except BaseException:
                    from . import receive
                    for me, pack, owner, generation in self.handoff_calls.get(mid, []):
                        receive.release_inbox(me, [c["token"] for c in pack["claims"]], owner=owner, generation=generation)
                    raise
            finally:
                self.handoff_calls.pop(mid, None)
                self.pending_requests.pop(mid, None)
                self.cancelled.discard(mid)
                if saved[2] is None:
                    self.last_context = self.ctx
                self.ctx, self.call_thread, self.active_request = saved
                consent.supplied, consent.used_via, consent.answer_request, consent.question_text = saved_consent
        elif method == "ping" and mid is not None:
            self.send({"id": mid, "result": {}})
        elif mid is not None:
            self.send({"id": mid, "error": {"code": -32601, "message": "not supported"}})

    def serve(self) -> int:
        while True:
            msg = self.read()
            if msg is None:
                return 0
            self.dispatch(msg)


# The shell command each consent-bearing tool stands for, for the note below.
SHELL_FORMS = {"xsm_join": "xsm join <project> (xsm leave <project>)",
               "xsm_link": "xsm link <folder>", "xsm_reach": "xsm reach <folder>",
               "xsm_send": "xsm send <target> --text \"...\""}


def removed_version_note(exc: BaseException, tool: str | None) -> str | None:
    """What to do when this server's own files are gone, or None.

    A plugin update deletes the old version folder while a session started on
    it is still open; a server that had not loaded a module yet then fails with
    ImportError and nothing said why (issue #6: `$xsm join` failed with
    "cannot import name 'workers'" from a deleted 0.4.7 folder). preload()
    prevents this for servers started on 0.4.9 or later; this tells the agent
    and its user the way out on the ones already running."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not isinstance(exc, ImportError) or os.path.isdir(os.path.join(here, "xsm")):
        return None
    shell = SHELL_FORMS.get(tool or "", "xsm <command>")
    return ("This session's xsm MCP server runs from %s, which a plugin update removed. Start a "
            "new session to load the installed xsm. Until then run the same thing in the shell: "
            "`%s`. If it says it needs your user's yes, ask them and run it again."
            % (here, shell))


def beacon_path() -> str:
    return paths.path(paths.MCP, "%d.json" % os.getpid())


def write_beacon() -> None:
    """This server's existence is the liveness signal for the Codex thread it
    serves (see identity._state_of): a Codex TUI launches MCP servers per
    thread and stops them when the thread closes. The hook that registers the
    thread reads the newest beacon under its Codex pid."""
    paths.write_json(beacon_path(), {"pid": os.getpid(), "ppid": os.getppid(),
                                     "lstart": identity.lstart(os.getpid()),
                                     "started": time.time(), "cwd": os.getcwd(), 'profile_migration': 1})


def remove_beacon() -> None:
    try:
        os.unlink(beacon_path())
    except OSError:
        pass


def preload() -> list:
    """Import every xsm module now, while the files this server started from
    are still there. The tools import most of them on first use; a plugin
    update deletes the old version folder (Codex removes it on `codex plugin
    add`), and a session left open then failed its first xsm tool call with
    the modules gone (measured 2026-09-30: three open Codex sessions still ran
    0.4.7 servers from a deleted folder). With everything loaded, an open
    session keeps working on the version it started with until it restarts.
    Returns the modules that could not be imported."""
    import importlib
    import pkgutil
    from . import __path__ as package_path
    failed = []
    for info in pkgutil.iter_modules(package_path):
        if info.name == "__main__":
            continue
        try:
            importlib.import_module("%s.%s" % (__package__, info.name))
        except Exception:                # noqa: BLE001 - a module the server never uses must not stop it
            failed.append(info.name)
    return failed


def main() -> int:
    # The MCP server runs outside any sandbox (that is why it exists); a
    # worker's `env` setting must not make it refuse like a sandboxed shell.
    os.environ.pop("XSM_SANDBOXED", None)
    paths.SANDBOX_HINT = ("the state folder %s must be writable by this server: fix its "
                          "permissions, or set XSM_HOME to a folder that is" % paths.HOME)
    preload()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        write_beacon()
    except OSError:
        # Only Codex's liveness check reads the beacon. A state folder that cannot
        # be written (read-only, a sandbox) died here before `initialize`, so the
        # session saw no xsm tools at all, not even the ones that explain it.
        pass
    try:
        return Server().serve()
    finally:
        remove_beacon()
