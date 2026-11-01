// Real Node participant used by Python's cross-language integration test.
import { XsmClient } from '../typescript/xsm-client.mjs';

const client = await XsmClient.connect({
  command: [process.env.PYTHON, '-B', '-m', 'xsm', 'protocol', 'serve', '--stdio'],
});
try {
  const session = await client.sessionOpen({ runtime: 'node-cross', profile: 'isolated',
    conversation: 'receiver', cwd: process.cwd(), capabilities: ['messaging', 'events', 'inbox'] });
  await client.eventsSubscribe(session.session);
  process.stdout.write(JSON.stringify({ ref: session.ref }) + '\n');
  const event = await client.nextNotification();
  const inbox = await client.operationCall(session.session, 'xsm_inbox', {});
  if (!JSON.stringify(inbox.messages).includes('Python → Node 요청')) throw new Error('lost request');
  if (inbox.claims.length !== 1 || event.params.ids[0] !== inbox.claims[0].id) throw new Error('wrong claim');
  const claim = inbox.claims[0];
  const ack = await client.operationCall(session.session, 'xsm_ack', { tokens: [claim.token] });
  const sent = await client.operationCall(session.session, 'xsm_send', {
    target: 'ref:' + process.argv[2], text: 'Node → Python 회신', kind: 'reply',
    reply_to: claim.id, outcome: 'succeeded', wait: 0,
  });
  const finished = new Promise(resolve => process.stdin.once('data', resolve));
  process.stdout.write(JSON.stringify({ acked: ack.acked, sent }) + '\n');
  await finished;
} finally {
  process.stdin.pause();
  await client.close();
}
