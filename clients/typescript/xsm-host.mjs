/** Runtime-neutral host coordination. Native bindings provide only delivery and UI. */
import { fileURLToPath } from 'node:url';
import { XsmHostClient, TransportError } from './xsm-client.mjs';

export class RetryAdmission extends Error {
  constructor(message, delayMs = 250) {
    super(message);
    if (!Number.isFinite(delayMs) || delayMs <= 0 || delayMs > 60000) throw new TypeError('retry delay must be within 0–60000 ms');
    this.name = 'RetryAdmission';
    this.delayMs = delayMs;
  }
}

function retryPause(signal, delayMs) {
  if (signal.aborted) return Promise.resolve(false);
  return new Promise(resolve => {
    const finish = value => { clearTimeout(timer); signal.removeEventListener('abort', cancel); resolve(value); };
    const cancel = () => finish(false);
    const timer = setTimeout(() => finish(true), delayMs);
    signal.addEventListener('abort', cancel, { once: true });
  });
}

export function inboxAcknowledgement(claims) {
  return claims.length ? '\n\nAfter reading, call xsm_ack with tokens: ' +
    JSON.stringify(claims.map(claim => claim.token)) +
    '. If expired, read xsm_inbox for current tokens; do not repeat the work.' : '';
}

export function renderInboxPacket(packet) {
  return packet.messages.join('\n\n') + inboxAcknowledgement(packet.claims);
}

function aborted() {
  const error = new Error('host operation wait cancelled; no effect applied by this waiter');
  error.name = 'AbortError';
  return error;
}

export function parseHostCommand(text) {
  const input = text.trim();
  const boundary = input.search(/\s/);
  const operation = boundary < 0 ? input : input.slice(0, boundary);
  const raw = boundary < 0 ? '' : input.slice(boundary).trim();
  const args = raw ? JSON.parse(raw) : {};
  if (!args || typeof args !== 'object' || Array.isArray(args)) {
    throw new TypeError('operation arguments must be a JSON object');
  }
  return { operation: operation || 'status', arguments: args };
}

export class XsmHost {
  static async open(options) {
    if (options.inboxMaxBytes !== undefined && (!Number.isInteger(options.inboxMaxBytes) ||
        options.inboxMaxBytes < 1 || options.inboxMaxBytes > 1048576)) {
      throw new TypeError('inboxMaxBytes must be an integer from 1 to 1048576');
    }
    if (options.inboxBatchSize !== undefined && (!Number.isInteger(options.inboxBatchSize) ||
        options.inboxBatchSize < 1 || options.inboxBatchSize > 100)) {
      throw new TypeError('inboxBatchSize must be an integer from 1 to 100');
    }
    const command = options.command ?? [fileURLToPath(new URL('../../bin/xsm', import.meta.url)),
      'protocol', 'serve', '--stdio'];
    const client = await XsmHostClient.connect({ command, cwd: options.cwd,
      env: options.env, onStderr: options.onStderr });
    try {
      const available = client.initialization.capabilities;
      const required = ['messaging', 'inbox', ...(options.deliver ? ['events'] : []),
        ...(options.present ? ['user-decisions'] : [])];
      if (!Array.isArray(available) || required.some(capability => !available.includes(capability)) ||
          (!Number.isFinite(client.initialization.limits?.claimLeaseSeconds) || client.initialization.limits.claimLeaseSeconds <= 0)) {
        throw new Error('server does not expose the required host protocol capabilities and claim lease');
      }
      const capabilities = ['messaging', 'inbox', ...(options.deliver ? ['events'] : [])];
      if (options.present) capabilities.push('user-decisions');
      const session = await client.sessionOpen({ runtime: options.runtime, profile: options.profile,
        conversation: options.conversation, cwd: options.cwd, capabilities });
      const { operations } = await client.request('operations/list');
      if (options.inboxMaxBytes !== undefined && !operations.find(item => item.name === 'xsm_inbox')?.inputSchema?.properties?.max_bytes) {
        throw new Error('server does not advertise inbox byte budgets');
      }
      const host = new XsmHost(client, session, operations, options);
      if (options.deliver) await client.eventsSubscribe(session.session);
      host.pumpTask = host.pump();
      return host;
    } catch (error) {
      try { await client.close(); }
      catch (cleanupError) {
        try { (options.onError ?? (failure => console.error('xsm:', failure.message)))(cleanupError); }
        catch {}
      }
      throw error;
    }
  }

  constructor(client, session, operations, options) {
    this.client = client;
    this.session = session;
    this.operations = operations;
    this.options = options;
    this.questions = new Map();
    this.controller = new AbortController();
    this.closed = false;
    this.deliverySuspended = false;
    this.pendingWake = false;
    this.invocationTail = Promise.resolve();
  }

  question(id) {
    let state = this.questions.get(id);
    if (!state) {
      state = { waiters: new Set(), controller: new AbortController() };
      this.questions.set(id, state);
    }
    return state;
  }

  scheduleDelivery(delayMs = 0, afterId) {
    if (this.closed || this.controller.signal.aborted || this.deliverySuspended || this.deliveryTask) return;
    this.deliveryTask = (async () => {
      if (delayMs && !await retryPause(this.controller.signal, delayMs)) return;
      await this.deliverLoop(afterId);
    })().finally(() => {
      this.deliveryTask = undefined;
      if (this.pendingWake) this.scheduleDelivery();
    });
  }

  error(error) {
    if (this.closed) return;
    try { (this.options.onError ?? (e => console.error('xsm:', e.message)))(error); }
    catch (reporter) { console.error('xsm diagnostic failed:', error.message, reporter.message); }
  }

  abandon(state) {
    if (state.event && !state.abandonTask && !this.closed) {
      state.abandonTask = this.client.abandonDecision(state.event);
    }
    return state.abandonTask;
  }

  serializeInvocation(callback) {
    const pending = this.invocationTail.then(callback);
    this.invocationTail = pending.catch(() => {});
    return pending;
  }

  cancelUnused(state) {
    const cleanup = this.serializeInvocation(async () => {
      if (state.waiters.size || state.result || this.closed) return;
      state.cancelled = true;
      state.controller.abort();
      await this.abandon(state);
    });
    cleanup.catch(error => this.error(error));
    return cleanup;
  }

  async pump() {
    try {
      while (!this.closed) {
        const event = await this.client.nextNotification();
        if (event.params?.session !== this.session.session) continue;
        if (event.method === 'decision/request') this.present(event);
        else if (event.method === 'events/available' && !this.deliverySuspended) {
          this.pendingWake = true;
          this.scheduleDelivery();
        }
      }
    } catch (error) {
      if (!this.closed) {
        this.controller.abort();
        for (const state of this.questions.values()) {
          state.error = error;
          state.controller.abort();
          for (const waiter of [...state.waiters]) waiter.reject(error);
        }
        this.error(error);
      }
    }
  }

  present(event) {
    const state = this.question(event.params.questionId);
    if (state.event) return;
    state.event = event;
    state.task = (async () => {
      try {
        if (state.cancelled || this.closed) {
          await this.abandon(state);
          return;
        }
        const response = await this.options.present(event, { signal: state.controller.signal });
        if (this.closed || state.controller.signal.aborted) return;
        const result = await this.client.respondToDecision(event, response);
        state.result = result;
        for (const waiter of [...state.waiters]) waiter.resolve(result);
      } catch (error) {
        if (state.controller.signal.aborted || this.closed) return;
        state.error = error;
        for (const waiter of [...state.waiters]) waiter.reject(error);
        try { await this.abandon(state); } catch { /* original remains protected */ }
        this.error(error);
      }
    })();
  }

  waitForQuestion(id, signal) {
    const state = this.question(id);
    if (signal?.aborted || this.closed) {
      this.cancelUnused(state);
      return Promise.reject(aborted());
    }
    if (state.error) return Promise.reject(state.error);
    if (state.result) return Promise.resolve(state.result);
    return new Promise((resolve, reject) => {
      const cleanup = () => { state.waiters.delete(waiter); signal?.removeEventListener('abort', cancel); };
      const waiter = {
        resolve: result => { cleanup(); resolve(result); },
        reject: error => { cleanup(); reject(error); },
      };
      const cancel = () => {
        waiter.reject(aborted());
        this.cancelUnused(state);
      };
      state.waiters.add(waiter);
      signal?.addEventListener('abort', cancel, { once: true });
    });
  }

  async call(operation, args = {}, { signal } = {}) {
    if (signal?.aborted || this.closed) throw aborted();
    const invoked = await this.serializeInvocation(async () => {
      if (signal?.aborted || this.closed) throw aborted();
      const result = await this.client.operationCall(this.session.session, operation, args);
      if (result?.status !== 'waiting-for-user') return { result };
      if (!result.question_id) throw new Error('server does not identify its host question');
      // Reserve the waiter inside the response-registration barrier. Returning
      // it in an object releases the barrier before waiting for a human.
      const waiting = this.waitForQuestion(result.question_id, signal);
      waiting.catch(() => {});
      return { result, waiting };
    });
    let result = invoked.result;
    if (invoked.waiting) {
      await invoked.waiting;
      if (signal?.aborted || this.closed) throw aborted();
      result = await this.client.operationCall(this.session.session, operation, args);
      if (result?.status === 'waiting-for-user') throw new Error('operation still waiting; inspect its decision status');
    }
    return result;
  }

  async deliverLoop(afterId) {
    while (this.pendingWake && !this.closed && !this.controller.signal.aborted && !this.deliverySuspended) {
      this.pendingWake = false;
      try {
        const pack = await this.deliverInbox(true, afterId);
        const progressed = pack.claims.length || (pack.next_after && pack.next_after !== afterId);
        afterId = pack.next_after ?? undefined;
        if (progressed && (pack.batch_limited ||
            (this.options.inboxBatchSize && pack.messages.length >= this.options.inboxBatchSize))) {
          this.pendingWake = true;
        }
      }
      catch (error) {
        if (error instanceof RetryAdmission) {
          if (!await retryPause(this.controller.signal, error.delayMs)) break;
          this.pendingWake = true;
        } else { this.deliverySuspended = true; this.error(error); }
      }
    }
  }

  async deliverInbox(wake, afterId) {
    if (!this.options.deliver) throw new Error('native delivery is not connected');
    const args = {};
    if (this.options.inboxBatchSize !== undefined) args.limit = this.options.inboxBatchSize;
    if (this.options.inboxMaxBytes !== undefined) args.max_bytes = this.options.inboxMaxBytes;
    if (afterId !== undefined) args.after_id = afterId;
    const pack = await this.client.operationCall(this.session.session, 'xsm_inbox', args);
    if (!pack.messages.length) return pack;
    try {
      // Resolves only after the native binding observes admission, never on stdout flush.
      const shouldWake = Boolean(wake && pack.claims.length && pack.items?.some(item => item.wake));
      const accepted = await this.options.deliver(pack, { wake: shouldWake, signal: this.controller.signal,
        leaseSeconds: this.client.initialization.limits.claimLeaseSeconds });
      if (accepted === false) throw new Error('native queue refused admission');
      for (const claim of pack.claims) await this.client.deliveryReport(this.session.session, claim.id, 'admitted', claim.token);
    } catch (error) {
      if (!this.closed && pack.claims.length) {
        try {
          await this.client.request('inbox.release', { session: this.session.session,
            tokens: pack.claims.map(claim => claim.token) });
        } catch (cleanupError) { this.error(cleanupError); }
      }
      throw error;
    }
    return pack;
  }

  async naturalBoundary() {
    this.deliverySuspended = false;
    try {
      const pack = await this.deliverInbox(false);
      if (pack.batch_limited && pack.next_after) {
        this.pendingWake = true;
        this.scheduleDelivery(0, pack.next_after);
      }
      return pack;
    }
    catch (error) {
      if (error instanceof RetryAdmission) {
        this.pendingWake = true;
        this.scheduleDelivery(error.delayMs);
      }
      throw error;
    }
  }

  update(state, name) {
    const updates = { state };
    if (name !== undefined) updates.name = name;
    return this.client.sessionUpdate(this.session.session, updates);
  }

  async close() {
    if (this.closed) return;
    this.closed = true;
    this.controller.abort();
    for (const state of this.questions.values()) {
      state.controller.abort();
      for (const waiter of [...state.waiters]) waiter.reject(new TransportError('host closed; question not answered'));
    }
    await this.client.close();
    await this.pumpTask;
  }
}
