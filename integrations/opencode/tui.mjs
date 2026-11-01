/** OpenCode 1.19.5 TUI companion. This exports only the native TUI entry point. */
import { NativeUiClient, uiParts } from './ui-channel.mjs';
import { presentQuestion } from './question-ui.mjs';

export default { id: 'xsm-opencode-ui', tui: async api => {
  const error = failure => api.ui.toast({ title: 'xsm', message: failure.message, variant: 'error' });
  const channel = new NativeUiClient({
    currentConversation: () => api.route.current.name === 'session' ? api.route.current.params.sessionID : undefined,
    present: (conversation, event, controls) => presentQuestion(api, conversation, event, controls),
    send: async (sessionID, frame) => {
      const result = await api.client.session.prompt({ sessionID, noReply: true, parts: uiParts(frame) });
      if (result.error) throw new Error('native UI callback transport failed');
    }, onError: error,
  });
  const off = api.event.on('message.part.updated', event => {
    const part = event.properties.part;
    void channel.receive(part.sessionID, [part]).catch(error);
  });
  api.lifecycle.onDispose(async () => { off(); await channel.close(); });
} };
