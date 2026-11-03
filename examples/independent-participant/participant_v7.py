"""Independent v7 JSONL transport. No xsm backend/SDK imports or ambient config reads."""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import threading
import time


class ContractError(ValueError):
    pass


def strict_json(raw):
    def pairs(entries):
        value = {}
        for key, item in entries:
            if key in value:
                raise ContractError('duplicate JSON member')
            value[key] = item
        return value
    def number(text):
        value = float(text)
        if not math.isfinite(value):
            raise ContractError('nonfinite number')
        return value
    def constant(text):
        raise ContractError('non-JSON constant')
    return json.loads(raw, object_pairs_hook=pairs, parse_float=number, parse_constant=constant)


class Consumer:
    """Public-schema validator is injected; transport and projections use stdlib only.

    A validator must raise on invalid data. Verification injects Draft202012Validator.
    Omitting it is intentionally refused, rather than claiming unchecked consumption.
    """
    names = {
        'owned': 'owned', 'files': 'file', 'decision_status': 'decision-status',
        'ask': 'question', 'question_status': 'question', 'connect': 'question',
        'discover': 'discovery', 'publish': 'publication', 'grant': 'grant',
        'send': 'send', 'team': 'team', 'handover': 'handover', 'board': 'board',
        'ack': 'ack', 'inbox': 'inbox', 'link': 'scope', 'join': 'scope',
        'reach': 'scope', 'doc': 'doc', 'doc_endorse': 'endorsement',
        'approve': 'approval', 'decide': 'decision'}

    def __init__(self, public_input, validate):
        self.root = Path(public_input) / 'docs/protocol'
        self.validate = validate
        self.schemas = {p.name: strict_json(p.read_text()) for p in self.root.glob('*.schema.json')}
        self.inventory = self.schemas['operations.schema.json']['properties']['operation']['enum']
        if set(self.inventory) != {'xsm_' + n for n in self.names}:
            raise ContractError('operation inventory mismatch')

    def check(self, schema, value, ref=None):
        if ref:
            schema = {'$ref': ref, '$defs': schema.get('$defs', {})}
        self.validate(schema, value)

    def frame(self, frame, method=None, params=None, expected_id=None):
        self.check(self.schemas['output.schema.json'], frame)
        if expected_id is not None and (type(frame.get('id')) is not int or frame['id'] != expected_id):
            raise ContractError('response correlation mismatch')
        if 'error' in frame:
            self.check(self.schemas['error.schema.json'], frame['error'])
            data = frame['error'].get('data')
            if isinstance(data, dict) and 'attachment_error' in data:
                self.check(self.schemas['send-result.schema.json'], data['attachment_error'], '#/$defs/attachmentError')
            return {'state': 'error-outcome-unknown', 'error': copy.deepcopy(frame['error']), 'retry': False}
        if 'id' not in frame:
            # Private UI events remain host-only. Never return challenge/display data.
            return {'state': 'host-question' if frame['method'] == 'decision/request' else 'availability-only'}
        if method:
            s = self.schemas['output.schema.json']
            self.check(s, frame['result'], s['x-methodResults'][method])
        if method == 'operation.call':
            return self.operation(params['operation'], params.get('arguments', {}), frame['result'])
        return {'state': 'wire-result', 'value': copy.deepcopy(frame['result'])}

    def action(self, operation, arguments):
        """Resolve only known original arguments; never infer action from a result.

        An empty dict means the caller actually omitted action. Missing original
        argument context must not be represented as an empty dict by a collector.
        """
        if not isinstance(arguments, dict):
            raise ContractError('original operation arguments required')
        catalog = self.schemas['operations.schema.json']['$defs'][operation]
        action_schema = catalog.get('properties', {}).get('action')
        result_schema = self.schemas[self.names[operation[4:]] + '-result.schema.json']
        if action_schema is None:
            return None
        defaults = [value for value in (action_schema.get('default'), result_schema.get('x-defaultAction')) if value is not None]
        if len(set(defaults)) > 1:
            raise ContractError('public action defaults disagree')
        action = arguments['action'] if 'action' in arguments else defaults[0] if defaults else None
        if action not in action_schema.get('enum', []):
            raise ContractError('missing or undeclared action')
        return action

    def operation(self, operation, arguments, value):
        if operation not in self.inventory:
            raise ContractError('unknown operation')
        action = self.action(operation, arguments)
        schema = self.schemas[self.names[operation[4:]] + '-result.schema.json']
        if 'x-actionResults' in schema:
            if action not in schema['x-actionResults']:
                raise ContractError('missing action result selector')
            self.check(schema, value, schema['x-actionResults'][action])
        elif 'x-operationResults' in schema:
            binding = {'anyOf': [{'$ref': '#/$defs/' + n} for n in schema['x-operationResults'][operation]], '$defs': schema['$defs']}
            self.check(binding, value)
        else:
            self.check(schema, value)
        if operation == 'xsm_owned':
            if action == 'status':
                # statusResult is intentionally a union; original request selects
                # history versus an exact retained task, even if root-valid.
                definition = 'taskResult' if 'request_id' in arguments else 'requestListing'
                self.check(schema, value, '#/$defs/' + definition)
            if action != 'create' and 'request_id' in arguments and value.get('id') != arguments['request_id']:
                raise ContractError('owned result belongs to another request')
        if operation in ('xsm_link', 'xsm_join', 'xsm_reach') and 'scope' in value:
            scope = value['scope']
            if scope['kind'] != {'xsm_link': 'link', 'xsm_join': 'membership', 'xsm_reach': 'reach'}[operation]:
                raise ContractError('scope operation mismatch')
            if 'removed' in scope and scope['changed'] != bool(scope['removed']):
                raise ContractError('scope removal mismatch')
        if operation == 'xsm_inbox' and [x['id'] for x in value['items']] != [x['id'] for x in value['claims']]:
            raise ContractError('inbox items/claims mismatch')
        if value.get('materials', {}).get('mode') == 'files':
            m = value['materials']; ref = m['references'][0]
            if ref['id'] != m['manifest_id'] or ref['path'] != 'manifest:' + ref['id']:
                raise ContractError('material manifest mismatch')
        if operation in ('xsm_ask', 'xsm_connect', 'xsm_question_status'):
            self.questions(value)
        if operation == 'xsm_decision_status' and 'question_digest' in value:
            digest = lambda text: hashlib.sha256(json.dumps(text, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
            if value['question_digest'] != digest(value['question']):
                raise ContractError('question digest mismatch')
            for a, b in [('text', 'digest'), ('reported_text', 'reported_digest')]:
                if b in value['display'] and value['display'][b] != digest(value['display'].get(a)):
                    raise ContractError('display digest mismatch')
            if value['native_question'] not in (value['question'], '[xsm-decision:%s] %s' % (value['id'][:16], value['question'])):
                raise ContractError('native question mismatch')
            if value['status'] == 'applied' and (not value['application'] or value['application'].get('phase') == 'started' or 'observed_at' not in value['application']):
                raise ContractError('applied without observation')
        if operation == 'xsm_handover' and 'handover' in value and value['handover']['action'] != action:
            raise ContractError('handover action mismatch')
        # Never infer authority from prose. Facts preserve distinct state dimensions.
        facts = {'state': 'structured-observation', 'operation': operation, 'retry': False,
                 'permission': 'not-established', 'business_success': None, 'acknowledged': None}
        if action is not None:
            facts['action'] = action
        if value.get('status') == 'waiting-for-user':
            return dict(facts, state='pending-human', decision_id=value['decision_id'], question_id=value['question_id'])
        if set(value) == {'text'}:
            return dict(facts, state='legacy-unconfirmed', text=value['text'])
        facts['value'] = copy.deepcopy(value)
        if operation in ('xsm_link', 'xsm_join', 'xsm_reach') and 'scope' in value: facts['state'] = 'scope-mutation-snapshot'
        if 'team_change' in value or 'board' in value: facts['state'] = 'collaboration-snapshot'
        if operation == 'xsm_decision_status':
            facts['answer_storage'] = value.get('answer')
            facts['application'] = value.get('application')
        if operation == 'xsm_owned':
            if action == 'create' and value.get('owned') is not True:
                raise ContractError('owned creation lacks service metadata')
            if action != 'create' and value.get('owned') is True:
                raise ContractError('owned service metadata substituted for task')
            facts['result_kind'] = 'service' if action == 'create' else 'history' if action == 'status' and 'request_id' not in arguments else 'task'
            facts.update(task_state=value.get('status'), outcome=(value.get('result') or {}).get('outcome'),
                         reply_id=value.get('reply_id'), reply_transport=value.get('send_evidence'), cancellation=value.get('cancellation'))
        if operation == 'xsm_send' and not value.get('grouped'):
            facts['acknowledged'] = value.get('send', {}).get('evidence', {}).get('ack')
        return facts

    def fragment(self, family, definition, value):
        schema = self.schemas[family + "-result.schema.json"]
        self.check(schema, value, "#/$defs/" + definition)
        if family == "question" and definition == "qNetworkDelivery":
            self.questions({"network_delivery": value})
        return {"state": "nested-observation", "value": copy.deepcopy(value)}

    def questions(self, value):
        network = value.get('network_delivery')
        if network and network.get('final_reply'):
            final = network['final_reply']
            metadata = {k: final[k] for k in ('id', 'fingerprint', 'status', 'reply_to', 'outcome')}
            if metadata not in network['replies'] or final['reply_to'] != network['id']:
                raise ContractError('network final reply mismatch')
            packet = final.get('packet')
            if packet:
                if any(packet[k] != final[k] for k in ('id','fingerprint','reply_to','outcome')) or packet['scope'] != 'network:' + packet['network_id'] or packet['reply_binding']['id'] != packet['reply_to']:
                    raise ContractError('network packet binding mismatch')
                if packet.get('file_packet'):
                    manifest = packet['file_packet']['manifest']; ref = packet['attachments'][0]
                    if ref != dict(path='manifest:'+manifest['id'], **{k:manifest[k] for k in ('id','version','sha256','size')}) or manifest['binding']['request_id'] != packet['id'] or manifest['binding']['body_sha256'] != hashlib.sha256(packet['body'].encode()).hexdigest():
                        raise ContractError('network file binding mismatch')
        rows = [r for r in value.get('recipients', []) if r['status'] != 'skipped'] if value.get('group') else [value] if 'purpose' in value else []
        for row in rows:
            replies = row['replies']
            final = next((r['outcome'] for r in reversed(replies) if r['outcome'] in ('succeeded', 'failed')), None)
            if row['final'] != (final is not None) or row['final_outcome'] != final:
                raise ContractError('question final differs from replies')
            expected = ('completed' if final == 'succeeded' else 'declined' if final == 'failed' else 'reply_received' if replies else 'pending') if row['purpose'] == 'handshake' else 'not-started'
            if row['handshake'] != expected or len({r['id'] for r in replies}) != len(replies):
                raise ContractError('handshake/reply mismatch')
            if any(c['id'] not in {r['id'] for r in replies} for c in row.get('claims', [])):
                raise ContractError('claim does not identify reply')

        if value.get('group') and 'asked' in value:
            rows = value['recipients']; asked = [r for r in rows if r['status'] != 'skipped']
            answered = [r for r in asked if r['replies']]
            ended = [r for r in asked if r['final'] or r['status'] in ('refused','selection-required','held','blocked','error','not-found')]
            waiting = [r for r in asked if r not in ended and not r['replies']]
            expected = ('refused' if not asked else 'final' if all(r['final'] for r in asked) else ('reply_received' if waiting else 'replied') if answered else 'refused' if all(r in ended for r in asked) else 'pending')
            flattened = [dict(reply, request_id=r['id'], recipient=r['recipient']) for r in asked for reply in r['replies']]
            if value['asked'] != len(asked) or value['answered'] != len(answered) or value['skipped'] != len(rows)-len(asked) or value['waiting_on'] != [r['recipient'] for r in waiting] or value['status'] != expected or value['replies'] != flattened or value['claims'] != [c for r in rows for c in r.get('claims',[])]:
                raise ContractError('group aggregation mismatch')


class Transport:
    """Serial request client; bounded frames, deadlines and host-only notifications.

    Executable argv is supplied by the operator, never extracted from peer data.
    All durable wire output is private test evidence, not a model result.
    """
    def __init__(self, command, cwd, env, consumer, evidence, timeout=8):
        self.consumer = consumer; self.timeout = timeout; self.serial = 0
        self.notifications = []; self.frames = queue.Queue(); self.lock = threading.Lock()
        root = Path(cwd).resolve()
        allowed = ('PATH', 'LANG', 'TMPDIR')
        child_env = {k: env[k] for k in allowed if k in env}
        for key in ('HOME', 'XSM_HOME', 'CODEX_HOME', 'CLAUDE_CONFIG_DIR'):
            path = Path(env[key])
            if not path.is_absolute() or not path.resolve().is_relative_to(root):
                raise ContractError('non-isolated ' + key)
            path.mkdir(parents=True, exist_ok=True)
            child_env[key] = str(path)
        self.evidence = Path(evidence); self.evidence.mkdir(parents=True, exist_ok=False)
        self.raw = (self.evidence / 'stdout.raw').open('wb')
        self.sent = (self.evidence / 'stdin.raw').open('wb')
        self.stderr = (self.evidence / 'stderr.raw').open('wb')
        self.observed = (self.evidence / 'wire.jsonl').open('w')
        self.process = subprocess.Popen(command, cwd=root, env=child_env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr)
        def read():
            try:
                while True:
                    raw = self.process.stdout.readline(4 * 1048576 + 1)
                    self.raw.write(raw); self.raw.flush()
                    if not raw: raise EOFError('peer EOF')
                    if not raw.endswith(b'\n') or len(raw) > 4 * 1048576: raise ContractError('oversized/truncated frame')
                    self.frames.put(strict_json(raw.decode('utf-8', errors='strict')))
            except Exception as exc: self.frames.put(exc)
        self.reader = threading.Thread(target=read, daemon=True); self.reader.start()

    def receive(self, deadline):
        try: value = self.frames.get(timeout=max(0, deadline-time.monotonic()))
        except queue.Empty: raise TimeoutError('RPC deadline') from None
        if isinstance(value, Exception): raise value
        return value

    def call(self, method, params=None):
        with self.lock:
            self.serial += 1
            request = dict(jsonrpc='2.0', id=self.serial, method=method, params=params or {})
            raw = (json.dumps(request, allow_nan=False) + '\n').encode()
            if len(raw.decode()) > 1048576: raise ContractError('request frame too large')
            self.sent.write(raw); self.sent.flush(); self.process.stdin.write(raw); self.process.stdin.flush()
            deadline = time.monotonic()+self.timeout
            while True:
                frame = self.receive(deadline)
                observation = dict(method=method, frame=frame)
                if method == 'operation.call': observation.update(operation=params['operation'], action=params.get('arguments', {}).get('action'))
                self.observed.write(json.dumps(observation) + '\n'); self.observed.flush()
                if isinstance(frame, dict) and 'id' not in frame:
                    self.consumer.frame(frame); self.notifications.append(frame); continue
                facts = self.consumer.frame(frame, method, params, self.serial)
                return frame, facts

    def notification(self):
        if self.notifications: return self.notifications.pop(0)
        value = self.receive(time.monotonic()+self.timeout)
        self.consumer.frame(value)
        if 'id' in value: raise ContractError('response when notification expected')
        self.observed.write(json.dumps({'frame': value})+'\n'); self.observed.flush()
        return value

    def close(self):
        if self.process.stdin and not self.process.stdin.closed: self.process.stdin.close()
        try: self.process.wait(timeout=3)
        except subprocess.TimeoutExpired: self.process.kill(); self.process.wait(timeout=3)
        self.reader.join(timeout=2)
        self.process.stdout.close()
        for f in (self.raw, self.sent, self.stderr, self.observed): f.close()
        return (self.evidence / 'stderr.raw').read_text(errors='replace')
