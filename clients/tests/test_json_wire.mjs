import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseWireJson } from '../typescript/json-wire.mjs';
import { XsmClient, TransportError } from '../typescript/xsm-client.mjs';

test('wire JSON preserves values and independent object keys', () => {
  const value = { a: [{ x: 'quote " brace } and backslash \\' }, { x: 2 }], n: null, b: true };
  assert.deepEqual(parseWireJson(JSON.stringify(value)), value);
});

test('duplicate and escaped-equivalent object members are refused at every level', () => {
  for (const value of ['{"a":1,"a":2}', '{"a":1,"\\u0061":2}', '{"a":[{"b":1,"b":2}]}']) {
    assert.throws(() => parseWireJson(value), /duplicate JSON member/);
  }
  for (const value of ['{"a":NaN}', '[] trailing', '{"a":1,}']) assert.throws(() => parseWireJson(value), SyntaxError);
});

test('SDK rejects a duplicate version supplied by an actual peer', async () => {
  const code = String.raw`process.stdin.once('data', line => {
    const frame=JSON.parse(line);
    const response=JSON.stringify({jsonrpc:'2.0',id:frame.id,result:{protocolVersion:'1'}});
    process.stdout.write(response.replace('"protocolVersion":"1"','"protocolVersion":"bad","protocolVersion":"1"')+String.fromCharCode(10));
  });`;
  await assert.rejects(async () => {
    const client = await XsmClient.connect({ command: [process.execPath, '-e', code], closeTimeout: 100,
      initializeTimeout: 2000, onStderr: () => {} });
    await client.close();
  }, { name: 'TransportError', message: /duplicate JSON member/ });
});
