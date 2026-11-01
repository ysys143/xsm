/** Exercise registered Pi tools through the native execution/validation kernel, without a model. */
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtemp, mkdir, writeFile, readdir, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { XsmClient } from '../clients/typescript/xsm-client.mjs';

const [packageRoot, output, mode, entryOverride] = process.argv.slice(2);
assert.ok(!mode || ['--notice', '--batch', '--recover'].includes(mode));
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
let sender;
try {
  let entry = entryOverride ?? join(root, 'integrations/pi/xsm.mjs');
  if (mode === '--notice') {
    const code = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));from xsm import receive;check=receive.check;receive.check=lambda p,m:('block','P2P admission temporarily unavailable: fixture') if p.body.startswith('defer-fixture') else check(p,m);runpy.run_module('xsm',run_name='__main__')";
    entry = join(temp, 'notice-extension.mjs');
    await writeFile(entry, `import binding from ${JSON.stringify(pathToFileURL(join(root, 'integrations/pi/xsm.mjs')).href)};
      export default pi => binding(pi, { command: ${JSON.stringify([process.env.XSM_PYTHON ?? 'python3', '-B', '-c', code, root, 'protocol', 'serve', '--stdio'])} });`);
  }
  const settings = sdk.SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: false } });
  const loader = new sdk.DefaultResourceLoader({ cwd: join(temp, 'project'), agentDir: process.env.PI_CODING_AGENT_DIR,
    settingsManager: settings, additionalExtensionPaths: [entry],
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
  if (mode === '--recover') {
    const records = async () => (await Promise.all((await readdir(join(process.env.XSM_HOME, 'sessions')))
      .filter(name => name.endsWith('.json')).map(async name => JSON.parse(await readFile(join(process.env.XSM_HOME, 'sessions', name), 'utf8')))))
      .filter(record => record.runtime === 'pi');
    const [before] = await records();
    sender = await XsmClient.connect({ command: [join(root, 'bin/xsm'), 'protocol', 'serve', '--stdio'],
      cwd: join(temp, 'project'), env: process.env });
    const origin = await sender.sessionOpen({ runtime: 'recovery-fixture', profile: temp,
      conversation: 'sender', cwd: join(temp, 'project') });
    await sender.operationCall(origin.session, 'xsm_send', { target: 'ref:' + before.ref,
      text: 'Pi original survives backend crash', wake: 'never', wait: 0 });
    const packet = await context.executeTool('xsm_inbox', {});
    assert.equal(packet.isError, false);
    const original = JSON.parse(packet.result.content[0].text).claims[0];
    assert.equal(Number(execFileSync('ps', ['-o', 'ppid=', '-p', String(before.pid)], { encoding: 'utf8' }).trim()),
      process.pid, 'refuse to kill a backend not created by this probe');
    process.kill(before.pid, 'SIGKILL');
    const deadline = Date.now() + 5000;
    while (true) {
      try { process.kill(before.pid, 0); }
      catch (error) { if (error.code === 'ESRCH') break; throw error; }
      assert.ok(Date.now() < deadline, 'backend was not reaped');
      await new Promise(resolve => setTimeout(resolve, 10));
    }
    const recovered = await context.executeTool('xsm_inbox', {});
    assert.equal(recovered.isError, false, JSON.stringify(recovered));
    const claim = JSON.parse(recovered.result.content[0].text).claims[0];
    const [after] = await records();
    assert.equal(after.ref, before.ref);
    assert.notEqual(after.pid, before.pid);
    assert.notEqual(after.protocol_generation, before.protocol_generation);
    assert.equal(claim.id, original.id);
    assert.notEqual(claim.token, original.token);
    const stale = await context.executeTool('xsm_ack', { tokens: [original.token] });
    assert.equal(stale.isError, true);
    const ack = await context.executeTool('xsm_ack', { tokens: [claim.token] });
    assert.equal(ack.isError, false);
    assert.deepEqual(JSON.parse(ack.result.content[0].text).acked, [claim.id]);
    result.backendRecovery = { sameRef: true, generationChanged: true, oldClaimRejected: true,
      originalRecovered: true, nativeAck: true, oldPid: before.pid, newPid: after.pid };
  }
  if (mode === '--notice') {
    const folder = join(process.env.XSM_HOME, 'sessions');
    const records = await Promise.all((await readdir(folder)).filter(name => name.endsWith('.json'))
      .map(async name => JSON.parse(await readFile(join(folder, name), 'utf8'))));
    const receiver = records.find(record => record.runtime === 'pi');
    assert.ok(receiver);
    sender = await XsmClient.connect({ command: [join(root, 'bin/xsm'), 'protocol', 'serve', '--stdio'],
      cwd: join(temp, 'project'), env: process.env });
    const origin = await sender.sessionOpen({ runtime: 'notice-fixture', profile: temp,
      conversation: 'sender', cwd: join(temp, 'project') });
    await sender.operationCall(origin.session, 'xsm_send', { target: 'ref:' + receiver.ref,
      text: 'defer-fixture original', wake: 'never', wait: 0 });
    const boundary = session.extensionRunner.emit({ type: 'before_agent_start', prompt: 'notice boundary fixture', systemPrompt: '' });
    boundary.catch(() => {});
    const admitted = await Promise.race([boundary.then(() => true), new Promise(resolve => setTimeout(() => resolve(false), 2000))]);
    const notice = session.sessionManager.getBranch().find(entry => entry.type === 'custom_message' &&
      entry.customType === 'xsm' && entry.content.includes('awaits network revalidation'));
    assert.ok(notice, 'actual Pi session tree did not store the notice');
    assert.equal(notice.content.includes('After reading, call xsm_ack'), false);
    assert.equal(admitted, true, 'idle native storage admission was not observed');
    result.nativeClaimFreeNotice = true;
    await sender.operationCall(origin.session, 'xsm_send', { target: 'ref:' + receiver.ref,
      text: 'ordinary Pi native original', wake: 'never', wait: 0 });
    await session.extensionRunner.emit({ type: 'before_agent_start', prompt: 'original boundary fixture', systemPrompt: '' });
    const original = session.sessionManager.getBranch().filter(entry => entry.type === 'custom_message' &&
      entry.customType === 'xsm' && entry.content.includes('ordinary Pi native original')).at(-1);
    assert.ok(original);
    const tokens = JSON.parse(/xsm_ack with tokens: (\[[^\n]*?\])/.exec(original.content)[1]);
    assert.equal(tokens.length, 1);
    session.agent.state.messages = [...session.agent.state.messages, {
      role: 'assistant', content: [{ type: 'toolCall', id: 'notice-ack-probe', name: 'fixture-parent', arguments: {} }],
      api: 'unknown', provider: 'unknown', model: 'offline-fixture', stopReason: 'toolUse', timestamp: Date.now(),
      usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
    }];
    const ackContext = session.extensionRunner.createToolContext('notice-ack-probe', new AbortController().signal);
    const ack = await ackContext.executeTool('xsm_ack', { tokens });
    assert.equal(ack.isError, false);
    assert.equal(JSON.parse(ack.result.content[0].text).acked.length, 1);
    result.nativeOriginalAfterNoticeAck = true;
  }
  if (mode === '--batch') {
    const folder = join(process.env.XSM_HOME, 'sessions');
    const records = await Promise.all((await readdir(folder)).filter(name => name.endsWith('.json'))
      .map(async name => JSON.parse(await readFile(join(folder, name), 'utf8'))));
    const receiver = records.find(record => record.runtime === 'pi');
    sender = await XsmClient.connect({ command: [join(root, 'bin/xsm'), 'protocol', 'serve', '--stdio'],
      cwd: join(temp, 'project'), env: process.env });
    const origin = await sender.sessionOpen({ runtime: 'batch-fixture', profile: temp,
      conversation: 'sender', cwd: join(temp, 'project') });
    const markers = ['first-large', 'second-large', 'third-large'];
    for (const marker of markers) await sender.operationCall(origin.session, 'xsm_send', {
      target: 'ref:' + receiver.ref, text: marker + 'x'.repeat(300000), wake: 'never', wait: 0,
    });
    await session.extensionRunner.emit({ type: 'before_agent_start', prompt: 'batch boundary fixture', systemPrompt: '' });
    const read = () => session.sessionManager.getBranch().filter(entry => entry.type === 'custom_message' &&
      entry.customType === 'xsm' && markers.some(marker => entry.content.includes(marker)));
    const deadline = Date.now() + 5000;
    while (read().length < 3 && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 10));
    const delivered = read();
    assert.equal(delivered.length, 3, 'native byte budget did not split the passive backlog');
    const tokens = [];
    for (const message of delivered) {
      assert.ok(Buffer.byteLength(message.content) < 524288);
      tokens.push(...JSON.parse(/xsm_ack with tokens: (\[[^\n]*?\])/.exec(message.content)[1]));
    }
    assert.equal(new Set(tokens).size, 3);
    session.agent.state.messages = [...session.agent.state.messages, {
      role: 'assistant', content: [{ type: 'toolCall', id: 'batch-ack-probe', name: 'fixture-parent', arguments: {} }],
      api: 'unknown', provider: 'unknown', model: 'offline-fixture', stopReason: 'toolUse', timestamp: Date.now(),
      usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
    }];
    const ack = await session.extensionRunner.createToolContext('batch-ack-probe', new AbortController().signal)
      .executeTool('xsm_ack', { tokens });
    assert.equal(ack.isError, false);
    assert.equal(JSON.parse(ack.result.content[0].text).acked.length, 3);
    result.nativeBoundedPassiveBacklog = { messages: 3, acknowledgements: 3,
      bytes: delivered.map(message => Buffer.byteLength(message.content)) };
  }
  assert.equal(result.modelCalls, 0);
  result.status = 'passed';
} catch (error) {
  result.status = 'failed';
  result.error = { message: error.message, stack: error.stack };
} finally {
  await sender?.close();
  if (session) {
    await session.extensionRunner.emit({ type: 'session_shutdown', reason: 'quit' });
    session.dispose();
  }
  await writeFile(resolve(output), JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify({ status: result.status, error: result.error?.message, nativeToolCount: result.nativeToolCount,
    modelCalls: result.modelCalls, root: temp }));
}
if (result.status !== 'passed') process.exitCode = 1;
