/** Private per-execution JSON-RPC binding; never a model-facing operation. */
import { Socket, connect } from 'node:net';
import { TextDecoder } from 'node:util';
import { parseWireJson } from './json-wire.mjs';

export const WORKER_CONTROL_FD = 'XSM_OWNED_CONTROL_FD';
export class WorkerControlError extends Error {}

export class NativeWorkerControl {
  #pending = new Map();
  #serial = 0;
  #buffer = Buffer.alloc(0);
  #failure;
  nativeID;

  static fromEnvironment(environment = process.env) {
    const value = environment[WORKER_CONTROL_FD];
    if (value === undefined) return undefined;
    delete environment[WORKER_CONTROL_FD];
    if (!/^[0-9]+$/.test(value) || !Number.isSafeInteger(Number(value)) || Number(value) < 3) {
      throw new WorkerControlError('invalid private native worker descriptor');
    }
    return new NativeWorkerControl(Number(value));
  }

  constructor(fd) {
    this.socket = globalThis.Bun ? connect({ fd }) : new Socket({ fd, readable: true, writable: true });
    this.socket.on('data', chunk => this.#data(chunk));
    this.socket.on('error', () => this.#fail('native worker control transport failed'));
    this.socket.on('close', () => this.#fail('native worker control closed'));
  }

  #fail(message) {
    this.#failure ??= new WorkerControlError(message);
    for (const waiter of this.#pending.values()) waiter.reject(this.#failure);
    this.#pending.clear();
    this.socket.destroy();
  }

  #data(chunk) {
    this.#buffer = Buffer.concat([this.#buffer, chunk]);
    try {
      for (;;) {
        const end = this.#buffer.indexOf(10);
        if (end < 0) break;
        if (end + 1 > 16384) throw new Error('frame size');
        const line = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(this.#buffer.subarray(0, end));
        this.#buffer = this.#buffer.subarray(end + 1);
        const frame = parseWireJson(line);
        if (!frame || Array.isArray(frame) || frame.jsonrpc !== '2.0' || !Number.isSafeInteger(frame.id)) throw new Error('envelope');
        const pending = this.#pending.get(frame.id);
        if (!pending) throw new Error('unknown response');
        if (Object.hasOwn(frame, 'error')) {
          if (Object.hasOwn(frame, 'result')) throw new Error('mixed response');
          this.#pending.delete(frame.id);
          pending.reject(new WorkerControlError('native context binding refused'));
          continue;
        }
        if (Object.keys(frame).sort().join(',') !== 'id,jsonrpc,result' || !frame.result ||
            Array.isArray(frame.result) || Object.keys(frame.result).join(',') !== pending.field ||
            typeof frame.result[pending.field] !== 'boolean' ||
            (pending.field !== 'requested' && frame.result[pending.field] !== true)) throw new Error('confirmation');
        this.#pending.delete(frame.id);
        pending.resolve(frame.result[pending.field]);
      }
      if (this.#buffer.length > 16384) throw new Error('frame size');
    } catch { this.#fail('invalid native worker control response'); }
  }

  async bind(nativeID) {
    if (typeof nativeID !== 'string' || !nativeID || nativeID.length > 4096) throw new WorkerControlError('invalid native conversation ID');
    if (this.nativeID !== undefined && this.nativeID !== nativeID) throw new WorkerControlError('native worker conversation changed');
    await this.#request('native.bind', { native_session_id: nativeID }, 'bound');
    this.nativeID = nativeID;
  }

  async #request(method, params, field) {
    if (this.#failure) throw this.#failure;
    const id = ++this.#serial;
    const frame = Buffer.from(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n');
    if (frame.length > 16384) throw new WorkerControlError('native binding frame is too large');
    return await new Promise((resolve, reject) => {
      this.#pending.set(id, { resolve, reject, field });
      this.socket.write(frame, error => { if (error) this.#fail('native binding write failed (' +
        (typeof error.code === 'string' && /^[A-Z0-9_]+$/.test(error.code) ? error.code : typeof error) + ')'); });
    });
  }

  async cancellationRequested() {
    if (this.nativeID === undefined) throw new WorkerControlError('native context is not bound');
    return await this.#request('native.cancellation', {}, 'requested');
  }

  async reportStopped() {
    if (this.nativeID === undefined) throw new WorkerControlError('native context is not bound');
    await this.#request('native.cancelled', { native_session_id: this.nativeID }, 'recorded');
  }

  close() { this.#fail('native worker control closed'); }
}
