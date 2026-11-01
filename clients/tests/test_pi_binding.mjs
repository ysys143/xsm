/** Actual Pi binding code with controlled native API/backend fixtures; no Pi certification. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { TransportError } from '../typescript/xsm-client.mjs';
import { randomUUID } from 'node:crypto';

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

async function fixture(t, options = {}) {
  const temp = await mkdtemp(join(tmpdir(), 'xsm-pi-lifetime-'));
  const key = 'xsmPiFixture' + randomUUID();
  const hooks = new Map(), commands = new Map(), opened = [], entered = deferred(), release = deferred();
  let pause = false, pauseUpdate = false, attempts = 0;
  const attemptTimes = [];
  const tools = new Map();
  const XsmHost = { async open(hostOptions) {
    attemptTimes.push(performance.now());
    if (++attempts === 1 && options.failOpen) throw new Error("initial backend unavailable");
    if (attempts > 1 && attempts <= 1 + (options.failRecoveries ?? 0)) throw new TransportError("backend still unavailable");
    const host = { onError: hostOptions.onError, controller: new AbortController(), closed: false, operations: [{ name: "fixture_tool", description: "fixture", inputSchema: { type: "object" } }],
      session: { ref: 'stable', generation: String(opened.length) },
      async update() { if (options.failUpdate && opened.length === 1) throw new Error("initial state unavailable"); if (pauseUpdate && opened.length > 1) { entered.resolve(); await release.promise; } }, async close() { this.closed = true; this.controller.abort(); } };
    opened.push(host);
    if (pause) { entered.resolve(); await release.promise; }
    return host;
  } };
  globalThis[key] = { XsmHost, getAgentDir: () => temp };
  let code = await readFile(new URL('../../integrations/pi/xsm.mjs', import.meta.url), 'utf8');
  code = code.replace("import { getAgentDir } from '@earendil-works/pi-coding-agent';", '');
  code = code.replace("import { XsmHost, RetryAdmission, parseHostCommand, renderInboxPacket } from '../../clients/typescript/xsm-host.mjs';",
    `import { RetryAdmission, parseHostCommand, renderInboxPacket } from ${JSON.stringify(new URL('../typescript/xsm-host.mjs', import.meta.url).href)};\nconst {XsmHost,getAgentDir}=globalThis[${JSON.stringify(key)}];`);
  if (process.env.XSM_PI_LIFETIME_MUTANT === 'backoff') {
    const changed = code.replace('reconnectDelay = Math.min(reconnectDelay * 2, 5000);', 'reconnectDelay = 1;');
    assert.notEqual(changed, code);
    code = changed;
  }
  if (process.env.XSM_PI_LIFETIME_MUTANT === 'auto') {
    const changed = code.replace('function scheduleReconnect() {', 'function scheduleReconnect() { return;');
    assert.notEqual(changed, code);
    code = changed;
  }
  if (process.env.XSM_PI_LIFETIME_MUTANT === 'epoch') {
    const changed = code.replace('if (token !== epoch) { await opened.close();', 'if (false) { await opened.close();')
      .replace('if (token !== epoch || host !== opened) { await opened.close();', 'if (false) { await opened.close();');
    assert.notEqual(changed, code, 'epoch guard moved; update intentional mutation');
    code = changed;
  }
  code = code.replace("'../../clients/typescript/xsm-client.mjs'", JSON.stringify(new URL('../typescript/xsm-client.mjs', import.meta.url).href));
  const { default: binding } = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));
  binding({ on: (name, callback) => hooks.set(name, callback), registerTool: tool => tools.set(tool.name, tool),
    registerCommand: (name, command) => commands.set(name, command), getAllTools: () => [] });
  const ctx = { cwd: temp, hasUI: false, isIdle: () => true,
    sessionManager: { getSessionId: () => 'native', getSessionName: () => '', getBranch: () => [] },
    ui: { notify() {}, setStatus() {} } };
  t.after(async () => { release.resolve(); await hooks.get('session_shutdown')(); delete globalThis[key]; await rm(temp, { recursive: true, force: true }); });
  if (options.failOpen || options.failUpdate) await assert.rejects(hooks.get('session_start')({}, ctx), /initial/);
  else await hooks.get('session_start')({}, ctx);
  return { ctx, hooks, opened, entered, release, tools, attemptTimes,
    pause: () => { pause = true; }, pauseUpdate: () => { pauseUpdate = true; }, command: context => commands.get('xsm').handler('status', context ?? ctx) };
}

test('Pi coalesces concurrent recovery entries', async t => {
  const f = await fixture(t);
  f.opened[0].controller.abort();
  f.pause();
  const first = f.command(), second = f.command();
  await f.entered.promise;
  f.release.resolve();
  await Promise.all([first, second]);
  assert.equal(f.opened.length, 2);
  assert.equal(f.opened[0].closed, true);
  assert.equal(f.opened[1].closed, false);
});

test('Pi shutdown during backend recovery closes the uncommitted host', async t => {
  const f = await fixture(t);
  f.opened[0].controller.abort();
  f.pause();
  const command = f.command();
  const rejected = assert.rejects(command, /native session changed/);
  await f.entered.promise;
  const shutdown = f.hooks.get('session_shutdown')();
  f.release.resolve();
  await Promise.all([rejected, shutdown]);
  assert.equal(f.opened.length, 2);
  assert.ok(f.opened.every(host => host.closed));
});

test('Pi rejects a different native conversation before recovering', async t => {
  const f = await fixture(t);
  f.opened[0].controller.abort();
  await assert.rejects(f.command({ ...f.ctx, sessionManager: { ...f.ctx.sessionManager, getSessionId: () => 'foreign' } }),
    /native session or workspace changed/);
  assert.equal(f.opened.length, 1);
});


test('Pi shutdown during recovered state update closes the new host', async t => {
  const f = await fixture(t);
  f.opened[0].controller.abort();
  f.pauseUpdate();
  const command = f.command();
  const rejected = assert.rejects(command, /native session changed/);
  await f.entered.promise;
  const shutdown = f.hooks.get('session_shutdown')();
  f.release.resolve();
  await Promise.all([rejected, shutdown]);
  assert.ok(f.opened.every(host => host.closed));
});


for (const phase of ['failOpen', 'failUpdate']) test(`Pi retries first registration after ${phase}`, async t => {
  const f = await fixture(t, { [phase]: true });
  await f.command();
  assert.ok(f.tools.has('fixture_tool'));
  assert.equal(f.opened.at(-1).closed, false);
  if (phase === 'failUpdate') assert.equal(f.opened[0].closed, true);
});

test('Pi shutdown prevents retrying a failed initial registration', async t => {
  const f = await fixture(t, { failOpen: true });
  await f.hooks.get('session_shutdown')();
  await assert.rejects(f.command(), /not registered/);
  assert.equal(f.opened.length, 0);
});


test('Pi reconnects a registered transport failure without a native operation', async t => {
  const f = await fixture(t);
  f.opened[0].controller.abort();
  f.opened[0].onError(new TransportError('backend exited'));
  const deadline = Date.now() + 2000;
  while (f.opened.length < 2 && Date.now() < deadline) await new Promise(done => setTimeout(done, 10));
  assert.equal(f.opened.length, 2);
  assert.equal(f.opened[0].closed, true);
  assert.equal(f.opened[1].closed, false);
});

test('Pi shutdown cancels pending automatic reconnect', async t => {
  const f = await fixture(t);
  f.opened[0].controller.abort();
  f.opened[0].onError(new TransportError('backend exited'));
  await f.hooks.get('session_shutdown')();
  await new Promise(done => setTimeout(done, 350));
  assert.equal(f.opened.length, 1);
});


test('Pi does not reconnect for an ordinary native error', async t => {
  const f = await fixture(t);
  f.opened[0].controller.abort();
  f.opened[0].onError(new Error('ordinary native refusal'));
  await new Promise(done => setTimeout(done, 350));
  assert.equal(f.opened.length, 1);
});

test('Pi backs off failed reconnects then recovers without replay', { timeout: 5000 }, async t => {
  const f = await fixture(t, { failRecoveries: 2 });
  f.opened[0].controller.abort();
  f.opened[0].onError(new TransportError('backend exited'));
  const deadline = Date.now() + 4000;
  while (f.opened.length < 2 && Date.now() < deadline) await new Promise(done => setTimeout(done, 10));
  assert.equal(f.opened.length, 2);
  assert.equal(f.opened[1].closed, false);
  assert.equal(f.attemptTimes.length, 4);
  assert.ok(f.attemptTimes[2] - f.attemptTimes[1] >= 450);
  assert.ok(f.attemptTimes[3] - f.attemptTimes[2] >= 950);
});
