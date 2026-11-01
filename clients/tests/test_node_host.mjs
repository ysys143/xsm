import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { XsmHostClient, RpcError } from '../typescript/xsm-client.mjs';

test('real host UI response is scoped and applies only on retry', { timeout: 20000 }, async () => {
  const root = fileURLToPath(new URL('../../', import.meta.url));
  const temp = await mkdtemp(join(tmpdir(), 'xsm-node-host-'));
  let host;
  try {
    host = await XsmHostClient.connect({
      command: [process.env.PYTHON ?? 'python3', '-B', '-m', 'xsm', 'protocol', 'serve', '--stdio'],
      cwd: root, env: { PATH: process.env.PATH ?? '/usr/bin:/bin', HOME: temp,
        XSM_HOME: join(temp, 'state'), PYTHONPATH: root, PYTHONDONTWRITEBYTECODE: '1' },
    });
    const session = await host.sessionOpen({ runtime: 'node-ui', profile: 'isolated',
      conversation: 'a', cwd: root, capabilities: ['user-decisions'] });
    const args = { question: 'Choose a color', options: ['blue', 'green'] };
    const pending = await host.operationCall(session.session, 'xsm_decide', args);
    assert.equal(pending.status, 'waiting-for-user');
    const event = await host.nextNotification();
    assert.equal(event.method, 'decision/request');
    assert.equal(event.params.question, args.question);
    await assert.rejects(host.request('decision.response', {}));
    await assert.rejects(host.respondToDecision(event, {
      displayed: 'wrong question', sourceId: 'node-ui-1', answer: 'blue',
    }), error => error instanceof RpcError);
    const answer = await host.respondToDecision(event, {
      displayed: args.question, sourceId: 'node-ui-1', answer: 'blue',
    });
    assert.equal(answer.status, 'answered');
    const result = await host.operationCall(session.session, 'xsm_decide', args);
    assert.match(JSON.stringify(result), /your user answered: blue/);
    const status = await host.operationCall(session.session, 'xsm_decision_status', { id: pending.decision_id });
    assert.equal(status.status, 'applied');
  } finally {
    if (host) await host.close();
    await rm(temp, { recursive: true, force: true });
  }
});

test('claim release failure preserves original admission error', async () => {
  const { XsmHost, RetryAdmission } = await import('../typescript/xsm-host.mjs');
  for (const primary of [new Error('native refused'), new RetryAdmission('native busy'),
    Object.assign(new Error('cancelled'), { name: 'AbortError' })]) {
    const calls = [], diagnostics = [];
    const cleanup = new Error('backend unavailable during release');
    const client = {
      initialization: { limits: { claimLeaseSeconds: 120 } },
      async operationCall() {
        calls.push('xsm_inbox');
        return { messages: ['original'], claims: [{ id: 'm', token: 't' }], items: [] };
      },
      async request(method, args) {
        calls.push(method);
        assert.deepEqual(args, { session: 's', tokens: ['t'] });
        throw cleanup;
      },
    };
    const host = new XsmHost(client, { session: 's' }, [], {
      deliver: async () => { throw primary; }, onError: error => diagnostics.push(error),
    });
    await assert.rejects(host.deliverInbox(false), error => error === primary);
    assert.deepEqual(diagnostics, [cleanup]);
    assert.deepEqual(calls, ['xsm_inbox', 'inbox.release']);
  }
});

test('host rejects nonfinite or nonnumeric initial leases', async t => {
  const { XsmHost } = await import('../typescript/xsm-host.mjs');
  for (const lease of [true, '120', NaN, Infinity, 0]) {
    let closed = 0;
    const client = { initialization: { capabilities: ['messaging', 'inbox'], limits: { claimLeaseSeconds: lease } },
      async close() { closed++; } };
    const mocked = t.mock.method(XsmHostClient, 'connect', async () => client);
    try {
      await assert.rejects(XsmHost.open({ runtime: 'fixture', profile: 'p', conversation: 'c', cwd: '.' }), /claim lease/);
      assert.equal(closed, 1);
    } finally { mocked.mock.restore(); }
  }
});

test('host initialization retains primary failure when close fails', async t => {
  const { XsmHost } = await import('../typescript/xsm-host.mjs');
  const primary = new Error('session registration failed'), cleanup = new Error('cleanup failed'), diagnostics = [];
  const client = { initialization: { capabilities: ['messaging', 'inbox'], limits: { claimLeaseSeconds: 120 } },
    async sessionOpen() { throw primary; }, async close() { throw cleanup; } };
  t.mock.method(XsmHostClient, 'connect', async () => client);
  await assert.rejects(XsmHost.open({ runtime: 'fixture', profile: 'p', conversation: 'c', cwd: '.',
    onError: error => diagnostics.push(error) }), error => error === primary);
  assert.deepEqual(diagnostics, [cleanup]);
});

test('host setup stalls reap the backend at every bootstrap RPC', { timeout: 12000 }, async t => {
  const { XsmHost } = await import('../typescript/xsm-host.mjs');
  for (const setupTimeout of [null, false, 0, -1, Infinity, NaN, '1', 2147483648]) {
    await assert.rejects(XsmHost.open({ runtime: 'fixture', profile: 'p', conversation: 'c', cwd: '.',
      command: ['must-not-spawn'], setupTimeout }), /setupTimeout/);
  }
  const original = XsmHostClient.connect.bind(XsmHostClient), clients = [];
  t.mock.method(XsmHostClient, 'connect', async (...args) => {
    const client = await original(...args); clients.push(client); return client;
  });
  for (const method of ['session.open', 'operations/list', 'events.subscribe', 'combined-budget']) {
    try {
      await assert.rejects(XsmHost.open({ runtime: 'fixture', profile: 'p', conversation: 'c', cwd: '.',
        command: [process.env.PYTHON ?? 'python3', '-u', fileURLToPath(new URL('./echo_peer.py', import.meta.url)),
          method === 'combined-budget' ? 'host-slow-setup' : 'host-stall-' + method],
        setupTimeout: method === 'combined-budget' ? 120 : 50, closeTimeout: 50, deliver: async () => {} }), /host setup timed out/);
      const child = clients.at(-1).process;
      assert.ok(child.exitCode !== null || child.signalCode !== null);
    } finally { await Promise.all(clients.map(client => client.close())); }
  }
});
