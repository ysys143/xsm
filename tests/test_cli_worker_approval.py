"""CLI user approval stays bound to the displayed worker invocation."""
import contextlib
import io
import os
from types import SimpleNamespace
from unittest import mock
from tests.test_xsm import TempState


class CliWorkerApprovalTest(TempState):
    def setup_request(self):
        from xsm import paths,workers
        worker=dict(name='approval-cli-worker',runtime='claude',home=self.tmp,session_id='worker-session',
            parent_ref='parent-ref',created=1)
        workers.save(worker)
        request=dict(id='cli-approval',worker=worker['name'],status='pending',summary='same displayed summary',
            runtime='claude',tool='Bash',input={'command':'fixture original'},t=1)
        paths.write_json(paths.path(workers.APPROVALS,request['id']+'.json'),request)
        return worker,request

    def invoke(self, approve):
        from xsm import cli,registry,workers
        args=SimpleNamespace(command='approve',id='cli-approval',reason=None)
        with mock.patch.object(workers,'human_terminal',return_value=False), \
                mock.patch.object(registry,'me',return_value={'ref':'parent-ref'}), \
                mock.patch.object(cli,'_person_or_refuse',side_effect=approve), \
                contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            return cli.cmd_answer(args)

    def test_cli_cannot_apply_answer_after_input_worker_or_display_change(self):
        from xsm import cli,paths,workers
        for field in ('input','worker-scope','summary'):
            with self.subTest(field=field):
                worker,request=self.setup_request()
                def approve(*args,**kwargs):
                    if field=='worker-scope':worker['home']+='-changed';workers.save(worker)
                    elif field=='summary':request['summary']='changed displayed request'
                    else:request['input']={'command':'fixture replaced'}
                    paths.write_json(paths.path(workers.APPROVALS,request['id']+'.json'),request)
                    return None
                self.assertEqual(self.invoke(approve),cli.REFUSED)
                self.assertEqual(paths.read_json(paths.path(workers.APPROVALS,request['id']+'.json'))['status'],'pending')

    def test_unchanged_cli_answer_applies_exact_request_and_binds_retained_ask(self):
        from xsm import cli,paths,workers
        worker,request=self.setup_request();seen=[]
        def approve(*args,**kwargs):seen.append(kwargs);return None
        self.assertEqual(self.invoke(approve),cli.OK)
        self.assertEqual(paths.read_json(paths.path(workers.APPROVALS,request['id']+'.json'))['status'],'approved')
        self.assertIn('binding',seen[0])
        self.assertEqual(seen[0]['binding']['worker_approval'],workers.approval_fingerprint(request,worker,include_display=True))

    def test_cli_retained_ask_for_same_id_changes_with_input(self):
        from xsm import workers,paths
        bindings=[]
        def waiting(*args,**kwargs):bindings.append(kwargs.get('binding'));return 'waiting'
        worker,request=self.setup_request();self.invoke(waiting)
        request['input']={'command':'fixture revised'}
        paths.write_json(paths.path(workers.APPROVALS,request['id']+'.json'),request)
        self.invoke(waiting)
        self.assertIsNotNone(bindings[0]);self.assertNotEqual(bindings[0],bindings[1])

    def test_real_cli_consent_does_not_upgrade_an_unbound_approval_ask(self):
        from xsm import cli,consent,registry,workers
        worker,request=self.setup_request()
        me=registry.upsert('codex',self.tmp+'/parent-profile','parent-session',os.getpid(),self.tmp,name='parent')
        worker['parent_ref']=me['ref'];workers.save(worker)
        consent.take_or_request(me,'approve',request['id'])
        before=consent.pending_status(me)['requests']
        self.assertEqual(len(before),1)
        args=SimpleNamespace(command='approve',id=request['id'],reason=None)
        with mock.patch.object(workers,'human_terminal',return_value=False),                 mock.patch.object(registry,'me',return_value=me),                 contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.cmd_answer(args),cli.REFUSED)
        after=consent.pending_status(me)['requests']
        self.assertEqual(len(after),2)
        self.assertEqual(len({row['id'] for row in after}),2)
