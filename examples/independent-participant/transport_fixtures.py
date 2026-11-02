"""Own stdlib mock transport regressions and in-memory defect mutations."""
import argparse
import io
import json
import os
import queue
import subprocess
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import participant


class Input:
    def __init__(self, fail_close=False):
        self.fail_close = fail_close
        self.raw = tempfile.TemporaryFile()
        self.writes = []

    @property
    def closed(self):
        return self.raw.closed

    def write(self, wire):
        self.writes.append(wire)

    def flush(self):
        pass

    def close(self):
        if self.fail_close:
            raise BrokenPipeError('synthetic stdin close failure')
        self.raw.close()


class Output:
    def __init__(self):
        self.frames = queue.Queue()
        self.closed = False

    def readline(self, limit):
        return self.frames.get(timeout=3)

    def close(self):
        self.closed = True
        self.frames.put(b'')


class Process:
    def __init__(self, fail_close=False):
        self.stdin = Input(fail_close)
        self.stdout = Output()
        self.killed = False
        self.waits = 0
        self.reaped = False

    def poll(self):
        return None  # Deliberately alive even after the reader's terminal failure.

    def wait(self, timeout):
        self.waits += 1
        if self.stdin.fail_close and not self.killed:
            raise subprocess.TimeoutExpired('mock', timeout)
        self.reaped = True
        self.stdout.frames.put(b'')
        return 0

    def kill(self):
        self.killed = True


def suite(module):
    class Transport(unittest.TestCase):
        def peer(self, fail_close=False):
            process = Process(fail_close)
            with patch.object(module.subprocess, 'Popen', return_value=process) as popen:
                peer = module.Peer(['/operator/fixture-server', 'protocol', 'serve', '--stdio'])
                argv = popen.call_args.args[0]
                self.assertEqual(argv, ['/operator/fixture-server', 'protocol', 'serve', '--stdio'])
                env = popen.call_args.kwargs['env']
                self.assertLessEqual(set(env), {'PATH', 'LANG', 'TMPDIR', 'HOME', 'XSM_HOME'})
                self.assertEqual(env['HOME'], popen.call_args.kwargs['cwd'])
            # Mutant cleanup must not leak the fixture's real FD or blocked reader.
            self.addCleanup(process.stdout.close)
            self.addCleanup(process.stdin.raw.close)
            self.addCleanup(peer.close)
            return peer, process

        def reject_wire(self, wire):
            peer, process = self.peer()
            future = peer.submit('operations/list')
            process.stdout.frames.put(wire)
            with self.assertRaises((ValueError, UnicodeError)):
                future.result(timeout=1)
            peer.reader.join(timeout=1)
            self.assertFalse(peer.reader.is_alive())
            self.assertIsNone(process.poll())
            before = time.monotonic()
            with self.assertRaises((ValueError, UnicodeError)):
                peer.submit('operations/list')
            self.assertLess(time.monotonic() - before, 0.2)
            self.assertFalse(peer.pending)

        def test_utf8_roundtrip_and_reverse_responses(self):
            peer, process = self.peer()
            one = peer.submit('first', {'text': '한글'})
            two = peer.submit('second')
            self.assertIn('한글'.encode('utf-8'), process.stdin.writes[0])
            process.stdout.frames.put(b'{"jsonrpc":"2.0","id":2,"result":{"value":2}}\n')
            process.stdout.frames.put('{"jsonrpc":"2.0","method":"events/available","params":{"session":"s","ids":["m"]}}\n'.encode('utf-8'))
            process.stdout.frames.put('{"jsonrpc":"2.0","id":1,"result":{"text":"한글"}}\n'.encode('utf-8'))
            self.assertEqual(two.result(timeout=1)['result'], {'value': 2})
            self.assertEqual(one.result(timeout=1)['result'], {'text': '한글'})
            self.assertEqual(peer.notification()['method'], 'events/available')

        def test_utf16_rejected(self):
            # Newline is a byte delimiter; json.loads(bytes) accepts this old defect.
            self.reject_wire(b'\xfe\xff' + '{"jsonrpc":"2.0","id":1,"result":{}}\n'.encode('utf-16-be'))

        def test_utf32_rejected(self):
            self.reject_wire(b'\x00\x00\xfe\xff' + '{"jsonrpc":"2.0","id":1,"result":{}}\n'.encode('utf-32-be'))

        def test_invalid_utf8_rejected(self):
            self.reject_wire(b'{"jsonrpc":"2.0","id":1,"result":"\xff"}\n')

        def test_nan_rejected(self):
            self.reject_wire(b'{"jsonrpc":"2.0","id":1,"result":{"value":NaN}}\n')

        def test_infinity_rejected(self):
            self.reject_wire(b'{"jsonrpc":"2.0","id":1,"result":{"value":Infinity}}\n')

        def test_negative_infinity_rejected(self):
            self.reject_wire(b'{"jsonrpc":"2.0","id":1,"result":{"value":-Infinity}}\n')

        def test_float_overflow_local_limit(self):
            self.reject_wire(b'{"jsonrpc":"2.0","id":1,"result":{"value":1e400}}\n')

        def test_reader_failure_is_terminal_while_process_alive(self):
            self.reject_wire(b'not-json\n')

        def test_close_failure_still_reaps_and_cleans(self):
            peer, process = self.peer(fail_close=True)
            folder = Path(peer.cwd)
            pending = peer.submit('operations/list')
            stdin_fd = process.stdin.raw.fileno()
            diagnostics = peer.close()
            self.assertTrue(process.killed)
            self.assertTrue(process.reaped)
            self.assertEqual(process.waits, 2)
            self.assertTrue(process.stdout.closed)
            self.assertTrue(process.stdin.raw.closed)
            with self.assertRaises(OSError):
                os.fstat(stdin_fd)
            self.assertTrue(peer.errors.closed)
            self.assertFalse(folder.exists())
            self.assertIn('stdin.close', diagnostics)
            with self.assertRaises(EOFError):
                pending.result(timeout=1)
            self.assertEqual(peer.close(), '')

        def test_outgoing_non_json_numbers_rejected_before_write(self):
            peer, process = self.peer()
            for value in (float('nan'), float('inf'), float('-inf')):
                with self.assertRaises(ValueError):
                    peer.submit('fixture', {'value':value})
            self.assertEqual(process.stdin.writes, [])
            self.assertEqual(peer.pending, {})
    return unittest.defaultTestLoader.loadTestsFromTestCase(Transport)


def run(module):
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite(module))
    return {'passed':result.wasSuccessful(), 'tests':result.testsRun,
            'failures':len(result.failures), 'errors':len(result.errors), 'output':stream.getvalue()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = Path(participant.__file__).read_text(encoding='utf-8')
    results = {'baseline':run(participant), 'mutants':{}}
    mutations = {
        'utf16_autodetection': ("decode_json(wire.decode('utf-8', errors='strict'))", 'json.loads(wire, parse_constant=reject_constant, parse_float=finite_float)'),
        'non_json_constants': ('parse_constant=reject_constant', 'parse_constant=float'),
        'lost_terminal_failure': ('if self.terminal_failure is not None:\n                raise self.terminal_failure', 'if False:\n                raise self.terminal_failure'),
        'stdin_close_skips_cleanup': ("attempt('stdin.close', self.process.stdin.close)", 'self.process.stdin.close()'),
    }
    for name, (before, after) in mutations.items():
        if source.count(before) != 1:
            raise AssertionError('mutation binding missing: '+name)
        module = types.ModuleType('fixture_mutant_'+name)
        exec(compile(source.replace(before,after), '<own in-memory mutant>', 'exec'), module.__dict__)
        results['mutants'][name] = run(module)
    success = results['baseline']['passed'] and all(not r['passed'] for r in results['mutants'].values())
    results['status'] = 'passed' if success else 'failed'
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(results,handle,ensure_ascii=False,indent=2)
        handle.write('\n')
    print(json.dumps({'status':results['status'],'baseline_tests':results['baseline']['tests'],
                     'mutants_detected':sum(not r['passed'] for r in results['mutants'].values())}))
    return 0 if success else 1

if __name__ == '__main__':
    raise SystemExit(main())
