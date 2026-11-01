/** Pin the actually loaded immutable UI snapshot for this native process lifetime. */
import { execFile } from 'node:child_process';
import { createHash } from 'node:crypto';
import { constants } from 'node:fs';
import { lstat, open, readFile, realpath, unlink } from 'node:fs/promises';
import { basename, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

export async function holdComponent(profile, component = 'opencode-tui') {
  const root = await realpath(fileURLToPath(new URL('../../', import.meta.url)));
  if (!/^[0-9a-f]{12}$/.test(basename(root)) || basename(dirname(root)) !== 'runtime') return async () => {};
  // The loaded snapshot owns the lease location, even if the caller changed XSM_HOME.
  const state = dirname(dirname(root));
  const home = await realpath(profile);
  const key = createHash('sha256').update('opencode\0' + home).digest('hex');
  const source = await open(join(state, 'host-installations', key + '.json'),
    constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  let manifest;
  try {
    const info = await source.stat();
    if (!info.isFile() || info.uid !== process.getuid() || (info.mode & 0o077) || info.size > 65536) {
      throw new Error('native UI interpreter record is not private');
    }
    manifest = JSON.parse(await source.readFile('utf8'));
  } finally { await source.close(); }
  if (manifest.bindingInstall !== 1 || !['prepared', 'installed'].includes(manifest.phase) ||
      manifest.runtime !== 'opencode' || manifest.home !== home || typeof manifest.python !== 'string') {
    throw new Error('native UI installation has no pinned interpreter');
  }
  const python = process.env.XSM_PYTHON || manifest.python;
  const code = "import sys,json;sys.path.insert(0,sys.argv[1]);from xsm.component_leases import hold;print(json.dumps(hold(sys.argv[2],int(sys.argv[3]))))";
  const { stdout } = await promisify(execFile)(python, ['-B', '-c', code, root, component, String(process.pid)],
    { timeout: 10000, env: { ...process.env, XSM_HOME: state } });
  const lease = JSON.parse(stdout);
  if (!/^[0-9a-f]{32}$/.test(lease.id) || lease.root !== root || lease.pid !== process.pid || lease.component !== component) {
    throw new Error('native UI component lease identity differs');
  }
  const name = join(state, 'component-leases', lease.id + '.json');
  const bytes = await readFile(name, 'utf8');
  const original = await lstat(name);
  return async () => {
    try {
      const current = await lstat(name);
      if (!current.isFile() || current.ino !== original.ino || current.dev !== original.dev) return;
      const file = await open(name, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
      try {
        const observed = await file.stat();
        const content = await file.readFile('utf8');
        const latest = await lstat(name);
        if (observed.ino === original.ino && observed.dev === original.dev &&
            latest.ino === original.ino && latest.dev === original.dev && content === bytes) {
          await unlink(name);
        }
      } finally { await file.close(); }
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
  };
}
