/** Pi 1.4 host binding. Collaboration policy and recovery live in xsm. */
import { randomUUID } from 'node:crypto';
import { mkdir, realpath } from 'node:fs/promises';
import { TransportError } from '../../clients/typescript/xsm-client.mjs';
import { getAgentDir } from '@earendil-works/pi-coding-agent';
import { XsmHost, RetryAdmission, parseHostCommand, renderInboxPacket } from '../../clients/typescript/xsm-host.mjs';

export default function xsm(pi, options = {}) {
  let host;
  let nativeContext;
  let conversation;
  let workspace;
  let epoch = 0;
  let recovering;
  let active = false;
  let toolsRegistered = false;
  let reconnectTimer;
  let reconnectDelay = 250;
  const admissions = new Map();

  const notify = error => { try { nativeContext?.ui.notify('xsm: ' + error.message, 'error'); } catch {} };
  const fail = error => {
    notify(error);
    if (error instanceof TransportError && active && host?.controller.signal.aborted) scheduleReconnect();
  };
  function cancelReconnect() {
    clearTimeout(reconnectTimer);
    reconnectTimer = undefined;
    reconnectDelay = 250;
  }
  function scheduleReconnect() {
    if (!active || reconnectTimer) return;
    const token = epoch;
    reconnectTimer = setTimeout(async () => {
      reconnectTimer = undefined;
      if (!active || token !== epoch) return;
      try {
        await ensure(nativeContext);
        reconnectDelay = 250;
      } catch (error) {
        notify(error);
        if (error instanceof TransportError && active && token === epoch) {
          reconnectDelay = Math.min(reconnectDelay * 2, 5000);
          scheduleReconnect();
        }
      }
    }, reconnectDelay);
    reconnectTimer.unref?.();
  }
  const assertCurrent = (signal, token) => {
    if (token !== epoch || signal?.aborted || !host || nativeContext.sessionManager.getSessionId() !== conversation) {
      throw new Error('xsm native session changed or delivery was cancelled');
    }
  };

  pi.on('message_start', event => {
    const id = event.message.role === 'custom' && event.message.customType === 'xsm'
      ? event.message.details?.xsmDelivery : undefined;
    admissions.get(id)?.resolve();
  });

  async function initialize(ctx, register = true, token = epoch) {
    const currentConversation = ctx.sessionManager.getSessionId();
    await mkdir(getAgentDir(), { recursive: true, mode: 0o700 });
    const profile = await realpath(getAgentDir());
    const cwd = await realpath(ctx.cwd);
    if (token !== epoch || ctx.sessionManager.getSessionId() !== currentConversation) throw new Error('native session changed during registration');
    nativeContext = ctx;
    conversation = currentConversation;
    workspace = cwd;
    const opened = await XsmHost.open({ runtime: 'pi', profile, conversation: currentConversation, cwd, command: options.command,
      inboxBatchSize: 16, inboxMaxBytes: 524288,
      onError: fail,
      present: ctx.hasUI ? async (event, { signal }) => {
        assertCurrent(signal, token);
        const { question, questionId, requestedSchema, expiresAt } = event.params;
        const choices = requestedSchema.properties.answer.enum;
        const options = { signal, timeout: Math.max(1, expiresAt * 1000 - Date.now()) };
        const answer = choices?.length
          ? await nativeContext.ui.select(question, choices, options)
          : await nativeContext.ui.input(question, undefined, options);
        assertCurrent(signal, token);
        return { displayed: question, sourceId: 'pi-ui:' + questionId,
          action: answer === undefined ? 'cancel' : 'accept', answer: answer ?? null };
      } : undefined,
      deliver: (pack, { wake, signal, leaseSeconds }) => new Promise((resolve, reject) => {
        assertCurrent(signal, token);
        const id = randomUUID();
        let timer;
        const cleanup = () => {
          clearTimeout(timer);
          signal.removeEventListener('abort', cancel);
          admissions.delete(id);
        };
        const cancel = () => { cleanup(); reject(new Error('native message admission cancelled')); };
        admissions.set(id, { resolve: () => { cleanup(); resolve(); }, reject: cancel });
        signal.addEventListener('abort', cancel, { once: true });
        timer = setTimeout(() => { cleanup(); reject(new Error('native admission not observed before claim lease')); },
          Math.max(1, leaseSeconds * 1000 - 1000));
        try {
          const text = renderInboxPacket(pack);
          pi.sendMessage({ customType: 'xsm', content: text, display: true,
            details: { xsmDelivery: id, messages: pack.claims.map(claim => claim.id) } },
          { triggerTurn: wake, deliverAs: pack.items.some(item => item.priority === 'now') ? 'steer' : 'followUp' });
          // Idle non-waking appends emit app events, not extension message_start.
          // Observe the committed active branch instead of waiting for a new turn.
          assertCurrent(signal, token);
          const stored = nativeContext.sessionManager.getBranch().some(entry => entry.type === 'custom_message' &&
            entry.customType === 'xsm' && entry.details?.xsmDelivery === id && entry.content === text);
          if (stored) admissions.get(id)?.resolve();
        } catch (error) { cleanup(); reject(error); }
      }),
    });
    try {
      if (token !== epoch) { await opened.close(); throw new Error('native session changed during registration'); }
      host = opened;
      await opened.update(ctx.isIdle() ? 'idle' : 'busy', ctx.sessionManager.getSessionName() || undefined);
      if (token !== epoch || host !== opened) { await opened.close(); throw new Error('native session changed during registration'); }
      if (register || !toolsRegistered) for (const operation of opened.operations) {
        pi.registerTool({ name: operation.name, label: operation.name, description: operation.description,
          parameters: operation.inputSchema,
          execute: async (_id, args, signal, _onUpdate, toolContext) => {
            try {
              const current = await ensure(toolContext);
              const result = await current.call(operation.name, args, { signal });
              return { content: [{ type: 'text', text: JSON.stringify(result) }] };
            } catch (error) { return { content: [{ type: 'text', text: error.message }], isError: true }; }
          },
        });
      }
      toolsRegistered = true;
      ctx.ui.setStatus('xsm', 'xsm [' + opened.session.ref + ']');
      return opened;
    } catch (error) {
      if (host === opened) host = undefined;
      await opened.close().catch(fail);
      throw error;
    }
  }

  async function ensure(ctx) {
    if (!active) throw new Error('xsm session is not registered');
    const token = epoch;
    const cwd = await realpath(ctx.cwd);
    if (token !== epoch || !active || ctx.sessionManager.getSessionId() !== conversation || cwd !== workspace) {
      throw new Error('native session or workspace changed; wait for session_start');
    }
    nativeContext = ctx;
    if (!host || host.closed || host.controller.signal.aborted) {
      if (!recovering) {
        const previous = host, token = epoch;
        const attempt = (async () => {
          await previous?.close();
          if (token !== epoch) throw new Error('native session changed during recovery');
          return initialize(ctx, false, token);
        })().finally(() => { if (recovering === attempt) recovering = undefined; });
        recovering = attempt;
      }
      return recovering;
    }
    return host;
  }

  pi.on('session_start', async (_event, ctx) => {
    cancelReconnect();
    const token = ++epoch, previous = host, pending = recovering;
    host = undefined;
    active = false;
    recovering = undefined;
    await previous?.close();
    await pending?.catch(() => {});
    const cwd = await realpath(ctx.cwd);
    if (token !== epoch) return;
    nativeContext = ctx;
    conversation = ctx.sessionManager.getSessionId();
    workspace = cwd;
    active = true;
    const opening = initialize(ctx, true, token);
    recovering = opening;
    try { await opening; }
    finally { if (recovering === opening) recovering = undefined; }
  });

  pi.on('before_agent_start', async (_event, ctx) => {
    if (active) await (await ensure(ctx)).naturalBoundary().catch(error => { if (!(error instanceof RetryAdmission)) throw error; });
  });
  pi.on('agent_start', (_event, ctx) => active && ensure(ctx).then(current => current.update('busy')).catch(fail));
  pi.on('agent_settled', (_event, ctx) => active && ensure(ctx).then(current => current.update('idle')).catch(fail));
  pi.on('session_info_changed', (event, ctx) => active && ensure(ctx).then(current => current.update(ctx.isIdle() ? 'idle' : 'busy', event.name ?? '')).catch(fail));
  pi.on('session_shutdown', async () => {
    cancelReconnect();
    active = false;
    ++epoch;
    const closing = host, pending = recovering;
    host = undefined;
    for (const admission of [...admissions.values()]) admission.reject();
    await closing?.close();
    await pending?.catch(() => {});
  });

  pi.registerCommand('xsm', {
    description: 'xsm status, or xsm <operation> <JSON arguments>',
    handler: async (args, ctx) => {
      const current = await ensure(ctx);
      const parsed = parseHostCommand(args);
      const result = parsed.operation === 'status'
        ? { ref: current.session.ref, generation: current.session.generation,
          operations: current.operations.map(tool => tool.name),
          nativeTools: pi.getAllTools().map(tool => tool.name).filter(name => name.startsWith('xsm_')) }
        : await current.call(parsed.operation, parsed.arguments);
      ctx.ui.notify(JSON.stringify(result), 'info');
    },
  });
}
