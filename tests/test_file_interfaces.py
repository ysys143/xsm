"""Files travel through actual CLI/MCP send, receive and private-copy reads."""
import contextlib
import io
import json
import os
from pathlib import Path
from unittest import mock

from tests.test_xsm import TempState


class FileInterfacesTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import adapters,context,mcp,registry
        self.a=registry.upsert('codex',self.tmp+'/profile','a',os.getpid(),self.tmp,name='a')
        self.b=registry.upsert('codex',self.tmp+'/profile','b',os.getpid(),self.tmp,name='b')
        self.a_call=context.of_record(self.a,context.BASIS_SESSION)
        self.mcp,self.registry=mcp,registry
        patcher=mock.patch.object(adapters,'to_codex',side_effect=AssertionError('passive test may not queue/wake'))
        patcher.start();self.addCleanup(patcher.stop)
        self.assertTrue(registry.note_capabilities(self.b,{'files':{'status':'observed','version':1}},reader_pid=os.getpid()))

    def server(self,who):
        result=self.mcp.Server(io.StringIO(),io.StringIO());result.session=lambda:who
        return result

    def test_inline_mcp_send_receive_read_copy_preserves_original_body_and_bytes(self):
        from xsm import handoff
        a,b=self.server(self.a),self.server(self.b)
        answer=a.call('xsm_send',{'target':'codex:b','text':'검토해 주세요','request_id':'file1',
              'attachments':[{'name':'설계.md','text':'사본 원문\n'}],'wake':'never','wait':0})
        self.assertIn('stored',answer)
        original=handoff.status(self.b,'file1')
        self.assertEqual(original['message']['body'],'검토해 주세요')
        storage=original['message']['file_storage']
        pack=json.loads(b.call('xsm_inbox',{}))
        self.assertIn(storage,pack['messages'][0])
        manifest=json.loads(b.call('xsm_files',{'storage_id':storage}))['manifest']
        entry=manifest['files'][0]['id']
        read=json.loads(b.call('xsm_files',{'storage_id':storage,'entry_id':entry}))
        self.assertEqual(read['content'],'사본 원문\n')
        b.call('xsm_ack',{'tokens':[c['token'] for c in pack['claims']]})
        self.assertEqual(handoff.status(self.b,'file1')['status'],'acknowledged')
        self.assertEqual(original['identity']['attachments'][0][1],manifest['sha256'])

    def test_cli_hidden_file_to_mcp_copy_read_needs_no_server_source_path_read(self):
        from xsm import cli,handoff
        source=Path(self.tmp,'.source.md');source.write_text('CLI authority\n')
        output=io.StringIO()
        with mock.patch.object(self.registry,'me',return_value=self.a), \
             mock.patch.object(self.registry,'last_identity',return_value=self.a_call),contextlib.redirect_stdout(output):
            code=cli.main(['send','codex:b','--text','body','--request-id','cli-file',
                          '--attachment',str(source),'--wake','never','--json'])
        self.assertEqual(code,0,output.getvalue())
        result=json.loads(output.getvalue())
        storage=handoff.status(self.b,'cli-file')['message']['file_storage']
        server=self.server(self.b)
        manifest=json.loads(server.call('xsm_files',{'storage_id':storage}))['manifest']
        self.assertNotIn(str(source),json.dumps(manifest))
        body=json.loads(server.call('xsm_files',{'storage_id':storage,'entry_id':manifest['files'][0]['id']}))
        self.assertEqual(body['content'],'CLI authority\n')
        self.assertEqual(result['materials']['mode'],'files')

    def test_received_copy_cannot_be_read_by_another_home(self):
        from xsm import files,handoff
        self.server(self.a).call('xsm_send',{'target':'codex:b','text':'body','request_id':'private-file',
                 'attachments':[{'name':'private.txt','text':'private copy'}],'wake':'never','wait':0})
        storage=handoff.status(self.b,'private-file')['message']['file_storage']
        other=self.registry.upsert('codex',self.tmp+'/other-profile','other',os.getpid(),self.tmp,name='other')
        with self.assertRaises(files.FileError):
            self.server(other).call('xsm_files',{'storage_id':storage})

    def test_housekeeping_removes_only_expired_copies_and_keeps_original_file_and_message(self):
        from xsm import files,handoff,housekeeping,materials,send
        original=Path(self.tmp,'.original.md');original.write_text('original survives')
        prepared=materials.prepare(self.a,'codex:b','body','expiry-message',[str(original)],source='cli',call=self.a_call)
        sent=send.send('codex:b','body',sender=self.a,msg_id='expiry-message',wake=False,
            attachments=prepared['attachments'],file_packet=prepared['file_packet'],file_limits=prepared['file_limits'])
        self.assertEqual(sent.status,'stored')
        expiry=prepared['file_packet']['manifest']['expires_at']+1
        dry=housekeeping.prune(now=expiry,dry_run=True)
        self.assertEqual(len(dry['files']['removed']),2)
        self.assertEqual(files.manifest(self.a,prepared['manifest_id'])['id'],prepared['manifest_id'])
        removed=housekeeping.prune(now=expiry)
        self.assertEqual(len(removed['files']['removed']),2)
        self.assertEqual(original.read_text(),'original survives')
        self.assertEqual(handoff.status(self.b,'expiry-message')['message']['body'],'body')
