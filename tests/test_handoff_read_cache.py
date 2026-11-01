"""A parsed-record cache is a read optimization, never ownership authority."""
import os
import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

from tests.test_xsm import TempState


class HandoffReadCacheTest(TempState):
    def setUp(self):
        super().setUp()
        from xsm import handoff
        handoff._clear_read_cache()
        self.addCleanup(handoff._clear_read_cache)
        self.receiver = {'runtime': 'fixture', 'home': self.tmp, 'session_id': 'receiver'}
        self.sender = {'runtime': 'fixture', 'home': self.tmp, 'session_id': 'sender'}
        handoff.store(self.receiver, {'id': 'cache-message', 'sender': self.sender, 'body': 'x' * 20000})

    def test_unchanged_large_records_are_not_reparsed_and_returned_values_are_private(self):
        from xsm import handoff, paths
        with mock.patch.object(paths, 'read_json', wraps=paths.read_json) as read:
            first = handoff.status(self.receiver, 'cache-message')
            first['message']['body'] = 'caller modification'
            second = handoff.status(self.receiver, 'cache-message')
            self.assertEqual(second['message']['body'], 'x' * 20000)
            self.assertEqual(read.call_count, 1)

    def test_inplace_rewrite_with_restored_mtime_still_invalidates_cache(self):
        from xsm import handoff
        handoff.status(self.receiver, 'cache-message')
        path = Path(handoff._folder(self.receiver), 'cache-message.json')
        before = path.stat()
        text = path.read_text()
        path.write_text(text.replace('x' * 20000, 'y' * 20000))
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertEqual(path.stat().st_size, before.st_size)
        self.assertEqual(handoff.status(self.receiver, 'cache-message')['message']['body'], 'y' * 20000)

    def test_transition_revalidates_current_claim_and_keeps_ack_idempotent(self):
        from xsm import handoff
        owner = {'type': 'native', 'id': 'reader'}
        claim = handoff.claim(self.receiver, owner, 'generation')
        token = claim['claim']['token']
        handoff.status(self.receiver, 'cache-message')
        handoff.release(self.receiver, token, owner, 'generation')
        with self.assertRaises(ValueError):
            handoff.ack(self.receiver, token, owner, 'generation')
        next_claim = handoff.claim(self.receiver, owner, 'generation')
        self.assertNotEqual(next_claim['claim']['token'], token)
        for _ in range(2):
            self.assertEqual(handoff.ack(self.receiver, next_claim['claim']['token'], owner, 'generation')['status'], 'acknowledged')

    def test_failed_write_does_not_mutate_the_cached_authoritative_state(self):
        from xsm import handoff, paths
        handoff.status(self.receiver, 'cache-message')
        with mock.patch.object(paths, 'write_json', side_effect=OSError('fixture write failed')):
            with self.assertRaises(OSError):
                handoff.claim(self.receiver, {'type': 'native', 'id': 'reader'}, 'generation')
        self.assertEqual(handoff.status(self.receiver, 'cache-message')['status'], 'pending')

    def test_cache_evicts_records_to_its_byte_budget(self):
        from xsm import handoff
        budget = Path(handoff._folder(self.receiver), 'cache-message.json').stat().st_size + 1000
        with mock.patch.object(handoff, '_READ_CACHE_LIMIT', budget):
            handoff.status(self.receiver, 'cache-message')
            handoff.store(self.receiver, {'id': 'second', 'sender': self.sender, 'body': 'y' * 20000})
            handoff.status(self.receiver, 'second')
            self.assertLessEqual(handoff._READ_CACHE_BYTES, budget)
            self.assertEqual(len(handoff._READ_CACHE), 1)

    def test_another_process_replacing_a_claim_cannot_reuse_cached_authority(self):
        from xsm import handoff
        owner = {'type': 'native', 'id': 'reader'}
        claim = handoff.claim(self.receiver, owner, 'old-generation')
        handoff.status(self.receiver, 'cache-message')
        code = "import json,sys;from xsm import handoff;r=json.loads(sys.argv[1]);o={'type':'native','id':'reader'};handoff.release(r,sys.argv[2],o,'old-generation');handoff.claim(r,o,'new-generation')"
        subprocess.run([sys.executable, '-B', '-c', code, json.dumps(self.receiver), claim['claim']['token']], check=True)
        with self.assertRaises(ValueError):
            handoff.ack(self.receiver, claim['claim']['token'], owner, 'old-generation')
        self.assertEqual(handoff.status(self.receiver, 'cache-message')['claim']['generation'], 'new-generation')
