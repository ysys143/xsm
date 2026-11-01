/** Pinned native loader/tools with explicit caller fixtures; no agent/model/messenger execution. */
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtemp, mkdir, readdir, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import operations from '../integrations/openclaw/tools.mjs';

const [nativeRoot, output, mode, countText, policyFlag] = process.argv.slice(2);
assert.ok(!mode || ['--execute', '--queue'].includes(mode));
assert.ok(!policyFlag || (mode === '--queue' && ['--deny-injection', '--large-context', '--deferred-notice', '--capacity-retry', '--capacity-fyi', '--burst-context', '--recover-context'].includes(policyFlag)));
const denied = policyFlag === '--deny-injection';
const burstContext = policyFlag === '--burst-context';
const recoverContext = policyFlag === '--recover-context';
const largeContext = policyFlag === '--large-context' || burstContext || recoverContext;
const deferredNotice = policyFlag === '--deferred-notice';
const capacityBoundary = policyFlag === '--capacity-fyi';
const capacityRetry = policyFlag === '--capacity-retry' || capacityBoundary;
const samples = Number(countText ?? 1);
assert.ok(Number.isInteger(samples) && samples >= 1 && samples <= 1000);
assert.ok(!countText || mode === '--queue');
if (!nativeRoot || !output) throw new Error('usage: node probe-openclaw-loader.mjs <native package root> <output.json> [--execute|--queue [samples]]');
const root = fileURLToPath(new URL('../', import.meta.url));
const destination = resolve(output);
const pkg = JSON.parse(await readFile(join(nativeRoot, 'package.json'), 'utf8'));
assert.equal(pkg.version, '2026.10.9');
const temp = await mkdtemp(join(tmpdir(), 'xsm-openclaw-loader-'));
for (const key of Object.keys(process.env)) {
  if (!['PATH', 'LANG', 'TMPDIR'].includes(key)) delete process.env[key];
}
process.env.HOME = join(temp, 'home');
process.env.OPENCLAW_STATE_DIR = join(temp, 'native-state');
process.env.XSM_HOME = join(temp, 'xsm');
process.env.OPENCLAW_NO_RESPAWN = '1';
process.env.PYTHONDONTWRITEBYTECODE = '1';
await mkdir(process.env.OPENCLAW_STATE_DIR);
process.chdir(temp);
// The loader is host internals, used only in this pinned probe, never by the product plugin.
const dist = join(nativeRoot, 'dist');
const candidates = (await readdir(dist)).filter(file => /^loader-runtime-load-.*\.mjs$/.test(file));
assert.equal(candidates.length, 1);
const file = join(dist, candidates[0]);
const text = await readFile(file, 'utf8');
const alias = /loadOpenClawPlugins as (\w+)/.exec(text)?.[1];
assert.ok(alias, 'native loader export was not found');
const native = await import(pathToFileURL(file));
const config = {
  plugins: { enabled: true, allow: ['xsm'], load: { paths: [join(root, 'integrations/openclaw/xsm.mjs')] },
    entries: { xsm: { enabled: true } } }, agents: { defaults: { workspace: temp } },
};
if (mode === '--queue') {
  if (capacityBoundary) config.plugins.entries.xsm.hooks = { allowConversationAccess: true };
  if (denied) config.plugins.entries.xsm.hooks = { allowPromptInjection: false };
  // This fixture exposes the real API proxy to the probe, without a production global.
  const directory = join(temp, 'probe-plugin');
  await mkdir(directory);
  await writeFile(join(directory, 'openclaw.plugin.json'), await readFile(join(root, 'integrations/openclaw/openclaw.plugin.json')));
  const code = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));from xsm import receive;check=receive.check;receive.check=lambda p,m:('block','P2P admission temporarily unavailable: fixture') if p.body.startswith('defer-fixture') else check(p,m);runpy.run_module('xsm',run_name='__main__')";
  const command = deferredNotice ? ['python3', '-B', '-c', code, root, 'protocol', 'serve', '--stdio']
    : [join(root, 'bin/xsm'), 'protocol', 'serve', '--stdio'];
  const source = `import { register } from ${JSON.stringify(pathToFileURL(join(root, 'integrations/openclaw/xsm.mjs')).href)};
    export default { id: 'xsm', register(api) {
      globalThis[Symbol.for('xsm.native.queue.probe')] = api;
      const errors = globalThis[Symbol.for('xsm.native.queue.errors')] = [];
      const logger = { ...api.logger, error(...args) {
        errors.push(args.map(value => String(value)));
        return api.logger.error(...args);
      } };
      register({ ...api, logger }, { command: ${JSON.stringify(command)} });
    } };`;
  const entry = join(directory, 'entry.mjs');
  await writeFile(entry, source);
  config.plugins.load.paths = [entry];
}
const registry = native[alias]({ config, workspaceDir: temp, cache: false, activate: true, onlyPluginIds: ['xsm'] });
const plugin = registry.plugins.find(item => item.id === 'xsm');
assert.equal(plugin?.status, 'loaded', JSON.stringify(registry.diagnostics));
assert.deepEqual(registry.diagnostics.filter(item => item.pluginId === 'xsm'), []);
const tools = registry.tools.filter(item => item.pluginId === 'xsm');
assert.deepEqual(tools.flatMap(item => item.names).sort(), operations.map(item => item.name).sort());
for (const tool of tools) assert.equal(tool.factory({}), null);
await assert.rejects(readdir(join(temp, 'xsm/sessions')), { code: 'ENOENT' });
const result = { status: 'incomplete', runtimeVersion: pkg.version, node: process.version,
  platform: process.platform, arch: process.arch,
  largeContext,
  nativeLoader: true, nativeTools: tools.length, metadataCreatedNoParticipant: true,
  nativeToolExecution: false, nativeUnloadTested: false, modelCalls: 0,
  physicalHumanUiTested: false, diagnostics: registry.diagnostics, root: temp,
  nativeDeliveryErrors: globalThis[Symbol.for('xsm.native.queue.errors')] ?? [] };
if (mode) {
  // Resolve pinned host-internal exports by their original names, not guessed minified aliases.
  async function nativeFunction(prefix, name) {
    const files = (await readdir(dist)).filter(file => file.startsWith(prefix) && file.endsWith('.mjs'));
    for (const nameFile of files) {
      const path = join(dist, nameFile);
      const source = await readFile(path, 'utf8');
      const symbol = new RegExp(name + ' as (\\w+)').exec(source)?.[1];
      if (symbol) return (await import(pathToFileURL(path)))[symbol];
    }
    throw new Error('native export missing: ' + name);
  }
  const dispose = await nativeFunction('runtime-', 'disposePluginRegistryInstances');
  try {
    const resolveTools = await nativeFunction('tools-', 'resolvePluginTools');
    const context = id => ({ config, workspaceDir: temp,
      sessionId: id, sessionKey: mode === '--queue' ? 'agent:main:' + id : 'agent:main:fixture',
      ...(mode === '--queue' ? { agentId: 'main' } : {}) });
    const api = mode === '--queue' ? globalThis[Symbol.for('xsm.native.queue.probe')] : undefined;
    if (mode === '--queue') assert.ok(api?.runtime?.agent?.session);
    if (api) {
      for (const id of ['native-fixture-a', 'native-fixture-b']) {
        await api.runtime.agent.session.upsertSessionEntry({ agentId: 'main', sessionKey: context(id).sessionKey,
          entry: { sessionId: id, updatedAt: Date.now() } });
      }
      if (denied) {
        const { nativeDelivery } = await import(pathToFileURL(join(root, 'integrations/openclaw/context-queue.mjs')));
        assert.equal(nativeDelivery(api, context('native-fixture-b'), () => {}), undefined);
        result.nativeInjectionPolicyDenied = true;
        result.registrationPromptPolicy = api.config.plugins?.entries?.xsm?.hooks?.allowPromptInjection ?? null;
        result.runtimePromptPolicy = api.runtime.config.current()?.plugins?.entries?.xsm?.hooks?.allowPromptInjection ?? null;
      }
    }
    const resolve = id => resolveTools({ context: context(id),
      runtimeRegistry: registry, toolAllowlist: ['xsm'] });
    const executable = resolve('native-fixture-a');
    assert.equal(executable.length, operations.length);
    const inbox = executable.find(tool => tool.name === 'xsm_inbox');
    const packet = await inbox.execute('native-inbox', { limit: 1 }, new AbortController().signal);
    assert.equal(packet.details.claims.length, 0);
    result.nativeToolExecution = true;
    result.explicitCallerFixture = true;
    const files = (await readdir(join(temp, 'xsm/sessions'))).filter(file => file.endsWith('.json'));
    assert.equal(files.length, 1);
    const record = JSON.parse(await readFile(join(temp, 'xsm/sessions', files[0]), 'utf8'));
    assert.equal(record.runtime, 'openclaw');
    result.nativeRef = record.ref;
    result.protocolPython = { version: record.protocol_python_version, executable: record.protocol_python };
    const records = async () => Promise.all((await readdir(join(temp, 'xsm/sessions')))
      .filter(file => file.endsWith('.json'))
      .map(async file => JSON.parse(await readFile(join(temp, 'xsm/sessions', file), 'utf8'))));
    const second = resolve('native-fixture-b');
    const inboxB = second.find(tool => tool.name === 'xsm_inbox');
    await inboxB.execute('open-b', {});
    const rows = await records();
    assert.equal(rows.length, 2);
    const target = rows.find(row => row.ref !== record.ref);
    assert.ok(target, 'same route must keep separate native conversation identities');
    if (recoverContext) {
      const errors = globalThis[Symbol.for('xsm.native.queue.errors')];
      const previousErrors = errors.length;
      process.kill(target.pid, 'SIGKILL');
      const deadline = Date.now() + 5000;
      while (errors.length === previousErrors && Date.now() < deadline) {
        await new Promise(resolve => setTimeout(resolve, 10));
      }
      assert.ok(errors.length > previousErrors, 'native host did not observe backend exit');
      await inboxB.execute('recover-b', {});
      const recovered = (await records()).find(row => row.ref === target.ref);
      assert.ok(recovered);
      assert.notEqual(recovered.pid, target.pid);
      assert.notEqual(recovered.protocol_generation, target.protocol_generation);
      result.nativeBackendRecovery = { sameRef: true, newGeneration: true, newPid: true,
        trigger: 'explicit native inbox tool after observed transport exit', automaticIdleReconnect: false };
    }

    if (capacityRetry) {
      await api.runtime.agent.session.patchSessionEntry({ agentId: 'main', sessionKey: context('native-fixture-b').sessionKey,
        update: row => ({ pluginNextTurnInjections: { ...row.pluginNextTurnInjections,
          xsm: Array.from({ length: 32 }, (_, index) => ({ id: 'capacity-fixture-' + index, pluginId: 'xsm',
            text: 'fixture reserved slot', placement: 'prepend_context', createdAt: Date.now(), ttlMs: 60000,
            metadata: { capacityFixture: true } })) } }) });
    }
    if (deferredNotice) {
      await executable.find(tool => tool.name === 'xsm_send').execute('send-deferred', {
        target: 'ref:' + target.ref, text: 'defer-fixture original', wait: 0,
      });
      let notice;
      const deadline = Date.now() + 5000;
      while (Date.now() < deadline) {
        const row = api.runtime.agent.session.getSessionEntry({ agentId: 'main',
          sessionKey: context('native-fixture-b').sessionKey, readConsistency: 'latest' });
        notice = row?.pluginNextTurnInjections?.xsm?.[0];
        if (notice) break;
        await new Promise(resolve => setTimeout(resolve, 10));
      }
      assert.ok(notice?.text.includes('awaits network revalidation'));
      assert.equal(notice.text.includes('After reading, call xsm_ack'), false);
      const drain = await nativeFunction('host-hook-state-', 'drainPluginNextTurnInjectionContext');
      const prompt = await drain({ cfg: config, agentId: 'main', sessionKey: context('native-fixture-b').sessionKey });
      assert.ok(prompt.prependContext.includes(notice.text));
      const retained = await inboxB.execute('deferred-still-pending', { limit: 1 });
      assert.equal(retained.details.claims.length, 0);
      assert.ok(retained.details.messages.some(text => text.includes('awaits network revalidation')));
      result.nativeClaimFreeNotice = true;
    }
    const sampleText = index => 'OpenClaw native factory fixture message sample-' + index + '-end' +
      (largeContext ? '\n \t' + '한글🚀 '.repeat(16000) + '\n\t ' : '');
    if (burstContext) {
      const sentAt = [], seen = new Set(), latencies = [];
      result.burst = { requested: samples, consumed: 0, acknowledged: 0, groups: [], milliseconds: latencies,
        measured: 'sender execute start through prompt-helper consumption after deliberately preloading the entire burst',
        queueLatencyCertification: false };
      for (let index = 0; index < samples; index++) {
        sentAt.push(performance.now());
        await executable.find(tool => tool.name === 'xsm_send').execute('burst-send-' + index, {
          target: 'ref:' + target.ref, text: sampleText(index), wait: 0,
        });
      }
      const drain = await nativeFunction('host-hook-state-', 'drainPluginNextTurnInjectionContext');
      const deadline = Date.now() + 20000;
      while (seen.size < samples && Date.now() < deadline) {
        const prompt = await drain({ cfg: config, agentId: 'main', sessionKey: context('native-fixture-b').sessionKey });
        if (!prompt.queuedInjections.length) { await new Promise(resolve => setTimeout(resolve, 10)); continue; }
        const groups = new Map();
        for (const item of prompt.queuedInjections) {
          assert.ok(item.text.length <= 32768);
          assert.ok(prompt.prependContext.includes(item.text));
          if (!groups.has(item.metadata.xsmHash)) groups.set(item.metadata.xsmHash, []);
          groups.get(item.metadata.xsmHash).push(item);
        }
        const tokens = [], observedAt = performance.now();
        let originals = 0;
        for (const group of groups.values()) {
          group.sort((a, b) => a.metadata.fragmentIndex - b.metadata.fragmentIndex);
          assert.equal(group.length, group[0].metadata.fragmentCount);
          const body = group.map(item => item.text.slice(item.metadata.fragmentHeaderLength,
            item.metadata.fragmentHeaderLength + item.metadata.fragmentBodyLength)).join('');
          let matched = 0;
          for (let index = 0; index < samples; index++) {
            if (!body.includes(sampleText(index))) continue;
            assert.ok(!seen.has(index), 'native burst duplicated an already consumed original');
            seen.add(index); matched++; latencies.push(observedAt - sentAt[index]);
          }
          assert.equal(matched, group[0].metadata.messageIds.length);
          const last = group[group.length - 1];
          const claims = JSON.parse(/xsm_ack with tokens: (\[[^\n]*?\])/.exec(last.text)[1]);
          assert.equal(claims.length, matched);
          tokens.push(...claims); originals += matched;
          result.burst.groups.push({ originals: matched, fragments: group.length });
        }
        result.burst.observedBeforeAck = seen.size;
        let ack;
        try { ack = await second.find(tool => tool.name === 'xsm_ack').execute('burst-consume-' + seen.size, { tokens }); }
        catch (error) {
          // This snapshot is collected only after the failed ACK. Earlier tokens
          // in a multi-token ACK may already have been acknowledged.
          const claimAudit = [];
          const requestedIDs = new Set(prompt.queuedInjections.flatMap(item => item.metadata.messageIds));
          for (const folder of await readdir(join(temp, 'xsm/handoffs'), { withFileTypes: true })) {
            if (!folder.isDirectory()) continue;
            for (const id of requestedIDs) {
              const path = join(temp, 'xsm/handoffs', folder.name, id + '.json');
              let original;
              try { original = JSON.parse(await readFile(path, 'utf8')); }
              catch (readError) { if (readError.code === 'ENOENT') continue; throw readError; }
              claimAudit.push({ id, state: original.state, token: original.claim?.token,
                previousToken: original.previous_claim?.token, deliveryState: original.delivery_state });
            }
          }
          result.burst.claimAuditAfterAckFailure = { tokens, originals: claimAudit };
          throw error;
        }
        assert.equal(ack.details.acked.length, originals);
        result.burst.consumed = seen.size;
        result.burst.acknowledged += ack.details.acked.length;
        await writeFile(destination, JSON.stringify(result, null, 2) + '\n');
      }
      assert.equal(seen.size, samples, 'native burst did not drain all retained originals');
      assert.equal(result.burst.acknowledged, samples);
      result.nativeQueuePromptConsumed = true;
      result.nativeQueueExplicitAck = true;
      result.nativeWakeTested = false;
    } else {
      const started = performance.now();
      const firstText = sampleText(0);
      result.lastSend = await executable.find(tool => tool.name === 'xsm_send').execute('send-a-b', {
        target: 'ref:' + target.ref, text: firstText, wait: 0,
        ...(capacityBoundary ? { wake: 'never' } : {}),
      });
      if (capacityBoundary) {
        const { getGlobalHookRunner } = await import(pathToFileURL(join(nativeRoot, 'dist/plugin-sdk/plugin-runtime.js')));
        const hooks = getGlobalHookRunner();
        assert.ok(hooks?.hasHooks('agent_end'));
        await hooks.runAgentEnd({ messages: [], success: true, durationMs: 0 }, context('native-fixture-b'));
        result.nativeFyiBoundaryReturned = true;
      }
      if (capacityRetry) {
        // Read-only inspection of this probe's canonical store proves an attempted admission was released.
        const code = "import json,sys;sys.path.insert(0,sys.argv[1]);from xsm.handoff import _folder;print(_folder(json.loads(sys.argv[2])))";
        const folder = execFileSync('python3', ['-B', '-c', code, root, JSON.stringify(target)],
          { env: process.env, encoding: 'utf8' }).trim();
        let released = false;
        const deadline = Date.now() + 5000;
        while (Date.now() < deadline) {
          const records = await Promise.all((await readdir(folder)).filter(name => name.endsWith('.json'))
            .map(async name => JSON.parse(await readFile(join(folder, name), 'utf8'))));
          if (records.some(row => row.previous_claim && row.state !== 'acknowledged')) { released = true; break; }
          await new Promise(resolve => setTimeout(resolve, 10));
        }
        assert.ok(released, 'capacity refusal never returned the canonical original');
        await api.runtime.agent.session.patchSessionEntry({ agentId: 'main', sessionKey: context('native-fixture-b').sessionKey,
          update(row) {
            const queued = row.pluginNextTurnInjections.xsm;
            assert.equal(queued.length, 32);
            assert.ok(queued.every(item => item.metadata.capacityFixture));
            return { pluginNextTurnInjections: { ...row.pluginNextTurnInjections, xsm: [] } };
          } });
        result.nativeCapacityClaimReleased = true;
      }
      let tokens;
      const latencies = [];
      if (api && !denied) {
        result.admission = { requestedSamples: samples, samples: 0, milliseconds: latencies };
        result.nativeQueueAckCount = 0;
        result.fragmentCounts = [];
        async function consume(started, expected) {
          const until = Date.now() + 5000;
          let injection, queued;
          while (Date.now() < until) {
            const row = api.runtime.agent.session.getSessionEntry({ agentId: 'main',
              sessionKey: context('native-fixture-b').sessionKey, readConsistency: 'latest' });
            queued = row?.pluginNextTurnInjections?.xsm ?? [];
            injection = queued[0];
            if (injection) break;
            await new Promise(resolve => setTimeout(resolve, 10));
          }
          if (!injection) {
            const entry = api.runtime.agent.session.getSessionEntry({ agentId: 'main', sessionKey: context('native-fixture-b').sessionKey, readConsistency: 'latest' });
            result.failedQueueObservation = { sessions: await records(), lastSend: result.lastSend,
              nativeSessionId: entry?.sessionId, lifecycleRevision: entry?.lifecycleRevision,
              queuedCount: entry?.pluginNextTurnInjections?.xsm?.length ?? 0 };
          }
          assert.ok(injection, 'actual native context queue did not accept the original');
          const group = queued.filter(item => item.metadata.xsmHash === injection.metadata.xsmHash)
            .sort((a, b) => a.metadata.fragmentIndex - b.metadata.fragmentIndex);
          assert.equal(group.length, injection.metadata.fragmentCount);
          if (largeContext) assert.ok(group.length > 1, 'large sample did not exercise fragmentation');
          result.fragmentCounts.push(group.length);
          const body = entries => entries.map(item => item.text.slice(item.metadata.fragmentHeaderLength,
            item.metadata.fragmentHeaderLength + item.metadata.fragmentBodyLength)).join('');
          assert.ok(body(group).includes(expected), 'native queue accepted another sample');
          assert.ok(group.every(item => item.text.length <= 32768));
          latencies.push(performance.now() - started);
          result.admission.samples = latencies.length;
          const drain = await nativeFunction('host-hook-state-', 'drainPluginNextTurnInjectionContext');
          const prompt = await drain({ cfg: config, agentId: 'main', sessionKey: context('native-fixture-b').sessionKey });
          assert.match(prompt.prependContext, /native factory fixture message/);
          assert.ok(body(prompt.queuedInjections).includes(expected), 'native prompt consumed another sample');
          assert.deepEqual(prompt.queuedInjections.map(item => item.id), group.map(item => item.id));
          for (const item of group) assert.ok(prompt.prependContext.includes(item.text), 'native prompt changed fragment whitespace');
          result.nativeFragmentCount = group.length;
          result.nativeFragmentTextLengths = group.map(item => item.text.length);
          result.expectedOriginalUtf16Length = expected.length;
          const tokens = JSON.parse(/xsm_ack with tokens: (\[[^\n]*?\])/.exec(prompt.prependContext)[1]);
          assert.equal(tokens.length, 1);
          const again = await drain({ cfg: config, agentId: 'main', sessionKey: context('native-fixture-b').sessionKey });
          assert.equal(again.queuedInjections.length, 0);
          await writeFile(destination, JSON.stringify(result, null, 2) + '\n');
          return tokens;
        }
        tokens = await consume(started, firstText);
        for (let index = 1; index < samples; index++) {
          const ack = await second.find(tool => tool.name === 'xsm_ack').execute('consume-' + index, { tokens });
          assert.equal(ack.details.acked.length, 1);
          result.nativeQueueAckCount++;
          const began = performance.now();
          const text = sampleText(index);
          result.lastSend = await executable.find(tool => tool.name === 'xsm_send').execute('send-' + index, {
            target: 'ref:' + target.ref, text, wait: 0,
          });
          assert.match(result.lastSend.details?.text ?? '', /stored/, 'send was refused before native admission');
          tokens = await consume(began, text);
        }
        const sorted = [...latencies].sort((a, b) => a - b);
        assert.equal(latencies.length, samples);
        result.admission = { requestedSamples: samples, samples: latencies.length, milliseconds: latencies,
          p95UpperBoundMs: sorted[Math.ceil(sorted.length * .95) - 1],
          measured: 'native sender execute start through observed native context queue; includes canonical store time' };
        result.nativeQueuePromptConsumed = true;
        if (capacityRetry) result.nativeCapacityRetryRecovered = true;
        if (capacityBoundary) result.nativeFyiBoundaryRetryRecovered = true;
        result.nativeWakeTested = false;
      } else {
        const received = await inboxB.execute('receive-b', { limit: 1 });
        assert.equal(received.details.claims.length, 1);
        assert.match(JSON.stringify(received.details.messages), /native factory fixture message/);
        tokens = received.details.claims.map(claim => claim.token);
      }
      const ack = await second.find(tool => tool.name === 'xsm_ack').execute('consume-b', {
        tokens,
      });
      assert.equal(ack.details.acked.length, 1);
      if (api && !denied) {
        result.nativeQueueAckCount++;
        assert.equal(result.nativeQueueAckCount, samples);
        if (samples >= 100) {
          result.admission.passesOneSecondDeadline = result.admission.p95UpperBoundMs < 1000;
          assert.ok(result.admission.passesOneSecondDeadline, 'native admission p95 exceeds one second');
        }
      }
      result.nativeDmPullAck = !api || denied;
      result.nativeQueueExplicitAck = Boolean(api) && !denied;
      if (denied) {
        const row = api.runtime.agent.session.getSessionEntry({ agentId: 'main',
          sessionKey: context('native-fixture-b').sessionKey, readConsistency: 'latest' });
        assert.equal(row.pluginNextTurnInjections?.xsm?.length ?? 0, 0);
      }
    }
    await assert.rejects(executable.find(tool => tool.name === 'xsm_decide').execute('unbound-ui', {
      question: 'Native fixture question', options: ['blue', 'green'],
    }), /no user-interface/);
    result.unboundUiRefused = true;
    const { getGlobalHookRunner } = await import(pathToFileURL(join(nativeRoot, 'dist/plugin-sdk/plugin-runtime.js')));
    const hooks = getGlobalHookRunner();
    assert.ok(hooks?.hasHooks('session_end'));
    await hooks.runSessionEnd({ sessionId: 'native-fixture-a', sessionKey: context('native-fixture-a').sessionKey,
      messageCount: 0, reason: 'reset' }, context('native-fixture-a'));
    assert.ok((await records()).find(row => row.ref === record.ref).ended_at);
    await assert.rejects(inbox.execute('late-a', {}), /no longer current/);
    const resumed = resolve('native-fixture-a').find(tool => tool.name === 'xsm_inbox');
    await resumed.execute('resume-a', {});
    const after = (await records()).find(row => row.ref === record.ref);
    assert.notEqual(after.protocol_generation, record.protocol_generation);
    assert.ok(!after.ended_at);
    result.nativeSessionEndResume = true;
    result.status = 'passed';
  } catch (error) {
    result.status = 'failed';
    result.error = error.message;
    throw error;
  } finally {
    try {
      const cleanup = await dispose(registry);
      assert.deepEqual(cleanup.failures, []);
      result.nativeUnloadTested = true;
      const sessionFiles = await readdir(join(temp, 'xsm/sessions')).catch(error => {
        if (error.code === 'ENOENT') return [];
        throw error;
      });
      for (const file of sessionFiles.filter(file => file.endsWith('.json'))) {
        const record = JSON.parse(await readFile(join(temp, 'xsm/sessions', file), 'utf8'));
        assert.ok(record.ended_at, 'native disposal left a live participation');
      }
    } catch (error) {
      result.status = 'failed'; result.cleanupError = error.message; throw error;
    } finally {
      await writeFile(destination, JSON.stringify(result, null, 2) + '\n');
    }
  }
} else {
  result.status = 'passed';
}
await writeFile(destination, JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify(result));
