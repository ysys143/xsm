import assert from 'node:assert/strict';
import { test } from 'node:test';
import { NativeUiServer, NativeUiClient, uiParts } from '../../integrations/opencode/ui-channel.mjs';

const event = () => ({ method: 'decision/request', params: { questionId: 'question-one',
  question: 'Choose', requestedSchema: { properties: { answer: { enum: ['blue', 'green'] } } },
  expiresAt: Date.now() / 1000 + 5, session: 'private-handle', challenge: 'private-core-challenge' } });
const deferred = () => {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
};

test('native UI frames bind one conversation, one display and a private challenge without exposing host handles',
  { timeout: 5000 }, async () => {
    const frames = [], displays = [];
    let client;
    const server = new NativeUiServer({ send: async (conversation, frame) => {
      frames.push(structuredClone(frame));
      await client.receive(conversation, uiParts(frame));
    } });
    client = new NativeUiClient({ currentConversation: () => 'native-a',
      send: (conversation, frame) => server.receive(conversation, uiParts(frame)),
      present: async (conversation, shown, controls) => {
        controls.onDisplayed();
        displays.push({ conversation, question: shown.params.question });
        return { displayed: shown.params.question, action: 'accept', answer: 'blue' };
      } });
    const answer = await server.present('native-a', event(), { signal: new AbortController().signal });
    assert.equal(answer.answer, 'blue');
    assert.match(answer.sourceId, /^opencode-tui:/);
    assert.deepEqual(displays, [{ conversation: 'native-a', question: 'Choose' }]);
    assert.doesNotMatch(JSON.stringify(frames), /private-handle|private-core-challenge/);
    const offer = frames.find(frame => frame.type === 'offer');
    await client.receive('native-a', uiParts(offer)); // Replayed offer cannot create a second display.
    assert.equal(displays.length, 1);
    assert.equal(server.pending.size, 0);
    await client.close();
    server.close();
  });

test('wrong conversation, nonce, UI instance and non-control text cannot answer a pending question',
  { timeout: 5000 }, async () => {
    const offered = deferred();
    const server = new NativeUiServer({ send: async (_conversation, frame) => offered.resolve(frame) });
    const controller = new AbortController();
    const result = server.present('native-a', event(), { signal: controller.signal });
    const rejected = assert.rejects(result, /cancelled/);
    const offer = await offered.promise;
    const claim = { ...offer, type: 'claim', instance: 'first-ui' };
    await server.receive('native-a', uiParts(claim));
    await server.receive('native-a', uiParts({ ...claim, type: 'displayed', displayed: 'Choose' }));
    const answer = { ...claim, type: 'answer', displayed: 'Choose', action: 'accept', answer: 'blue' };
    await server.receive('native-b', uiParts(answer));
    await server.receive('native-a', uiParts({ ...answer, nonce: 'wrong' }));
    await server.receive('native-a', uiParts({ ...answer, instance: 'second-ui' }));
    const ordinary = uiParts(answer);
    ordinary[0].ignored = false;
    assert.equal(await server.receive('native-a', ordinary), false);
    assert.equal(await server.receive('native-a', [...uiParts(answer), { type: 'text', text: 'ordinary input' }]), false);
    assert.equal(server.pending.size, 1);
    controller.abort();
    await rejected;
  });

test('only the first native UI claims a display and the other window releases its local state',
  { timeout: 5000 }, async () => {
    const shown = deferred(), release = deferred();
    const clients = [];
    const server = new NativeUiServer({ send: async (conversation, frame) => {
      await Promise.all(clients.map(client => client.receive(conversation, uiParts(frame))));
    } });
    const displays = [];
    for (const name of ['first', 'second']) clients.push(new NativeUiClient({
      currentConversation: () => 'native-a', send: (id, frame) => server.receive(id, uiParts(frame)),
      present: async (_id, request, controls) => {
        controls.onDisplayed();
        displays.push(name); shown.resolve(); await release.promise;
        return { displayed: request.params.question, action: 'cancel', answer: null };
      },
    }));
    const result = server.present('native-a', event(), { signal: new AbortController().signal });
    await shown.promise;
    release.resolve();
    assert.equal((await result).action, 'cancel');
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(clients.map(client => client.pending.size), [0, 0]);
    await Promise.all(clients.map(client => client.close()));
    assert.equal(displays.length, 1);
    assert.equal(server.pending.size, 0);
  });

test('UI disconnect and host cancellation reject a live display without accepting its late callback',
  { timeout: 5000 }, async () => {
    for (const cause of ['disconnect', 'host-cancel']) {
      const shown = deferred(), release = deferred();
      let client;
      const server = new NativeUiServer({ send: (id, frame) => client.receive(id, uiParts(frame)) });
      client = new NativeUiClient({ currentConversation: () => 'native-a',
        send: (id, frame) => server.receive(id, uiParts(frame)), present: async (_id, _event, controls) => {
          controls.onDisplayed();
          shown.resolve(); await release.promise;
          return { displayed: 'Choose', action: 'accept', answer: 'blue' };
        } });
      const controller = new AbortController();
      const result = server.present('native-a', event(), { signal: controller.signal });
      const rejected = assert.rejects(result, /could not be displayed|cancelled/);
      await shown.promise;
      if (cause === 'disconnect') await client.close();
      else controller.abort();
      await rejected;
      release.resolve();
      await client.close();
      server.close();
      assert.equal(server.pending.size, 0);
    }
  });

test('an offline native TUI rejects without interpreting silence as an answer', { timeout: 5000 }, async () => {
  const server = new NativeUiServer({ send: async () => {}, claimTimeout: 10 });
  await assert.rejects(server.present('native-a', event(), { signal: new AbortController().signal }), /no connected/);
  assert.equal(server.pending.size, 0);
});

test('a claimed UI that never renders cannot answer the question', { timeout: 5000 }, async () => {
  const offered = deferred();
  const server = new NativeUiServer({ send: async (_id, frame) => offered.resolve(frame), claimTimeout: 20 });
  const result = server.present('native-a', event(), { signal: new AbortController().signal });
  const rejected = assert.rejects(result, /no connected native UI rendered/);
  const offer = await offered.promise;
  const claim = { ...offer, type: 'claim', instance: 'first-ui' };
  await server.receive('native-a', uiParts(claim));
  await server.receive('native-a', uiParts({ ...claim, type: 'answer', displayed: 'Choose', action: 'accept', answer: 'blue' }));
  assert.equal(server.pending.size, 1);
  await rejected;
});
