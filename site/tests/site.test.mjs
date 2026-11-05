import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile, access } from 'node:fs/promises';
import { once } from 'node:events';
import { scenes, topics, repository } from '../content.mjs';
import { createSiteServer } from '../serve.mjs';

test('all documentation topics map to scenes and existing source references', async () => {
  assert.equal(topics.length, 8);
  for (const topic of topics) {
    assert.ok(scenes[topic.scene], topic.id);
    assert.ok(topic.sections.length >= 2, topic.id);
    for (const section of topic.sections) {
      assert.ok(section.paragraphs.every(paragraph => paragraph.length > 20), topic.id);
      if (section.link) assert.ok(topics.some(target => target.id === section.link[0]));
    }
    for (const [, reference] of topic.references) {
      const path = reference.replace(`${repository}/blob/main/`, '');
      assert.notEqual(path, reference);
      await access(new URL(`../../${path}`, import.meta.url));
    }
  }
});

test('the static page and stylesheet only refer to packaged local assets', async () => {
  const html = await readFile(new URL('../index.html', import.meta.url), 'utf8');
  const css = await readFile(new URL('../styles.css', import.meta.url), 'utf8');
  for (const match of html.matchAll(/(?:src|href)="(\.\/[^"#]+)"/g)) await access(new URL(`../${match[1]}`, import.meta.url));
  for (const match of css.matchAll(/url\('([^']+)'\)/g)) await access(new URL(`../${match[1]}`, import.meta.url));
  assert.match(html, /All you need is/);
  assert.match(html, /OpenClaw/);
  assert.ok(!html.includes('hero-aside'));
});

test('the local server serves real HTML, JavaScript and fonts with usable MIME types', async () => {
  const server = createSiteServer();
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  try {
    const base = `http://127.0.0.1:${server.address().port}`;
    for (const [path, type] of [['/', 'text/html'], ['/app.mjs', 'text/javascript'], ['/assets/archivo-latin.woff2', 'font/woff2']]) {
      const response = await fetch(base + path);
      assert.equal(response.status, 200, path);
      assert.ok(response.headers.get('content-type').startsWith(type), path);
      assert.ok((await response.arrayBuffer()).byteLength > 0, path);
    }
    assert.equal((await fetch(base + '/missing-file')).status, 404);
  } finally {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
});
