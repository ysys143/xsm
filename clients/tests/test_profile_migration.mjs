import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { XsmHostClient, RpcError } from '../typescript/xsm-client.mjs';

test('profile migration works through Node SDK without runtime-specific adapters', { timeout: 20000 }, async () => {
  const root = fileURLToPath(new URL('../../', import.meta.url));
  const temp = await mkdtemp(join(tmpdir(), 'xsm-node-profile-migration-'));
  let client;
  try {
    client = await XsmHostClient.connect({
      command: [process.env.PYTHON ?? 'python3', '-B', '-m', 'xsm', 'protocol', 'serve', '--stdio'],
      cwd: root,
      env: { PATH: process.env.PATH ?? '/usr/bin:/bin', HOME: temp, XSM_HOME: join(temp, 'state'),
        PYTHONDONTWRITEBYTECODE: '1' },
    });
    const a = await client.sessionOpen({ runtime: 'node-migration', profile: 'a', conversation: 'copy',
      cwd: temp, capabilities: ['user-decisions'] });
    const b = await client.sessionOpen({ runtime: 'node-migration', profile: 'b', conversation: 'copy',
      cwd: temp, capabilities: ['user-decisions'] });
    const args = { source: a.address };
    const pending = await client.operationCall(b.session, 'xsm_migrate', args);
    assert.equal(pending.status, 'waiting-for-user');
    const event = await client.nextNotification();
    assert.equal(event.method, 'decision/request');
    await client.respondToDecision(event, {
      displayed: event.params.question, sourceId: 'node-migration-user', answer: 'allow',
    });
    const result = await client.operationCall(b.session, 'xsm_migrate', args);
    assert.equal(result.status, 'committed');
    assert.equal(result.forward_until - result.committed_at, 86400);
    const again = await client.operationCall(b.session, 'xsm_migrate', args);
    assert.equal(again.id, result.id);
    assert.equal(again.committed_at, result.committed_at);
    await assert.rejects(client.operationCall(a.session, 'xsm_inbox', {}), error => error instanceof RpcError);
    const history = await client.operationCall(b.session, 'xsm_migrate', {});
    assert.equal(history.migrations[0].id, result.id);
    assert.equal(history.current_owner, b.address);
  } finally {
    if (client) await client.close();
    await rm(temp, { recursive: true, force: true });
  }
});
