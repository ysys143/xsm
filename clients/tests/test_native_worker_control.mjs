import assert from 'node:assert/strict';
import { test } from 'node:test';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';
import { NativeWorkerControl, WorkerControlError, WORKER_CONTROL_FD } from '../typescript/native-worker-control.mjs';
const run = promisify(execFile);
const peer = fileURLToPath(new URL('./native_worker_control_peer.py', import.meta.url));

test('Node cancellation query preserves false and reports only its bound native stop', async () => {
  const { stdout } = await run(process.env.PYTHON ?? 'python3', ['-B', peer, 'cancel', process.execPath], { timeout: 6000 });
  const result = JSON.parse(stdout);
  assert.equal(result.exit, 0);
  assert.deepEqual(result.node.cancellation, [false, true]);
  assert.deepEqual(result.stops, ['native-한글']);
});

test('private descriptor is absent ordinarily and invalid hints are removed/refused', () => {
  assert.equal(NativeWorkerControl.fromEnvironment({}), undefined);
  for (const value of ['2', 'bad', '-1', '9007199254740993']) {
    const env = { [WORKER_CONTROL_FD]: value };
    assert.throws(() => NativeWorkerControl.fromEnvironment(env), WorkerControlError);
    assert.equal(env[WORKER_CONTROL_FD], undefined);
  }
});

test('Node frontend binds over the actual Python private control descriptor', async () => {
  const { stdout } = await run(process.env.PYTHON ?? 'python3', ['-B', peer, 'normal', process.execPath], { timeout: 6000 });
  const result = JSON.parse(stdout);
  assert.equal(result.exit, 0);
  assert.deepEqual(result.bindings, ['native-한글', 'native-한글']);
  assert.equal(result.node.nativeID, 'native-한글');
  assert.equal(result.node.changedRefused, true);
  assert.equal(result.node.descriptorHintRemoved, true);
});

for (const mode of ['refuse', 'bad-duplicate', 'bad-bool-id', 'bad-int-confirmation']) {
  test(`private binding rejects ${mode} without confirmed native ownership`, async () => {
    const { stdout } = await run(process.env.PYTHON ?? 'python3', ['-B', peer, mode, process.execPath], { timeout: 6000 });
    const result = JSON.parse(stdout);
    assert.equal(result.exit, 0);
    assert.equal(result.node.status, 'refused');
    assert.equal(result.node.nativeID, null);
    assert.deepEqual(result.bindings, []);
  });
}
