/** Controlled native admission seam; the native SQLite/prompt consumer is probed separately. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { nativeDelivery } from '../../integrations/openclaw/context-queue.mjs';

function fixture() {
  let row = { sessionId: 'a', lifecycleRevision: 'generation-a', pluginNextTurnInjections: {
    other: [{ id: 'foreign', text: 'keep' }],
  } };
  let config = {}, beforeCommit = () => {}, current = true;
  const session = {
    resolveStorePath: store => store ?? '/isolated/native/sessions.json',
    getSessionEntry: () => structuredClone(row),
    runWithWorkAdmission: async ({ signal }, run) => run(signal),
    patchSessionEntry: async ({ update, assertCommitAllowed }) => {
      const patch = await update(structuredClone(row));
      beforeCommit(patch);
      assertCommitAllowed();
      if (patch) row = { ...row, ...patch };
      return structuredClone(row);
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
    beforeCommit: callback => { beforeCommit = callback; }, retire: () => { current = false; } };
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
  await assert.rejects(large.deliver({ ...large.packet, messages: ['x'.repeat(32768)] }, large.controls), /queue limit/);
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
