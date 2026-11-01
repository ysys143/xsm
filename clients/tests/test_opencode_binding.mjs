import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, mkdir, readdir, readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import binding from '../../integrations/opencode/xsm.mjs';
import { XsmClient } from '../typescript/xsm-client.mjs';
import { XsmHost } from '../typescript/xsm-host.mjs';

const root = fileURLToPath(new URL('../../', import.meta.url));
// Native schema objects are inspected here; the pinned native CLI separately checks real Zod schemas.
function node(type, value) {
  return { type, value, optional() { return { ...this, optionalField: true }; },
    describe() { return this; }, min() { return this; }, max() { return this; },
    int() { return this; }, passthrough() { return this; } };
}
const schema = Object.fromEntries(['string', 'boolean', 'number', 'object', 'array', 'enum']
  .map(type => [type, value => node(type, value)]));
const pause = () => new Promise(resolve => setTimeout(resolve, 10));
async function until(predicate) {
  const end = Date.now() + 5000;
  do { const value = await predicate(); if (value) return value; await pause(); } while (Date.now() < end);
  throw new Error('expected native observation did not occur');
}

async function fixture(t, options = {}) {
  const temp = await mkdtemp(join(tmpdir(), 'xsm-opencode-binding-'));
  const profile = join(temp, 'profile');
  await mkdir(profile);
  const command = [process.env.PYTHON ?? 'python3', '-B', '-m', 'xsm', 'protocol', 'serve', '--stdio'];
  const env = { PATH: process.env.PATH, HOME: temp, XSM_HOME: join(temp, 'state'), PYTHONPATH: root,
    PYTHONDONTWRITEBYTECODE: '1' };
  const native = new Map(), statuses = {}, errors = [], wakes = [];
  let corrupt = false;
  const api = { directory: temp, client: { session: {
    get: async ({ path: { id } }) => ({ data: { id, title: 'Native ' + id } }),
    prompt: async ({ path: { id }, body }) => {
      assert.equal(body.messageID, undefined, 'native host must allocate its ordered message ID');
      const message = { info: { id: 'msg_fixture_' + native.size, sessionID: id }, parts: body.parts };
      native.set(message.info.id, message);
      return { data: message };
    },
    message: async ({ path: { messageID } }) => ({ data: corrupt
      ? { ...native.get(messageID), parts: [] } : native.get(messageID) }),
    status: async () => ({ data: statuses }),
    promptAsync: async ({ path: { id } }) => { wakes.push(id); return { data: undefined }; },
  } } };
  const hooks = await binding(api, { schema, command, env, profile,
    onError: error => errors.push(error), ...options });
  const invoke = async (id, name, args = {}, extra = {}) => JSON.parse(await hooks.tool[name].execute(args,
    { sessionID: id, directory: temp, abort: new AbortController().signal, ...extra }));
  const records = async () => {
    const dir = join(temp, 'state/sessions');
    return (await Promise.all((await readdir(dir)).filter(file => file.endsWith('.json'))
      .map(file => readFile(join(dir, file), 'utf8'))))
      .map(JSON.parse).filter(record => record.runtime === 'opencode');
  };
  const sender = await XsmClient.connect({ command, env, cwd: temp });
  const origin = await sender.sessionOpen({ runtime: 'sender-fixture', profile: 'one', conversation: 'sender', cwd: temp });
  const send = (record, text, options = {}) => sender.operationCall(origin.session, 'xsm_send',
    { target: 'ref:' + record.ref, text, wait: 0, ...options });
  t.after(async () => { await hooks.dispose(); await sender.close(); await rm(temp, { recursive: true, force: true }); });
  return { hooks, invoke, records, native, errors, wakes, statuses, send,
    corrupt: value => { corrupt = value; } };
}

test('OpenCode uses native conversation identity and preserves optional tool arguments', { timeout: 10000 }, async t => {
  const { hooks, invoke, records } = await fixture(t);
  assert.equal(Object.keys(hooks.tool).length, 21);
  assert.equal(hooks.tool.xsm_decide.args.question.optionalField, undefined);
  assert.equal(hooks.tool.xsm_send.args.wait.optionalField, true);
  await Promise.all([invoke('a', 'xsm_inbox'), invoke('a', 'xsm_inbox'), invoke('b', 'xsm_inbox')]);
  const rows = await records();
  assert.equal(rows.length, 2);
  assert.equal(new Set(rows.map(row => row.ref)).size, 2);
  await assert.rejects(invoke('forged', 'xsm_inbox', {}, { directory: root }), /directory differs/);
  assert.equal((await records()).length, 2);
  await assert.rejects(invoke('a', 'xsm_decide', { question: 'Choose', options: ['blue', 'green'] }), /no user-interface/);
});

test('OpenCode admits a real deferred inbox notice without an empty ACK instruction', { timeout: 10000 }, async t => {
  const code = "import runpy;from xsm import receive;receive.check=lambda *a,**k:('block','P2P admission temporarily unavailable: fixture');runpy.run_module('xsm',run_name='__main__')";
  const { invoke, records, native, send } = await fixture(t, {
    command: [process.env.PYTHON ?? 'python3', '-B', '-c', code, 'protocol', 'serve', '--stdio'],
  });
  await invoke('notice-reader', 'xsm_inbox');
  await send((await records())[0], 'retain this deferred original');
  await until(() => [...native.values()].some(message => message.parts.some(part => part.text?.includes('awaits network revalidation'))));
  const text = [...native.values()].flatMap(message => message.parts).find(part => part.text?.includes('awaits network revalidation')).text;
  assert.equal(text.includes('After reading, call xsm_ack'), false);
});

test('OpenCode default byte budget splits a passive backlog across native admissions', { timeout: 10000 }, async t => {
  const { hooks, invoke, records, native, send, wakes } = await fixture(t);
  await invoke('byte-reader', 'xsm_inbox');
  const receiver = (await records())[0];
  for (const marker of ['first-large', 'second-large', 'third-large']) {
    await send(receiver, marker + 'x'.repeat(300000), { wake: 'never' });
  }
  await hooks['chat.message']({ sessionID: 'byte-reader' }, { parts: [] });
  await until(() => native.size === 3);
  const texts = [...native.values()].flatMap(message => message.parts).filter(part => part.type === 'text').map(part => part.text);
  assert.equal(texts.length, 3);
  assert.ok(texts.every(text => Buffer.byteLength(text) < 524288));
  for (const marker of ['first-large', 'second-large', 'third-large']) assert.equal(texts.filter(text => text.includes(marker)).length, 1);
  assert.deepEqual(wakes, []);
});

test('native deletion and resume preserve address but replace the host generation', { timeout: 10000 }, async t => {
  const { hooks, invoke, records } = await fixture(t);
  await invoke('a', 'xsm_inbox');
  const [before] = await records();
  await hooks.event({ event: { type: 'session.deleted', properties: { info: { id: 'a' } } } });
  await invoke('a', 'xsm_inbox');
  const [after] = await records();
  assert.equal(after.ref, before.ref);
  assert.notEqual(after.protocol_generation, before.protocol_generation);
});

test('an attached native UI receives the actual tool conversation and applies through the common host',
  { timeout: 10000 }, async t => {
    const displays = [];
    const { invoke } = await fixture(t, { present: async (conversation, event, { signal }) => {
      assert.equal(signal.aborted, false);
      displays.push({ conversation, question: event.params.question });
      return { displayed: event.params.question, sourceId: 'opencode-tui:' + event.params.questionId,
        action: 'accept', answer: 'blue' };
    } });
    const result = await invoke('native-question-a', 'xsm_decide', { question: 'Choose a color', options: ['blue', 'green'] });
    assert.match(JSON.stringify(result), /your user answered: blue/);
    assert.deepEqual(displays, [{ conversation: 'native-question-a', question: 'Choose a color' }]);
  });

test('stored native input keeps consumption explicit and does not wake an already busy conversation', { timeout: 10000 }, async t => {
  const { invoke, records, native, send, statuses, wakes, errors } = await fixture(t);
  await invoke('a', 'xsm_inbox');
  const [receiver] = await records();
  statuses.a = { type: 'busy' };
  await send(receiver, 'admit only in a');
  await until(() => native.size);
  const text = [...native.values()][0].parts[0].text;
  assert.match(text, /admit only in a/);
  assert.equal([...native.values()][0].info.sessionID, 'a');
  assert.deepEqual(wakes, []);
  const tokens = JSON.parse(text.match(/tokens: (\[[^\n]+?\])/)[1]);
  const ack = await invoke('a', 'xsm_ack', { tokens });
  assert.equal(ack.acked.length, 1);
  assert.deepEqual(errors, []);
});

test('unverified native storage releases a claim for a later natural boundary', { timeout: 10000 }, async t => {
  const { hooks, invoke, records, send, corrupt, errors, native } = await fixture(t);
  await invoke('a', 'xsm_inbox');
  const [receiver] = await records();
  corrupt(true);
  await send(receiver, 'keep after failed verification');
  await until(() => errors.some(error => /admission was not observed/.test(error.message)));
  corrupt(false);
  await hooks['chat.message']({ sessionID: 'a' }, { parts: [{ type: 'text', text: 'natural user input' }] });
  assert.equal(native.size, 2);
  const text = [...native.values()].at(-1).parts[0].text;
  assert.match(text, /keep after failed verification/);
  const tokens = JSON.parse(text.match(/tokens: (\[[^\n]+?\])/)[1]);
  assert.equal((await invoke('a', 'xsm_ack', { tokens })).acked.length, 1);
});

test('concurrent native calls recover a dead backend with new claims', { timeout: 15000 }, async t => {
  const { invoke, records, send, errors, native } = await fixture(t);
  await invoke('a', 'xsm_inbox');
  const [before] = await records();
  await send(before, 'survive OpenCode backend death', { wake: 'never' });
  const original = (await invoke('a', 'xsm_inbox')).claims[0];
  process.kill(before.pid, 'SIGKILL');
  await until(() => errors.length > 0);
  const packets = await Promise.all([invoke('a', 'xsm_inbox'), invoke('a', 'xsm_inbox')]);
  const [after] = await records();
  assert.equal(after.ref, before.ref);
  assert.notEqual(after.pid, before.pid);
  assert.notEqual(after.protocol_generation, before.protocol_generation);
  const claims = packets.flatMap(packet => packet.claims);
  assert.equal(claims.length, 1);
  assert.equal(claims[0].id, original.id);
  assert.notEqual(claims[0].token, original.token);
  await assert.rejects(invoke('a', 'xsm_ack', { tokens: [original.token] }), error => error.code === -32602);
  assert.deepEqual((await invoke('a', 'xsm_ack', { tokens: [claims[0].token] })).acked, [original.id]);
  assert.equal(native.size, 0, 'FYI recovery is a pull, not an unsolicited native injection');
});


test('failed initial state update closes participation before retry', { timeout: 15000 }, async t => {
  const { invoke, records } = await fixture(t);
  const update = XsmHost.prototype.update;
  let first;
  t.mock.method(XsmHost.prototype, 'update', async function (...args) {
    if (!first) { first = this; throw new Error('initial state update failed'); }
    return update.apply(this, args);
  });
  try {
    await assert.rejects(invoke('a', 'xsm_inbox'), /initial state update failed/);
    assert.equal(first.closed, true);
    const [ended] = await records();
    assert.ok(ended.ended_at);
    await invoke('a', 'xsm_inbox');
    const [recovered] = await records();
    assert.equal(recovered.ref, ended.ref);
    assert.notEqual(recovered.protocol_generation, ended.protocol_generation);
    assert.equal(recovered.ended_at, undefined);
  } finally { await first?.close(); }
});
