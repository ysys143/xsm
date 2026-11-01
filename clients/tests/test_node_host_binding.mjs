import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { XsmHost, RetryAdmission, parseHostCommand, inboxAcknowledgement, renderInboxPacket } from '../typescript/xsm-host.mjs';
import { XsmClient } from '../typescript/xsm-client.mjs';

const root = fileURLToPath(new URL('../../', import.meta.url));

test('shared native notice rendering keeps claim-free content without inventing ACK tokens', () => {
  assert.equal(inboxAcknowledgement([]), '');
  assert.equal(renderInboxPacket({ messages: ['first notice', 'second notice'], claims: [] }), 'first notice\n\nsecond notice');
});

test('shared native original rendering retains the exact ACK tokens and recovery hint', () => {
  const result = renderInboxPacket({ messages: ['original'], claims: [{ id: 'a', token: 'opaque-a' }] });
  assert.match(result, /^original\n\nAfter reading, call xsm_ack with tokens: \["opaque-a"\]/);
  assert.match(result, /read xsm_inbox for current tokens with message_ids: \["a"\]/);
});

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

test('pull-only binding preserves explicit inbox claims without advertising delivery', { timeout: 10000 }, async t => {
  const { host, command, env, errors } = await fixture(t, { deliver: undefined });
  assert.equal(host.session.capabilities.includes('events'), false);
  await assert.rejects(host.naturalBoundary(), /not connected/);
  const sender = await XsmClient.connect({ command, env, cwd: root });
  t.after(() => sender.close());
  const origin = await sender.sessionOpen({ runtime: 'sender-fixture', profile: 'isolated',
    conversation: 'b', cwd: root });
  await sender.operationCall(origin.session, 'xsm_send', {
    target: 'ref:' + host.session.ref, text: 'Pull this original', wait: 0,
  });
  const pack = await host.call('xsm_inbox');
  assert.equal(pack.claims.length, 1);
  assert.match(JSON.stringify(pack.messages), /Pull this original/);
  const ack = await host.call('xsm_ack', { tokens: pack.claims.map(c => c.token) });
  assert.equal(ack.acked.length, 1);
  assert.deepEqual(errors, []);
});

test('one coalesced wake drains bounded batches without acknowledging originals', { timeout: 10000 }, async t => {
  const delivered = [];
  const { host, command, env } = await fixture(t, { inboxBatchSize: 2,
    deliver: async packet => { delivered.push(packet); } });
  const sender = await XsmClient.connect({ command, env, cwd: root });
  t.after(() => sender.close());
  const origin = await sender.sessionOpen({ runtime: 'batch-sender', profile: 'one', conversation: 'a', cwd: root });
  for (let index = 0; index < 5; index++) await sender.operationCall(origin.session, 'xsm_send', {
    target: 'ref:' + host.session.ref, text: 'bounded-' + index, wake: 'never', wait: 0,
  });
  assert.equal(delivered.length, 0);
  host.pendingWake = true; // One availability tick, without another server notification.
  await host.deliverLoop();
  assert.deepEqual(delivered.map(packet => packet.messages.length), [2, 2, 1]);
  const claims = delivered.flatMap(packet => packet.claims);
  assert.equal(new Set(claims.map(claim => claim.id)).size, 5);
  assert.equal((await host.call('xsm_ack', { tokens: claims.map(claim => claim.token) })).acked.length, 5);
});

test('a byte-limited batch keeps draining even below the message count limit', { timeout: 10000 }, async t => {
  const packets = [];
  const { host, command, env } = await fixture(t, { inboxBatchSize: 16, inboxMaxBytes: 5000,
    deliver: async packet => { packets.push(packet); } });
  const sender = await XsmClient.connect({ command, env, cwd: root });
  t.after(() => sender.close());
  const origin = await sender.sessionOpen({ runtime: 'byte-sender', profile: 'one', conversation: 'a', cwd: root });
  for (let index = 0; index < 3; index++) await sender.operationCall(origin.session, 'xsm_send', {
    target: 'ref:' + host.session.ref, text: 'byte-' + index + 'x'.repeat(3000), wake: 'never', wait: 0,
  });
  host.pendingWake = true;
  await host.deliverLoop();
  assert.deepEqual(packets.map(packet => packet.claims.length), [1, 1, 1]);
  assert.ok(packets.every(packet => packet.rendered_bytes <= 5000));
  assert.equal((await host.call('xsm_ack', { tokens: packets.flatMap(packet => packet.claims.map(claim => claim.token)) })).acked.length, 3);
});

test('notice-only cursor progress reaches a later original in one bounded drain', { timeout: 10000 }, async t => {
  const code = "import runpy;from xsm import receive;check=receive.check;receive.check=lambda p,m:('block','P2P admission temporarily unavailable: fixture') if p.body.startswith('defer-') else check(p,m);runpy.run_module('xsm',run_name='__main__')";
  const packets = [];
  const { host, command, env } = await fixture(t, { inboxBatchSize: 2, inboxMaxBytes: 10000,
    command: [process.env.PYTHON ?? 'python3', '-B', '-c', code, 'protocol', 'serve', '--stdio'],
    deliver: async packet => { packets.push(packet); } });
  const sender = await XsmClient.connect({ command, env, cwd: root });
  t.after(() => sender.close());
  const origin = await sender.sessionOpen({ runtime: 'cursor-sender', profile: 'one', conversation: 'a', cwd: root });
  for (const text of ['defer-one', 'defer-two', 'allowed-last']) await sender.operationCall(origin.session, 'xsm_send', {
    target: 'ref:' + host.session.ref, text, wake: 'never', wait: 0,
  });
  host.pendingWake = true;
  await host.deliverLoop();
  assert.deepEqual(packets.map(packet => packet.claims.length), [0, 1]);
  assert.match(JSON.stringify(packets[1].messages), /allowed-last/);
  assert.equal((await host.call('xsm_ack', { tokens: packets[1].claims.map(claim => claim.token) })).acked.length, 1);
});

test('a full notice-only batch does not spin without acquiring any original', async t => {
  const { host, errors } = await fixture(t, { inboxBatchSize: 2 });
  let reads = 0;
  host.client.operationCall = async () => {
    if (++reads > 2) throw new Error('notice-only batch repeated');
    return { messages: ['deferred first', 'deferred second'], claims: [] };
  };
  host.pendingWake = true;
  await host.deliverLoop();
  assert.equal(reads, 1);
  assert.deepEqual(errors, []);
});

test('retryable native backpressure releases then reacquires the same original without another wake', { timeout: 10000 }, async t => {
  const attempted = deferred(), admitted = deferred(), packets = [];
  const { host, command, env, errors } = await fixture(t, { deliver: async packet => {
    packets.push(packet);
    if (packets.length === 1) { attempted.resolve(); throw new RetryAdmission('queue full', 50); }
    admitted.resolve();
  } });
  const sender = await XsmClient.connect({ command, env, cwd: root });
  t.after(() => sender.close());
  const origin = await sender.sessionOpen({ runtime: 'retry-sender', profile: 'one', conversation: 'a', cwd: root });
  await sender.operationCall(origin.session, 'xsm_send', { target: 'ref:' + host.session.ref, text: 'retry original', wait: 0 });
  await attempted.promise;
  assert.ok((await host.client.request('operations/list')).operations.length);
  await admitted.promise;
  await host.deliveryTask;
  assert.equal(packets.length, 2);
  assert.equal(packets[0].claims[0].id, packets[1].claims[0].id);
  assert.notEqual(packets[0].claims[0].token, packets[1].claims[0].token);
  assert.equal((await host.call('xsm_ack', { tokens: [packets[1].claims[0].token] })).acked.length, 1);
  assert.deepEqual(errors, []);
});

test('closing during native backpressure cancels the retry timer and prevents a later admission', { timeout: 10000 }, async t => {
  const attempted = deferred();
  let attempts = 0;
  const { host, command, env, errors } = await fixture(t, { deliver: async () => {
    attempts++; attempted.resolve(); throw new RetryAdmission('queue full', 5000);
  } });
  const sender = await XsmClient.connect({ command, env, cwd: root });
  t.after(() => sender.close());
  const origin = await sender.sessionOpen({ runtime: 'retry-sender', profile: 'one', conversation: 'a', cwd: root });
  await sender.operationCall(origin.session, 'xsm_send', { target: 'ref:' + host.session.ref, text: 'retain on close', wait: 0 });
  await attempted.promise;
  await host.close();
  assert.equal(attempts, 1);
  assert.equal(host.deliveryTask, undefined);
  assert.deepEqual(errors, []);
});

test('a stale normal wake does not wake passive originals found after retry', { timeout: 10000 }, async t => {
  const retryRead = deferred(), release = deferred(), admitted = deferred();
  const packets = [];
  const { host, command, env } = await fixture(t, { deliver: async (packet, options) => {
    packets.push({ packet, wake: options.wake });
    if (packets.length === 1) throw new RetryAdmission('queue full', 1);
    admitted.resolve();
  } });
  const call = host.client.operationCall.bind(host.client);
  let reads = 0;
  host.client.operationCall = async (session, name, args) => {
    if (name === 'xsm_inbox' && args.limit === undefined && ++reads === 2) {
      retryRead.resolve(); await release.promise;
    }
    return call(session, name, args);
  };
  const sender = await XsmClient.connect({ command, env, cwd: root });
  t.after(() => sender.close());
  const origin = await sender.sessionOpen({ runtime: 'retry-sender', profile: 'one', conversation: 'a', cwd: root });
  await sender.operationCall(origin.session, 'xsm_send', { target: 'ref:' + host.session.ref, text: 'taken directly', wait: 0 });
  await retryRead.promise;
  const direct = await host.call('xsm_inbox', { limit: 1 });
  assert.match(JSON.stringify(direct.messages), /taken directly/);
  await host.call('xsm_ack', { tokens: direct.claims.map(claim => claim.token) });
  await sender.operationCall(origin.session, 'xsm_send', { target: 'ref:' + host.session.ref, text: 'quiet original', wake: 'never', wait: 0 });
  release.resolve();
  await admitted.promise;
  await host.deliveryTask;
  assert.equal(packets.length, 2);
  assert.equal(packets[1].wake, false);
  assert.match(JSON.stringify(packets[1].packet.messages), /quiet original/);
});

test('a deferred FYI boundary retries in the background without waking a turn', { timeout: 10000 }, async t => {
  const admitted = deferred(), packets = [];
  const { host, command, env, errors } = await fixture(t, { deliver: async (packet, options) => {
    packets.push({ packet, wake: options.wake });
    if (packets.length === 1) throw new RetryAdmission('queue full', 10);
    admitted.resolve();
  } });
  const sender = await XsmClient.connect({ command, env, cwd: root });
  t.after(() => sender.close());
  const origin = await sender.sessionOpen({ runtime: 'boundary-sender', profile: 'one', conversation: 'a', cwd: root });
  await sender.operationCall(origin.session, 'xsm_send', { target: 'ref:' + host.session.ref,
    text: 'deferred quiet original', wake: 'never', wait: 0 });
  await assert.rejects(host.naturalBoundary(), error => error instanceof RetryAdmission);
  await admitted.promise;
  await host.deliveryTask;
  assert.deepEqual(packets.map(item => item.wake), [false, false]);
  assert.equal(packets[0].packet.claims[0].id, packets[1].packet.claims[0].id);
  assert.notEqual(packets[0].packet.claims[0].token, packets[1].packet.claims[0].token);
  assert.equal((await host.call('xsm_ack', { tokens: [packets[1].packet.claims[0].token] })).acked.length, 1);
  assert.deepEqual(errors, []);
});

test('closing a deferred boundary cancels its initial retry delay', { timeout: 10000 }, async t => {
  let attempts = 0;
  const { host, command, env, errors } = await fixture(t, { deliver: async () => {
    attempts++; throw new RetryAdmission('queue full', 5000);
  } });
  const sender = await XsmClient.connect({ command, env, cwd: root });
  t.after(() => sender.close());
  const origin = await sender.sessionOpen({ runtime: 'boundary-sender', profile: 'one', conversation: 'a', cwd: root });
  await sender.operationCall(origin.session, 'xsm_send', { target: 'ref:' + host.session.ref,
    text: 'retain quiet original', wake: 'never', wait: 0 });
  await assert.rejects(host.naturalBoundary(), error => error instanceof RetryAdmission);
  await host.close();
  assert.equal(attempts, 1);
  assert.equal(host.deliveryTask, undefined);
  assert.deepEqual(errors, []);
});

test('missing wake metadata cannot turn a boundary retry into an active wake', { timeout: 10000 }, async t => {
  const wakes = [];
  const { host, command, env } = await fixture(t, { deliver: async (_packet, options) => { wakes.push(options.wake); } });
  const call = host.client.operationCall.bind(host.client);
  host.client.operationCall = async (...args) => {
    const result = await call(...args);
    if (args[1] === 'xsm_inbox') delete result.items;
    return result;
  };
  const sender = await XsmClient.connect({ command, env, cwd: root });
  t.after(() => sender.close());
  const origin = await sender.sessionOpen({ runtime: 'boundary-sender', profile: 'one', conversation: 'a', cwd: root });
  await sender.operationCall(origin.session, 'xsm_send', { target: 'ref:' + host.session.ref,
    text: 'unknown wake metadata', wake: 'never', wait: 0 });
  await host.deliverInbox(true);
  assert.deepEqual(wakes, [false]);
});

test('explicit false native admission releases claims without recording admission', { timeout: 10000 }, async t => {
  const { host, command, env } = await fixture(t, { deliver: async () => false });
  const sender = await XsmClient.connect({ command, env, cwd: root });
  t.after(() => sender.close());
  const origin = await sender.sessionOpen({ runtime: 'sender-fixture', profile: 'isolated',
    conversation: 'b', cwd: root });
  const reports = [];
  const original = host.client.deliveryReport.bind(host.client);
  host.client.deliveryReport = (...args) => { reports.push(args); return original(...args); };
  // FYI reaches only the explicit boundary, avoiding timing assumptions about the pump.
  await sender.operationCall(origin.session, 'xsm_send', {
    target: 'ref:' + host.session.ref, text: 'Rejected original', wake: 'never', wait: 0,
  });
  await assert.rejects(host.naturalBoundary(), /refused/);
  assert.deepEqual(reports, []);
  const pack = await host.call('xsm_inbox');
  assert.equal(pack.claims.length, 1);
  assert.match(JSON.stringify(pack.messages), /Rejected original/);
});

test('pull-only binding presents a native callback once and retries original operation', { timeout: 10000 }, async t => {
  const displayed = [];
  const { host, errors } = await fixture(t, { deliver: undefined, present: async event => {
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

test('a pending decision RPC is registered before another caller abandons the display', { timeout: 10000 }, async t => {
  const shown = deferred(), reply = deferred(), pending = deferred(), release = deferred();
  let uiSignal;
  const { host } = await fixture(t, { present: async (event, { signal }) => {
    uiSignal = signal; shown.resolve(); await reply.promise;
    return { displayed: event.params.question, sourceId: event.params.questionId, answer: 'blue' };
  } });
  const original = host.client.operationCall.bind(host.client);
  let requests = 0;
  host.client.operationCall = async (...args) => {
    const number = ++requests;
    const result = await original(...args);
    if (number === 2) { pending.resolve(); await release.promise; }
    return result;
  };
  const args = { question: 'Choose', options: ['blue', 'green'] };
  const controller = new AbortController();
  const first = host.call('xsm_decide', args, { signal: controller.signal });
  const rejected = assert.rejects(first, error => error.name === 'AbortError');
  await shown.promise;
  const second = host.call('xsm_decide', args);
  try {
    await pending.promise;
    controller.abort();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(uiSignal.aborted, false, 'pending RPC caller must keep its display');
    release.resolve();
    await rejected;
    reply.resolve();
    assert.match(JSON.stringify(await second), /your user answered: blue/);
  } finally {
    release.resolve(); reply.resolve();
    await host.close();
    await Promise.allSettled([first, second, rejected]);
  }
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
