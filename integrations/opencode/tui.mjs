/** OpenCode 1.19.5 TUI companion. This exports only the native TUI entry point. */
import { NativeUiClient, uiParts } from './ui-channel.mjs';
import { presentQuestion } from './question-ui.mjs';
import { holdComponent } from './component-lease.mjs';
import { homedir } from 'node:os';
import { join } from 'node:path';

export default { id: 'xsm-opencode-ui', tui: async api => {
  const profile = process.env.OPENCODE_CONFIG_DIR ??
    join(process.env.XDG_CONFIG_HOME ?? join(homedir(), '.config'), 'opencode');
  const release = await holdComponent(profile);
  api.lifecycle.onDispose(release);
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
