import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { XsmHost, parseHostCommand } from '../typescript/xsm-host.mjs';
import { XsmClient } from '../typescript/xsm-client.mjs';

const root = fileURLToPath(new URL('../../', import.meta.url));

test('native command arguments preserve JSON string whitespace and Unicode', () => {
  const args = { text: 'two  spaces\n다음 줄\tend' };
  assert.deepEqual(parseHostCommand('xsm_send ' + JSON.stringify(args)), { operation: 'xsm_send', arguments: args });
  assert.deepEqual(parseHostCommand(''), { operation: 'status', arguments: {} });
  assert.throws(() => parseHostCommand('xsm_send []'));
  assert.throws(() => parseHostCommand('xsm_send {broken'));
});
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

async function fixture(t, callbacks = {}) {
  const temp = await mkdtemp(join(tmpdir(), 'xsm-host-binding-'));
  const env = { PATH: process.env.PATH ?? '/usr/bin:/bin', HOME: temp,
    XSM_HOME: join(temp, 'state'), PYTHONPATH: root, PYTHONDONTWRITEBYTECODE: '1' };
  const command = [process.env.PYTHON ?? 'python3', '-B', '-m', 'xsm', 'protocol', 'serve', '--stdio'];
  const errors = [];
  const host = await XsmHost.open({ command, env, cwd: root, runtime: 'host-fixture',
    profile: 'isolated', conversation: 'a', deliver: async () => {},
    onError: error => errors.push(error), ...callbacks });
  t.after(async () => { await host.close(); await rm(temp, { recursive: true, force: true }); });
  return { host, errors, command, env };
}

test('binding presents a native callback once and retries original operation', { timeout: 10000 }, async t => {
  const displayed = [];
  const { host, errors } = await fixture(t, { present: async event => {
    displayed.push(event.params.question);
    return { displayed: event.params.question, sourceId: event.params.questionId, answer: 'blue' };
  } });
  const args = { question: 'Choose a color', options: ['blue', 'green'] };
  const result = await host.call('xsm_decide', args);
  assert.match(JSON.stringify(result), /your user answered: blue/);
  assert.deepEqual(displayed, ['Choose a color']);
  assert.deepEqual(errors, []);
});

test('one cancelled waiter does not cancel another waiter or forge denial', { timeout: 10000 }, async t => {
  const shown = deferred(), answer = deferred();
  const { host, errors } = await fixture(t, { present: async event => {
    shown.resolve(event);
    await answer.promise;
    return { displayed: event.params.question, sourceId: event.params.questionId, answer: 'blue' };
  } });
  const controller = new AbortController();
  const args = { question: 'Choose a color', options: ['blue', 'green'] };
  const first = host.call('xsm_decide', args, { signal: controller.signal });
  const firstRejected = assert.rejects(first, error => error.name === 'AbortError');
  const event = await shown.promise;
  const second = host.call('xsm_decide', args);
  // Register the second wait through the actual server response before cancelling the first.
  while (host.questions.get(event.params.questionId).waiters.size !== 2) {
    await new Promise(resolve => setImmediate(resolve));
  }
  controller.abort();
  await firstRejected;
  answer.resolve();
  assert.match(JSON.stringify(await second), /your user answered: blue/);
  assert.deepEqual(errors, []);
});

test('all cancelled waiters abandon the display and a deliberate retry gets a fresh question', { timeout: 10000 }, async t => {
  const shown = deferred();
  let number = 0;
  const { host, errors } = await fixture(t, { present: async (event, { signal }) => {
    number += 1;
    if (number === 1) {
      shown.resolve(event);
      await new Promise(resolve => signal.addEventListener('abort', resolve, { once: true }));
    }
    return { displayed: event.params.question, sourceId: event.params.questionId, answer: 'blue' };
  } });
  const controller = new AbortController();
  const args = { question: 'Choose a color', options: ['blue', 'green'] };
  const first = host.call('xsm_decide', args, { signal: controller.signal });
  const rejected = assert.rejects(first, error => error.name === 'AbortError');
  const event = await shown.promise;
  controller.abort();
  await rejected;
  // Order behind the abandon request on the same connection, without wall-clock sleeps.
  await host.client.request('operations/list');
  const status = await host.client.operationCall(host.session.session, 'xsm_decision_status', { id: event.params.decisionId });
  assert.equal(status.status, 'pending');
  assert.equal(status.answer, null);
  const result = await host.call('xsm_decide', args);
  assert.match(JSON.stringify(result), /your user answered: blue/);
  assert.equal(number, 2);
  assert.deepEqual(errors, []);
});

test('cancellation between request and waiter registration never opens an orphan dialog', { timeout: 10000 }, async t => {
  const abandoned = deferred();
  let presented = 0;
  const { host, errors } = await fixture(t, { present: async event => {
    presented += 1;
    return { displayed: event.params.question, sourceId: event.params.questionId, answer: 'blue' };
  } });
  const controller = new AbortController();
  const operationCall = host.client.operationCall.bind(host.client);
  host.client.operationCall = async (...args) => {
    const result = await operationCall(...args);
    if (result?.status === 'waiting-for-user') controller.abort();
    return result;
  };
  const abandon = host.client.abandonDecision.bind(host.client);
  host.client.abandonDecision = async event => {
    const result = await abandon(event);
    abandoned.resolve(result);
    return result;
  };
  await assert.rejects(host.call('xsm_decide', { question: 'Choose', options: ['blue', 'green'] },
    { signal: controller.signal }), error => error.name === 'AbortError');
  assert.equal((await abandoned.promise).status, 'pending');
  assert.equal(presented, 0);
  assert.deepEqual(errors, []);
});

test('native admission failure releases originals for a later natural boundary', { timeout: 10000 }, async t => {
  const failed = deferred();
  let fail = true;
  const delivered = [];
  const { host, command, env } = await fixture(t, { deliver: async (pack, options) => {
    if (fail) { failed.resolve(); throw new Error('native queue refused'); }
    delivered.push({ pack, wake: options.wake });
  } });
  const sender = await XsmClient.connect({ command, env, cwd: root });
  t.after(() => sender.close());
  const origin = await sender.sessionOpen({ runtime: 'sender-fixture', profile: 'isolated',
    conversation: 'b', cwd: root });
  await sender.operationCall(origin.session, 'xsm_send', {
    target: 'ref:' + host.session.ref, text: 'Retain this work', wait: 0,
  });
  await failed.promise;
  await host.deliveryTask;
  fail = false;
  const pack = await host.naturalBoundary();
  assert.equal(pack.claims.length, 1);
  assert.match(JSON.stringify(pack.messages), /Retain this work/);
  assert.equal(delivered[0].wake, false);
  const ack = await host.call('xsm_ack', { tokens: pack.claims.map(c => c.token) });
  assert.equal(ack.acked.length, 1);
});

test('transport death rejects a pending host question without accepting its late callback', { timeout: 10000 }, async t => {
  const shown = deferred(), uiCancelled = deferred();
  const { host } = await fixture(t, { present: async (event, { signal }) => {
    shown.resolve();
    await new Promise(resolve => signal.addEventListener('abort', resolve, { once: true }));
    uiCancelled.resolve();
    return { displayed: event.params.question, sourceId: event.params.questionId, answer: 'blue' };
  } });
  const operation = host.call('xsm_decide', { question: 'Choose', options: ['blue', 'green'] });
  const rejected = assert.rejects(operation, error => error.name === 'TransportError');
  await shown.promise;
  host.client.process.kill('SIGKILL');
  await rejected;
  await uiCancelled.promise;
  assert.equal(host.client.process.exitCode, null); // terminated by a signal, not a normal result
});
