import assert from 'node:assert/strict';
import { test } from 'node:test';
import { presentQuestion } from '../../integrations/opencode/question-ui.mjs';

function fixture() {
  const lifecycle = new AbortController();
  let current;
  let clears = 0;
  const dialog = {
    get open() { return !!current; },
    replace(render, onClose) { current?.onClose?.(); current = { element: render(), onClose }; },
    clear() { clears += 1; const old = current; current = undefined; old?.onClose?.(); },
  };
  const api = { route: { current: { name: 'session', params: { sessionID: 'native-a' } } },
    lifecycle: { signal: lifecycle.signal }, ui: { dialog,
      DialogSelect: props => ({ kind: 'select', ...props }),
      DialogPrompt: props => ({ kind: 'prompt', ...props }),
    } };
  const event = { method: 'decision/request', params: { question: 'Choose a color\nScope: native-a',
    questionId: 'qid-one', requestedSchema: { properties: { answer: { enum: ['blue', 'green'] } } },
    expiresAt: Date.now() / 1000 + 10 } };
  return { api, event, lifecycle, current: () => current, clears: () => clears };
}

test('OpenCode native selection preserves the exact question and callback source', async () => {
  const { api, event, current } = fixture();
  const result = presentQuestion(api, 'native-a', event);
  const display = current().element;
  assert.equal(display.title, event.params.question);
  assert.deepEqual(display.options, [{ title: 'blue', value: 'blue' }, { title: 'green', value: 'green' }]);
  event.params.question = 'changed after display';
  event.params.questionId = 'different';
  display.onSelect(display.options[0]);
  assert.deepEqual(await result, { displayed: display.title, sourceId: 'opencode-tui:qid-one',
    action: 'accept', answer: 'blue' });
  assert.equal(api.ui.dialog.open, false);
});

test('OpenCode free text and native cancel have distinct outcomes', async () => {
  const { api, event, current } = fixture();
  delete event.params.requestedSchema.properties.answer.enum;
  const reply = presentQuestion(api, 'native-a', event);
  current().element.onConfirm('two  spaces\n다음 줄');
  assert.equal((await reply).answer, 'two  spaces\n다음 줄');
  const cancelled = presentQuestion(api, 'native-a', event);
  current().element.onCancel();
  assert.equal((await cancelled).action, 'cancel');
  assert.equal(api.ui.dialog.open, false);
});

test('a foreign native dialog is never replaced or cleared by an old question callback', async () => {
  const { api, event, current, clears } = fixture();
  const result = presentQuestion(api, 'native-a', event);
  const old = current().element;
  api.ui.dialog.replace(() => ({ kind: 'foreign' }));
  assert.equal((await result).action, 'cancel');
  old.onSelect(old.options[0]);
  assert.equal(current().element.kind, 'foreign');
  assert.equal(clears(), 0);
  await assert.rejects(presentQuestion(api, 'native-a', event), /busy/);
  assert.equal(current().element.kind, 'foreign');
});

test('native conversation switches reject both an open question and its late answer', async () => {
  const { api, event, current } = fixture();
  const result = presentQuestion(api, 'native-a', event);
  const rejected = assert.rejects(result, /context changed|cancelled/);
  const old = current().element;
  api.route.current = { name: 'session', params: { sessionID: 'native-b' } };
  old.onSelect(old.options[0]);
  await rejected;
  await assert.rejects(presentQuestion(api, 'native-a', event), /another conversation/);
});

test('abort, lifecycle shutdown and expired questions never return an accepted answer', async () => {
  for (const cause of ['abort', 'shutdown', 'expiry']) {
    const { api, event, current, lifecycle } = fixture();
    const signal = new AbortController();
    if (cause === 'expiry') event.params.expiresAt = Date.now() / 1000 + .025;
    const result = presentQuestion(api, 'native-a', event, { signal: signal.signal });
    const rejected = assert.rejects(result, /cancelled/);
    const old = current().element;
    if (cause === 'abort') signal.abort();
    if (cause === 'shutdown') lifecycle.abort();
    await rejected;
    old.onSelect(old.options[0]);
    assert.equal(api.ui.dialog.open, false);
  }
});

test('native callbacks cannot submit a value outside the displayed options', async () => {
  const { api, event, current } = fixture();
  const result = presentQuestion(api, 'native-a', event);
  const rejected = assert.rejects(result, /outside/);
  current().element.onSelect({ value: 'forged' });
  await rejected;
});
