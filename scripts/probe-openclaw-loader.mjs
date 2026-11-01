/** Pinned native loader + metadata discovery only; no agent/model/messenger execution. */
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readdir, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import operations from '../integrations/openclaw/tools.mjs';

const [nativeRoot, output] = process.argv.slice(2);
if (!nativeRoot || !output) throw new Error('usage: node probe-openclaw-loader.mjs <native package root> <output.json>');
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
const registry = native[alias]({ config: {
  plugins: { enabled: true, allow: ['xsm'], load: { paths: [join(root, 'integrations/openclaw/xsm.mjs')] },
    entries: { xsm: { enabled: true } } }, agents: { defaults: { workspace: temp } },
}, workspaceDir: temp, cache: false, activate: true, onlyPluginIds: ['xsm'] });
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
await writeFile(destination, JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify(result));
