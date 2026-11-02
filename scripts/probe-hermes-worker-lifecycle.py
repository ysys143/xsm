#!/usr/bin/env python3
"""Actual native parent tool call and public child lifecycle; no XSM provider claim."""
import argparse, hashlib, json, logging, os, subprocess, sys, tempfile, time, urllib.request
from urllib.parse import urlsplit
from pathlib import Path
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--native-source', type=Path, required=True)
parser.add_argument('--model', required=True, help='Exact model ID from the existing local subscription proxy catalog')
parser.add_argument('--base-url', default='http://127.0.0.1:10100/v1')
parser.add_argument('--mode', choices=('complete', 'cancel'), default='complete')
parser.add_argument('--output', type=Path, required=True)
options = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
source = options.native_source.resolve()
out = options.output.absolute()
nonce = os.urandom(4).hex()
if out.exists():
    parser.error('output must be new; preserve previous evidence')
url = urlsplit(options.base_url)
if url.scheme != 'http' or url.hostname != '127.0.0.1' or url.username or url.password or url.query or url.fragment or (url.path != '/v1'):
    parser.error('an existing loopback /v1 subscription proxy is required')
actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
if actual != subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'v0.22.5^{}'], text=True).strip():
    parser.error('pinned Hermes v0.22.5 checkout required')
if subprocess.run(['git', '-C', str(source), 'diff', '--quiet', 'HEAD']).returncode:
    parser.error('native tracked source must match its tag')
with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(options.base_url + '/models', timeout=10) as response:
    catalog = json.load(response)
if not any((row.get('id') == options.model for row in catalog.get('data', []))):
    parser.error('model is absent from the live local catalog')
profile = Path(tempfile.mkdtemp(prefix='xsm-hermes-native-worker-'))
profile.chmod(0o700)
home = profile / 'home'
home.mkdir(mode=0o700)
env = {k: os.environ[k] for k in ('PATH', 'LANG', 'TMPDIR') if k in os.environ}
os.environ.clear()
os.environ.update(env, HOME=str(home), HERMES_HOME=str(profile), XSM_HOME=str(profile / 'xsm-state'), TERMINAL_CWD=str(home), PYTHONDONTWRITEBYTECODE='1')
os.chdir(home)
sys.path.insert(0, str(source))
logging.disable(logging.CRITICAL)
settings = {'model': {'default': options.model, 'provider': 'custom', 'base_url': options.base_url, 'api_key': 'local-proxy-placeholder', 'api_mode': 'chat_completions'}, 'fallback_providers': [], 'agent': {'max_turns': 6, 'max_tokens': 1536, 'skip_context_files': True, 'background_review': {'enabled': False}}, 'memory': {'enabled': False}, 'plugins': {'enabled': []}, 'terminal': {'cwd': str(home)}}
(profile / 'config.yaml').write_text(json.dumps(settings, indent=2) + '\n')
(profile / 'config.yaml').chmod(0o600)
out.mkdir(parents=True, exist_ok=False)
report = {'status': 'starting', 'started_at': time.time(), 'scope': 'actual Hermes parent model/tool and native public child lifecycle, not XSM owned provider', 'telegram_send': False, 'mode': options.mode, 'nativeSourceCommit': actual, 'checks': []}

def save():
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')

def check(name, value):
    if not value:
        raise AssertionError(name)
    report['checks'].append(name)
    save()
try:
    from hermes_cli import plugins
    from hermes_cli.plugins_manifest import PluginManifest
    from run_agent import AIAgent
    from agent.subagent_lifecycle import SubagentState, SubagentLifecycleError, get_active_subagent_parent
    manager = plugins.get_plugin_manager()
    context = plugins.PluginContext(PluginManifest(name='xsm-worker-probe', version='dev', source='user', path=str(profile)), manager)

    def native_worker(args, *, session_id='', **native):
        check('native dispatcher has the actual active parent', get_active_subagent_parent() is not None and get_active_subagent_parent().session_id == session_id)
        if report.get('child_launched'):
            raise RuntimeError('probe child was already launched; do not replay')
        lifecycle = context.subagent_lifecycle
        if options.mode == 'cancel':
            for field, value in (('working_directory', str(home)), ('timeout_seconds', 10), ('blocked_tools', ('terminal',))):
                try:
                    unexpected = lifecycle.launch({'goal': 'must not launch unsupported options', field: value})
                except SubagentLifecycleError:
                    check('native unsupported ' + field + ' rejected', True)
                else:
                    lifecycle.cancel(unexpected, reason='unsupported option unexpectedly accepted')
                    raise AssertionError('native unsupported option accepted')
        handle = lifecycle.launch({'goal': 'Reply exactly XSM_HERMES_CHILD_' + nonce + '. Do not use tools.', 'role': 'leaf', 'parent_session_id': session_id, 'correlation_id': 'xsm-native-child-' + nonce})
        report['child_launched'] = True
        report['child_model'] = handle.model
        report['child_provider'] = handle.provider
        report['child_id_fingerprint'] = hashlib.sha256(handle.subagent_id.encode()).hexdigest()[:12]
        save()
        private = profile / 'child-handle.json'
        private.write_text(json.dumps(handle.to_dict()))
        private.chmod(0o600)
        try:
            status = lifecycle.status(handle)
            report['initial_child_state'] = status.state.value
            if options.mode == 'cancel':
                deadline = time.monotonic() + 5
                while status.state in (SubagentState.PENDING, SubagentState.STARTING) and time.monotonic() < deadline:
                    time.sleep(0.01)
                    status = lifecycle.status(handle)
                report['state_before_cancel'] = status.state.value
                cancellation = lifecycle.cancel(handle, reason='user-authorized isolated native stop probe')
                report['cancel_accepted'] = cancellation.accepted
                report['cancel_already_terminal'] = cancellation.already_terminal
                report['cancel_unsupported'] = cancellation.unsupported
                save()
                check('native owned-child cancellation accepted', cancellation.accepted and (not cancellation.already_terminal))
            terminal = lifecycle.wait(handle, timeout_seconds=60)
            report['child_terminal_state'] = terminal.state.value
            if not terminal.completed:
                report['cancel_accepted'] = lifecycle.cancel(handle, reason='probe deadline').accepted
                save()
                raise TimeoutError('native child did not finish')
            result = lifecycle.result(handle)
            report['child_api_calls'] = result.usage_metadata.get('api_calls')
            report['child_result_hash_present'] = bool(result.result_hash)
            if options.mode == 'cancel':
                check('native child reached confirmed cancelled terminal', terminal.completed and terminal.state == SubagentState.CANCELLED and result.ready)
            else:
                check('native child completed', terminal.state == SubagentState.SUCCEEDED and result.ready)
                check('native child returned actual expected nonce', 'XSM_HERMES_CHILD_' + nonce in (result.summary or ''))
                check('same-process native handle reconnects', lifecycle.reconnect(handle).connected)
            check('terminal cancellation does not claim a new stop', lifecycle.cancel(handle, reason='probe terminal cleanup').already_terminal)
            if options.mode == 'complete':
                try:
                    unexpected = lifecycle.launch({'goal': 'must not launch duplicate', 'parent_session_id': session_id, 'correlation_id': 'xsm-native-child-' + nonce})
                except SubagentLifecycleError:
                    check('duplicate correlation refused before another child', True)
                else:
                    lifecycle.cancel(unexpected, reason='duplicate unexpectedly accepted')
                    raise AssertionError('duplicate correlation accepted')
            return json.dumps({'status': 'passed', 'cancelled': True} if options.mode == 'cancel' else {'status': 'passed', 'child_nonce': 'XSM_HERMES_CHILD_' + nonce})
        except BaseException:
            lifecycle.cancel(handle, reason='probe failed; stop only its owned child')
            raise
    context.register_tool(name='xsm_probe_native_worker', toolset='xsm-worker-probe', schema={'name': 'xsm_probe_native_worker', 'description': 'Run one user-authorized isolated native worker lifecycle probe. Call once only.', 'parameters': {'type': 'object', 'properties': {}, 'additionalProperties': False}}, handler=native_worker, description='Isolated native worker lifecycle probe')
    agent = AIAgent(model=options.model, provider='custom', base_url=options.base_url, api_key='local-proxy-placeholder', api_mode='chat_completions', enabled_toolsets=['xsm-worker-probe'], max_iterations=6, max_tokens=1536, quiet_mode=True, skip_context_files=True, skip_memory=True, skip_background_review=True, save_trajectories=False, load_soul_identity=False, cwd=str(home), run_budget_seconds=90)
    result = agent.run_conversation('Your user authorizes this isolated test. Find and call xsm_probe_native_worker exactly once using native tools. Do not invent its result. If it succeeds, reply XSM_HERMES_NATIVE_LIFECYCLE_READY_' + nonce + '. If it fails, report failure and do not retry it.')
    report['parent_api_calls'] = result.get('api_calls')
    report['requested_model'] = result.get('requested_model')
    report['served_model'] = result.get('served_model')
    report['parent_completed'] = result.get('completed')
    report['parent_failed'] = result.get('failed')
    report['parent_tool_trace'] = [{'name': m.get('name') or m.get('tool_name'), 'error': 'error' in str(m.get('content', '')).lower()} for m in result.get('messages', []) if isinstance(m, dict) and m.get('role') == 'tool']
    check('actual parent turn invoked native lifecycle', report.get('child_launched') is True)
    check('parent model completed without failure', result.get('completed') is True and (not result.get('failed')))
    check('actual parent final contains confirmation', 'XSM_HERMES_NATIVE_LIFECYCLE_READY_' + nonce in (result.get('final_response') or ''))
    report['status'] = 'passed'
except BaseException as error:
    report.update(status='failed', failure_type=type(error).__name__)
report['finished_at'] = time.time()
save()
print(json.dumps(report), flush=True)
raise SystemExit(0 if report['status'] == 'passed' else 1)
