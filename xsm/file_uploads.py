"""Bounded volatile preparation buffers; durable copies use existing material intents."""
from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import re
import uuid

from . import context, files, handoff, materials


def _schema(properties, required):
    return {'type': 'object', 'additionalProperties': False,
            'properties': dict(session={'type': 'string', 'minLength': 1}, **properties),
            'required': ['session'] + required}


UPLOAD_SCHEMAS = {
    'files.upload.open': _schema({
        'target': {'type': 'string', 'minLength': 1},
        'request_id': {'type': 'string', 'pattern': '^[A-Za-z0-9_-]{1,160}(?![\\s\\S])'},
        'text': {'type': 'string'},
        'entries': {'type': 'array', 'minItems': 1, 'maxItems': 16, 'items': {
            'type': 'object', 'additionalProperties': False, 'required': ['name', 'size', 'sha256'],
            'properties': {'name': {'type': 'string', 'minLength': 1, 'maxLength': 4096},
                           'size': {'type': 'integer', 'minimum': 0, 'maximum': 1048576},
                           'sha256': {'type': 'string', 'pattern': '^[0-9a-f]{64}(?![\\s\\S])'},
                           'source_version': {'type': 'string', 'maxLength': 4096}}}},
        'previous_manifest': {'type': 'string'},
        'attachment_fallback': {'type': 'string', 'enum': ['inline']},
    }, ['target', 'request_id', 'text', 'entries']),
    'files.upload.write': _schema({
        'upload': {'type': 'string', 'pattern': '^[0-9a-f]{32}(?![\\s\\S])'},
        'entry': {'type': 'integer', 'minimum': 0, 'maximum': 15},
        'offset': {'type': 'integer', 'minimum': 0, 'maximum': 1048576},
        'base64': {'type': 'string', 'maxLength': 262144},
    }, ['upload', 'entry', 'offset', 'base64']),
    'files.upload.commit': _schema({'upload': {'type': 'string', 'pattern': '^[0-9a-f]{32}(?![\\s\\S])'}}, ['upload']),
    'files.upload.status': _schema({'request_id': {'type': 'string', 'pattern': '^[A-Za-z0-9_-]{1,160}(?![\\s\\S])'}}, ['request_id']),
    'files.upload.abort': _schema({'upload': {'type': 'string', 'pattern': '^[0-9a-f]{32}(?![\\s\\S])'}}, ['upload']),
}


class Uploads:
    CHUNK_BYTES = 192 * 1024
    MAX_UPLOADS = 16

    def __init__(self):
        self.uploads = {}
        self.reserved_bytes = 0

    @staticmethod
    def _owner(caller):
        generation = caller.get('protocol_generation') or context.generation(caller.get('pid'), caller.get('lstart'))
        return (handoff._identity(caller), generation)

    @staticmethod
    def _verified(call):
        why = context.require_sure(call, 'prepare attachments')
        if why:
            raise files.FileError('caller-unverified', why)

    def _owned(self, caller, upload):
        value = self.uploads.get(upload)
        if value is None or value['owner'] != self._owner(caller):
            raise files.FileError('unknown-upload', 'no upload owned by this execution')
        return value

    def _release(self, value):
        if value['buffers'] is not None:
            self.reserved_bytes -= value['size']
            value['buffers'] = None

    @staticmethod
    def _matches_frozen(status, args):
        value = status['manifest']
        entries = value['files']
        return (status['body_digest'] == materials._digest(args['text'])
                and value.get('previous') == args.get('previous_manifest')
                and len(entries) == len(args['entries'])
                and all(entry.get('original_name') == spec['name']
                        and entry['size'] == spec['size'] and entry['sha256'] == spec['sha256']
                        and entry.get('source_version') == spec.get('source_version')
                        for entry, spec in zip(entries, args['entries'])))

    def open(self, caller, arguments, *, call):
        self._verified(call)
        args = copy.deepcopy(arguments)
        limits = files.product_limits()
        request_id, entries = args.get('request_id'), args.get('entries')
        handoff._id(request_id)
        if not isinstance(args.get('text'), str) or not isinstance(args.get('target'), str) or not args['target'].strip():
            raise files.FileError('invalid-upload', 'target and text are required', request_id)
        if not isinstance(entries, list) or not 1 <= len(entries) <= limits.max_files:
            raise files.FileError('too-many-files', 'upload needs 1 to 16 entries', request_id)
        total = 0
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) - {'name', 'size', 'sha256', 'source_version'}:
                raise files.FileError('invalid-upload', 'invalid entry metadata', request_id)
            files.safe_name(entry.get('name'))
            size, digest = entry.get('size'), entry.get('sha256')
            if type(size) is not int or not 0 <= size <= limits.file_bytes:
                raise files.FileError('file-too-large', 'entry exceeds the 1MiB file limit', request_id)
            if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
                raise files.FileError('invalid-upload', 'entry SHA-256 required', request_id)
            if entry.get('source_version') is not None and not isinstance(entry['source_version'], str):
                raise files.FileError('invalid-upload', 'source version must be text', request_id)
            total += size
        if total > limits.total_bytes:
            raise files.FileError('bundle-too-large', 'upload exceeds 4MiB', request_id)
        owner = self._owner(caller)
        for upload, value in self.uploads.items():
            if value['owner'] == owner and value['args']['request_id'] == request_id:
                if value['args'] != args:
                    raise files.FileError('intent-conflict', 'upload request content differs', request_id)
                if value.get('manifest_id'):
                    return materials.frozen_status(caller, request_id)
                return self._progress(upload, value)
        frozen = materials.frozen_status(caller, request_id)
        if frozen['state'] == 'frozen':
            if not self._matches_frozen(frozen, args):
                raise files.FileError('intent-conflict', 'frozen request content differs', request_id)
            return frozen
        if self.reserved_bytes + total > limits.total_bytes:
            raise files.FileError('upload-capacity', 'connection upload budget exhausted', request_id)
        while len(self.uploads) >= self.MAX_UPLOADS:
            completed = next((key for key, value in self.uploads.items() if value['buffers'] is None), None)
            if completed is None:
                raise files.FileError('upload-capacity', 'too many active preparations', request_id)
            del self.uploads[completed]
        upload = uuid.uuid4().hex
        value = {'owner': owner, 'args': args, 'size': total,
                 'buffers': [bytearray() for entry in entries]}
        self.uploads[upload] = value
        self.reserved_bytes += total
        return self._progress(upload, value)

    def _progress(self, upload, value):
        return {'state': 'uploading', 'upload': upload, 'request_id': value['args']['request_id'],
                'offsets': [len(data) for data in value['buffers']], 'chunk_bytes': self.CHUNK_BYTES}

    def write(self, caller, upload, entry, offset, encoded):
        value = self._owned(caller, upload)
        if value['buffers'] is None:
            raise files.FileError('upload-frozen', 'preparation already frozen')
        if type(entry) is not int or not 0 <= entry < len(value['buffers']) or type(offset) is not int or offset < 0:
            raise files.FileError('invalid-chunk', 'entry index and byte offset required')
        if not isinstance(encoded, str) or len(encoded) > ((self.CHUNK_BYTES + 2) // 3) * 4:
            raise files.FileError('chunk-too-large', 'chunk exceeds 192KiB')
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise files.FileError('invalid-chunk', 'valid base64 required') from exc
        if len(data) > self.CHUNK_BYTES:
            raise files.FileError('chunk-too-large', 'chunk exceeds 192KiB')
        buffer = value['buffers'][entry]
        end = offset + len(data)
        if end > value['args']['entries'][entry]['size'] or offset > len(buffer):
            raise files.FileError('invalid-chunk', 'chunk exceeds entry or skips bytes')
        if offset < len(buffer):
            if end > len(buffer) or buffer[offset:end] != data:
                raise files.FileError('intent-conflict', 'replayed chunk differs')
        else:
            buffer.extend(data)
        return {'upload': upload, 'entry': entry, 'offset': len(buffer)}

    def commit(self, caller, upload, *, call):
        self._verified(call)
        value = self._owned(caller, upload)
        if 'result' in value:
            return copy.deepcopy(value['result'])
        args, items = value['args'], None
        if not value.get('manifest_id'):
            items = []
            for spec, data in zip(args['entries'], value['buffers']):
                if len(data) != spec['size'] or hashlib.sha256(data).hexdigest() != spec['sha256']:
                    raise files.FileError('incomplete-or-corrupt-upload', 'entry size or hash differs', args['request_id'])
                item = {'name': spec['name'], 'base64': base64.b64encode(data).decode('ascii')}
                if 'source_version' in spec:
                    item['source_version'] = spec['source_version']
                items.append(item)
        try:
            prepared = materials.prepare(caller, args['target'], args['text'], args['request_id'], items,
                manifest_id=value.get('manifest_id'), previous=args.get('previous_manifest'),
                fallback=args.get('attachment_fallback'), call=call)
        except files.FileError as exc:
            if getattr(exc, 'manifest_id', None):
                value['manifest_id'] = exc.manifest_id
                self._release(value)
            raise
        value['manifest_id'] = prepared['manifest_id']
        self._release(value)
        value['result'] = dict(materials.public(prepared), state='frozen', request_id=args['request_id'], body_sent=False)
        return copy.deepcopy(value['result'])

    def status(self, caller, request_id):
        for upload, value in self.uploads.items():
            if value['owner'] == self._owner(caller) and value['args']['request_id'] == request_id and value['buffers'] is not None:
                return self._progress(upload, value)
        return materials.frozen_status(caller, request_id)

    def abort(self, caller, upload):
        value = self._owned(caller, upload)
        self._release(value)
        del self.uploads[upload]
        return {'aborted': True, 'request_id': value['args']['request_id'], 'body_sent': False}

    def close(self, caller):
        owner = self._owner(caller)
        for upload, value in list(self.uploads.items()):
            if value['owner'] == owner:
                self._release(value)
                del self.uploads[upload]
