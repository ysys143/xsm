import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, mkdir, readdir, readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import binding from '../../integrations/opencode/xsm.mjs';
import { XsmClient } from '../typescript/xsm-client.mjs';

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

async function fixture(t) {
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
  const hooks = await binding(api, { schema, command, env, profile, onError: error => errors.push(error) });
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
  const send = (record, text) => sender.operationCall(origin.session, 'xsm_send',
    { target: 'ref:' + record.ref, text, wait: 0 });
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
