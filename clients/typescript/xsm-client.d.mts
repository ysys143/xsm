/** JSON-compatible values only; no runtime dependencies or TS compilation needed. */
export type JsonValue = null | boolean | number | string | JsonValue[] | JsonObject;
export interface JsonObject { [key: string]: JsonValue; }
export type SessionHandle = string;
export interface OpenSessionParams {
  runtime: string;
  profile: string;
  conversation: string;
  cwd: string;
  capabilities?: string[];
}
export type OpenSessionResult = JsonObject & {
  address?: string;
  session: SessionHandle;
  generation: JsonValue;
};
export interface Notification {
  jsonrpc: '2.0';
  method: string;
  params?: JsonObject;
}
export interface EventsAvailable extends Notification {
  method: 'events/available';
  params: { session: SessionHandle; ids: string[] };
}
export interface ConnectOptions {
  command?: readonly string[];
  cwd?: string;
  /** Replaces the child environment; omit to inherit. */
  env?: Record<string, string | undefined>;
  /** Synchronous stderr chunk consumer; defaults to process.stderr.write. */
  onStderr?: (text: string) => unknown;
  /** Grace period in milliseconds before each termination step. Default 1000. */
  closeTimeout?: number;
  /** Initialize response deadline in milliseconds. Default 10000. */
  initializeTimeout?: number;
}
export class TransportError extends Error {}
export class RpcError extends Error {
  code: number;
  data: JsonValue | undefined;
  constructor(code: number, message: string, data?: JsonValue);
}
export class XsmClient {
  protected constructor();
  static readonly DEFAULT_COMMAND: readonly string[];
  static connect(options?: ConnectOptions): Promise<XsmClient>;
  readonly initialization: JsonValue;
  request(method: string, params?: JsonObject): Promise<JsonValue>;
  sessionOpen(params: OpenSessionParams): Promise<OpenSessionResult>;
  sessionUpdate(session: SessionHandle, updates: JsonObject): Promise<JsonValue>;
  sessionClose(session: SessionHandle): Promise<JsonValue>;
  operationCall(session: SessionHandle, operation: string, args: JsonObject): Promise<JsonValue>;
  prepareFiles(session: SessionHandle, params: {
    target: string; request_id: string; text: string;
    entries: Array<{ name: string; data: Uint8Array; source_version?: string }>;
    previous_manifest?: string; attachment_fallback?: 'inline';
  }): Promise<JsonObject>;
  eventsSubscribe(session: SessionHandle): Promise<JsonValue>;
  deliveryReport(session: SessionHandle, id: string, state: string, token?: string): Promise<JsonValue>;
  nextNotification(): Promise<Notification>;
  close(): Promise<void>;
}
export class XsmHostClient extends XsmClient {
  static connect(options?: ConnectOptions): Promise<XsmHostClient>;
  abandonDecision(event: Notification): Promise<JsonValue>;
  respondToDecision(event: Notification, response: {
    displayed: string; sourceId: string; answer?: string | null;
    action?: 'accept' | 'decline' | 'cancel';
  }): Promise<JsonValue>;
}
