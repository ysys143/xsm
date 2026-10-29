"""The send side.

Everything the receiver will check is checked here first — scope, liveness,
registration — so a refusal is immediate and local instead of a message that
vanishes on the far side. The S8 prototype skipped these checks and happily
"sent" to a session that had been killed, or after the policy had changed
underneath it.

What this does not do is claim delivery. The result is `sent-unconfirmed`
until the receiving hook writes a receipt.
"""
from __future__ import annotations

import os
from contextlib import nullcontext

from . import adapters, config, context, envelope, inbox, ledger, outbox, paths, probe, registry, \
    resolve


PRIORITY_CAPABILITIES = {"claude": ["next", "now"], "codex": ["next"]}


def priority_refusal(target, priority):
    if priority not in ("next", "now"):
        return "unsupported priority; use next or now"
    if priority not in PRIORITY_CAPABILITIES.get(target.get("runtime"), ["next"]):
        return ("unsupported: this target exposes queued next delivery, not per-message now "
                "interruption; its existing wake policy still applies")
    return None


class SendResult:
    def __init__(self, status: str, reason: str = "", msg_id: str | None = None,
                 target: dict | None = None, candidates=None):
        self.status = status          # delivered | sent-unconfirmed | held | refused | error
        self.reason = reason
        self.msg_id = msg_id
        self.target = target
        self.candidates = candidates or []
        self.notes = []               # what a one-yes send did before it sent (connect.py)
        self.evidence = None          # delivery steps actually observed (ledger.evidence_of)

    def as_dict(self) -> dict:
        out = {"status": self.status, "reason": self.reason, "id": self.msg_id}
        if self.notes:
            out["notes"] = list(self.notes)
        if self.target:
            out["to"] = "%s@%s" % (self.target.get("name"), self.target.get("alias"))
        if self.candidates:
            out["candidates"] = ["%s@%s [%s]" % (c.get("name"), c.get("alias"), c.get("ref"))
                                 for c in self.candidates]
        if self.evidence:
            # The axes beside the legacy `status`: which trips actually happened,
            # and whether the receiver's own side is what says it arrived.
            out["runtime_reached"] = self.evidence.get("runtime_reached")
            out["evidence"] = {k: v.get("ok") for k, v in (self.evidence.get("steps") or {}).items()}
        return out

    def lines(self) -> list:
        """What the CLI prints and the MCP tool returns: the notes of a one-yes
        send, the status and reason, and the candidates when naming them helps
        the caller find the right one."""
        head = "%s: %s" % (self.status, self.reason or self.msg_id or "")
        if self.reason and self.msg_id and self.status != "refused":
            # `--resend <id>` needs the id, and a send that went out printed only its
            # reason ("queued; ..."). A refusal's text says what to do, and some name
            # the id of the message they kept themselves.
            head += " (id %s)" % self.msg_id
        out = list(self.notes) + [head]
        if self.candidates and "resume it with" not in (self.reason or "") \
                and "has not registered" not in (self.reason or ""):
            out.append("registered sessions right now:" if "no session" in (self.reason or "")
                       else "candidates:")
            out.append(resolve.describe(self.candidates))
        return out


# A held message has left once the receiving side has taken it, even to hold it.
LEFT = ("delivered", "sent-unconfirmed", "held", "blocked", "stored")


def send(target_spec: str, body: str, *, sender: dict | None = None, kind: str = "note",
         reply_to: str | None = None, priority: str = "next", wait: float = 0.0,
         msg_id: str | None = None, outcome: str | None = None,
         resend: bool = False, held: str | None = None, call=None, wake: bool = True,
         attachments=None, file_packet=None, file_limits=None) -> SendResult:
    """One span around the whole attempt, refusals included.

    A refusal is as worth timing as a delivery: "out of scope" and "target has
    no inbox socket" are the two things a caller actually hits, and neither
    shows up in a log that only records what succeeded.

    `held` is the id of a message a refused send kept (outbox.py): it is sent
    as it was kept, and the target, text and kind arguments are not read.
    wake=False is strict local FYI: canonical storage only, without any native
    delivery export/queue/socket/wake. It is consumed at a natural boundary.
    """
    try:
        from . import telemetry
    except ImportError:
        telemetry = None
    span_cm = telemetry.span("xsm.send", {"xsm.msg.kind": kind},
                             kind="PRODUCER") if telemetry else nullcontext()
    with span_cm as span:
        ctx = {"notes": [], "held": None}
        try:
            result = _send(target_spec, body, sender=sender, kind=kind, reply_to=reply_to,
                           priority=priority, wait=wait, msg_id=msg_id, outcome=outcome,
                           resend=resend, span=span, held=held, ctx=ctx, call=call, wake=wake,
                           attachments=attachments, file_packet=file_packet, file_limits=file_limits)
        except OSError as err:
            # A sandboxed or read-only shell cannot write the ledger, and the send
            # crashed with a traceback (found in the audit of 2026-10-01). The
            # ledger is written before anything is delivered, so this is a send
            # that did not go; say what to do instead.
            if not paths.blocked_write(err):
                raise
            result = SendResult("error", paths.sandbox_blocked(err))
        result.notes = ctx["notes"]
        # The CLI resolves its own caller inside `_send`; that context has to
        # come back out, or the provisional note below never fires for a shell
        # (P01 item 2: the basis must be visible in the result, not only in the
        # ledger). A context the caller passed in stands.
        if ctx.get("call") is not None:
            call = ctx["call"]
        if call is not None and getattr(call, "sure", True) is False:
            # An MCP call whose caller was a guess (the newest live record under
            # a shared daemon's pid). The send still goes -- the old messaging
            # policy is kept -- but the identity is provisional and the result
            # says so, so an agent does not treat it as an exact answer
            # (P01 item 2).
            result.notes = list(result.notes) + [
                "note: xsm identified this session only as %s (not an exact session id), so it "
                "signed the send as a best guess. Run from the session's own shell for an exact "
                "identity." % getattr(call, "basis", "unknown")]
        if result.msg_id:
            # The evidence axes as they stand after this send: the caller's
            # result says which trips happened, not one word for all of them
            # (A18-01).
            result.evidence = ledger.evidence_of(result.msg_id)
        if ctx["held"] and result.status in LEFT:
            outbox.drop(ctx["held"])        # it went: the held copy must not send it twice
        if span is not None:
            span.set_attribute("xsm.result.status", result.status)
            if result.msg_id:
                span.set_attribute("xsm.msg.id", result.msg_id)
            if result.target:
                span.set_attribute("xsm.target.ref", result.target.get("ref"))
                span.set_attribute("xsm.target.runtime", result.target.get("runtime"))
            if result.status in ("refused", "error"):
                span.set_status("ERROR", result.reason)
        if telemetry:
            telemetry.counter("xsm.send.count", 1, {"xsm.result.status": result.status})
        return result



def _full_endpoint(record):
    """Fill missing startup fields only from one matching registered pointer."""
    from . import handoff
    try:
        handoff._identity(record)
        return record
    except ValueError:
        pass
    if not record or not record.get("session_id"):
        return None
    candidates = [r for r in registry.raw_records()
                  if str(r.get("session_id")) == str(record["session_id"])
                  and (not record.get("runtime") or r.get("runtime") == record["runtime"])
                  and (not record.get("home") or r.get("home") == record["home"])
                  and (not record.get("ref") or r.get("ref") == record["ref"])]
    if len(candidates) != 1:
        return None
    complete = dict(candidates[0], **record)
    for field in ("runtime", "home", "session_id"):
        if not complete.get(field):
            complete[field] = candidates[0].get(field)
    try:
        handoff._identity(complete)
        return complete
    except ValueError:
        return None


def _send(target_spec: str, body: str, *, sender: dict | None = None, kind: str = "note",
          reply_to: str | None = None, priority: str = "next", wait: float = 0.0,
          msg_id: str | None = None, outcome: str | None = None, resend: bool = False,
          span=None, held: str | None = None, ctx: dict | None = None, call=None,
          wake: bool = True, attachments=None, file_packet=None, file_limits=None) -> SendResult:
    if not isinstance(wake, bool):
        return SendResult("refused", "wake must be a boolean")
    if not wake and priority != "next":
        return SendResult("refused", "strict FYI cannot request immediate delivery")
    if sender is None:
        # The CLI path: resolve the caller and *how* it was found in one pass, so
        # the identity basis reaches the ledger and the result. The lookup runs
        # once: `me` records the rule it matched, and that context is read back
        # here. The old `sender or registry.me()` walked the process tree twice
        # for one send -- two three-second budgets for one question (#17, G01
        # review).
        registry.forget_identity()
        with probe.quick():
            sender = registry.me()
            call = registry.last_identity()
        if call is not None and call.basis == context.BASIS_NONE:
            # Nothing matched at all: that is the unregistered refusal, not a
            # guessed identity to report on a send that went out.
            call = None
    ctx = ctx if ctx is not None else {"notes": [], "held": None}
    ctx["call"] = call
    if not sender:
        return SendResult("refused", "this session is not registered; run `xsm doctor`")
    sender = _full_endpoint(sender) or sender
    if resend and not msg_id:
        return SendResult("refused", "--resend needs the id of the message to send again")
    if held:
        rec = outbox.get(held, sender)
        if not rec:
            return SendResult("refused", "no message %s is held for this session (a refused "
                              "send is kept for a day, by the session that sent it)" % held)
        target_spec, body, kind = rec["spec"], rec["body"], rec["kind"]
        reply_to, outcome, priority = rec.get("reply_to"), rec.get("outcome"), \
            rec.get("priority") or "next"
        msg_id, ctx["held"] = rec["id"], rec["id"]
        stored_refs = rec.get("attachments") or []
        if attachments is not None and envelope.attachment_refs(attachments) != envelope.attachment_refs(stored_refs):
            return SendResult("refused", "held attachment refs differ; original request retained", msg_id)
        attachments = stored_refs

    if resend and attachments is None and msg_id:
        attachments = ledger.status(msg_id).get("attachments") or []
    try:
        attachments = envelope.attachment_refs(attachments)
    except ValueError as exc:
        return SendResult("refused", str(exc), msg_id)
    if file_packet is not None and not attachments:
        return SendResult("refused", "file packet requires immutable attachment refs", msg_id)
    if attachments:
        from . import files, handoff
        if len(attachments) != 1:
            return SendResult("refused", "one bundle manifest per message is supported; combine files in one manifest", msg_id)
        if call is not None and not call.sure:
            return SendResult("refused", "attachment dispatch requires an exact caller identity", msg_id)
        if not isinstance(file_packet, dict) or not isinstance(file_packet.get("manifest"), dict):
            return SendResult("refused", "immutable file packet required, including on resend", msg_id)
        msg_id = msg_id or (file_packet["manifest"].get("binding") or {}).get("request_id")
        try:
            handoff._id(msg_id)
            file_limits = file_limits or files.product_limits()
            if not isinstance(file_limits, files.Limits):
                raise ValueError("explicit file limits have invalid type")
            if file_packet["manifest"].get("owner") != files._owner(sender):
                raise ValueError("file packet belongs to a different native sender")
            if files.reference(file_packet["manifest"]) != attachments[0]:
                raise ValueError("file packet differs from immutable message refs")
        except (ValueError, KeyError, TypeError) as exc:
            return SendResult("refused", str(exc), msg_id)

    if target_spec.strip().startswith("net:"):
        from . import network, network_identity
        target_spec = target_spec.strip()
        try:
            endpoint = network_identity.parse_target(target_spec)
        except ValueError as exc:
            return SendResult("refused", str(exc), msg_id)
        if sender.get("ref") in config.blocked():
            return SendResult("refused", "this session is blocked (xsm block)", msg_id)
        if msg_id:
            prior = ledger.status(msg_id)
            if prior:
                scope = prior.get("scope") or ""
                intent = envelope.request_identity(msg_id, sender, dict(endpoint, ref=target_spec), body,
                    kind=kind, reply_to=reply_to, outcome=outcome, scope=scope,
                    priority=priority, attachments=attachments)
                if not scope.startswith("network:") or prior.get("req_version") != envelope.CANON_VERSION \
                        or prior.get("digest") != envelope.request_digest(intent):
                    return SendResult("refused", "message-id-conflict", msg_id)
        if resend:
            why = resend_refusal(msg_id, sender, body, kind, target=dict(endpoint, ref=target_spec),
                                 reply_to=reply_to, outcome=outcome,
                                 scope=ledger.status(msg_id).get("scope"), priority=priority,
                                 attachments=attachments)
            if why:
                return SendResult("refused", why, msg_id)
        msg_id = msg_id or envelope.new_id()
        try:
            reply = network.call({"op": "send", "caller": sender, "target": target_spec,
                                  "body": body, "id": msg_id, "kind": kind,
                                  "reply_to": reply_to, "outcome": outcome,
                                  "priority": priority, "wake": wake,
                                  "attachments": attachments, "file_packet": file_packet})
        except network.NetworkError as exc:
            status = "refused" if str(exc) in (
                "caller-unverified", "target-unavailable", "selection-required",
                "selection-unverified", "message-id-conflict", "no-active-network", "peer-refused",
                "request-archived") else "unknown"
            reply = {"status": status, "reason": str(exc), "id": msg_id}
        status = reply.get("status", "unknown")
        status = {"queued": "sent-unconfirmed"}.get(status, status)
        msg_id = reply.get("id") or msg_id
        reason = reply.get("reason") or ""
        if wait > 0 and status in ("sent-unconfirmed", "unknown", "stored"):
            state = network.reconcile(msg_id, caller=sender, wait=wait)
            current = state.get("status")
            if current in ("delivered", "held", "blocked", "refused", "error"):
                status = current
                reason = (state.get("receipt") or {}).get("reason") or state.get("error") or reason
        return SendResult(status, reason, msg_id, reply.get("target"))

    from . import remote
    local_spec, peer = remote.split_target(target_spec)
    if peer:
        if attachments:
            return SendResult("refused", "unsupported: remote files require P12 negotiation", msg_id)
        if not wake:
            return SendResult("refused", "unsupported: remote strict no-wake FYI needs receiver support")
        if priority != "next":
            return SendResult("refused", "unsupported: remote per-message priority control is not available")
        if sender.get("ref") in config.blocked():
            return SendResult("refused", "this session is blocked (xsm block)")
        why = resend_refusal(msg_id, sender, body, kind, peer=peer, spec=local_spec,
                             reply_to=reply_to, outcome=outcome) if resend else None
        if why:
            return SendResult("refused", why, msg_id)
        reply = remote.send(sender, local_spec, peer, body, kind, reply_to, wait, msg_id,
                            traceparent=span.traceparent() if span is not None else None,
                            outcome=outcome)
        status = reply.get("status") or ("queued" if reply.get("ok") else "error")
        status = {"queued": "sent-unconfirmed"}.get(status, status)
        return SendResult(status, reply.get("error") or ("on %s" % peer), reply.get("id"),
                          reply.get("target"))

    # Discovery alone runs under the shared budget. Scope, the forecast, the
    # delivery and the wait come after it: a spent budget must never turn into
    # an "out of scope" refusal (#17).
    with probe.quick():
        # Stable addresses already in the registry need only the target's
        # probes. Keep discovery for names and threads that have not registered.
        prefix, _, value = target_spec.strip().partition(":")
        known = prefix in ("ref", "claude", "codex") and any(
            r.get("ref") == value if prefix == "ref" else
            r.get("runtime") == prefix and r.get("session_id") == value
            for r in registry.raw_records())
        if not known:
            registry.adopt_open_codex()
        found = (resolve.resolve(target_spec, caller=sender) if target_spec.startswith("candidate:")
                 else resolve.resolve(target_spec))
    if not found.ok:
        return SendResult("refused", found.reason, candidates=found.candidates)
    target = found.record or {}
    if target.get("remote"):
        return _send(target["target"], body, sender=sender, kind=kind, reply_to=reply_to,
                     priority=priority, wait=wait, msg_id=msg_id, outcome=outcome,
                     resend=resend, span=span, ctx=ctx, call=call, wake=wake,
                     attachments=attachments, file_packet=file_packet, file_limits=file_limits)

    if not target.get("registered"):
        return SendResult("refused", "target has no hook record, so it cannot be addressed")
    why_priority = priority_refusal(target, priority)
    if why_priority:
        return SendResult("refused", why_priority, target=target)
    stopped = not_running(target)
    if stopped:
        return SendResult("refused", stopped + "\n" + resolve.resume_hint(target), target=target)
    if target.get("ref") == sender.get("ref"):
        return SendResult("refused", "refusing to send to yourself")
    blocked = config.blocked()
    if sender.get("ref") in blocked or target.get("ref") in blocked:
        mine = sender.get("ref") in blocked
        return SendResult("refused", "%s is blocked (xsm block); to lift it, ask your user and "
                          "run `xsm unblock %s`" % (
                              "this session" if mine else "the target",
                              sender.get("ref") if mine else target.get("ref")), target=target)

    scope, reason = config.scope_for(sender, target)
    if attachments and not scope:
        # Legacy outbox allocates a new ID and omits refs from its hold key.
        # Never rewrite the bound manifest/request just to fit that older API.
        return SendResult("refused", "out of scope: connect the exact target first, then retry "
                          "request_id=%s with manifest_id=%s; the snapshot and refs are retained"
                          % (msg_id, attachments[0]["id"]), msg_id, target)
    if not scope and not wake:
        return SendResult("refused", "out of scope: %s" % reason, target=target)
    if not scope and not resend:
        # Connecting the two folders is a widening, so a caller xsm only guessed
        # must not do it: a neighbour of a shared daemon could otherwise consume
        # another session's recorded yes and apply its link or reach (P01 item 2,
        # G01 review F2b). A send that carries no context at all keeps the old
        # behaviour: the CLI and the direct callers resolve their own identity.
        # A person at this terminal deciding for themselves is not a guessed
        # session identity, so their own typed send keeps connecting (the old
        # one-yes flow). Only a caller xsm had to guess at is refused.
        from . import workers
        why_sure = context.require_sure(call, "connect this folder so the message can go") \
            if call is not None and not workers.human_terminal() else None
        if why_sure:
            return SendResult("refused", why_sure, target=target)
        from . import connect
        step = connect.offer(sender, target, target_spec, {
            "body": body, "kind": kind, "reply_to": reply_to, "outcome": outcome,
            "priority": priority}, reason)
        if step is not None:
            ctx["held"] = step.id
            ctx["notes"] += step.notes
            if not step.go:
                return SendResult("refused", step.text, step.id, target)
            msg_id = step.id
            scope, reason = config.scope_for(sender, target)    # connected: send it now
    if not scope:
        return SendResult("refused", "out of scope: %s" % reason, target=target)
    if msg_id is None and not resend and not held:
        # The connection already exists this time, so `connect.offer` was never
        # reached -- but an earlier run may have applied the connection and died
        # before sending, leaving the message held (P02 item 5, the crash
        # boundary `tests/test_crash_boundaries.py` pins). Pick that copy up and
        # send under *its* id, so the person's one yes and the message keep one
        # identity across the crash; the held copy is dropped once it goes.
        mine = outbox.find(sender, target_spec, {
            "body": body, "kind": kind, "reply_to": reply_to, "outcome": outcome})
        if mine is not None:
            msg_id = mine["id"]
            ctx["held"] = mine["id"]
    if ctx["held"] and msg_id:
        previous = ledger.status(msg_id)
        if previous.get("from"):
            # The process may have died after delivery but before dropping
            # its held copy. Read back before ever rewriting the ledger.
            ident = envelope.request_identity(
                msg_id, sender, target, body, kind=kind, reply_to=reply_to,
                outcome=outcome, scope=scope, priority=priority, attachments=attachments)
            if (previous.get("req_version") != envelope.CANON_VERSION or
                    not previous.get("digest") or
                    previous["digest"] != envelope.request_digest(ident)):
                return SendResult("refused", "held message no longer matches its recorded "
                                  "request or target; it was not resent", msg_id, target)
            if previous.get("status") in ("delivered", "held", "blocked"):
                ctx["notes"].append("recovered the recorded result of held message %s" % msg_id)
                return SendResult(previous["status"], "receiver result recovered; not resent",
                                  msg_id, target)
            why = resend_refusal(msg_id, sender, body, kind, target=target,
                                 reply_to=reply_to, outcome=outcome, scope=scope,
                                 priority=priority, attachments=attachments)
            if why:
                return SendResult("refused", why, msg_id, target)
        if not ctx["notes"]:
            ctx["notes"].append("resuming held message %s under its original id" % msg_id)
    if wake and target.get("runtime") == "codex" and sandboxed():
        # `codex queue` opens Codex's state DB for writing and starts an
        # embedded app server; a Codex workspace-write sandbox or a Claude
        # worker's OS sandbox blocks both, and every worker in S10 lost one
        # attempt finding that out. Say it before trying.
        return SendResult("refused", "this shell is sandboxed and cannot reach a Codex session "
                          "(`codex queue` needs Codex's state DB and app server); send it with "
                          "the xsm_send MCP tool: same target, kind and text", target=target)

    forecast, why = native_forecast(sender, target)
    if forecast in ("refuse",):
        return SendResult("refused", "the receiver would drop this: %s" % why, target=target)

    if resend:
        why = resend_refusal(msg_id, sender, body, kind, target=target, reply_to=reply_to,
                             outcome=outcome, scope=scope, priority=priority, attachments=attachments)
        if why:
            return SendResult("refused", why, msg_id, target)
    msg_id = msg_id or envelope.new_id()
    content = envelope.build(body, msg_id=msg_id, sender=sender, scope=scope, kind=kind,
                             reply_to=reply_to, outcome=outcome,
                             traceparent=span.traceparent() if span is not None else None,
                             attachments=attachments)
    previous = ledger.status(msg_id)
    if previous.get("digest"):
        identity = envelope.request_identity(msg_id, sender, target, body, kind=kind,
                                             reply_to=reply_to, outcome=outcome,
                                             scope=scope, priority=priority, attachments=attachments)
        if previous["digest"] != envelope.request_digest(identity):
            return SendResult("refused", "message ID differs from its full recorded request", msg_id, target)
    # The original survives old hooks/export readers before any native write.
    from . import handoff
    exact_sender = _full_endpoint(sender)
    exact_target = _full_endpoint(target)
    file_storage = None
    if attachments:
        capability = registry.file_capability(target)
        if capability.get("status") != "observed" or capability.get("version") != 1:
            return SendResult("refused", "unsupported or unknown files capability: " + capability.get("reason", "no current reader"),
                              msg_id, target)
        if exact_sender is None or exact_target is None:
            return SendResult("refused", "files require exact native sender and target handles", msg_id, target)
        try:
            # Reserve the global endpoint before any target copy side effect.
            ledger.handoff_step(msg_id, None, exact_target)
        except ValueError as exc:
            return SendResult("refused", str(exc), msg_id, target)
        try:
            receipt = files.receive(exact_target, file_packet, request_id=msg_id, body=body,
                                    expected_reference=attachments[0], limits=file_limits)
            file_storage = receipt["storage_id"]
        except (ValueError, OSError) as exc:
            ledger.queued(msg_id, sender, target, scope, kind, body, forecast=forecast,
                          reply_to=reply_to, outcome=outcome, priority=priority, attachments=attachments)
            ledger.step(msg_id, "file-storage", False, str(exc))
            if getattr(exc, "stored", False) is None:
                ledger.unknown(msg_id, str(exc))
                return SendResult("unknown", "file storage unknown; body was not dispatched: " + str(exc), msg_id, target)
            ledger.failed(msg_id, "file storage failed; body was not dispatched: " + str(exc))
            return SendResult("error", "file storage failed; body was not dispatched: " + str(exc), msg_id, target)
    if exact_sender is not None and exact_target is not None:
        try:
            # Reserve the global ledger ID before creating an endpoint original.
            ledger.handoff_step(msg_id, None, exact_target)
            message = {
                "id": msg_id, "sender": exact_sender, "target": exact_target,
                "body": body, "kind": kind, "reply_to": reply_to, "outcome": outcome,
                "scope": scope, "priority": priority, "content": content, "wake": wake}
            if attachments:
                message.update(attachments=attachments, file_storage=file_storage)
            original = handoff.store(exact_target, message)
            if original["message"].get("wake", True) != wake:
                return SendResult("refused", "message ID has a different wake policy", msg_id, target)
            ledger.handoff_step(msg_id, "stored", exact_target)
            if original["status"] == "acknowledged":
                return SendResult("delivered", "canonical consumption already acknowledged; not resent", msg_id, target)
        except ValueError as exc:
            return SendResult("refused", str(exc), msg_id, target)
    elif not wake:
        return SendResult("refused", "strict FYI requires full native sender and target identities", msg_id, target)
    ledger.queued(msg_id, sender, target, scope, kind, body, forecast=forecast,
                  reply_to=reply_to, outcome=outcome, priority=priority,
                  basis=getattr(call, "basis", None),
                  certainty=getattr(call, "certainty", None), attachments=attachments)
    if attachments:
        ledger.step(msg_id, "file-storage", True, file_storage)
    ledger.step(msg_id, "accepted")
    if exact_target is not None:
        handoff.delivery(exact_target, msg_id, "pending",
                         route="native" if wake else "mcp-inbox")

    if not wake:
        # No compatibility export, socket, queue command, daemon or wake call.
        ledger.step(msg_id, "wake", False, "strict no-wake: transport not attempted")
        return SendResult("stored", "strict FYI stored for the next natural consumer boundary", msg_id, target)

    inbox.preserve({"id": msg_id, "content": content,
                    "receiver": exact_target}, str(target.get("session_id")))
    queued = None
    stored_for_mcp = False
    try:
        if target.get("runtime") == "claude":
            if not target.get("socket"):
                # The row is already `queued`; left so, doctor reported it as a
                # message nobody had received (#18).
                ledger.step(msg_id, "queued", False, "no-inbox: target has no inbox socket")
                ledger.failed(msg_id, "no-inbox: target has no inbox socket")
                if exact_target is not None:
                    handoff.delivery(exact_target, msg_id, "refused")
                return SendResult("refused", "target has no inbox socket", msg_id, target)
            if kind == "reply":
                # A Claude caller can be blocked inside ask's CLI/MCP wait.
                # Keep a reply copy for checked read-only polling; the native
                # hook still performs its ordinary handover and removes it.
                inbox.keep(str(target.get("session_id")), msg_id, content, receiver=exact_target)
            adapters.to_claude(target["socket"], content, msg_id, priority=priority,
                               reply_address=("uds:%s" % sender["socket"]) if sender.get("socket")
                               else None)
            # The socket write landed. That is `queued`: the runtime's own
            # channel took the frame. It is not the receiver -- only a receipt
            # is (A18-01).
            ledger.step(msg_id, "queued", True, "uds:%s" % target["socket"])
        else:
            # Codex takes its queue only between turns; the copy is what a
            # session in the middle of one reads with `xsm inbox`.
            inbox.keep(str(target.get("session_id")), msg_id, content, receiver=exact_target)
            home = target.get("home", os.path.expanduser("~/.codex"))
            queued = adapters.to_codex(home, str(target.get("session_id")), content)
            inbox.note_queued(str(target.get("session_id")), msg_id, home,
                              adapters.queued_id(queued))
            # The queue command ran; and the daemon was or was not asked to
            # start it. Two separate steps, neither one a delivery.
            ledger.step(msg_id, "queued", True, adapters.queued_id(queued))
            ledger.step(msg_id, "wake", getattr(queued, "wake", "skipped") == "started",
                        getattr(queued, "wake", "skipped"))
    except adapters.DeliveryError as err:
        if (isinstance(err, adapters.UnsupportedCapability) and
                err.capability == adapters.UNLOADED_SUBAGENT_INPUT and
                target.get("runtime") == "codex" and exact_target is not None and
                exact_sender is not None):
            # Scope/deny/full endpoint validation and canonical storage already
            # succeeded. Native explicitly refused only direct subagent input;
            # keep this exact request available to the permitted local reader.
            # No native load/resume/steer, wake-policy change or queue success.
            handoff.delivery(exact_target, msg_id, "pending", route="mcp-inbox")
            # The auto request's already-written compatibility export is a
            # local pull copy, not a native queue or wake. Keep it for older
            # MCP readers; disappearance alone can never ACK the canonical.
            ledger.step(msg_id, "queued", False, "%s: %s" % (err.reason, err.detail))
            ledger.step(msg_id, "wake", False, "native capability unsupported; MCP inbox route")
            paths.append_jsonl("decisions.jsonl", {
                "decision": "send-stored", "id": msg_id, "route": "mcp-inbox",
                "reason": err.reason, "capability": err.capability})
            stored_for_mcp = True
        else:
            if exact_target is not None:
                handoff.delivery(exact_target, msg_id, "error")
            inbox.drop(str(target.get("session_id")), msg_id)
            ledger.step(msg_id, "queued", False, "%s: %s" % (err.reason, err.detail))
            ledger.failed(msg_id, "%s: %s" % (err.reason, err.detail))
            paths.append_jsonl("decisions.jsonl", {"decision": "send-failed", "id": msg_id,
                                                   "reason": err.reason, "detail": err.detail})
            return SendResult("error", "%s: %s" % (err.reason, err.detail), msg_id, target)

    if kind == "reply" and reply_to and (call is None or call.sure):
        from . import questions
        if questions.expects_reply(target, sender, reply_to):
            # Preserve the full answer even if an older receiving hook consumes
            # its native inbox copy without knowing the new question index.
            try:
                inbox.keep_reply(target, msg_id, reply_to, content)
            except OSError:
                ctx["notes"].append("the reply recovery copy could not be stored; the original is retained")
    if wait > 0:
        state = ledger.wait_for(msg_id, wait)
        if state.get("status") == "delivered":
            return SendResult("delivered", "receiver recorded it", msg_id, target)
        if state.get("status") in ("held", "blocked"):
            return SendResult(state["status"], (state.get("receipt") or {}).get("reason", ""),
                              msg_id, target)
    if stored_for_mcp:
        return SendResult("stored", "native direct subagent input is unsupported; "
                          "original retained for the MCP inbox, awaiting actual consumption",
                          msg_id, target)
    note = "queued"
    if target.get("runtime") == "codex" and getattr(queued, "wake", None) == "started":
        # Still unconfirmed: the gate's receipt is what says it arrived.
        note = ("queued and started now: the Codex session is running it as a turn (this also "
                "wakes a session its user stopped with Esc)")
    elif target.get("runtime") == "codex":
        note = ("queued; a Codex session picks the queue up within about 10 seconds when the "
                "thread is loaded and idle, or mid-turn with `xsm inbox`")
    elif forecast == "hold":
        note = "queued, but Claude will hold it for its user: %s" % why
    elif forecast == "unknown":
        note = "queued; %s, so the receiver's own gate may hold it" % why
    return SendResult("sent-unconfirmed", note, msg_id, target)


RESENDABLE = ("queued", "unknown", "error")


def resend_refusal(msg_id: str, sender: dict, body: str, kind: str, *, target: dict | None = None,
                   peer: str | None = None, spec: str | None = None,
                   reply_to: str | None = None, outcome: str | None = None,
                   scope: str | None = None, priority: str | None = None,
                   attachments=None) -> str | None:
    """Why `msg_id` may not be sent again as it is, or None when it may.

    Sending again under the same id is safe only because the receiver drops an
    id it already holds a receipt for; so the id must be one this session sent
    from here, to this same target, and not yet answered. Otherwise a caller
    could reuse someone else's id, or aim a delivered id at a new target and
    get the receiver's dedup to swallow the real message (2026-09-29). The
    ledger records `from.ref` only, so that is what "the same sender" means.

    Since P01 the compare is on the *digest* of the canonical request -- the
    whole body, both handles, kind, reply_to, outcome, scope and the attachment
    manifest -- so two bodies that share their first 200 characters are two
    different messages and a swapped reply_to or outcome is refused (A18-03).
    A record written before the digest existed has none: it is read as
    legacy/unverified, and only the fields it does carry (sender, target, kind,
    and the 200-char preview) are compared. No digest is ever rebuilt from a
    preview (P01 item 5).
    """
    if os.path.basename(msg_id) != msg_id or msg_id.startswith("."):
        return "%r is not a message id" % msg_id
    state = ledger.status(msg_id)
    if not state.get("from"):
        return ("no message %s in this machine's ledger; only an id sent from here can be "
                "resent" % msg_id)
    if not sender.get("ref") or (state["from"] or {}).get("ref") != sender.get("ref"):
        return "message %s was not sent by this session" % msg_id
    traffic_deferred=(state.get('status')=='held' and
        str((state.get('receipt') or {}).get('reason') or '').startswith('traffic ') and not state.get('outcome'))
    if state.get("status") not in RESENDABLE and not traffic_deferred:
        return ("message %s is %s; only a message still queued, unknown or error can be sent "
                "again" % (msg_id, state.get("status")))
    was = state.get("to") or {}
    if peer:
        same = was.get("runtime") == "remote" and was.get("name") == spec \
            and was.get("alias") == peer
    else:
        same = bool((target or {}).get("ref")) and was.get("ref") == target.get("ref")
    if not same:
        return "message %s went to %s@%s, not to this target; a resend keeps its target" % (
            msg_id, was.get("name"), was.get("alias"))
    if state.get("kind") != kind:
        return "message %s was a %s, not a %s" % (msg_id, state.get("kind"), kind)
    recorded = state.get("digest")
    if recorded and state.get("req_version") == envelope.CANON_VERSION:
        # The full contract: recompute the canonical digest from exactly what
        # would go out, and require it equals what went out before. Scope and
        # priority are derived, not typed by the caller, so the recorded values
        # stand in when the caller did not restate them.
        same_target = None if peer else target
        ident = envelope.request_identity(
            msg_id, sender, _resend_target(same_target, spec, peer), body, kind=kind,
            reply_to=reply_to, outcome=outcome,
            scope=scope if scope is not None else state.get("scope"),
            priority=priority if priority is not None else state.get("priority"),
            attachments=attachments if attachments is not None else state.get("attachments"))
        if envelope.request_digest(ident) != recorded:
            return ("this message differs from message %s: its body, kind, reply_to, outcome, "
                    "scope or target has changed. A resend must be the same message; send the new "
                    "one without --resend as a new message" % msg_id)
        return None
    # A legacy record: no digest, so compare only what it kept. The preview is
    # not a body, and this path never claims the message is identical -- only
    # that nothing this record can see has changed.
    if body[:200] != (state.get("preview") or ""):
        return ("this text differs from message %s (recorded before xsm kept a full digest, so "
                "only its first 200 characters are known); a resend must be the same message. "
                "Send the new text without --resend as a new message" % msg_id)
    return None


def _resend_target(target: dict | None, spec: str | None, peer: str | None) -> dict | None:
    """The handle the digest was built from. A remote send queued the request
    under the reduced handle remote.send writes, so a resend must rebuild that
    same one or the digests cannot match."""
    if peer:
        return {"name": spec, "alias": peer, "ref": None, "runtime": "remote"}
    return target


def not_running(target: dict) -> str | None:
    """Why a message must not go to `target` because it stopped, or None.

    Names resolve to live sessions only, but ref:, claude: and codex: name one
    session exactly and used to reach a stopped one too; the queue then held
    the message for nobody, and a reach granted to that session looked usable
    (2026-09-28). `unknown` stays sendable: it is a session whose liveness
    could not be checked, not a dead one. Shared with remote ingress, which
    delivered to a stopped session for the same reason."""
    if target.get("state") in ("ended", "stale"):
        return "%s@%s [%s] is not running (%s)" % (
            target.get("name"), target.get("alias"), target.get("ref"), target.get("state"))
    return None


def sandboxed() -> bool:
    """Codex marks its sandboxed shells with CODEX_SANDBOX; a background Claude
    worker's settings mark its shells with XSM_SANDBOXED (workers.py)."""
    return bool(os.environ.get("CODEX_SANDBOX") or os.environ.get("XSM_SANDBOXED"))


def native_forecast(sender: dict, target: dict) -> tuple:
    """What Claude's own gate will most likely do with this message.

    Returns (verdict, explanation). Only meaningful for a Claude target: Codex
    has no such gate. The order mirrors the receive decision measured in S1 —
    an explicit setting wins, then permission-mode parity.
    """
    if target.get("runtime") != "claude":
        return "n/a", ""
    setting = registry.inbound_setting(target.get("home", ""), target.get("cwd"))
    if setting == "accept":
        return "accept", "receiver's user settings say crossSessionInbound=accept"
    if setting in ("hold", "refuse"):
        return setting, ("receiver's settings say crossSessionInbound=%s (its user's own "
                         "choice: xsm install leaves a value that is set)" % setting)
    mine, theirs = registry.mode_class(sender), registry.mode_class(target)
    if mine is None or theirs is None:
        return "unknown", "one of the two permission modes is not known yet"
    if mine == theirs:
        return "accept", "both sessions run in %s mode" % theirs
    return "hold", ("sender is %s and receiver is %s, so Claude holds the message for its "
                    "user. `xsm install --refresh` (your agent can run it) sets "
                    "crossSessionInbound to \"accept\" in the receiver's Claude home, %s, after "
                    "which a message goes through whatever the modes are (user decision, "
                    "2026-10-01); or match the permission modes" % (
                        mine, theirs, target.get("home") or "wherever it is installed"))
