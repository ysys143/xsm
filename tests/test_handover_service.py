"""Shared handover orchestration preserves approval and exact successor identity."""
import io
import os
from contextlib import redirect_stdout, redirect_stderr
from unittest import mock
from tests.test_xsm import TempState


class HandoverServiceTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import registry
        self.home = self.tmp + '/profile'; os.makedirs(self.home)
        for sid in ('a', 'b', 'c', 'd'):
            registry.upsert('codex', self.home, sid, os.getpid(), self.tmp, name=sid)
        self.a, self.b, self.c, self.d = [registry.by_session('codex', sid) for sid in ('a', 'b', 'c', 'd')]

    def test_absent_or_empty_approval_cannot_move_a_place(self):
        from xsm import handover, handover_service
        for authorize in (None, lambda target: '', lambda target: True):
            with self.subTest(authorize=authorize), self.assertRaises(handover_service.DecisionRefused):
                handover_service.execute(self.a, {'target': 'ref:' + self.b['ref'], 'summary': 'continue'}, authorize=authorize)
            self.assertIsNone(handover.load(self.a))

    def test_cli_and_model_use_common_handover(self):
        from xsm import cli, context, handover, handover_service, mcp, registry
        server = mcp.Server(io.StringIO(), io.StringIO()); server.session = lambda: self.c
        with mock.patch.object(handover_service, 'execute', wraps=handover_service.execute) as common:
            with mock.patch.object(registry, 'me', return_value=self.a), \
                    mock.patch.object(registry, 'last_identity', return_value=context.of_record(self.a, context.BASIS_SESSION)), \
                    mock.patch.object(cli, '_person_or_refuse', return_value=None), \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(['handover', 'ref:' + self.b['ref'], '--summary', 'cli context']), 0)
            with mock.patch.object(server, 'allowed', return_value=(True, '')):
                result = server.call('xsm_handover', {'action': 'hand_over', 'target': 'ref:' + self.d['ref'], 'summary': 'model context'})
            self.assertEqual(common.call_count, 2)
            self.assertIn('handed', result)
        self.assertEqual(handover.load(self.a)['to_identity']['session_id'], self.b['session_id'])
        self.assertEqual(handover.load(self.c)['to_identity']['session_id'], self.d['session_id'])

    def test_approval_cannot_redirect_a_reassigned_name(self):
        from xsm import handover_service, registry
        def approve(target):
            registry.upsert('codex', self.home, 'b', os.getpid(), self.tmp, name='renamed')
            registry.upsert('codex', self.home, 'd', os.getpid(), self.tmp, name='b')
            return 'synthetic user approval'
        result = handover_service.execute(self.a, {'target': 'b', 'summary': 'exact successor'}, authorize=approve)
        self.assertEqual(result['record']['to_identity']['session_id'], self.b['session_id'])

    def test_successor_closed_during_approval_is_refused_before_mutation(self):
        from xsm import handover, handover_service, registry
        def approve(target):
            registry.mark_ended('codex', 'b', 'worker-stopped', home=self.home)
            return 'synthetic user approval'
        with self.assertRaises(handover.HandoverError):
            handover_service.execute(self.a, {'target': 'b', 'summary': 'continue'}, authorize=approve)
        self.assertIsNone(handover.load(self.a))
