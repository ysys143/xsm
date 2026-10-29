import argparse, hashlib, hmac, ipaddress, json, os, pathlib, signal, socket, stat, subprocess, sys, time
CLI = '/opt/homebrew/bin/codex'
PROFILE = '.codex-3'
MAX_TURN_SECONDS = 150

def json_write(path, data):
    tmp = path.with_suffix(path.suffix + '.new')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    os.chmod(tmp, 384)
    os.replace(tmp, path)

def proc_start(pid):
    import sys
    return sys.modules['no_ssh_v2_proc'].start(pid)

def settings_metadata():
    result = {}
    home = pathlib.Path.home()
    for name in ('.ssh/known_hosts', '.claude/settings.json', '.claude-3/settings.json', '.claude.json', '.codex/config.toml', '.codex-3/config.toml', '.xsm/config.json', '.xsm/homes.json'):
        path = home / name
        if path.exists():
            info = path.stat()
            result[name] = {'size': info.st_size, 'mtime_ns': info.st_mtime_ns, 'mode': stat.S_IMODE(info.st_mode)}
    return result

def native(req, folder):
    folder.mkdir(mode=448, parents=True, exist_ok=True)
    rid = req['id']
    phase = req['phase']
    prompt = req['body']
    schema = {'type': 'object', 'additionalProperties': False, 'required': ['request_id', 'phase', 'claim_valid', 'corrected_sum', 'counterexample'], 'properties': {'request_id': {'type': 'string'}, 'phase': {'type': 'string'}, 'claim_valid': {'type': 'boolean'}, 'corrected_sum': {'type': 'integer'}, 'counterexample': {'type': 'string'}}}
    json_write(folder / 'schema.json', schema)
    (folder / 'instructions.txt').write_text('You are a text-only arithmetic reviewer. Use no tools or network tools. Return only the requested JSON. Compute rather than echo the claim. Do not inspect files or settings.\n')
    (folder / 'request.txt').write_text(prompt)
    env = dict(os.environ)
    removed = []
    for name in list(env):
        if name.startswith('ANTHROPIC_') or name in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'OPENAI_BASE_URL', 'CLAUDE_CODE_OAUTH_TOKEN'):
            removed.append(name)
            env.pop(name, None)
        elif name.startswith(('CLAUDE_', 'CODEX_', 'XSM_')):
            env.pop(name, None)
    env['CODEX_HOME'] = str(pathlib.Path.home() / PROFILE)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['TMPDIR'] = str(folder)
    argv = [CLI, 'exec', '--ignore-user-config', '--ignore-rules', '--ephemeral', '--skip-git-repo-check', '--sandbox', 'read-only', '--json', '--disable', 'hooks', '--disable', 'plugins', '--disable', 'apps', '--disable', 'shell_tool', '--disable', 'shell_snapshot', '--disable', 'remote_plugin', '-c', 'approval_policy="never"', '-c', 'project_doc_max_bytes=0', '-c', 'log_dir=' + json.dumps(str(folder / 'logs')), '-c', 'model_instructions_file=' + json.dumps(str(folder / 'instructions.txt')), '--output-schema', str(folder / 'schema.json'), '--output-last-message', str(folder / 'last-message.json'), '-']
    before = settings_metadata()
    start = time.perf_counter()
    with open(folder / 'stdout.jsonl', 'w') as stdout, open(folder / 'stderr.txt', 'w') as stderr:
        import sys
        launch = str(pathlib.Path(__file__).resolve().parent / 'no-ssh-v2-native-launch.py')
        proc = subprocess.Popen([sys.executable, launch] + argv, cwd=str(folder), env=env, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, text=True, start_new_session=True)
        handle = {'pid': proc.pid, 'lstart': proc_start(proc.pid), 'alive_after_start': proc.poll() is None, 'argv': argv, 'profile': PROFILE}
        json_write(folder / 'handle.json', handle)
        try:
            proc.communicate(prompt, timeout=MAX_TURN_SECONDS)
        except subprocess.TimeoutExpired:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=5)
    elapsed = (time.perf_counter() - start) * 1000
    events = []
    for line in (folder / 'stdout.jsonl').read_text().splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    thread = next((row.get('thread_id') for row in events if row.get('type') == 'thread.started'), None)
    tool_events = [row for row in events if isinstance(row.get('item'), dict) and row['item'].get('type') in ('command_execution', 'mcp_tool_call', 'web_search', 'file_change')]
    try:
        answer = json.loads((folder / 'last-message.json').read_text())
    except (OSError, ValueError):
        answer = None
    valid = proc.returncode == 0 and isinstance(answer, dict) and (answer.get('request_id') == rid) and (answer.get('phase') == phase) and (answer.get('claim_valid') is False) and (answer.get('corrected_sum') == 4) and bool(answer.get('counterexample')) and bool(thread) and (not tool_events)
    result = {'id': 'reply-' + rid + '-' + phase, 'reply_to': rid, 'phase': phase, 'hostname': socket.gethostname(), 'digest': hashlib.sha256(prompt.encode()).hexdigest(), 'actual_agent_task': True, 'status': 'succeeded' if valid else 'failed', 'actual_json_answer': answer, 'native_conversation': thread, 'native_cli': CLI, 'native_cli_version': subprocess.run([CLI, '--version'], capture_output=True, text=True, timeout=10).stdout.strip(), 'subscription_auth': 'preflight native login status: ChatGPT', 'api_key_env_removed_names': removed, 'returncode': proc.returncode, 'native_elapsed_ms': round(elapsed, 3), 'native_handle': handle, 'native_process_exited': proc.poll() is not None, 'tool_events': len(tool_events), 'settings_metadata_before': before, 'settings_metadata_after': settings_metadata(), 'native_continuation': 'fresh ephemeral exec; prior task context supplied in request, not native resume', 'model': 'CLI default; not overridden', 'output_folder': str(folder)}
    json_write(folder / 'result.json', result)
    return result
