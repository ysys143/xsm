/** Actual Pi SDK wake/ACK path; scripted stream, no network or credentials. */
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtemp, mkdir, readFile, readdir, writeFile, appendFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { XsmClient } from '../clients/typescript/xsm-client.mjs';

const [packageRoot, outputArg, countArg = '2', mutant] = process.argv.slice(2);
const count = Number(countArg);
assert.ok(packageRoot && outputArg && Number.isInteger(count) && count > 0 && count <= 100);
assert.ok(!mutant || mutant === '--missing-native-observation');
const output = resolve(outputArg), root = fileURLToPath(new URL('../', import.meta.url));
await mkdir(output, { recursive: true });
const temp = await mkdtemp(join(tmpdir(), 'xsm-pi-latency-'));
for (const key of Object.keys(process.env)) if (!['PATH', 'LANG', 'TMPDIR', 'XSM_PYTHON'].includes(key)) delete process.env[key];
const python = process.env.XSM_PYTHON ?? 'python3';
Object.assign(process.env, { HOME: join(temp, 'home'), PI_CODING_AGENT_DIR: join(temp, 'pi'),
  XSM_HOME: join(temp, 'state'), PYTHONDONTWRITEBYTECODE: '1' });
const project = join(temp, 'project'); await mkdir(project);
execFileSync('git', ['init', '-q', project]);
const result = { status: 'running', root: temp, requested: count, samples: [], realModelCalls: 0,
  scope: 'Pi SDK actual idle wake, native agent state acceptance, scripted native ACK; not CLI/UI/real model',
  mutant: mutant ?? null, clockBrackets: [], scriptedResponses: 0 };
const checkpoint = () => writeFile(join(output, 'result.json'), JSON.stringify(result, null, 2) + '\n');
const pause = () => new Promise(resolve => setTimeout(resolve, 10));
async function until(predicate, description) {
  const deadline = Date.now() + 15000;
  while (!await predicate()) { assert.ok(Date.now() < deadline, description); await pause(); }
}
let session, sender;
try {
  const clock = process.platform === 'darwin' ? 'CLOCK_MONOTONIC_RAW' : 'CLOCK_MONOTONIC';
  const tick = () => BigInt(execFileSync(python, ['-c', `import time;print(time.clock_gettime_ns(time.${clock}))`], { encoding: 'utf8' }).trim());
  for (let i = 0; i < 5; i++) {
    const before = tick(), node = process.hrtime.bigint(), after = tick();
    assert.ok(before <= node && node <= after, 'Python/Node clock domains differ');
    result.clockBrackets.push({ before: String(before), node: String(node), after: String(after) });
  }
  const sdk = await import(pathToFileURL(join(packageRoot, 'dist/index.js')));
  assert.equal(sdk.VERSION, '1.4.0'); result.runtimeVersion = sdk.VERSION;
  const settings = sdk.SettingsManager.inMemory({ compaction: { enabled: false }, retry: { enabled: false } });
  const loader = new sdk.DefaultResourceLoader({ cwd: project, agentDir: process.env.PI_CODING_AGENT_DIR,
    settingsManager: settings, additionalExtensionPaths: [join(root, 'integrations/pi/xsm.mjs')],
    noSkills: true, noPromptTemplates: true, noThemes: true, noContextFiles: true });
  await loader.reload();
  ({ session } = await sdk.createAgentSession({ cwd: project, agentDir: process.env.PI_CODING_AGENT_DIR,
    settingsManager: settings, sessionManager: sdk.SessionManager.inMemory(), resourceLoader: loader }));
  const queued = [];
  const original = session.agent.processEvents.bind(session.agent);
  session.agent.processEvents = async event => {
    await original(event);
    if (event.type === 'message_end' && event.message.customType === 'xsm') {
      const end = process.hrtime.bigint();
      assert.ok(session.agent.state.messages.includes(event.message), 'native agent did not accept the message');
      const entry = session.sessionManager.getBranch().find(e => e.type === 'custom_message' &&
        e.details?.xsmDelivery === event.message.details?.xsmDelivery);
      assert.ok(entry, 'native session branch did not commit the accepted message');
      if (!mutant) for (const id of event.message.details.messages) {
        const row = { id, queuedMonotonicNs: String(end), nativeItemId: entry.id,
          nativeSessionId: session.sessionManager.getSessionId() };
        queued.push(row); await appendFile(join(output, 'queued.jsonl'), JSON.stringify(row) + '\n');
      }
    }
  };
  session.agent.getApiKey = async () => undefined;
  let serial = 0;
  session.agent.streamFunction = async (_model, context) => {
    result.scriptedResponses++;
    const last = context.messages.at(-1);
    const text = JSON.stringify(context.messages);
    const match = [...text.matchAll(/xsm_ack with tokens: (\[[^\n]*?\])/g)].at(-1);
    const content = last?.role === 'toolResult' ? [{ type: 'text', text: 'scripted ACK completed' }]
      : [{ type: 'toolCall', id: 'latency-ack-' + serial++, name: 'xsm_ack',
        arguments: { tokens: match ? JSON.parse(match[1].replaceAll('\\"', '"')) : [] } }];
    const message = { role: 'assistant', content, api: 'unknown', provider: 'unknown', model: 'offline-fixture',
      stopReason: last?.role === 'toolResult' ? 'stop' : 'toolUse', timestamp: Date.now(),
      usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } } };
    return { async *[Symbol.asyncIterator]() {}, result: async () => message };
  };
  await session.bindExtensions({ mode: 'rpc', uiContext: { notify(message) { (result.notifications ??= []).push(String(message)); }, setStatus() {} } });
  const records = async () => Promise.all((await readdir(join(process.env.XSM_HOME, 'sessions')))
    .filter(n => n.endsWith('.json')).map(async n => JSON.parse(await readFile(join(process.env.XSM_HOME, 'sessions', n), 'utf8'))));
  const receiver = (await records()).find(r => r.runtime === 'pi'); assert.ok(receiver);
  sender = await XsmClient.connect({ command: [python, '-B', join(root, 'tests/fixtures/protocol_timed_host.py'),
    join(output, 'stored.jsonl'), clock], cwd: project, env: process.env });
  const origin = await sender.sessionOpen({ runtime: 'latency-probe', profile: temp, conversation: 'sender', cwd: project });
  for (let i = 0; i < count; i++) {
    const id = 'latency-pi-' + i;
    const sample = { id, index: i, status: 'starting' }; result.samples.push(sample); await checkpoint();
    await until(async () => (await records()).some(r => r.ref === receiver.ref && r.activity === 'idle'), 'native idle before send');
    await sender.operationCall(origin.session, 'xsm_send', { target: 'ref:' + receiver.ref, text: id, request_id: id, wake: 'auto' });
    const buckets = await readdir(join(process.env.XSM_HOME, 'handoffs'));
    let path;
    for (const bucket of buckets) {
      const candidate = join(process.env.XSM_HOME, 'handoffs', bucket, id + '.json');
      try { await readFile(candidate); assert.ok(!path, 'duplicate canonical handoff'); path = candidate; }
      catch (e) { if (e.code !== 'ENOENT' && e.code !== 'ENOTDIR') throw e; }
    }
    assert.ok(path, 'canonical handoff exists');
    let stored;
    await until(async () => {
      try { stored = JSON.parse(await readFile(path, 'utf8')); return stored.state === 'acknowledged' &&
        (await records()).some(r => r.ref === receiver.ref && r.activity === 'idle'); } catch (e) { if (e.code === 'ENOENT') return false; throw e; }
    }, 'native scripted ACK and idle');
    const starts = (await readFile(join(output, 'stored.jsonl'), 'utf8')).trim().split('\n').map(JSON.parse).filter(r => r.id === id);
    const ends = queued.filter(r => r.id === id);
    assert.equal(starts.length, 1, 'exact canonical store observation');
    assert.equal(ends.length, 1, 'exact native acceptance observation');
    const elapsed = Number(BigInt(ends[0].queuedMonotonicNs) - BigInt(starts[0].storedMonotonicNs)) / 1e6;
    assert.ok(elapsed >= 0); Object.assign(sample, { status: 'passed', milliseconds: elapsed, nativeItemId: ends[0].nativeItemId, acknowledged: true });
    await checkpoint();
  }
  const values = result.samples.map(s => s.milliseconds).sort((a, b) => a - b);
  result.p95Milliseconds = values[Math.ceil(values.length * .95) - 1];
  result.maxMilliseconds = values.at(-1); assert.ok(result.p95Milliseconds <= 1000);
  result.status = 'passed';
} catch (error) { result.status = 'failed'; result.error = { message: error.message, stack: error.stack }; }
finally {
  await sender?.close();
  if (session) { await session.extensionRunner.emit({ type: 'session_shutdown', reason: 'quit' }); session.dispose(); }
  result.completed = result.samples.filter(s => s.status === 'passed').length;
  result.failed = result.samples.length - result.completed; result.unexecuted = count - result.samples.length;
  await checkpoint(); console.log(JSON.stringify({ status: result.status, completed: result.completed, error: result.error?.message }));
}
if (result.status !== 'passed') process.exitCode = 1;
