"""Probe diagnostics stay in an exact isolated service, not the model result."""
from unittest import mock
from pathlib import Path
from tests.test_xsm import TempState
from scripts.probe_owned_observer import OwnedProbeObserver


class OwnedProbeObserverTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import registry,workers,owned_requests
        import os
        self.owner=registry.upsert('codex',self.tmp+'/owner','owner',os.getpid(),self.tmp)
        self.worker=dict(name='probe-service',id='a'*32,mode='owned',owned=True,runtime='codex',home=self.tmp,
            cwd=self.tmp,owner=self.owner,parent_ref=self.owner['ref'],created=1)
        workers.save(self.worker)
        self.journal=owned_requests
        self.observer=OwnedProbeObserver(self.tmp,self.owner['ref'],self.worker['name'],self.worker['id'])

    def submit(self,request='probe-task',worker=None):
        worker=worker or self.worker
        return self.journal.submit(self.owner,worker,self.owner,'probe-context','fixture body',request_id=request)

    def test_wrong_state_root_refuses_before_loading_worker(self):
        from xsm import workers
        observer=OwnedProbeObserver(Path(self.tmp)/'other-state',self.owner['ref'],self.worker['name'],self.worker['id'])
        with mock.patch.object(workers,'load') as load, self.assertRaisesRegex(RuntimeError,'state root'):
            observer.worker()
        load.assert_not_called()

    def test_replaced_service_and_other_service_request_are_refused(self):
        from xsm import workers
        other=dict(self.worker,name='other-service',id='b'*32);workers.save(other)
        self.submit('other-request',other)
        with self.assertRaisesRegex(RuntimeError,'selected service'):self.observer.request('other-request')
        for changed in (dict(self.worker,id='c'*32),dict(self.worker,owned=False)):
            workers.save(changed)
            with self.assertRaisesRegex(RuntimeError,'identity changed'):self.observer.worker()

    def test_cleanup_cancels_only_selected_queued_launches(self):
        from xsm import workers
        self.submit()
        other=dict(self.worker,name='other-service',id='b'*32);workers.save(other)
        self.submit('other-request',other)
        with mock.patch.object(workers,'_terminate') as terminate:
            self.assertTrue(self.observer.stop_children())
        terminate.assert_not_called()
        self.assertEqual(self.observer.request('probe-task')['status'],'cancelled')
        self.assertEqual(self.journal.status(self.owner,'other-request')['status'],'queued')

    def active_child(self):
        self.submit()
        reserved=self.journal.reserve(self.owner,'probe-task',1)
        token=reserved['reservation']['token']
        self.journal.acknowledge(self.owner,'probe-task',token)
        self.journal.begin(self.owner,'probe-task',token)
        self.journal.note_child(self.owner,'probe-task',token,321,'probe-generation')

    def test_cleanup_stops_exact_controlled_child_and_checks_exit(self):
        from xsm import workers,identity
        self.active_child();alive=[True]
        def terminate(pid,birth):
            self.assertEqual((pid,birth),(321,'probe-generation'));alive[0]=False
        with mock.patch.object(identity,'pid_alive',side_effect=lambda pid:alive[0]), \
                mock.patch.object(identity,'process_matches',return_value=True), \
                mock.patch.object(workers,'_terminate',side_effect=terminate) as stop:
            self.assertTrue(self.observer.stop_children())
        stop.assert_called_once()

    def test_cleanup_never_signals_reused_or_unverified_pid(self):
        from xsm import workers,identity
        self.active_child()
        for match,exited in ((False,True),(None,False)):
            with self.subTest(match=match),mock.patch.object(identity,'pid_alive',return_value=True), \
                    mock.patch.object(identity,'process_matches',return_value=match), \
                    mock.patch.object(workers,'_terminate') as stop:
                self.assertIs(self.observer.stop_children(),exited)
                stop.assert_not_called()
