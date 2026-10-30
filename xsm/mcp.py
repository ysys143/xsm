"""The xsm MCP server: channel tools for a session, over stdio.

Started by the session (Claude Code or Codex) and ending with it, so it is not
a resident process (ADR-0003). It exists for two reasons (ADR-0005):

- A decision recorded from a session must be the person's. `xsm_decide` asks
  them through MCP elicitation, and their answer comes back from the client to
  this server without passing through the model (measured on both runtimes,
  2026-09-22). The answer and the question are stored with the decision.
- A sandboxed Codex cannot write `~/.xsm` from its shell, but the MCP servers it
  starts run outside the sandbox (measured), so posting and reading go through
  here too.

The session is identified by this process's ancestry: the nearest `claude` or
`codex` ancestor is the session, and its registry record is the author. Codex
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

from . import channel, consent, context, identity, paths, probe, registry
from .instructions import HANDSHAKE_TEXT, MESSAGING_GUIDE

PROTOCOL = "2025-06-18"

# MCP tool annotations (spec 2025-06-18, ToolAnnotations). Codex under
# approval_policy "never" declines an MCP tool that carries none, and a tool
# that does not say it is read-only, or neither destructive nor open-world, is
# asked about first: a message a person wants must not wait on that (user
# decision, 2026-10-01). The tool that only reads says so; the ones that write
# xsm's own state or hand a message to another local session say they destroy
# nothing and reach nothing outside. xsm_send to a paired machine travels over
# the person's own SSH pairing, which is theirs, not an open world.
READ_ONLY = {"readOnlyHint": True, "openWorldHint": False}
MESSAGING = {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}
# Tools that widen a permission or touch another session's files: these require
# an exact caller identity, never a neighbour guessed from a shared daemon pid
# (P01 item 2, A17-02, A23-03).
WIDENING = ("xsm_publish", "xsm_connect", "xsm_grant", "xsm_approve", "xsm_link", "xsm_join", "xsm_reach",
            "xsm_team")
# Tools that read a file on the caller's behalf. The path is taken relative to
# the caller's own folder, so a guessed neighbour would have another session's
# files read for it -- the second thing spec P01 item 2 puts behind an exact
# identity (IC01). Whether that folder is authority for the file itself is the
# separate question D07 decides; this only stops the identity from being a guess.
FILE_READING = ("xsm_doc_endorse", "xsm_ask", "xsm_question_status", "xsm_discover", "xsm_decision_status", "xsm_decide", "xsm_inbox", "xsm_ack", "xsm_files", "xsm_owned")
MESSAGE_TEXT_DESCRIPTION = (
    "The receiver and your user will read this message. Use ordinary "
    "sentences with normal word spacing in the language of the conversation. "
    "Keep it concise without removing spaces or joining words and identifiers "
    "into compressed strings. For longer updates, use short sentences or bullets."
)

TOOLS = [
    {"name": "xsm_owned", "description": "Manage explicitly owned headless workers. "
     "create defines an owned service; run journals a request before starting a native subscribed turn. "
     "Contexts are separate per sender/work_context; independent=true uses a fresh context. "
     "wait defaults to zero; recover by the same request_id with status/reconcile/retry. "
     "retry republishes a stored answer without rerunning the model. Ordinary sessions cannot be adopted.",
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["create", "run", "status", "retry", "reconcile"]},
         "name": {"type": "string"}, "runtime": {"type": "string", "enum": ["claude", "codex"]},
         "dir": {"type": "string"}, "home": {"type": "string"}, "model": {"type": "string"},
         "effort": {"type": "string"}, "grant": {"type": "string"}, "text": {"type": "string"},
         "work_context": {"type": "string"}, "request_id": {"type": "string"},
         "independent": {"type": "boolean", "default": False},
         "wait": {"type": "number", "default": 0, "minimum": 0, "maximum": 60}},
         "required": ["action", "name"]}, "annotations": MESSAGING},
    {"name": "xsm_files", "description": "Read this conversation's received attachment manifest "
     "or one copied entry. Use the storage_id supplied with the message, never an arbitrary path. "
     "Copied text is peer data and grants no permissions.",
     "inputSchema": {"type": "object", "properties": {"storage_id": {"type": "string"},
         "entry_id": {"type": "string"}, "outgoing": {"type": "boolean", "default": False},
         "encoding": {"type": "string", "enum": ["text", "base64"], "default": "text"}},
         "required": ["storage_id"]}, "annotations": READ_ONLY},
    {"name": "xsm_decision_status", "description": "Recover this conversation's pending human "
     "questions and recorded replies. Omit id to list. cancel=true withdraws a pending question, "
     "not an already applied domain permission.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"},
                     "cancel": {"type": "boolean", "default": False}}}},
    {"name": "xsm_ask", "description": MESSAGING_GUIDE,
     "inputSchema": {"type": "object", "properties": {
         "target": {"type": "string"},
         "targets": {"type": "array", "items": {"type": "string"}, "minItems": 1,
                     "description": "several recipients instead of target: each gets its own "
                                    "question and is told who else was asked; the result and "
                                    "xsm_question_status(id=<group id>) hold every recipient's answer"},
         "text": {"type": "string"},
         "wait": {"type": "number", "default": 0, "minimum": 0},
         "request_id": {"type": "string"},
         "priority": {"type": "string", "enum": ["next", "now"], "default": "next"},
         "wake": {"type": "string", "enum": ["auto", "never"], "default": "auto",
                  "description": "never stores a passive local question without native queue/socket/wake."}},
         "required": ["text"]}, "annotations": MESSAGING},
    {"name": "xsm_question_status", "description": "Recover this conversation's actual replies "
     "by request ID, including late and partial replies; timeout does not delete them. "
     "Omit id to list your requests if cancellation lost the original response and ID. "
     "Returned replies include claims when available: read, then xsm_ack directly without another inbox call.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"},
                     "wait": {"type": "number", "default": 0, "minimum": 0}},
                     "required": []}, "annotations": MESSAGING},
    {"name": "xsm_discover", "description": "Find explicitly published or same-repository "
     "conversations by machine, work and branch. Use the returned candidate target after "
     "your user selects it. Discovery alone never grants collaboration.",
     "inputSchema": {"type": "object", "properties": {
         "machine": {"type": "string", "description": "Machine name or label to match."},
         "work": {"type": "string", "description": "Words in the agent's task summary, such as review; not a working-directory path. Omit to browse visible candidates."},
         "branch": {"type": "string", "description": "Git branch name to match."}}}, "annotations": READ_ONLY},
    {"name": "xsm_publish", "description": "Publish only this conversation for discovery after "
     "your user's instruction. visible=false withdraws publication; neither operation links folders.",
     "inputSchema": {"type": "object", "properties": {
         "visible": {"type": "boolean", "default": True},
         "answer_request": {"type": "string"}, "original_question": {"type": "string"}}}},
    {"name": "xsm_connect", "description": "Connect only the selected native conversation "
     "using your user's selection, then request the peer's actual handshake reply. "
     "Permission or a receipt alone never completes it; recover the returned ID after timeout. "
     "Read the actual reply, then acknowledge its returned claims with xsm_ack; no extra inbox call is needed.",
     "inputSchema": {"type": "object", "properties": {"target": {"type": "string"},
         "wait": {"type": "number", "default": 0, "minimum": 0},
         "request_id": {"type": "string"}, "answer_request": {"type": "string"},
         "original_question": {"type": "string"}}, "required": ["target"]},
     "annotations": MESSAGING},
    {"name": "xsm_post",
     "description": ("Post to this project's xsm channel, the record people and sessions share. "
                     "Tags: note, question, proposal, result, hypothesis. A decision cannot be "
                     "posted: ask your user with xsm_decide."),
     "inputSchema": {"type": "object", "properties": {
         "text": {"type": "string", "description": MESSAGE_TEXT_DESCRIPTION},
         "tag": {"type": "string", "enum": [t for t in channel.TAGS if t != "decision"]},
         "reply_to": {"type": "string", "description": "id of the post this answers"},
         "channel": {"type": "string", "description": "a named project; default: this project"}},
         "required": ["text"]},
     "annotations": MESSAGING},
    {"name": "xsm_channel",
     "description": "Read this project's xsm channel: threads, or only posts with one tag.",
     "inputSchema": {"type": "object", "properties": {
         "tag": {"type": "string", "enum": list(channel.TAGS)},
         "limit": {"type": "integer", "default": 30},
         "channel": {"type": "string"}}},
     "annotations": READ_ONLY},
    {"name": "xsm_grant",
     "description": ("Ask your user for explicit permission to start a worker with dangerous "
                     "options: full_access (no sandbox, no approvals) and/or trust_hooks (Codex: "
                     "run hooks without trust review). Returns a one-time grant id for "
                     "`xsm spawn ... --grant <id>`, valid 10 minutes, for this session, runtime "
                     "and folder only. Say plainly why the worker needs it."),
     "inputSchema": {"type": "object", "properties": {
         "runtime": {"type": "string", "description": "claude or codex for a worker; "
                     "remote:<host> for a remote pairing"},
         "options": {"type": "array", "items": {"type": "string",
                                                 "enum": ["full_access", "trust_hooks",
                                                          "outside_scope", "remote"]}},
         "reason": {"type": "string"},
         "dir": {"type": "string", "description": "the worker's folder; default this session's "
                 "(a remote pairing is always for this session's folder)"}},
         "required": ["runtime", "options", "reason"]}},
    {"name": "xsm_send",
     "description": ("Send a message to another session through xsm, the same as `xsm send`. Use "
                     "it when your shell cannot run xsm (a sandboxed Codex cannot: xsm needs the "
                     "process table, and a remote needs the network). Targets: name, "
                     "name@home, ref:xxxxxx, and …@<paired machine>."),
     "inputSchema": {"type": "object", "properties": {
         "target": {"type": "string"},
         "targets": {"type": "array", "items": {"type": "string"}, "minItems": 1,
                     "description": "several recipients instead of target: one DM to each, and "
                                    "each is told who else got it; one outside your scope is "
                                    "skipped and named in the result"},
         "text": {"type": "string", "description": MESSAGE_TEXT_DESCRIPTION},
         "kind": {"type": "string", "enum": ["note", "task", "reply"], "default": "note"},
         "reply_to": {"type": "string"},
         "outcome": {"type": "string", "enum": ["succeeded", "failed"],
                     "description": "only on a reply that closes a task you were given: how it "
                                    "ended. Say a failure here, not only in the words — the flag "
                                    "is what the sender can act on."},
         "priority": {"type": "string", "enum": ["next", "now"], "default": "next"},
         "wake": {"type": "string", "enum": ["auto", "never"], "default": "auto",
                  "description": "never stores a local FYI without queueing or waking the peer; natural prompt/tool input retrieves it."},
         "resend": {"type": "string",
                    "description": "the id of an earlier send that ended unknown or error: sends "
                                   "that same message again under its id, which the receiver "
                                   "drops if it already has it. Same target, kind and text only."},
         "held": {"type": "string",
                  "description": "the id of a message a refused send kept (out of scope: it "
                                 "waits for your user's yes to connect, then goes with it): "
                                 "sends it as it was kept, so target and text are not needed."},
         "wait": {"type": "number", "default": 15}}, "required": []},
     "annotations": MESSAGING},
    {"name": "xsm_team",
     "description": ("Teams of sessions working together (a team is a list of members with an "
                     "optional lead; a DM to team:<name> goes to every member). Actions: list, "
                     "show, create, add, remove, lead, leave, mute, unmute. A lead adds and removes "
                     "sessions of its own project; adding a session outside your scope, and naming "
                     "the lead, ask your user with a form."),
     "inputSchema": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["list", "show", "create", "add", "remove", "lead",
                                               "leave", "mute", "unmute"]},
         "team": {"type": "string"},
         "member": {"type": "string", "description": "add: a session (name, ref:xxxxxx, net:...); "
                                                     "remove/lead: a member's name or ref"},
         "reason": {"type": "string"}},
         "required": ["action"]}, "annotations": MESSAGING},
    {"name": "xsm_ack", "description": "Acknowledge inbox claim tokens only after reading their messages. "
     "Output delivery alone does not acknowledge them. Unacknowledged originals remain recoverable. "
     "Pass each claim's token value; a claim object as shown in the receive context is also accepted.",
     "inputSchema": {"type": "object", "properties": {
         "tokens": {"type": "array", "items": {"type": "string"}, "minItems": 1}},
         "required": ["tokens"]}, "annotations": MESSAGING},
    {"name": "xsm_inbox",
     "description": ("Codex sessions: read messages other sessions sent you that are still "
                     "waiting. Codex takes them only between turns; while you are working, call "
                     "this whenever an xsm result says messages are waiting, and before you wait "
                     "on a peer. A Claude session never needs it: its messages arrive on their "
                     "own. `wait` blocks until one arrives instead of sleeping in a loop — a "
                     "loop that never ends your turn is why six messages once went unread. "
                     "Returns messages and claim tokens. After reading, call xsm_ack with their tokens."),
     "inputSchema": {"type": "object", "properties": {
         "wait": {"type": "number", "default": 0,
                  "description": "seconds to block until a message arrives (max 60 here; the "
                                 "shell `xsm inbox --wait` allows longer)"}}},
     "annotations": MESSAGING},
    {"name": "xsm_link",
     "description": ("Link this session's project folder with another folder, so the sessions "
                     "of both talk both ways until unlinked; one side is enough. The normal way "
                     "to connect another folder. When your user typed `/xsm link <folder>` "
                     "(Codex: `$xsm link <folder>`), that is their consent and no form is shown; "
                     "otherwise this asks them with a form. drop=true unlinks without asking."),
     "inputSchema": {"type": "object", "properties": {
         "dir": {"type": "string", "description": "the other folder, e.g. ~/src/other-repo"},
         "drop": {"type": "boolean", "default": False},
         "reason": {"type": "string"}}, "required": ["dir"]}},
    {"name": "xsm_join",
     "description": ("Ask your user to let this session's folder join (or leave) a named xsm "
                     "project, so sessions in other repositories that also joined it can talk "
                     "with this one. Joining is their decision; this shows them a form."),
     "inputSchema": {"type": "object", "properties": {
         "project": {"type": "string"}, "leave": {"type": "boolean", "default": False},
         "reason": {"type": "string"}}, "required": ["project"]}},
    {"name": "xsm_reach",
     "description": ("Ask your user to let this session talk with the sessions of one other "
                     "folder (both ways, while this session runs), when a send is refused as out "
                     "of scope. Narrower than joining a project: nothing else changes. This "
                     "shows them a form; drop=true takes it back without asking."),
     "inputSchema": {"type": "object", "properties": {
         "dir": {"type": "string", "description": "the other folder, e.g. ~/src/other-repo"},
         "drop": {"type": "boolean", "default": False},
         "reason": {"type": "string"}}, "required": ["dir"]}},
    {"name": "xsm_doc_endorse",
     "description": ("Ask your user to endorse a node of a shared document (xsm doc), making it "
                     "the document's canonical text when rendered. They see the node and decide."),
     "inputSchema": {"type": "object", "properties": {
         "doc": {"type": "string", "description": "path of the document, e.g. docs/x.md"},
         "node": {"type": "string"}}, "required": ["doc", "node"]}},
    {"name": "xsm_approve",
     "description": ("Show your user a permission request from a worker you started, and pass "
                     "on their answer. Call it as soon as you are told a worker is waiting; the "
                     "worker is blocked until it is answered. Without an id, takes the oldest "
                     "waiting request of your workers."),
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}}},
    {"name": "xsm_decide",
     "description": ("Ask your user to decide, and record their answer as a decision in the "
                     "channel. Your user sees the question and picks an option or writes an "
                     "answer; you do not choose for them. Use it when a choice should be on "
                     "record as the user's."),
     "inputSchema": {"type": "object", "properties": {
         "question": {"type": "string"},
         "options": {"type": "array", "items": {"type": "string"},
                     "description": "choices to offer; omit for a free-text answer"},
         "summary": {"type": "string", "description": "one line on what is being decided"},
         "reply_to": {"type": "string"},
         "channel": {"type": "string"}},
         "required": ["question"]}},
]


# The clientInfo.name Codex sends in initialize (codex-rs/codex-mcp/src/rmcp_client.rs,
# 0.158). Only Codex is known to decline forms without showing them.
CODEX_CLIENT = "codex-mcp-client"
ACTIONS = {"accept": "accepted", "decline": "declined", "cancel": "dismissed"}
# The MCP spec's three results of a form: accept (the person submitted it),
# decline (they explicitly said no) and cancel (they dismissed it without
# choosing). A client that shows its forms reports a no as a decline, so xsm
# reads it as the person's no and the agent does not ask again (2026-10-01).
DECLINED = "declined by your user"


for _tool in TOOLS:
    if _tool["name"] in ("xsm_ask", "xsm_send"):
        _tool["inputSchema"]["properties"].update({
            "attachments": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string"}, "text": {"type": "string"}, "base64": {"type": "string"}},
                "required": ["name"], "additionalProperties": False},
                "description": "Content you actually read: name and exactly one of text/base64. Server-side paths are refused."},
            "manifest_id": {"type": "string", "description": "Reuse this frozen manifest after interruption or approval; keep the original request ID and body."},
            "previous_manifest": {"type": "string", "description": "Create a new version under a new request ID, retaining the prior snapshot."},
            "attachment_fallback": {"type": "string", "enum": ["inline"],
                "description": "Explicitly carry UTF-8 copies in the body if peer files support is unknown; never automatic."},
            "request_id": {"type": "string"}})
    if _tool["name"] in ("xsm_link", "xsm_join", "xsm_reach", "xsm_grant", "xsm_approve", "xsm_decide", "xsm_doc_endorse",
                         "xsm_team"):
        _tool["inputSchema"]["properties"]["answer_request"] = {"type": "string"}
        _tool["inputSchema"]["properties"]["original_question"] = {"type": "string"}
        _tool["inputSchema"]["properties"]["decision_key"] = {
            "type": "string", "description": "Reuse for retries of one human decision; "
            "use a different label only for a genuinely new user request."}
        _tool["inputSchema"]["properties"]["notify"] = {
            "type": "boolean", "default": False,
            "description": "Opt in to one frequency-limited OS notification. OS success is not proof of human viewing."}


def person_answer(reply, allowed=None, client=None) -> tuple:
    """The answer a person chose in a form, or (None, why not).

    Every form tool acts only on this. It takes what the client reports: an
    accepted form whose `answer` is a non-empty string (one of `allowed`, when
    the form offers choices), unless `_meta.approvals_reviewer` says someone
    other than the user answered it. Anything malformed — an `action` that is
    not one of the three, a `_meta` or `content` that is not an object — is no
    answer, never an exception: an unhashable `action` once raised past serve()
    and took the server down, and a list `_meta` was read as no meta at all, so
    all six tools acted (second review, 2026-09-28). A client that answers
    forms by itself — a Claude Code Elicitation hook the user configured, say —
    reports it as the user's, and xsm cannot tell; that is outside what it can
    detect.

    Codex (0.158): its auto-review does not look at xsm's forms (it reviews only
    elicitations whose `_meta` asks for an approval), but approval_policy
    "never" (or a granular policy with MCP elicitations off) declines them
    without showing them, unless full-access form input is on for the thread.
    That bare decline is also what a person pressing Decline sends, so it is
    reported as either. A bare "your user did not allow it" read as a refusal
    nobody had given (a tester's report, 2026-09-28). `client` is the
    clientInfo.name from initialize, so the wording names Codex only when it
    is Codex. From a client known to show its forms, a decline is the person's
    no (DECLINED); a client that did not say who it is stays unsure. A cancel
    is no answer: the form was dismissed."""
    if not isinstance(reply, dict):
        return None, "the client sent no reply"
    error = reply.get("error")
    if error is not None:
        return None, "the client returned an error: %s" % (
            (error.get("message") if isinstance(error, dict) else None) or error)
    result = reply.get("result")
    if not isinstance(result, dict):
        return None, "the client sent no result"
    action = result.get("action")
    if not isinstance(action, str) or action not in ACTIONS:
        return None, "the client answered %r, which is not a form answer" % (action,)
    meta = result.get("_meta")
    if meta is not None and not isinstance(meta, dict):
        return None, "the client sent a malformed _meta, so who answered is unknown"
    reviewer = (meta or {}).get("approvals_reviewer")
    if reviewer not in (None, "user"):
        note = next((v for k, v in meta.items() if k != "approvals_reviewer" and isinstance(v, str)),
                    "")
        return None, ("%s by the client's automatic reviewer, not by your user%s; xsm counts only "
                      "a person's answer" % (ACTIONS[action], (": " + note) if note else ""))
    if action == "decline":
        if client == CODEX_CLIENT:
            return None, ("declined — by your user, or by Codex without showing the form "
                          "(approval_policy \"never\")")
        if client:
            return None, DECLINED
        return None, ("declined — by your user, or by the client without showing the form "
                      "(Codex does this under approval_policy \"never\")")
    if action == "cancel":
        return None, "the form was dismissed"
    content = result.get("content")
    answer = content.get("answer") if isinstance(content, dict) else None
    # Stripped, and compared with choices that were offered stripped (decide).
    answer = answer.strip() if isinstance(answer, str) else ""
    if not answer:
        return None, "the form came back with no choice in it, so nobody picked one"
    if allowed and answer not in allowed:
        return None, "the form came back with %r, which is not one of its choices" % answer
    return answer, "they chose %r" % answer


def unanswered(why: str) -> str:
    """The head of a form tool's result when no choice came back. A decline
    (DECLINED) is the person's no and says so; the agent must not ask again.
    Anything else is no answer, and the agent may ask in plain words."""
    if why == DECLINED:
        return "your user declined (they said no; do not ask again or work around it)"
    return "your user did not answer (%s)" % why


def who_answered(reply, client=None) -> str:
    """Who answered a form, in words for the tool's result."""
    return person_answer(reply, client=client)[1]


class Server:
    def __init__(self, inp=sys.stdin, out=sys.stdout):
        self.inp, self.out = inp, out
        self.client_caps = {}
        self.client_name = None         # clientInfo.name from initialize
        self.call_thread = None         # the thread id the current tools/call names, if it does
        # The context of the call in flight, built once at the top of tools/call
        # and never let to leak across calls (P01/IC01). Held under a private
        # name: `call_thread` stays as the raw field it always was, so tests and
        # readers that set it keep working, but the *identity* a tool acts on is
        # `self.ctx` -- a frozen object, not a mutable field another call can
        # overwrite mid-flight.
        self.ctx = None
        self.last_context = None  # diagnostics only, never a caller authority
        self.next_id = 0
        self.active_request = None
        self.pending_requests = {}
        self.pending_client = {}
        self.decision_calls = {}
        self.decision_routes = {}
        self.handoff_calls = {}
        self.owned_jobs = {}
        self.instance_id = os.urandom(12).hex()
        self.reader_identity = {"instance": self.instance_id, "pid": os.getpid(),
                                "generation": context.generation(os.getpid(), identity.lstart(os.getpid()))}
        self.client_replies = {}
        self.cancelled = set()
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
            if decision.get("native_request"):
                from . import user_answers
                evidence = user_answers.read_answer(decision["me"], request=decision["native_request"],
                            since=time.time() - consent.TTL, latest_only=True,
                            tail_bytes=user_answers.MAX_TAIL_BYTES)
                original = decision.get("native_question")
                if not evidence or evidence["question"] != original or original != record["question"]:
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
                    return record["answer"]["reply"]
                return {"id": rid, "error": {"code": -32000, "message": "decision is not applicable: " + record["status"] +
                        "; inspect xsm_decision_status; a renewed user request uses a new decision_key"}}
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

    def _decision_current(self, decision):
        from . import decisions
        record = decisions.read(decision["key"])
        if (record["status"] == "answered" and
                (not record["display"].get("complete") or time.time() > record["expires_at"] or
                 time.time()<record['created_at'])):
            return False
        original = decision["me"]
        if original.get("registered") and original.get("session_id"):
            current = registry.by_session(original["runtime"], original["session_id"])
            if (not current or current.get("state") in ("ended", "stale") or
                    decisions.owner(current) != decisions.owner(original) or
                    current.get("cwd") != original.get("cwd") or
                    context.of_record(current, context.BASIS_SESSION).generation != decision["generation"]):
                decisions.supersede(decision["key"])
                return False
        return True

    def _deny_current_decision(self):
        decision = self.decision_calls.get(self.active_request)
        if decision:
            from . import decisions
            decisions.deny(decision["key"])

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
        rows = [r for r in mine if r.get("state") == "live"]
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
            for r in codex:
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
            return context.normalize_home(os.environ.get("CODEX_HOME") or "~/.codex")
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
    def call(self, name: str, args: dict) -> str:
        # The caller lookup shares one bounded budget. The channel below stays out of
        # it: a spent budget must not starve the git lookup that says which channel
        # or scope a message belongs to.
        with probe.quick():
            me = self.session()
        if not me:
            # The server's own environment does not carry the caller's thread id,
            # so name the runtime and thread the call resolved, and say why it
            # found no record: a bare "no hook record" hid the cause (T0).
            runtime = self.ctx.runtime if self.ctx and self.ctx.runtime else None
            why = registry.unregistered_reason(runtime or ("codex" if self.call_thread else None),
                                               self.call_thread)
            evidence = "; ".join(self.ctx.evidence) if self.ctx and self.ctx.evidence else ""
            raise channel.ChannelError(why + (" (caller lookup: %s)" % evidence if evidence else ""))
        if self.ctx is None:
            # A harness or an older entry point set the record without going
            # through `_resolve`: its identity is the record itself.
            self.ctx = context.of_record(me, context.BASIS_SESSION,
                                         evidence=("the caller was provided directly",))
        # Widening a permission is the one thing a guessed neighbour must never
        # do (P01 item 2). Plain messaging does not come through here.
        if name in WIDENING:
            why = context.require_sure(self.ctx, "widen a permission")
            if why:
                paths.append_jsonl("decisions.jsonl", {
                    "event": "mcp", "decision": "refused", "tool": name,
                    "reason": "caller not surely identified", "basis": self.ctx.basis,
                    "certainty": self.ctx.certainty, "ref": me.get("ref")})
                raise channel.ChannelError(why)
            from . import config
            config.require_valid_policy()
        if name in FILE_READING:
            why = context.require_sure(self.ctx, "read a file")
            if why:
                paths.append_jsonl("decisions.jsonl", {
                    "event": "mcp", "decision": "refused", "tool": name,
                    "reason": "caller not surely identified", "basis": self.ctx.basis,
                    "certainty": self.ctx.certainty, "ref": me.get("ref")})
                raise channel.ChannelError(why)
        if self.ctx.sure:
            registry.note_capabilities(me, {"files": {"version": 1, "status": "observed"}},
                                       reader_pid=os.getpid())
        where = channel.resolve(me.get("cwd") or os.getcwd(), args.get("channel"))
        author = {"kind": "agent", "name": me.get("name"), "alias": me.get("alias"),
                  "ref": me.get("ref"), "runtime": me.get("runtime")}
        if not self.ctx.sure:
            # Say how the caller was identified on anything it posts, so a
            # provisional identity is visible where it matters (P01 item 2).
            author["identity_basis"] = self.ctx.basis
            author["identity_certainty"] = self.ctx.certainty
        form_tools = ("xsm_link", "xsm_join", "xsm_reach", "xsm_grant", "xsm_approve",
                      "xsm_decide", "xsm_doc_endorse", "xsm_team")
        decision_call = None
        if name in form_tools:
            from . import decisions
            generation = self.ctx.generation or {"server": self.instance_id}
            scope = {"tool": name, "arguments": {k: v for k, v in args.items()
                     if k not in ("answer_request", "original_question", "notify")}, "cwd": me.get("cwd")}
            key = decisions.invocation(me, name, args, generation)
            prior = decisions.read(key)
            if prior and prior["status"] == "applied":
                return prior["application"]["result"]
            decision_call = {"key": key, "me": copy.deepcopy(me), "scope": scope, "generation": generation,
                             "notify": args.get("notify") is True,
                             "native_request": args.get("answer_request"),
                             "native_question": args.get("original_question")}
            self.decision_calls[self.active_request] = decision_call
        try:
            text = self._call(name, args, me, where, author)
            if decision_call:
                record = decisions.read(decision_call["key"])
                if record and record["status"] == "answered":
                    decisions.applied(record["id"], text, decision_call["generation"], scope)
        finally:
            if decision_call:
                self.decision_calls.pop(self.active_request, None)
        incoming = None
        if self.ctx.sure and name not in ("xsm_inbox", "xsm_ack", "xsm_ask", "xsm_question_status", "xsm_connect"):
            from . import receive
            try:
                owner, generation = receive.consumer_for(me)
            except ValueError:
                # No runtime generation means no inbox claim, not failure of
                # the unrelated channel/tool operation already performed.
                incoming = {"messages": [], "claims": []}
            else:
                incoming = receive.take_inbox_claims(me, owner=owner, generation=generation, passive_only=True)
            if incoming["claims"]:
                self.handoff_calls.setdefault(self.active_request, []).append((me, incoming, owner, generation))
        if name in ("xsm_ask", "xsm_question_status", "xsm_connect", "xsm_discover", "xsm_publish", "xsm_decision_status", "xsm_inbox", "xsm_ack", "xsm_files", "xsm_owned"):
            from . import inbox
            value = json.loads(text)
            if name in ("xsm_ask", "xsm_question_status", "xsm_connect"):
                from . import receive
                value = receive.claim_question_replies(me, value)
                if value['claims']:
                    first = value['claims'][0]
                    self.handoff_calls.setdefault(self.active_request, []).append(
                        (me, value, first['owner'], first['generation']))
            from . import receive
            value.update(inbox.pending_fields(me, owner_alive=receive._consumer_alive))
            if incoming and incoming["messages"]:
                value["incoming"] = incoming
            from .provenance import readable
            return readable(value)
        if incoming and incoming["messages"]:
            text += "\n\nUnconfirmed incoming messages (read, then xsm_ack):\n" + json.dumps(incoming, ensure_ascii=False)
        if me.get("runtime") == "codex" and name != "xsm_inbox":
            from . import inbox
            from . import receive
            waiting = inbox.notice(me.get("session_id"), receiver=me, owner_alive=receive._consumer_alive)
            if waiting:
                text += "\n\n" + waiting
        from . import bounce
        held = bounce.notice(me.get("session_id"))     # issue #8
        if held:
            text += "\n\n" + held
        return text

    def _call(self, name: str, args: dict, me: dict, where: tuple, author: dict) -> str:
        if name == "xsm_owned":
            return json.dumps(self.owned(me,args),ensure_ascii=False)
        if name == "xsm_files":
            from . import files
            storage, entry = args.get("storage_id"), args.get("entry_id")
            incoming = not args.get("outgoing", False)
            if not entry:
                return json.dumps({"storage_id": storage, "manifest": files.manifest(me, storage, incoming=incoming)}, ensure_ascii=False)
            data = files.read_copy(me, storage, entry, incoming=incoming)
            encoding = args.get("encoding", "text")
            if encoding not in ("text", "base64"):
                raise channel.ChannelError("encoding must be text or base64")
            try:
                content = base64.b64encode(data).decode("ascii") if encoding == "base64" else data.decode("utf-8")
            except UnicodeError as exc:
                raise channel.ChannelError("binary copy: request encoding=base64") from exc
            return json.dumps({"storage_id": storage, "entry_id": entry, "encoding": encoding, "content": content}, ensure_ascii=False)
        if name == "xsm_decision_status":
            from . import decisions
            return json.dumps(decisions.public_status(me, args.get("id"), args.get("cancel", False)), ensure_ascii=False)
        if name in ("xsm_connect", "xsm_publish") and args.get("answer_request"):
            if not args.get("original_question"):
                raise channel.ChannelError("answer_request requires original_question")
            consent.answer_request = args["answer_request"]
            consent.question_text = args["original_question"]
        if name == "xsm_publish":
            from . import connect
            visible = args.get("visible", True)
            if not isinstance(visible, bool):
                raise channel.ChannelError("visible must be a boolean")
            return json.dumps(connect.publication(me, visible=visible, call=self.ctx), ensure_ascii=False)
        if name == "xsm_discover":
            from . import directory
            return json.dumps(directory.discover(me, machine=args.get("machine"),
                              work=args.get("work"), branch=args.get("branch")), ensure_ascii=False)
        if name in ("xsm_ask", "xsm_question_status", "xsm_connect"):
            from . import envelope, questions, receive
            requested_wait = float(args.get("wait", 0) or 0)
            if not math.isfinite(requested_wait) or requested_wait < 0:
                raise channel.ChannelError("wait must be finite and nonnegative")
            wait = min(requested_wait, 60.0)
            if args.get("wake", "auto") not in ("auto", "never"):
                raise channel.ChannelError("unsupported wake mode; use auto or never")
            if name == "xsm_question_status" and args.get("id") is None:
                if requested_wait:
                    raise channel.ChannelError("an id is required to wait; omit wait to list your requests")
                return json.dumps({"status": "requests", "requests": questions.list_requests(me)}, ensure_ascii=False)
            request_id = args.get("id") if name == "xsm_question_status" else \
                (args.get("request_id") or envelope.new_id())
            owner = self.active_request
            last_scan = [float("-inf")]

            def pump():
                live = self.pump()
                now = time.monotonic()
                if now - last_scan[0] >= .2:
                    last_scan[0] = now
                    receive.poll_replies(me, request_id)
                return live

            kwargs = {"wait": wait, "pump": pump,
                      "cancelled": lambda: owner in self.cancelled}
            from . import inbox, question_groups
            group_poll = lambda child: receive.poll_replies(me, child)  # noqa: E731
            from . import teams as teams_mod
            if name == "xsm_ask" and args.get("targets") is None and teams_mod.is_address(args.get("target") or ""):
                args = dict(args, targets=[args["target"]], target=None)
            if name == "xsm_ask" and args.get("targets") is not None:
                targets = args.get("targets")
                if not isinstance(targets, list) or not all(isinstance(t, str) for t in targets) \
                        or args.get("target") or args.get("request_id") \
                        or args.get("attachments") or args.get("manifest_id"):
                    raise channel.ChannelError("targets is a list of recipients, used instead of "
                                               "target, request_id and attachments")
                try:
                    result = question_groups.ask_many(
                        me, targets, args.get("text") or "", wait=wait,
                        priority=args.get("priority", "next"), wake=args.get("wake", "auto"),
                        pump=self.pump, cancelled=lambda: owner in self.cancelled, poll=group_poll)
                except question_groups.GroupError as exc:
                    raise channel.ChannelError(str(exc))
                result = question_groups.with_claims(me, result)
                result.update(inbox.pending_fields(me, owner_alive=receive._consumer_alive))
                result["wait_budget"] = {"requested": requested_wait, "effective": wait, "cap": 60}
                return json.dumps(result, ensure_ascii=False)
            if name == "xsm_question_status" and question_groups.is_group(request_id):
                result = question_groups.wait_for(me, request_id, wait=wait, pump=self.pump,
                                                  cancelled=lambda: owner in self.cancelled,
                                                  poll=group_poll)
                result = question_groups.with_claims(me, result)
                result.update(inbox.pending_fields(me, owner_alive=receive._consumer_alive))
                result["wait_budget"] = {"requested": requested_wait, "effective": wait, "cap": 60}
                return json.dumps(result, ensure_ascii=False)
            if name == "xsm_ask" and not args.get("target"):
                raise channel.ChannelError("target (or targets) is required")
            if name == "xsm_question_status":
                from . import ledger
                network_state = None
                if str(ledger.status(request_id).get("scope") or "").startswith("network:"):
                    from . import network
                    network_state = network.reconcile(request_id, caller=me)
                receive.poll_replies(me, request_id)
                result = questions.wait_for(me, request_id, **kwargs)
                if network_state is not None:
                    for key in ("network_status", "network_delivery"):
                        if key in network_state:
                            result[key] = network_state[key]
            else:
                purpose = "question"
                body = args.get("text") or ""
                prepared = None
                if name == "xsm_ask":
                    from . import materials
                    prepared = self.prepare_materials(me,args,body,request_id)
                    body = prepared["body"]
                if name == "xsm_connect":
                    from . import connect, resolve
                    with probe.quick():
                        found = resolve.resolve(args.get("target", ""), caller=me)
                    if not found.ok:
                        raise channel.ChannelError(found.reason)
                    if args.get("request_id") and (
                            not questions.expects_reply(me, found.record, request_id) or
                            questions.status(me, request_id).get("purpose") != "handshake"):
                        raise channel.ChannelError("request ID does not belong to this selected handshake")
                    result = connect.select(me, found.record, call=self.ctx)
                    if result["status"] != "permitted":
                        return json.dumps(result, ensure_ascii=False)
                    if args.get("request_id"):
                        receive.poll_replies(me, request_id)
                        result = questions.wait_for(me, request_id, **kwargs)
                        result["wait_budget"] = {"requested": requested_wait, "effective": wait, "cap": 60}
                        return json.dumps(result, ensure_ascii=False)
                    purpose, body = "handshake", HANDSHAKE_TEXT
                result = questions.ask(me, args.get("target", ""), body,
                                       request_id=request_id, priority=args.get("priority", "next"),
                                       purpose=purpose, wake=args.get("wake", "auto"),
                                       attachments=prepared["attachments"] if prepared else None,
                                       file_packet=prepared["file_packet"] if prepared else None,
                                       file_limits=prepared["file_limits"] if prepared else None, **kwargs)
                if prepared and prepared["manifest_id"]:
                    result["materials"] = materials.public(prepared)
            result["wait_budget"] = {"requested": requested_wait, "effective": wait, "cap": 60}
            return json.dumps(result, ensure_ascii=False)
        if name == "xsm_post":
            rec = channel.post(where, author, args.get("text", ""), args.get("tag") or "note",
                               args.get("reply_to"))
            return "posted %s to %s" % (rec["id"], where[0])
        if name == "xsm_channel":
            text = channel.render(channel.read(where[1]), tag=args.get("tag"),
                                  limit=int(args.get("limit") or 30))
            return text or "(no posts in %s)" % where[0]
        if name == "xsm_decide":
            return self.decide(where, me, args)
        if name == "xsm_grant":
            return self.grant(where, me, args)
        if name == "xsm_approve":
            return self.approve(me, args)
        if name == "xsm_join":
            return self.join(me, args)
        if name == "xsm_reach":
            return self.reach(me, args)
        if name == "xsm_link":
            return self.link(me, args)
        if name == "xsm_send":
            from . import send as send_mod
            if args.get("outcome") and (args.get("kind") or "note") != "reply":
                raise channel.ChannelError("outcome belongs only to a reply that closes a task")
            if args.get("wake", "auto") not in ("auto", "never"):
                raise channel.ChannelError("unsupported wake mode; use auto or never")
            targets = args.get("targets")
            from . import teams as teams_mod
            if targets is None and teams_mod.is_address(args.get("target") or ""):
                args = dict(args, targets=[args["target"]], target=None)
                targets = args["targets"]
            if targets is not None:
                from . import multisend
                if not isinstance(targets, list) or not all(isinstance(t, str) for t in targets) \
                        or args.get("target") or args.get("held") or args.get("resend") \
                        or args.get("attachments") or args.get("manifest_id"):
                    raise channel.ChannelError("targets is a list of recipients, used instead of "
                                               "target, held, resend and attachments")
                wait = args.get("wait", 15)
                try:
                    result = multisend.send_many(
                        targets, args.get("text") or "", sender=me, call=self.ctx,
                        kind=args.get("kind") or "note", reply_to=args.get("reply_to"),
                        priority=args.get("priority") or "next", wait=float(15 if wait is None else wait),
                        outcome=args.get("outcome") if args.get("kind") == "reply" else None,
                        wake=args.get("wake", "auto") != "never")
                except multisend.MultiError as exc:
                    raise channel.ChannelError(str(exc))
                return "\n".join(result.lines())
            from . import envelope, materials
            request_id = args.get("resend") or args.get("request_id") or envelope.new_id()
            if args.get("held") and (args.get("attachments") or args.get("manifest_id")):
                raise channel.ChannelError("held sends reuse their stored material; do not supply new attachments")
            prepared = self.prepare_materials(me,args,args.get("text") or "",request_id)
            wait = args.get("wait", 15)             # the schema's default
            r = send_mod.send(args.get("target") or "", prepared["body"], sender=me,
                              kind=args.get("kind") or "note", reply_to=args.get("reply_to"),
                              priority=args.get("priority") or "next",
                              wait=float(15 if wait is None else wait),
                              outcome=args.get("outcome") if args.get("kind") == "reply" else None,
                              msg_id=request_id if (args.get('resend') or args.get('request_id') or prepared['manifest_id']) else None,
                              resend=bool(args.get("resend")), held=args.get("held") or None,
                              call=self.ctx, wake=args.get("wake", "auto") != "never",
                              attachments=prepared["attachments"], file_packet=prepared["file_packet"],
                              file_limits=prepared["file_limits"])
            text = "\n".join(r.lines())
            if prepared["manifest_id"]:
                text += "\nMaterials: " + json.dumps(materials.public(prepared), ensure_ascii=False)
            return text
        if name == "xsm_doc_endorse":
            return self.endorse(me, args)
        if name == "xsm_team":
            return self.team(me, args)
        if name == "xsm_ack":
            from . import receive
            tokens = args.get("tokens")
            if not isinstance(tokens, list) or not tokens or not all(isinstance(t, (str, dict)) for t in tokens):
                raise channel.ChannelError("tokens must be a nonempty array of claim tokens "
                                           "(the token values, or the claim objects as shown)")
            owner, generation = receive.consumer_for(me)
            return json.dumps(receive.ack_inbox(me, tokens, owner=owner, generation=generation))
        if name == "xsm_inbox":
            from . import inbox, receive
            wait = float(args.get("wait") or 0)
            if not math.isfinite(wait) or wait < 0:
                raise channel.ChannelError('wait must be finite and nonnegative')
            call_owner = self.active_request
            if wait > 0:
                # Shorter than the shell's cap: serve() reads one request at a
                # time, so a long block looks to the client like a dead server.
                inbox.wait_for(me.get("session_id"), min(wait, inbox.MCP_MAX_WAIT),
                    counter=lambda: inbox.pending_fields(me, owner_alive=receive._consumer_alive)['inbox_pending'],
                    pump=self.pump if call_owner is not None else None,
                    cancelled=lambda: call_owner in self.cancelled)
                if call_owner in self.cancelled or (call_owner is not None and self._closed):
                    raise channel.ChannelError('inbox wait cancelled or input closed; original retained')
            owner, generation = receive.consumer_for(me)
            pack = receive.take_inbox_claims(me, owner=owner, generation=generation)
            if pack["claims"]:
                self.handoff_calls.setdefault(self.active_request, []).append((me, pack, owner, generation))
            return json.dumps(pack, ensure_ascii=False)
        # A client that loaded its tool list from a newer xsm than this server
        # (the server reads TOOLS once, at its start) names a tool it lacks.
        raise channel.ChannelError(
            "unknown tool %s: this xsm server started before xsm was updated. Reconnect it (Claude "
            "Code: /mcp, then xsm) or start a new session; meanwhile run the same `xsm` command "
            "in the shell" % name)

    def owned(self,me,args):
        from . import workers,owned_requests,envelope,decisions
        action,name=args.get("action"),args.get("name")
        if not isinstance(name,str) or not name:
            raise channel.ChannelError("owned worker name required")
        if action=="create":
            return workers.create_owned(args.get("runtime"),caller=me,name=name,cwd=args.get("dir"),
                home=args.get("home"),model=args.get("model"),effort=args.get("effort"),grant=args.get("grant"))
        if action=="status":
            if args.get("request_id"):
                return workers.owned_status(name,me,args["request_id"])
            return {"status":"requests","requests":workers.owned_history(name,me)}
        if action in ("retry","reconcile"):
            if not args.get("request_id"):
                raise channel.ChannelError("request_id required for reply recovery")
            fn=workers.resend_owned if action=="retry" else workers.reconcile_owned
            return fn(name,me,args["request_id"])
        if action!="run":
            raise channel.ChannelError("unknown owned action")
        wait=float(args.get("wait",0) or 0)
        if not math.isfinite(wait) or wait<0:
            raise channel.ChannelError("wait must be finite and nonnegative")
        wait=min(wait,60)
        request_id=args.get("request_id") or envelope.new_id()
        from . import handoff
        handoff._id(request_id)
        arguments={"work_context":args.get("work_context"),"request_id":request_id,
                   "independent":args.get("independent",False)}
        try:
            verified=workers.submit_owned(name,me,args.get('text') or '',**arguments)
        except (workers.WorkerError,owned_requests.OwnedError) as exc:
            raise channel.ChannelError(str(exc)) from exc
        fingerprint=verified['digest']
        key=(me.get("runtime"),me.get("home"),me.get("session_id"),self.ctx.generation,
             verified['worker']['id'],request_id)
        job=self.owned_jobs.get(key)
        if job is not None and job["fingerprint"]!=fingerprint:
            raise channel.ChannelError("request_id differs in body, work context or sender")
        if job is not None and not job['thread'].is_alive():
            self.owned_jobs.pop(key,None)
            job=None
        if job is None:
            job={"fingerprint":fingerprint,"result":None,"error":None}
            caller=copy.deepcopy(me)
            def execute():
                try:
                    job["result"]=workers.run_owned(name,caller,args.get("text") or "",**arguments)
                except Exception as exc:
                    job["error"]=exc
            job["thread"]=threading.Thread(target=execute,daemon=True,name="xsm-owned-"+request_id)
            self.owned_jobs[key]=job
            job["thread"].start()
        deadline=time.monotonic()+max(wait,1.0)
        value=verified
        owner=self.active_request
        while True:
            if job["error"] is not None:
                raise channel.ChannelError(str(job["error"]))
            if job["result"] is not None:
                value=job["result"]
                break
            try:
                value=owned_requests.status(verified['owner'],request_id,sender=me)
            except ValueError:
                value=None
            if value is not None and wait==0:
                break
            if owner in self.cancelled or time.monotonic()>=deadline or not self.pump():
                break
            time.sleep(.02)
        value=value or {"id":request_id,"status":"unknown","reason":"request not yet readable; do not use a new ID"}
        value=dict(value)
        value["recover_at"]={"tool":"xsm_owned","arguments":{"action":"status","name":name,"request_id":request_id}}
        value["waiter_cancelled"]=owner in self.cancelled
        if not job['thread'].is_alive():
            self.owned_jobs.pop(key,None)
        return value

    def prepare_materials(self,me,args,body,request_id):
        from . import materials,files
        try:
            return materials.prepare(me,args.get("target") or "",body,request_id,args.get("attachments"),
                manifest_id=args.get("manifest_id"),previous=args.get("previous_manifest"),
                fallback=args.get("attachment_fallback"),call=self.ctx)
        except files.FileError as exc:
            from .provenance import readable
            raise channel.ChannelError(readable(materials.failure(exc))) from exc

    def decide(self, where: tuple, me: dict, args: dict) -> str:
        if "elicitation" not in (self.client_caps or {}):
            # The text to record is the agent's, so there is no ask to record
            # for it here: the command comes first (in_words).
            raise channel.ChannelError("this client cannot show a form (no elicitation "
                                       "support). " + self.in_words(
                                           me, 'xsm post --tag decision "<the decision to '
                                               'record>"'))
        question = (args.get("question") or "").strip()
        # Offered as they will be compared: stripped, no empties, no repeats.
        # " yes " used to be offered as is and then compared stripped, so the
        # person's choice was rejected (second review, 2026-09-28).
        options = []
        for o in args.get("options") or []:
            o = o.strip() if isinstance(o, str) else ""
            if o and o not in options:
                options.append(o)
        field = {"type": "string", "title": "Answer"}
        if options:
            field["enum"] = options
        reply = self.ask_client("elicitation/create", {
            "message": question,
            "requestedSchema": {"type": "object", "properties": {"answer": field},
                                "required": ["answer"]}})
        answer, why = self.answer(reply, options)
        if answer is None:
            return "%s; nothing was recorded%s" % (unanswered(why), "" if why == DECLINED else
                                                   ". " + self.in_words(
                                                       me, 'xsm post --tag decision "<the '
                                                           'decision to record>"'))
        summary = (args.get("summary") or "").strip()
        text = "%s: %s" % (summary, answer) if summary else "%s -> %s" % (question, answer)
        author = {"kind": "human", "name": os.environ.get("USER") or "person",
                  "via": "mcp-elicitation", "asked_by": me.get("ref"),
                  "runtime": me.get("runtime")}
        rec = channel.post(where, author, text, "decision", args.get("reply_to"),
                           approved={"question": question, "answer": answer,
                                     "options": options or None})
        return "recorded decision %s in %s: %s" % (rec["id"], where[0], answer)

    def endorse(self, me: dict, args: dict) -> str:
        from . import doc
        path = args.get("doc") or ""
        if not os.path.isabs(path):
            path = os.path.join(me.get("cwd") or os.getcwd(), path)
        node = next((n for n in doc.read(path) if n["id"] == args.get("node")), None)
        if not node:
            raise channel.ChannelError("no node %s in %s" % (args.get("node"), path))
        # The command is the node's own text, so the ask recorded for it here is
        # the one that command finds (consent.digest as the CLI keys it).
        command = "xsm doc add %s --tag endorsed --parent %s --text %s" % (
            shlex.quote(args.get("doc") or ""), shlex.quote(node["id"]), shlex.quote(node["body"]))
        key = ("endorse", consent.digest(args.get("doc"), node["body"], [node["id"]]))
        if "elicitation" not in (self.client_caps or {}):
            raise channel.ChannelError("this client cannot show a form. "
                                       + self.in_words(me, command, key))
        preview = node["body"] if len(node["body"]) < 1500 else node["body"][:1500] + " …"
        reply = self.ask_client("elicitation/create", {
            "message": "Endorse this node of %s as the document's text?\n[%s] by %s\n\n%s" % (
                os.path.basename(path), ", ".join(node["tags"]), node["author"], preview),
            "requestedSchema": {"type": "object", "properties": {"answer": {
                "type": "string", "title": "Endorse", "enum": ["endorse", "not now"]}},
                "required": ["answer"]}})
        answer, why = self.answer(reply, ["endorse", "not now"])
        if answer != "endorse":
            if answer is not None:
                self._deny_current_decision()
            return "your user did not endorse it (%s); nothing was added%s" % (
                why, ". " + self.in_words(me, command, key) if answer is None and why != DECLINED
                else "")
        author = {"kind": "human", "name": os.environ.get("USER") or "person",
                  "via": "mcp-elicitation"}
        new = doc.add(path, author, node["body"], ["endorsed"], [node["id"]],
                      approved="asked by %s" % me.get("ref"))
        return "endorsed: node %s now carries %s; run `xsm doc render %s`" % (
            new["id"], node["id"], args.get("doc"))

    def in_words(self, me: dict, command: str, key: tuple | None = None) -> str:
        """What to tell the agent when a form got no answer: ask in plain words,
        then run `command`. The ask is recorded here under `key` (the one that
        command computes), so their first "yes" has an ask to attach to; with no
        key, or no session xsm can keep a reply for, the command goes first
        (consent.in_words)."""
        return consent.in_words(command, bool(key) and consent.ask(me, *key), me.get("runtime"))

    def allowed(self, me: dict, question: str, command: str, key: tuple | None = None) -> tuple:
        """Ask the person allow/deny. Returns (True, None) on their allow, else
        (False, what to tell the agent). The way round a form that cannot show
        is the agent's own shell command, which asks for the user's reply
        (consent.py) — never the person typing it (user decision, 2026-10-01)."""
        if "elicitation" not in (self.client_caps or {}):
            raise channel.ChannelError("this client cannot show a form. "
                                       + self.in_words(me, command, key))
        reply = self.ask_client("elicitation/create", {"message": question, "requestedSchema": {
            "type": "object", "properties": {"answer": {"type": "string", "title": "Permission",
                                                        "enum": ["allow", "deny"]}},
            "required": ["answer"]}})
        answer, why = self.answer(reply, ["allow", "deny"])
        if answer == "allow":
            return True, None
        if answer == "deny":
            self._deny_current_decision()
            return False, "your user declined: they chose 'deny'; do not work around it"
        if why == DECLINED:
            return False, unanswered(why)
        return False, "your user did not answer (%s). %s" % (why, self.in_words(me, command, key))

    def link(self, me: dict, args: dict) -> str:
        from . import config
        if not args.get("dir"):
            raise channel.ChannelError("dir: the folder to link with")
        here = me.get("cwd") or os.getcwd()
        root = config.project_root(here)
        # Relative to the session, like reach: the form, the command and the
        # link all name the same absolute root.
        other = config.project_root(os.path.join(here, os.path.expanduser(args["dir"])))
        if args.get("drop"):
            return ("unlinked %s and %s" % (root, other)) if config.drop_link(root, other) \
                else "%s and %s were not linked" % (root, other)
        # What can be checked is checked before the consent is used up: a
        # folder not created yet used it, and the retry asked with a form
        # (review, 2026-09-28).
        try:
            config.check_link(root, other)
        except ValueError as exc:
            raise channel.ChannelError(str(exc))
        if not consent.take(me, "link", other, here):
            # Run from this session's own folder; --dir is taken only from a
            # person at a terminal, so it would refuse the agent (issue #9).
            command = "xsm link %s" % shlex.quote(other)
            ok, refusal = self.allowed(
                me, "%s@%s asks to link %s with %s: the sessions of both folders talk, both ways, "
                "until unlinked.%s\nAllow it?" % (
                    me.get("name"), me.get("alias"), root, other,
                    ("\nReason: " + args["reason"]) if args.get("reason") else ""), command,
                ("link", other, here))
            if not ok:
                return refusal
        try:
            entry, added = config.add_link(root, other, os.environ.get("USER") or "person")
        except ValueError as exc:
            raise channel.ChannelError(str(exc))
        return ("%s: the sessions in %s and %s can talk, both ways, until unlinked; run `xsm list` "
                "to see them" % ("linked" if added else "already linked", root, other))

    def team(self, me: dict, args: dict) -> str:
        """xsm_team: the same rules as `xsm team`; a decision that is the
        user's is asked with a form (self.allowed)."""
        from . import resolve, team_sync, teams
        action = args.get("action")
        try:
            if action == "list":
                return json.dumps({"teams": [{"name": t["name"], "lead": teams.label(t["lead"]) if t.get("lead") else None,
                                              "members": [teams.label(m) for m in t["members"]]}
                                             for t in teams.all_teams()]}, ensure_ascii=False)
            name = (args.get("team") or "").strip()
            if not name:
                raise channel.ChannelError("team: the team's name")
            if action == "create":
                team = teams.create(me, name)
                return "created team %s with %s" % (team["name"], teams.label(team["members"][0]))
            team = teams.require(name)
            if action == "show":
                return json.dumps({"name": team["name"], "lead": teams.label(team["lead"]) if team.get("lead") else None,
                                   "members": [{"member": teams.label(m), "running": teams.address(m) is not None}
                                               for m in team["members"]]}, ensure_ascii=False)
            if action in ("mute", "unmute"):
                if not teams.is_member(team, me):
                    raise teams.TeamError("you are not in team %s" % team["name"])
                teams.mute(team["name"], me, on=action == "mute")
                return "%sd team %s's DMs for this session" % (action, team["name"])
            if action == "leave":
                team = teams.remove(me, name, teams.member_of(me), None)
                team_sync.publish(team)
                return "left team %s" % team["name"]
            word = (args.get("member") or "").strip()
            if not word:
                raise channel.ChannelError("member: the session to %s" % action)
            reason = ("\nReason: " + args["reason"]) if args.get("reason") else ""
            if action == "add":
                with probe.quick():
                    found = resolve.resolve(word, caller=me) if word.startswith(("net:", "candidate:")) \
                        else resolve.resolve(word)
                if not found.ok:
                    raise channel.ChannelError(found.reason)
                target = found.record
                approval = "lead"
                if teams.add_rule(me, team, target) == "user":
                    who = teams.label(teams.member_of(target))
                    ok, refusal = self.allowed(
                        me, "%s@%s asks to add %s to team %s, so the team's members and it can DM "
                        "each other.%s\nAllow it?" % (me.get("name"), me.get("alias"), who, name, reason),
                        "xsm team add %s %s" % (shlex.quote(name), shlex.quote(word)),
                        ("team-add-" + name, target.get("name") or word))
                    if not ok:
                        return refusal + "; the team is unchanged"
                    approval = "your user approved in the form"
                team = teams.add(me, name, target, approval)
                notes = team_sync.publish(team)
                return "\n".join(["added %s to team %s" % (teams.label(teams.member_of(target)), name)] + notes)
            member = teams.find_member(team, word)
            if action == "remove":
                approval = None
                if not (teams.matches(member, me) or teams.is_lead(team, me)):
                    ok, refusal = self.allowed(
                        me, "%s@%s asks to remove %s from team %s.%s\nAllow it?" % (
                            me.get("name"), me.get("alias"), teams.label(member), name, reason),
                        "xsm team remove %s %s" % (shlex.quote(name), shlex.quote(word)),
                        ("team-remove-" + name, member.get("name") or word))
                    if not ok:
                        return refusal + "; the team is unchanged"
                    approval = "your user approved in the form"
                team = teams.remove(me, name, member, approval)
                team_sync.publish(team)
                return "removed %s from team %s" % (teams.label(member), name)
            if action == "lead":
                ok, refusal = self.allowed(
                    me, "%s@%s asks to make %s the lead of team %s: the session that faces you, "
                    "takes your approvals and adds or removes this project's sessions.%s\nAllow it?" % (
                        me.get("name"), me.get("alias"), teams.label(member), name, reason),
                    "xsm team lead %s %s" % (shlex.quote(name), shlex.quote(word)),
                    ("team-lead-" + name, member.get("name") or word))
                if not ok:
                    return refusal + "; the lead is unchanged"
                team = teams.set_lead(me, name, member, "your user approved in the form")
                team_sync.publish(team)
                return "%s is the lead of team %s" % (teams.label(member), name)
        except teams.TeamError as exc:
            raise channel.ChannelError(str(exc))
        raise channel.ChannelError("unknown action %r" % action)

    def join(self, me: dict, args: dict) -> str:
        from . import config
        project, leaving = (args.get("project") or "").strip(), bool(args.get("leave"))
        root = config.project_root(me.get("cwd") or os.getcwd())
        verb = "leave" if leaving else "join"
        # What the agent runs instead, from this session's own folder: --dir is
        # taken only from a person at a terminal (issue #9).
        command = "xsm %s %s" % (verb, shlex.quote(project))
        if not leaving:
            try:
                config.check_join(project)      # before the consent is used up, as for link
            except ValueError as exc:
                raise channel.ChannelError(str(exc))
        if not consent.take(me, verb, project):       # the person typed /xsm join <project>
            ok, refusal = self.allowed(
                me, "%s@%s asks to let %s %s the xsm project %r.%s\nAllow it?" % (
                    me.get("name"), me.get("alias"), root, verb, project,
                    ("\nReason: " + args["reason"]) if args.get("reason") else ""), command,
                (verb, project))
            if not ok:
                return refusal + "; the folder's projects are unchanged"
        try:
            if leaving:
                changed = config.leave(project, me.get("cwd") or os.getcwd())
                return ("left %s" % project) if changed else "this folder was not in %s" % project
            scope, added = config.join(project, me.get("cwd") or os.getcwd())
        except ValueError as exc:
            raise channel.ChannelError(str(exc))
        others = [m["root"] for m in scope["members"] if os.path.realpath(m["root"]) != root]
        return "%s %s; other members: %s" % ("joined" if added else "already in", project,
                                             ", ".join(others) or "none yet")

    def reach(self, me: dict, args: dict) -> str:
        from . import config
        if not args.get("dir"):
            raise channel.ChannelError("dir: the folder to reach")
        # A relative dir is the session's, and the person's terminal may be
        # anywhere: the form, the command offered instead and the reach itself
        # all name the same absolute root. "../other" was quoted raw in the
        # command while the form showed the root (second review, 2026-09-28).
        folder = os.path.join(me.get("cwd") or os.getcwd(), os.path.expanduser(args["dir"]))
        root = config.project_root(folder)
        if args.get("drop"):
            return "dropped %d reach(es)" % config.drop_reach(me.get("ref"), root, session=me)
        command = "xsm reach %s --session %s" % (shlex.quote(root),
                                                 shlex.quote("ref:%s" % me.get("ref")))
        try:
            config.check_reach(root)            # before the consent is used up, as for link
        except ValueError as exc:
            raise channel.ChannelError(str(exc))
        if not consent.take(me, "reach", root):        # the person typed /xsm reach <dir>
            ok, refusal = self.allowed(
                me, "%s@%s (%s) asks to talk with the sessions in %s, both ways, until it ends.%s\n"
                "Allow it?" % (me.get("name"), me.get("alias"), me.get("ref"), root,
                               ("\nReason: " + args["reason"]) if args.get("reason") else ""),
                command, ("reach", root))
            if not ok:
                return refusal
        try:
            entry, added = config.add_reach(me.get("ref"), root,
                                            os.environ.get("USER") or "person", session=me)
        except ValueError as exc:
            raise channel.ChannelError(str(exc))
        return "%s: this session can now talk with the sessions in %s; run `xsm list` to see them" % (
            "allowed" if added else "already allowed", entry["root"])

    def approve(self, me: dict, args: dict) -> str:
        from . import workers
        mine = [r for r in workers.approvals()
                if (workers.load(r.get("worker") or "") or {}).get("parent_ref") == me.get("ref")]
        req = next((r for r in mine if r["id"] == args.get("id")), None) if args.get("id") \
            else (mine[0] if mine else None)
        if not req:
            return "no waiting request from your workers" + (
                " with id %s" % args["id"] if args.get("id") else "")
        command, key = "xsm approve %s" % shlex.quote(req["id"]), ("approve", req["id"])
        if "elicitation" not in (self.client_caps or {}):
            raise channel.ChannelError("this client cannot show a form. "
                                       + self.in_words(me, command, key))
        allow, deny = "allow", "deny"
        reply = self.ask_client("elicitation/create", {
            "message": "Worker %s is waiting for your permission:\n%s\nAllow it?"
                       % (req["worker"], req["summary"]),
            "requestedSchema": {"type": "object", "properties": {"answer": {
                "type": "string", "title": "Permission", "enum": [allow, deny]}},
                "required": ["answer"]}})
        answer, why = self.answer(reply, [allow, deny])
        if why == DECLINED:
            answer = deny               # they said no to the form: the request is answered
        if answer is None:
            return ("your user did not answer (%s); the request is still waiting and the worker "
                    "is blocked until it is answered. %s" % (why, self.in_words(me, command, key)))
        workers.answer_asked(req["id"], answer == allow, me.get("ref"),
                             None if answer == allow else "your user said no")
        return "%s: worker %s's request [%s] %s" % (
            "allowed" if answer == allow else "denied", req["worker"], req["id"], req["summary"])

    def grant(self, where: tuple, me: dict, args: dict) -> str:
        from . import config, workers
        options = sorted(set(o for o in (args.get("options") or []) if o in workers.DANGEROUS))
        if not options:
            raise channel.ChannelError("options must name full_access and/or trust_hooks")
        runtime = args.get("runtime")
        remote = isinstance(runtime, str) and runtime.startswith("remote:")
        # `xsm remote add` takes no --dir: it pairs the session's own folder, and
        # its grant is keyed by that folder, so `dir` cannot move a pairing.
        cwd = os.path.realpath(os.path.expanduser(
            (None if remote else args.get("dir")) or me.get("cwd") or os.getcwd()))
        reason = (args.get("reason") or "").strip() or "(no reason given)"
        words = {"remote": "PAIRING with another machine over SSH: sessions there in the paired "
                           "project can message this project",
                 "outside_scope": "a folder OUTSIDE this session's project: the worker will be "
                                  "able to talk to the sessions there (and to this session, "
                                  "which starts it)",
                 "full_access": "FULL ACCESS: no sandbox and no approval prompts",
                 "trust_hooks": "hooks run WITHOUT Codex's trust review, including any in that "
                                "folder"}
        question = ("%s@%s wants to start a %s worker in %s with %s.\nReason: %s\n"
                    "Allow it once?" % (me.get("name"), me.get("alias"), runtime, cwd,
                                        "; ".join(words[o] for o in options), reason))
        allow, deny = "allow once", "deny"
        reply = self.ask_client("elicitation/create", {
            "message": question, "requestedSchema": {"type": "object", "properties": {
                "answer": {"type": "string", "title": "Permission", "enum": [deny, allow]}},
                "required": ["answer"]}}) if "elicitation" in (self.client_caps or {}) else None
        # What the agent runs without --grant, and the ask that command finds.
        # workers.spawn adds outside_scope itself for a folder outside this
        # session's scope; the other options are the flags it was given.
        flags = [o for o in options if o in ("full_access", "trust_hooks")]
        if remote:
            command, asked = "xsm remote add %s --project <project>" % shlex.quote(runtime[7:]), \
                ["remote"]
        else:
            command = " ".join(["xsm spawn", str(runtime), "--dir", shlex.quote(cwd)]
                               + ["--" + o.replace("_", "-") for o in flags])
            asked = flags + ([] if config.scope_for(me, {"cwd": cwd})[0] else ["outside_scope"])
        key = ("grant", workers.grant_target(runtime, cwd, asked))
        if reply is None:
            raise channel.ChannelError("this client cannot show a form. "
                                       + self.in_words(me, command, key))
        answer, why = self.answer(reply, [deny, allow])
        if answer is None:
            # Nobody chose, so there is no decision to put on record.
            if why == DECLINED:
                return "%s; nothing was granted — do not start that worker" % unanswered(why)
            return ("%s; nothing was granted, so do not start that worker without their yes. %s"
                    % (unanswered(why), self.in_words(me, command, key)))
        author = {"kind": "human", "name": os.environ.get("USER") or "person",
                  "via": "mcp-elicitation", "asked_by": me.get("ref"), "runtime": me.get("runtime")}
        verdict = "allowed" if answer == allow else "refused"
        channel.post(where, author, "worker permission %s: %s %s in %s" % (
            verdict, runtime, "+".join(options), cwd), "decision",
            approved={"question": question, "answer": answer, "options": [deny, allow]})
        if answer != allow:
            if answer is not None:
                self._deny_current_decision()
            return "your user declined: they chose 'deny'; do not start that worker"
        g = workers.create_grant(me.get("ref"), runtime, cwd, options, answer)
        use = command if remote else "xsm spawn %s --dir %s %s" % (
            runtime, cwd, " ".join("--" + o.replace("_", "-") for o in options))
        return "granted %s: %s --grant %s   (one use, %d minutes)" % (
            g["id"], use, g["id"], workers.GRANT_TTL // 60)

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
                except (channel.ChannelError, EOFError) as exc:
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
                                     "started": time.time(), "cwd": os.getcwd()})


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
