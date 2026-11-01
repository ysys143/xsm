/** Native storage characterization in an isolated profile; no model or production settings. */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, mkdir, readdir, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const [nativeRoot, output] = process.argv.slice(2);
if (!nativeRoot || !output) throw new Error('usage: node probe-openclaw-session-guard.mjs <native package root> <output.json>');
const destination = resolve(output);
assert.equal(JSON.parse(await readFile(join(nativeRoot, 'package.json'), 'utf8')).version, '2026.10.9');
const temp = await mkdtemp(join(tmpdir(), 'xsm-openclaw-guard-'));
for (const key of Object.keys(process.env)) {
  if (!['PATH', 'LANG', 'TMPDIR'].includes(key)) delete process.env[key];
}
process.env.HOME = join(temp, 'home');
process.env.OPENCLAW_STATE_DIR = join(temp, 'state');
await mkdir(process.env.OPENCLAW_STATE_DIR);
process.chdir(temp);
const dist = join(nativeRoot, 'dist');
const nativeExports = new Map();
async function exported(prefix, symbol) {
  for (const file of (await readdir(dist)).filter(file => file.startsWith(prefix) && file.endsWith('.mjs'))) {
    const path = join(dist, file);
    const text = await readFile(path, 'utf8');
    const alias = new RegExp(symbol + ' as (\\w+)').exec(text)?.[1];
    if (alias) {
      nativeExports.set(symbol, { url: pathToFileURL(path).href, alias });
      return (await import(pathToFileURL(path)))[alias];
    }
  }
  throw new Error('pinned native export missing: ' + symbol);
}
const createRuntime = await exported('runtime-', 'createPluginRuntime');
const runtime = createRuntime();
const session = runtime.agent.session;
const storePath = session.resolveStorePath(undefined, { agentId: 'main' });
const cfg = { agents: { entries: { main: {} } } };
const enqueue = await exported('host-hook-state-', 'enqueuePluginNextTurnInjection');
const scope = { sessionKey: 'agent:main:probe', agentId: 'main', storePath };
const replace = sessionId => session.upsertSessionEntry({ ...scope, entry: { sessionId, updatedAt: Date.now() } });
const read = () => session.getSessionEntry({ ...scope, readConsistency: 'latest' });
await replace('old-conversation');
await replace('replacement-conversation');
const queued = await enqueue({ cfg, pluginId: 'xsm', injection: {
  sessionKey: scope.sessionKey, agentId: scope.agentId, text: 'old conversation only',
  metadata: { expectedSessionId: 'old-conversation' },
} });
assert.equal(queued.enqueued, true);
assert.equal(read().sessionId, 'replacement-conversation');
assert.equal(read().pluginNextTurnInjections.xsm[0].metadata.expectedSessionId, 'old-conversation');
let staleGuardCalls = 0, staleUpdatePrepared = false;
await assert.rejects(session.patchSessionEntry({ ...scope,
  assertCommitAllowed() {
    staleGuardCalls++;
    if (read()?.sessionId !== 'old-conversation') throw new Error('exact native conversation changed');
  },
  update() { staleUpdatePrepared = true; return { pluginExtensions: { xsm: { probe: 'stale-write' } } }; },
}), /exact native conversation changed/);
assert.equal(read().pluginExtensions?.xsm?.probe, undefined);
assert.ok(staleGuardCalls > 0);

const results = [];
for (const crossProcess of [false, true]) for (const guarded of [false, true]) {
  await replace('prepared-conversation');
  let release, started;
  const pause = new Promise(resolve => { release = resolve; });
  const entered = new Promise(resolve => { started = resolve; });
  let guardCalls = 0;
  const patch = session.patchSessionEntry({ ...scope,
    ...(guarded ? { assertCommitAllowed() {
      guardCalls++;
      if (read()?.sessionId !== 'prepared-conversation') throw new Error('exact native conversation changed');
    } } : {}),
    update: async () => { started(); await pause; return { pluginExtensions: { xsm: { probe: 'prepared-only' } } }; },
  });
  const settled = patch.then(() => ({ rejected: false }), error => ({ rejected: true, error: error.message }));
  await entered;
  let child;
  const replacement = crossProcess ? new Promise((resolve, reject) => {
    const entry = nativeExports.get('createPluginRuntime');
    const code = `const native = await import(process.argv[1]);
      const runtime = native[process.argv[2]]();
      await runtime.agent.session.upsertSessionEntry({ ...JSON.parse(process.argv[3]),
        entry: { sessionId: 'replaced-during-prepare', updatedAt: Date.now() } });
      console.log('replacement-committed');`;
    child = spawn(process.execPath, ['--input-type=module', '-e', code, entry.url, entry.alias, JSON.stringify(scope)],
      { env: process.env, stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '', stderr = '';
    child.stdout.on('data', data => { stdout += data; });
    child.stderr.on('data', data => { stderr += data; });
    child.once('error', reject);
    child.once('close', code => code === 0 && stdout.includes('replacement-committed')
      ? resolve() : reject(new Error('native child failed: ' + stderr)));
  }) : replace('replaced-during-prepare');
  let raced;
  try {
    raced = await Promise.race([replacement.then(() => true), new Promise(resolve => setTimeout(() => resolve(false), crossProcess ? 3000 : 500))]);
  } finally { release(); }
  const outcome = await settled;
  await replacement;
  const row = read();
  results.push({ crossProcess, guarded, raced, guardCalls, ...outcome, sessionId: row.sessionId,
    preparedWritePresent: row.pluginExtensions?.xsm?.probe === 'prepared-only' });
  if (guarded && raced) {
    assert.equal(row.sessionId, 'replaced-during-prepare');
    assert.equal(outcome.rejected, true);
    assert.equal(row.pluginExtensions?.xsm?.probe, undefined);
  }
}
const result = { status: 'passed', runtimeVersion: '2026.10.9', root: temp,
  queueMetadataDoesNotBindConversation: true, staleGuardCalls, staleUpdatePrepared,
  staleAdmissionGuardRejected: true, storageRaces: results, modelCalls: 0,
  nativeAgentTurn: false, scope: 'native SDK storage fixture, not automatic delivery certification' };
await writeFile(destination, JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify(result));
