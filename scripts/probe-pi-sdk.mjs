/** Exercise registered Pi tools through the native execution/validation kernel, without a model. */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdtemp, mkdir, writeFile, readdir, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { XsmClient } from '../clients/typescript/xsm-client.mjs';

const [packageRoot, output, mode, entryOverride] = process.argv.slice(2);
assert.ok(!mode || ['--notice', '--batch', '--recover', '--collaboration'].includes(mode));
if (!packageRoot || !output) throw new Error('usage: node probe-pi-sdk.mjs <Pi package root> <output.json>');
const root = fileURLToPath(new URL('../', import.meta.url));
const temp = await mkdtemp(join(tmpdir(), 'xsm-pi-sdk-'));
for (const key of Object.keys(process.env)) {
  if (!['PATH', 'LANG', 'TMPDIR', 'XSM_PYTHON'].includes(key)) delete process.env[key];
}
await mkdir(join(temp, 'project'));
if (mode === '--collaboration') execFileSync('git', ['init', '-q', join(temp, 'project')]);
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
  session.agent.streamFunction = () => { result.modelCalls += 1; throw new Error('model execution forbidden in native SDK probe'); };
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
  assert.equal(declared.length, 23);
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
  if (mode === '--collaboration') {
    const checks = [], observations = [];
    result.collaboration = { checks, observations,
      scope: 'actual Pi SDK native tool kernel; synthetic issuing assistant and UI answers; no model or physical user' };
    const check = (name, test) => { result.collaboration.activeCheck = name; test(); checks.push(name); };
    const call = async (name, args, error = false) => {
      const packet = await context.executeTool(name, args);
      observations.push({ operation: name, arguments: args, packet });
      assert.equal(Boolean(packet.isError), error, JSON.stringify(packet));
      if (error) return packet;
      return JSON.parse(packet.result.content[0].text);
    };
    const team = 'native-collaboration';
    await call('xsm_team', { action: 'create', team });
    const listed = await call('xsm_team', { action: 'list' });
    check('native team list contains created team', () => assert.ok(listed.teams.some(t => t.name === team)));
    const shown = await call('xsm_team', { action: 'show', team });
    check('native team member is running', () => assert.equal(shown.members[0].running, true));
    const board = (action, args = {}) => call('xsm_board', { action, team, ...args });
    const emptyBoard = await board('log');
    check('native empty board', () => assert.deepEqual(emptyBoard.nodes, []));
    const item = 'decision: cache', body = 'Native contribution: 한글 preserved';
    await board('set', { item, text: body });
    const first = (await board('log')).nodes[0];
    check('native board first body and root', () => {
      assert.equal(first.body, body); assert.deepEqual(first.parents, []); assert.equal(first.item, item);
    });
    await board('set', { item, text: 'Native revision' });
    const revised = (await board('log', { item })).nodes;
    check('native board links observed predecessor', () => {
      assert.equal(revised.length, 2); assert.deepEqual(revised.find(n => n.body === 'Native revision').parents, [first.id]);
    });
    const filtered = await board('log', { item: 'absent' });
    check('native board item filter', () => assert.deepEqual(filtered.nodes, []));
    const decided = await call('xsm_decide', { question: 'Native SDK cache strategy', options: ['bounded', 'none'], team, item });
    const decisions = (await board('decisions')).decisions;
    check('synthetic native UI answer persisted once', () => {
      assert.equal(decisions.length, 1); assert.equal(decisions[0].answer, 'bounded'); assert.equal(decisions[0].via, 'host-user');
      assert.equal(decided.decision.recorded, true);
    });
    const decisionNodes = (await board('log', { item })).nodes;
    check('native board decision has human node reference', () => assert.equal(
      decisionNodes.filter(n => n.decision === decisions[0].id && n.author_kind === 'human').length, 1));
    const doc = (action, args = {}, error = false) => call('xsm_doc', { action, doc: 'BOARD.md', ...args }, error);
    const report = (await doc('add', { text: 'Native document report: 한글', tags: ['report'] })).node;
    const read = await doc('show', { node: report.id });
    check('native document immutable readback', () => assert.deepEqual(read.node, report));
    check('native document author belongs to agent', () => assert.equal(report.author_kind, 'agent'));
    const hypothesis = (await doc('add', { text: 'Native hypothesis', tags: ['hypothesis'], parents: [report.id] })).node;
    const frontier = await doc('leaves');
    check('native document frontier links predecessor', () => {
      assert.deepEqual(hypothesis.parents, [report.id]); assert.deepEqual(frontier.nodes.map(n => n.id), [hypothesis.id]);
    });
    await doc('add', { text: 'Native working declaration', tags: ['wip'], parents: [hypothesis.id] });
    const next = await doc('next');
    check('native wip does not allocate or hide hypothesis', () => {
      assert.equal(next.assigns, false); assert.equal(next.total, 1); assert.equal(next.candidates[0].id, hypothesis.id);
    });
    await doc('add', { text: 'Native independent insight', tags: ['insight'] });
    const all = await doc('next'), limited = await doc('next', { limit: 1 });
    check('native document limit preserves total', () => {
      assert.equal(all.total, 2); assert.equal(limited.total, 2); assert.deepEqual(limited.candidates, all.candidates.slice(0, 1));
    });
    await doc('add', { text: 'orphan', parents: ['f'.repeat(12)] }, true);
    const logged = await doc('log'), rendered = await doc('render');
    check('native missing parent leaves graph unchanged', () => assert.equal(logged.nodes.length, 4));
    check('native render includes all contributions', () => {
      assert.equal(rendered.nodes, 4); assert.ok(rendered.text.includes(report.body));
    });
    await doc('show', { node: 'f'.repeat(12) }, true);
    check('native unknown node rejected', () => assert.equal(observations.at(-1).packet.isError, true));
    const endorsementArgs = { doc: 'BOARD.md', node: report.id };
    const endorsed = await call('xsm_doc_endorse', endorsementArgs);
    const human = (await doc('show', { node: endorsed.endorsement.node })).node;
    check('synthetic native endorsement binds original', () => {
      assert.equal(endorsed.endorsement.parent, report.id); assert.equal(endorsed.endorsement.via, 'host-user');
      assert.deepEqual(human.parents, [report.id]); assert.equal(human.author_kind, 'human'); assert.equal(human.body, report.body);
    });
    const replay = await call('xsm_doc_endorse', endorsementArgs);
    const afterEndorsement = await doc('log');
    check('native endorsement replay preserves receipt and node count', () => {
      assert.deepEqual(replay, endorsed); assert.equal(afterEndorsement.nodes.length, 5);
    });

    sender = await XsmClient.connect({ command: [join(root, 'bin/xsm'), 'protocol', 'serve', '--stdio'],
      cwd: join(temp, 'project'), env: process.env });
    const origin = await sender.sessionOpen({ runtime: 'collaboration-fixture', profile: temp,
      conversation: 'sender', cwd: join(temp, 'project') });
    await sender.operationCall(origin.session, 'xsm_inbox', {});
    const records = await Promise.all((await readdir(join(process.env.XSM_HOME, 'sessions')))
      .filter(n => n.endsWith('.json')).map(async n => JSON.parse(await readFile(join(process.env.XSM_HOME, 'sessions', n), 'utf8'))));
    const receiver = records.find(r => r.runtime === 'pi'); assert.ok(receiver);
    check('native document author matches actual Pi conversation', () => assert.ok(report.author.includes('[' + receiver.ref + ']')));
    const bytes = Buffer.from([0, 255, 65, 10]);
    const sent = await sender.operationCall(origin.session, 'xsm_send', { target: 'ref:' + receiver.ref,
      text: 'Native binary attachment', request_id: 'native-incoming-file', wake: 'never', wait: 0,
      attachments: [{ name: 'fixture.bin', base64: bytes.toString('base64') }] });
    const packet = await call('xsm_inbox', { message_ids: [sent.send.id] });
    const metadata = packet.items.find(i => i.id === sent.send.id).files;
    const file = metadata.files[0];
    const content = await call('xsm_files', { storage_id: metadata.storage_id, entry_id: file.id, encoding: 'base64' });
    check('native binary attachment preserves bytes', () => assert.deepEqual(Buffer.from(content.content, 'base64'), bytes));
    check('native attachment metadata preserves size name and hash', () => {
      assert.equal(file.size, bytes.length); assert.equal(file.name, 'fixture.bin');
      assert.equal(file.sha256, createHash('sha256').update(bytes).digest('hex'));
    });
    const ack = await call('xsm_ack', { tokens: packet.claims.filter(c => c.id === sent.send.id).map(c => c.token) });
    check('native attachment original explicitly ACKed', () => assert.deepEqual(ack.acked, [sent.send.id]));
    const outgoing = await call('xsm_send', { target: 'ref:' + origin.ref, text: 'Native outbound attachment',
      request_id: 'native-outgoing-file', wake: 'never', wait: 0, attachments: [{ name: 'owned.txt', text: 'Native outgoing 한글' }] });
    const manifest = await call('xsm_files', { storage_id: outgoing.materials.manifest_id, outgoing: true });
    const original = await call('xsm_files', { storage_id: outgoing.materials.manifest_id, entry_id: manifest.manifest.files[0].id, outgoing: true });
    check('native outgoing manifest retains original text', () => assert.equal(original.content, 'Native outgoing 한글'));
    const incoming = await sender.operationCall(origin.session, 'xsm_inbox', {});
    const ownFile = incoming.items.find(i => i.id === outgoing.send.id).files;
    const copied = await sender.operationCall(origin.session, 'xsm_files', { storage_id: ownFile.storage_id, entry_id: ownFile.files[0].id });
    check('native sent attachment available to real reference receiver', () => assert.equal(copied.content, 'Native outgoing 한글'));
    const denied = await call('xsm_files', { storage_id: ownFile.storage_id, entry_id: ownFile.files[0].id }, true);
    check('native file reader rejects another conversation storage', () => assert.match(JSON.stringify(denied), /owner|another|session/i));
    await sender.operationCall(origin.session, 'xsm_ack', { tokens: incoming.claims.filter(c => c.id === outgoing.send.id).map(c => c.token) });
    delete result.collaboration.activeCheck;
  }
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
