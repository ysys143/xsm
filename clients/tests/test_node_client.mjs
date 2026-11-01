import assert from 'node:assert/strict';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { XsmClient, RpcError, TransportError } from '../typescript/xsm-client.mjs';

const peer = fileURLToPath(new URL('./echo_peer.py', import.meta.url));
const python = process.env.PYTHON ?? 'python3';
async function connect(t, mode = 'normal', options = {}) {
  const client = await XsmClient.connect({
    command: [python, '-u', peer, mode], closeTimeout: 100, ...options,
  });
  t.after(() => client.close());
  return client;
}
const settings = { timeout: 5000 };

test('default command', settings, () => {
  assert.deepEqual(XsmClient.DEFAULT_COMMAND, ['python3', '-m', 'xsm', 'protocol', 'serve', '--stdio']);
});

test('concurrent requests correlate reversed responses and split UTF-8', settings, async t => {
  const client = await connect(t);
  assert.deepEqual(await Promise.all([
    client.request('test.pair', { text: 'first 세션' }),
    client.request('test.pair', { text: 'second 세션' }),
  ]), [{ text: 'first 세션' }, { text: 'second 세션' }]);
});

test('session methods and events/available carry opaque handle', settings, async t => {
  const client = await connect(t);
  const opened = await client.sessionOpen({ runtime: 'test', profile: 'local', conversation: 'a', cwd: '/tmp' });
  assert.equal(opened.generation, 7);
  assert.equal(opened.extra, 'preserved');
  const { session } = opened;
  // The echo fixture checks transport only; real server validation is separate.
  assert.equal((await client.sessionUpdate(session, { state: 'busy' })).session, session);
  assert.deepEqual(await client.operationCall(session, 'echo', { value: '한글' }),
    { session, operation: 'echo', arguments: { value: '한글' } });
  // Exercise a consumer already waiting when the notification arrives.
  const notification = client.nextNotification();
  await client.eventsSubscribe(session);
  assert.deepEqual(await notification, { jsonrpc: '2.0', method: 'events/available',
    params: { session, ids: ['delivery-세'] } });
  assert.deepEqual(await client.deliveryReport(session, 'delivery-세', 'queued'),
    { session, id: 'delivery-세', state: 'queued' });
  assert.deepEqual(await client.sessionClose(session), { session });
});

test('RPC error preserves code/data and leaves transport usable', settings, async t => {
  const client = await connect(t);
  await assert.rejects(client.request('test.error'), error => {
    assert.ok(error instanceof RpcError);
    assert.equal(error.code, -32042);
    assert.equal(error.message, 'expected failure');
    assert.deepEqual(error.data, { detail: '세부' });
    return true;
  });
  assert.deepEqual(await client.request('echo', { ok: true }), { ok: true });
});

test('stderr cannot be mistaken for an RPC response', settings, async t => {
  const chunks = [];
  const client = await connect(t, 'normal', { onStderr: text => chunks.push(text) });
  assert.equal(await client.request('test.stderr'), 'stdout only');
  await client.close();
  assert.match(chunks.join(''), /"id":"fake"/);
  assert.equal(chunks.join('').split('진단').length - 1, 50_000);
});

test('large JSONL frame', settings, async t => {
  const client = await connect(t);
  assert.equal(await client.request('test.large'), '세'.repeat(100_000));
});

test('stderr consumer failure still drains and reaps the peer', settings, async t => {
  const client = await connect(t, 'normal', { onStderr() { throw new Error('consumer failed'); } });
  await assert.rejects(client.request('test.stderr'), TransportError);
  await client.close();
  assert.ok(client.process.exitCode !== null || client.process.signalCode !== null);
});

for (const mode of ['eof', 'malformed', 'malformed-noisy', 'truncated', 'utf8', 'bad-response', 'bad-error', 'peer-request']) {
  test(`reject every pending request and notification consumer on ${mode}`, settings, async t => {
    const client = await connect(t, mode);
    const results = await Promise.allSettled([
      client.request('test.pair'), client.request('test.pair'), client.nextNotification(),
    ]);
    for (const result of results) {
      assert.equal(result.status, 'rejected');
      assert.ok(result.reason instanceof TransportError, result.reason);
    }
    await assert.rejects(client.request('echo'), TransportError);
    await client.close();
    assert.ok(client.process.exitCode !== null || client.process.signalCode !== null);
  });
}

test('close rejects pending calls, is idempotent, and kills a stubborn peer', settings, async t => {
  const client = await connect(t, 'stubborn');
  const pending = assert.rejects(client.request('test.hold'), TransportError);
  await client.close();
  await pending;
  assert.equal(client.process.signalCode, 'SIGKILL');
  await client.close();
});

test('host decision and missing session guards; bad caller data leaves transport usable', settings, async t => {
  const client = await connect(t);
  await assert.rejects(client.request('decision.response', { session: 'forged' }), /trusted host/);
  for (const method of ['session.update', 'session.close', 'operation.call', 'events.subscribe', 'delivery.report']) {
    await assert.rejects(client.request(method), /opaque handle/);
  }
  assert.throws(() => client.sessionUpdate('handle', { session: 'forged' }), /without session/);
  const circular = {};
  circular.self = circular;
  await assert.rejects(client.request('echo', circular), TypeError);
  assert.deepEqual(await client.request('echo'), {});
});

test('initialize error, initialize EOF and spawn failure reject connect', settings, async () => {
  for (const [mode, error] of [['init-error', RpcError], ['init-eof', TransportError]]) {
    await assert.rejects(XsmClient.connect({ command: [python, '-u', peer, mode] }), error);
  }
  await assert.rejects(XsmClient.connect({ command: ['/does-not-exist/xsm'] }), TransportError);
});

test('final response before exit is delivered and graceful close reaps the peer', settings, async t => {
  const client = await connect(t);
  assert.deepEqual(await client.request('test.final'), { final: true });
  await assert.rejects(client.nextNotification(), TransportError);
  await client.close();
  assert.equal(client.process.exitCode, 0);
});

test('version negotiation rejects invalid results and reaps peer', settings, async t => {
  const seen = [];
  class Observed extends XsmClient {
    constructor(...args) { super(...args); seen.push(this); }
  }
  t.after(() => Promise.all(seen.map(client => client.close())));
  for (const mode of ['init-wrong-version', 'init-missing-version', 'init-nonobject']) {
    await assert.rejects(Observed.connect({ command: [python, '-u', peer, mode], closeTimeout: 100 }),
      error => error instanceof TransportError && /version negotiation/.test(error.message));
    assert.ok(seen.at(-1).process.exitCode !== null || seen.at(-1).process.signalCode !== null);
  }
});

test('negotiation error survives cleanup failure after reaping', settings, async t => {
  const seen = [], diagnostics = [];
  class CleanupFails extends XsmClient {
    constructor(...args) { super(...args); seen.push(this); }
    async close() { await super.close(); throw new Error('fixture cleanup failure'); }
  }
  t.after(() => Promise.all(seen.map(client => client.close().catch(() => {}))));
  await assert.rejects(CleanupFails.connect({ command: [python, '-u', peer, 'init-wrong-version'],
    closeTimeout: 100, onStderr: text => diagnostics.push(text) }),
    error => error instanceof TransportError && /version negotiation/.test(error.message));
  assert.ok(seen[0].process.exitCode !== null || seen[0].process.signalCode !== null);
  assert.ok(diagnostics.some(text => /fixture cleanup failure/.test(text)));
});
