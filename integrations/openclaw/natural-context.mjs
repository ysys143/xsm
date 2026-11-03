/** Bind a passive inbox batch to one actual native model-input observation. */
import { AsyncLocalStorage } from 'node:async_hooks';
import { randomUUID } from 'node:crypto';
import { inboxAcknowledgement } from '../../clients/typescript/xsm-host.mjs';

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  promise.catch(() => {});
  return { promise, resolve, reject };
}
export class NaturalContext {
  constructor() { this.pending = new Map(); this.boundary = new AsyncLocalStorage(); }
  isBoundary() { return Boolean(this.boundary.getStore()); }
  async begin(id, host, runId) {
    if (typeof runId !== 'string' || !runId) throw new Error('native context run identity unavailable');
    await this.cancel(id);
    const state = { id, host, runId, staged: deferred(), accepted: deferred(), cancelled: false };
    this.pending.set(id, state);
    state.task = this.boundary.run(state, () => host.naturalBoundary());
    state.task.catch(() => {});
    try {
      const text = await Promise.race([state.staged.promise, state.task.then(() => undefined)]);
      if (!text && this.pending.get(id) === state) this.pending.delete(id);
      return text ? { prependContext: text } : undefined;
    } catch (error) {
      await this.cancel(id); throw error;
    }
  }
  async deliver(id, host, packet) {
    const state = this.boundary.getStore();
    if (!state || state.id !== id || state.host !== host || state.cancelled || this.pending.get(id) !== state) {
      throw new Error('native natural context boundary closed');
    }
    state.text = `[XSM peer context ${randomUUID()}]\n` + packet.messages.join('\n\n') + inboxAcknowledgement(packet.claims);
    state.staged.resolve(state.text);
    return state.accepted.promise;
  }
  async observe(id, host, runId, prompt) {
    const state = this.pending.get(id);
    if (!state || state.host !== host || state.runId !== runId || state.cancelled ||
        !state.text || typeof prompt !== 'string' || !prompt.includes(state.text)) return false;
    state.accepted.resolve();
    try { await state.task; }
    finally { if (this.pending.get(id) === state) this.pending.delete(id); }
    return true;
  }
  async cancel(id) {
    const state = this.pending.get(id);
    if (!state) return;
    state.cancelled = true;
    state.accepted.reject(new Error('native model context was not observed'));
    try { await state.task; } catch {}
    if (this.pending.get(id) === state) this.pending.delete(id);
  }
  async close() { await Promise.all([...this.pending.keys()].map(id => this.cancel(id))); }
}
