/** One native backend RPC; native SDK owns profile, auth and transport policy. */
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { dirname, isAbsolute, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseWireJson } from '../../clients/typescript/json-wire.mjs';

const methods = new Set(['health', 'sessions.create', 'sessions.resolve', 'sessions.list', 'agent', 'agent.wait']);

export async function nativeRpc(nativeCli, request) {
  if (typeof nativeCli !== 'string' || !isAbsolute(nativeCli)) throw new Error('absolute native CLI required');
  if (!request || typeof request !== 'object' || Array.isArray(request)
      || Object.keys(request).sort().join(',') !== 'method,params'
      || !methods.has(request.method) || !request.params || typeof request.params !== 'object'
      || Array.isArray(request.params)) throw new Error('invalid native RPC request');
  const info = JSON.parse(await readFile(join(dirname(nativeCli), 'package.json'), 'utf8'));
  if (info.name !== 'openclaw' || info.version !== '2026.10.9') throw new Error('pinned native package required');
  const require = createRequire(nativeCli);
  const sdk = await import(pathToFileURL(require.resolve('openclaw/plugin-sdk/gateway-runtime')).href);
  return sdk.callGatewayFromCli(request.method, { json: true, timeout: '40000' }, request.params,
    { mode: 'backend', clientName: 'gateway-client', progress: false, scopes: ['operator.admin'] });
}

async function main() {
  try {
    if (process.argv.length !== 3) throw new Error('native CLI required');
    const chunks = [];
    let size = 0;
    for await (const chunk of process.stdin) {
      size += chunk.length;
      if (size > 4 * 1024 * 1024) throw new Error('native RPC input too large');
      chunks.push(chunk);
    }
    const input = new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(chunks));
    const result = await nativeRpc(process.argv[2], parseWireJson(input));
    process.stdout.write(JSON.stringify(result) + '\n');
  } catch (error) {
    // Native errors can contain credentials or profile contents. Export only
    // the specific lifecycle refusal fact needed by the model-free probe.
    process.stderr.write(JSON.stringify({ nativeError: true,
      operatorExecRefused: /from agent exec would lose inter-session attribution/.test(String(error?.message)),
      expectedSessionChanged: /changed (while starting expected work|before expected work could start)/
        .test(String(error?.message)) }) + '\n');
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
