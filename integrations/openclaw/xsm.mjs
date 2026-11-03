/** Pinned tools/context queue and opt-in native wake; UI/continuation certification remains open. */
import { realpath } from 'node:fs/promises';
import { dirname, isAbsolute, resolve } from 'node:path';
import { XsmHost, RetryAdmission } from '../../clients/typescript/xsm-host.mjs';
import { TransportError } from '../../clients/typescript/xsm-client.mjs';
import { holdComponent } from '../../clients/typescript/component-lease.mjs';
import operations from './tools.mjs';
import { nativeDelivery } from './context-queue.mjs';
import { createNativeWake } from './native-wake.mjs';
import { NaturalContext } from './natural-context.mjs';

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
  const wakeEnabled = api.pluginConfig?.nativeWake ?? false;
  if (typeof wakeEnabled !== 'boolean') throw new Error('nativeWake must be a boolean');
  if (wakeEnabled && !observeTurns) throw new Error('nativeWake requires native conversation access');
  let disposed = false;
  const fail = error => api.logger.error('xsm: ' + error.message);
  const nativeWake = wakeEnabled ? createNativeWake(api, fail) : undefined;
  const naturalContext = wakeEnabled ? new NaturalContext() : undefined;
  const componentLease = options.runtimeRoot
    ? holdComponent(profilePath, 'openclaw-plugin', 'openclaw', options.runtimeRoot)
    : Promise.resolve(async () => {});
  componentLease.catch(fail);
  let componentReleased = false;

  function cancelReconnect(entry) {
    clearTimeout(entry.retry?.timer);
    entry.retry = undefined;
    entry.retryDelay = 250;
  }

  function scheduleReconnect(entry, epoch) {
    if (disposed || !entry.registered || entry.epoch !== epoch || entry.retry) return;
    const retry = {};
    entry.retry = retry;
    retry.timer = setTimeout(async () => {
      if (disposed || entry.epoch !== epoch || entry.retry !== retry) return;
      try {
        await open(entry, epoch, entry.nativeContext);
      } catch (error) {
        if (entry.retry !== retry || disposed || entry.epoch !== epoch) return;
        entry.retry = undefined;
        fail(error);
        if (error instanceof TransportError) {
          entry.retryDelay = Math.min((entry.retryDelay ?? 250) * 2, 5000);
          scheduleReconnect(entry, epoch);
        }
      }
    }, entry.retryDelay ?? 250);
    retry.timer.unref?.();
  }

  function state(context) {
    const { sessionId: id, sessionKey: route, workspaceDir: cwd } = context;
    if (!id || !route || typeof cwd !== 'string' || !isAbsolute(cwd)) return undefined;
    if (!sessions.has(id)) sessions.set(id, { id, route, cwd, epoch: 0, closing: Promise.resolve(),
      nativeContext: { sessionId: id, sessionKey: route, workspaceDir: cwd, agentId: context.agentId } });
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
    await componentLease;
    await entry.closing;
    current(entry, epoch, context, signal);
    if (entry.pending) {
      const previous = entry.pending;
      const existing = await previous;
      current(entry, epoch, context, signal);
      if ((existing.closed || existing.controller.signal.aborted) && entry.pending === previous) {
        const recovering = (async () => {
          await existing.close();
          current(entry, epoch, context, signal);
          if (entry.pending !== recovering) throw new Error('xsm native recovery was replaced');
          entry.pending = undefined;
          return open(entry, epoch, context, signal);
        })();
        entry.pending = recovering;
        recovering.catch(() => { if (entry.pending === recovering) entry.pending = undefined; });
      }
    }
    if (!entry.pending) {
      const pending = (async () => {
        const [profile, cwd] = await Promise.all([realpath(profilePath), realpath(entry.cwd)]);
        current(entry, epoch, context, signal);
        const queued = nativeDelivery(api, context, () => {
          if (disposed || epoch !== entry.epoch) throw new Error('xsm native delivery is no longer current');
        }, nativeWake?.start);
        let observed;
        const deliver = queued && (async (packet, deliveryOptions) => {
          if (!deliveryOptions.wake && naturalContext?.isBoundary()) return naturalContext.deliver(entry.id, observed, packet);
          return queued(packet, deliveryOptions);
        });
        if (wakeEnabled && !deliver) throw new Error('native wake requires guarded native context delivery');
        entry.deliveryConnected = Boolean(deliver);
        const connect = async () => {
          observed = await XsmHost.open({ command, env: options.env, runtime: 'openclaw',
            profile, conversation: entry.id, cwd, onError: error => {
              fail(error);
              if (error instanceof TransportError && observed?.controller.signal.aborted) scheduleReconnect(entry, epoch);
            }, deliver, ...(deliver ? { inboxBatchSize: 16, inboxMaxBytes: 524288 } : {}) });
          try {
            current(entry, epoch, context, signal);
            if (entry.activity) await observed.update(entry.activity);
            current(entry, epoch, context, signal);
            return observed;
          } catch (error) {
            try { await observed.close(); } catch (cleanupError) { fail(cleanupError); }
            throw error;
          }
        };
        return api.lifecycle.runInBackgroundContext ? api.lifecycle.runInBackgroundContext(connect) : connect();
      })();
      entry.pending = pending;
      pending.catch(() => { if (entry.pending === pending) entry.pending = undefined; });
    }
    const host = await entry.pending;
    current(entry, epoch, context, signal);
    entry.registered = true;
    cancelReconnect(entry);
    if (host.controller.signal.aborted) scheduleReconnect(entry, epoch);
    return host;
  }

  async function end(entry) {
    entry.epoch++;
    nativeWake?.cancelSession(entry.id);
    await naturalContext?.cancel(entry.id);
    entry.registered = false;
    cancelReconnect(entry);
    entry.deliveryConnected = false;
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
    await naturalContext?.close();
    await nativeWake?.close();
    const results = await Promise.allSettled([...sessions.values()].map(end));
    const failed = results.find(result => result.status === 'rejected');
    try { if (failed) throw failed.reason; }
    finally {
      if (!componentReleased) {
        componentReleased = true;
        await (await componentLease)();
      }
    }
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
  if (wakeEnabled) api.on('agent_turn_prepare', async (_event, context) => {
    const session = api.runtime.agent.session;
    if (!context.agentId || !context.sessionKey || !context.sessionId) return;
    const scope = { agentId: context.agentId, sessionKey: context.sessionKey,
      storePath: session.resolveStorePath(api.runtime.config?.current?.()?.session?.store ?? api.config?.session?.store,
        { agentId: context.agentId }), readConsistency: 'latest' };
    if (session.getSessionEntry(scope)?.sessionId !== context.sessionId) return;
    const entry = state(context);
    if (!entry) return;
    entry.activity = 'busy';
    const host = await open(entry, entry.epoch, context);
    await host.update('busy');
    return naturalContext.begin(entry.id, host, context.runId);
  });
  if (wakeEnabled) api.on('llm_input', async (event, context) => {
    const entry = sessions.get(event.sessionId);
    if (!entry?.pending || !naturalContext.pending.has(entry.id) || context.sessionId !== entry.id) return;
    await naturalContext.observe(entry.id, await entry.pending, event.runId, event.prompt);
  });
  if (observeTurns) api.on('agent_end', async (_event, context) => {
    const entry = sessions.get(context.sessionId);
    if ((entry?.pending || entry?.registered) && (!context.sessionKey || context.sessionKey === entry.route)) {
      const epoch = entry.epoch;
      let host;
      try { host = await open(entry, epoch, entry.nativeContext); }
      catch (error) {
        if (disposed || entry.epoch !== epoch) return;
        throw error;
      }
      const pending = entry.pending;
      if (entry.epoch !== epoch || !pending) return;
      if (wakeEnabled) await naturalContext.cancel(entry.id);
      else if (entry.deliveryConnected) await host.naturalBoundary().catch(error => { if (!(error instanceof RetryAdmission)) throw error; });
      if (entry.epoch === epoch && entry.pending === pending) { await host.update('idle'); entry.activity = 'idle'; }
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
          if (observeTurns) { await host.update('busy'); entry.activity = 'busy'; }
          current(entry, epoch, context, signal);
          const result = await host.call(operation.name, args, { signal });
          return { content: [{ type: 'text', text: JSON.stringify(result) }], details: result };
        } };
    }, { name: operation.name });
  }
  return { close };
}

export default { id: 'xsm', name: 'xsm',
  description: 'Experimental xsm tools, guarded context and opt-in native wake; user UI remains unverified', register };
