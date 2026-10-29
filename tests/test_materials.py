"""Public attachment preparation preserves snapshots and caller boundaries."""
import os
from pathlib import Path
from unittest import mock

from tests.test_xsm import TempState


class MaterialPreparationTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import context,files,materials,registry
        self.f,self.m,self.r=files,materials,registry
        self.a=registry.upsert('codex',self.tmp+'/profile','a',os.getpid(),self.tmp,name='a')
        self.b=registry.upsert('codex',self.tmp+'/profile','b',os.getpid(),self.tmp,name='b')
        self.call=context.of_record(self.a,context.BASIS_SESSION)

    def capable(self):
        self.assertTrue(self.r.note_capabilities(self.b,{'files':{'status':'observed','version':1}},reader_pid=os.getpid()))

    def prepare(self,items=None,**kwargs):
        return self.m.prepare(self.a,'codex:b','원 요청','request1',items,call=self.call,**kwargs)

    def test_inline_copy_reuses_one_frozen_manifest_for_the_same_request(self):
        self.capable()
        items=[{'name':'설계.md','text':'정확한 사본\n'}]
        first=self.prepare(items)
        second=self.prepare(items)
        self.assertEqual(first['manifest_id'],second['manifest_id'])
        self.assertEqual(first['file_packet'],second['file_packet'])
        self.assertEqual(first['body'],'원 요청')
        self.assertEqual(first['mode'],'files')
        self.assertEqual(len(first['attachments']),1)

    def test_unknown_peer_requires_explicit_fallback_and_reports_recovery_id(self):
        with self.assertRaises(self.f.FileError) as caught:
            self.prepare([{'name':'note.txt','text':'copy'}])
        failure=self.m.failure(caught.exception)
        self.assertEqual(failure['request_id'],'request1')
        self.assertTrue(failure['manifest_id'])
        self.assertFalse(failure['body_sent'])
        fallback=self.prepare(manifest_id=failure['manifest_id'],fallback='inline')
        self.assertEqual(fallback['mode'],'inline')
        self.assertIn('copy',fallback['body'])
        self.assertEqual(fallback['attachments'],[])
        self.assertIsNone(fallback['file_packet'])

    def test_cli_can_snapshot_hidden_file_outside_its_work_folder_and_reject_changed_original(self):
        self.capable()
        outside=Path(self.tmp,'outside');outside.mkdir()
        source=outside/'.hidden.md';source.write_text('first')
        first=self.prepare([str(source)],source='cli')
        self.assertEqual(first['mode'],'files')
        source.write_text('second')
        with self.assertRaises(self.f.FileError):
            self.prepare(manifest_id=first['manifest_id'],source='cli')
        original=self.f.manifest(self.a,first['manifest_id'])
        self.assertEqual(self.f.read_copy(self.a,first['manifest_id'],original['files'][0]['id']),b'first')

    def test_mcp_path_claim_never_authorizes_a_server_read(self):
        self.capable()
        secret=Path(self.tmp,'private.txt');secret.write_text('must not be read by MCP')
        with self.assertRaises(self.f.FileError):
            self.prepare([{'name':'leak','path':str(secret)}])

    def test_same_request_id_with_changed_input_cannot_replace_a_snapshot(self):
        self.capable()
        first=self.prepare([{'name':'note.txt','text':'first'}])
        with self.assertRaisesRegex(self.f.FileError,'intent-conflict'):
            self.prepare([{'name':'note.txt','text':'different'}])
        saved=self.f.manifest(self.a,first['manifest_id'])
        self.assertEqual(self.f.read_copy(self.a,first['manifest_id'],saved['files'][0]['id']),b'first')

    def test_provisional_call_cannot_prepare_a_file(self):
        from xsm import context
        with self.assertRaises(self.f.FileError):
            self.m.prepare(self.a,'codex:b','body','request1',[{'name':'a','text':'b'}],
                           call=context.of_record(self.a,context.BASIS_NEIGHBOR))

    def test_mcp_can_export_the_same_cli_frozen_copy_without_reopening_a_changed_original(self):
        self.capable()
        original=Path(self.tmp,'.source.md');original.write_text('frozen first version')
        first=self.prepare([str(original)],source='cli')
        original.write_text('later source version')
        with mock.patch.object(self.f,'_snapshot_cli',side_effect=AssertionError('server source path read')):
            reused=self.prepare(manifest_id=first['manifest_id'],source='inline')
        self.assertEqual(reused['file_packet'],first['file_packet'])
        self.assertEqual(reused['manifest_id'],first['manifest_id'])
        with self.assertRaises(self.f.FileError):
            self.prepare([str(original)],source='cli')
