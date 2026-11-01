/** Real local stdio server, with environment isolation before Python imports. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, mkdir, readFile, readdir, realpath, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, relative, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';
import { XsmClient, RpcError } from '../typescript/xsm-client.mjs';

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
