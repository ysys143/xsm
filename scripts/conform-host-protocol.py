#!/usr/bin/env python3
"""Stdio conformance checks without xsm imports; approval suite seeds and inspects synthetic worker state."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import time


def require(condition, details):
    if not condition:
        raise AssertionError(details)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError('non-JSON numeric constant: ' + value)


class Peer:
    def __init__(self, command, cwd, env, observations=None):
        root = Path(cwd).resolve()
        for key in ('HOME', 'XSM_HOME'):
            value = env.get(key)
            if (not isinstance(value, str) or not value or not Path(value).is_absolute()
                    or not Path(value).resolve().is_relative_to(root)):
                raise ValueError('candidate requires isolated HOME and XSM_HOME within its fixture directory')
        self.observations = observations
        self.notifications = []
        self.frames = queue.Queue(maxsize=128)
        self.errors = tempfile.TemporaryFile()
        try:
            self.process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=self.errors)
        except BaseException:
            self.errors.close()
            raise
        self.serial = 0
        def read():
            try:
                while True:
                    line = self.process.stdout.readline(4 * 1048576 + 1)
                    if not line:
                        raise RuntimeError("candidate closed stdout")
                    if len(line) > 4 * 1048576 or not line.endswith(b"\n"):
                        raise RuntimeError("candidate emitted an invalid or oversized frame")
                    self.frames.put(json.loads(line.decode('utf-8', errors='strict'),
                        object_pairs_hook=unique_object, parse_constant=reject_constant))
            except Exception as error:
                self.frames.put(error)
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

    def call(self, method, params=None, error=None):
        self.serial += 1
        frame = {"jsonrpc": "2.0", "id": self.serial, "method": method, "params": params or {}}
        self.process.stdin.write((json.dumps(frame) + "\n").encode())
        self.process.stdin.flush()
        deadline = time.monotonic() + 5
        while True:
            value = self.frames.get(timeout=max(0, deadline - time.monotonic()))
            if isinstance(value, Exception):
                raise value
            require(isinstance(value, dict) and value.get("jsonrpc") == "2.0", value)
            if "id" not in value:
                require(isinstance(value.get("method"), str) and isinstance(value.get("params"), dict), value)
                self.notifications.append(value)
                if self.observations is not None:
                    self.observations.append({"frame": value})
                continue
            require(type(value["id"]) is int and value["id"] == self.serial, value)
            require(("result" in value) != ("error" in value), value)
            if self.observations is not None:
                observation = {"method": method, "frame": value}
                if method == 'operation.call' and isinstance(params, dict):
                    observation['operation'] = params.get('operation')
                    arguments = params.get('arguments')
                    if isinstance(arguments, dict):
                        observation['action'] = arguments.get('action')
                self.observations.append(observation)
            if error is not None:
                require(isinstance(value.get("error"), dict) and type(value["error"].get("code")) is int and value["error"]["code"] == error, value)
                return value["error"]
            require("result" in value, value)
            return value["result"]

    def notification(self):
        if self.notifications:
            return self.notifications.pop(0)
        value = self.frames.get(timeout=5)
        if isinstance(value, Exception):
            raise value
        require(isinstance(value, dict) and value.get("jsonrpc") == "2.0" and
                "id" not in value and isinstance(value.get("method"), str) and
                isinstance(value.get("params"), dict), value)
        if self.observations is not None:
            self.observations.append({"frame": value})
        return value

    def close(self):
        if self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=3)
        self.process.stdout.close()
        self.reader.join(timeout=1)
        self.errors.seek(0)
        diagnostics = self.errors.read(8192).decode(errors="replace")
        self.errors.close()
        return diagnostics


def uploads(peer, sender, receiver, reopen, limits, check, equal):
    """Public bytes-only preparation, canonical delivery, and explicit consumption."""
    def operation(session, name, **arguments):
        return peer.call('operation.call', {'session': session['session'], 'operation': name, 'arguments': arguments})
    chunk = limits.get('fileUploadChunkBytes')
    check('bounded upload extension advertised', lambda: equal(type(chunk) is int and 0 < chunk <= 196608, True))
    operation(receiver, 'xsm_inbox')  # Actual reader observation, not a claimed file capability.
    entries = [bytes([index]) * 1048576 for index in range(4)]
    specs = [{'name': 'copy%d.bin' % index, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
             for index, data in enumerate(entries)]
    target = receiver.get('address') or 'ref:' + receiver['ref']
    args = dict(session=sender['session'], target=target, request_id='upload-four-mib', text='four exact copies', entries=specs)
    bad = dict(args, request_id='oversized', entries=[dict(specs[0], size=1048577)])
    check('oversized entry refused before upload', lambda: peer.call('files.upload.open', bad, error=-32602))
    opened = peer.call('files.upload.open', args)
    handle = opened['upload']
    def write(index, offset, data, session=sender, error=None):
        return peer.call('files.upload.write', dict(session=session['session'], upload=handle,
            entry=index, offset=offset, base64=base64.b64encode(data).decode('ascii')), error=error)
    check('foreign session cannot write upload', lambda: write(0, 0, entries[0][:13], receiver, -32602))
    write(0, 0, entries[0][:13])
    check('exact chunk replay is idempotent', lambda: equal(write(0, 0, entries[0][:13])['offset'], 13))
    check('changed chunk replay refused', lambda: write(0, 0, b'changed bytes', error=-32602))
    for index, data in enumerate(entries):
        for offset in range(13 if index == 0 else 0, len(data), chunk):
            write(index, offset, data[offset:offset + chunk])
    committed = peer.call('files.upload.commit', dict(session=sender['session'], upload=handle))
    check('four MiB frozen without body send', lambda: equal(committed.get('body_sent'), False))
    check('prepared bytes do not populate receiver inbox', lambda: equal(operation(receiver, 'xsm_inbox')['items'], []))
    check('foreign session cannot recover material intent', lambda: equal(peer.call('files.upload.status',
        dict(session=receiver['session'], request_id=args['request_id']))['state'], 'unknown'))
    peer.call('session.close', {'session': sender['session']})
    sender = peer.call('session.open', reopen)
    status = peer.call('files.upload.status', dict(session=sender['session'], request_id=args['request_id']))
    check('new execution recovers frozen manifest by request ID', lambda: equal(status['manifest_id'], committed['manifest_id']))
    check('closed upload handle cannot be written', lambda: peer.call('files.upload.write', dict(
        session=sender['session'], upload=handle, entry=0, offset=0, base64=''), error=-32602))
    check('changed reopened preparation refused', lambda: peer.call('files.upload.open', dict(args,
        session=sender['session'], text='changed original'), error=-32602))
    operation(sender, 'xsm_send', target=target, request_id=args['request_id'], text=args['text'],
              manifest_id=committed['manifest_id'], wait=0, wake='never')
    packet = operation(receiver, 'xsm_inbox')
    check('explicit send creates one original', lambda: equal([c['id'] for c in packet['claims']], [args['request_id']]))
    copied = packet['items'][0]['files']
    check('all four copied entries retained', lambda: equal(len(copied['files']), 4))
    for index, metadata in enumerate(copied['files']):
        result = operation(receiver, 'xsm_files', storage_id=copied['storage_id'], entry_id=metadata['id'], encoding='base64')
        data = base64.b64decode(result['content'], validate=True)
        check('copy %d exact bytes and digest' % index, lambda data=data, metadata=metadata, index=index:
            equal(data == entries[index] and hashlib.sha256(data).hexdigest() == metadata['sha256'], True))
    manifest_result = operation(receiver, 'xsm_files', storage_id=copied['storage_id'])
    canonical = operation(receiver, 'xsm_files', storage_id=copied['storage_id'], manifest_bytes=True)
    preimage = base64.b64decode(canonical['content'], validate=True)
    check('manifest digest verifies exact exported bytes', lambda: equal(
        hashlib.sha256(preimage).hexdigest() == canonical['manifest_sha256'] == copied['sha256'], True))
    check('digest preimage binds the complete manifest', lambda: equal(json.loads(preimage.decode('utf-8')),
        {key: value for key, value in manifest_result['manifest'].items() if key != 'sha256'}))
    check('manifest bytes are a distinct response kind', lambda: equal(
        canonical['canonical_format'] == 'xsm.files/v1' and canonical['encoding'] == 'base64' and 'entry_id' not in canonical, True))
    temporary = peer.call('files.upload.open', dict(args, session=sender['session'], request_id='abort-buffer', entries=[specs[0]]))
    check('abort frees volatile preparation only', lambda: equal(peer.call('files.upload.abort', {
        'session': sender['session'], 'upload': temporary['upload']})['aborted'], True))
    check('abort does not acknowledge existing original', lambda: equal(
        [c['id'] for c in operation(receiver, 'xsm_inbox', message_ids=[args['request_id']])['claims']], [args['request_id']]))
    check('explicit ACK consumes copied original', lambda: equal(operation(receiver, 'xsm_ack',
        tokens=[c['token'] for c in packet['claims']])['acked'], [args['request_id']]))
    corrupt = peer.call('files.upload.open', dict(args, session=sender['session'], request_id='bad-digest',
        entries=[{'name': 'bad.bin', 'size': 1, 'sha256': '0' * 64}]))
    peer.call('files.upload.write', dict(session=sender['session'], upload=corrupt['upload'],
        entry=0, offset=0, base64='YQ=='))
    check('declared digest mismatch refuses commit', lambda: peer.call('files.upload.commit',
        dict(session=sender['session'], upload=corrupt['upload']), error=-32602))
    peer.call('files.upload.abort', dict(session=sender['session'], upload=corrupt['upload']))
    check('aborted corrupt upload has no indexed preparation', lambda: equal(peer.call('files.upload.status',
        dict(session=sender['session'], request_id='bad-digest'))['state'], 'unknown'))
    check('digest refusal does not send a body', lambda: equal(operation(receiver, 'xsm_inbox')['items'], []))


def messaging(peer, sender, receiver, reopen, check, equal, events=False):
    def operation(session, name, error=None, **arguments):
        return peer.call("operation.call", {"session": session["session"],
                         "operation": name, "arguments": arguments}, error=error)
    def report(claim, **fields):
        return peer.call("delivery.report", dict(session=receiver["session"], id=claim["id"], **fields))
    peer.call("events.subscribe", {"session": receiver["session"]})
    body = "black-box delivery: 한글 🚀 preserved\n  whitespace"
    operation(sender, "xsm_send", target="ref:" + receiver["ref"], text=body, wake="never", wait=0)
    packet = operation(receiver, "xsm_inbox", limit=1)
    check("stored original can be claimed whole", lambda: equal(len(packet["claims"]) == 1 and
          body in packet["messages"][0], True))
    claim = packet["claims"][0]
    check("foreign consumer cannot acknowledge", lambda:
          operation(sender, "xsm_ack", tokens=[claim["token"]], error=-32602))
    check("native admission requires exact claim", lambda: peer.call("delivery.report", {
          "session": receiver["session"], "id": claim["id"], "state": "admitted", "token": "forged"}, error=-32003))
    check("queued report is not consumption", lambda: equal(report(claim, state="queued")["acknowledged"], False))
    check("failed admission releases own claim", lambda: equal(peer.call("inbox.release", {
          "session": receiver["session"], "tokens": [claim["token"]]})["released"], [claim["id"]]))
    retry = operation(receiver, "xsm_inbox", limit=1)
    check("released original remains recoverable", lambda: equal(len(retry["claims"]) == 1 and
          retry["claims"][0]["id"] == claim["id"] and body in retry["messages"][0], True))
    current = retry["claims"][0]
    check("retry rotates claim token", lambda: equal(current["token"] != claim["token"], True))
    check("released claim cannot acknowledge", lambda:
          operation(receiver, "xsm_ack", tokens=[claim["token"]], error=-32602))
    check("admitted report is not consumption", lambda: equal(
          report(current, state="admitted", token=current["token"])["acknowledged"], False))
    peer.call("session.close", {"session": receiver["session"]})
    receiver = peer.call("session.open", reopen)
    check("resumed receiver rejects previous generation claim", lambda:
          operation(receiver, "xsm_ack", tokens=[current["token"]], error=-32602))
    resumed = operation(receiver, "xsm_inbox", limit=1)
    check("admitted original survives generation change", lambda: equal(len(resumed["claims"]) == 1 and
          resumed["claims"][0]["id"] == claim["id"] and body in resumed["messages"][0], True))
    check("ordinary inbox omits current owned claims", lambda: equal(
          operation(receiver, "xsm_inbox")["claims"], []))
    check("targeted inbox returns current owned token", lambda: equal(
          operation(receiver, "xsm_inbox", message_ids=[claim["id"]])["claims"], resumed["claims"]))
    check("targeted inbox cannot read another conversation", lambda: equal(
          operation(sender, "xsm_inbox", message_ids=[claim["id"]])["claims"], []))
    token = resumed["claims"][0]["token"]
    check("explicit consumer ACK commits", lambda: equal(
          operation(receiver, "xsm_ack", tokens=[token])["acked"], [claim["id"]]))
    consumed = operation(receiver, "xsm_inbox")
    check("consumed original is absent from inbox", lambda: equal(
          consumed["claims"] == [] and consumed["messages"] == [], True))

    check("acknowledged targeted original stays absent", lambda: equal(
          operation(receiver, "xsm_inbox", message_ids=[claim["id"]])["claims"], []))

    if events:
        peer.call("events.subscribe", {"session": receiver["session"]})
        operation(sender, "xsm_send", target="ref:" + receiver["ref"], text="event-bound original", wait=0)
        event = peer.notification()
        check("event binds receiver and pending IDs", lambda: equal(event["method"] == "events/available" and
              set(event["params"]) == {"session", "ids"} and event["params"]["session"] == receiver["session"] and
              len(event["params"]["ids"]) == 1, True))
        pending = operation(receiver, "xsm_inbox")
        check("notification neither claims nor consumes original", lambda: equal(len(pending["claims"]) == 1 and
              pending["claims"][0]["id"] == event["params"]["ids"][0] and
              "event-bound original" in pending["messages"][0], True))
        check("event original requires explicit ACK", lambda: equal(operation(receiver, "xsm_ack",
              tokens=[pending["claims"][0]["token"]])["acked"], event["params"]["ids"]))


def approvals(peer, params, env, check, equal):
    """Seed synthetic worker requests; exercise answers through public stdio only."""
    owner = peer.call('session.open', dict(params, conversation='approval-contract-owner', capabilities=['user-decisions']))
    def operation(**arguments):
        return peer.call('operation.call', dict(session=owner['session'], operation='xsm_approve', arguments=arguments))
    state = Path(env['XSM_HOME'])
    def seed(ident):
        # This fixture does not launch a worker or execute a requested command.
        for relative, value in (
            ('workers/approval-fixture.json', dict(name='approval-fixture', parent_ref=owner['ref'], created=1)),
            ('approvals/' + ident + '.json', dict(id=ident, worker='approval-fixture', status='pending',
                summary='fixture summary', t=1, runtime='codex', tool='Bash', input=dict(command='fixture only')))):
            target = state / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(value))
    check('no worker request returns text only', lambda: equal(set(operation()), {'text'}))
    for ident, answer, status in (('approval-allow', 'allow', 'approved'), ('approval-deny', 'deny', 'denied')):
        seed(ident)
        pending = operation(id=ident)
        check(status + ' requires host question', lambda: equal(pending.get('status'), 'waiting-for-user'))
        event = peer.notification()['params']
        check(status + ' hides host challenge', lambda: equal('challenge' not in pending, True))
        peer.call('decision.response', dict(session=owner['session'], questionId=event['questionId'], challenge=event['challenge'],
            displayed=event['question'], action='accept', answer=answer, source_id='synthetic-' + ident))
        result = operation(id=ident)
        check(status + ' snapshot binds exact request', lambda: equal(
            result['approval']['id'] == ident and result['approval']['status'] == status and
            result['approval']['worker'] == 'approval-fixture' and result['approval']['via'] == 'host-user', True))
        stored = json.loads((state / 'approvals' / (ident + '.json')).read_text())
        check(status + ' persists exact worker answer', lambda: equal(stored['status'], status))
        if status == 'approved':
            check('allow replay preserves producer snapshot', lambda: equal(operation(id=ident), result))


def grants(peer, params, check, equal):
    owner = peer.call('session.open', dict(params, conversation='grant-contract-owner', capabilities=['user-decisions']))
    def operation(name, error=None, **arguments):
        return peer.call('operation.call', dict(session=owner['session'], operation=name, arguments=arguments), error=error)
    args = dict(runtime='codex', options=['full_access'], reason='isolated grant producer fixture')
    pending = operation('xsm_grant', **args)
    check('worker grant requires a host question', lambda: equal(pending['status'], 'waiting-for-user'))
    event = peer.notification()['params']
    check('grant model result has no private challenge', lambda: equal('challenge' not in pending, True))
    peer.call('decision.response', dict(session=owner['session'], questionId=event['questionId'], challenge=event['challenge'],
        displayed=event['question'], action='accept', answer='allow once', source_id='synthetic-grant-answer'))
    before = operation('xsm_decision_status', id=pending['decision_id'])
    check('grant answer is not an applied issuance', lambda: equal(before['status']=='answered' and before['application'] is None, True))
    issued = {}
    def issue():
        value = operation('xsm_grant', **args)
        equal('grant' in value, True)
        issued.update(value['grant'])
        equal(issued['runtime']=='codex' and issued['cwd']==str(Path(params['cwd']).resolve()) and
              issued['options']==['full_access'] and issued['asked_by']==owner['ref'] and
              issued['single_use'] is True and len(issued['id'])==8 and
              all(c in '0123456789abcdef' for c in issued['id']),True)
    check('grant issuance returns producer scope', issue)
    check('grant retry preserves original producer snapshot', lambda: equal(operation('xsm_grant', **args)['grant'], issued))
    check('grant issuance is observed in decision journal', lambda: equal(operation('xsm_decision_status', id=pending['decision_id'])['status'],'applied'))
    denied_args = dict(args, reason='isolated denied grant fixture')
    denied = operation('xsm_grant', **denied_args)
    deny_event = peer.notification()['params']
    peer.call('decision.response', dict(session=owner['session'], questionId=deny_event['questionId'], challenge=deny_event['challenge'],
        displayed=deny_event['question'], action='accept', answer='deny', source_id='synthetic-denied-grant'))
    check('denied grant retry cannot issue a worker grant', lambda: operation('xsm_grant', error=-32602, **denied_args))
    check('denied grant stays denied', lambda: equal(operation('xsm_decision_status', id=denied['decision_id'])['status'],'denied'))


def selection_ui(peer, params, env, check, equal):
    owner = peer.call('session.open', dict(params, conversation='selection-owner', capabilities=['user-decisions','inbox']))
    outside = Path(params['cwd']) / 'selection-repository'; outside.mkdir()
    subprocess.run(['git','init','-q','-b','main',str(outside)],env=env,check=True,capture_output=True,timeout=5)
    other = peer.call('session.open', dict(params, conversation='selection-peer', cwd=str(outside), capabilities=['messaging','inbox','user-decisions']))
    def operation(session, name, error=None, **arguments):
        return peer.call('operation.call',dict(session=session['session'],operation=name,arguments=arguments),error=error)
    def visible():
        return owner['ref'] in [row['ref'] for row in operation(other,'xsm_discover')['candidates']]
    def answer(event, word, error=None, session=owner):
        return peer.call('decision.response',dict(session=session['session'],questionId=event['questionId'],
            challenge=event['challenge'],displayed=event['question'],action='accept',answer=word,
            source_id='synthetic-selection-' + event['questionId']),error=error)
    pending = {}
    def publication_question():
        pending.update(operation(owner,'xsm_publish'))
        equal(pending['status']=='waiting-for-user' and not visible() and 'challenge' not in pending,True)
    check('publication asks host before effect',publication_question)
    event = peer.notification()['params']
    check('foreign host cannot approve publication',lambda:answer(event,'allow',error=-32003,session=other))
    answer(event,'allow')
    check('host answer does not publish before retry',lambda:equal(visible(),False))
    check('explicit retry publishes selected conversation',lambda:equal(operation(owner,'xsm_publish')['status']=='published' and visible(),True))
    selected = operation(owner,'xsm_connect',target='ref:' + other['ref'])
    check('publication alone grants no pair permission',lambda:equal(selected['status'],'waiting-for-user'))
    selection = peer.notification()['params']
    answer(selection,'allow')
    check('selection answer does not dispatch handshake before retry',lambda:equal(operation(other,'xsm_inbox')['claims'],[]))
    handshake = operation(owner,'xsm_connect',target='ref:' + other['ref'])
    check('pair approval starts a pending handshake',lambda:equal(handshake['handshake']=='pending' and handshake['purpose']=='handshake',True))
    task = operation(other,'xsm_inbox',message_ids=[handshake['id']])
    operation(other,'xsm_ack',tokens=[c['token'] for c in task['claims']])
    operation(other,'xsm_send',target='ref:' + owner['ref'],text='Fixture selected peer handshake',kind='reply',
        reply_to=handshake['id'],outcome='succeeded',request_id='selection-handshake-reply',wake='never',wait=0)
    recovered = operation(owner,'xsm_connect',target='ref:' + other['ref'],request_id=handshake['id'])
    check('handshake recovery is live rather than cached approval output',lambda:equal(recovered['handshake']=='completed' and
        [c['id'] for c in recovered['claims']]==['selection-handshake-reply'],True))
    operation(owner,'xsm_ack',tokens=[c['token'] for c in recovered['claims']])
    check('withdrawal hides publication without revoking pair',lambda:equal(operation(owner,'xsm_publish',visible=False)['status']=='hidden' and
        operation(owner,'xsm_connect',target='ref:' + other['ref'],request_id=handshake['id'])['handshake']=='completed',True))
    renewed = operation(owner,'xsm_publish')
    check('republish requires a fresh host question',lambda:equal(renewed['status']=='waiting-for-user' and renewed['decision_id']!=pending['decision_id'],True))
    denied = peer.notification()['params'];answer(denied,'deny')
    check('publication denial cannot reapply old allow',lambda:equal(operation(owner,'xsm_publish')['status']=='refused' and not visible(),True))
    no_ui = peer.call('session.open',dict(params,conversation='selection-no-ui'))
    check('host without UI retains selection required',lambda:equal(operation(no_ui,'xsm_publish')['status'],'selection-required'))


def correlated_questions(peer, owner, recipient, check, equal):
    def operation(session, name, **arguments):
        return peer.call('operation.call', dict(session=session['session'], operation=name, arguments=arguments))
    def status(session, ident):
        return operation(session, 'xsm_question_status', id=ident)
    check('question request listing starts empty', lambda: equal(operation(owner, 'xsm_question_status')['requests'], []))
    asked = operation(owner, 'xsm_ask', targets=['ref:' + recipient['ref'], 'ref:000000'],
                      text='Fixture private group question', wake='never', wait=0)
    check('group question preserves pending and skipped recipients', lambda: equal(asked['group'] is True and
          asked['status'] == 'pending' and asked['asked'] == 1 and asked['skipped'] == 1 and
          len(asked['waiting_on']) == 1, True))
    child = next(row['id'] for row in asked['recipients'] if row['status'] != 'skipped')
    def foreign_refusal():
        denied = status(recipient, asked['id'])
        equal(denied['status'] == 'refused' and denied['replies'] == [] and
              denied['recipients'] == [] and denied['claims'] == [], True)
    check('foreign group status is a scoped refusal', foreign_refusal)
    original = operation(recipient, 'xsm_inbox', message_ids=[child])
    check('foreign status does not consume original question', lambda: equal(
          [claim['id'] for claim in original['claims']], [child]))
    operation(recipient, 'xsm_ack', tokens=[claim['token'] for claim in original['claims']])
    partial_body = 'Fixture private progress without final outcome'
    operation(recipient, 'xsm_send', target='ref:' + owner['ref'], text=partial_body, kind='reply',
              reply_to=child, request_id='question-partial-reply', wake='never', wait=0)
    partial = status(owner, asked['id'])
    check('partial group answer is not a final task outcome', lambda: equal(partial['status'] == 'replied' and
          partial['recipients'][0]['final'] is False and partial['replies'][0]['body'] == partial_body, True))
    check('question status returns exact reply ACK claims', lambda: equal(
          [claim['id'] for claim in partial['claims']], ['question-partial-reply']))
    operation(owner, 'xsm_ack', tokens=[claim['token'] for claim in partial['claims']])
    retained = status(owner, asked['id'])
    check('ACK retains indexed group answer without a new claim', lambda: equal(
          [reply['body'] for reply in retained['replies']] == [partial_body] and retained['claims'] == [], True))
    operation(recipient, 'xsm_send', target='ref:' + owner['ref'], text='Fixture private final answer',
              kind='reply', reply_to=child, outcome='succeeded', request_id='question-final-reply', wake='never', wait=0)
    final = status(owner, asked['id'])
    check('final group answer retains partial history and exact new claim', lambda: equal(final['status'] == 'final' and
          len(final['replies']) == 2 and final['recipients'][0]['final_outcome'] == 'succeeded' and
          [claim['id'] for claim in final['claims']] == ['question-final-reply'], True))
    def no_private_home(value):
        if isinstance(value, dict):
            return 'home' not in value and all(no_private_home(v) for v in value.values())
        return not isinstance(value, list) or all(no_private_home(v) for v in value)
    check('question reply handles expose opaque homes only', lambda: equal(no_private_home(final) and
          len(final['replies'][0]['sender']['home_id']) == 64, True))
    check('foreign group remains unreadable after private answers', foreign_refusal)
    operation(owner, 'xsm_ack', tokens=[claim['token'] for claim in final['claims']])
    check('absent single request has no replies or claims', lambda: equal(
          status(owner, 'absent-request')['status'] == 'not-found' and status(owner, 'absent-request')['claims'] == [], True))
    listed = operation(owner, 'xsm_question_status')['requests']
    check('request listing recovers owned child IDs without reply bodies', lambda: equal(
          child in [row['id'] for row in listed] and all('replies' not in row for row in listed), True))
    single = operation(owner, 'xsm_ask', target='ref:' + recipient['ref'], text='Fixture single timeout',
                       request_id='question-single-timeout', wake='never', wait=0)
    check('zero wait retains pending single question', lambda: equal(single['status'] == 'pending' and
          single['wait_end_reason'] == 'timeout' and single['wait_budget']['effective'] == 0, True))
    single_packet = operation(recipient, 'xsm_inbox', message_ids=[single['id']])
    check('question timeout does not cancel peer original', lambda: equal(
          [claim['id'] for claim in single_packet['claims']], [single['id']]))
    operation(recipient, 'xsm_ack', tokens=[claim['token'] for claim in single_packet['claims']])
    handshake = operation(owner, 'xsm_connect', target='ref:' + recipient['ref'], wait=0)
    check('existing scope alone does not complete handshake', lambda: equal(handshake['handshake'] == 'pending' and
          handshake['purpose'] == 'handshake', True))
    task = operation(recipient, 'xsm_inbox', message_ids=[handshake['id']])
    operation(recipient, 'xsm_ack', tokens=[claim['token'] for claim in task['claims']])
    operation(recipient, 'xsm_send', target='ref:' + owner['ref'], text='Fixture handshake reply', kind='reply',
              reply_to=handshake['id'], outcome='succeeded', request_id='question-handshake-reply', wake='never', wait=0)
    completed = operation(owner, 'xsm_connect', target='ref:' + recipient['ref'], request_id=handshake['id'], wait=0)
    check('selected peer reply completes the same handshake', lambda: equal(completed['handshake'] == 'completed' and
          [claim['id'] for claim in completed['claims']] == ['question-handshake-reply'], True))
    operation(owner, 'xsm_ack', tokens=[claim['token'] for claim in completed['claims']])


def sending(peer, sender, receiver, params, check, equal):
    def operation(owner, name, error=None, **arguments):
        return peer.call('operation.call', dict(session=owner['session'], operation=name,
                         arguments=arguments), error=error)
    def send(owner=sender, **arguments):
        return operation(owner, 'xsm_send', wait=0, wake='never', **arguments)
    target = 'ref:' + receiver['ref']
    refused = send(target='ref:000000', text='refused fixture')
    check('send refusal retains producer result', lambda: equal(refused['grouped'] is False and
          refused['send']['status'] == 'refused' and isinstance(refused['text'], str), True))
    body = 'Fixture stored before explicit consumption'
    original = send(target=target, text=body, request_id='send-contract-original')
    check('send storage is not native arrival or ACK', lambda: equal(original['grouped'] is False and
          original['send']['id'] == 'send-contract-original' and original['send']['status'] == 'stored' and
          original['send']['runtime_reached'] is False and original['send']['evidence']['stored'] is True and
          original['send']['evidence'].get('ack') is not True, True))
    packet = operation(receiver, 'xsm_inbox', message_ids=[original['send']['id']])
    claim = packet['claims'][0]
    peer.call('delivery.report', dict(session=receiver['session'], id=claim['id'],
              state='admitted', token=claim['token']))
    check('admission keeps original claim available', lambda: equal(operation(receiver, 'xsm_inbox',
          message_ids=[claim['id']])['claims'], packet['claims']))
    operation(receiver, 'xsm_ack', tokens=[claim['token']])
    replay = send(target=target, text=body, resend=claim['id'])
    check('consumed original refuses resend and retains ACK evidence', lambda: equal(replay['send']['id'] == claim['id'] and
          replay['send']['status'] == 'refused' and replay['send']['evidence']['ack'] is True and
          operation(receiver, 'xsm_inbox', message_ids=[claim['id']])['claims'] == [], True))
    other = peer.call('session.open', dict(params, conversation='send-contract-other'))
    other_target = 'ref:' + other['ref']
    group = send(targets=[target, other_target, 'ref:000000'], text='Fixture group body')
    rows = group['send']['recipients']
    check('group result keeps partial per recipient outcomes', lambda: equal(group['grouped'] is True and
          group['send']['status'] == 'refused' and len(rows) == 3 and
          [r['status'] for r in rows] == ['stored', 'stored', 'refused'] and rows[2]['id'] is None, True))
    check('group delivery IDs are independent of group ID', lambda: equal(len({
          group['send']['group'], rows[0]['id'], rows[1]['id']}) == 3, True))
    first_packet = operation(receiver, 'xsm_inbox', message_ids=[rows[0]['id']])
    check('group recipient sees its own original and other recipient note', lambda: equal(
          [c['id'] for c in first_packet['claims']] == [rows[0]['id']] and
          'also sent to:' in first_packet['messages'][0] and 'Fixture group body' in first_packet['messages'][0], True))
    operation(receiver, 'xsm_ack', tokens=[c['token'] for c in first_packet['claims']])
    other_packet = operation(other, 'xsm_inbox', message_ids=[rows[1]['id']])
    check('one group ACK does not consume another recipient', lambda: equal(
          [c['id'] for c in other_packet['claims']], [rows[1]['id']]))
    operation(other, 'xsm_ack', tokens=[c['token'] for c in other_packet['claims']])
    fresh = peer.call('session.open', dict(params, conversation='send-contract-fresh'))
    fresh_target = 'ref:' + fresh['ref']
    args = dict(target=fresh_target, text='Fixture frozen body', request_id='send-contract-files',
                attachments=[{'name': 'fixture.txt', 'text': 'Fixture frozen bytes'}])
    failure = operation(sender, 'xsm_send', error=-32602, wake='never', wait=0, **args)['data']['attachment_error']
    check('attachment refusal retains frozen recovery identity', lambda: equal(failure['body_sent'] is False and
          failure['request_id'] == args['request_id'] and isinstance(failure['manifest_id'], str), True))
    check('attachment refusal did not send a body', lambda: equal(operation(fresh, 'xsm_inbox')['claims'], []))
    copied = send(target=fresh_target, text=args['text'], request_id=args['request_id'], manifest_id=failure['manifest_id'])
    check('retry reuses frozen manifest as structured material', lambda: equal(copied['send']['id'] == args['request_id'] and
          copied['materials']['manifest_id'] == failure['manifest_id'] and copied['materials']['mode'] == 'files' and
          len(copied['materials']['references']) == 1 and copied['materials']['references'][0]['id'] == failure['manifest_id'], True))
    copied_packet = operation(fresh, 'xsm_inbox', message_ids=[copied['send']['id']])
    metadata = copied_packet['items'][0]['files']
    content = operation(fresh, 'xsm_files', storage_id=metadata['storage_id'], entry_id=metadata['files'][0]['id'])
    check('structured material drives receiver private copy read', lambda: equal(content['content'], 'Fixture frozen bytes'))
    operation(fresh, 'xsm_ack', tokens=[c['token'] for c in copied_packet['claims']])
    inline_owner = peer.call('session.open', dict(params, conversation='send-contract-inline'))
    inline = send(target='ref:' + inline_owner['ref'], text='Fixture inline body', request_id='send-contract-inline',
                  attachments=[{'name': 'inline.txt', 'text': 'Fixture inline bytes'}], attachment_fallback='inline')
    check('explicit inline fallback has no file references', lambda: equal(inline['materials']['mode'] == 'inline' and
          inline['materials']['references'] == [], True))
    inline_packet = operation(inline_owner, 'xsm_inbox', message_ids=[inline['send']['id']])
    check('inline fallback arrives as body rather than invented attachment', lambda: equal(
          'Fixture inline bytes' in inline_packet['messages'][0] and 'files' not in inline_packet['items'][0], True))
    operation(inline_owner, 'xsm_ack', tokens=[c['token'] for c in inline_packet['claims']])


def documents(peer, owner, check, equal):
    def operation(action, error=None, **arguments):
        return peer.call('operation.call', {'session': owner['session'], 'operation': 'xsm_doc',
                         'arguments': dict(doc='BOARD.md', action=action, **arguments)}, error=error)
    check('empty document log', lambda: equal(operation('log')['nodes'], []))
    first = operation('add', text='Fixture report: 한글 preserved', tags=['report'])['node']
    check('document add binds conversation author', lambda: equal(first['author_kind'] == 'agent' and
          first['body'] == 'Fixture report: 한글 preserved' and first['parents'] == [] and
          '[' + owner['ref'] + ']' in first['author'], True))
    check('document show returns immutable node', lambda: equal(operation('show', node=first['id'])['node'], first))
    hypothesis = operation('add', text='Fixture hypothesis', tags=['hypothesis'], parents=[first['id']])['node']
    logged = operation('log')['nodes']
    check('document log preserves predecessor and contributions', lambda: equal(len(logged) == 2 and
          {n['id'] for n in logged} == {first['id'], hypothesis['id']} and
          hypothesis['parents'] == [first['id']], True))
    check('document leaves retain graph frontier', lambda: equal(
          [n['id'] for n in operation('leaves')['nodes']], [hypothesis['id']]))
    held = operation('add', text='Fixture working declaration', tags=['wip'], parents=[hypothesis['id']])['node']
    candidates = operation('next')
    check('document next states order and no assignment', lambda: equal(candidates['doc'] == 'BOARD.md' and
          candidates['order'] == 'created' and candidates['assigns'] is False and candidates['total'] == 1, True))
    check('wip declaration neither hides nor becomes candidate', lambda: equal(candidates['candidates'], [{
          'id': hypothesis['id'], 'tags': hypothesis['tags'], 'author': hypothesis['author'], 't': hypothesis['t'],
          'why': ['unverified hypothesis'], 'wip': [held['author']]}]))
    operation('add', text='Fixture independent contribution', tags=['insight'])
    all_candidates = operation('next')
    limited = operation('next', limit=1)
    check('document next limit preserves total and prefix', lambda: equal(all_candidates['total'] == 2 and
          limited['total'] == 2 and len(all_candidates['candidates']) == 2 and
          limited['candidates'] == all_candidates['candidates'][:1], True))
    rendered = operation('render')
    check('document render reports complete node count', lambda: equal(rendered['nodes'] == 4 and
          first['body'] in rendered['text'], True))
    check('document rejects missing parent', lambda: operation('add', text='orphan', parents=['f' * 12], error=-32602))
    check('refused parent creates no contribution', lambda: equal(len(operation('log')['nodes']), 4))
    check('document rejects missing show node', lambda: operation('show', node='f' * 12, error=-32602))


def collaboration(peer, params, check, equal):
    """Public query projections and synthetic host decision, never a human UI test."""
    owner = peer.call('session.open', dict(params, conversation='board-owner', capabilities=['user-decisions']))
    def operation(name, **arguments):
        return peer.call('operation.call', {'session': owner['session'], 'operation': name, 'arguments': arguments})
    name = 'contract-probe'
    operation('xsm_team', action='create', team=name)
    listed = operation('xsm_team', action='list')['teams']
    check('team list contains public labels only', lambda: equal(len(listed) == 1 and
          set(listed[0]) == {'name', 'lead', 'members'} and listed[0]['name'] == name and
          listed[0]['lead'] is None and len(listed[0]['members']) == 1 and
          isinstance(listed[0]['members'][0], str), True))
    shown = operation('xsm_team', action='show', team=name)
    check('team show observes current member running', lambda: equal(shown['members'],
          [{'member': listed[0]['members'][0], 'running': True}]))
    check('empty board log', lambda: equal(operation('xsm_board', action='log', team=name)['nodes'], []))
    check('empty board decisions', lambda: equal(operation('xsm_board', action='decisions', team=name)['decisions'], []))
    item = 'decision: cache'
    body = 'Fixture contribution: 한글 preserved'
    operation('xsm_board', action='set', team=name, item=item, text=body)
    first = operation('xsm_board', action='log', team=name)['nodes']
    check('board log preserves item body and root', lambda: equal(len(first) == 1 and
          first[0]['body'] == body and first[0]['item'] == item and first[0]['parents'] == [], True))
    operation('xsm_board', action='set', team=name, item=item, text='Fixture revision')
    nodes = operation('xsm_board', action='log', team=name, item=item)['nodes']
    check('board update links observed predecessor', lambda: equal(len(nodes) == 2 and
          next(n for n in nodes if n['body'] == 'Fixture revision')['parents'] == [first[0]['id']], True))
    check('board item filter excludes other items', lambda: equal(
          operation('xsm_board', action='log', team=name, item='absent')['nodes'], []))
    args = dict(question='Fixture: cache strategy', options=['bounded', 'none'],
                decision_key='board-contract-answer', team=name, item=item)
    pending = operation('xsm_decide', **args)
    check('board decision status remains pending', lambda: equal(
          operation('xsm_decision_status', id=pending['decision_id'])['status'], 'pending'))
    event = peer.notification()['params']
    check('board decision waits for host answer', lambda: equal(pending['status'] == 'waiting-for-user' and
          pending['question_id'] == event['questionId'], True))
    peer.call('decision.response', dict(session=owner['session'], questionId=event['questionId'],
              challenge=event['challenge'], displayed=event['question'], action='accept',
              answer='bounded', source_id='synthetic-board-conformance-answer'))
    check('answer receipt does not write board decision', lambda: equal(
          operation('xsm_board', action='decisions', team=name)['decisions'], []))
    receipt = operation('xsm_decide', **args)
    check('board decision returns structured recorded receipt', lambda: equal(
          receipt['decision']['recorded'] is True and receipt['decision']['record']['answer'] == 'bounded', True))
    check('board decision replay preserves receipt', lambda: equal(operation('xsm_decide', **args), receipt))
    records = operation('xsm_board', action='decisions', team=name)['decisions']
    check('retry persists host sourced board decision', lambda: equal(len(records) == 1 and
          records[0]['answer'] == 'bounded' and records[0]['via'] == 'host-user' and
          records[0]['team'] == name and records[0]['item'] == item and
          records[0]['options'] == ['bounded', 'none'] and 'node' not in records[0] and
          'sync_notes' not in records[0], True))
    check('board receipt matches persisted projection', lambda: equal(receipt['decision']['record'], records[0]))
    final = operation('xsm_board', action='log', team=name, item=item)['nodes']
    check('decision reference resolves to persisted record', lambda: equal(len(final) == 3 and
          len([n for n in final if n.get('decision') == records[0]['id'] and n['author_kind'] == 'human']) == 1,
          True))


def decisions(peer, params, check, equal):
    ui_params = dict(params, conversation="decision-owner", capabilities=["user-decisions"])
    owner = peer.call("session.open", ui_params)
    foreign = peer.call("session.open", dict(ui_params, conversation="decision-foreign"))
    def operation(name, **arguments):
        return peer.call("operation.call", {"session": owner["session"], "operation": name, "arguments": arguments})
    args = {"question": "Fixture: choose a color", "options": ["blue", "green"], "decision_key": "wire-first"}
    pending = operation("xsm_decide", **args)
    event_frame = peer.notification()
    event = event_frame["params"]
    check("host question binds waiting operation", lambda: equal(event_frame["method"] == "decision/request" and
          pending["status"] == "waiting-for-user" and pending["decision_id"] == event["decisionId"] and
          pending["question_id"] == event["questionId"] and event["session"] == owner["session"], True))
    check("model result excludes private challenge", lambda: equal("challenge" not in pending and
          event["challenge"] not in json.dumps(pending), True))
    answer = dict(session=owner["session"], questionId=event["questionId"], challenge=event["challenge"],
                  displayed=event["question"], action="accept", answer="blue", source_id="conformance-fixture-answer")
    for name, changes, code in (
            ("foreign host cannot answer", {"session": foreign["session"]}, -32003),
            ("wrong challenge cannot answer", {"challenge": "forged"}, -32003),
            ("changed display cannot answer", {"displayed": "altered question"}, -32003),
            ("unlisted option cannot answer", {"answer": "red"}, -32602)):
        check(name, lambda changes=changes, code=code: peer.call("decision.response", dict(answer, **changes), error=code))
    status = operation("xsm_decision_status", id=pending["decision_id"])
    check("refused answers leave decision pending", lambda: equal(status["status"] == "pending" and status["answer"] is None, True))
    stored = peer.call("decision.response", answer)
    check("valid host answer is stored", lambda: equal(stored["status"], "answered"))
    status = operation("xsm_decision_status", id=pending["decision_id"])
    check("stored answer has host source and no applied effect", lambda: equal(status["status"] == "answered" and
          status["answer"]["source"] == "host-user" and not status["application"], True))
    check("identical answer replay is idempotent", lambda: equal(peer.call("decision.response", answer), stored))
    check("stored answer cannot be overwritten", lambda: peer.call("decision.response", dict(answer, answer="green"), error=-32003))
    applied = operation("xsm_decide", **args)
    check("no team answer has an explicit unrecorded receipt", lambda: equal(
          applied['decision'] == dict(recorded=False, question=args['question'], answer='blue',
              options=args['options'], via='host-user'), True))
    check("original operation retry applies stored answer", lambda: equal("blue" in json.dumps(applied) and
          operation("xsm_decision_status", id=pending["decision_id"])["status"] == "applied", True))
    second_args = dict(args, question="Fixture: another color", decision_key="wire-second")
    second = operation("xsm_decide", **second_args)
    abandoned = peer.notification()["params"]
    reused = dict(answer, questionId=abandoned["questionId"], challenge=abandoned["challenge"], displayed=abandoned["question"])
    check("applied answer source cannot answer another question", lambda:
          peer.call("decision.response", reused, error=-32003))
    route = {key: abandoned[key] for key in ("session", "questionId", "challenge")}
    check("abandon display does not decline decision", lambda: equal(peer.call("decision.abandon", route)["status"], "pending"))
    status = operation("xsm_decision_status", id=second["decision_id"])
    check("abandon leaves answer and application empty", lambda: equal(status["answer"] is None and not status["application"], True))
    retried = operation("xsm_decide", **second_args)
    fresh = peer.notification()["params"]
    check("abandoned decision retries with fresh display", lambda: equal(retried["decision_id"] == second["decision_id"] and
          fresh["questionId"] != abandoned["questionId"] and fresh["challenge"] != abandoned["challenge"], True))
    late = dict(answer, questionId=abandoned["questionId"], challenge=abandoned["challenge"], displayed=abandoned["question"])
    check("abandoned display cannot answer later", lambda: peer.call("decision.response", late, error=-32003))
    old_owner = owner
    peer.call("session.close", {"session": owner["session"]})
    check("closed host rejects late answer", lambda: peer.call("decision.response", answer, error=-32001))
    owner = peer.call("session.open", ui_params)
    renewed = operation("xsm_decide", **args)
    check("new generation cannot inherit prior answer", lambda: equal(owner["ref"] == old_owner["ref"] and
          owner["generation"] != old_owner["generation"] and renewed["status"] == "waiting-for-user" and
          renewed["decision_id"] != pending["decision_id"], True))
    cancelled_event = peer.notification()['params']
    check('applied decision cancellation does not undo effect', lambda: equal(
          operation('xsm_decision_status', id=pending['decision_id'], cancel=True)['status'], 'already-applied'))
    denied = peer.call('operation.call', dict(session=foreign['session'], operation='xsm_decision_status',
                       arguments={'id': pending['decision_id']}))
    check('foreign decision lookup reveals no record', lambda: equal(
          set(denied) <= {'id','status','inbox_pending','inbox_notice','inbox_pending_known','inbox_pending_diagnostics'}
          and denied['status'] == 'not-found', True))
    listed = operation('xsm_decision_status')
    check('decision listing retains own historical and current IDs', lambda: equal(
          {pending['decision_id'], renewed['decision_id']} <= {r['id'] for r in listed['decisions']}, True))
    check('pending cancellation leaves no answer or application', lambda: equal(
          operation('xsm_decision_status', id=renewed['decision_id'], cancel=True)['status'], 'cancelled'))
    check('cancelled display cannot accept a late answer', lambda: peer.call('decision.response',
          dict(answer, session=owner['session'], questionId=cancelled_event['questionId'],
               challenge=cancelled_event['challenge'], displayed=cancelled_event['question'],
               source_id='cancelled-decision-source'), error=-32003))
    foreign_list = peer.call('operation.call', dict(session=foreign['session'], operation='xsm_decision_status', arguments={}))
    check('foreign decision listing excludes owner history', lambda: equal(foreign_list['decisions'], []))
    publication = operation('xsm_publish')
    peer.notification()
    legacy = operation('xsm_decision_status', pending_consent=True)
    check('pending consent inspection is separate from approval', lambda: equal(
          len(legacy['requests']) == 1 and legacy['requests'][0]['status'] == 'pending', True))
    mark = legacy['requests'][0]['marker']
    check('closing consent returns exact requested marker', lambda: equal(
          operation('xsm_decision_status', drop_consent=mark)['closed'], mark))
    check('closing consent does not approve the host decision', lambda: equal(
          operation('xsm_decision_status', id=publication['decision_id'])['status'], 'pending'))
    check('closed consent no longer appears in pending list', lambda: equal(
          operation('xsm_decision_status', pending_consent=True)['requests'], []))
    operation('xsm_decision_status', id=publication['decision_id'], cancel=True)


def discovery(peer, first, second, check, equal):
    """Public directory observations only; never publish, connect or send."""
    def discover(**arguments):
        return peer.call('operation.call', {'session': first['session'],
            'operation': 'xsm_discover', 'arguments': arguments})
    peer.call('session.update', {'session': second['session'], 'state': 'idle',
                                'name': 'Independent discovery fixture'})
    result = discover()
    check('discovery status and partial observations', lambda: equal(
        result.get('status') in ('ok', 'unknown') and 'reason' in result
        and isinstance(result.get('unanswered'), dict), True))
    candidates = result.get('candidates')
    require(isinstance(candidates, list), result)
    selected = [row for row in candidates if row.get('ref') == second['ref']]
    check('same repository participant discovered', lambda: equal(len(selected), 1))
    row = selected[0]
    check('local candidate target and opaque identity', lambda: equal(
        row.get('target') == 'candidate:' + row.get('id', '')
        and len(row.get('id', '')) == 64 and row.get('machine') == 'local'
        and row.get('handle', {}).get('machine') == 'local'
        and row.get('handle', {}).get('runtime') == row.get('runtime')
        and row.get('is_self') is False, True))
    check('discovery exposes no local home or process identity', lambda: equal(
        not ({'home', 'cwd', 'pid', 'lstart'} & set(row))
        and set(row['handle']) == {'machine', 'runtime', 'home_id', 'session_id'}, True))
    check('discovery observations retain source and freshness', lambda: equal(all(
        isinstance(row.get(key), dict)
        and {'value', 'status', 'source', 'timestamp', 'observed_at', 'freshness'} <= set(row[key])
        for key in ('title', 'branch', 'summary', 'todo', 'activity', 'state', 'receive')), True))
    check('work filter selects named participant', lambda: equal(
        [candidate['ref'] for candidate in discover(work='Independent discovery fixture')['candidates']],
        [second['ref']]))
    check('unmatched branch returns no candidates', lambda: equal(
        discover(branch='unmatched-fixture-branch')['candidates'], []))
    peer.call('session.close', {'session': second['session']})
    check('closed participant leaves discovery', lambda: equal(
        second['ref'] not in [candidate['ref'] for candidate in discover()['candidates']], True))


def run(command, suite="lifecycle", capture=False):
    result = {"suite": "xsm-host-" + suite + "-v1", "status": "running", "checks": [], "activeCheck": None,
              "scope": "stdio negotiation and participation only; no operations, delivery or UI certification"}
    peers = []
    observations = [] if capture else None
    if capture:
        result["observations"] = observations
    with tempfile.TemporaryDirectory(prefix="xsm-conformance-") as folder:
        env = {key: os.environ[key] for key in ("PATH", "LANG", "TMPDIR", "SYSTEMROOT") if key in os.environ}
        env.update(HOME=folder, XSM_HOME=folder + "/state", CODEX_HOME=folder + "/codex",
                   CLAUDE_CONFIG_DIR=folder + "/claude", PYTHONDONTWRITEBYTECODE="1")
        def check(name, action):
            result["activeCheck"] = name
            action()
            result["checks"].append(name)
        def equal(actual, expected):
            require(actual == expected, {"actual": actual, "expected": expected})
        try:
            if suite == 'discovery':
                subprocess.run(['git', 'init', '-q', '-b', 'main', folder], env=env,
                               check=True, capture_output=True, timeout=5)
            a = Peer(command, folder, env, observations)
            peers.append(a)
            check("initialize required", lambda: a.call("operations/list", error=-32002))
            check("unsupported version refused", lambda: a.call("initialize", {"protocolVersion": "unsupported"}, error=-32002))
            check("version negotiated", lambda: equal(a.call("initialize", {"protocolVersion": "1"})["protocolVersion"], "1"))
            check("duplicate initialize refused", lambda: a.call("initialize", {"protocolVersion": "1"}, error=-32600))
            operations = a.call("operations/list")["operations"]
            check("operation descriptors", lambda: equal(all(isinstance(o.get("name"), str) and
                  isinstance(o.get("inputSchema"), dict) for o in operations) and bool(operations), True))
            params = dict(runtime="conformance", profile="isolated", conversation="a", cwd=folder,
                          capabilities=["messaging", "inbox"])
            check("native impersonation refused", lambda: a.call("session.open", dict(params, runtime="codex"), error=-32602))
            first = a.call("session.open", params)
            check("opaque participation fields", lambda: equal(all(isinstance(first.get(k), str) and
                  first[k] and folder not in first[k] for k in ("session", "generation", "ref")), True))
            check("immutable session identity", lambda: a.call("session.update", {"session": first["session"], "cwd": folder}, error=-32602))
            check("state update", lambda: equal(a.call("session.update", {"session": first["session"], "state": "busy"})["state"], "busy"))
            b = Peer(command, folder, env, observations)
            peers.append(b)
            initialization = b.call("initialize", {"protocolVersion": "1"})
            check("connection-local handles", lambda: b.call("session.update", {"session": first["session"], "state": "idle"}, error=-32001))
            check("single live conversation owner", lambda: b.call("session.open", params, error=-32003))
            other = a.call("session.open", dict(params, profile="other"))
            check("profile isolation", lambda: equal(other["ref"] != first["ref"], True))
            check("explicit close", lambda: equal(a.call("session.close", {"session": first["session"]}), {"closed": True}))
            check("closed handle refused", lambda: a.call("session.update", {"session": first["session"], "state": "idle"}, error=-32001))
            reopened = b.call("session.open", params)
            check("stable address new generation", lambda: equal(reopened["ref"] == first["ref"] and
                  reopened["generation"] != first["generation"] and reopened["session"] != first["session"], True))
            a.close()
            peers.remove(a)
            resumed = b.call("session.open", dict(params, profile="other"))
            check("EOF releases conversation ownership", lambda: equal(resumed["ref"] == other["ref"] and
                  resumed["generation"] != other["generation"], True))
            if suite in ("messaging", "events"):
                result["scope"] = "lifecycle and claim/queue/ACK recovery; no native delivery, UI or complete operations certification"
                messaging(b, reopened, resumed, dict(params, profile="other"), check, equal, events=suite == "events")
            if suite == "decisions":
                result["scope"] = "lifecycle and host decision binding fixture; no human UI or domain authorization certification"
                decisions(b, params, check, equal)
            if suite == 'uploads':
                result['scope'] = 'lifecycle and 4MiB public preparation/copy/ACK; no native UI, models or messenger certification'
                uploads(b, reopened, resumed, params, initialization['limits'], check, equal)
            if suite == 'discovery':
                result['scope'] = 'lifecycle and local public discovery; no physical remote, native UI or messenger certification'
                discovery(b, reopened, resumed, check, equal)
            if suite == 'approvals':
                result['scope'] = 'synthetic worker request answers through stdio; no worker execution or actual human/native UI certification'
                approvals(b, params, env, check, equal)
            if suite == 'grants':
                result['scope'] = 'lifecycle and synthetic host worker grant issuance/readback; no worker launch or actual dangerous mode'
                grants(b, params, check, equal)
            if suite == 'selection':
                result['scope'] = 'lifecycle and synthetic host publication/selection approval; no actual human, native runtime or physical network certification'
                selection_ui(b, params, env, check, equal)
            if suite == 'questions':
                result['scope'] = 'lifecycle and correlated question/group/handshake replies; no human approval or native runtime certification'
                correlated_questions(b, reopened, resumed, check, equal)
            if suite == 'sending':
                result['scope'] = 'lifecycle and send producer/group/material metadata; no native wake, human UI or physical remote certification'
                sending(b, reopened, resumed, params, check, equal)
            if suite == 'documents':
                result['scope'] = 'lifecycle and document graph operations; no native runtime, human endorsement or remote certification'
                documents(b, reopened, check, equal)
            if suite == 'collaboration':
                result['scope'] = 'lifecycle, team/board queries and synthetic host decision; no human or native UI certification'
                collaboration(b, params, check, equal)
            result.update(status="passed", activeCheck=None)
        except Exception as error:
            result.update(status="failed", error=repr(error))
        finally:
            result["diagnostics"] = [peer.close() for peer in peers]
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="store_true", help="include isolated wire observations in the report")
    parser.add_argument("--suite", choices=("lifecycle", "messaging", "events", "decisions", "uploads", "discovery", "collaboration", "documents", "sending", "questions", "selection", "grants", "approvals"), default="lifecycle")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--command", nargs=argparse.REMAINDER, required=True)
    args = parser.parse_args()
    if not args.command:
        parser.error("--command requires an executable")
    result = run(args.command, args.suite, args.capture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "checks": len(result["checks"]), "activeCheck": result["activeCheck"]}))
    raise SystemExit(0 if result["status"] == "passed" else 1)
