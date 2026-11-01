/** Pinned 2026.10.9 public SessionEntry queue, written through guarded native admission. */
import { createHash } from 'node:crypto';

export function nativeDelivery(api, context, assertBindingCurrent) {
  const session = api.runtime.agent?.session;
  const config = () => api.runtime.config?.current?.() ?? api.config;
  const allowed = () => ![api.config, config()].some(value =>
    value?.plugins?.entries?.xsm?.hooks?.allowPromptInjection === false);
  if (!context.agentId || !session?.patchSessionEntry || !session.getSessionEntry ||
      !session.runWithWorkAdmission || !session.resolveStorePath ||
      !allowed()) return undefined;
  const scope = { agentId: context.agentId, sessionKey: context.sessionKey,
    storePath: session.resolveStorePath(config()?.session?.store, { agentId: context.agentId }) };
  const read = () => session.getSessionEntry({ ...scope, readConsistency: 'latest' });
  const initial = read();
  if (initial?.sessionId !== context.sessionId) throw new Error('native delivery conversation differs from caller');
  const revision = initial.lifecycleRevision;
  function guard(signal) {
    assertBindingCurrent();
    if (signal?.aborted || api.lifecycle.signal?.aborted) throw new Error('native context admission cancelled');
    if (!allowed() ||
        session.resolveStorePath(config()?.session?.store, { agentId: context.agentId }) !== scope.storePath) {
      throw new Error('native context admission policy or store changed');
    }
    const current = read();
    if (current?.sessionId !== context.sessionId || current.lifecycleRevision !== revision) {
      throw new Error('native context admission conversation changed');
    }
  }
  return async (packet, { signal, leaseSeconds }) => {
    guard(signal);
    const ids = packet.claims.map(claim => claim.id);
    const body = packet.messages.join('\n\n');
    const digest = createHash('sha256').update(JSON.stringify([context.sessionId, ids, body])).digest('hex');
    const id = 'xsm-' + digest;
    const prefix = body + '\n\nAfter reading, call xsm_ack with tokens: ';
    const text = prefix +
      JSON.stringify(packet.claims.map(claim => claim.token)) +
      '. If expired, read xsm_inbox for current tokens; do not repeat the work.';
    if (text.length > 32768 || !Number.isFinite(leaseSeconds) || leaseSeconds <= 0) {
      throw new Error('native context exceeds the pinned queue limit or claim lease');
    }
    const matches = item => item?.metadata?.xsmHash === digest &&
      item.metadata.nativeSessionId === context.sessionId && typeof item.text === 'string' && item.text.startsWith(prefix);
    await session.runWithWorkAdmission({ ...scope, signal }, async admittedSignal => {
      guard(admittedSignal);
      await session.patchSessionEntry({ ...scope,
        assertCommitAllowed: () => guard(admittedSignal),
        update(current) {
          guard(admittedSignal);
          if (current.sessionId !== context.sessionId || current.lifecycleRevision !== revision) {
            throw new Error('native context admission conversation changed');
          }
          const all = current.pluginNextTurnInjections ?? {};
          if (all.xsm !== undefined && !Array.isArray(all.xsm)) throw new Error('native xsm queue is malformed');
          const now = Date.now();
          const queue = (all.xsm ?? []).filter(item => !(Number.isFinite(item?.ttlMs) && now - item.createdAt > item.ttlMs));
          const existing = queue.find(item => item?.id === id);
          if (existing) {
            if (!matches(existing)) throw new Error('native xsm queue identity collision');
            return null;
          }
          if (queue.length >= 32) throw new Error('native xsm context queue is full');
          return { pluginNextTurnInjections: { ...all, xsm: [...queue, {
            id, pluginId: 'xsm', pluginName: 'xsm', text, idempotencyKey: id,
            placement: 'prepend_context', createdAt: now, ttlMs: Math.floor(leaseSeconds * 1000),
            metadata: { xsmHash: digest, nativeSessionId: context.sessionId, messageIds: ids },
          }] } };
        },
      });
      guard(admittedSignal);
      const accepted = read()?.pluginNextTurnInjections?.xsm?.find(item => item.id === id);
      if (!matches(accepted)) throw new Error('native context admission was not observed');
    });
  };
}
