/** Real local stdio server, with environment isolation before Python imports. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, mkdir, readFile, readdir, realpath, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, relative, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';
import { XsmClient, RpcError } from '../typescript/xsm-client.mjs';
import { createHash } from 'node:crypto';

test('chunk preparation resumes exact bytes and never sends the body implicitly', { timeout: 30000 }, async () => {
  const root = await realpath(fileURLToPath(new URL('../../', import.meta.url)));
  const temp = await mkdtemp(join(tmpdir(), 'xsm-node-upload-'));
  let client;
  try {
    client = await XsmClient.connect({ command: [process.env.PYTHON ?? 'python3', '-B', '-m', 'xsm', 'protocol', 'serve', '--stdio'],
      cwd: root, env: { PATH: process.env.PATH ?? '/usr/bin:/bin', HOME: temp, XSM_HOME: join(temp, 'state'), PYTHONDONTWRITEBYTECODE: '1' } });
    const a = await client.sessionOpen({ runtime: 'upload-fixture', profile: 'private', conversation: 'a', cwd: temp });
    const b = await client.sessionOpen({ runtime: 'upload-fixture', profile: 'private', conversation: 'b', cwd: temp });
    await client.operationCall(b.session, 'xsm_inbox', {});
    const data = Buffer.alloc(1048576, 255);
    const params = { session: a.session, target: b.address, request_id: 'node-upload', text: 'exact binary',
      entries: [{ name: 'binary.bin', size: data.length, sha256: createHash('sha256').update(data).digest('hex') }] };
    const opened = await client.request('files.upload.open', params);
    await client.request('files.upload.write', { session: a.session, upload: opened.upload, entry: 0, offset: 0,
      base64: data.subarray(0, 13).toString('base64') });
    const prepared = await client.prepareFiles(a.session, { target: b.address, request_id: 'node-upload', text: 'exact binary',
      entries: [{ name: 'binary.bin', data }] });
    assert.equal(prepared.body_sent, false);
    assert.deepEqual((await client.operationCall(b.session, 'xsm_inbox', {})).items, []);
    const replay = await client.prepareFiles(a.session, { target: b.address, request_id: 'node-upload', text: 'exact binary',
      entries: [{ name: 'binary.bin', data }] });
    assert.equal(replay.manifest_id, prepared.manifest_id);
    await client.operationCall(a.session, 'xsm_send', { target: b.address, request_id: 'node-upload', text: 'exact binary',
      manifest_id: prepared.manifest_id, wake: 'never', wait: 0 });
    const pack = await client.operationCall(b.session, 'xsm_inbox', {});
    const copy = pack.items[0].files;
    const read = await client.operationCall(b.session, 'xsm_files', {
      storage_id: copy.storage_id, entry_id: copy.files[0].id, encoding: 'base64' });
    assert.deepEqual(Buffer.from(read.content, 'base64'), data);
    const canonical = await client.operationCall(b.session, 'xsm_files', { storage_id: copy.storage_id, manifest_bytes: true });
    assert.equal(createHash('sha256').update(Buffer.from(canonical.content, 'base64')).digest('hex'), copy.sha256);
    assert.equal((await client.operationCall(b.session, 'xsm_ack', { tokens: pack.claims.map(c => c.token) })).acked[0], 'node-upload');
  } finally { await client?.close(); await rm(temp, { recursive: true, force: true }); }
});

test('real server: two sessions in same repo, wait=0 send, notification, inbox and ack',
  { timeout: 30000 }, async () => {
    const root = await realpath(fileURLToPath(new URL('../../', import.meta.url)));
    const temp = await mkdtemp(join(tmpdir(), 'xsm-node-interop-'));
    const home = join(temp, 'home'), state = join(temp, 'state');
    let client;
    try {
      await mkdir(home);
      await mkdir(state);
      // No inherited XSM policy, native identities, configuration, or credentials.
      client = await XsmClient.connect({
        command: [process.env.PYTHON ?? 'python3', '-m', 'xsm', 'protocol', 'serve', '--stdio'],
        cwd: root,
        env: { PATH: process.env.PATH ?? '/usr/bin:/bin', HOME: home, XSM_HOME: state,
          PYTHONPATH: root, PYTHONDONTWRITEBYTECODE: '1', PYTHONUNBUFFERED: '1' },
      });
      assert.equal(client.initialization.protocolVersion, '1');
      const [a, b] = await Promise.all(['sender', 'receiver'].map(conversation =>
        client.sessionOpen({ runtime: 'node-interop', profile: 'isolated', conversation, cwd: root, capabilities: [] })));
      assert.notEqual(a.session, b.session);
      assert.notEqual(a.ref, b.ref);
      const records = await Promise.all((await readdir(join(state, 'sessions')))
        .filter(name => name.endsWith('.json')).map(async name =>
          JSON.parse(await readFile(join(state, 'sessions', name), 'utf8'))));
      assert.equal(records.length, 2);
      for (const record of records) {
        assert.equal(record.cwd, root);
        const inside = relative(state, record.home);
        assert.ok(!inside.startsWith('..') && !isAbsolute(inside));
      }
      assert.deepEqual(await client.sessionUpdate(a.session, { state: 'busy' }), { state: 'busy' });
      await assert.rejects(client.sessionUpdate(a.session, { cwd: home }),
        error => error instanceof RpcError && error.code === -32602);
      await client.eventsSubscribe(b.session);
      const sent = await client.operationCall(a.session, 'xsm_send', {
        target: 'ref:' + b.ref, text: '실제 Node 전송', wait: 0,
      });
      assert.match(JSON.stringify(sent), /stored/);
      const event = await client.nextNotification();
      assert.equal(event.method, 'events/available');
      assert.equal(event.params.session, b.session);
      assert.equal(event.params.ids.length, 1);
      const mid = event.params.ids[0];
      const originals = [];
      for (const folder of await readdir(join(state, 'handoffs'))) {
        if ((await readdir(join(state, 'handoffs', folder))).includes(mid + '.json')) {
          originals.push(join(state, 'handoffs', folder, mid + '.json'));
        }
      }
      assert.equal(originals.length, 1);
      const original = async () => JSON.parse(await readFile(originals[0], 'utf8'));
      for (const deliveryState of ['queued', 'refused', 'unknown']) {
        assert.deepEqual(await client.deliveryReport(b.session, mid, deliveryState),
          { recorded: deliveryState, acknowledged: false });
        assert.equal((await original()).state, 'pending');
      }
      await assert.rejects(client.deliveryReport(b.session, mid, 'received'),
        error => error instanceof RpcError && error.code === -32602);
      const pack = await client.operationCall(b.session, 'xsm_inbox', { wait: 0 });
      assert.match(JSON.stringify(pack.messages), /실제 Node 전송/);
      assert.equal(pack.claims.length, 1);
      assert.equal(pack.claims[0].id, mid);
      assert.notEqual((await original()).state, 'acknowledged');
      const ack = await client.operationCall(b.session, 'xsm_ack', { tokens: [pack.claims[0].token] });
      assert.deepEqual(ack.acked, [mid]);
      assert.equal(ack.inbox_pending, 0);
      assert.equal((await original()).state, 'acknowledged');
      const empty = await client.operationCall(b.session, 'xsm_inbox', { wait: 0 });
      assert.deepEqual(empty.messages, []);
      assert.deepEqual(empty.claims, []);
      for (const opened of [a, b]) assert.deepEqual(await client.sessionClose(opened.session), { closed: true });
      await client.close();
      assert.equal(client.process.exitCode, 0);
    } finally {
      if (client) await client.close();
      await rm(temp, { recursive: true, force: true });
    }
  });

test('internal RPC error preserves the current claim and connection', { timeout: 10000 }, async () => {
  const root = await realpath(fileURLToPath(new URL('../../', import.meta.url)));
  const temp = await mkdtemp(join(tmpdir(), 'xsm-node-internal-error-'));
  const diagnostics = [];
  let client;
  try {
    client = await XsmClient.connect({ command: [process.env.PYTHON ?? 'python3', '-B',
      join(root, 'tests/fixtures/protocol_internal_fault.py')], cwd: root,
      env: { PATH: process.env.PATH, HOME: temp, XSM_HOME: join(temp, 'state'),
        PYTHONPATH: root, PYTHONDONTWRITEBYTECODE: '1' }, onStderr: text => diagnostics.push(text) });
    const [a, b] = await Promise.all(['a', 'b'].map(conversation => client.sessionOpen({
      runtime: 'node-error', profile: 'fixture', conversation, cwd: root, capabilities: ['messaging', 'inbox', 'events'] })));
    await client.eventsSubscribe(b.session);
    await client.operationCall(a.session, 'xsm_send', { target: 'ref:' + b.ref, text: 'retain after internal error', wait: 0 });
    const event = await client.nextNotification();
    await assert.rejects(client.operationCall(b.session, 'xsm_inbox', {}), error =>
      error instanceof RpcError && error.code === -32603 && error.message === 'internal server error');
    const pack = await client.operationCall(b.session, 'xsm_inbox', { message_ids: event.params.ids });
    assert.deepEqual(pack.claims.map(claim => claim.id), event.params.ids);
    const ack = await client.operationCall(b.session, 'xsm_ack', { tokens: pack.claims.map(claim => claim.token) });
    assert.deepEqual(ack.acked, event.params.ids);
    assert.deepEqual(await client.sessionUpdate(b.session, { state: 'idle' }), { state: 'idle' });
  } finally { if (client) await client.close(); await rm(temp, { recursive: true, force: true }); }
  assert.ok(!diagnostics.join('').includes('private-post-claim-fixture'));
  assert.ok(!diagnostics.join('').includes('Traceback'));
});
