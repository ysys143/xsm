"""Chunk preparation preserves ownership, exact bytes and existing material intents."""
import base64
import hashlib
from tests.test_xsm import TempState


class FileUploadsTest(TempState):
    def setUp(self):
        super().setUp()
        import os
        from xsm import context, files, registry
        self.f, self.r = files, registry
        self.a = registry.upsert('codex', self.tmp + '/profile', 'a', os.getpid(), self.tmp, name='a')
        self.b = registry.upsert('codex', self.tmp + '/profile', 'b', os.getpid(), self.tmp, name='b')
        self.call = context.of_record(self.a, context.BASIS_SESSION)

    def capable(self):
        import os
        self.assertTrue(self.r.note_capabilities(self.b, {'files': {'status': 'observed', 'version': 1}}, reader_pid=os.getpid()))
    def spec(self, data=b'original bytes', request='upload-request'):
        return {'target': 'ref:' + self.b['ref'], 'request_id': request, 'text': 'body',
                'entries': [{'name': 'copy.bin', 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}]}

    def upload(self, data=b'original bytes', request='upload-request'):
        from xsm.file_uploads import Uploads
        self.capable()
        store = Uploads()
        args = self.spec(data, request)
        opened = store.open(self.a, args, call=self.call)
        for offset in range(0, len(data), store.CHUNK_BYTES):
            store.write(self.a, opened['upload'], 0, offset,
                        base64.b64encode(data[offset:offset + store.CHUNK_BYTES]).decode())
        return store, opened, args

    def test_exact_replay_and_restart_recover_the_same_frozen_manifest(self):
        from xsm.file_uploads import Uploads
        store, opened, args = self.upload()
        one = store.commit(self.a, opened['upload'], call=self.call)
        two = store.commit(self.a, opened['upload'], call=self.call)
        self.assertEqual(one, two)
        recovered = Uploads().status(self.a, args['request_id'])
        self.assertEqual(recovered['manifest_id'], one['manifest_id'])
        manifest = self.f.manifest(self.a, one['manifest_id'])
        self.assertEqual(self.f.read_copy(self.a, one['manifest_id'], manifest['files'][0]['id']), b'original bytes')
        self.assertEqual(Uploads().open(self.a, args, call=self.call)['manifest_id'], one['manifest_id'])

    def test_wrong_owner_or_changed_replayed_chunk_cannot_modify_a_buffer(self):
        store, opened, args = self.upload()
        encoded = base64.b64encode(b'original bytes').decode()
        self.assertEqual(store.write(self.a, opened['upload'], 0, 0, encoded)['offset'], len(b'original bytes'))
        with self.assertRaises(self.f.FileError):
            store.write(self.b, opened['upload'], 0, 0, encoded)
        with self.assertRaises(self.f.FileError):
            store.write(self.a, opened['upload'], 0, 0, base64.b64encode(b'changed bytes!').decode())
        self.assertEqual(store.status(self.a, args['request_id'])['offsets'], [len(b'original bytes')])

    def test_incomplete_or_bad_hash_never_creates_a_frozen_manifest(self):
        from xsm.file_uploads import Uploads
        store = Uploads(); self.capable()
        args = self.spec(); opened = store.open(self.a, args, call=self.call)
        with self.assertRaises(self.f.FileError):
            store.commit(self.a, opened['upload'], call=self.call)
        store.write(self.a, opened['upload'], 0, 0, base64.b64encode(b'corrupt bytes!').decode())
        with self.assertRaises(self.f.FileError):
            store.commit(self.a, opened['upload'], call=self.call)
        self.assertEqual(Uploads().status(self.a, args['request_id'])['state'], 'unknown')

    def test_budget_and_provisional_caller_refuse_before_allocating(self):
        from xsm import context
        from xsm.file_uploads import Uploads
        store = Uploads(); args = self.spec()
        args['entries'][0]['size'] = 1024 * 1024 + 1
        with self.assertRaises(self.f.FileError):
            store.open(self.a, args, call=self.call)
        with self.assertRaises(self.f.FileError):
            store.open(self.a, self.spec(), call=context.of_record(self.a, context.BASIS_NEIGHBOR))
        self.assertEqual(store.reserved_bytes, 0)

    def test_close_releases_only_volatile_buffers(self):
        store, opened, args = self.upload()
        result = store.commit(self.a, opened['upload'], call=self.call)
        store.open(self.a, self.spec(request='unfinished'), call=self.call)
        self.assertGreater(store.reserved_bytes, 0)
        store.close(self.a)
        self.assertEqual(store.reserved_bytes, 0)
        self.assertEqual(store.status(self.a, args['request_id'])['manifest_id'], result['manifest_id'])
        self.assertEqual(store.status(self.a, 'unfinished')['state'], 'unknown')

    def test_chunk_larger_than_frame_budget_is_rejected(self):
        from xsm.file_uploads import Uploads
        store = Uploads(); data = b'x' * (store.CHUNK_BYTES + 1)
        opened = store.open(self.a, self.spec(data), call=self.call)
        with self.assertRaises(self.f.FileError):
            store.write(self.a, opened['upload'], 0, 0, base64.b64encode(data).decode())

    def test_connection_budget_is_shared_and_abort_frees_it_without_sending(self):
        from xsm import handoff
        from xsm.file_uploads import Uploads
        store = Uploads(); args = self.spec()
        args['entries'] = [{'name': 'file%d.bin' % i, 'size': 1048576, 'sha256': '0' * 64} for i in range(4)]
        opened = store.open(self.a, args, call=self.call)
        self.assertEqual(store.reserved_bytes, 4194304)
        with self.assertRaises(self.f.FileError):
            store.open(self.a, self.spec(request='second'), call=self.call)
        store.abort(self.a, opened['upload'])
        self.assertEqual(store.reserved_bytes, 0)
        self.assertEqual(handoff.pending_ids(self.b), [])
        with self.assertRaises(self.f.FileError):
            store.commit(self.a, opened['upload'], call=self.call)
        self.assertEqual(store.open(self.a, self.spec(request='second'), call=self.call)['state'], 'uploading')

    def test_sixteen_active_slots_are_bounded_and_abort_releases_one(self):
        from xsm.file_uploads import Uploads
        store = Uploads()
        opened = [store.open(self.a, self.spec(request='slot-%d' % index), call=self.call) for index in range(16)]
        with self.assertRaises(self.f.FileError):
            store.open(self.a, self.spec(request='slot-16'), call=self.call)
        store.abort(self.a, opened[0]['upload'])
        self.assertEqual(store.open(self.a, self.spec(request='slot-16'), call=self.call)['state'], 'uploading')
        self.assertEqual(len(store.uploads), 16)

    def test_new_execution_cannot_reuse_an_old_buffer_handle(self):
        store, opened, args = self.upload()
        successor = dict(self.a, lstart='different process start')
        with self.assertRaises(self.f.FileError):
            store.write(successor, opened['upload'], 0, 0, base64.b64encode(b'original bytes').decode())

    def test_protocol_generation_changes_even_when_host_pid_does_not(self):
        from xsm.file_uploads import Uploads
        store = Uploads(); original = dict(self.a, protocol_generation='old-execution')
        opened = store.open(original, self.spec(), call=self.call)
        successor = dict(original, protocol_generation='new-execution')
        with self.assertRaises(self.f.FileError):
            store.write(successor, opened['upload'], 0, 0, base64.b64encode(b'original bytes').decode())
        self.assertEqual(store.status(successor, 'upload-request')['state'], 'unknown')

    def test_reopening_frozen_request_with_other_bytes_is_refused(self):
        from xsm.file_uploads import Uploads
        store, opened, args = self.upload()
        prepared = store.commit(self.a, opened['upload'], call=self.call)
        with self.assertRaises(self.f.FileError):
            Uploads().open(self.a, self.spec(b'different bytes'), call=self.call)
        self.assertEqual(store.status(self.a, args['request_id'])['manifest_id'], prepared['manifest_id'])

    def test_capability_refusal_keeps_frozen_id_and_releases_buffer_for_retry(self):
        from xsm import handoff
        from xsm.file_uploads import Uploads
        store = Uploads(); args = self.spec(); data = b'original bytes'
        opened = store.open(self.a, args, call=self.call)
        store.write(self.a, opened['upload'], 0, 0, base64.b64encode(data).decode())
        with self.assertRaises(self.f.FileError) as caught:
            store.commit(self.a, opened['upload'], call=self.call)
        manifest_id = caught.exception.manifest_id
        self.assertEqual(store.reserved_bytes, 0)
        self.assertEqual(store.status(self.a, args['request_id'])['manifest_id'], manifest_id)
        self.capable()
        self.assertEqual(store.commit(self.a, opened['upload'], call=self.call)['manifest_id'], manifest_id)
        self.assertEqual(handoff.pending_ids(self.b), [])
