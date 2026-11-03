/** Controlled actual-boundary observer; native hook dispatch is probed separately. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
const source = new URL('../../integrations/openclaw/natural-context.mjs', import.meta.url);
let contextModule;
if (process.env.XSM_OPENCLAW_CONTEXT_MUTANT === 'ignore-content') {
  const code = await readFile(source, 'utf8');
  const changed = code.replace('!prompt.includes(state.text)', 'false');
  assert.notEqual(code, changed, 'prompt guard moved; revise deliberate mutant');
  const sdk = new URL('../../clients/typescript/xsm-host.mjs', import.meta.url).href;
  contextModule = await import('data:text/javascript;base64,' + Buffer.from(changed.replace(
    "'../../clients/typescript/xsm-host.mjs'", JSON.stringify(sdk))).toString('base64'));
} else contextModule = await import(source);
const { NaturalContext } = contextModule;

function fixture({ delayed = false, empty = false } = {}) {
  const stage = new NaturalContext();
  let admitted = 0, released = 0, release;
  const ready = new Promise(resolve => { release = resolve; });
  const packet = { messages: ['exact quiet original'], claims: [{ id: 'original', token: 'token' }] };
  const host = { async naturalBoundary() {
    if (empty) return { messages: [] };
    try {
      if (delayed) await ready;
      await stage.deliver('native', host, packet); admitted++;
    } catch (error) { released++; throw error; }
  } };
  return { stage, host, release, admitted: () => admitted, released: () => released };
}

test('passive native context waits for exact run/host/full prompt before admission', async () => {
  const f = fixture();
  const context = await f.stage.begin('native', f.host, 'run-a');
  assert.match(context.prependContext, /exact quiet original/);
  assert.equal(f.admitted(), 0);
  for (const [id, host, run, text] of [
    ['other', f.host, 'run-a', context.prependContext],
    ['native', {}, 'run-a', context.prependContext],
    ['native', f.host, 'run-b', context.prependContext],
    ['native', f.host, 'run-a', context.prependContext.slice(0, 30)]]) {
    assert.equal(await f.stage.observe(id, host, run, text), false);
  }
  assert.equal(await f.stage.observe('native', f.host, 'run-a', 'user input\n' + context.prependContext), true);
  assert.equal(f.admitted(), 1); assert.equal(f.released(), 0); assert.equal(f.stage.pending.size, 0);
});

test('ending an unobserved context releases it without admission', async () => {
  const f = fixture(); await f.stage.begin('native', f.host, 'run-a');
  await f.stage.cancel('native');
  assert.equal(f.admitted(), 0); assert.equal(f.released(), 1); assert.equal(f.stage.pending.size, 0);
});

test('late inbox response stays bound to its cancelled boundary', async () => {
  const f = fixture({ delayed: true });
  const beginning = f.stage.begin('native', f.host, 'run-a');
  // begin first crosses its cancellation await before registering the boundary.
  await new Promise(setImmediate);
  const rejected = assert.rejects(beginning, /closed/);
  const cancelling = f.stage.cancel('native'); f.release();
  await cancelling; await rejected;
  assert.equal(f.admitted(), 0); assert.equal(f.released(), 1);
});

test('empty native boundary and missing run identity manufacture no context', async () => {
  const f = fixture({ empty: true });
  assert.equal(await f.stage.begin('native', f.host, 'run-a'), undefined);
  assert.equal(f.stage.pending.size, 0);
  await assert.rejects(f.stage.begin('native', f.host, ''), /identity/);
});
