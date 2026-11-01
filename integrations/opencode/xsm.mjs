/** OpenCode 1.19.5 server binding. Each native conversation owns its own host. */
import { randomUUID } from 'node:crypto';
import { mkdir, realpath } from 'node:fs/promises';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { XsmClient } from '../../clients/typescript/xsm-client.mjs';
import { XsmHost, renderInboxPacket } from '../../clients/typescript/xsm-host.mjs';
import { NativeUiServer, uiParts } from './ui-channel.mjs';
import { holdComponent } from './component-lease.mjs';

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
  const release = await holdComponent(profile, 'opencode-server');
  try { return await attach(api, { ...options, command, profile }, release); }
  catch (error) { await release(); throw error; }
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
  let disposed = false;
  const fail = error => {
    if (options.onError) options.onError(error);
    else void api.client.app.log({ body: { service: 'xsm', level: 'error',
      message: error.message } }).catch(() => {});
  };
  const ui = options.nativeUi ? new NativeUiServer({ onError: fail,
    send: async (id, frame) => {
      unwrap(await api.client.session.prompt({ path: { id }, body: { noReply: true, parts: uiParts(frame) } }));
    } }) : undefined;
  async function open(id, cwd) {
    if (disposed) throw new Error('xsm OpenCode binding disposed');
    if (cwd !== undefined && await realpath(cwd) !== await realpath(api.directory)) {
      throw new Error('xsm tool directory differs from native plugin directory');
    }
    if (!sessions.has(id)) {
      const opening = (async () => {
        const native = unwrap(await api.client.session.get({ path: { id } }));
        if (native.id !== id) throw new Error('native session identity differs');
        const host = await XsmHost.open({ command, env: options.env, runtime: 'opencode',
          profile, conversation: id, cwd: api.directory, onError: fail,
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
        if (disposed) { await host.close(); throw new Error('binding disposed during session registration'); }
        await host.update(states.get(id) ?? 'idle', native.title);
        return host;
      })();
      sessions.set(id, opening);
      opening.catch(() => { if (sessions.get(id) === opening) sessions.delete(id); });
    }
    return sessions.get(id);
  }
  async function close(id) {
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
      if (ui && await ui.receive(input.sessionID, output.parts)) return;
      if (output.parts.some(part => part.metadata?.xsmDelivery)) return;
      await (await open(input.sessionID)).naturalBoundary();
    },
    event: async ({ event }) => {
      const { type, properties } = event;
      if (type === 'session.created') await open(properties.info.id);
      else if (type === 'session.deleted') await close(properties.info.id);
      else if (type === 'session.updated' && sessions.has(properties.info.id)) {
        const host = await sessions.get(properties.info.id);
        await host.update(states.get(properties.info.id) ?? 'idle', properties.info.title);
      } else if (type === 'session.status') {
        const state = properties.status.type === 'idle' ? 'idle' : 'busy';
        states.set(properties.sessionID, state);
        if (sessions.has(properties.sessionID)) await (await sessions.get(properties.sessionID)).update(state);
      }
    },
    dispose: async () => {
      disposed = true;
      ui?.close();
      const closing = await Promise.allSettled([...sessions.keys()].map(close));
      await release();
      for (const result of closing) if (result.status === 'rejected') fail(result.reason);
    },
  };
}
