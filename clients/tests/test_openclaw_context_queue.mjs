/** Controlled native admission seam; the native SQLite/prompt consumer is probed separately. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { nativeDelivery } from '../../integrations/openclaw/context-queue.mjs';

function fixture() {
  let row = { sessionId: 'a', lifecycleRevision: 'generation-a', pluginNextTurnInjections: {
    other: [{ id: 'foreign', text: 'keep' }],
  } };
  let config = {}, beforeCommit = () => {}, afterCommit = () => {}, current = true;
  const session = {
    resolveStorePath: store => store ?? '/isolated/native/sessions.json',
    getSessionEntry: () => structuredClone(row),
    runWithWorkAdmission: async ({ signal }, run) => run(signal),
    patchSessionEntry: async ({ update, assertCommitAllowed }) => {
      const patch = await update(structuredClone(row));
      beforeCommit(patch);
      assertCommitAllowed();
      if (patch) row = { ...row, ...patch };
      const committed = structuredClone(row);
      afterCommit();
      return committed;
    },
  };
  const api = { runtime: { agent: { session }, config: { current: () => config } }, lifecycle: {} };
  const context = { agentId: 'main', sessionKey: 'agent:main:test', sessionId: 'a' };
  const deliver = nativeDelivery(api, context, () => {
    if (!current) throw new Error('binding retired');
  });
  const packet = { messages: ['exact original'], claims: [{ id: 'message-a', token: 'claim-a' }] };
  const controls = { signal: new AbortController().signal, leaseSeconds: 120 };
  return { api, context, deliver, packet, controls, read: () => structuredClone(row),
    edit: change => { row = { ...row, ...change }; }, config: value => { config = value; },
    beforeCommit: callback => { beforeCommit = callback; }, afterCommit: callback => { afterCommit = callback; }, retire: () => { current = false; } };
}

test('native context is observed after admission, preserves other plugins and deduplicates originals', async () => {
  const f = fixture();
  await f.deliver(f.packet, f.controls);
  await f.deliver({ ...f.packet, claims: [{ id: 'message-a', token: 'retry-token' }] }, f.controls);
  const all = f.read().pluginNextTurnInjections;
  assert.equal(all.xsm.length, 1);
  assert.deepEqual(all.other, [{ id: 'foreign', text: 'keep' }]);
  assert.match(all.xsm[0].text, /exact original/);
  assert.match(all.xsm[0].text, /claim-a/);
  assert.equal(all.xsm[0].metadata.nativeSessionId, 'a');
  assert.equal(all.xsm[0].ttlMs, 120000);
});

test('wake callback follows committed context and FYI never invokes it', async () => {
  const f = fixture(), calls = [];
  const deliver = nativeDelivery(f.api, f.context, () => {}, value => {
    assert.match(f.read().pluginNextTurnInjections.xsm[0].text, /exact original/);
    calls.push(value);
  });
  await deliver(f.packet, { ...f.controls, wake: false });
  assert.equal(calls.length, 0);
  await deliver(f.packet, { ...f.controls, wake: true });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].revision, 'generation-a');
  assert.equal(calls[0].context.sessionId, 'a');
});

test('final native guard rejects a replaced conversation after update preparation', async () => {
  const f = fixture();
  f.beforeCommit(() => f.edit({ sessionId: 'replacement' }));
  await assert.rejects(f.deliver(f.packet, f.controls), /conversation changed/);
  assert.equal(f.read().pluginNextTurnInjections.xsm, undefined);
});

test('revision changes, retirement and policy changes cannot admit old native context', async () => {
  for (const mutation of [f => f.edit({ lifecycleRevision: 'new' }), f => f.retire(),
    f => f.config({ plugins: { entries: { xsm: { hooks: { allowPromptInjection: false } } } } }),
    f => f.config({ session: { store: '/different-store' } })]) {
    const f = fixture();
    f.beforeCommit(() => mutation(f));
    await assert.rejects(f.deliver(f.packet, f.controls), /changed|retired/);
    assert.equal(f.read().pluginNextTurnInjections.xsm, undefined);
  }
});

test('queue capacity, oversized context and cancellation retain unadmitted originals', async () => {
  const full = fixture();
  full.edit({ pluginNextTurnInjections: { xsm: Array.from({ length: 32 }, (_, i) => ({ id: String(i) })) } });
  await assert.rejects(full.deliver(full.packet, full.controls), /queue is full/);
  assert.equal(full.read().pluginNextTurnInjections.xsm.length, 32);
  const large = fixture();
  await assert.rejects(large.deliver({ ...large.packet, messages: ['x'.repeat(32768 * 32)] }, large.controls), /batch capacity/);
  assert.equal(large.read().pluginNextTurnInjections.xsm, undefined);
  const cancelled = fixture(), controller = new AbortController();
  cancelled.beforeCommit(() => controller.abort());
  await assert.rejects(cancelled.deliver(cancelled.packet, { ...cancelled.controls, signal: controller.signal }), /cancelled/);
  assert.equal(cancelled.read().pluginNextTurnInjections.xsm, undefined);
});

test('missing native owner or disabled injection keeps the binding pull-only', () => {
  const f = fixture();
  assert.equal(nativeDelivery(f.api, { ...f.context, agentId: undefined }, () => {}), undefined);
  f.config({ plugins: { entries: { xsm: { hooks: { allowPromptInjection: false } } } } });
  assert.equal(nativeDelivery(f.api, f.context, () => {}), undefined);
});

test('a registration policy denial cannot be widened by a sparse runtime config', () => {
  const f = fixture();
  f.api.config = { plugins: { entries: { xsm: { hooks: { allowPromptInjection: false } } } } };
  assert.equal(nativeDelivery(f.api, f.context, () => {}), undefined);
});

test('a claim-free native notice does not ask the agent to ACK an empty token array', async () => {
  const f = fixture(), notice = 'Original retained pending network revalidation.';
  await f.deliver({ messages: [notice], claims: [] }, f.controls);
  assert.equal(f.read().pluginNextTurnInjections.xsm[0].text, notice);
});

test('fragmented claim-free notices have no acknowledgement fragment', async () => {
  const f = fixture(), notice = 'notice '.repeat(10000);
  await f.deliver({ messages: [notice], claims: [] }, f.controls);
  const group = f.read().pluginNextTurnInjections.xsm;
  assert.equal(recoverBody(group), notice);
  assert.ok(group.every(item => item.metadata.fragmentBodyLength > 0));
  assert.ok(group.every(item => !item.text.includes('After reading, call xsm_ack')));
});

test('an unobserved native write never reports successful admission', async () => {
  const f = fixture();
  f.api.runtime.agent.session.patchSessionEntry = async () => f.read();
  await assert.rejects(f.deliver(f.packet, f.controls), /was not observed/);
  assert.equal(f.read().pluginNextTurnInjections.xsm, undefined);
});

test('queue identity alone does not prove that the actual original text was admitted', async () => {
  const f = fixture();
  f.beforeCommit(patch => { patch.pluginNextTurnInjections.xsm[0].text = 'wrong native context'; });
  await assert.rejects(f.deliver(f.packet, f.controls), /was not observed/);
});

const recoverBody = items => items.map(item => item.text.slice(item.metadata.fragmentHeaderLength,
  item.metadata.fragmentHeaderLength + item.metadata.fragmentBodyLength)).join('');

test('large Unicode context survives native trim boundaries and ACK appears only after every fragment', async () => {
  const f = fixture();
  const body = ' \t\n' + '한글🚀 '.repeat(16000) + '\n\t ';
  await f.deliver({ ...f.packet, messages: [body] }, f.controls);
  const group = f.read().pluginNextTurnInjections.xsm;
  assert.ok(group.length > 1);
  assert.equal(recoverBody(group), body);
  for (const [index, item] of group.entries()) {
    assert.ok(item.text.length <= 32768);
    assert.equal(item.text.trim(), item.text, 'native prompt preparation must not trim body whitespace');
    assert.equal(item.metadata.fragmentIndex, index);
    assert.equal(item.metadata.fragmentCount, group.length);
    const piece = item.text.slice(item.metadata.fragmentHeaderLength,
      item.metadata.fragmentHeaderLength + item.metadata.fragmentBodyLength);
    assert.ok(!(piece.charCodeAt(0) >= 0xdc00 && piece.charCodeAt(0) <= 0xdfff));
    assert.ok(!(piece.charCodeAt(piece.length - 1) >= 0xd800 && piece.charCodeAt(piece.length - 1) <= 0xdbff));
    assert.equal(item.text.includes('After reading, call xsm_ack'), index === group.length - 1);
  }
});

test('a surrogate pair that straddles the observed native fragment boundary stays together', async () => {
  const baseline = fixture();
  await baseline.deliver({ ...baseline.packet, messages: ['x'.repeat(40000)] }, baseline.controls);
  const capacity = baseline.read().pluginNextTurnInjections.xsm[0].metadata.fragmentBodyLength;
  const f = fixture(), body = 'x'.repeat(capacity - 1) + '🚀' + 'x'.repeat(capacity * 2);
  await f.deliver({ ...f.packet, messages: [body] }, f.controls);
  const group = f.read().pluginNextTurnInjections.xsm;
  const first = group[0].text.slice(group[0].metadata.fragmentHeaderLength,
    group[0].metadata.fragmentHeaderLength + group[0].metadata.fragmentBodyLength);
  assert.ok(!(first.charCodeAt(first.length - 1) >= 0xd800 && first.charCodeAt(first.length - 1) <= 0xdbff));
  assert.equal(recoverBody(group), body);
});

test('fragmented context reserves the entire batch before publishing any part', async () => {
  const f = fixture();
  const retained = Array.from({ length: 31 }, (_, index) => ({ id: String(index) }));
  f.edit({ pluginNextTurnInjections: { xsm: retained } });
  await assert.rejects(f.deliver({ ...f.packet, messages: ['x'.repeat(40000)] }, f.controls), /queue is full/);
  assert.deepEqual(f.read().pluginNextTurnInjections.xsm, retained);
});

test('fragment retry deduplicates rotated tokens and refuses an incomplete prior group', async () => {
  const f = fixture(), packet = { ...f.packet, messages: ['x'.repeat(70000)] };
  await f.deliver(packet, f.controls);
  const group = f.read().pluginNextTurnInjections.xsm;
  await f.deliver({ ...packet, claims: [{ id: 'message-a', token: 'rotated-longer-token' }] }, f.controls);
  assert.deepEqual(f.read().pluginNextTurnInjections.xsm, group);
  f.edit({ pluginNextTurnInjections: { xsm: group.slice(1) } });
  await assert.rejects(f.deliver(packet, f.controls), /incomplete fragment group/);
  assert.deepEqual(f.read().pluginNextTurnInjections.xsm, group.slice(1));
});

test('missing observed fragment cannot report that the whole original was admitted', async () => {
  const f = fixture();
  f.beforeCommit(patch => { patch.pluginNextTurnInjections.xsm.pop(); });
  await assert.rejects(f.deliver({ ...f.packet, messages: ['x'.repeat(40000)] }, f.controls), /was not observed/);
});

test('a complete pending single context stays reusable when rotated tokens require a larger encoding', async () => {
  const f = fixture(), packet = { ...f.packet, messages: ['x'.repeat(32000)] };
  await f.deliver(packet, f.controls);
  const group = f.read().pluginNextTurnInjections.xsm;
  assert.equal(group.length, 1);
  await f.deliver({ ...packet, claims: [{ id: 'message-a', token: 'x'.repeat(2000) }] }, f.controls);
  assert.deepEqual(f.read().pluginNextTurnInjections.xsm, group);
});


test('native committed snapshot proves admission when consumer drains before readback', async () => {
  const f = fixture();
  f.afterCommit(() => f.edit({ pluginNextTurnInjections: { other: [{ id: 'foreign', text: 'keep' }] } }));
  await f.deliver({ ...f.packet, messages: ['x'.repeat(40000)] }, f.controls);
  assert.equal(f.read().pluginNextTurnInjections.xsm, undefined);
  assert.deepEqual(f.read().pluginNextTurnInjections.other, [{ id: 'foreign', text: 'keep' }]);
});

test('native commit snapshot from another conversation is refused', async () => {
  const f = fixture(), patch = f.api.runtime.agent.session.patchSessionEntry;
  f.api.runtime.agent.session.patchSessionEntry = async args => ({ ...await patch(args), sessionId: 'foreign' });
  await assert.rejects(f.deliver(f.packet, f.controls), /another conversation/);
});

test('missing native return falls back to exact observed current queue', async () => {
  const f = fixture(), patch = f.api.runtime.agent.session.patchSessionEntry;
  f.api.runtime.agent.session.patchSessionEntry = async args => { await patch(args); return null; };
  await f.deliver(f.packet, f.controls);
  assert.equal(f.read().pluginNextTurnInjections.xsm.length, 1);
});
