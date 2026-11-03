/** Controlled native API seam; actual registered-plugin execution is a separate probe. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
const source = new URL('../../integrations/openclaw/native-wake.mjs', import.meta.url);
let wakeModule;
if (process.env.XSM_OPENCLAW_WAKE_MUTANT === 'ignore-revision') {
  const code = await readFile(source, 'utf8');
  const changed = code.replace('current.lifecycleRevision !== revision', 'false');
  assert.notEqual(code, changed, 'revision guard moved; revise deliberate mutant');
  wakeModule = await import('data:text/javascript;base64,' + Buffer.from(changed).toString('base64'));
} else wakeModule = await import(source);
const { createNativeWake } = wakeModule;

function fixture() {
  let row = { sessionId: 'native', lifecycleRevision: 'rev' }, beforeLease = () => {};
  const calls = [], order = [], errors = [], root = new AbortController(), native = new AbortController(), transport = new AbortController();
  let enteredResolve, errorResolve, finish;
  const entered = new Promise(resolve => { enteredResolve = resolve; });
  const failed = new Promise(resolve => { errorResolve = resolve; });
  const done = new Promise(resolve => { finish = resolve; });
  const config = { plugins: { entries: { xsm: { config: { nativeWake: true }, hooks: { allowConversationAccess: true } } } } };
  const api = { config, lifecycle: { signal: root.signal, runInBackgroundContext: async run => {
    order.push('background'); return run();
  } }, runtime: { config: { current: () => config }, agent: {
    resolveAgentTimeoutMs: () => 10000,
    session: { getSessionEntry: () => row, runWithWorkAdmission: async ({ signal }, run) => {
      order.push('lease'); beforeLease();
      return run(AbortSignal.any([signal, native.signal]));
    } },
    runEmbeddedAgent: async params => {
      params.abortSignal.throwIfAborted();
      order.push('model'); calls.push(params); enteredResolve(params);
      await Promise.race([done, new Promise((_, reject) => params.abortSignal.addEventListener('abort',
        () => reject(new Error('cancelled')), { once: true }))]);
      return { meta: {} };
    },
  } } };
  const wake = createNativeWake(api, error => { errors.push(error); errorResolve(error); });
  const options = { runId: 'wake-original', context: { agentId: 'main', sessionId: 'native',
    sessionKey: 'agent:main:route', workspaceDir: '/isolated/work' },
    scope: { agentId: 'main', sessionKey: 'agent:main:route', storePath: '/isolated/store' },
    revision: 'rev', signal: transport.signal, guard: signal => signal?.throwIfAborted() };
  return { api, wake, options, calls, order, errors, root, native, transport, entered, failed, finish,
    beforeLease: callback => { beforeLease = callback; }, edit: patch => { row = { ...row, ...patch }; } };
}

test('wake runs under native background lease and preserves untrusted input and native model selection', async () => {
  const f = fixture(); f.wake.start(f.options); f.wake.start(f.options);
  const params = await f.entered;
  assert.deepEqual(f.order, ['background', 'lease', 'model']);
  assert.equal(f.calls.length, 1);
  assert.equal(params.sessionTarget.expectedLifecycleRevision, 'rev');
  assert.equal(params.provider, undefined); assert.equal(params.model, undefined);
  assert.equal(params.inputProvenance.kind, 'inter_session');
  assert.equal(params.initialTurnTainted, true);
  assert.equal(params.cliBackendDispatch, 'subscription-auth');
  assert.match(params.prompt, /untrusted/);
  f.finish(); await f.wake.close();
  assert.deepEqual(f.errors, []);
});

test('session selectors are forwarded without parsing aliases or guessing another provider', async () => {
  const f = fixture(); f.edit({ providerOverride: 'selected', modelOverride: 'configured-alias' });
  f.wake.start(f.options); const params = await f.entered;
  assert.equal(params.provider, 'selected'); assert.equal(params.model, 'configured-alias');
  f.finish(); await f.wake.close();
});

test('protocol transport loss cannot cancel an already submitted native turn', async () => {
  const f = fixture(); f.wake.start(f.options); const params = await f.entered;
  try {
    f.transport.abort();
    assert.equal(params.abortSignal.aborted, false, 'stdio loss cancelled native work');
  } finally { f.finish(); await f.wake.close(); }
});

test('revision and policy changes before native lease execution prevent model admission', async () => {
  for (const mutate of [f => f.edit({ lifecycleRevision: 'new' }),
    f => { f.api.config.plugins.entries.xsm.config.nativeWake = false; },
    f => { f.api.config.plugins.entries.xsm.hooks.allowConversationAccess = false; }]) {
    const f = fixture(); f.beforeLease(() => mutate(f)); f.wake.start(f.options);
    const result = await Promise.race([f.failed.then(error => ({ refused: true, error })),
      f.entered.then(() => ({ refused: false }))]);
    try {
      assert.equal(result.refused, true, 'changed target/policy reached native execution');
      assert.match(result.error.message, /original remains/);
      assert.equal(f.calls.length, 0);
    } finally { f.finish(); await f.wake.close(); }
  }
});

test('native reset and host disposal cancel actual submitted execution without logging native secrets', async () => {
  const f = fixture(); f.wake.start(f.options); const params = await f.entered;
  f.native.abort(); await new Promise(setImmediate);
  assert.deepEqual(f.errors, []); await f.wake.close();
  assert.equal(params.abortSignal.aborted, true); assert.deepEqual(f.errors, []);
  assert.throws(() => f.wake.start(f.options), /closed/);
  const other = fixture(); other.wake.start(other.options); const second = await other.entered;
  other.wake.cancelSession('native'); await other.wake.close();
  assert.equal(second.abortSignal.aborted, true); assert.deepEqual(other.errors, []);
  const failed = fixture(); failed.beforeLease(() => { throw new Error('synthetic-native-private-detail'); });
  failed.wake.start(failed.options);
  assert.doesNotMatch((await failed.failed).message, /synthetic-native-private-detail/);
  await failed.wake.close();
});
