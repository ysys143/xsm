/** Pi 1.4 host binding. Collaboration policy and recovery live in xsm. */
import { randomUUID } from 'node:crypto';
import { mkdir, realpath } from 'node:fs/promises';
import { getAgentDir } from '@earendil-works/pi-coding-agent';
import { XsmHost, parseHostCommand } from '../../clients/typescript/xsm-host.mjs';

export default function xsm(pi) {
  let host;
  let nativeContext;
  let conversation;
  const admissions = new Map();

  const fail = error => nativeContext?.ui.notify('xsm: ' + error.message, 'error');
  const assertCurrent = signal => {
    if (signal?.aborted || !host || nativeContext.sessionManager.getSessionId() !== conversation) {
      throw new Error('xsm native session changed or delivery was cancelled');
    }
  };

  pi.on('message_start', event => {
    const id = event.message.role === 'custom' && event.message.customType === 'xsm'
      ? event.message.details?.xsmDelivery : undefined;
    admissions.get(id)?.resolve();
  });

  pi.on('session_start', async (_event, ctx) => {
    nativeContext = ctx;
    conversation = ctx.sessionManager.getSessionId();
    await mkdir(getAgentDir(), { recursive: true, mode: 0o700 });
    const profile = await realpath(getAgentDir());
    host = await XsmHost.open({ runtime: 'pi', profile, conversation, cwd: ctx.cwd,
      onError: fail,
      present: ctx.hasUI ? async (event, { signal }) => {
        assertCurrent(signal);
        const { question, questionId, requestedSchema, expiresAt } = event.params;
        const choices = requestedSchema.properties.answer.enum;
        const options = { signal, timeout: Math.max(1, expiresAt * 1000 - Date.now()) };
        const answer = choices?.length
          ? await nativeContext.ui.select(question, choices, options)
          : await nativeContext.ui.input(question, undefined, options);
        assertCurrent(signal);
        return { displayed: question, sourceId: 'pi-ui:' + questionId,
          action: answer === undefined ? 'cancel' : 'accept', answer: answer ?? null };
      } : undefined,
      deliver: (pack, { wake, signal, leaseSeconds }) => new Promise((resolve, reject) => {
        assertCurrent(signal);
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
          const text = pack.messages.join('\n\n') + '\n\nAfter reading, call xsm_ack with tokens: ' +
            JSON.stringify(pack.claims.map(claim => claim.token)) +
            '. If a token expired, read xsm_inbox for current tokens; do not repeat the work.';
          pi.sendMessage({ customType: 'xsm', content: text, display: true,
            details: { xsmDelivery: id, messages: pack.claims.map(claim => claim.id) } },
          { triggerTurn: wake, deliverAs: pack.items.some(item => item.priority === 'now') ? 'steer' : 'followUp' });
        } catch (error) { cleanup(); reject(error); }
      }),
    });
    await host.update('idle', ctx.sessionManager.getSessionName() || undefined);
    for (const operation of host.operations) {
      pi.registerTool({ name: operation.name, label: operation.name, description: operation.description,
        parameters: operation.inputSchema,
        execute: async (_id, args, signal, _onUpdate, toolContext) => {
          nativeContext = toolContext;
          try {
            const result = await host.call(operation.name, args, { signal });
            return { content: [{ type: 'text', text: JSON.stringify(result) }] };
          } catch (error) { return { content: [{ type: 'text', text: error.message }], isError: true }; }
        },
      });
    }
    ctx.ui.setStatus('xsm', 'xsm [' + host.session.ref + ']');
  });

  pi.on('before_agent_start', async (_event, ctx) => {
    nativeContext = ctx;
    if (host) await host.naturalBoundary();
  });
  pi.on('agent_start', () => host?.update('busy').catch(fail));
  pi.on('agent_settled', () => host?.update('idle').catch(fail));
  pi.on('session_info_changed', event => host?.update(nativeContext.isIdle() ? 'idle' : 'busy', event.name ?? '').catch(fail));
  pi.on('session_shutdown', async () => {
    const closing = host;
    host = undefined;
    for (const admission of [...admissions.values()]) admission.reject();
    await closing?.close();
  });

  pi.registerCommand('xsm', {
    description: 'xsm status, or xsm <operation> <JSON arguments>',
    handler: async (args, ctx) => {
      nativeContext = ctx;
      if (!host) throw new Error('xsm session is not registered');
      const parsed = parseHostCommand(args);
      const result = parsed.operation === 'status'
        ? { ref: host.session.ref, generation: host.session.generation,
          operations: host.operations.map(tool => tool.name),
          nativeTools: pi.getAllTools().map(tool => tool.name).filter(name => name.startsWith('xsm_')) }
        : await host.call(parsed.operation, parsed.arguments);
      ctx.ui.notify(JSON.stringify(result), 'info');
    },
  });
}
