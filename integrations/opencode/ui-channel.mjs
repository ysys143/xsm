/** Native UI control frames. Ignored synthetic parts never become model input. */
import { randomUUID } from 'node:crypto';

export function uiParts(frame) {
  return [{ type: 'text', text: '', ignored: true, synthetic: true,
    metadata: { xsmUi: { ...frame, version: 1 } } }];
}

function frames(parts) {
  return parts.filter(part => part.type === 'text' && part.ignored === true && part.synthetic === true &&
    part.text === '' && part.metadata?.xsmUi?.version === 1).map(part => part.metadata.xsmUi);
}

export class NativeUiServer {
  constructor({ send, claimTimeout = 3000, onError = () => {} }) {
    this.send = send;
    this.claimTimeout = claimTimeout;
    this.onError = onError;
    this.pending = new Map();
    this.closed = false;
  }

  present(conversation, event, { signal }) {
    if (this.closed || signal.aborted) return Promise.reject(new Error('native UI request cancelled'));
    const { questionId, expiresAt, question, requestedSchema } = event.params;
    if (this.pending.has(questionId)) return Promise.reject(new Error('native UI question is already pending'));
    return new Promise((resolve, reject) => {
      const pending = { conversation, questionId, nonce: randomUUID(), instance: null,
        display: { params: { questionId, expiresAt, question, requestedSchema } } };
      const finish = (result, error) => {
        if (this.pending.get(questionId) !== pending) return;
        this.pending.delete(questionId);
        clearTimeout(pending.claimTimer);
        clearTimeout(pending.expiryTimer);
        signal.removeEventListener('abort', cancel);
        if (error) {
          reject(error);
          if (pending.instance) this.send(conversation, { type: 'cancel', questionId,
            nonce: pending.nonce, instance: pending.instance }).catch(this.onError);
        } else resolve(result);
      };
      pending.finish = finish;
      const cancel = () => finish(undefined, new Error('native UI request cancelled'));
      signal.addEventListener('abort', cancel, { once: true });
      pending.claimTimer = setTimeout(() => finish(undefined, new Error('no connected native UI rendered the question')),
        this.claimTimeout);
      pending.expiryTimer = setTimeout(() => finish(undefined, new Error('native UI question expired')),
        Math.max(1, expiresAt * 1000 - Date.now()));
      this.pending.set(questionId, pending);
      Promise.resolve().then(() => this.pending.get(questionId) === pending &&
        this.send(conversation, { type: 'offer', questionId, nonce: pending.nonce, expiresAt }))
        .catch(error => finish(undefined, error));
    });
  }

  async receive(conversation, parts) {
    const controls = frames(parts);
    if (controls.length !== parts.length) return false;
    for (const frame of controls) {
      const pending = this.pending.get(frame.questionId);
      if (!pending || pending.conversation !== conversation || pending.nonce !== frame.nonce ||
          typeof frame.instance !== 'string' || !frame.instance) continue;
      if (frame.type === 'claim' && !pending.instance) {
        pending.instance = frame.instance;
        try {
          await this.send(conversation, { type: 'question', questionId: frame.questionId,
            nonce: pending.nonce, instance: frame.instance, event: pending.display });
        } catch (error) { pending.finish(undefined, error); }
      } else if (frame.type === 'claim' && frame.instance !== pending.instance) {
        await this.send(conversation, { type: 'cancel', questionId: frame.questionId,
          nonce: pending.nonce, instance: frame.instance }).catch(this.onError);
      } else if (frame.type === 'displayed' && frame.instance === pending.instance &&
                 frame.displayed === pending.display.params.question) {
        pending.displayed = true;
        clearTimeout(pending.claimTimer);
      } else if (frame.type === 'answer' && frame.instance === pending.instance && pending.displayed) {
        pending.finish({ displayed: frame.displayed, action: frame.action, answer: frame.answer,
          sourceId: 'opencode-tui:' + frame.instance + ':' + frame.questionId });
      } else if (frame.type === 'failed' && frame.instance === pending.instance) {
        pending.finish(undefined, new Error('native question could not be displayed'));
      }
    }
    return controls.length > 0;
  }

  close(conversation) {
    if (conversation === undefined) this.closed = true;
    for (const pending of [...this.pending.values()]) {
      if (conversation === undefined || pending.conversation === conversation) {
        pending.finish(undefined, new Error('native UI host closed'));
      }
    }
  }
}

export class NativeUiClient {
  constructor({ send, present, currentConversation, onError = () => {} }) {
    this.send = send;
    this.present = present;
    this.currentConversation = currentConversation;
    this.onError = onError;
    this.instance = randomUUID();
    this.pending = new Map();
    this.seen = new Set();
    this.closed = false;
  }

  async receive(conversation, parts) {
    if (this.closed) return;
    for (const frame of frames(parts)) {
      if (typeof frame.questionId !== 'string' || typeof frame.nonce !== 'string') continue;
      const current = this.pending.get(frame.questionId);
      const key = frame.questionId + ':' + frame.nonce;
      if (frame.type === 'offer' && conversation === this.currentConversation() && !current && !this.seen.has(key)) {
        this.seen.add(key);
        const pending = { conversation, nonce: frame.nonce, controller: new AbortController(), shown: false };
        pending.timer = setTimeout(() => {
          if (this.pending.get(frame.questionId) === pending) {
            pending.controller.abort();
            this.pending.delete(frame.questionId);
          }
        }, 5000);
        this.pending.set(frame.questionId, pending);
        try {
          await this.send(conversation, { type: 'claim', questionId: frame.questionId,
            nonce: frame.nonce, instance: this.instance });
        } catch (error) { clearTimeout(pending.timer); this.pending.delete(frame.questionId); this.onError(error); }
      } else if (frame.type === 'question' && current && frame.instance !== this.instance &&
                 current.conversation === conversation && current.nonce === frame.nonce) {
        current.controller.abort();
        clearTimeout(current.timer);
        this.pending.delete(frame.questionId);
      } else if (current && frame.instance === this.instance && current.conversation === conversation &&
                 current.nonce === frame.nonce) {
        if (frame.type === 'cancel') {
          current.controller.abort();
          clearTimeout(current.timer);
          this.pending.delete(frame.questionId);
        } else if (frame.type === 'question' && !current.shown) {
          current.shown = true;
          clearTimeout(current.timer);
          // Do not await a human answer inside the event bus/claim POST callback.
          current.task = (async () => {
            try {
              if (this.currentConversation() !== conversation || frame.event?.params?.questionId !== frame.questionId) {
                throw new Error('native UI context changed before display');
              }
              let displayed;
              const reply = await this.present(conversation, frame.event, { signal: current.controller.signal,
                onDisplayed: () => {
                  if (!displayed) {
                    displayed = this.send(conversation, { type: 'displayed', questionId: frame.questionId,
                      nonce: frame.nonce, instance: this.instance, displayed: frame.event.params.question });
                    displayed.catch(() => current.controller.abort());
                  }
                } });
              if (!displayed) throw new Error('native UI did not report rendering the question');
              await displayed;
              if (current.controller.signal.aborted || this.closed) return;
              if (this.currentConversation() !== conversation) throw new Error('native UI conversation changed after display');
              await this.send(conversation, { type: 'answer', questionId: frame.questionId, nonce: frame.nonce,
                instance: this.instance, displayed: reply.displayed, action: reply.action, answer: reply.answer });
            } catch (error) {
              if (!current.controller.signal.aborted && !this.closed) {
                await this.send(conversation, { type: 'failed', questionId: frame.questionId,
                  nonce: frame.nonce, instance: this.instance }).catch(this.onError);
                this.onError(error);
              }
            } finally {
              if (this.pending.get(frame.questionId) === current) this.pending.delete(frame.questionId);
            }
          })();
        }
      }
    }
  }

  async close() {
    this.closed = true;
    const notifications = [];
    for (const [questionId, pending] of this.pending) {
      pending.controller.abort();
      clearTimeout(pending.timer);
      if (pending.shown) notifications.push(this.send(pending.conversation, { type: 'failed', questionId,
        nonce: pending.nonce, instance: this.instance }));
    }
    this.pending.clear();
    await Promise.allSettled(notifications);
  }
}
