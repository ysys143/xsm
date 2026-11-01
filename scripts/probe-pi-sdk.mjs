/** Exercise registered Pi tools through the native execution/validation kernel, without a model. */
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';

const [packageRoot, output] = process.argv.slice(2);
if (!packageRoot || !output) throw new Error('usage: node probe-pi-sdk.mjs <Pi package root> <output.json>');
const root = fileURLToPath(new URL('../', import.meta.url));
const temp = await mkdtemp(join(tmpdir(), 'xsm-pi-sdk-'));
for (const key of Object.keys(process.env)) {
  if (!['PATH', 'LANG', 'TMPDIR', 'XSM_PYTHON'].includes(key)) delete process.env[key];
}
await mkdir(join(temp, 'project'));
process.env.HOME = join(temp, 'home');
process.env.PI_CODING_AGENT_DIR = join(temp, 'pi');
process.env.XSM_HOME = join(temp, 'state');
process.env.PYTHONDONTWRITEBYTECODE = '1';
const sdk = await import(pathToFileURL(join(packageRoot, 'dist/index.js')));
const result = { status: 'incomplete', root: temp, runtimeVersion: sdk.VERSION,
  modelCalls: 0, physicalHumanUiTested: false };
let session;
try {
  const settings = sdk.SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: false } });
  const loader = new sdk.DefaultResourceLoader({ cwd: join(temp, 'project'), agentDir: process.env.PI_CODING_AGENT_DIR,
    settingsManager: settings, additionalExtensionPaths: [join(root, 'integrations/pi/xsm.mjs')],
    noSkills: true, noPromptTemplates: true, noThemes: true, noContextFiles: true });
  await loader.reload();
  const loaded = await sdk.createAgentSession({ cwd: join(temp, 'project'), agentDir: process.env.PI_CODING_AGENT_DIR,
    settingsManager: settings, sessionManager: sdk.SessionManager.inMemory(), resourceLoader: loader });
  session = loaded.session;
  const displayed = [];
  await session.bindExtensions({ mode: 'rpc', uiContext: {
    notify() {}, setStatus() {},
    select: async (title, options) => { displayed.push({ title, options }); return options[0]; },
    input: async title => { displayed.push({ title }); return 'blue'; },
  } });
  session.agent.streamFn = () => { result.modelCalls += 1; throw new Error('model execution forbidden in native SDK probe'); };
  // The native nested-tool kernel requires an issuing assistant message.
  // This is an explicit fixture, not a model-produced response or human approval.
  session.agent.state.messages = [...session.agent.state.messages, {
    role: 'assistant', content: [{ type: 'toolCall', id: 'native-tool-probe', name: 'fixture-parent', arguments: {} }],
    api: 'unknown', provider: 'unknown', model: 'offline-fixture', stopReason: 'toolUse', timestamp: Date.now(),
    usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
  }];
  result.assistantFixture = true;
  const context = session.extensionRunner.createToolContext('native-tool-probe', new AbortController().signal);
  const declared = session.getAllTools().filter(tool => tool.name.startsWith('xsm_'));
  result.nativeToolCount = declared.length;
  assert.equal(declared.length, 21);
  const invalid = await context.executeTool('xsm_inbox', { wait: 5 });
  result.invalidWait = invalid;
  assert.equal(invalid.isError, true, 'unsupported capability must be an actual native tool error');
  const inbox = await context.executeTool('xsm_inbox', {});
  result.inbox = inbox;
  assert.equal(inbox.isError, false);
  const question = await context.executeTool('xsm_decide', { question: 'Native SDK choose', options: ['blue', 'green'] });
  result.question = question;
  assert.equal(question.isError, false);
  assert.match(JSON.stringify(question.result.content), /your user answered: blue/);
  assert.deepEqual(displayed, [{ title: 'Native SDK choose', options: ['blue', 'green'] }]);
  assert.equal(result.modelCalls, 0);
  result.status = 'passed';
} catch (error) {
  result.status = 'failed';
  result.error = { message: error.message, stack: error.stack };
} finally {
  if (session) {
    await session.extensionRunner.emit({ type: 'session_shutdown', reason: 'quit' });
    session.dispose();
  }
  await writeFile(resolve(output), JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify({ status: result.status, error: result.error?.message, nativeToolCount: result.nativeToolCount,
    modelCalls: result.modelCalls, root: temp }));
}
if (result.status !== 'passed') process.exitCode = 1;
