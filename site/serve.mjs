import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { resolve, extname, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = fileURLToPath(new URL('.', import.meta.url));
const types = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.png': 'image/png', '.md': 'text/plain; charset=utf-8' };

export function createSiteServer(directory = root) {
  const base = resolve(directory);
  return createServer(async (request, response) => {
    try {
      const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
      let path = resolve(base, `.${pathname}`);
      if (path !== base && !path.startsWith(base + sep)) {
        response.writeHead(403).end('Forbidden'); return;
      }
      if ((await stat(path)).isDirectory()) path = resolve(path, 'index.html');
      const body = await readFile(path);
      response.writeHead(200, { 'Content-Type': types[extname(path)] ?? 'application/octet-stream', 'Cache-Control': 'no-store' });
      response.end(request.method === 'HEAD' ? undefined : body);
    } catch (error) {
      response.writeHead(error.code === 'ENOENT' ? 404 : 400).end('Not found');
    }
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const port = Number(process.argv[2] ?? 0);
  if (!Number.isInteger(port) || port < 0 || port > 65535) throw new Error('Port must be between 0 and 65535.');
  const server = createSiteServer();
  server.listen(port, '127.0.0.1', () => console.log(`XSM demo: http://127.0.0.1:${server.address().port}/`));
  for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.close(() => process.exit(0)));
}
