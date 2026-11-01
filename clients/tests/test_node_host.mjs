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
