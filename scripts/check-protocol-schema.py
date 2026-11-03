#!/usr/bin/env python3
"""Validate public request artifacts with jsonschema (development-only dependency)."""
import argparse
import copy
import importlib.metadata
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[1]


def validate_send_result(value, schema):
    Draft202012Validator(schema).validate(value)
    materials = value.get('materials')
    if materials and materials['mode'] == 'files':
        ref = materials['references'][0]
        if ref['id'] != materials['manifest_id'] or ref['path'] != 'manifest:' + ref['id']:
            raise ValueError('send material reference differs from frozen manifest')


def validate_question_result(value, schema, operation=None, definition=None):
    binding = ({'$ref': '#/$defs/' + definition} if definition else
               {'anyOf': [{'$ref': '#/$defs/' + key} for key in schema['x-operationResults'][operation]]})
    Draft202012Validator(dict(binding, **{'$defs': schema['$defs']})).validate(value)
    def check_network(network):
        final = network.get('final_reply')
        if not final:
            return
        metadata = {k: final[k] for k in ('id', 'fingerprint', 'status', 'reply_to', 'outcome')}
        if metadata not in network['replies'] or final['reply_to'] != network['id']:
            raise ValueError('network final reply differs from returned metadata/request')
        packet = final.get('packet')
        if not packet:
            return
        if (packet['id'] != final['id'] or packet['fingerprint'] != final['fingerprint'] or
                packet['reply_to'] != final['reply_to'] or packet['outcome'] != final['outcome'] or
                packet['scope'] != 'network:' + packet['network_id'] or
                packet['reply_binding']['id'] != packet['reply_to']):
            raise ValueError('network packet differs from final reply binding')
        if packet['file_packet']:
            manifest = packet['file_packet']['manifest']
            ref = packet['attachments'][0]
            if (ref != dict(path='manifest:' + manifest['id'], **{k: manifest[k] for k in ('id', 'version', 'sha256', 'size')}) or
                    manifest['binding']['request_id'] != packet['id'] or
                    manifest['binding']['body_sha256'] != hashlib.sha256(packet['body'].encode('utf-8')).hexdigest()):
                raise ValueError('network file material differs from request binding')
    if definition == 'qNetworkDelivery':
        check_network(value)
        return
    singles = ([r for r in value['recipients'] if r['status'] != 'skipped'] if value.get('group')
               else [value] if 'purpose' in value else [])
    for row in singles:
        replies = row['replies']
        final = next((r['outcome'] for r in reversed(replies) if r['outcome'] in ('succeeded', 'failed')), None)
        if row['final'] != (final is not None) or row['final_outcome'] != final:
            raise ValueError('question final outcome differs from reply history')
        expected = ('completed' if final == 'succeeded' else 'declined' if final == 'failed' else
                    'reply_received' if replies else 'pending') if row['purpose'] == 'handshake' else 'not-started'
        if row['handshake'] != expected:
            raise ValueError('handshake status differs from correlated answers')
        if len({r['id'] for r in replies}) != len(replies):
            raise ValueError('question repeats a reply ID')
        if any(c['id'] not in {r['id'] for r in replies} for c in row.get('claims', [])):
            raise ValueError('question claim does not identify a returned reply')
    if value.get('group') and 'asked' in value:
        rows = value['recipients']
        asked = [r for r in rows if r['status'] != 'skipped']
        answered = [r for r in asked if r['replies']]
        ended = [r for r in asked if r['final'] or r['status'] in ('refused', 'selection-required', 'held', 'blocked', 'error', 'not-found')]
        waiting = [r for r in asked if r not in ended and not r['replies']]
        expected = ('refused' if not asked else 'final' if all(r['final'] for r in asked) else
                    ('reply_received' if waiting else 'replied') if answered else
                    'refused' if all(r in ended for r in asked) else 'pending')
        flattened = [dict(reply, request_id=r['id'], recipient=r['recipient']) for r in asked for reply in r['replies']]
        if (len({r['id'] for r in asked}) != len(asked) or
                len({r['id'] for r in flattened}) != len(flattened) or
                value['asked'] != len(asked) or value['answered'] != len(answered) or
                value['skipped'] != len(rows) - len(asked) or value['waiting_on'] != [r['recipient'] for r in waiting] or
                value['status'] != expected or value['replies'] != flattened or
                value['claims'] != [c for r in rows for c in r.get('claims', [])]):
            raise ValueError('question group aggregate differs from recipient results')
    if value.get('materials') and value['materials']['mode'] == 'files':
        m = value['materials']; ref = m['references'][0]
        if ref['id'] != m['manifest_id'] or ref['path'] != 'manifest:' + ref['id']:
            raise ValueError('question material differs from frozen manifest')
    if 'network_delivery' in value:
        check_network(value['network_delivery'])


def validate_decision_status(value, schema):
    Draft202012Validator(schema).validate(value)
    if 'question_digest' in value:
        def digest(text):
            return hashlib.sha256(json.dumps(text, sort_keys=True, ensure_ascii=False,
                separators=(',', ':')).encode('utf-8')).hexdigest()
        if value['question_digest'] != digest(value['question']):
            raise ValueError('decision question digest differs from text')
        display = value['display']
        for text, checksum in (('text', 'digest'), ('reported_text', 'reported_digest')):
            if checksum in display and (text not in display or display[checksum] != digest(display[text])):
                raise ValueError('decision display digest differs from text')
        if value['native_question'] not in (value['question'], '[xsm-decision:%s] %s' % (value['id'][:16], value['question'])):
            raise ValueError('decision native question differs from bound question')
        if value['status'] == 'applied':
            application = value['application']
            if not application or application.get('phase') == 'started' or 'observed_at' not in application:
                raise ValueError('applied decision has no observed application')
            if not value.get('permission_receipt') and display.get('complete') is not True:
                raise ValueError('applied decision has no complete display or permission receipt')
        if value['attention'] and value['attention']['id'] != value['id']:
            raise ValueError('decision attention belongs to a different decision')
    if 'requests' in value:
        for request in value['requests']:
            if request['marker'] != '[xsm:%s]' % request['id']:
                raise ValueError('consent marker differs from its request ID')


def output_contract(trace=None):
    schema = json.loads((ROOT / 'docs/protocol/output.schema.json').read_text())
    examples = json.loads((ROOT / 'docs/protocol/output-examples.json').read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    request_methods = json.loads((ROOT / 'docs/protocol/request.schema.json').read_text())['properties']['method']['enum']
    if set(schema['x-methodResults']) != set(request_methods):
        raise ValueError('output method result map differs from request inventory')
    example_methods = {entry['method'] for entry in examples if 'result' in entry['frame']}
    if example_methods != set(request_methods):
        raise ValueError('output examples omit a method result')
    inbox_schema = json.loads((ROOT / 'docs/protocol/inbox-result.schema.json').read_text())
    Draft202012Validator.check_schema(inbox_schema)
    inbox_validator = Draft202012Validator(inbox_schema)
    file_schema = json.loads((ROOT / 'docs/protocol/file-result.schema.json').read_text())
    Draft202012Validator.check_schema(file_schema)
    file_validator = Draft202012Validator(file_schema)
    ack_schema = json.loads((ROOT / 'docs/protocol/ack-result.schema.json').read_text())
    Draft202012Validator.check_schema(ack_schema)
    ack_validator = Draft202012Validator(ack_schema)
    discovery_schema = json.loads((ROOT / 'docs/protocol/discovery-result.schema.json').read_text())
    Draft202012Validator.check_schema(discovery_schema)
    discovery_validator = Draft202012Validator(discovery_schema)
    team_schema = json.loads((ROOT / 'docs/protocol/team-result.schema.json').read_text())
    Draft202012Validator.check_schema(team_schema)
    board_schema = json.loads((ROOT / 'docs/protocol/board-result.schema.json').read_text())
    Draft202012Validator.check_schema(board_schema)
    doc_schema = json.loads((ROOT / 'docs/protocol/doc-result.schema.json').read_text())
    Draft202012Validator.check_schema(doc_schema)
    send_schema = json.loads((ROOT / 'docs/protocol/send-result.schema.json').read_text())
    Draft202012Validator.check_schema(send_schema)
    question_schema = json.loads((ROOT / 'docs/protocol/question-result.schema.json').read_text())
    Draft202012Validator.check_schema(question_schema)
    publication_schema = json.loads((ROOT / 'docs/protocol/publication-result.schema.json').read_text())
    Draft202012Validator.check_schema(publication_schema)
    decision_schema = json.loads((ROOT / 'docs/protocol/decision-status-result.schema.json').read_text())
    Draft202012Validator.check_schema(decision_schema)
    grant_schema = json.loads((ROOT / 'docs/protocol/grant-result.schema.json').read_text())
    Draft202012Validator.check_schema(grant_schema)
    decide_schema = json.loads((ROOT / 'docs/protocol/decision-result.schema.json').read_text())
    Draft202012Validator.check_schema(decide_schema)
    approval_schema = json.loads((ROOT / 'docs/protocol/approval-result.schema.json').read_text())
    Draft202012Validator.check_schema(approval_schema)
    inbox_observed = 0
    inbox_empty = dict(messages=[], claims=[], items=[], inbox_pending=0)
    inbox_file = dict(messages=['fixture'], claims=[dict(id='original', token='opaque-token',
        owner=dict(type='native', id='opaque-owner'), generation='opaque-generation', digest='0' * 64)],
        items=[dict(id='original', kind='note', priority='next', wake=False, files=dict(
            storage_id='receiver-copy', manifest_id='source-manifest', version=1, sha256='0' * 64,
            files=[dict(id='entry', name='fixture.txt', size=0, sha256='0' * 64)]))], inbox_pending=0)
    for value in (inbox_empty, inbox_file):
        inbox_validator.validate(value)
    invalid_inbox = []
    bad = copy.deepcopy(inbox_file); del bad['items']; invalid_inbox.append(bad)
    bad = copy.deepcopy(inbox_file); bad['items'][0]['wake'] = 'never'; invalid_inbox.append(bad)
    bad = copy.deepcopy(inbox_file); del bad['items'][0]['files']['storage_id']; invalid_inbox.append(bad)
    bad = copy.deepcopy(inbox_file); bad['items'][0]['files']['files'][0]['size'] = '0'; invalid_inbox.append(bad)
    bad = copy.deepcopy(inbox_file); bad['items'][0]['files']['sha256'] = 'not-a-checksum'; invalid_inbox.append(bad)
    bad = copy.deepcopy(inbox_file); bad['claims'][0]['token'] = None; invalid_inbox.append(bad)
    bad = copy.deepcopy(inbox_empty); bad['inbox_pending'] = '0'; invalid_inbox.append(bad)
    for value in invalid_inbox:
        if inbox_validator.is_valid(value):
            raise ValueError('invalid inbox contract accepted: ' + repr(value))
    def validate(observation):
        nonlocal inbox_observed
        frame = observation['frame']
        validator.validate(frame)
        if observation.get('operation') in ('xsm_send', 'xsm_ask', 'xsm_connect', 'xsm_question_status') and 'error' in frame:
            data = frame['error'].get('data')
            if isinstance(data, dict) and 'attachment_error' in data:
                Draft202012Validator({'$ref': '#/$defs/attachmentError',
                                      '$defs': send_schema['$defs']}).validate(data['attachment_error'])
        if 'result' in frame:
            definition = schema['x-methodResults'][observation['method']]
            Draft202012Validator({'$ref': definition, '$defs': schema['$defs']}).validate(frame['result'])
            if observation.get('operation') == 'xsm_grant':
                Draft202012Validator(grant_schema).validate(frame['result'])
            if observation.get('operation') == 'xsm_decide':
                Draft202012Validator(decide_schema).validate(frame['result'])
            if observation.get('operation') == 'xsm_approve':
                Draft202012Validator(approval_schema).validate(frame['result'])
            if observation.get('operation') == 'xsm_decision_status':
                validate_decision_status(frame['result'], decision_schema)
            if observation.get('operation') == 'xsm_publish':
                Draft202012Validator(publication_schema).validate(frame['result'])
            if observation.get('operation') in question_schema['x-operationResults']:
                validate_question_result(frame['result'], question_schema, operation=observation['operation'])
            if observation.get('operation') == 'xsm_send':
                validate_send_result(frame['result'], send_schema)
            if observation.get('operation') == 'xsm_inbox':
                inbox_validator.validate(frame['result'])
                if [item['id'] for item in frame['result']['items']] != [claim['id'] for claim in frame['result']['claims']]:
                    raise ValueError('inbox item IDs differ from claimed originals')
                inbox_observed += 1
            if observation.get('operation') == 'xsm_files':
                file_validator.validate(frame['result'])
            if observation.get('operation') == 'xsm_ack':
                ack_validator.validate(frame['result'])
            if observation.get('operation') == 'xsm_doc':
                action = observation.get('action')
                if action not in doc_schema['x-actionResults']:
                    raise ValueError('document observation lacks a declared action')
                Draft202012Validator({'$ref': doc_schema['x-actionResults'][action],
                                      '$defs': doc_schema['$defs']}).validate(frame['result'])
            if observation.get('operation') == 'xsm_board' and observation.get('action') in ('log', 'decisions'):
                Draft202012Validator({'$ref': '#/$defs/' + observation['action'],
                                      '$defs': board_schema['$defs']}).validate(frame['result'])
            if observation.get('operation') == 'xsm_team' and observation.get('action') in ('list', 'show'):
                Draft202012Validator({'$ref': '#/$defs/' + observation['action'],
                                      '$defs': team_schema['$defs']}).validate(frame['result'])
            if observation.get('operation') == 'xsm_discover':
                discovery_validator.validate(frame['result'])
    for example in examples:
        validate(example)
    error = next(copy.deepcopy(e['frame']) for e in examples if 'error' in e['frame'])
    event = next(copy.deepcopy(e['frame']) for e in examples if e['frame'].get('method') == 'events/available')
    question = next(copy.deepcopy(e['frame']) for e in examples if e['frame'].get('method') == 'decision/request')
    bad_question = copy.deepcopy(question)
    del bad_question['params']['challenge']
    bad_error = copy.deepcopy(error)
    del bad_error['error']['message']
    invalid = [dict(error, result={}), dict(error, id=True), bad_error,
               dict(error, error={'code': 1.5, 'message': 'bad'}), dict(event, id=1),
               dict(event, method='unknown/notification'), bad_question,
               dict(event, params={'session': 's', 'ids': []})]
    for frame in invalid:
        if validator.is_valid(frame):
            raise ValueError('invalid output accepted: ' + repr(frame))
    delivery = Draft202012Validator({'$ref': schema['x-methodResults']['delivery.report'], '$defs': schema['$defs']})
    if delivery.is_valid({'recorded': 'admitted', 'acknowledged': True}):
        raise ValueError('admission incorrectly permits acknowledged=true')
    operation = Draft202012Validator({'$ref': schema['x-methodResults']['operation.call'], '$defs': schema['$defs']})
    bad_operation_results = (True, 17, ['not-an-object'], 'unwrapped text', None)
    for value in bad_operation_results:
        if operation.is_valid(value):
            raise ValueError('non-object operation result accepted: ' + repr(value))
    traces = [] if trace is None else [trace] if isinstance(trace, Path) else trace
    observations = [observation for filename in traces
                    for observation in json.loads(filename.read_text())['observations']]
    for observation in observations:
        validate(observation)
    return dict(examples=len(examples), rejected=len(invalid) + 1 + len(bad_operation_results), observed=len(observations),
                inboxExamples=2, inboxRejected=len(invalid_inbox), observedInboxResults=inbox_observed, observedSuccessfulMethods=sorted({o['method'] for o in observations if 'result' in o['frame']}),
                observedNotifications=sum('method' in o['frame'] for o in observations))


def ack_contract():
    schema = json.loads((ROOT / 'docs/protocol/ack-result.schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    examples = [dict(acked=[], inbox_pending=0),
                dict(acked=['original', 'original'], inbox_pending=1, inbox_notice='one pending'),
                dict(acked=['original'], inbox_pending=None, inbox_pending_known=0,
                     inbox_pending_diagnostics=['pending-unavailable:OSError'])]
    for value in examples:
        validator.validate(value)
    invalid = [dict(inbox_pending=0), dict(acked=[], inbox_pending=-1),
               dict(acked=['original\n'], inbox_pending=0),
               dict(acked=[True], inbox_pending=0), dict(acked=['a' * 161], inbox_pending=0),
               dict(acked=[], inbox_pending=True), dict(acked=[], inbox_pending=0, consumed=True)]
    for value in invalid:
        if validator.is_valid(value):
            raise ValueError('invalid ACK result accepted: ' + repr(value))
    return dict(examples=len(examples), rejected=len(invalid),
                scope='successful result structure; batch errors may follow earlier durable acknowledgements')


def grant_contract():
    schema = json.loads((ROOT / 'docs/protocol/grant-result.schema.json').read_text())
    examples = json.loads((ROOT / 'docs/protocol/grant-result-examples.json').read_text())
    Draft202012Validator.check_schema(schema)
    question = json.loads((ROOT / 'docs/protocol/question-result.schema.json').read_text())
    if schema['$defs']['awaiting'] != question['$defs']['qAwaiting']:
        raise ValueError('grant pending structure differs from question contract')
    validator = Draft202012Validator(schema)
    for example in examples:
        validator.validate(example['result'])
    issued = next(e['result'] for e in examples if 'grant' in e['result'])
    pending = next(e['result'] for e in examples if e['result'].get('status') == 'waiting-for-user')
    invalid = []
    for path, value in ((['grant','id'],'../victim'),(['grant','id'],'a'*8+'\n'),
                        (['grant','single_use'],False),(['grant','options'],[]),
                        (['grant','options'],['invented_mode']),(['grant','expires_at'],True),
                        (['grant','answer'],'must not leak private verdict'),(['extra'],'unknown')):
        bad = copy.deepcopy(issued);target = bad
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value;invalid.append(bad)
    bad = copy.deepcopy(pending); bad['challenge']='host-only'; invalid.append(bad)
    bad = copy.deepcopy(issued); del bad['grant']['asked_by']; invalid.append(bad)
    for value in invalid:
        if validator.is_valid(value):
            raise ValueError('invalid grant result accepted')
    return dict(examples=len(examples), rejected=len(invalid))


def decide_contract():
    schema = json.loads((ROOT / 'docs/protocol/decision-result.schema.json').read_text())
    examples = json.loads((ROOT / 'docs/protocol/decision-result-examples.json').read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    for example in examples:
        validator.validate(example['result'])
    recorded = next(e['result'] for e in examples if e['result'].get('decision', {}).get('recorded'))
    invalid = []
    for path, value in ((['decision','recorded'],False),(['decision','record','id'],'../record'),
                        (['decision','record','t'],True),(['decision','record','via'],'agent-supplied'),
                        (['decision','record','answer'],None),(['decision','node'],'../node'),
                        (['decision','sync_notes'],[7]),(['decision','record','private_path'],'/secret')):
        bad = copy.deepcopy(recorded); target = bad
        for key in path[:-1]: target = target[key]
        target[path[-1]] = value; invalid.append(bad)
    bad = copy.deepcopy(recorded); del bad['decision']['record']['id']; invalid.append(bad)
    for bad in invalid:
        if validator.is_valid(bad):
            raise ValueError('invalid decision result accepted: ' + repr(bad))
    question = json.loads((ROOT / 'docs/protocol/question-result.schema.json').read_text())
    if schema['$defs']['awaiting'] != question['$defs']['qAwaiting']:
        raise ValueError('decision pending differs from question contract')
    board = json.loads((ROOT / 'docs/protocol/board-result.schema.json').read_text())['$defs']['decision']
    expected = copy.deepcopy(board); expected['properties'].pop('from_machine')
    if schema['$defs']['record'] != expected:
        raise ValueError('decision receipt differs from local board projection')
    return dict(examples=len(examples), rejected=len(invalid))


def approval_contract():
    schema = json.loads((ROOT / 'docs/protocol/approval-result.schema.json').read_text())
    examples = json.loads((ROOT / 'docs/protocol/approval-result-examples.json').read_text())
    Draft202012Validator.check_schema(schema)
    question = json.loads((ROOT / 'docs/protocol/question-result.schema.json').read_text())
    if schema['$defs']['awaiting'] != question['$defs']['qAwaiting']:
        raise ValueError('approval pending structure differs from question contract')
    validator = Draft202012Validator(schema)
    for example in examples:
        validator.validate(example['result'])
    issued = next(e['result'] for e in examples if 'approval' in e['result'])
    denied = next(e['result'] for e in examples if e['result'].get('approval', {}).get('status') == 'denied')
    pending = next(e['result'] for e in examples if e['result'].get('status') == 'waiting-for-user')
    invalid = []
    for path, value in ((['approval','id'],'../victim'),(['approval','id'],'a'*8+'_\n'),
                        (['approval','id'],'a'*161),(['approval','status'],'allowed'),
                        (['approval','via'],'invented-source'),(['approval','answered_at'],True),
                        (['approval','worker'],'bad worker name'),(['approval','answer'],'private verdict'),
                        (['extra'],'unknown')):
        bad = copy.deepcopy(issued); target = bad
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value; invalid.append(bad)
    bad = copy.deepcopy(issued); del bad['approval']['answered_at']; invalid.append(bad)
    bad = copy.deepcopy(pending); bad['challenge'] = 'host-only'; invalid.append(bad)
    bad = copy.deepcopy(denied); bad['approval']['reason'] = 7; invalid.append(bad)
    for value in invalid:
        if validator.is_valid(value):
            raise ValueError('invalid approval result accepted: ' + repr(value))
    return dict(examples=len(examples), rejected=len(invalid))


def decision_status_contract():
    schema = json.loads((ROOT / 'docs/protocol/decision-status-result.schema.json').read_text())
    examples = json.loads((ROOT / 'docs/protocol/decision-status-result-examples.json').read_text())
    Draft202012Validator.check_schema(schema)
    inbox = json.loads((ROOT / 'docs/protocol/inbox-result.schema.json').read_text())
    if schema['$defs']['claim'] != inbox['$defs']['claim']:
        raise ValueError('decision status claim structure differs from inbox')
    for example in examples:
        validate_decision_status(example['result'], schema)
    def sample(predicate):
        return next(e['result'] for e in examples if predicate(e['result']))
    pending = sample(lambda v: v.get('status') == 'pending' and v.get('display', {}).get('status') == 'requested')
    applied = sample(lambda v: v.get('status') == 'applied' and v.get('application', {}).get('phase') == 'completed')
    attention = sample(lambda v: bool(v.get('attention')))
    legacy = sample(lambda v: bool(v.get('requests')) and bool(v.get('unbound')))
    blocked = sample(lambda v: v.get('status') == 'application-started')
    invalid = []
    for source, path, value in (
            (pending, ['display', 'human_saw'], True),
            (pending, ['question_digest'], '0' * 64),
            (pending, ['native_question'], 'unbound question'),
            (pending, ['display', 'digest'], '0' * 64),
            (pending, ['status'], 'permission-granted'),
            (applied, ['application'], None),
            (applied, ['display', 'complete'], False),
            (applied, ['application', 'observed_at'], 'now'),
            (applied, ['answer', 'recorded_at'], True),
            (attention, ['attention', 'human_saw'], True),
            (attention, ['attention', 'id'], '0' * 64),
            (attention, ['attention', 'observed_display_range'], [0, 100]),
            (legacy, ['requests', 0, 'marker'], '[xsm:wrong]'),
            (legacy, ['unbound', 0, 't'], 'now'),
            (blocked, ['undo'], True)):
        bad = copy.deepcopy(source)
        target = bad
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        invalid.append(bad)
    bad = copy.deepcopy(pending); del bad['scope']; invalid.append(bad)
    for value in invalid:
        try:
            validate_decision_status(value, schema)
        except (ValueError, ValidationError):
            pass
        else:
            raise ValueError('invalid decision status accepted')
    return dict(examples=len(examples), rejected=len(invalid))


def publication_contract():
    schema = json.loads((ROOT / 'docs/protocol/publication-result.schema.json').read_text())
    examples = json.loads((ROOT / 'docs/protocol/publication-result-examples.json').read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    inbox = json.loads((ROOT / 'docs/protocol/inbox-result.schema.json').read_text())
    question = json.loads((ROOT / 'docs/protocol/question-result.schema.json').read_text())
    if schema['$defs']['claim'] != inbox['$defs']['claim'] or schema['$defs']['awaiting'] != question['$defs']['qAwaiting']:
        raise ValueError('publication shared claim/waiting definitions differ')
    for example in examples:
        validator.validate(example['result'])
    results = {e['result']['status']: e['result'] for e in examples}
    invalid = [dict(results['published'], visible=False), dict(results['hidden'], visible=True),
               dict(results['selection-required'], visible=True), dict(results['refused'], visible=True),
               dict(results['published'], scope='invented grant'),
               dict(results['waiting-for-user'], challenge='must remain host-only')]
    bad = copy.deepcopy(results['waiting-for-user']); del bad['decision_id']; invalid.append(bad)
    bad = copy.deepcopy(results['refused']); del bad['reason']; invalid.append(bad)
    for value in invalid:
        if validator.is_valid(value):
            raise ValueError('invalid publication result accepted')
    return dict(examples=len(examples), rejected=len(invalid))


def question_contract():
    schema = json.loads((ROOT / 'docs/protocol/question-result.schema.json').read_text())
    examples = json.loads((ROOT / 'docs/protocol/question-result-examples.json').read_text())
    Draft202012Validator.check_schema(schema)
    expected = {'xsm_ask', 'xsm_question_status', 'xsm_connect'}
    if set(schema['x-operationResults']) != expected or {e['operation'] for e in examples if 'operation' in e} != expected:
        raise ValueError('question operation inventory differs from declared examples')
    for filename in ('inbox-result.schema.json', 'file-result.schema.json', 'send-result.schema.json'):
        for name, definition in json.loads((ROOT / 'docs/protocol' / filename).read_text())['$defs'].items():
            if schema['$defs'].get(name) != definition:
                raise ValueError('question shared definition differs: ' + name)
    for example in examples:
        validate_question_result(example['result'], schema, operation=example.get('operation'), definition=example.get('definition'))
    def sample(operation, predicate):
        return next(e for e in examples if e.get('operation') == operation and predicate(e['result']))
    final = sample('xsm_connect', lambda v: v.get('handshake') == 'completed')
    group = sample('xsm_question_status', lambda v: v.get('group') and v['status'] == 'final')
    listing = sample('xsm_question_status', lambda v: bool(v.get('requests')))
    selection = sample('xsm_connect', lambda v: v['status'] == 'selection-required')
    denied = sample('xsm_question_status', lambda v: v.get('group') and v['status'] == 'refused')
    network = next(e for e in examples if e.get('definition') == 'qNetworkDelivery' and e['result'].get('final_reply'))
    invalid = []
    for example, path, value in (
            (final, ['replies', 0, 'sender', 'home'], '/private/profile'),
            (final, ['replies', 0, 'outcome'], 'approved'),
            (final, ['claims', 0, 'token'], None),
            (final, ['claims', 0, 'id'], 'not-the-reply'),
            (final, ['handshake'], 'pending'),
            (final, ['wait_budget', 'effective'], 1),
            (group, ['claims'], []), (group, ['replies'], []),
            (group, ['asked'], -1), (group, ['waiting_on'], ['stale name']),
            (listing, ['requests', 0, 'target', 'home'], '/private/profile'),
            (selection, ['status'], 'permitted'), (denied, ['recipients'], [{}]),
            (network, ['final_reply', 'packet', 'sender', 'home'], '/private/profile'),
            (network, ['final_reply', 'packet', 'reply_binding', 'id'], 'wrong-original'),
            (network, ['final_reply', 'packet', 'file_packet', 'manifest', 'binding', 'request_id'], 'wrong-original'),
            (network, ['final_reply', 'packet', 'body'], 'changed bytes')):
        bad = copy.deepcopy(example)
        target = bad['result']
        for part in path[:-1]:
            target = target[part]
        target[path[-1]] = value
        invalid.append(bad)
    bad = copy.deepcopy(final); bad['result']['replies'].append(copy.deepcopy(bad['result']['replies'][0])); invalid.append(bad)
    bad = copy.deepcopy(group); del bad['result']['claims']; invalid.append(bad)
    bad = copy.deepcopy(listing); bad['operation'] = 'xsm_ask'; invalid.append(bad)
    for example in invalid:
        try:
            validate_question_result(example['result'], schema, operation=example.get('operation'), definition=example.get('definition'))
        except (ValueError, ValidationError):
            pass
        else:
            raise ValueError('invalid question result accepted')
    return dict(operations=len(schema['x-operationResults']), examples=len(examples), rejected=len(invalid))


def send_contract():
    schema = json.loads((ROOT / 'docs/protocol/send-result.schema.json').read_text())
    examples = json.loads((ROOT / 'docs/protocol/send-result-examples.json').read_text())
    Draft202012Validator.check_schema(schema)
    for value in examples:
        validate_send_result(value, schema)
    invalid = []
    for index, path, value in (
            (0, ['grouped'], True), (0, ['send', 'runtime_reached'], 'yes'),
            (0, ['send', 'evidence', 'ack'], 'true'), (0, ['send', 'id'], True),
            (0, ['send', 'acknowledged'], True), (0, ['send', 'status'], ''),
            (3, ['materials', 'references'], []),
            (3, ['materials', 'references', 0, 'size'], -1),
            (3, ['materials', 'references', 0, 'sha256'], 'not-a-digest'),
            (3, ['materials', 'references', 0, 'id'], 'c' * 32),
            (3, ['materials', 'references', 0, 'path'], 'manifest:' + 'c' * 32),
            (5, ['send', 'recipients', 0, 'spec'], None),
            (5, ['materials'], examples[3]['materials'])):
        bad = copy.deepcopy(examples[index])
        target = bad
        for part in path[:-1]:
            target = target[part]
        target[path[-1]] = value
        invalid.append(bad)
    bad = copy.deepcopy(examples[0]); del bad['send']['evidence']; invalid.append(bad)
    bad = copy.deepcopy(examples[0]); del bad['send']; invalid.append(bad)
    for value in invalid:
        try:
            validate_send_result(value, schema)
        except (ValueError, ValidationError):
            pass
        else:
            raise ValueError('invalid send result accepted: ' + repr(value))
    error = dict(status='attachment-error', code='reader-unknown', reason='fixture',
                 request_id='original', manifest_id='a' * 32, body_sent=False, recovery='reuse original')
    validator = Draft202012Validator({'$ref': '#/$defs/attachmentError', '$defs': schema['$defs']})
    validator.validate(error)
    rejected_errors = [dict(error, body_sent=True), dict(error, manifest_id=True)]
    for value in rejected_errors:
        if validator.is_valid(value):
            raise ValueError('invalid attachment failure accepted')
    return dict(examples=len(examples), rejected=len(invalid), attachmentErrors=1,
                rejectedAttachmentErrors=len(rejected_errors))


def doc_contract():
    schema = json.loads((ROOT / 'docs/protocol/doc-result.schema.json').read_text())
    examples = json.loads((ROOT / 'docs/protocol/doc-result-examples.json').read_text())
    Draft202012Validator.check_schema(schema)
    board = json.loads((ROOT / 'docs/protocol/board-result.schema.json').read_text())
    if schema['$defs']['node'] != board['$defs']['node']:
        raise ValueError('document and board node structures differ')
    inputs = json.loads((ROOT / 'docs/protocol/operations.schema.json').read_text())
    actions = inputs['$defs']['xsm_doc']['properties']['action']['enum']
    if set(schema['x-actionResults']) != set(actions) or {e['action'] for e in examples} != set(actions):
        raise ValueError('document result action inventory differs from requests/examples')
    validators = {action: Draft202012Validator({'$ref': ref, '$defs': schema['$defs']})
                  for action, ref in schema['x-actionResults'].items()}
    for example in examples:
        validators[example['action']].validate(example['result'])
    invalid = []
    for index, path, value in (
            (0, ['node', 'id'], 'not-a-node'),
            (0, ['node', 'parents'], [None]),
            (2, ['nodes'], 1),
            (4, ['nodes'], True),
            (4, ['text'], None),
            (5, ['order'], 'ranked'),
            (5, ['assigns'], True),
            (5, ['total'], -1),
            (5, ['candidates', 0, 'why'], ['assigned']),
            (5, ['candidates', 0, 'wip'], True),
            (5, ['candidates', 0, 'id'], 'a' * 12 + '\n'),
            (6, ['inbox_pending'], True)):
        bad = copy.deepcopy(examples[index]['result'])
        target = bad
        for part in path[:-1]:
            target = target[part]
        target[path[-1]] = value
        invalid.append((examples[index]['action'], bad))
    invalid.extend([('render', examples[2]['result']), ('log', examples[4]['result'])])
    for action, value in invalid:
        if validators[action].is_valid(value):
            raise ValueError('invalid document result accepted: ' + repr(value))
    return dict(actions=len(actions), examples=len(examples), rejected=len(invalid))


def board_contract():
    schema = json.loads((ROOT / 'docs/protocol/board-result.schema.json').read_text())
    examples = json.loads((ROOT / 'docs/protocol/board-result-examples.json').read_text())
    Draft202012Validator.check_schema(schema)
    validators = {action: Draft202012Validator({'$ref': '#/$defs/' + action,
                  '$defs': schema['$defs']}) for action in ('log', 'decisions')}
    for example in examples:
        validators[example['action']].validate(example['result'])
    invalid = []
    for index, path, value in (
            (1, ['nodes', 0, 'id'], 'not-a-node'),
            (1, ['nodes', 0, 'parents'], [True]),
            (1, ['nodes', 0, 'tags'], 'update'),
            (1, ['nodes', 0, 'body'], None),
            (1, ['nodes', 1, 'decision'], 'c' * 12 + '\n'),
            (3, ['decisions', 0, 't'], True),
            (3, ['decisions', 0, 'via'], 'model'),
            (3, ['decisions', 0, 'options'], [True]),
            (3, ['decisions', 0, 'answer'], None),
            (3, ['decisions', 0, 'node'], 'b' * 12),
            (3, ['inbox_pending'], -1),
            (4, ['decisions', 0, 'from_machine'], 'unverified-origin')):
        bad = copy.deepcopy(examples[index]['result'])
        target = bad
        for part in path[:-1]:
            target = target[part]
        target[path[-1]] = value
        invalid.append((examples[index]['action'], bad))
    for index, key, field in ((1, 'nodes', 'author'), (3, 'decisions', 'asked_by')):
        bad = copy.deepcopy(examples[index]['result'])
        del bad[key][0][field]
        invalid.append((examples[index]['action'], bad))
    invalid.extend([('log', examples[2]['result']), ('decisions', examples[0]['result'])])
    for action, value in invalid:
        if validators[action].is_valid(value):
            raise ValueError('invalid board result accepted: ' + repr(value))
    return dict(examples=len(examples), rejected=len(invalid))


def team_contract():
    schema = json.loads((ROOT / 'docs/protocol/team-result.schema.json').read_text())
    examples = json.loads((ROOT / 'docs/protocol/team-result-examples.json').read_text())
    Draft202012Validator.check_schema(schema)
    validators = {action: Draft202012Validator({'$ref': '#/$defs/' + action,
                  '$defs': schema['$defs']}) for action in ('list', 'show')}
    for example in examples:
        validators[example['action']].validate(example['result'])
    invalid = []
    for path, value in ((['members', 0, 'running'], 'yes'),
                        (['members', 0, 'home'], '/private/profile'),
                        (['name'], 'probe\n'), (['lead'], True),
                        (['inbox_pending'], -1)):
        bad = copy.deepcopy(examples[2]['result'])
        target = bad
        for part in path[:-1]:
            target = target[part]
        target[path[-1]] = value
        invalid.append(('show', bad))
    bad = copy.deepcopy(examples[2]['result'])
    del bad['members'][0]['running']
    invalid.append(('show', bad))
    invalid.extend([('list', examples[2]['result']), ('show', examples[0]['result']),
                    ('list', {'teams': [{'name': 'probe', 'lead': None, 'members': [{}]}]})])
    for action, value in invalid:
        if validators[action].is_valid(value):
            raise ValueError('invalid team result accepted: ' + repr(value))
    return dict(examples=len(examples), rejected=len(invalid))


def discovery_contract():
    schema = json.loads((ROOT / 'docs/protocol/discovery-result.schema.json').read_text())
    examples = json.loads((ROOT / 'docs/protocol/discovery-result-examples.json').read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    for value in examples:
        validator.validate(value)
    invalid = []
    def changed(path, value):
        candidate = copy.deepcopy(examples[1])
        target = candidate
        for part in path[:-1]:
            target = target[part]
        target[path[-1]] = value
        invalid.append(candidate)
    for path, value in (
        (['status'], 'complete'), (['unanswered'], {'read': True}),
        (['unanswered'], {'read': 0}), (['candidates', 0, 'home'], '/private/profile'),
        (['candidates', 0, 'handle', 'home'], '/private/profile'),
        (['candidates', 0, 'id'], 'not-an-opaque-id'),
        (['candidates', 0, 'runtime'], 'runtime\n'),
        (['candidates', 0, 'title', 'status'], 'certain'),
        (['candidates', 0, 'title', 'value'], 'claimed-known-without-known-status'),
        (['candidates', 0, 'title', 'freshness'], 'current'),
        (['candidates', 0, 'todo', 'value'], 'not-a-plan'),
        (['candidates', 1, 'handle', 'generation'], None),
        (['candidates', 1, 'origin_assurance'], 'unverified'),
        (['candidates', 1, 'is_self'], True)):
        changed(path, value)
    bad = copy.deepcopy(examples[1]); del bad['candidates'][1]['handle']['generation']; invalid.append(bad)
    bad = copy.deepcopy(examples[1]); del bad['candidates'][0]['receive']['source']; invalid.append(bad)
    for value in invalid:
        if validator.is_valid(value):
            raise ValueError('invalid discovery result accepted: ' + repr(value))
    return dict(examples=len(examples), rejected=len(invalid),
                scope='local/remote result structure; visibility and current selection require runtime revalidation')


def files_contract():
    schema = json.loads((ROOT / 'docs/protocol/file-result.schema.json').read_text())
    validator = Draft202012Validator(schema)
    manifest = dict(schema='xsm.files/v1', id='0' * 32, version=1, previous=None,
        owner=dict(runtime='fixture', home_id='0' * 64, session_id='opaque'),
        binding=dict(request_id='fixture', body_sha256='0' * 64), created_at=1, expires_at=2,
        files=[dict(id='1' * 32, version=1, name='copy', original_name='copy', source_version=None,
                    size=1, sha256='0' * 64, copy=True, input_source='caller-inline')], size=1, sha256='0' * 64)
    examples = [dict(storage_id='0' * 32, manifest=manifest),
                dict(storage_id='0' * 32, entry_id='1' * 32, encoding='text', content='a'),
                dict(storage_id='0' * 32, canonical_format='xsm.files/v1', manifest_sha256='0' * 64,
                     encoding='base64', content='e30=')]
    for value in examples:
        validator.validate(value)
    invalid = []
    bad = copy.deepcopy(examples[0]); bad['manifest']['files'][0]['path'] = '/not-an-owned-id'; invalid.append(bad)
    bad = copy.deepcopy(examples[0]); bad['manifest']['owner']['home_id'] += '\n'; invalid.append(bad)
    bad = copy.deepcopy(examples[0]); del bad['manifest']['binding']; invalid.append(bad)
    bad = copy.deepcopy(examples[0]); bad['manifest']['files'][0]['copy'] = False; invalid.append(bad)
    bad = copy.deepcopy(examples[1]); bad['entry_id'] += '\n'; invalid.append(bad)
    bad = copy.deepcopy(examples[1]); bad['content'] = 1; invalid.append(bad)
    bad = copy.deepcopy(examples[2]); bad['encoding'] = 'text'; invalid.append(bad)
    bad = copy.deepcopy(examples[2]); bad['entry_id'] = '1' * 32; invalid.append(bad)
    for value in invalid:
        if validator.is_valid(value):
            raise ValueError('invalid file result accepted: ' + repr(value))
    return dict(examples=len(examples), rejected=len(invalid), scope='structure only; fixture digests are not semantic checksum evidence')


def operations_contract():
    schema = json.loads((ROOT / 'docs/protocol/operations.schema.json').read_text())
    examples = json.loads((ROOT / 'docs/protocol/operation-examples.json').read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    names = schema['properties']['operation']['enum']
    if set(names) != set(schema['$defs']) or len(names) != len(examples) or set(names) != {e['operation'] for e in examples}:
        raise ValueError('operation inventory/examples differ')
    rejected = 0
    def invalid(value):
        nonlocal rejected
        if validator.is_valid(value):
            raise ValueError('invalid operation parameters accepted: ' + repr(value))
        rejected += 1
    for example in examples:
        validator.validate(example)
        bad = copy.deepcopy(example)
        bad['arguments']['unrecognized'] = True
        invalid(bad)
        definition = schema['$defs'][example['operation']]
        if definition.get('required'):
            invalid({key: value for key, value in example.items() if key != 'arguments'})
        for key in definition.get('required', []):
            bad = copy.deepcopy(example)
            del bad['arguments'][key]
            invalid(bad)
        for key in ('wait', 'wait_secs'):
            if key in definition['properties']:
                bad = copy.deepcopy(example)
                bad['arguments'][key] = 1
                invalid(bad)
        if 'answer_request' in definition['properties']:
            bad = copy.deepcopy(example)
            bad['arguments']['answer_request'] = 'unverified-transcript'
            invalid(bad)
    for action in ('decisions', 'sync'):
        validator.validate(dict(session='opaque-session', operation='xsm_board', arguments={'action': action, 'team': 'fixture'}))
    invalid(dict(session='opaque-session', operation='xsm_board', arguments={'action': 'decide', 'team': 'fixture'}))
    targeted = dict(session='opaque-session', operation='xsm_inbox', arguments={'message_ids': ['original-1']})
    validator.validate(targeted)
    for ids in (None, [], 'original-1', [True], ['../bad'], ['bad\n'], ['x' * 161], ['x'] * 101):
        invalid(dict(targeted, arguments={'message_ids': ids}))
    invalid(dict(examples[0], operation='unlisted-operation'))
    invalid(dict(examples[0], arguments=True))
    for name in ('xsm_send', 'xsm_ask'):
        bad = copy.deepcopy(next(e for e in examples if e['operation'] == name))
        bad['arguments']['attachments'] = [{'name': 'x', 'text': 'copied', 'unrecognized': True}]
        invalid(bad)
    return dict(operations=len(names), examples=len(examples), targetedInboxExamples=1, boardExtensionExamples=2, rejected=rejected,
                scope='structural inputs and transport restrictions; no domain effects or result certification')


def run(trace=None):
    schema = json.loads((ROOT / 'docs/protocol/request.schema.json').read_text())
    examples = json.loads((ROOT / 'docs/protocol/request-examples.json').read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    methods = schema['properties']['method']['enum']
    if len(methods) != len(set(methods)) or set(methods) != {value['method'] for value in examples}:
        raise ValueError('examples must cover every declared method exactly once')
    if len(examples) != len(methods):
        raise ValueError('duplicate or missing method examples')
    accepted = rejected = 0
    for example in examples:
        validator.validate(example)
        accepted += 1
        bad = copy.deepcopy(example)
        bad['params']['unrecognized'] = True
        if validator.is_valid(bad):
            raise ValueError('unknown field accepted for ' + example['method'])
        rejected += 1
        binding = next(item['then'] for item in schema['allOf']
                       if item['if']['properties']['method']['const'] == example['method'])
        definition = schema['$defs'][binding['properties']['params']['$ref'].split('/')[-1]]
        for required in definition['required']:
            bad = copy.deepcopy(example)
            del bad['params'][required]
            if validator.is_valid(bad):
                raise ValueError('missing required field accepted: ' + example['method'] + '/' + required)
            rejected += 1
    for changes in ({'id': True}, {'params': []}, {'method': 'unknown.method'}, {'extra': True}):
        bad = dict(examples[0], **changes)
        if validator.is_valid(bad):
            raise ValueError('invalid envelope accepted: ' + repr(changes))
        rejected += 1
    bad = next(copy.deepcopy(e) for e in examples if e['method'] == 'delivery.report')
    del bad['params']['token']
    if validator.is_valid(bad):
        raise ValueError('admitted report without claim token accepted')
    rejected += 1
    return dict(passed=True, methods=len(methods), accepted=accepted, rejected=rejected,
                validator='jsonschema', validatorVersion=importlib.metadata.version('jsonschema'),
                scope='request and output structures; no full operation results or semantic certification',
                output=output_contract(trace), operations=operations_contract(), files=files_contract(), ack=ack_contract(),
                discovery=discovery_contract(), team=team_contract(), board=board_contract(), doc=doc_contract(), send=send_contract(), question=question_contract(), publication=publication_contract(), decisionStatus=decision_status_contract(), grant=grant_contract(), approval=approval_contract(), decide=decide_contract())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wire-trace', type=Path, action='append')
    args = parser.parse_args()
    result = run(args.wire_trace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
