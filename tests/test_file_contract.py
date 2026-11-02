"""A caller can verify the exact legacy digest bytes without Python float formatting."""
import base64
import hashlib
import io
import json
import os
from contextlib import redirect_stdout
from unittest import mock
from tests.test_xsm import TempState


class FileContractTest(TempState):
    def test_legacy_serialization_vector_is_unchanged(self):
        # Encoding vector, not a claim that this partial object is a valid manifest.
        value = {'created_at': 1e-7, 'label': '한글', 'sha256': 'excluded'}
        expected = '{"created_at":1e-07,"label":"한글"}'.encode('utf-8')
        self.assertEqual(self.f.canonical_manifest_bytes(value), expected)
        self.assertEqual(self.f._manifest_digest(value), hashlib.sha256(expected).hexdigest())

    def setUp(self):
        super().setUp()
        from xsm import context, files, registry
        self.f, self.r = files, registry
        self.me = registry.upsert('codex', self.tmp + '/profile', 'sender', os.getpid(), self.tmp, name='sender')
        self.peer = registry.upsert('codex', self.tmp + '/profile', 'receiver', os.getpid(), self.tmp, name='receiver')
        self.call = context.of_record(self.me, context.BASIS_SESSION)
        self.manifest = files.prepare_inline(self.me, 'digest-request', 'body',
            [{'name': '한글.txt', 'text': 'exact copy', 'source_version': 'v1\n한글'}],
            limits=files.product_limits(), now=1793591234.000001)

    def verify(self, result):
        raw = base64.b64decode(result['content'], validate=True)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), self.manifest['sha256'])
        self.assertEqual(result['manifest_sha256'], self.manifest['sha256'])
        self.assertEqual(json.loads(raw.decode('utf-8')), {k: v for k, v in self.manifest.items() if k != 'sha256'})

    def test_manifest_preimage_preserves_the_existing_digest_and_unicode(self):
        result = self.f.read_result(self.me, self.manifest['id'], outgoing=True, manifest_bytes=True)
        self.verify(result)
        self.assertEqual(result['canonical_format'], 'xsm.files/v1')
        with self.assertRaises(self.f.FileError):
            self.f.read_result(self.peer, self.manifest['id'], outgoing=True, manifest_bytes=True)

    def test_cli_and_model_export_the_same_digest_bytes(self):
        from xsm import cli, mcp
        out = io.StringIO()
        with mock.patch.object(self.r, 'me', return_value=self.me), mock.patch.object(self.r, 'last_identity', return_value=self.call), redirect_stdout(out):
            self.assertEqual(cli.main(['files', self.manifest['id'], '--outgoing', '--manifest-bytes']), 0)
        server = mcp.Server(io.StringIO(), io.StringIO()); server.session = lambda: self.me
        model = json.loads(server.call('xsm_files', {'storage_id': self.manifest['id'], 'outgoing': True, 'manifest_bytes': True}))
        self.assertEqual(model.pop('inbox_pending'), 0)
        self.assertEqual(json.loads(out.getvalue()), model)
        self.verify(model)

    def test_canonical_manifest_and_file_entry_cannot_be_confused(self):
        with self.assertRaises(self.f.FileError):
            self.f.read_result(self.me, self.manifest['id'], self.manifest['files'][0]['id'],
                               outgoing=True, manifest_bytes=True)

    def test_missing_copy_is_a_typed_domain_failure(self):
        for outgoing in (False, True):
            with self.subTest(outgoing=outgoing), self.assertRaises(self.f.FileError) as error:
                self.f.read_result(self.me, '0' * 32, outgoing=outgoing)
            self.assertEqual(error.exception.code, 'copy-not-found')
