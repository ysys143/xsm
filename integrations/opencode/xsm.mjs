/** OpenCode 1.19.5 server binding. Each native conversation owns its own host. */
import { randomUUID } from 'node:crypto';
import { mkdir, realpath } from 'node:fs/promises';
import { homedir } from 'node:os';
import { isAbsolute, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { XsmClient, TransportError } from '../../clients/typescript/xsm-client.mjs';
import { XsmHost, RetryAdmission, renderInboxPacket } from '../../clients/typescript/xsm-host.mjs';
import { NativeUiServer, uiParts } from './ui-channel.mjs';
import { holdComponent } from './component-lease.mjs';
import { NativeWorkerControl } from '../../clients/typescript/native-worker-control.mjs';

function unwrap(result) {
  if (result.error) throw new Error('OpenCode: ' + JSON.stringify(result.error));
  if (result.data === undefined) throw new Error('OpenCode returned no native data');
  return result.data;
}

export default async function xsm(api, options = {}) {
  const command = options.command ?? [fileURLToPath(new URL('../../bin/xsm', import.meta.url)),
    'protocol', 'serve', '--stdio'];
  // Calling a native route here re-enters plugin initialization and can deadlock.
  const profilePath = options.profile ?? process.env.OPENCODE_CONFIG_DIR ??
    join(process.env.XDG_CONFIG_HOME ?? join(homedir(), '.config'), 'opencode');
  await mkdir(profilePath, { recursive: true, mode: 0o700 });
  const profile = await realpath(profilePath);
  const workerControl = options.workerControl ?? NativeWorkerControl.fromEnvironment();
  let release;
  try {
    release = await holdComponent(profile, 'opencode-server');
    return await attach(api, { ...options, command, profile, workerControl }, release);
  } catch (error) { workerControl?.close(); if (release) await release(); throw error; }
}

async function attach(api, options, release) {
  const { command, profile } = options;
  // The native loader imports OpenCode's SDK from its own profile dependency tree.
  const z = options.schema;
  if (!z) throw new Error('xsm native loader must provide OpenCode tool.schema');
  const describe = await XsmClient.connect({ command, cwd: api.directory, env: options.env });
  let operations;
  try { ({ operations } = await describe.request('operations/list')); }
  finally { await describe.close(); }

  function schema(spec) {
    let value;
    if (spec.enum) value = z.enum(spec.enum);
    else if (spec.type === 'string') value = z.string();
    else if (spec.type === 'boolean') value = z.boolean();
    else if (spec.type === 'number' || spec.type === 'integer') {
      value = z.number();
      if (spec.type === 'integer') value = value.int();
      if (spec.minimum !== undefined) value = value.min(spec.minimum);
      if (spec.maximum !== undefined) value = value.max(spec.maximum);
    } else if (spec.type === 'array') {
      value = z.array(schema(spec.items));
      if (spec.minItems !== undefined) value = value.min(spec.minItems);
    } else if (spec.type === 'object') {
      value = z.object(shape(spec));
      if (spec.additionalProperties !== false) value = value.passthrough();
    } else throw new Error('unsupported xsm tool schema: ' + JSON.stringify(spec));
    return spec.description ? value.describe(spec.description) : value;
  }
  function shape(spec) {
    return Object.fromEntries(Object.entries(spec.properties ?? {}).map(([key, definition]) => {
      const value = schema(definition);
      return [key, spec.required?.includes(key) ? value : value.optional()];
    }));
  }

  const sessions = new Map();
  const states = new Map();
  const intents = new Set(), versions = new Map(), retries = new Map();
  const cancellationMonitors = new Map();
  let disposed = false;
  const fail = error => {
    if (options.onError) options.onError(error);
    else void api.client.app.log({ body: { service: 'xsm', level: 'error',
      message: error.message } }).catch(() => {});
  };
  function stopCancellationMonitor(id) {
    const monitor = cancellationMonitors.get(id);
    if (!monitor) return;
    cancellationMonitors.delete(id);
    monitor.closed = true;
    clearTimeout(monitor.timer);
    monitor.controller.abort();
    monitor.resolveDone();
  }
  function monitorCancellation(id, parentID) {
    const control = options.workerControl;
    if (typeof control?.cancellationRequested !== 'function' || control.nativeID !== id) return;
    if (typeof parentID !== 'string' || !parentID) throw new Error('native cancellation requires the actual input message ID');
    if (cancellationMonitors.has(id)) return;
    const monitor = { version: versions.get(id) ?? 0, controller: new AbortController(), closed: false };
    monitor.done = new Promise(resolve => { monitor.resolveDone = resolve; });
    cancellationMonitors.set(id, monitor);
    const current = () => !disposed && !monitor.closed && cancellationMonitors.get(id) === monitor &&
      control.nativeID === id && (versions.get(id) ?? 0) === monitor.version;
    const requestOptions = { signal: monitor.controller.signal };
    const messages = async () => {
      const rows = unwrap(await api.client.session.messages({ path: { id }, query: { limit: 20 }, ...requestOptions }));
      if (!Array.isArray(rows)) throw new Error('native cancellation transcript is unavailable');
      const latest = rows.filter(row => row.info?.role === 'assistant' && row.info.sessionID === id &&
        typeof row.info.id === 'string')
        .sort((a, b) => a.info.id < b.info.id ? -1 : a.info.id > b.info.id ? 1 : 0).at(-1)?.info;
      return latest?.parentID === parentID ? latest : undefined;
    };
    async function poll() {
      if (!current()) return;
      try {
        const requested = await control.cancellationRequested();
        if (!current()) return;
        if (requested) {
          let info = await messages();
          if (!current()) return;
          if (info) {
            const statuses = unwrap(await api.client.session.status(requestOptions));
            if (!current()) return;
            const busy = statuses[id] && statuses[id].type !== 'idle';
            if (busy && !monitor.abortRequested) {
              // This CLI process owns one input generation. Never select a
              // different parent message or an arbitrary native conversation.
              monitor.abortRequested = true;
              unwrap(await api.client.session.abort({ path: { id }, ...requestOptions }));
              if (!current()) return;
              info = await messages();
              if (!current()) return;
            }
            const after = unwrap(await api.client.session.status(requestOptions));
            if (!current()) return;
            if ((!after[id] || after[id].type === 'idle') && info?.error?.name === 'MessageAbortedError' &&
                typeof info.time?.completed === 'number') {
              monitor.reporting = true;
              const evidence = { type: 'xsm_native_cancelled', source: 'opencode/1.19.5', sessionID: id,
                native_input_message_id: parentID, native_assistant_message_id: info.id,
                native_error: 'MessageAbortedError', native_completed: info.time.completed, native_idle: true };
              if (options.writeCancellationEvidence) await options.writeCancellationEvidence(evidence);
              else await new Promise((resolve, reject) => process.stdout.write(JSON.stringify(evidence) + '\n',
                error => error ? reject(error) : resolve()));
              if (!current()) return;
              await control.reportStopped();
              stopCancellationMonitor(id);
              return;
            }
            if ((!after[id] || after[id].type === 'idle') && typeof info?.time?.completed === 'number' && !info.error) {
              stopCancellationMonitor(id); // Completion won; preserve its actual result.
              return;
            }
          }
        }
        if (current()) {
          monitor.timer = setTimeout(() => { void poll(); }, 200);
          monitor.timer.unref?.();
        }
      } catch (error) {
        if (current()) { stopCancellationMonitor(id); fail(error); }
      }
    }
    void poll();
  }
  function cancelRetry(id) {
    const pending = retries.get(id);
    if (pending) clearTimeout(pending.timer);
    retries.delete(id);
  }
  function scheduleRetry(id, token, delay = 250) {
    if (disposed || !intents.has(id) || (versions.get(id) ?? 0) !== token || retries.has(id)) return;
    const pending = {};
    retries.set(id, pending);
    pending.timer = setTimeout(async () => {
      pending.timer = undefined;
      if (disposed || retries.get(id) !== pending || !intents.has(id) || (versions.get(id) ?? 0) !== token) return;
      let retry = false;
      try {
        const current = await open(id);
        retry = current.closed || current.controller.signal.aborted;
      } catch (error) {
        try { fail(error); } catch {}
        retry = error instanceof TransportError;
      } finally {
        if (retries.get(id) === pending) retries.delete(id);
      }
      if (retry) scheduleRetry(id, token, Math.min(delay * 2, 5000));
    }, delay);
    pending.timer.unref?.();
  }
  const ui = options.nativeUi ? new NativeUiServer({ onError: fail,
    send: async (id, frame) => {
      unwrap(await api.client.session.prompt({ path: { id }, body: { noReply: true, parts: uiParts(frame) } }));
    } }) : undefined;
  async function assertOwnedDescendant(id) {
    const root = options.workerControl.nativeID;
    const seen = new Set();
    let current = id;
    while (current !== root) {
      if (seen.has(current)) throw new Error('native worker ancestry contains a cycle');
      seen.add(current);
      const native = unwrap(await api.client.session.get({ path: { id: current } }));
      if (native.id !== current || typeof native.parentID !== 'string' || !native.parentID) {
        throw new Error('native input does not belong to the owned conversation tree');
      }
      current = native.parentID;
    }
  }
  async function open(id, cwd) {
    if (disposed) throw new Error('xsm OpenCode binding disposed');
    const token = versions.get(id) ?? 0;
    if (cwd !== undefined && await realpath(cwd) !== await realpath(api.directory)) {
      throw new Error('xsm tool directory differs from native plugin directory');
    }
    if (disposed || (versions.get(id) ?? 0) !== token) throw new Error('native session closed during registration');
    if (sessions.has(id)) {
      const previous = sessions.get(id);
      const existing = await previous;
      if ((existing.closed || existing.controller.signal.aborted) && sessions.get(id) === previous) {
        const recovering = (async () => {
          ui?.close(id);
          await existing.close();
          if (disposed || sessions.get(id) !== recovering) {
            throw new Error('native session closed during backend recovery');
          }
          sessions.delete(id);
          return open(id, cwd);
        })();
        sessions.set(id, recovering);
        recovering.catch(() => { if (sessions.get(id) === recovering) sessions.delete(id); });
      }
    }
    if (!sessions.has(id)) {
      const opening = (async () => {
        const native = unwrap(await api.client.session.get({ path: { id } }));
        if (native.id !== id) throw new Error('native session identity differs');
        if (typeof native.directory !== 'string' || !isAbsolute(native.directory)) {
          throw new Error('native session workspace must be an absolute directory');
        }
        let nativeDirectory;
        try { nativeDirectory = await realpath(native.directory); }
        catch { throw new Error('native session workspace is unavailable'); }
        if (nativeDirectory !== await realpath(api.directory)) throw new Error('native session workspace differs from plugin directory');
        if (disposed || (versions.get(id) ?? 0) !== token) throw new Error('native session closed during registration');
        intents.add(id);
        let observed;
        const host = await XsmHost.open({ command, env: options.env, runtime: 'opencode',
          inboxBatchSize: 16, inboxMaxBytes: 524288,
          profile, conversation: id, cwd: api.directory, parentConversation: native.parentID ?? undefined,
          onError: error => {
            try { fail(error); }
            finally {
              if (error instanceof TransportError && observed && !observed.closed && observed.controller.signal.aborted) scheduleRetry(id, token);
            }
          },
          // Only an explicitly connected native UI can advertise user-decisions.
          present: options.present ? (event, controls) => options.present(id, event, controls)
            : ui ? (event, controls) => ui.present(id, event, controls) : undefined,
          deliver: async (pack, { wake, signal }) => {
            if (disposed || signal.aborted) throw new Error('native delivery cancelled');
            const admissionID = randomUUID();
            const text = renderInboxPacket(pack);
            const inserted = unwrap(await api.client.session.prompt({ path: { id }, body: { noReply: true,
              parts: [{ type: 'text', text, synthetic: true, metadata: { xsmDelivery: admissionID } }] },
            signal }));
            // Native IDs encode ordering. Let OpenCode allocate one rather than inserting a random ID.
            const messageID = inserted.info?.id;
            if (typeof messageID !== 'string' || !messageID) throw new Error('native message ID missing');
            // Acceptance is observed through the actual native transcript, not HTTP enqueue alone.
            const stored = unwrap(await api.client.session.message({ path: { id, messageID }, signal }));
            if (stored.info.id !== messageID || stored.info.sessionID !== id ||
                !stored.parts.some(part => part.type === 'text' && part.text === text &&
                  part.metadata?.xsmDelivery === admissionID) || signal.aborted || disposed) {
              throw new Error('native message admission was not observed');
            }
            if (wake) {
              // Existing busy loops see the appended user input; idle conversations need a native turn.
              try {
                const status = unwrap(await api.client.session.status());
                if (!status[id] || status[id].type === 'idle') {
                  const result = await api.client.session.promptAsync({ path: { id }, body: { parts: [] } });
                  if (result.error) throw new Error('native wake failed: ' + JSON.stringify(result.error));
                }
              } catch (error) { fail(error); }
            }
          },
        });
        observed = host;
        try {
          if (disposed || (versions.get(id) ?? 0) !== token) throw new Error('binding or native session closed during registration');
          await host.update(states.get(id) ?? 'idle', native.title);
          return host;
        } catch (error) {
          try { await host.close(); }
          catch (cleanupError) { try { fail(cleanupError); } catch {} }
          throw error;
        }
      })();
      sessions.set(id, opening);
      opening.catch(() => { if (sessions.get(id) === opening) sessions.delete(id); });
    }
    return sessions.get(id);
  }
  async function close(id) {
    stopCancellationMonitor(id);
    intents.delete(id);
    versions.set(id, (versions.get(id) ?? 0) + 1);
    cancelRetry(id);
    ui?.close(id);
    const pending = sessions.get(id);
    sessions.delete(id);
    states.delete(id);
    if (pending) await (await pending).close();
  }
  return {
    tool: Object.fromEntries(operations.map(operation => [operation.name, {
      description: operation.description, args: shape(operation.inputSchema),
      execute: async (args, context) => {
        const host = await open(context.sessionID, context.directory);
        return JSON.stringify(await host.call(operation.name, args, { signal: context.abort }));
      },
    }])),
    'chat.message': async (input, output) => {
      if (options.workerControl) {
        if (options.workerControl.nativeID !== undefined && options.workerControl.nativeID !== input.sessionID) await assertOwnedDescendant(input.sessionID);
        else await options.workerControl.bind(input.sessionID);
      }
      if (ui && await ui.receive(input.sessionID, output.parts)) return;
      if (output.parts.some(part => part.metadata?.xsmDelivery)) return;
      await (await open(input.sessionID)).naturalBoundary().catch(error => { if (!(error instanceof RetryAdmission)) throw error; });
      monitorCancellation(input.sessionID, output.message?.id);
    },
    event: async ({ event }) => {
      if (disposed) return;
      const { type, properties } = event;
      try {
        if (type === 'session.created') await open(properties.info.id);
        else if (type === 'session.deleted') await close(properties.info.id);
        else if (type === 'session.updated' && sessions.has(properties.info.id)) {
          const host = await open(properties.info.id);
          await host.update(states.get(properties.info.id) ?? 'idle', properties.info.title);
        } else if (type === 'session.status') {
          const state = properties.status.type === 'idle' ? 'idle' : 'busy';
          states.set(properties.sessionID, state);
          if (sessions.has(properties.sessionID)) await (await open(properties.sessionID)).update(state);
        }
      } catch (error) {
        // Disposing intentionally rejects outstanding protocol requests. A live
        // transport failure still belongs to the native host's error handling.
        if (!(disposed && error instanceof TransportError)) throw error;
      }
    },
    dispose: async () => {
      const stopping = [...cancellationMonitors.values()].filter(monitor => monitor.abortRequested || monitor.reporting);
      if (stopping.length) {
        let timer;
        try {
          await Promise.race([Promise.allSettled(stopping.map(monitor => monitor.done)),
            new Promise(resolve => { timer = setTimeout(resolve, 2000); })]);
        } finally { clearTimeout(timer); }
      }
      disposed = true;
      for (const id of cancellationMonitors.keys()) stopCancellationMonitor(id);
      for (const id of retries.keys()) cancelRetry(id);
      intents.clear();
      ui?.close();
      const closing = await Promise.allSettled([...sessions.keys()].map(close));
      try {
        await release();
        for (const result of closing) if (result.status === 'rejected') fail(result.reason);
      } finally { options.workerControl?.close(); }
    },
  };
}
