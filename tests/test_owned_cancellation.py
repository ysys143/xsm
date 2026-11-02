"""Durable cancellation intent versus native process birth; no runtime/model stubs claimed native."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from unittest import mock
from tests.test_xsm import TempState


class OwnedCancellationTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import workers
        self.owner = dict(runtime='codex', home=self.tmp + '/owner', session_id='owner', cwd=self.tmp)
        self.worker = dict(id='a' * 32, name='service', mode='owned', owned=True, owner=self.owner,
                           runtime='claude', home=self.tmp + '/worker', cwd=self.tmp)
        workers.save(self.worker)
        patcher = mock.patch.dict(os.environ, {key: '' for _, keys in workers.FRAMEWORKS for key in keys})
        patcher.start(); self.addCleanup(patcher.stop)

    def submit(self):
        from xsm import owned_requests
        return owned_requests.submit(self.owner, self.worker, self.owner, 'work', 'body', request_id='request')

    def running(self):
        from xsm import owned_requests
        self.submit(); row = owned_requests.reserve(self.owner, 'request', 1)
        token = row['reservation']['token']
        owned_requests.acknowledge(self.owner, 'request', token)
        return owned_requests.begin(self.owner, 'request', token)

    def cancel(self):
        from xsm import owned_requests
        return owned_requests.request_cancellation(self.owner, 'request', self.owner, self.worker['id'])

    def command(self, row):
        code = ('import sys,json;sys.stdin.read();print(json.dumps(' + repr(dict(
            type='result', subtype='success', session_id=row['context']['session_seed'], result='fixture answer')) + '))')
        return [sys.executable, '-B', '-c', code]

    def test_queued_cancel_is_durable_unaccepted_and_cannot_reserve_or_replay(self):
        from xsm import owned_requests
        self.submit(); cancelled = self.cancel()
        self.assertEqual(cancelled['status'], 'cancelled')
        self.assertFalse(cancelled['accepted'])
        self.assertFalse(cancelled['slot_occupied'])
        self.assertFalse(owned_requests.reserve(self.owner, 'request', 1)['reservation_acquired'])
        self.assertEqual(self.submit()['status'], 'cancelled')
        self.assertEqual(self.cancel()['cancellation'], cancelled['cancellation'])

    def test_sender_and_service_identity_are_required_before_recording_intent(self):
        from xsm import owned_requests
        self.submit()
        for sender, worker_id in ((dict(self.owner, home=self.tmp + '/other'), self.worker['id']),
                                  (self.owner, 'another-service')):
            with self.assertRaises(owned_requests.OwnedError):
                owned_requests.request_cancellation(self.owner, 'request', sender, worker_id)
        self.assertNotIn('cancellation', owned_requests.status(self.owner, 'request'))

    def test_cancel_after_ack_is_not_requeued_or_relabelled_unknown(self):
        from xsm import workers
        calls = []
        result = workers.run_owned('service', self.owner, 'body', work_context='work', request_id='request',
            checkpoint=lambda stage, row: self.cancel() if stage == 'acknowledged' else None,
            executor=lambda *args: calls.append(True))
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(calls, [])

    def test_running_intent_is_not_a_stop_claim_and_prevents_actual_process_birth(self):
        from xsm import workers, owned_requests
        row = self.running()
        pending = self.cancel()
        self.assertEqual(pending['status'], 'running')
        self.assertEqual(pending['cancellation']['native_state'], 'unverified')
        with mock.patch.object(workers, '_owned_argv', return_value=self.command(row)), \
                mock.patch.object(workers.subprocess, 'Popen', side_effect=AssertionError('must not create child')):
            with self.assertRaises(workers.OwnedLaunchError):
                workers._execute_owned(self.worker, row['context'], 'body', row)
        saved = owned_requests.status(self.owner, 'request')
        self.assertEqual(saved['status'], 'cancelled')
        self.assertEqual(saved['cancellation']['native_state'], 'not-started')

    def test_cancellation_cannot_pass_between_actual_spawn_and_durable_child_record(self):
        from xsm import workers
        row = self.running(); original = subprocess.Popen
        spawned, release, attempting = threading.Event(), threading.Event(), threading.Event()
        children = []
        def spawn(*args, **kwargs):
            child = original(*args, **kwargs)
            if args[0][0] != sys.executable:
                return child
            children.append(child); spawned.set()
            if not release.wait(3): raise RuntimeError('test launch release deadline')
            return child
        def cancel():
            attempting.set(); return self.cancel()
        with mock.patch.object(workers, '_owned_argv', return_value=self.command(row)), \
                mock.patch.object(workers.subprocess, 'Popen', side_effect=spawn), \
                concurrent.futures.ThreadPoolExecutor(2) as pool:
            execution = pool.submit(workers._execute_owned, self.worker, row['context'], 'body', row)
            try:
                self.assertTrue(spawned.wait(3))
                cancellation = pool.submit(cancel); self.assertTrue(attempting.wait(3))
                self.assertFalse(cancellation.done())
            finally: release.set()
            saved = cancellation.result(5); answer = execution.result(5)
        self.assertEqual(saved['child']['pid'], children[0].pid)
        self.assertEqual(saved['cancellation']['status'], 'requested')
        self.assertEqual(saved['cancellation']['native_state'], 'unverified')
        self.assertEqual(answer['body'], 'fixture answer')
        self.assertIsNotNone(children[0].poll())

    def test_birth_record_write_failure_stops_the_new_child_and_remains_unknown(self):
        from xsm import workers, owned_requests
        original_spawn, original_write = subprocess.Popen, owned_requests.handoff._write
        children, failures = [], []
        def spawn(*args, **kwargs):
            child = original_spawn(*args, **kwargs)
            if args[0][0] == sys.executable: children.append(child)
            return child
        def write(path, value):
            row = value.get('requests', {}).get('request', {})
            if row.get('child') and not failures:
                failures.append(True); raise OSError('explicit child-record write failure')
            return original_write(path, value)
        with mock.patch.object(workers, '_owned_argv', side_effect=lambda worker, context: self.command({'context': context})), \
                mock.patch.object(workers.subprocess, 'Popen', side_effect=spawn), \
                mock.patch.object(owned_requests.handoff, '_write', side_effect=write):
            result = workers.run_owned('service', self.owner, 'body', work_context='work', request_id='request')
        self.assertEqual(failures, [True])
        self.assertEqual(result['status'], 'unknown')
        self.assertIsNotNone(children[0].poll())
        with mock.patch.object(workers, '_execute_owned', side_effect=AssertionError('must not rerun')):
            self.assertEqual(workers.run_owned('service', self.owner, 'body', work_context='work',
                                              request_id='request')['status'], 'unknown')

    def test_cancellation_after_birth_refuses_native_model_binding(self):
        from xsm import owned_requests, identity
        row = self.running()
        child = subprocess.Popen([sys.executable, '-B', '-c', 'import sys;sys.stdin.read()'], stdin=subprocess.PIPE)
        try:
            owned_requests.note_child(self.owner, 'request', row['reservation']['token'],
                                      child.pid, identity.lstart(child.pid))
            self.cancel()
            with self.assertRaisesRegex(owned_requests.OwnedError, 'cancellation requested'):
                owned_requests.bind_native_context(self.owner, 'request', row['reservation']['token'], 'observed-native')
        finally:
            child.stdin.close(); child.wait(timeout=3)

    def test_native_stop_report_requires_current_bound_child_and_request(self):
        from xsm import owned_requests, identity
        row = self.running(); token = row['reservation']['token']
        child = subprocess.Popen([sys.executable, '-B', '-c', 'import sys;sys.stdin.read()'], stdin=subprocess.PIPE)
        try:
            owned_requests.note_child(self.owner, 'request', token, child.pid, identity.lstart(child.pid))
            owned_requests.bind_native_context(self.owner, 'request', token, 'observed-native')
            self.assertFalse(owned_requests.cancellation_pending(self.owner, 'request', token))
            with self.assertRaises(owned_requests.OwnedError):
                owned_requests.confirm_native_stop(self.owner, 'request', token, 'observed-native')
            self.cancel()
            self.assertTrue(owned_requests.cancellation_pending(self.owner, 'request', token))
            with self.assertRaises(owned_requests.OwnedError):
                owned_requests.confirm_native_stop(self.owner, 'request', token, 'another-native')
            reported = owned_requests.confirm_native_stop(self.owner, 'request', token, 'observed-native')
            self.assertEqual(reported['cancellation']['child_pid'], child.pid)
            self.assertEqual(reported['cancellation']['native_state'], 'stopped')
            # This process is a frontend fixture, not proof of a native model stop.
            # Recording its explicit observation must not kill the frontend itself.
            self.assertIsNone(child.poll())
        finally:
            child.stdin.close(); child.wait(timeout=3)
        with self.assertRaises(owned_requests.OwnedError):
            owned_requests.confirm_native_stop(self.owner, 'request', token, 'observed-native')
        owned_requests.note_exit(self.owner, 'request', token, child.returncode)
        finished = owned_requests.mark_unknown(self.owner, 'request', token, 'aborted native turn has unknown effects')
        self.assertFalse(finished['slot_occupied'])

    def test_client_exit_does_not_release_capacity_without_native_stop_confirmation(self):
        from xsm import owned_requests, identity
        row = self.running(); token = row['reservation']['token']
        child = subprocess.Popen([sys.executable, '-B', '-c', 'import sys;sys.stdin.read()'], stdin=subprocess.PIPE)
        try:
            owned_requests.note_child(self.owner, 'request', token, child.pid, identity.lstart(child.pid))
            self.cancel()
        finally:
            child.stdin.close(); child.wait(timeout=3)
        owned_requests.note_exit(self.owner, 'request', token, child.returncode)
        unverified = owned_requests.mark_unknown(self.owner, 'request', token, 'client detached')
        self.assertEqual(unverified['execution_state'], 'exited')
        self.assertTrue(unverified['slot_occupied'])
        self.assertEqual(owned_requests.active_count(self.owner), 1)

    def test_shared_action_and_cli_cancel_the_exact_queued_request(self):
        import contextlib
        import io
        from xsm import cli, owned_service
        self.submit()
        result = owned_service.execute(self.owner, dict(action='cancel', name='service', request_id='request'))
        self.assertEqual(result['status'], 'cancelled')
        self.assertFalse(result['cancellation']['native_supported'])
        args = cli.build_parser().parse_args(['owned', 'cancel', 'service', '--request-id', 'request'])
        with mock.patch.object(cli, '_unsure_caller', return_value=(self.owner, None)), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.cmd_owned(args), cli.OK)
        with self.assertRaises(owned_service.ActionError):
            owned_service.execute(self.owner, dict(action='cancel', name='service'))

    def test_cancel_does_not_discard_a_completed_native_result(self):
        from xsm import owned_requests
        row = self.running()
        ready = owned_requests.save_result(self.owner, 'request', row['reservation']['token'],
            dict(body='observed result', outcome=None, native_session_id=row['context']['session_seed']))
        cancelled = self.cancel()
        self.assertEqual(cancelled['status'], 'result-ready')
        self.assertEqual(cancelled['result'], ready['result'])
        self.assertEqual(cancelled['reply_id'], ready['reply_id'])
        self.assertNotIn('cancellation', cancelled)

    def readback_fixture(self, *, alive=False, exit_code=0, runtime='pi'):
        """Version/output fixtures, not actual native runs; the native probes are separate."""
        from xsm import workers, owned_requests, native_workers, host_install, identity
        self.worker['runtime'] = runtime
        host_install.apply(runtime, self.worker['home'])
        binary = Path(self.tmp, 'version-fixture')
        version = '1.19.5' if runtime == 'opencode' else '1.4.0'
        binary.write_text('#!' + sys.executable + '\nprint(' + repr(version) + ')\n'); binary.chmod(0o700)
        with mock.patch.dict(os.environ, {'XSM_OPENCODE' if runtime == 'opencode' else 'XSM_PI': str(binary)}):
            provider = native_workers.provider(runtime)
            self.worker['native_provider'] = provider.prepare(self.worker['home'])
        workers.save(self.worker); row = self.running(); token = row['reservation']['token']
        output = Path(self.tmp, 'owned-runs', self.worker['id'], 'request.jsonl')
        output.parent.mkdir(parents=True)
        native_id = 'ses_fixturecancelled' if runtime == 'opencode' else row['context']['session_seed']
        events = ([dict(type='error', sessionID=native_id, error={'name': 'MessageAbortedError'})]
                  if runtime == 'opencode' else [dict(type='session', id=native_id, cwd=self.tmp),
                    dict(type='agent_end', willRetry=False, messages=[]), dict(type='agent_settled', aborted=True)])
        output.write_text('\n'.join(json.dumps(event) for event in events) + '\n')
        child = subprocess.Popen([sys.executable, '-B', '-c',
            'import sys;sys.stdin.read();sys.exit(' + str(exit_code) + ')'], stdin=subprocess.PIPE)
        def cleanup():
            if not child.stdin.closed: child.stdin.close()
            child.wait(timeout=3)
        self.addCleanup(cleanup)
        owned_requests.note_child(self.owner, 'request', token, child.pid, identity.lstart(child.pid), stdout=str(output))
        owned_requests.bind_native_context(self.owner, 'request', token, native_id)
        self.cancel()
        if not alive:
            cleanup(); owned_requests.note_exit(self.owner, 'request', token, child.returncode)
        owned_requests.mark_unknown(self.owner, 'request', token, 'lost native stop confirmation')
        return output, provider

    def test_reconcile_recovers_stop_without_executing_or_creating_an_answer(self):
        from xsm import workers
        output, provider = self.readback_fixture()
        with mock.patch.object(provider, 'argv', side_effect=AssertionError('must not execute native CLI')):
            recovered = workers.reconcile_owned('service', self.owner, 'request')
            repeated = workers.reconcile_owned('service', self.owner, 'request')
        self.assertEqual(recovered['status'], 'unknown')
        self.assertEqual(recovered['cancellation']['recovered_from'], 'native-output')
        self.assertEqual(recovered['cancellation']['native_state'], 'stopped')
        self.assertEqual(recovered['cancellation'], repeated['cancellation'])
        self.assertFalse(recovered['slot_occupied'])
        self.assertIsNone(recovered['result']); self.assertIsNone(recovered['reply_id'])

    def test_reconcile_refuses_symlinked_output_file_and_directory(self):
        from xsm import workers
        output, _ = self.readback_fixture(); text = output.read_text()
        other = Path(self.tmp, 'other-output.jsonl'); other.write_text(text)
        output.unlink(); output.symlink_to(other)
        self.assertEqual(workers.reconcile_owned('service', self.owner, 'request')['cancellation']['native_state'], 'unverified')
        output.unlink(); output.write_text(text)
        directory = output.parent; relocated = Path(self.tmp, 'relocated-output'); directory.rename(relocated)
        directory.symlink_to(relocated, target_is_directory=True)
        self.assertEqual(workers.reconcile_owned('service', self.owner, 'request')['cancellation']['native_state'], 'unverified')

    def test_reconcile_refuses_output_while_execution_child_is_live(self):
        from xsm import workers
        self.readback_fixture(alive=True)
        result = workers.reconcile_owned('service', self.owner, 'request')
        self.assertEqual(result['cancellation']['native_state'], 'unverified')
        self.assertTrue(result['slot_occupied'])

    def test_reconcile_refuses_known_failed_exit_even_with_abort_output(self):
        from xsm import workers
        self.readback_fixture(exit_code=7)
        result = workers.reconcile_owned('service', self.owner, 'request')
        self.assertEqual(result['cancellation']['native_state'], 'unverified')
        self.assertTrue(result['slot_occupied'])

    def test_reconcile_refuses_another_native_conversation_output(self):
        from xsm import workers
        output, _ = self.readback_fixture()
        events = [json.loads(line) for line in output.read_text().splitlines()]
        events[0]['id'] = '22345678-1234-4234-8234-123456789abc'
        output.write_text('\n'.join(json.dumps(event) for event in events))
        result = workers.reconcile_owned('service', self.owner, 'request')
        self.assertEqual(result['cancellation']['native_state'], 'unverified')
        self.assertIsNone(result['result'])

    def test_reconcile_cannot_apply_old_stop_evidence_to_a_new_context_generation(self):
        from xsm import workers, owned_requests
        self.readback_fixture()
        with owned_requests._locked(self.owner) as state:
            request = state['requests']['request']
            state['contexts'][request['context_id']]['epoch'] = 'different-generation'
        with self.assertRaisesRegex(owned_requests.OwnedError, 'generation changed'):
            workers.reconcile_owned('service', self.owner, 'request')
        self.assertEqual(owned_requests.status(self.owner, 'request')['cancellation']['native_state'], 'unverified')

    def test_opencode_abort_exit_one_recovers_stop_without_a_business_answer(self):
        from xsm import workers
        self.readback_fixture(runtime='opencode', exit_code=1)
        result = workers.reconcile_owned('service', self.owner, 'request')
        self.assertEqual(result['cancellation']['native_state'], 'stopped')
        self.assertEqual(result['status'], 'unknown')
        self.assertIsNone(result['result']); self.assertIsNone(result['reply_id'])

    def test_opencode_other_exit_or_other_error_does_not_recover_stop(self):
        from xsm import workers, owned_requests
        output, _ = self.readback_fixture(runtime='opencode', exit_code=1)
        output.write_text(json.dumps(dict(type='error', sessionID='ses_fixturecancelled',
                                          error={'name': 'APIError', 'data': {'message': 'Aborted'}})))
        self.assertEqual(workers.reconcile_owned('service', self.owner, 'request')['cancellation']['native_state'], 'unverified')
        with owned_requests._locked(self.owner) as state:
            state['requests']['request']['child']['returncode'] = 7
        output.write_text(json.dumps(dict(type='error', sessionID='ses_fixturecancelled', error={'name': 'MessageAbortedError'})))
        self.assertEqual(workers.reconcile_owned('service', self.owner, 'request')['cancellation']['native_state'], 'unverified')

    def test_confirmed_stopped_service_removal_keeps_unknown_request_and_native_profile(self):
        from xsm import workers, owned_requests
        self.readback_fixture()
        recovered = workers.reconcile_owned('service', self.owner, 'request')
        journal = Path(owned_requests._path(self.owner))
        before = journal.read_bytes(); modified = journal.stat().st_mtime_ns
        workers.stop('service')
        self.assertIsNone(workers.load('service'))
        self.assertTrue(Path(self.worker['home']).is_dir())
        self.assertEqual(journal.read_bytes(), before)
        self.assertEqual(journal.stat().st_mtime_ns, modified)
        retained = workers.owned_status('service', self.owner, 'request')
        self.assertEqual(retained['status'], 'unknown')
        self.assertFalse(retained['worker_record_present'])
        self.assertEqual(retained['cancellation'], recovered['cancellation'])

    def test_service_removal_cannot_drop_a_queued_request(self):
        from xsm import workers
        self.submit()
        with self.assertRaises(workers.WorkerError): workers.stop('service')
        self.assertIsNotNone(workers.load('service'))

    def test_service_removal_cannot_drop_an_unpublished_result(self):
        from xsm import workers, owned_requests
        row = self.running()
        owned_requests.save_result(self.owner, 'request', row['reservation']['token'],
            dict(body='stored answer', outcome=None, native_session_id=row['context']['session_seed']))
        with self.assertRaises(workers.WorkerError): workers.stop('service')
        self.assertIsNotNone(workers.load('service'))

    def test_service_removal_rechecks_worker_generation_before_cleanup(self):
        import contextlib
        from xsm import workers
        replacement = dict(self.worker, id='b' * 32)
        @contextlib.contextmanager
        def swapped(_worker):
            workers.save(replacement)
            yield
        with mock.patch.object(workers, '_owned_record_lock', side_effect=swapped):
            with self.assertRaisesRegex(workers.WorkerError, 'service changed'): workers.stop('service')
        self.assertEqual(workers.load('service')['id'], replacement['id'])

    def test_submission_cannot_create_orphan_request_after_service_removal(self):
        from xsm import workers, owned_requests
        original_cleanup, original_lookup = workers._cleanup, workers._owned_worker
        removing, loaded, release = threading.Event(), threading.Event(), threading.Event()
        def cleanup(worker):
            removing.set()
            if not release.wait(3): raise RuntimeError('test cleanup release deadline')
            return original_cleanup(worker)
        def lookup(name):
            worker = original_lookup(name); loaded.set(); return worker
        with mock.patch.object(workers, '_cleanup', side_effect=cleanup), \
                mock.patch.object(workers, '_owned_worker', side_effect=lookup), \
                concurrent.futures.ThreadPoolExecutor(2) as pool:
            stopping = pool.submit(workers.stop, 'service')
            try:
                self.assertTrue(removing.wait(3))
                submission = pool.submit(workers.submit_owned, 'service', self.owner, 'body',
                                         work_context='work', request_id='request')
                self.assertTrue(loaded.wait(3))
                self.assertFalse(submission.done())
            finally: release.set()
            stopping.result(5)
            with self.assertRaises(workers.WorkerError): submission.result(5)
        self.assertEqual(owned_requests.status(self.owner, 'request')['status'], 'not-found')

    def test_confirmed_native_stop_cannot_remove_a_still_live_frontend(self):
        from xsm import workers, owned_requests
        self.readback_fixture(alive=True)
        row = owned_requests.status(self.owner, 'request')
        owned_requests.confirm_native_stop(self.owner, 'request', row['reservation']['token'],
                                           row['context']['native_session_id'])
        with self.assertRaises(workers.WorkerError): workers.stop('service')
        self.assertIsNotNone(workers.load('service'))

    def test_retained_status_survives_service_name_reuse_by_another_owner(self):
        from xsm import workers
        self.readback_fixture(); workers.reconcile_owned('service', self.owner, 'request'); workers.stop('service')
        replacement = dict(self.worker, id='b' * 32, owner=dict(self.owner, session_id='another-owner'))
        workers.save(replacement)
        retained = workers.owned_status('service', self.owner, 'request')
        self.assertEqual(retained['worker']['id'], self.worker['id'])
        self.assertFalse(retained['worker_record_present'])
        self.assertEqual(retained['status'], 'unknown')
