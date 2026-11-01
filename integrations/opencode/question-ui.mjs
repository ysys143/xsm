/** OpenCode 1.19.5 TUI callbacks. Transport and protocol policy stay outside the renderer. */
const active = new WeakMap();

export function presentQuestion(api, conversation, event, { signal, onDisplayed } = {}) {
  const params = structuredClone(event.params);
  const { question, questionId, requestedSchema, expiresAt } = params;
  const choices = requestedSchema?.properties?.answer?.enum;
  const current = () => api.route.current.name === 'session' &&
    api.route.current.params?.sessionID === conversation;
  if (!current()) return Promise.reject(new Error('native UI is showing another conversation'));
  if (signal?.aborted || api.lifecycle.signal.aborted || expiresAt * 1000 <= Date.now()) {
    return Promise.reject(new Error('native question is no longer active'));
  }
  if (typeof question !== 'string' || !question || typeof questionId !== 'string' ||
      !Number.isFinite(expiresAt) || (choices !== undefined &&
        (!Array.isArray(choices) || !choices.length || choices.some(value => typeof value !== 'string')))) {
    return Promise.reject(new Error('invalid native question display request'));
  }
  const dialog = api.ui.dialog;
  if (dialog.open || active.has(dialog)) return Promise.reject(new Error('native UI is busy with another dialog'));
  return new Promise((resolve, reject) => {
    const state = { visible: true };
    active.set(dialog, state);
    let finished = false;
    let watcher;
    const finish = (answer, error, clear = true) => {
      if (finished) return;
      finished = true;
      clearInterval(watcher);
      signal?.removeEventListener('abort', cancel);
      api.lifecycle.signal.removeEventListener('abort', cancel);
      if (clear && state.visible && active.get(dialog) === state) {
        try { dialog.clear(); } catch (failure) { error = failure; }
      }
      if (active.get(dialog) === state) active.delete(dialog);
      if (error) reject(error);
      else resolve({ displayed: question, sourceId: 'opencode-tui:' + questionId,
        action: answer === undefined ? 'cancel' : 'accept', answer: answer ?? null });
    };
    const cancel = () => finish(undefined, new Error('native question cancelled'));
    const submit = answer => {
      if (!current() || signal?.aborted || api.lifecycle.signal.aborted || expiresAt * 1000 <= Date.now()) {
        finish(undefined, new Error('native question context changed before answer'));
      } else if (typeof answer !== 'string' || (choices && !choices.includes(answer))) {
        finish(undefined, new Error('native selection is outside the displayed choices'));
      } else finish(answer);
    };
    const closed = () => { state.visible = false; finish(undefined, undefined, false); };
    signal?.addEventListener('abort', cancel, { once: true });
    api.lifecycle.signal.addEventListener('abort', cancel, { once: true });
    watcher = setInterval(() => {
      if (!current() || expiresAt * 1000 <= Date.now()) cancel();
    }, 50);
    try {
      let rendered = false;
      dialog.replace(() => {
        const element = choices ? api.ui.DialogSelect({ title: question, skipFilter: true,
          options: choices.map(value => ({ title: value, value })), onSelect: option => submit(option.value) })
          : api.ui.DialogPrompt({ title: question, onConfirm: submit, onCancel: () => finish(undefined) });
        if (!rendered) { rendered = true; onDisplayed?.(); }
        return element;
      }, closed);
    } catch (error) { finish(undefined, error); }
  });
}
