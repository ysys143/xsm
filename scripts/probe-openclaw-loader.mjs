/** Pinned native loader/tools with explicit caller fixtures; no agent/model/messenger execution. */
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readdir, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import operations from '../integrations/openclaw/tools.mjs';

const [nativeRoot, output, mode] = process.argv.slice(2);
assert.ok(!mode || mode === '--execute');
if (!nativeRoot || !output) throw new Error('usage: node probe-openclaw-loader.mjs <native package root> <output.json> [--execute]');
const root = fileURLToPath(new URL('../', import.meta.url));
const destination = resolve(output);
const pkg = JSON.parse(await readFile(join(nativeRoot, 'package.json'), 'utf8'));
assert.equal(pkg.version, '2026.10.9');
const temp = await mkdtemp(join(tmpdir(), 'xsm-openclaw-loader-'));
for (const key of Object.keys(process.env)) {
  if (!['PATH', 'LANG', 'TMPDIR'].includes(key)) delete process.env[key];
}
process.env.HOME = join(temp, 'home');
process.env.OPENCLAW_STATE_DIR = join(temp, 'native-state');
process.env.XSM_HOME = join(temp, 'xsm');
process.env.OPENCLAW_NO_RESPAWN = '1';
process.env.PYTHONDONTWRITEBYTECODE = '1';
await mkdir(process.env.OPENCLAW_STATE_DIR);
process.chdir(temp);
// The loader is host internals, used only in this pinned probe, never by the product plugin.
const dist = join(nativeRoot, 'dist');
const candidates = (await readdir(dist)).filter(file => /^loader-runtime-load-.*\.mjs$/.test(file));
assert.equal(candidates.length, 1);
const file = join(dist, candidates[0]);
const text = await readFile(file, 'utf8');
const alias = /loadOpenClawPlugins as (\w+)/.exec(text)?.[1];
assert.ok(alias, 'native loader export was not found');
const native = await import(pathToFileURL(file));
const config = {
  plugins: { enabled: true, allow: ['xsm'], load: { paths: [join(root, 'integrations/openclaw/xsm.mjs')] },
    entries: { xsm: { enabled: true } } }, agents: { defaults: { workspace: temp } },
};
const registry = native[alias]({ config, workspaceDir: temp, cache: false, activate: true, onlyPluginIds: ['xsm'] });
const plugin = registry.plugins.find(item => item.id === 'xsm');
assert.equal(plugin?.status, 'loaded', JSON.stringify(registry.diagnostics));
assert.deepEqual(registry.diagnostics.filter(item => item.pluginId === 'xsm'), []);
const tools = registry.tools.filter(item => item.pluginId === 'xsm');
assert.deepEqual(tools.flatMap(item => item.names).sort(), operations.map(item => item.name).sort());
for (const tool of tools) assert.equal(tool.factory({}), null);
await assert.rejects(readdir(join(temp, 'xsm/sessions')), { code: 'ENOENT' });
const result = { status: 'passed', runtimeVersion: pkg.version, node: process.version,
  nativeLoader: true, nativeTools: tools.length, metadataCreatedNoParticipant: true,
  nativeToolExecution: false, nativeUnloadTested: false, modelCalls: 0,
  physicalHumanUiTested: false, diagnostics: registry.diagnostics, root: temp };
if (mode === '--execute') {
  // Resolve pinned host-internal exports by their original names, not guessed minified aliases.
  async function nativeFunction(prefix, name) {
    const files = (await readdir(dist)).filter(file => file.startsWith(prefix) && file.endsWith('.mjs'));
    for (const nameFile of files) {
      const path = join(dist, nameFile);
      const source = await readFile(path, 'utf8');
      const symbol = new RegExp(name + ' as (\\w+)').exec(source)?.[1];
      if (symbol) return (await import(pathToFileURL(path)))[symbol];
    }
    throw new Error('native export missing: ' + name);
  }
  const dispose = await nativeFunction('runtime-', 'disposePluginRegistryInstances');
  try {
    const resolveTools = await nativeFunction('tools-', 'resolvePluginTools');
    const context = id => ({ config, workspaceDir: temp,
      sessionId: id, sessionKey: 'agent:main:fixture' });
    const resolve = id => resolveTools({ context: context(id),
      runtimeRegistry: registry, toolAllowlist: ['xsm'] });
    const executable = resolve('native-fixture-a');
    assert.equal(executable.length, operations.length);
    const inbox = executable.find(tool => tool.name === 'xsm_inbox');
    const packet = await inbox.execute('native-inbox', {}, new AbortController().signal);
    assert.equal(packet.details.claims.length, 0);
    result.nativeToolExecution = true;
    result.explicitCallerFixture = true;
    const files = (await readdir(join(temp, 'xsm/sessions'))).filter(file => file.endsWith('.json'));
    assert.equal(files.length, 1);
    const record = JSON.parse(await readFile(join(temp, 'xsm/sessions', files[0]), 'utf8'));
    assert.equal(record.runtime, 'openclaw');
    result.nativeRef = record.ref;
    const records = async () => Promise.all((await readdir(join(temp, 'xsm/sessions')))
      .filter(file => file.endsWith('.json'))
      .map(async file => JSON.parse(await readFile(join(temp, 'xsm/sessions', file), 'utf8'))));
    const second = resolve('native-fixture-b');
    const inboxB = second.find(tool => tool.name === 'xsm_inbox');
    await inboxB.execute('open-b', {});
    const rows = await records();
    assert.equal(rows.length, 2);
    const target = rows.find(row => row.ref !== record.ref);
    assert.ok(target, 'same route must keep separate native conversation identities');
    await executable.find(tool => tool.name === 'xsm_send').execute('send-a-b', {
      target: 'ref:' + target.ref, text: 'OpenClaw native factory fixture message', wait: 0,
    });
    const received = await inboxB.execute('receive-b', {});
    assert.equal(received.details.claims.length, 1);
    assert.match(JSON.stringify(received.details.messages), /native factory fixture message/);
    const ack = await second.find(tool => tool.name === 'xsm_ack').execute('consume-b', {
      tokens: received.details.claims.map(claim => claim.token),
    });
    assert.equal(ack.details.acked.length, 1);
    result.nativeDmPullAck = true;
    await assert.rejects(executable.find(tool => tool.name === 'xsm_decide').execute('unbound-ui', {
      question: 'Native fixture question', options: ['blue', 'green'],
    }), /no user-interface/);
    result.unboundUiRefused = true;
    const { getGlobalHookRunner } = await import(pathToFileURL(join(nativeRoot, 'dist/plugin-sdk/plugin-runtime.js')));
    const hooks = getGlobalHookRunner();
    assert.ok(hooks?.hasHooks('session_end'));
    await hooks.runSessionEnd({ sessionId: 'native-fixture-a', sessionKey: 'agent:main:fixture',
      messageCount: 0, reason: 'reset' }, context('native-fixture-a'));
    assert.ok((await records()).find(row => row.ref === record.ref).ended_at);
    await assert.rejects(inbox.execute('late-a', {}), /no longer current/);
    const resumed = resolve('native-fixture-a').find(tool => tool.name === 'xsm_inbox');
    await resumed.execute('resume-a', {});
    const after = (await records()).find(row => row.ref === record.ref);
    assert.notEqual(after.protocol_generation, record.protocol_generation);
    assert.ok(!after.ended_at);
    result.nativeSessionEndResume = true;
  } finally {
    const cleanup = await dispose(registry);
    assert.deepEqual(cleanup.failures, []);
    result.nativeUnloadTested = true;
  }
  for (const file of (await readdir(join(temp, 'xsm/sessions'))).filter(file => file.endsWith('.json'))) {
    const record = JSON.parse(await readFile(join(temp, 'xsm/sessions', file), 'utf8'));
    assert.ok(record.ended_at, 'native disposal left a live participation');
  }
}
await writeFile(destination, JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify(result));
