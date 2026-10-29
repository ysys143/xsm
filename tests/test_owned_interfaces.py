"""Owned public adapters use the durable journal; tests launch no models."""
import contextlib
import io
import json
import os
import threading
import uuid
from unittest import mock

from tests.test_xsm import TempState


class OwnedInterfacesTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import context,identity,mcp,registry,workers
        self.me=registry.upsert('codex',self.tmp+'/profile','owner',os.getpid(),self.tmp,name='owner')
        self.call=context.of_record(self.me,context.BASIS_SESSION)
        self.workers,self.registry,self.mcp=workers,registry,mcp
        self.server=mcp.Server(io.StringIO(),io.StringIO());self.server.session=lambda:self.me
        self.server.pump=lambda:True
        self.count=0
        def executor(worker,context,body,request):
            self.count+=1
            return {'body':'actual adapter result','outcome':'succeeded',
                    'native_session_id':str(uuid.uuid4()),
                    'execution':{'pid':os.getpid(),'lstart':identity.lstart(os.getpid())}}
        # A suite run from an Orca or herdr terminal inherits its pane markers, and
        # owned workers are refused there; the siblings clear them the same way.
        for patcher in (mock.patch.dict(os.environ, {k: '' for _, keys in workers.FRAMEWORKS for k in keys}),
                        mock.patch.object(workers,'_check_installed'),
                        mock.patch.object(workers,'_execute_owned',side_effect=executor),
                        mock.patch.object(workers,'_reply_owned',side_effect=lambda w,r:{'id':r['reply_id'],'status':'stored'})):
            patcher.start();self.addCleanup(patcher.stop)

    def invoke(self,**kwargs):
        return json.loads(self.server.call('xsm_owned',kwargs))

    def create(self):
        return self.invoke(action='create',name='service',runtime='codex')

    def test_mcp_create_run_same_id_replay_and_collision(self):
        self.create()
        args={'action':'run','name':'service','text':'work','work_context':'topic','request_id':'owned-public','wait':1}
        result=self.invoke(**args)
        self.assertEqual(result['status'],'reply-stored')
        self.assertEqual(result['result']['body'],'actual adapter result')
        self.assertEqual(self.invoke(**args)['reply_id'],result['reply_id'])
        self.assertEqual(self.count,1)
        from xsm import channel
        with self.assertRaisesRegex(channel.ChannelError,'differs'):
            self.invoke(**dict(args,text='different'))
        listed=self.invoke(action='status',name='service')
        self.assertEqual([r['id'] for r in listed['requests']],['owned-public'])

    def test_cancelled_mcp_waiter_does_not_stop_a_saved_owned_request(self):
        entered,release=threading.Event(),threading.Event()
        execute=self.workers._execute_owned.side_effect
        def blocked(*args):
            entered.set()
            if not release.wait(5):raise RuntimeError('fixture barrier timed out')
            return execute(*args)
        self.workers._execute_owned.side_effect=blocked
        self.create()
        self.server.active_request='cancelled-call';self.server.cancelled.add('cancelled-call')
        args={'action':'run','name':'service','text':'work','work_context':'topic','request_id':'cancelled-owned','wait':1}
        try:
            result=self.invoke(**args)
            self.assertTrue(result['waiter_cancelled'])
            self.assertEqual(result['recover_at']['arguments']['request_id'],'cancelled-owned')
            self.assertTrue(entered.wait(2))
        finally:release.set()
        for job in self.server.owned_jobs.values():job['thread'].join(3)
        self.server.cancelled.clear()
        recovered=self.invoke(**args)
        self.assertEqual(recovered['status'],'reply-stored')
        self.assertEqual(self.count,1)

    def test_cli_owned_entry_points_share_the_same_journal(self):
        from xsm import cli
        with mock.patch.object(self.registry,'me',return_value=self.me), \
             mock.patch.object(self.registry,'last_identity',return_value=self.call):
            for args,expected in ((['owned','create','cli-service','--runtime','codex'],0),
                 (['owned','run','cli-service','--text','work','--work','topic','--request-id','cli-owned'],3),
                 (['owned','status','cli-service'],0)):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(cli.main(args),expected,output.getvalue())
                value=json.loads(output.getvalue())
            self.assertEqual(value['requests'][0]['id'],'cli-owned')
        self.assertEqual(self.count,1)

    def test_provisional_identity_cannot_create_an_owned_service(self):
        from xsm import channel,context
        self.server.ctx=context.of_record(self.me,context.BASIS_NEIGHBOR)
        with self.assertRaisesRegex(channel.ChannelError,'guess'):
            self.create()

    def test_public_status_recovers_a_saved_answer_after_worker_record_removal(self):
        self.create()
        result=self.invoke(action='run',name='service',text='work',work_context='topic',
                           request_id='retained-answer',wait=1)
        self.workers.stop('service')
        self.assertIsNone(self.workers.load('service'))
        recovered=self.invoke(action='status',name='service',request_id='retained-answer')
        self.assertEqual(recovered['reply_id'],result['reply_id'])
        self.assertEqual(recovered['result']['body'],'actual adapter result')
        self.assertEqual(self.count,1)
        self.assertEqual(self.invoke(action='status',name='service')['requests'][0]['id'],'retained-answer')
        other=self.registry.upsert('codex',self.tmp+'/other-profile','other',os.getpid(),self.tmp,name='other')
        server=self.mcp.Server(io.StringIO(),io.StringIO());server.session=lambda:other
        with self.assertRaises(self.workers.WorkerError):
            server.call('xsm_owned',{'action':'status','name':'service','request_id':'retained-answer'})

    def test_mcp_overloaded_request_resumes_with_the_same_id_after_capacity_frees(self):
        self.create()
        args={'action':'run','name':'service','text':'work','work_context':'topic','request_id':'mcp-overloaded','wait':1}
        with mock.patch.object(self.workers,'_limit',return_value=0):
            queued=self.invoke(**args)
        self.assertEqual(queued['status'],'queued')
        self.assertEqual(queued['admission'],'overloaded')
        resumed=self.invoke(**args)
        self.assertEqual(resumed['status'],'reply-stored')
        self.assertEqual(resumed['id'],queued['id'])
        self.assertEqual(self.count,1)

    def test_recreated_worker_does_not_reuse_the_previous_workers_cached_result(self):
        from xsm import channel
        first=self.create()
        args={'action':'run','name':'service','text':'work','work_context':'topic','request_id':'worker-generation','wait':1}
        self.invoke(**args)
        self.workers.stop('service')
        self.assertNotEqual(self.create()['id'],first['id'])
        with self.assertRaisesRegex(channel.ChannelError,'differs'):
            self.invoke(**args)
        self.assertEqual(self.count,1)
