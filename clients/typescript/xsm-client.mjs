/** Dependency-free xsm v1 stdio JSON-RPC client. See xsm-client.d.mts. */
import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { TextDecoder } from 'node:util';
import { StringDecoder } from 'node:string_decoder';
import { parseWireJson } from './json-wire.mjs';

export class TransportError extends Error {
  constructor(message) { super(message); this.name = 'TransportError'; }
}

export class RpcError extends Error {
  constructor(code, message, data) {
    super(message);
    this.name = 'RpcError';
    this.code = code;
    this.data = data;
  }
}

const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const handle = session => {
  if (typeof session !== 'string' || !session) throw new TypeError('session must be a nonempty opaque handle');
  return session;
};

export class XsmClient {
  static DEFAULT_COMMAND = ['python3', '-m', 'xsm', 'protocol', 'serve', '--stdio'];
  #pending = new Map();
  #sequence = 0n;
  #failure;
  #closePromise;
  #exitPromise;
  #notifications = [];
  #waiters = [];
  #closeTimeout;

  static async connect(options = {}) {
    const { command = XsmClient.DEFAULT_COMMAND, cwd, env,
      onStderr = text => process.stderr.write(text), closeTimeout = 1000, initializeTimeout = 10000 } = options;
    if (!Array.isArray(command) || !command.length || !Number.isFinite(closeTimeout) || closeTimeout <= 0) {
      throw new TypeError('command must be nonempty and closeTimeout positive');
    }
    if (!Number.isFinite(initializeTimeout) || initializeTimeout <= 0 || initializeTimeout > 2147483647) {
      throw new TypeError('initializeTimeout must be finite and within the positive timer range');
    }
    const child = spawn(command[0], command.slice(1), { cwd, env, stdio: ['pipe', 'pipe', 'pipe'], shell: false });
    const client = new this(child, onStderr, closeTimeout);
    try {
      let timer;
      try {
        client.initialization = await Promise.race([
          client.request('initialize', { protocolVersion: '1' }),
          new Promise((_, reject) => { timer = setTimeout(() =>
            reject(new TransportError('initialize negotiation timed out')), initializeTimeout); }),
        ]);
      } finally { clearTimeout(timer); }
      if (!object(client.initialization) || client.initialization.protocolVersion !== '1') {
        throw new TransportError('unsupported or malformed protocol version negotiation');
      }
      return client;
    } catch (error) {
      try { await client.close(); }
      catch (cleanupError) {
        try { onStderr('xsm cleanup: ' + cleanupError.message + '\n'); } catch {}
      }
      throw error;
    }
  }

  constructor(child, onStderr, closeTimeout) {
    this.process = child;
    this.initialization = undefined;
    this.#closeTimeout = closeTimeout;
    // Observe process closure even if spawn fails before initialize is written.
    this.#exitPromise = new Promise(resolve => child.once('close', (code, signal) => {
      resolve();
      this.#fail(new TransportError(`peer closed (${signal ?? code})`));
    }));
    child.on('error', error => this.#fail(new TransportError(`process error: ${error.message}`)));
    child.stdin.on('error', error => this.#fail(new TransportError(`stdin error: ${error.message}`)));
    child.stdout.on('error', error => this.#fail(new TransportError(`stdout error: ${error.message}`)));
    child.stderr.on('error', error => this.#fail(new TransportError(`stderr error: ${error.message}`)));
    const stderrDecoder = new StringDecoder('utf8');
    const stderr = text => {
      try { if (text) onStderr(text); }
      catch (error) { this.#fail(new TransportError(`stderr consumer failed: ${error.message}`)); }
    };
    child.stderr.on('data', chunk => stderr(stderrDecoder.write(chunk)));
    child.stderr.on('end', () => stderr(stderrDecoder.end()));
    let buffered = '';
    const decoder = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true });
    child.stdout.on('data', chunk => {
      if (this.#failure) return;
      try {
        buffered += decoder.decode(chunk, { stream: true });
        let newline;
        while ((newline = buffered.indexOf('\n')) !== -1) {
          const line = buffered.slice(0, newline);
          buffered = buffered.slice(newline + 1);
          this.#dispatch(parseWireJson(line));
        }
      } catch (error) { this.#fail(new TransportError(`invalid RPC stream: ${error.message}`)); }
    });
    child.stdout.on('end', () => {
      try {
        buffered += decoder.decode();
        this.#fail(new TransportError(buffered ? 'unterminated JSONL frame at EOF' : 'peer closed stdout (EOF)'));
      } catch (error) { this.#fail(new TransportError(`invalid UTF-8: ${error.message}`)); }
    });
  }

  async request(method, params = {}) {
    if (['decision.response', 'decision.abandon'].includes(method)) throw new Error('decision.response requires a trusted host client');
    return this._request(method, params);
  }

  async _request(method, params = {}) {
    if (typeof method !== 'string' || !method) throw new TypeError('method must be a nonempty string');
    if (!object(params)) throw new TypeError('params must be an object');
    if ((method.startsWith('session.') && method !== 'session.open') ||
        ['operation.call', 'events.subscribe', 'delivery.report'].includes(method)) handle(params.session);
    if (this.#failure) throw this.#failure;
    const id = String(++this.#sequence);
    // JSON.stringify runs before correlation registration (e.g. circular data).
    const frame = JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n';
    return new Promise((resolve, reject) => {
      this.#pending.set(id, { resolve, reject });
      try {
        this.process.stdin.write(frame, 'utf8', error => {
          if (error) this.#fail(new TransportError(`stdin write failed: ${error.message}`));
        });
      } catch (error) { this.#fail(new TransportError(`stdin write failed: ${error.message}`)); }
    });
  }

  async sessionOpen({ runtime, profile, conversation, cwd, capabilities = [], parentConversation }) {
    const fields = { runtime, profile, conversation, cwd, capabilities: [...capabilities] };
    if (parentConversation !== undefined) {
      if (!this.initialization.capabilities?.includes('native-lineage')) throw new TransportError('server does not support native parent lineage');
      fields.parent_conversation = parentConversation;
      if (!fields.capabilities.includes('native-lineage')) fields.capabilities.push('native-lineage');
    }
    const result = await this.request('session.open', fields);
    if (!object(result) || typeof result.session !== 'string' || !result.session || !Object.hasOwn(result, 'generation')) {
      const error = new TransportError('session.open must return session and generation');
      this.#fail(error);
      throw error;
    }
    return result;
  }

  sessionUpdate(session, updates) {
    handle(session);
    if (!object(updates) || Object.hasOwn(updates, 'session')) throw new TypeError('updates must be an object without session');
    return this.request('session.update', { ...updates, session });
  }

  sessionClose(session) { return this.request('session.close', { session: handle(session) }); }
  operationCall(session, operation, args) {
    return this.request('operation.call', { session: handle(session), operation, arguments: args });
  }
  async prepareFiles(session, { target, request_id, text, entries, previous_manifest, attachment_fallback }) {
    handle(session);
    const limit = this.initialization?.limits?.fileUploadChunkBytes;
    if (!Number.isInteger(limit) || limit <= 0 || limit > 192 * 1024) throw new Error('server does not advertise supported chunk preparation');
    if (!Array.isArray(entries) || !entries.length || entries.length > 16) throw new TypeError('1 to 16 caller-read entries required');
    let total = 0;
    const frozen = [], specs = [];
    for (const entry of entries) {
      if (!object(entry) || Object.keys(entry).some(key => !['name', 'data', 'source_version'].includes(key)) || !(entry.data instanceof Uint8Array)) {
        throw new TypeError('entries accept name, caller-read Uint8Array data and optional source_version only');
      }
      total += entry.data.byteLength;
      if (entry.data.byteLength > 1048576 || total > 4194304) throw new RangeError('entry or bundle exceeds 1MiB/4MiB limit');
      const data = Buffer.from(entry.data);
      frozen.push(data);
      specs.push({ name: entry.name, size: data.length, sha256: createHash('sha256').update(data).digest('hex'),
        ...(entry.source_version !== undefined ? { source_version: entry.source_version } : {}) });
    }
    const opened = await this.request('files.upload.open', { session, target, request_id, text, entries: specs,
      ...(previous_manifest !== undefined ? { previous_manifest } : {}),
      ...(attachment_fallback !== undefined ? { attachment_fallback } : {}) });
    if (!object(opened)) throw new TransportError('invalid upload open response');
    if (opened.state === 'frozen') return { ...opened, body_sent: false };
    const chunk = opened.chunk_bytes, offsets = opened.offsets;
    if (opened.state !== 'uploading' || !Number.isInteger(chunk) || chunk <= 0 || chunk > limit || !Array.isArray(offsets) || offsets.length !== frozen.length ||
        offsets.some((offset, index) => !Number.isInteger(offset) || offset < 0 || offset > frozen[index].length)) {
      throw new TransportError('invalid upload progress response');
    }
    for (let index = 0; index < frozen.length; index++) {
      const data = frozen[index];
      for (let offset = offsets[index]; offset < data.length; offset += chunk) {
        await this.request('files.upload.write', { session, upload: opened.upload, entry: index, offset,
          base64: data.subarray(offset, offset + chunk).toString('base64') });
      }
    }
    return this.request('files.upload.commit', { session, upload: opened.upload });
  }
  eventsSubscribe(session) { return this.request('events.subscribe', { session: handle(session) }); }
  deliveryReport(session, id, state, token) {
    return this.request('delivery.report', { session: handle(session), id, state,
      ...(token !== undefined ? { token } : {}) });
  }

  nextNotification() {
    if (this.#notifications.length) return Promise.resolve(this.#notifications.shift());
    if (this.#failure) return Promise.reject(this.#failure);
    return new Promise((resolve, reject) => this.#waiters.push({ resolve, reject }));
  }

  #dispatch(message) {
    if (!object(message) || message.jsonrpc !== '2.0') throw new Error('expected a JSON-RPC 2.0 object');
    if (Object.hasOwn(message, 'method')) {
      if (Object.hasOwn(message, 'id') || typeof message.method !== 'string' ||
          (Object.hasOwn(message, 'params') && !object(message.params)) ||
          Object.hasOwn(message, 'result') || Object.hasOwn(message, 'error')) {
        throw new Error('expected a notification, not a peer request');
      }
      const waiter = this.#waiters.shift();
      if (waiter) waiter.resolve(message);
      else this.#notifications.push(message);
      return;
    }
    const hasError = Object.hasOwn(message, 'error');
    if (typeof message.id !== 'string' || Object.hasOwn(message, 'result') === hasError) {
      throw new Error('invalid RPC response');
    }
    if (hasError && (!object(message.error) || !Number.isInteger(message.error.code) || typeof message.error.message !== 'string')) {
      throw new Error('invalid RPC error object');
    }
    const pending = this.#pending.get(message.id);
    if (!pending) return;
    this.#pending.delete(message.id);
    if (hasError) pending.reject(new RpcError(message.error.code, message.error.message, message.error.data));
    else pending.resolve(message.result);
  }

  #fail(error) {
    if (this.#failure) return;
    this.#failure = error;
    for (const pending of this.#pending.values()) pending.reject(error);
    this.#pending.clear();
    for (const waiter of this.#waiters.splice(0)) waiter.reject(error);
    this.#closePromise = this.#shutdown();
  }

  async #shutdown() {
    this.process.stdin.end();
    const wait = async () => {
      let timer;
      try {
        return await Promise.race([
          this.#exitPromise.then(() => true),
          new Promise(resolve => { timer = setTimeout(() => resolve(false), this.#closeTimeout); }),
        ]);
      } finally { clearTimeout(timer); }
    };
    if (await wait()) return;
    this.process.kill('SIGTERM');
    if (await wait()) return;
    this.process.kill('SIGKILL');
    await this.#exitPromise;
  }

  async close() {
    this.#fail(new TransportError('client closed'));
    await this.#closePromise;
  }
}

/** Trusted UI bridge; never expose this object as a model-callable tool. */
export class XsmHostClient extends XsmClient {
  abandonDecision(event) {
    if (!object(event) || event.method !== 'decision/request' || !object(event.params)) {
      throw new TypeError('an actual host decision/request event is required');
    }
    const { session, questionId, challenge } = event.params;
    return this._request('decision.abandon', { session, questionId, challenge });
  }
  respondToDecision(event, { displayed, sourceId, answer = null, action = 'accept' }) {
    if (!object(event) || event.method !== 'decision/request' || !object(event.params)) {
      throw new TypeError('an actual host decision/request event is required');
    }
    const { session, questionId, challenge } = event.params;
    return this._request('decision.response', {
      session, questionId, challenge, displayed, source_id: sourceId, action, answer,
    });
  }
}
