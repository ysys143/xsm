/** OpenClaw 2026.10.9 direct-turn tools. Native push/UI and v2 continuations remain open. */
import { realpath } from 'node:fs/promises';
import { dirname, isAbsolute, resolve } from 'node:path';
import { XsmHost } from '../../clients/typescript/xsm-host.mjs';
import operations from './tools.mjs';

export function register(api, options = {}) {
  // Native capture relocates imported JS without copying bin/xsm. The host's
  // original entry is authoritative; installed loaders pass their pinned command.
  if (!options.command && (typeof api.source !== 'string' || !isAbsolute(api.source))) {
    throw new Error('OpenClaw original plugin source must be absolute');
  }
  const command = options.command ?? [resolve(dirname(api.source), '../../bin/xsm'), 'protocol', 'serve', '--stdio'];
  const profilePath = api.runtime.state.resolveStateDir();
  if (typeof profilePath !== 'string' || !isAbsolute(profilePath)) {
    throw new Error('OpenClaw state directory must be native and absolute');
  }
  const sessions = new Map();
  const observeTurns = api.config?.plugins?.entries?.xsm?.hooks?.allowConversationAccess === true;
  let disposed = false;
  const fail = error => api.logger.error('xsm: ' + error.message);

  function state(context) {
    const { sessionId: id, sessionKey: route, workspaceDir: cwd } = context;
    if (!id || !route || typeof cwd !== 'string' || !isAbsolute(cwd)) return undefined;
    if (!sessions.has(id)) sessions.set(id, { id, route, cwd, epoch: 0, closing: Promise.resolve() });
    const entry = sessions.get(id);
    if (entry.route !== route || entry.cwd !== cwd) {
      throw new Error('native conversation route or workspace changed; end previous participation first');
    }
    return entry;
  }

  function current(entry, epoch, context, signal) {
    if (disposed || epoch !== entry.epoch || signal?.aborted) {
      throw new Error('xsm native invocation is no longer current');
    }
    context.assertInvocationCurrent?.();
  }

  async function open(entry, epoch, context, signal) {
    await entry.closing;
    current(entry, epoch, context, signal);
    if (!entry.pending) {
      const pending = (async () => {
        const [profile, cwd] = await Promise.all([realpath(profilePath), realpath(entry.cwd)]);
        current(entry, epoch, context, signal);
        return XsmHost.open({ command, env: options.env, runtime: 'openclaw',
          profile, conversation: entry.id, cwd, onError: fail });
      })();
      entry.pending = pending;
      pending.catch(() => { if (entry.pending === pending) entry.pending = undefined; });
    }
    const host = await entry.pending;
    current(entry, epoch, context, signal);
    return host;
  }

  async function end(entry) {
    entry.epoch++;
    const pending = entry.pending;
    entry.pending = undefined;
    entry.closing = entry.closing.then(async () => {
      if (pending) {
        const host = await pending.catch(() => undefined);
        if (host) await host.close();
      }
    });
    await entry.closing;
  }

  async function close() {
    disposed = true;
    const results = await Promise.allSettled([...sessions.values()].map(end));
    const failed = results.find(result => result.status === 'rejected');
    if (failed) throw failed.reason;
  }

  api.lifecycle.registerRuntimeLifecycle({ id: 'xsm-protocol', dispose: close,
    cleanup: async ({ sessionKey }) => {
      if (!sessionKey) return close();
      await Promise.all([...sessions.values()].filter(entry => entry.route === sessionKey).map(end));
    } });
  api.on('session_end', async event => {
    const entry = sessions.get(event.sessionId);
    if (entry && (!event.sessionKey || event.sessionKey === entry.route)) await end(entry);
  });
  if (observeTurns) api.on('agent_end', async (_event, context) => {
    const entry = sessions.get(context.sessionId);
    if (entry?.pending && (!context.sessionKey || context.sessionKey === entry.route)) {
      await (await entry.pending).update('idle');
    }
  });

  for (const operation of operations) {
    api.registerTool(context => {
      const entry = state(context);
      if (!entry) return null; // Metadata-only discovery does not create a participant.
      const epoch = entry.epoch;
      return { name: operation.name, label: operation.name, description: operation.description,
        parameters: structuredClone(operation.inputSchema),
        async execute(_id, args, signal) {
          current(entry, epoch, context, signal);
          const host = await open(entry, epoch, context, signal);
          if (observeTurns) await host.update('busy');
          current(entry, epoch, context, signal);
          const result = await host.call(operation.name, args, { signal });
          return { content: [{ type: 'text', text: JSON.stringify(result) }], details: result };
        } };
    }, { name: operation.name });
  }
  return { close };
}

export default { id: 'xsm', name: 'xsm',
  description: 'Experimental xsm protocol tools; native push/UI not connected', register };
