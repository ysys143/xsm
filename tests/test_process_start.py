"""Owned process identity uses kernel generation without wall-clock rounding."""
import os
import unittest
from unittest import mock
from pathlib import Path
from xsm import identity, owned_requests

BOOT = '00000000-0000-4000-8000-000000000001'


def proc_stat(ticks):
    return '321 (worker (with spaces)) ' + ' '.join(['S'] + ['0'] * 18 + [str(ticks)] + ['0'] * 5)


class ProcessStartTest(unittest.TestCase):
    def setUp(self):
        # TempState-based neighbors reload xsm modules. Patch the same identity
        # instance the current worker module actually uses, never a stale import.
        global identity, owned_requests
        from xsm import identity as current_identity, owned_requests as current_owned
        identity, owned_requests = current_identity, current_owned

    def test_linux_generation_ignores_ps_wall_clock_changes(self):
        def read(path, *args, **kwargs):
            return BOOT if str(path).endswith('boot_id') else proc_stat(123)
        with mock.patch.object(identity.sys, 'platform', 'linux'), \
                mock.patch.object(Path, 'read_text', autospec=True, side_effect=read), \
                mock.patch.object(identity, 'lstart', side_effect=['time one','time two']) as wall:
            first = identity.process_start(321)
            self.assertEqual(identity.process_start(321), first)
            self.assertTrue(identity.process_matches(321, first))
            wall.assert_not_called()

    def test_pid_reuse_and_reboot_are_distinct_generations(self):
        state = {'ticks':123, 'boot':BOOT}
        def read(path, *args, **kwargs):
            return state['boot'] if str(path).endswith('boot_id') else proc_stat(state['ticks'])
        with mock.patch.object(identity.sys, 'platform', 'linux'), \
                mock.patch.object(Path, 'read_text', autospec=True, side_effect=read):
            original=identity.process_start(321)
            state['ticks']=124
            self.assertFalse(identity.process_matches(321, original))
            state.update(ticks=123,boot='00000000-0000-4000-8000-000000000002')
            self.assertFalse(identity.process_matches(321, original))

    def test_unreadable_generation_is_unknown_without_ps_fallback(self):
        with mock.patch.object(identity.sys, 'platform', 'linux'), \
                mock.patch.object(Path, 'read_text', side_effect=PermissionError), \
                mock.patch.object(identity,'lstart') as wall:
            self.assertIsNone(identity.process_start(321))
            self.assertIsNone(identity.process_matches(321,'linux-start:'+BOOT+':123'))
            wall.assert_not_called()

    def test_legacy_journal_generations_keep_existing_comparison(self):
        with mock.patch.object(identity,'lstart',return_value='legacy timestamp'):
            self.assertTrue(identity.process_matches(321,'legacy timestamp'))
            self.assertFalse(identity.process_matches(321,'other timestamp'))
        with mock.patch.object(identity.sys,'platform','darwin'), mock.patch.object(identity,'lstart',return_value='mac timestamp'):
            self.assertEqual(identity.process_start(321),'mac timestamp')

    def test_owned_liveness_uses_stable_generation(self):
        with mock.patch.object(identity,'pid_alive',return_value=True), \
                mock.patch.object(identity,'process_matches',return_value=True) as check:
            self.assertTrue(owned_requests._alive({'pid':321,'lstart':'linux-start:'+BOOT+':123'}))
            check.assert_called_once_with(321,'linux-start:'+BOOT+':123')

    def test_actual_current_process_has_a_repeatable_generation(self):
        key=identity.process_start(os.getpid())
        self.assertIsInstance(key,str)
        self.assertTrue(identity.process_matches(os.getpid(),key))

    def test_termination_accepts_exact_kernel_key_without_legacy_ps(self):
        from xsm import workers
        with mock.patch.object(identity,'pid_alive',side_effect=[True,False]),                 mock.patch.object(identity,'process_matches',return_value=True),                 mock.patch.object(identity,'lstart',side_effect=AssertionError('legacy ps queried')),                 mock.patch.object(workers.os,'killpg') as signal:
            workers._terminate(321,'linux-start:'+BOOT+':123')
        signal.assert_called_once()

    def test_termination_rechecks_generation_before_escalation(self):
        from xsm import workers
        for matches,expected in (([True,False],1),([None],0),([False],0)):
            with self.subTest(matches=matches),mock.patch.object(identity,'pid_alive',return_value=True),                     mock.patch.object(identity,'process_matches',side_effect=matches),                     mock.patch.object(workers.os,'killpg') as signal:
                workers._terminate(321,'linux-start:'+BOOT+':123')
                self.assertEqual(signal.call_count,expected)
