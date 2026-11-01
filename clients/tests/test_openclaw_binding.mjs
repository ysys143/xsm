/** Explicit caller fixtures + actual protocol subprocesses, not a native OpenClaw certification. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, mkdir, readdir, readFile, realpath, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { register } from '../../integrations/openclaw/xsm.mjs';

const root = fileURLToPath(new URL('../../', import.meta.url));
async function fixture(t) {
  const temp = await realpath(await mkdtemp(join(tmpdir(), 'xsm-openclaw-binding-')));
  const profile = join(temp, 'native-state');
  await mkdir(profile);
  const tools = new Map(), hooks = new Map();
  let lifecycle;
  const result = register({ config: { plugins: { entries: { xsm: { hooks: { allowConversationAccess: true } } } } },
    runtime: { state: { resolveStateDir: () => profile } },
    logger: { error: message => assert.fail(message) },
    lifecycle: { registerRuntimeLifecycle: entry => { lifecycle = entry; } },
    registerTool: (factory, options) => tools.set(options.name, factory),
    on: (name, callback) => hooks.set(name, callback),
  }, { command: [process.env.PYTHON ?? 'python3', '-B', '-m', 'xsm', 'protocol', 'serve', '--stdio'],
    env: { PATH: process.env.PATH, HOME: temp, XSM_HOME: join(temp, 'state'), PYTHONPATH: root,
      PYTHONDONTWRITEBYTECODE: '1' } });
  assert.equal(typeof result.then, 'undefined', 'native register must be synchronous');
  const context = (id, extra = {}) => ({ sessionId: id, sessionKey: 'agent:main:route', workspaceDir: temp, ...extra });
  const tool = (id, name = 'xsm_inbox', extra = {}) => tools.get(name)(context(id, extra));
  const invoke = async (id, name = 'xsm_inbox', args = {}, extra = {}) =>
    (await tool(id, name, extra).execute('call', args, new AbortController().signal)).details;
  const records = async () => {
    const dir = join(temp, 'state/sessions');
    return (await Promise.all((await readdir(dir)).filter(name => name.endsWith('.json'))
      .map(name => readFile(join(dir, name), 'utf8')))).map(JSON.parse);
  };
  t.after(async () => { await result.close(); await rm(temp, { recursive: true, force: true }); });
  return { tools, hooks, lifecycle, context, tool, invoke, records, temp };
}

test('OpenClaw synchronous catalog and metadata discovery create no participant', async t => {
  const { tools } = await fixture(t);
  assert.equal(tools.size, 21);
  for (const factory of tools.values()) assert.equal(factory({}), null);
});

test('native conversation UUID isolates two conversations sharing a route and supports DM pull ACK',
  { timeout: 10000 }, async t => {
    const { invoke, records, temp } = await fixture(t);
    await Promise.all([invoke('a'), invoke('a')]);
    const [sender] = await records();
    await invoke('b');
    const rows = await records();
    assert.equal(rows.length, 2);
    assert.equal(new Set(rows.map(row => row.ref)).size, 2);
    assert.ok(rows.every(row => row.cwd === temp && row.runtime === 'openclaw'));
    const target = rows.find(row => row.ref !== sender.ref);
    await invoke('a', 'xsm_send', { target: 'ref:' + target.ref, text: 'Native fixture DM', wait: 0 });
    const packets = await Promise.all([invoke('a'), invoke('b')]);
    const receiver = packets.findIndex(packet => packet.claims.length);
    assert.equal(receiver, 1);
    assert.match(JSON.stringify(packets[receiver].messages), /Native fixture DM/);
    const ack = await invoke(['a', 'b'][receiver], 'xsm_ack', { tokens: packets[receiver].claims.map(c => c.token) });
    assert.equal(ack.acked.length, 1);
  });

test('session end invalidates retained tools and resume replaces participation generation',
  { timeout: 10000 }, async t => {
    const { invoke, tool, hooks, records } = await fixture(t);
    const retained = tool('a');
    await retained.execute('first', {});
    const [before] = await records();
    await hooks.get('session_end')({ sessionId: 'a', sessionKey: 'agent:main:route', reason: 'reset' });
    await assert.rejects(retained.execute('late', {}), /no longer current/);
    await invoke('a');
    const [after] = await records();
    assert.equal(after.ref, before.ref);
    assert.notEqual(after.protocol_generation, before.protocol_generation);
    await hooks.get('agent_end')({}, { sessionId: 'a' });
    assert.equal((await records())[0].activity, 'idle');
  });

test('unbound UI, changed workspace, cancellation and retired plugin cannot manufacture effects',
  { timeout: 10000 }, async t => {
    const { invoke, tool, lifecycle, temp } = await fixture(t);
    await invoke('a');
    await assert.rejects(invoke('a', 'xsm_decide', { question: 'Choose', options: ['blue', 'green'] }), /no user-interface/);
    const other = join(temp, 'other');
    await mkdir(other);
    assert.throws(() => tool('a', 'xsm_inbox', { workspaceDir: other }), /workspace changed/);
    const aborted = new AbortController(); aborted.abort();
    await assert.rejects(tool('a').execute('cancelled', {}, aborted.signal), /no longer current/);
    const retained = tool('a');
    await lifecycle.dispose();
    await assert.rejects(retained.execute('retired', {}), /no longer current/);
  });
