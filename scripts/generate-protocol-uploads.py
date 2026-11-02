#!/usr/bin/env python3
"""Add the bounded file-preparation extension to public request/output artifacts."""
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from xsm.file_uploads import UPLOAD_SCHEMAS, Uploads
from xsm.file_schema import definitions, result_schema


def write(name, value):
    (ROOT / 'docs/protocol' / name).write_text(json.dumps(value, indent=2) + '\n')


def read(name):
    return json.loads((ROOT / 'docs/protocol' / name).read_text())


def generate():
    request, examples = read('request.schema.json'), read('request-examples.json')
    outputs, output_examples = read('output.schema.json'), read('output-examples.json')
    claim = read('inbox-result.schema.json')['$defs']['claim']
    outputs['$defs'].update(definitions(claim))
    write('file-result.schema.json', result_schema(claim))
    methods = set(UPLOAD_SCHEMAS)
    request['properties']['method']['enum'] = [m for m in request['properties']['method']['enum'] if m not in methods]
    request['allOf'] = [rule for rule in request['allOf'] if rule['if']['properties']['method']['const'] not in methods]
    examples = [value for value in examples if value['method'] not in methods]
    output_examples = [value for value in output_examples if value.get('method') not in methods]
    string = {'type': 'string', 'minLength': 1}
    upload_id = {'type': 'string', 'pattern': '^[0-9a-f]{32}(?![\\s\\S])'}
    integer = {'type': 'integer', 'minimum': 0}
    def closed(properties, required):
        return {'type': 'object', 'properties': properties, 'required': required, 'additionalProperties': False}
    progress = closed({'state': {'const': 'uploading'}, 'upload': upload_id,
        'request_id': string, 'offsets': {'type': 'array', 'maxItems': 16, 'items': integer},
        'chunk_bytes': {'const': Uploads.CHUNK_BYTES}}, ['state', 'upload', 'request_id', 'offsets', 'chunk_bytes'])
    frozen = closed({'state': {'const': 'frozen'}, 'request_id': string, 'manifest_id': upload_id,
        'body_digest': {'type': 'string', 'pattern': '^[0-9a-f]{64}(?![\\s\\S])'},
        'manifest': {'$ref': '#/$defs/fileManifest'}, 'mode': {'enum': ['files', 'inline']},
        'references': {'type': 'array', 'maxItems': 1, 'items': {'$ref': '#/$defs/fileReference'}},
        'body_sent': {'const': False}}, ['state', 'request_id', 'manifest_id'])
    unknown = closed({'state': {'const': 'unknown'}, 'request_id': string}, ['state', 'request_id'])
    outputs['$defs']['uploadProgress'] = progress
    outputs['$defs']['uploadFrozen'] = frozen
    outputs['$defs']['uploadStatus'] = {'oneOf': [progress, frozen, unknown]}
    outputs['$defs']['uploadWrite'] = closed({'upload': upload_id, 'entry': integer, 'offset': integer}, ['upload', 'entry', 'offset'])
    outputs['$defs']['uploadAbort'] = closed({'aborted': {'const': True}, 'request_id': string,
        'body_sent': {'const': False}}, ['aborted', 'request_id', 'body_sent'])
    limit_properties = outputs['$defs']['initializeResult']['properties']['limits']['properties']
    for name, value in [('fileUploadChunkBytes', Uploads.CHUNK_BYTES), ('fileUploadBudgetBytes', 4194304), ('fileUploadSlots', Uploads.MAX_UPLOADS)]:
        limit_properties[name] = {'const': value}
    request_args = {
        'open': {'target': 'peer:' + '0' * 64, 'request_id': 'upload-fixture', 'text': 'body',
                 'entries': [{'name': 'copy.bin', 'size': 1, 'sha256': '0' * 64}]},
        'write': {'upload': '0' * 32, 'entry': 0, 'offset': 0, 'base64': 'YQ=='},
        'commit': {'upload': '0' * 32}, 'abort': {'upload': '0' * 32},
        'status': {'request_id': 'upload-fixture'},
    }
    results = {
        'open': {'state': 'uploading', 'upload': '0' * 32, 'request_id': 'upload-fixture', 'offsets': [0], 'chunk_bytes': Uploads.CHUNK_BYTES},
        'write': {'upload': '0' * 32, 'entry': 0, 'offset': 1},
        'commit': {'state': 'frozen', 'request_id': 'upload-fixture', 'manifest_id': '1' * 32, 'mode': 'files', 'references': [], 'body_sent': False},
        'status': {'state': 'unknown', 'request_id': 'upload-fixture'},
        'abort': {'aborted': True, 'request_id': 'upload-fixture', 'body_sent': False},
    }
    result_types = {'open': 'uploadStatus', 'write': 'uploadWrite', 'commit': 'uploadFrozen', 'status': 'uploadStatus', 'abort': 'uploadAbort'}
    for method, schema in UPLOAD_SCHEMAS.items():
        action = method.rsplit('.', 1)[1]
        definition = 'upload' + action.title()
        request['properties']['method']['enum'].append(method)
        request['$defs'][definition] = copy.deepcopy(schema)
        request['allOf'].append({'if': {'properties': {'method': {'const': method}}, 'required': ['method']},
            'then': {'properties': {'params': {'$ref': '#/$defs/' + definition}}, 'required': ['params']}})
        examples.append({'jsonrpc': '2.0', 'id': len(examples) + 1, 'method': method,
                         'params': dict(session='fixture-session', **request_args[action])})
        outputs['x-methodResults'][method] = '#/$defs/' + result_types[action]
        output_examples.append({'method': method, 'frame': {'jsonrpc': '2.0', 'id': len(output_examples) + 1, 'result': results[action]}})
    write('request.schema.json', request)
    write('request-examples.json', examples)
    write('output.schema.json', outputs)
    write('output-examples.json', output_examples)


if __name__ == '__main__':
    generate()
