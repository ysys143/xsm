// Compile-only coverage: .mjs imports must resolve the adjacent .d.mts.
import { XsmClient, XsmHostClient, RpcError, TransportError } from '../typescript/xsm-client.mjs';
import type { EventsAvailable, JsonValue, SessionHandle, Notification } from '../typescript/xsm-client.mjs';
import { XsmHost, RetryAdmission, parseHostCommand, renderInboxPacket, inboxAcknowledgement } from '../typescript/xsm-host.mjs';

export async function example(operation: string, args: { text: string }): Promise<JsonValue> {
  const client = await XsmClient.connect({ onStderr: text => console.error(text) });
  try {
    const opened = await client.sessionOpen({
      runtime: 'node', profile: 'example', conversation: 'example', cwd: '/tmp', capabilities: [],
    });
    const session: SessionHandle = opened.session;
    await client.sessionUpdate(session, { state: 'busy' });
    await client.eventsSubscribe(session);
    const notification = await client.nextNotification();
    if (notification.method === 'events/available') {
      const event = notification as EventsAvailable;
      for (const id of event.params.ids) await client.deliveryReport(event.params.session, id, 'queued');
    }
    const result = await client.operationCall(session, operation, args);
    await client.sessionClose(session);
    return result;
  } catch (error) {
    if (error instanceof RpcError) console.error(error.code, error.data);
    if (error instanceof TransportError) console.error(error.message);
    throw error;
  } finally {
    await client.close();
  }
}

// This function is never executed. The compiler checks invalid callers as well.
function invalid(client: XsmClient) {
  // @ts-expect-error session handle is required
  client.sessionClose();
  // @ts-expect-error non-JSON argument values are not accepted
  client.operationCall('session', 'echo', { callback: () => {} });
  // @ts-expect-error runtime/profile/conversation/cwd are required
  client.sessionOpen({ capabilities: [] });
}
void invalid;

export async function hostExample(event: Notification): Promise<JsonValue> {
  const host = await XsmHostClient.connect();
  try {
    // @ts-expect-error actual display and native source ID are mandatory
    host.respondToDecision(event, { answer: 'blue' });
    return await host.respondToDecision(event, {
      displayed: 'The text shown by the host UI', sourceId: 'native-question-1', answer: 'blue',
    });
  } finally { await host.close(); }
}

function hostBindingTypes(host: XsmHost) {
  const retry = new RetryAdmission('native capacity', 250);
  const delay: number = retry.delayMs;
  void delay;
  const claim = { id: 'example', token: 'opaque' };
  inboxAcknowledgement([claim]);
  renderInboxPacket({ messages: ['example'], claims: [claim] });
  const parsed = parseHostCommand('xsm_inbox {}');
  const result = host.call(parsed.operation, parsed.arguments);
  XsmHost.open({ runtime: 'fixture', profile: 'p', conversation: 'a', cwd: '/tmp', inboxBatchSize: 2, inboxMaxBytes: 524288 });
  XsmHost.open({ runtime: 'fixture', profile: 'p', conversation: 'a', cwd: '/tmp',
    deliver: async () => false });
  // @ts-expect-error only observed idle/busy states are reported by this helper
  host.update('stopped');
  return result;
}
void hostBindingTypes;
