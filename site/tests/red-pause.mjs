import { mkdtemp, mkdir, copyFile, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve, join } from 'node:path';
import { spawnSync } from 'node:child_process';
import assert from 'node:assert/strict';

// Mutate only an isolated copy, and prove that the pause assertions reject it.
const supplied = process.argv[2];
const directory = supplied ? resolve(supplied) : await mkdtemp(join(tmpdir(), 'xsm-demo-red-'));
const site = join(directory, 'site');
assert.notEqual(site, resolve('site'), 'The working source must never be mutated.');
try {
  if (!supplied) {
    await mkdir(join(site, 'tests'), { recursive: true });
    for (const path of ['player.mjs', 'content.mjs', 'tests/player.test.mjs']) await copyFile(new URL(`../${path}`, import.meta.url), join(site, path));
  }
  const path = join(site, 'player.mjs');
  const source = await readFile(path, 'utf8');
  assert.equal(source.split('player.paused || ').length, 2, 'Expected exactly one pause guard.');
  await writeFile(path, source.replace('player.paused || ', ''));
  const result = spawnSync(process.execPath, ['--test', join(site, 'tests/player.test.mjs')], { encoding: 'utf8', timeout: 10000 });
  assert.equal(result.status, 1, 'Removing pause must fail the tests.');
  assert.match(result.stdout, /a paused show stays at the same moment/);
  assert.match(result.stdout + result.stderr, /AssertionError|ERR_ASSERTION/);
  console.log('Pause regression deliberately introduced in an isolated copy: caught.');
  console.log(result.stdout);
} finally {
  if (!supplied) await rm(directory, { recursive: true, force: true });
}
