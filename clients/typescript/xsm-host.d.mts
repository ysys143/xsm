import type { JsonObject, JsonValue, Notification, OpenSessionResult, ConnectOptions } from './xsm-client.mjs';
import { XsmHostClient } from './xsm-client.mjs';

export class RetryAdmission extends Error {
  constructor(message: string, delayMs?: number);
  readonly delayMs: number;
}

export interface InboxClaim extends JsonObject { id: string; token: string; }
export interface InboxPacket extends JsonObject {
  messages: string[];
  claims: InboxClaim[];
  items: { id: string; priority: string; kind: string; wake: boolean }[];
}
export interface HostOptions extends ConnectOptions {
  runtime: string;
  profile: string;
  conversation: string;
  cwd: string;
  inboxBatchSize?: number;
  deliver?: (packet: InboxPacket, options: { wake: boolean; signal: AbortSignal; leaseSeconds: number }) => Promise<void | boolean>;
  present?: (event: Notification, options: { signal: AbortSignal }) => Promise<{
    displayed: string; sourceId: string; answer?: string | null; action?: 'accept' | 'decline' | 'cancel';
  }>;
  onError?: (error: Error) => void;
}
export function parseHostCommand(text: string): { operation: string; arguments: JsonObject };
export function inboxAcknowledgement(claims: readonly Pick<InboxClaim, 'token'>[]): string;
export function renderInboxPacket(packet: Pick<InboxPacket, 'messages' | 'claims'>): string;
export class XsmHost {
  private constructor();
  static open(options: HostOptions): Promise<XsmHost>;
  readonly client: XsmHostClient;
  readonly session: OpenSessionResult;
  readonly operations: { name: string; description: string; inputSchema: JsonObject }[];
  call(operation: string, args?: JsonObject, options?: { signal?: AbortSignal }): Promise<JsonValue>;
  naturalBoundary(): Promise<InboxPacket>;
  update(state: 'idle' | 'busy', name?: string): Promise<JsonValue>;
  close(): Promise<void>;
}
