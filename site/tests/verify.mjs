import { createHash } from 'node:crypto';
import { readdir, readFile, mkdir, writeFile } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';
import { once } from 'node:events';
import assert from 'node:assert/strict';
import { createSiteServer } from '../serve.mjs';

const root = fileURLToPath(new URL('../../', import.meta.url));
const arguments_ = process.argv.slice(2);
const option = (name, fallback) => arguments_[arguments_.indexOf(name) + 1] ?? fallback;
const space = arguments_.includes('--space') ? Number(option('--space')) : null;
const output = resolve(root, arguments_.includes('--output') ? option('--output') : 'deliverables/xsm-demo-web-20261105/verified');
assert.ok(Number.isInteger(space) && space > 0, 'Use --space <owned ego-browser space ID>.');
await mkdir(output, { recursive: true });

async function inputs() {
  const result = {};
  async function walk(directory) {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) await walk(path);
      else if (/\.(mjs|html|css|svg|woff2)$/.test(entry.name)) {
        result[path.slice(root.length).replaceAll('\\', '/')] = createHash('sha256').update(await readFile(path)).digest('hex');
      }
    }
  }
  await walk(join(root, 'site'));
  return result;
}

const before = await inputs();
const unit = spawnSync(process.execPath, ['--test', 'site/tests/player.test.mjs', 'site/tests/site.test.mjs', 'site/tests/i18n.test.mjs'], { cwd: root, encoding: 'utf8', timeout: 10000 });
await writeFile(join(output, 'unit.txt'), unit.stdout + unit.stderr);
process.stdout.write(unit.stdout + unit.stderr);
assert.equal(unit.status, 0, 'Node checks failed.');
const server = createSiteServer();
const [staticHandler] = server.listeners('request');
server.removeAllListeners('request');
server.on('request', (request, response) => {
  const url = new URL(request.url, 'http://localhost');
  if (url.pathname === '/__viewport') {
    const width = Number(url.searchParams.get('width'));
    assert.ok([320, 390, 900, 1440].includes(width));
    response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    response.end(`<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><title>Responsive test viewport</title><style>html,body{margin:0;width:${width}px}iframe{display:block;width:${width}px;height:844px;border:0}</style></head><body><iframe id="responsive-frame" title="XSM responsive viewport" src="/index.html#demo/progress"></iframe></body></html>`);
  } else void staticHandler(request, response);
});
server.listen(0, '127.0.0.1');
await once(server, 'listening');
const baseURL = `http://127.0.0.1:${server.address().port}/`;
try {
  const moduleURL = pathToFileURL(join(root, 'site/tests/browser.mjs')).href;
  const localeModuleURL = pathToFileURL(join(root, 'site/tests/i18n-browser.mjs')).href;
  const options = JSON.stringify({ spaceId: space, baseURL, outputDirectory: output });
  const script = `await (await import(${JSON.stringify(moduleURL)})).run(${options}); await (await import(${JSON.stringify(localeModuleURL)})).run(${options});`;
  // Async spawn keeps the local server responsive while the browser checks run.
  const { spawn } = await import('node:child_process');
  const child = spawn('ego-browser', ['nodejs', '-e', script], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
  let stdout = '', stderr = '';
  child.stdout.on('data', chunk => { stdout += chunk; process.stdout.write(chunk); });
  child.stderr.on('data', chunk => { stderr += chunk; process.stderr.write(chunk); });
  const timeout = setTimeout(() => child.kill('SIGTERM'), 90000);
  let code;
  try { [code] = await once(child, 'close'); } finally { clearTimeout(timeout); }
  await writeFile(join(output, 'browser-tool.txt'), stdout + stderr);
  assert.equal(code, 0, 'Browser checks failed; inspect the preserved failure report.');
  assert.deepEqual(await inputs(), before, 'Inputs changed during verification.');
  const browser = JSON.parse(await readFile(join(output, 'browser.json'), 'utf8'));
  const localized = JSON.parse(await readFile(join(output, 'i18n-browser.json'), 'utf8'));
  const browserChecks = browser.passed + localized.passed;
  await writeFile(join(output, 'verified-inputs.json'), JSON.stringify({ inputs: before, node: process.version, browserChecks, result: 'passed' }, null, 2) + '\n');
  console.log(`Verified: Node checks and ${browserChecks} real-browser checks.`);
} finally {
  server.closeAllConnections();
  await new Promise(resolve => server.close(resolve));
}
