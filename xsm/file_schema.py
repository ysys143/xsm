"""Public structural file-result definitions; checksum/ownership remain semantic checks."""
from __future__ import annotations

import copy


def definitions(claim):
    def closed(properties, required=None):
        return {'type': 'object', 'properties': properties,
                'required': list(properties) if required is None else required,
                'additionalProperties': False}
    identifier = {'type': 'string', 'pattern': '^[0-9a-f]{32}(?![\\s\\S])'}
    digest = {'type': 'string', 'pattern': '^[0-9a-f]{64}(?![\\s\\S])'}
    string = {'type': 'string', 'minLength': 1}
    version = {'type': 'integer', 'minimum': 1}
    result = {'fileClaim': copy.deepcopy(claim)}
    result['fileManifestEntry'] = closed({
        'id': identifier, 'version': version, 'name': string, 'original_name': string,
        'source_version': {'type': ['string', 'null']},
        'size': {'type': 'integer', 'minimum': 0, 'maximum': 1048576}, 'sha256': digest,
        'copy': {'const': True}, 'input_source': {'enum': ['cli-os-read', 'caller-inline']},
    })
    result['fileManifest'] = closed({
        'schema': {'const': 'xsm.files/v1'}, 'id': identifier, 'version': version,
        'previous': {'anyOf': [identifier, {'type': 'null'}]},
        'owner': closed({'runtime': string, 'home_id': digest, 'session_id': string}),
        'binding': closed({'request_id': string, 'body_sha256': digest}),
        'created_at': {'type': 'number', 'minimum': 0}, 'expires_at': {'type': 'number', 'exclusiveMinimum': 0},
        'files': {'type': 'array', 'maxItems': 16, 'items': {'$ref': '#/$defs/fileManifestEntry'}},
        'size': {'type': 'integer', 'minimum': 0, 'maximum': 4194304}, 'sha256': digest,
    })
    result['fileReference'] = closed({'path': {'type': 'string', 'pattern': '^manifest:[0-9a-f]{32}(?![\\s\\S])'},
        'id': identifier, 'version': version, 'sha256': digest,
        'size': {'type': 'integer', 'minimum': 0, 'maximum': 4194304}})
    passive = {
        'inbox_pending': {'type': ['integer', 'null'], 'minimum': 0},
        'inbox_notice': {'type': 'string'}, 'inbox_pending_known': {'type': 'integer', 'minimum': 0},
        'inbox_pending_diagnostics': {'type': 'array', 'items': {'type': 'string'}},
        'incoming': closed({
            'messages': {'type': 'array', 'items': {'type': 'string'}},
            'claims': {'type': 'array', 'items': {'$ref': '#/$defs/fileClaim'}},
            'batch_limited': {'type': 'boolean'}, 'next_after': {'type': ['string', 'null']},
            'rendered_bytes': {'type': 'integer', 'minimum': 0},
        }, ['messages', 'claims']),
    }
    def response(properties):
        return closed(dict(properties, **passive), list(properties))
    result['fileManifestResult'] = response({'storage_id': identifier, 'manifest': {'$ref': '#/$defs/fileManifest'}})
    result['fileEntryResult'] = response({'storage_id': identifier, 'entry_id': identifier,
        'encoding': {'enum': ['text', 'base64']}, 'content': {'type': 'string'}})
    result['fileCanonicalResult'] = response({'storage_id': identifier, 'canonical_format': {'const': 'xsm.files/v1'},
        'manifest_sha256': digest, 'encoding': {'const': 'base64'}, 'content': {'type': 'string'}})
    result['fileResult'] = {'oneOf': [{'$ref': '#/$defs/' + name} for name in
                                   ('fileManifestResult', 'fileEntryResult', 'fileCanonicalResult')]}
    return result


def result_schema(claim):
    return {'$schema': 'https://json-schema.org/draft/2020-12/schema',
            '$id': 'urn:xsm:host-protocol:1:file-result',
            'title': 'Owned file manifest, copied bytes, or exact v1 digest preimage',
            '$ref': '#/$defs/fileResult', '$defs': definitions(claim)}
