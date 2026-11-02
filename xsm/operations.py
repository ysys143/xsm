"""Shared operation service, independent of MCP and host-protocol transport.

Hosts supply exact caller identity, user-interface callbacks and a wait pump.
Policy, human decisions, file preparation and canonical handoffs live here.
"""
from __future__ import annotations

import base64
import copy
import json
import math
import os
import shlex
import signal
import threading
import time
from . import consent, context, identity, paths, probe, registry, workers
from .instructions import HANDSHAKE_TEXT
from .operation_schema import ToolError, TOOLS, WIDENING, FILE_READING, DECLINED, unanswered, who_answered, person_answer, operation_returns_json, OperationDisplay


def invoke(host, name, arguments):
    return host._invoke_operation(name, arguments)


class OperationService:
    def initialize_service(self):
        self.client_caps = {}
        self.client_name = None
        self.call_thread = None
        self.ctx = None
        self.last_context = None
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

    def call(self, name, args):
        return invoke(self, name, args)

    def answer(self, reply, allowed):
        return person_answer(reply, allowed, self.client_name)

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
            consent.spend_recent(decision["me"])

    def _invoke_operation(self, name: str, args: dict) -> str:
        # The caller lookup shares one bounded budget. The tool's own lookups stay
        # out of it: a spent budget must not starve the git lookup that says which
        # scope a message belongs to.
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
            raise ToolError(why + (" (caller lookup: %s)" % evidence if evidence else ""))
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
                raise ToolError(why)
            from . import config
            config.require_valid_policy()
        if name in FILE_READING:
            why = context.require_sure(self.ctx, "read a file")
            if why:
                paths.append_jsonl("decisions.jsonl", {
                    "event": "mcp", "decision": "refused", "tool": name,
                    "reason": "caller not surely identified", "basis": self.ctx.basis,
                    "certainty": self.ctx.certainty, "ref": me.get("ref")})
                raise ToolError(why)
        if self.ctx.sure:
            registry.note_capabilities(me, {"files": {"version": 1, "status": "observed"}},
                                       reader_pid=os.getpid())
        form_tools = ("xsm_link", "xsm_join", "xsm_reach", "xsm_grant", "xsm_approve",
                      "xsm_decide", "xsm_doc_endorse", "xsm_team", "xsm_handover")
        decision_call = None
        inferred_team = False
        if name == "xsm_decide" and not args.get("team"):
            from . import teams
            names = sorted(t["name"] for t in teams.teams_of(me))
            own = [n for n in names if not (teams.load(n) or {}).get("pair")]
            names = own if own else names
            if len(names) > 1:
                raise ToolError("this session is in teams %s; pass team. Nothing was asked" % ", ".join(names))
            if names:
                args = dict(args, team=names[0])
                inferred_team = True
        resolved_handover = None
        if name in ("xsm_link", "xsm_reach", "xsm_grant") and args.get("dir"):
            directory = os.path.expanduser(args["dir"])
            if not os.path.isabs(directory):
                directory = os.path.join(me.get("cwd") or os.getcwd(), directory)
            args = dict(args, dir=os.path.realpath(directory))
        if name == "xsm_handover" and args.get("action") != "show" and args.get("target") and args.get("summary"):
            from . import resolve
            with probe.quick():
                selected = resolve.resolve(args["target"])
            if not selected.ok:
                raise ToolError(selected.reason)
            resolved_handover = selected.record
            args = dict(args, target="ref:" + resolved_handover["ref"])
        if name in form_tools:
            if not me.get("ref"):
                raise ToolError("this session is not registered for user decisions; use a registered foreground session")
            from . import decisions
            generation = self.ctx.generation or {"server": self.instance_id}
            scope = {"tool": name, "arguments": {k: v for k, v in args.items()
                     if k not in ("answer_request", "original_question", "notify")}, "cwd": os.path.realpath(me["cwd"]) if me.get("cwd") else None}
            resource = {k: resolved_handover.get(k) for k in ("runtime", "home", "session_id", "machine")} if resolved_handover else None
            if resource:
                scope["resource"] = resource
            key = decisions.invocation(me, name, args, generation, resource=resource)
            prior = decisions.read(key)
            if not prior:
                legacy = decisions.digest({"owner": decisions.owner(me), "tool": name,
                    "scope": {k: v for k, v in args.items() if k not in ("answer_request", "original_question", "notify")},
                    "generation": generation})
                old = decisions.read(legacy)
                if old and old["owner"] == decisions.owner(me) and old["scope_digest"] == decisions.digest(scope):
                    key, prior = legacy, old
            if prior and prior["status"] == "applied":
                return prior["application"]["result"]
            if prior and (prior.get("application") or {}).get("phase") == "started":
                raise ToolError("outcome unknown or still applying; inspect xsm_decision_status and domain state before retrying; no operation repeated")
            decision_call = {"key": key, "me": copy.deepcopy(me), "scope": scope, "generation": generation,
                             "notify": args.get("notify") is True,
                             "native_request": args.get("answer_request"),
                             "native_question": args.get("original_question"), "team_inferred": inferred_team,
                             "resolved_handover": resolved_handover}
            self.decision_calls[self.active_request] = decision_call
        try:
            text = self._call(name, args, me)
            producer_metadata = text.metadata if isinstance(text, OperationDisplay) else None
            if decision_call:
                record = decisions.read(decision_call["key"])
                if record and (record["status"] == "answered" or (record.get("application") or {}).get("phase") == "started"):
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
                # the unrelated tool operation already performed.
                incoming = {"messages": [], "claims": []}
            else:
                incoming = receive.take_inbox_claims(me, owner=owner, generation=generation, passive_only=True)
            if incoming["claims"]:
                self.handoff_calls.setdefault(self.active_request, []).append((me, incoming, owner, generation))
        if operation_returns_json(name, args):
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
        return OperationDisplay(text, producer_metadata) if producer_metadata is not None else text

    def _call(self, name: str, args: dict, me: dict) -> str:
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
                raise ToolError("encoding must be text or base64")
            try:
                content = base64.b64encode(data).decode("ascii") if encoding == "base64" else data.decode("utf-8")
            except UnicodeError as exc:
                raise ToolError("binary copy: request encoding=base64") from exc
            return json.dumps({"storage_id": storage, "entry_id": entry, "encoding": encoding, "content": content}, ensure_ascii=False)
        if name == "xsm_decision_status":
            from . import decisions
            if args.get("pending_consent"):
                if args.get("id") or args.get("cancel"):
                    raise ToolError("pending_consent is read-only; omit id and cancel")
                return json.dumps(consent.pending_status(me), ensure_ascii=False)
            if args.get("drop_consent"):
                if not consent.drop_request(me, args["drop_consent"]):
                    raise ToolError("no open request %s in this conversation" % args["drop_consent"])
                return json.dumps({"closed": args["drop_consent"]}, ensure_ascii=False)
            return json.dumps(decisions.public_status(me, args.get("id"), args.get("cancel", False)), ensure_ascii=False)
        if name in ("xsm_connect", "xsm_publish") and args.get("answer_request"):
            if not args.get("original_question"):
                raise ToolError("answer_request requires original_question")
            consent.answer_request = args["answer_request"]
            consent.question_text = args["original_question"]
        if name == "xsm_publish":
            from . import connect
            visible = args.get("visible", True)
            if not isinstance(visible, bool):
                raise ToolError("visible must be a boolean")
            return json.dumps(connect.publication(me, visible=visible, call=self.ctx), ensure_ascii=False)
        if name == "xsm_discover":
            from . import directory
            return json.dumps(directory.discover(me, machine=args.get("machine"),
                              work=args.get("work"), branch=args.get("branch")), ensure_ascii=False)
        if name in ("xsm_ask", "xsm_question_status", "xsm_connect"):
            from . import question_service, question_groups, materials, files, receive, inbox
            requested_wait = float(args.get("wait", 0) or 0)
            if not math.isfinite(requested_wait) or requested_wait < 0:
                raise ToolError("wait must be finite and nonnegative")
            wait = min(requested_wait, 60.0)
            if args.get("wake", "auto") not in ("auto", "never"):
                raise ToolError("unsupported wake mode; use auto or never")
            owner = self.active_request
            def pump_factory(request_id):
                last_scan = [float("-inf")]
                def pump():
                    live = self.pump()
                    now = time.monotonic()
                    if now - last_scan[0] >= .2:
                        last_scan[0] = now
                        receive.poll_replies(me, request_id)
                    return live
                return pump
            common = {"wait": wait, "pump": self.pump, "pump_factory": pump_factory,
                      "cancelled": lambda: owner in self.cancelled}
            poll = lambda child: receive.poll_replies(me, child)
            try:
                if name == "xsm_ask":
                    value = question_service.ask(me, args, call=self.ctx, poll=poll, **common)
                elif name == "xsm_connect":
                    value = question_service.connect(me, args, call=self.ctx, **common)
                else:
                    value = question_service.status(me, args.get("id"), poll=poll, **common)
            except files.FileError as exc:
                from .provenance import readable
                failure = materials.failure(exc)
                raise ToolError(readable(failure), data={"attachment_error": failure}) from exc
            except (question_service.QuestionError, question_groups.GroupError) as exc:
                raise ToolError(str(exc)) from exc
            result = value["result"]
            if value["grouped"]:
                result = question_groups.with_claims(me, result)
                result.update(inbox.pending_fields(me, owner_alive=receive._consumer_alive))
            if value["wait_applies"]:
                result["wait_budget"] = {"requested": requested_wait, "effective": wait, "cap": 60}
            return json.dumps(result, ensure_ascii=False)
        if name == "xsm_decide":
            return self.decide(me, args)
        if name == "xsm_grant":
            return self.grant(me, args)
        if name == "xsm_approve":
            return self.approve(me, args)
        if name == "xsm_join":
            return self.join(me, args)
        if name == "xsm_reach":
            return self.reach(me, args)
        if name == "xsm_link":
            return self.link(me, args)
        if name == "xsm_send":
            from . import send_service, materials, files, multisend
            try:
                value = send_service.execute(args, caller=me, call=self.ctx)
            except files.FileError as exc:
                from .provenance import readable
                failure = materials.failure(exc)
                raise ToolError(readable(failure), data={"attachment_error": failure}) from exc
            except (send_service.SendError, multisend.MultiError) as exc:
                raise ToolError(str(exc)) from exc
            text = "\n".join(value["result"].lines())
            metadata = {"send": value["result"].as_dict(), "grouped": value["grouped"]}
            if value["materials"]:
                metadata["materials"] = materials.public(value["materials"])
                text += "\nMaterials: " + json.dumps(metadata["materials"], ensure_ascii=False)
            return OperationDisplay(text, metadata)
        if name == "xsm_doc_endorse":
            return self.endorse(me, args)
        if name == "xsm_team":
            return self.team(me, args)
        if name == "xsm_handover":
            return self.handover(me, args)
        if name == "xsm_board":
            from . import board, board_service, teams
            try:
                result = board_service.execute(me, args)
            except (board.BoardError, teams.TeamError) as exc:
                raise ToolError(str(exc))
            action = result["action"]
            if action == "show":
                return result["text"]
            if action == "log":
                return json.dumps({"nodes": result["nodes"]}, ensure_ascii=False)
            if action == "decisions":
                return json.dumps({"decisions": result["decisions"]}, ensure_ascii=False)
            if action == "set":
                return "\n".join(["set %s (node %s)" % (args.get("item"), result["node"]["id"])] + result["sync_notes"])
            if action == "sync":
                return "\n".join(result["sync_notes"]) if result["sync_notes"] else \
                    "sent every node of %s's board to its other machines" % result["team"]["name"]
            return "%sd board %s's change lines for this session" % (action, result["team"]["name"])
        if name == "xsm_ack":
            from . import receive
            tokens = args.get("tokens")
            if not isinstance(tokens, list) or not tokens or not all(isinstance(t, (str, dict)) for t in tokens):
                raise ToolError("tokens must be a nonempty array of claim tokens "
                                           "(the token values, or the claim objects as shown)")
            owner, generation = receive.consumer_for(me)
            return json.dumps(receive.ack_inbox(me, tokens, owner=owner, generation=generation))
        if name == "xsm_inbox":
            from . import inbox, receive
            limit = args.get("limit")
            if "limit" in args and (type(limit) is not int or not 1 <= limit <= 100):
                raise ToolError('inbox limit must be an integer from 1 to 100')
            max_bytes = args.get('max_bytes')
            if 'max_bytes' in args and (type(max_bytes) is not int or not 1 <= max_bytes <= 1048576):
                raise ToolError('inbox max_bytes must be an integer from 1 to 1048576')
            after_id = args.get('after_id')
            if 'after_id' in args:
                from . import handoff
                try:
                    handoff._id(after_id)
                except ValueError as error:
                    raise ToolError(str(error))
            message_ids = args.get('message_ids')
            if 'message_ids' in args:
                from . import handoff
                if not isinstance(message_ids, list) or not 1 <= len(message_ids) <= 100:
                    raise ToolError('message_ids must be an array of 1 to 100 message IDs')
                try:
                    for mid in message_ids:
                        handoff._id(mid)
                except ValueError as error:
                    raise ToolError(str(error))
            wait = float(args.get("wait") or 0)
            if not math.isfinite(wait) or wait < 0:
                raise ToolError('wait must be finite and nonnegative')
            call_owner = self.active_request
            if wait > 0:
                # Shorter than the shell's cap: serve() reads one request at a
                # time, so a long block looks to the client like a dead server.
                inbox.wait_for(me.get("session_id"), min(wait, inbox.MCP_MAX_WAIT),
                    counter=lambda: inbox.pending_fields(me, owner_alive=receive._consumer_alive)['inbox_pending'],
                    pump=self.pump if call_owner is not None else None,
                    cancelled=lambda: call_owner in self.cancelled)
                if call_owner in self.cancelled or (call_owner is not None and self._closed):
                    raise ToolError('inbox wait cancelled or input closed; original retained')
            owner, generation = receive.consumer_for(me)
            try:
                pack = receive.take_inbox_claims(me, owner=owner, generation=generation, limit=limit,
                    max_bytes=max_bytes, after_id=after_id, message_ids=message_ids)
            except ValueError as error:
                raise ToolError(str(error))
            if pack["claims"]:
                self.handoff_calls.setdefault(self.active_request, []).append((me, pack, owner, generation))
            return json.dumps(pack, ensure_ascii=False)
        # A client that loaded its tool list from a newer xsm than this server
        # (the server reads TOOLS once, at its start) names a tool it lacks.
        raise ToolError(
            "unknown tool %s: this xsm server started before xsm was updated. Reconnect it (Claude "
            "Code: /mcp, then xsm) or start a new session; meanwhile run the same `xsm` command "
            "in the shell" % name)

    def owned(self,me,args):
        from . import workers,owned_requests,envelope,decisions
        action,name=args.get("action"),args.get("name")
        if not isinstance(name,str) or not name:
            raise ToolError("owned worker name required")
        if action=="create":
            return workers.create_owned(args.get("runtime"),caller=me,name=name,cwd=args.get("dir"),
                home=args.get("home"),model=args.get("model"),effort=args.get("effort"),grant=args.get("grant"))
        if action=="status":
            if args.get("request_id"):
                return workers.owned_status(name,me,args["request_id"])
            return {"status":"requests","requests":workers.owned_history(name,me)}
        if action in ("retry","reconcile"):
            if not args.get("request_id"):
                raise ToolError("request_id required for reply recovery")
            fn=workers.resend_owned if action=="retry" else workers.reconcile_owned
            return fn(name,me,args["request_id"])
        if action!="run":
            raise ToolError("unknown owned action")
        wait=float(args.get("wait",0) or 0)
        if not math.isfinite(wait) or wait<0:
            raise ToolError("wait must be finite and nonnegative")
        wait=min(wait,60)
        request_id=args.get("request_id") or envelope.new_id()
        from . import handoff
        handoff._id(request_id)
        arguments={"work_context":args.get("work_context"),"request_id":request_id,
                   "independent":args.get("independent",False)}
        try:
            verified=workers.submit_owned(name,me,args.get('text') or '',**arguments)
        except (workers.WorkerError,owned_requests.OwnedError) as exc:
            raise ToolError(str(exc)) from exc
        fingerprint=verified['digest']
        key=(me.get("runtime"),me.get("home"),me.get("session_id"),self.ctx.generation,
             verified['worker']['id'],request_id)
        job=self.owned_jobs.get(key)
        if job is not None and job["fingerprint"]!=fingerprint:
            raise ToolError("request_id differs in body, work context or sender")
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
                raise ToolError(str(job["error"]))
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

    def permission_closed(self):
        from . import decisions
        call = self.decision_calls.get(self.active_request)
        record = decisions.read(call["key"]) if call else None
        if record and (record["status"] in decisions.TERMINAL or
                       (record.get("application") or {}).get("phase") == "started" or
                       time.time() > record["expires_at"]):
            return "decision closed, expired or outcome unknown; inspect xsm_decision_status; a renewed user request needs a new decision_key"
        if record and record.get("answer") and self.answer(record["answer"]["reply"], record.get("choices"))[1] == DECLINED:
            return "your user declined; do not work around it"
        return None

    def permission_started(self, receipt):
        from . import decisions
        call = self.decision_calls.get(self.active_request)
        if call:
            if not decisions.read(call["key"]):
                decisions.begin(call["key"], call["me"], call["scope"], call["generation"], "", waiter=self.active_request)
            decisions.start_application(call["key"], call["generation"], call["scope"], receipt=receipt, reader=self.reader_identity)
            call["permission_receipt"] = receipt

    def refuse_unattended(self, me, what):
        """No form for a session nobody answers: the question goes up in a DM. Only what
        would ask the person: a worker still lists its teams and leaves one."""
        worker = consent.unattended(me)
        if worker:
            raise ToolError(consent.no_person(what, worker))

    def typed_permission(self, me, *key):
        """A command the person typed is a new yes, whatever became of an earlier ask
        for the same thing (a denied form), so it comes before that ask's state."""
        if consent.take(me, *key):
            if not self.permission_closed():
                self.permission_started({"source": "typed-command", "verb": key[0], "target": key[1]})
            return True
        closed = self.permission_closed()
        if closed:
            raise ToolError(closed)
        return False

    def permission_reply(self, me, key, question):
        call = self.decision_calls.get(self.active_request)
        if call and call.get("native_request"):
            return None  # explicit form recovery must validate its exact scoped question
        if key and self.typed_permission(me, *key):
            return True
        closed = self.permission_closed()
        if closed:
            raise ToolError(closed)
        if not key:
            return None
        binding = {"mcp_decision": call["key"]} if call else None
        verdict, go, kept = consent.take_or_request(me, *key, binding=binding)
        if call:
            call["permission_key"], call["permission_kept"] = key, bool(kept)
        if verdict is None:
            return None
        if not go:
            raise ToolError(consent.shown_refusal(verdict, question, kept))
        self.permission_started({"source": "input-consent", "text": verdict,
                                 "via": consent.used_via, "binding_note": kept if isinstance(kept, str) else None})
        return True

    def permission_form(self, me, command, key, params, accept):
        from . import decisions
        self.refuse_unattended(me, command)
        call = self.decision_calls.get(self.active_request)
        record = decisions.read(call["key"]) if call else None
        if record and record["question"] and record["question"] != params["message"]:
            raise ToolError("question or resolved target changed; inspect status and renew the user request")
        if self.permission_reply(me, key, params["message"]):
            return accept, "input-consent"
        reply = self.ask_client("elicitation/create", params)
        call = self.decision_calls.get(self.active_request) or {}
        if "elicitation" not in (self.client_caps or {}) and not call.get("native_request"):
            raise ToolError("this client cannot show a form. " + self.in_words(me, command, key))
        choices = params["requestedSchema"]["properties"]["answer"].get("enum")
        return self.answer(reply, choices)

    def clear_permission(self, me, key):
        call = self.decision_calls.get(self.active_request)
        if call:
            consent.cancel_bound_requests(me, call["key"])
        else:
            consent.clear_request(me, *key)

    def permission_words(self, fallback):
        call = self.decision_calls.get(self.active_request) or {}
        return (call.get("permission_receipt") or {}).get("text", fallback)

    def answer_source(self):
        from . import decisions
        call = self.decision_calls.get(self.active_request)
        receipt = (call or {}).get("permission_receipt")
        if receipt:
            return "agent-supplied" if receipt.get("via") == "flag" else receipt["source"]
        record = decisions.read(call["key"]) if call else None
        source = ((record or {}).get("answer") or {}).get("source")
        return source if source in ("native-user", "host-user") else "mcp-elicitation"

    def decide(self, me: dict, args: dict) -> str:
        self.refuse_unattended(me, "Recording a decision")
        # Where the answer is kept is settled before the form: a session in
        # several teams must not be asked for an answer xsm then cannot place.
        team, inferred = (args.get("team") or "").strip() or None, bool((self.decision_calls.get(self.active_request) or {}).get("team_inferred"))
        if not team:
            from . import teams
            mine = sorted(t["name"] for t in teams.teams_of(me))
            # A connect pair is a team of two (T4); a session with one team of
            # its own besides its pairs means that team.
            own = [n for n in mine if not (teams.load(n) or {}).get("pair")]
            mine = own if own else mine
            if len(mine) > 1:
                raise ToolError("this session is in teams %s; pass team to say beside which "
                                "board the decision is recorded. Nothing was asked"
                                % ", ".join(mine))
            team, inferred = (mine[0], True) if mine else (None, False)
        item = (args.get("item") or "").strip() or None
        if team:
            # A named team the caller is not in, or an item name the board
            # refuses, is refused before your user answers, not after.
            from . import board, doc
            try:
                board._require_member(me, team)
            except board.BoardError as exc:
                raise ToolError("%s. Nothing was asked" % exc)
            if item and not doc.ITEM_RE.match(item):
                raise ToolError("item: a short name (letters, digits, spaces, . _ / : -), e.g. "
                                "'decision: cache'. Nothing was asked")
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
                                                   ". Your answer cannot be recorded as a decision from here without a verified reply. "
                                                   "Ask them in plain words or a supported native question tool. "
                                                   "No team decision was recorded. Inspect xsm_decision_status. "
                                                   "Recover a verified native question answer with answer_request "
                                                   "and original_question; do not repeat the unanswered form")
        if not team:
            # The answer is the person's and goes back to the agent; the record
            # lives beside a team's board, and there is none (T11).
            return ("your user answered: %s\nIt is not recorded as a decision: this session is in "
                    "no team, and a decision is kept beside a team's board (`xsm team create "
                    "<name>` makes one)." % answer)
        summary = (args.get("summary") or "").strip()
        from . import board
        try:
            rec = board.record_decision(me, team, question, answer, via=self.answer_source(),
                                        options=options or None, item=item, summary=summary or None,
                                        asked_question=args.get("original_question") if self.answer_source() == "native-user" else None)
        except board.BoardError as exc:
            raise ToolError("%s; the answer was %r and is not recorded" % (exc, answer))
        return "\n".join(["recorded decision %s beside team %s's board%s: %s%s" % (
            rec["id"], team, " (the one team this session is in)" if inferred else "", answer,
            " (item %s set)" % item if rec.get("node") else "")]
            + (rec.get("sync_notes") or []))

    def endorse(self, me: dict, args: dict) -> str:
        from . import doc
        path = args.get("doc") or ""
        if not os.path.isabs(path):
            path = os.path.join(me.get("cwd") or os.getcwd(), path)
        node = next((n for n in doc.read(path) if n["id"] == args.get("node")), None)
        if not node:
            raise ToolError("no node %s in %s" % (args.get("node"), path))
        # The command is the node's own text, so the ask recorded for it here is
        # the one that command finds (consent.digest as the CLI keys it).
        command = "xsm doc add %s --tag endorsed --parent %s --text %s" % (
            shlex.quote(args.get("doc") or ""), shlex.quote(node["id"]), shlex.quote(node["body"]))
        key = ("endorse", consent.digest(args.get("doc"), node["body"], [node["id"]]))
        preview = node["body"] if len(node["body"]) < 1500 else node["body"][:1500] + " …"
        answer, why = self.permission_form(me, command, key, {
            "message": "Endorse this node of %s as the document's text?\n[%s] by %s\n\n%s" % (
                os.path.basename(path), ", ".join(node["tags"]), node["author"], preview),
            "requestedSchema": {"type": "object", "properties": {"answer": {
                "type": "string", "title": "Endorse", "enum": ["endorse", "not now"]}},
                "required": ["answer"]}}, accept="endorse")
        if answer != "endorse":
            if answer is not None:
                self.clear_permission(me, key)
                self._deny_current_decision()
            return "your user did not endorse it (%s); nothing was added%s" % (
                why, ". " + self.in_words(me, command, key) if answer is None and why != DECLINED
                else "")
        self.clear_permission(me, key)
        author = {"kind": "human", "name": os.environ.get("USER") or "person",
                  "via": self.answer_source()}
        new = doc.add(path, author, node["body"], ["endorsed"], [node["id"]],
                      approved="asked by %s" % me.get("ref"))
        return "endorsed: node %s now carries %s; run `xsm doc render %s`" % (
            new["id"], node["id"], args.get("doc"))

    def in_words(self, me: dict, command: str, key: tuple | None = None) -> str:
        """Describe the retained request and same-MCP reply recovery.
        Legacy callers without a decision controller use consent.in_words.
        """
        worker = consent.unattended(me)
        if worker:
            return consent.no_person(command, worker)
        call = self.decision_calls.get(self.active_request)
        if call and key == call.get("permission_key"):
            if not call.get("permission_kept"):
                return ("the input reply cannot be retained here; nothing was approved. Inspect "
                        "xsm_decision_status id %s for a supported verified-native recovery path, "
                        "or use a registered user-facing foreground session. Do not bounce between "
                        "shell and MCP." % call["key"])
            return ("Ask your user now, %s. %s After their answer, retry this same MCP "
                    "tool to read the reply, then once more only on a yes; do not switch to a sandboxed shell. "
                    "For verified form recovery instead, inspect xsm_decision_status id %s and copy "
                    "native_question and choices exactly, without adding a CLI marker; then pass "
                    "answer_request and original_question. Shell equivalent: `%s`." %
                    (consent.how(me.get("runtime")), consent.ask_hint(), call["key"], command))
        return consent.in_words(command, bool(key) and consent.ask(me, *key), me.get("runtime"))

    def allowed(self, me: dict, question: str, command: str, key: tuple | None = None) -> tuple:
        """Ask the person allow/deny. Returns (True, None) on their allow, else
        (False, what to tell the agent). If the form cannot show, the same
        controller retains the input request or verifies native evidence;
        the agent performs the operation after the user's answer.
        """
        answer, why = self.permission_form(me, command, key, {"message": question,
            "requestedSchema": {"type": "object", "properties": {"answer": {
                "type": "string", "title": "Permission", "enum": ["allow", "deny"]}},
                "required": ["answer"]}}, accept="allow")
        if answer == "allow":
            if key:
                self.clear_permission(me, key)
            return True, None
        if answer == "deny":
            if key:
                self.clear_permission(me, key)
            self._deny_current_decision()
            return False, "your user declined: they chose 'deny'; do not work around it"
        if why == DECLINED:
            if key:
                self.clear_permission(me, key)
            self._deny_current_decision()
            return False, unanswered(why)
        return False, "your user did not answer (%s). %s" % (why, self.in_words(me, command, key))

    def link(self, me: dict, args: dict) -> str:
        from . import config
        if not args.get("dir"):
            raise ToolError("dir: the folder to link with")
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
            raise ToolError(str(exc))
        if not self.typed_permission(me, "link", other, here):
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
            raise ToolError(str(exc))
        return ("%s: the sessions in %s and %s can talk, both ways, until unlinked; run `xsm list` "
                "to see them" % ("linked" if added else "already linked", root, other))

    def handover(self, me: dict, args: dict) -> str:
        """xsm_handover: the same as `xsm handover`; the user confirms in a form."""
        from . import handover, resolve
        if args.get("action") == "show":
            rows = handover.received(me)
            return "\n\n".join(r["letter"] for r in rows) if rows else \
                "no session handed its place over to this one"
        word = (args.get("target") or "").strip()
        summary = (args.get("summary") or "").strip()
        if not word or not summary:
            raise ToolError("target (the session that takes over) and summary (what it "
                                       "needs to continue) are both required")
        target = (self.decision_calls.get(self.active_request) or {}).get("resolved_handover")
        if target is None:
            with probe.quick():
                found = resolve.resolve(word)
            if not found.ok:
                raise ToolError(found.reason)
            target = found.record
        try:
            handover._check(me, target)
            ok, refusal = self.allowed(
                me, "%s@%s asks to hand its xsm place over to %s: its teams and lead's seat, its "
                "board items, unread DMs and pending questions move there, and DMs to it reach "
                "that session from now on.\nAllow it?" % (me.get("name"), me.get("alias"),
                                                          handover.label(target)),
                "xsm handover %s --summary-file <file>" % shlex.quote(word),
                ("handover", target.get("name") or word))
            if not ok:
                return refusal + "; nothing moved"
            rec = handover.hand_over(me, target, summary, "your user approved in the form")
        except handover.HandoverError as exc:
            raise ToolError(str(exc))
        return "\n".join([handover.summary_line(rec)] + (rec.get("notes") or []))

    def team(self, me: dict, args: dict) -> str:
        from . import team_service, teams
        action = args.get("action")
        name = (args.get("team") or "").strip()
        word = (args.get("member") or "").strip()
        reason = ("\nReason: " + args["reason"]) if args.get("reason") else ""
        def authorize(action, team, subject):
            member = teams.member_of(subject) if action == "add" else subject
            label = teams.label(member)
            if action == "add":
                question = "%s@%s asks to add %s to team %s, so the team's members and it can DM each other.%s\nAllow it?" % (
                    me.get("name"), me.get("alias"), label, name, reason)
                key = ("team-add-" + name, subject.get("name") or word)
            elif action == "remove":
                question = "%s@%s asks to remove %s from team %s.%s\nAllow it?" % (
                    me.get("name"), me.get("alias"), label, name, reason)
                key = ("team-remove-" + name, member.get("name") or word)
            else:
                question = "%s@%s asks to make %s the lead of team %s: the session that faces you, takes your approvals and adds or removes this project's sessions.%s\nAllow it?" % (
                    me.get("name"), me.get("alias"), label, name, reason)
                key = ("team-lead-" + name, member.get("name") or word)
            ok, refusal = self.allowed(me, question,
                "xsm team %s %s %s" % (action, shlex.quote(name), shlex.quote(word)), key)
            if not ok:
                raise team_service.DecisionRefused(refusal + ("; the lead is unchanged" if action == "lead" else "; the team is unchanged"))
            return "your user approved in the form"
        try:
            result = team_service.execute(me, args, authorize=authorize)
        except team_service.DecisionRefused as exc:
            return str(exc)
        except teams.TeamError as exc:
            raise ToolError(str(exc))
        if action == "list":
            return json.dumps({"teams": [{"name": t["name"], "lead": teams.label(t["lead"]) if t.get("lead") else None,
                "members": [teams.label(m) for m in t["members"]]} for t in result["teams"]]}, ensure_ascii=False)
        team = result["team"]
        if action == "show":
            return json.dumps({"name": team["name"], "lead": teams.label(team["lead"]) if team.get("lead") else None,
                "members": [{"member": teams.label(m), "running": teams.address(m) is not None} for m in team["members"]]}, ensure_ascii=False)
        if action == "create":
            return "created team %s with %s" % (team["name"], teams.label(team["members"][0]))
        if action in ("mute", "unmute"):
            return "%sd team %s's DMs for this session" % (action, team["name"])
        if action == "leave":
            return "left team %s" % team["name"]
        member = teams.label(result["member"])
        if action == "add":
            return "\n".join(["added %s to team %s" % (member, name)] + result["sync_notes"])
        if action == "remove":
            return "removed %s from team %s" % (member, name)
        return "%s is the lead of team %s" % (member, name)

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
                raise ToolError(str(exc))
        if not self.typed_permission(me, verb, project):       # the person typed /xsm join <project>
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
            raise ToolError(str(exc))
        others = [m["root"] for m in scope["members"] if os.path.realpath(m["root"]) != root]
        return "%s %s; other members: %s" % ("joined" if added else "already in", project,
                                             ", ".join(others) or "none yet")

    def reach(self, me: dict, args: dict) -> str:
        from . import config
        if not args.get("dir"):
            raise ToolError("dir: the folder to reach")
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
            raise ToolError(str(exc))
        if not self.typed_permission(me, "reach", root):        # the person typed /xsm reach <dir>
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
            raise ToolError(str(exc))
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
        allow, deny = "allow", "deny"
        answer, why = self.permission_form(me, command, key, {
            "message": "Worker %s is waiting for your permission:\n%s\nAllow it?"
                       % (req["worker"], req["summary"]),
            "requestedSchema": {"type": "object", "properties": {"answer": {
                "type": "string", "title": "Permission", "enum": [allow, deny]}},
                "required": ["answer"]}}, accept=allow)
        if why == DECLINED:
            answer = deny               # they said no to the form: the request is answered
        if answer is None:
            return ("your user did not answer (%s); the request is still waiting and the worker "
                    "is blocked until it is answered. %s" % (why, self.in_words(me, command, key)))
        self.clear_permission(me, key)
        workers.answer_asked(req["id"], answer == allow, me.get("ref"),
                             None if answer == allow else "your user said no", via=self.answer_source())
        return "%s: worker %s's request [%s] %s" % (
            "allowed" if answer == allow else "denied", req["worker"], req["id"], req["summary"])

    def grant(self, me: dict, args: dict) -> str:
        from . import config, workers
        options = sorted(set(o for o in (args.get("options") or []) if o in workers.DANGEROUS))
        if not options:
            raise ToolError("options must name full_access and/or trust_hooks")
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
        answer, why = self.permission_form(me, command, key, {
            "message": question, "requestedSchema": {"type": "object", "properties": {
                "answer": {"type": "string", "title": "Permission", "enum": [deny, allow]}},
                "required": ["answer"]}}, accept=allow)
        if answer is None:
            # Nobody chose, so there is no decision to put on record.
            if why == DECLINED:
                consent.cancel_bound_requests(me, (self.decision_calls.get(self.active_request) or {}).get("key"))
                self._deny_current_decision()
                return "%s; nothing was granted — do not start that worker" % unanswered(why)
            return ("%s; nothing was granted, so do not start that worker without their yes. %s"
                    % (unanswered(why), self.in_words(me, command, key)))
        # The answer is on record already: the form's human-decisions record holds
        # the question, the choices, the answer and who asked (decisions.py).
        self.clear_permission(me, key)
        if answer != allow:
            if answer is not None:
                self._deny_current_decision()
            return "your user declined: they chose 'deny'; do not start that worker"
        g = workers.create_grant(me.get("ref"), runtime, cwd, options, self.permission_words(answer))
        use = command if remote else "xsm spawn %s --dir %s %s" % (
            runtime, cwd, " ".join("--" + o.replace("_", "-") for o in options))
        return "granted %s: %s --grant %s   (one use, %d minutes)" % (
            g["id"], use, g["id"], workers.GRANT_TTL // 60)
